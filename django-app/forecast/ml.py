# ML logic for the app: load the saved models once and answer the questions about tomorrow in Cairo
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX

MODEL_PATH = Path(__file__).resolve().parent.parent / "ml_models" / "weather_model.pkl"

# loaded once, when Django starts; every request reuses it
MODEL = joblib.load(MODEL_PATH)

# how many past days the app needs: 3 for the temperature models, more for "warm days in a row"
HISTORY_DAYS = 120

RAINY_MONTHS = [10, 11, 12, 1, 2, 3, 4]
TEMPERATURES = ["temp_max", "temp_mean", "temp_min"]


def make_exog(index, K=3):
    # same as the notebook: a level, a slow trend (in decades since 1990) and the season as sine/cosine
    day = index.dayofyear
    exog = pd.DataFrame(index=index)
    exog["const"] = 1.0
    exog["trend"] = (index - pd.Timestamp("1990-01-01")).days / 3652.5
    for k in range(1, K + 1):
        exog["sin_" + str(k)] = np.sin(2 * np.pi * k * day / 365.25)
        exog["cos_" + str(k)] = np.cos(2 * np.pi * k * day / 365.25)
    return exog


def normal(column, day):
    # the normal value of a column for this day of the year (1990-2019, as in the notebook)
    return MODEL["normals"][column][pd.Timestamp(day).dayofyear]


def forecast_temperature(column, today, last_3_values, steps=1):
    # rebuild the saved model from its numbers, give it the last 3 days (its memory), forecast `steps` days ahead
    today = pd.Timestamp(today)
    last_3_days = pd.date_range(end=today, periods=3, freq="D")
    future_days = pd.date_range(today + pd.Timedelta(days=1), periods=steps, freq="D")
    numbers = MODEL["temperature_models"][column]

    model = SARIMAX(np.array(last_3_values, dtype=float), exog=make_exog(last_3_days, MODEL["K"]).values, order=MODEL["order"])
    result = model.filter(np.array(numbers["params"]))
    forecast = result.get_forecast(steps=steps, exog=make_exog(future_days, MODEL["K"]).values)

    # the last step is the day we want
    lower, upper = forecast.conf_int(alpha=0.05)[-1]
    return {"forecast": float(forecast.predicted_mean[-1]), "lower": float(lower), "upper": float(upper)}


def heat_inputs_today(history):
    # the same 12 inputs as Q3 in the notebook, for the last day of the history
    today = history.index[-1]
    temp_max = history["temp_max"]
    max_vs_normal = temp_max - np.array([normal("temp_max", day) for day in history.index])

    # how many days in a row, up to today, the max was above its normal
    warm_days_in_a_row = 0
    for value in reversed(max_vs_normal.values):
        if value > 0:
            warm_days_in_a_row += 1
        else:
            break

    inputs = {
        "temp_max_today": temp_max.iloc[-1],
        "temp_max_yesterday": temp_max.iloc[-2],
        "temp_max_2_days_ago": temp_max.iloc[-3],
        "temp_max_vs_normal": max_vs_normal.iloc[-1],
        "temp_max_change_3d": temp_max.iloc[-1] - temp_max.iloc[-4],
        "warm_days_in_a_row": warm_days_in_a_row,
        "humidity_vs_normal": history["humidity"].iloc[-1] - normal("humidity", today),
        "pressure_vs_normal": history["pressure"].iloc[-1] - normal("pressure", today),
        "pressure_change_3d": history["pressure"].iloc[-1] - history["pressure"].iloc[-4],
        "wind_vs_normal": history["wind_speed"].iloc[-1] - normal("wind_speed", today),
        "day_sin": np.sin(2 * np.pi * today.dayofyear / 365.25),
        "day_cos": np.cos(2 * np.pi * today.dayofyear / 365.25),
    }
    # the same order the model learned them in
    return np.array([inputs[name] for name in MODEL["heat_warning"]["inputs"]], dtype=float)


def very_hot_warning(history):
    # chance of a very hot day (max > 40.1 °C) 1, 2 and 3 days after the last known day (Q3)
    today = history.index[-1]
    inputs = heat_inputs_today(history)
    days = []
    for lead in [1, 2, 3]:
        part = MODEL["heat_warning"]["leads"][lead]
        # the logistic regression written out: scale the inputs, weight them, squash to a chance
        scaled = (inputs - np.array(part["scaler_mean"])) / np.array(part["scaler_scale"])
        chance = 1 / (1 + np.exp(-(part["intercept"] + scaled @ np.array(part["coef"]))))
        days.append({
            "date": (today + pd.Timedelta(days=lead)).date(),
            "chance": float(chance),
            "warning": bool(chance >= part["threshold"]),
        })
    return days


