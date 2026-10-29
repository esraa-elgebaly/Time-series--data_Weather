# Patterns from the project's own data: Cairo's storms, the signs before them, and very hot days by year.
# Worked out once when Django starts, with the same definitions as the notebooks.
import math

import numpy as np
import pandas as pd

from .ml import MODEL, make_exog, normal
from .weather_data import DATA

STORM_DAYS = pd.to_datetime([storm["date"] for storm in MODEL["storm_list"]])
ONE_DAY = pd.Timedelta(days=1)


def storm_history():
    # every storm (first day of rain >= 10 mm, 2016-2025) and the signs on the day before it
    pressure_change = DATA["pressure"].diff()
    storms = []
    for day in STORM_DAYS:
        before = day - ONE_DAY
        rain_before = DATA.loc[before, "precipitation"] >= 1
        falling_before = pressure_change.loc[before] < 0
        storms.append({
            "date": day.date(),
            "day_before": before.date(),
            "rain_mm": float(DATA.loc[day, "precipitation"]),
            "rain_before_mm": float(DATA.loc[before, "precipitation"]),
            "rain_before": bool(rain_before),
            "pressure_falling_before": bool(falling_before),
            # the 9.5 rule: rain and falling pressure the day before
            "warned": bool(rain_before and falling_before),
        })
    return storms


def pre_storm_pattern():
    # the average of each sign from 3 days before a storm to the storm day, compared with normal
    pressure_change = DATA["pressure"].diff() * 10  # kPa to hPa
    rows = []
    for offset, label in [(-3, "3 days before"), (-2, "2 days before"), (-1, "Day before"), (0, "Storm day")]:
        days = STORM_DAYS + pd.Timedelta(days=offset)
        rows.append({
            "label": label,
            "rain_mm": float(DATA.loc[days, "precipitation"].mean()),
            "rain_days": int((DATA.loc[days, "precipitation"] >= 1).sum()),
            "pressure_change": float(pressure_change.loc[days].mean()),
            "humidity_vs_normal": float(sum(DATA.loc[d, "humidity"] - normal("humidity", d) for d in days) / len(days)),
            "max_vs_normal": float(sum(DATA.loc[d, "temp_max"] - normal("temp_max", d) for d in days) / len(days)),
        })
    return rows


def very_hot_by_year():
    # Task 4's very hot days (max > 40.1 °C) in each year
    counts = (DATA["temp_max"] > 40.1).groupby(DATA.index.year).sum()
    most = counts.max()
    return [{"year": int(year), "count": int(count), "height": round(100 * count / most)} for year, count in counts.items()]


def usual_rain_chance():
    # how often a day in each month had rain (>= 1 mm) in 2016-2025, in %
    rain_years = DATA.loc["2016":"2025", "precipitation"]
    chance = 100 * (rain_years >= 1).groupby(rain_years.index.month).mean()
    return {int(month): float(value) for month, value in chance.items()}


STORMS = storm_history()
PRE_STORM = pre_storm_pattern()
VERY_HOT_BY_YEAR = very_hot_by_year()
USUAL_RAIN_CHANCE = usual_rain_chance()

STORM_SUMMARY = {
    "total": len(STORMS),
    "after_rain": sum(storm["rain_before"] for storm in STORMS),
    "warned": sum(storm["warned"] for storm in STORMS),
    "after_dry_day": sum(not storm["rain_before"] for storm in STORMS),
}

# very hot days a year: the first ten years against the last ten (Task 4, H2)
HOT_FIRST_DECADE = sum(row["count"] for row in VERY_HOT_BY_YEAR if row["year"] <= 1999) / 10
HOT_LAST_DECADE = sum(row["count"] for row in VERY_HOT_BY_YEAR if row["year"] >= 2016) / 10


# ---- for the Storm outlook page ----

RAINY_SEASON_MONTHS = [10, 11, 12, 1, 2, 3, 4]
STORM_YEARS = range(2016, 2026)


def month_outlook():
    # for each month of the rainy season: storms seen in 2016-2025, and the chance of at least one storm in a coming year
    outlook = []
    for month in RAINY_SEASON_MONTHS:
        storms = int((STORM_DAYS.month == month).sum())
        per_year = storms / len(STORM_YEARS)
        # storms come one by one and rarely, so the chance of at least one is 1 - e^(-storms per year)
        chance = 100 * (1 - math.exp(-per_year))
        outlook.append({"month": month, "storms": storms, "per_year": per_year, "chance": chance})
    return outlook


def storms_by_season():
    # storms in each full rainy season (October to April) seen in the data
    seasons = []
    for start in range(2016, 2025):
        first = pd.Timestamp(start, 10, 1)
        last = pd.Timestamp(start + 1, 4, 30)
        count = int(((STORM_DAYS >= first) & (STORM_DAYS <= last)).sum())
        seasons.append({"label": f"{start}/{str(start + 1)[2:]}", "count": count})
    most = max(season["count"] for season in seasons)
    for season in seasons:
        season["height"] = round(100 * season["count"] / most) if most else 0
    return seasons


def storms_by_year():
    counts = [int((STORM_DAYS.year == year).sum()) for year in STORM_YEARS]
    most = max(counts)
    return [{"year": year, "count": count, "height": round(100 * count / most)} for year, count in zip(STORM_YEARS, counts)]