def storm_and_rain(history):
    # the signs from 9.5 and 9.6 on the last known day, and what they meant in 2016-2025
    today = history.index[-1]
    in_season = today.month in RAINY_MONTHS
    rain_mm = float(history["precipitation"].iloc[-1])
    rain_today = rain_mm >= 1
    pressure_change = float(history["pressure"].iloc[-1] - history["pressure"].iloc[-2])
    pressure_falling = pressure_change < 0

    if not in_season:
        storm_situation = "Outside the rainy season"
    elif not rain_today:
        storm_situation = "Rainy season, dry today"
    elif pressure_falling:
        storm_situation = "Rainy season, rain today, pressure falling"
    else:
        storm_situation = "Rainy season, rain today, pressure not falling"

    rain_situation = ("Rainy season" if in_season else "Outside the rainy season") + (", rain today" if rain_today else ", dry today")
    storm_table = MODEL["storm_chance"][storm_situation]
    rain_table = MODEL["rain_chance"][rain_situation]

    return {
        "in_season": in_season,
        "rain_mm": rain_mm,
        "rain_today": rain_today,
        "pressure_change": pressure_change,
        "storm_today": rain_mm >= 10,
        # how many days like today there were in 2016-2025, and how many were followed by a storm or by rain
        "storm": {"situation": storm_situation, "days": storm_table["Days"], "count": storm_table["Storms tomorrow"], "chance": storm_table["Chance (%)"]},
        "rain": {"situation": rain_situation, "days": rain_table["Days"], "count": rain_table["Rain tomorrow"], "chance": rain_table["Chance (%)"]},
    }


def analyze(history, target_day=None):
    # everything the app shows, from the history up to the last known day
    history = history.iloc[-HISTORY_DAYS:]
    today = history.index[-1]
    target_day = pd.Timestamp(target_day) if target_day is not None else today + pd.Timedelta(days=1)
    steps = (target_day - today).days

    temperature = {}
    for column in TEMPERATURES:
        result = forecast_temperature(column, today, history[column].iloc[-3:].values, steps)
        result["normal"] = float(normal(column, target_day))
        temperature[column] = result

    return {
        "today": today.date(),
        "target_day": target_day.date(),
        "steps": steps,
        "temperature": temperature,
        "very_hot": very_hot_warning(history),
        **storm_and_rain(history),
        "last_days": history.iloc[-3:],
    }


def expected_for_date(column, day):
    # the model's own "normal" for a date: the yearly season plus the warming trend, without the last days
    numbers = MODEL["temperature_models"][column]
    exog = make_exog(pd.DatetimeIndex([pd.Timestamp(day)]), MODEL["K"]).values[0]
    weights = np.array(numbers["params"][:len(exog)])
    return float(exog @ weights)


def explain_temperature(column, today, last_3_values, steps=1):
    # split a forecast into two parts: what the date alone gives, and what the last 3 days add
    today = pd.Timestamp(today)
    target_day = today + pd.Timedelta(days=steps)
    forecast = forecast_temperature(column, today, last_3_values, steps)["forecast"]
    expected = expected_for_date(column, target_day)
    last_3_days = pd.date_range(end=today, periods=3, freq="D")
    return {
        "expected": expected,
        "memory": forecast - expected,
        "forecast": forecast,
        # how far each of the last 3 days was from the model's normal for its date
        "last_days": [{"date": day.date(), "value": float(value), "difference": float(value) - expected_for_date(column, day)}
                      for day, value in zip(last_3_days, last_3_values)],
        # how much of today's difference the model keeps for tomorrow (the first AR weight)
        "keeps": float(MODEL["temperature_models"][column]["params"][len(make_exog(last_3_days[:1], MODEL["K"]).columns)]),
    }


def feels_like(temp, humidity, wind_ms):
    # apparent temperature (Steadman): humid air feels warmer, wind feels cooler
    vapour = humidity / 100 * 6.105 * np.exp(17.27 * temp / (237.7 + temp))
    return float(temp + 0.33 * vapour - 0.70 * wind_ms - 4.00)