def heat_projection():
    # very hot days a year: a straight line through 1990-2025, carried on to 2030, with a 95 % range for one year
    years = np.array([row["year"] for row in VERY_HOT_BY_YEAR])
    counts = np.array([row["count"] for row in VERY_HOT_BY_YEAR])
    slope, intercept = np.polyfit(years, counts, 1)
    spread = (counts - (intercept + slope * years)).std(ddof=2)
    rows = []
    for year in range(2026, 2031):
        expected = intercept + slope * year
        rows.append({"year": year, "expected": expected, "low": max(expected - 1.96 * spread, 0), "high": expected + 1.96 * spread})
    return {"per_decade": 10 * slope, "years": rows}


MONTH_OUTLOOK = month_outlook()
SEASONS = storms_by_season()
STORMS_BY_YEAR = storms_by_year()
HEAT_PROJECTION = heat_projection()
STORMS_PER_YEAR = len(STORMS) / len(STORM_YEARS)
FIRST_HALF_PER_YEAR = sum(row["count"] for row in STORMS_BY_YEAR if row["year"] <= 2020) / 5
SECOND_HALF_PER_YEAR = sum(row["count"] for row in STORMS_BY_YEAR if row["year"] >= 2021) / 5


# ---- how accurate the model is, on the test years it never saw (2023-2025) ----

TEST_DAYS = pd.date_range("2023-01-01", "2025-12-30")


def one_day_forecasts(column):
    # the same one-day-ahead forecast as forecast_temperature, for every day at once:
    # usual for tomorrow + the AR weights times how far the last 3 days were from their usual value
    params = np.array(MODEL["temperature_models"][column]["params"])
    exog = make_exog(DATA.index, MODEL["K"]).values
    usual = pd.Series(exog @ params[:exog.shape[1]], index=DATA.index)
    gap = DATA[column] - usual
    weights = params[exog.shape[1]:exog.shape[1] + 3]
    forecast = usual.shift(-1) + weights[0] * gap + weights[1] * gap.shift(1) + weights[2] * gap.shift(2)
    # one day ahead, the 95 % range is the forecast plus or minus 1.96 times the noise of the model
    half_range = 1.96 * math.sqrt(params[-1])
    return forecast, half_range


def temperature_accuracy():
    rows = []
    for column, name in [("temp_max", "Max (day)"), ("temp_mean", "Average"), ("temp_min", "Min (night)")]:
        forecast, half_range = one_day_forecasts(column)
        real = DATA[column].shift(-1).loc[TEST_DAYS]
        error = (real - forecast.loc[TEST_DAYS]).abs()
        persistence = (real - DATA[column].loc[TEST_DAYS]).abs()
        rows.append({
            "name": name,
            "mae": float(error.mean()),
            "within_1": float(100 * (error <= 1).mean()),
            "within_2": float(100 * (error <= 2).mean()),
            "over_3": float(100 * (error > 3).mean()),
            "worst": float(error.max()),
            "inside_range": float(100 * (error <= half_range).mean()),
            "persistence": float(persistence.mean()),
            "better": float(100 * (1 - error.mean() / persistence.mean())),
        })
    return rows


def heat_warning_accuracy():
    # Q3 one day ahead on the test years: the same 12 inputs as the notebook, for every day at once
    max_vs_normal = DATA["temp_max"] - np.array([normal("temp_max", day) for day in DATA.index])
    warm = (max_vs_normal > 0).astype(int)
    warm_days_in_a_row = warm.groupby((warm == 0).cumsum()).cumsum()

    def vs_normal(column):
        return DATA[column] - np.array([normal(column, day) for day in DATA.index])

    inputs = pd.DataFrame({
        "temp_max_today": DATA["temp_max"],
        "temp_max_yesterday": DATA["temp_max"].shift(1),
        "temp_max_2_days_ago": DATA["temp_max"].shift(2),
        "temp_max_vs_normal": max_vs_normal,
        "temp_max_change_3d": DATA["temp_max"].diff(3),
        "warm_days_in_a_row": warm_days_in_a_row,
        "humidity_vs_normal": vs_normal("humidity"),
        "pressure_vs_normal": vs_normal("pressure"),
        "pressure_change_3d": DATA["pressure"].diff(3),
        "wind_vs_normal": vs_normal("wind_speed"),
        "day_sin": np.sin(2 * np.pi * DATA.index.dayofyear / 365.25),
        "day_cos": np.cos(2 * np.pi * DATA.index.dayofyear / 365.25),
    })[MODEL["heat_warning"]["inputs"]].loc[TEST_DAYS]

    part = MODEL["heat_warning"]["leads"][1]
    scaled = (inputs.values - np.array(part["scaler_mean"])) / np.array(part["scaler_scale"])
    chance = 1 / (1 + np.exp(-(part["intercept"] + scaled @ np.array(part["coef"]))))
    warning = chance >= part["threshold"]
    very_hot = (DATA["temp_max"].shift(-1).loc[TEST_DAYS] > 40.1).values
    return {
        "very_hot_days": int(very_hot.sum()),
        "caught": int((warning & very_hot).sum()),
        "false_alarms": int((warning & ~very_hot).sum()),
    }


TEMPERATURE_ACCURACY = temperature_accuracy()
HEAT_ACCURACY = heat_warning_accuracy()