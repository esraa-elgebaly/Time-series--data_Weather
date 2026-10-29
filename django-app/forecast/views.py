import calendar
import datetime
import math

import pandas as pd
from django.shortcuts import render
from django.utils import timezone

from . import history
from .forms import ManualForm, PastDayForm
from .ml import MODEL, analyze, expected_for_date, explain_temperature, feels_like, forecast_temperature, normal
from .weather_data import DATA, LAST_PAST_DAY, WeatherDataError, history_from_csv, history_from_nasa, what_happened

FORECAST_DAYS = 5


def temperature_level(temp):
    # a simple label for the colors, from the mean temperature
    if temp < 15:
        return "cold"
    if temp < 22:
        return "mild"
    if temp < 28:
        return "warm"
    return "hot"


def day_condition(rain_mm, temp_max, temp_mean):
    # what a known day was like, from the measured values only
    if rain_mm >= 10:
        return {"name": "Storm", "icon": "bi-cloud-lightning-rain", "level": "storm"}
    if rain_mm >= 1:
        return {"name": "Rain", "icon": "bi-cloud-rain", "level": "rain"}
    if temp_max > 40.1:
        return {"name": "Very hot and dry", "icon": "bi-thermometer-sun", "level": "hot"}
    level = temperature_level(temp_mean)
    looks = {
        "cold": {"name": "Cool and dry", "icon": "bi-cloud-sun"},
        "mild": {"name": "Mild and dry", "icon": "bi-cloud-sun"},
        "warm": {"name": "Warm and dry", "icon": "bi-sun"},
        "hot": {"name": "Hot and dry", "icon": "bi-sun"},
    }
    return {**looks[level], "level": level}


def forecast_condition(rain_chance, temp_mean):
    # what a forecast day will probably be like, from the rain chance and the temperature
    if rain_chance >= 30:
        return {"name": "Rain likely", "icon": "bi-cloud-rain", "level": "rain"}
    if rain_chance >= 10:
        return {"name": "Rain possible", "icon": "bi-cloud-drizzle", "level": "rain"}
    level = temperature_level(temp_mean)
    looks = {
        "cold": {"name": "Cool", "icon": "bi-cloud-sun"},
        "mild": {"name": "Mild", "icon": "bi-cloud-sun"},
        "warm": {"name": "Warm", "icon": "bi-sun"},
        "hot": {"name": "Hot", "icon": "bi-sun"},
    }
    return {**looks[level], "level": level}


def chance_level(chance, low, high):
    # turn a chance (%) into a word and a color
    if chance >= high:
        return {"word": "High", "color": "high"}
    if chance >= low:
        return {"word": "Possible", "color": "medium"}
    return {"word": "Low", "color": "low"}


def latest_conditions(days):
    # the last known day, shown like "current weather"
    today = days.index[-1]
    row = days.iloc[-1]
    return {
        "date": today.date(),
        "temp_mean": float(row["temp_mean"]),
        "temp_max": float(row["temp_max"]),
        "temp_min": float(row["temp_min"]),
        "humidity": float(row["humidity"]),
        "wind_kmh": float(row["wind_speed"]) * 3.6,
        "pressure_hpa": float(row["pressure"]) * 10,
        "pressure_change_hpa": float(row["pressure"] - days["pressure"].iloc[-2]) * 10,
        "rain_mm": float(row["precipitation"]),
        "normal_mean": float(normal("temp_mean", today)),
        "feels_like": feels_like(row["temp_mean"], row["humidity"], row["wind_speed"]),
        "condition": day_condition(row["precipitation"], row["temp_max"], row["temp_mean"]),
    }


def five_day_forecast(days, first_day, tomorrow_rain_chance, show_real):
    # max, mean and min for 5 days, starting at first_day; far days use the usual rain chance of their month
    today = days.index[-1]
    forecast = []
    for number in range(FORECAST_DAYS):
        day = pd.Timestamp(first_day) + pd.Timedelta(days=number)
        steps = (day - today).days
        temps = {column: forecast_temperature(column, today, days[column].iloc[-3:].values, steps) for column in ["temp_max", "temp_mean", "temp_min"]}

        # only the day right after the last known day has a rain chance from today's signs (9.6)
        if steps == 1 and tomorrow_rain_chance is not None:
            rain_chance = tomorrow_rain_chance
            rain_note = "from today's signs"
        else:
            rain_chance = history.USUAL_RAIN_CHANCE[day.month]
            rain_note = "usual for " + calendar.month_name[day.month]

        item = {
            "date": day.date(),
            "steps": steps,
            "temps": temps,
            "rain_chance": rain_chance,
            "rain_note": rain_note,
            "condition": forecast_condition(rain_chance, temps["temp_mean"]["forecast"]),
            # why the model gives this average: the date alone, plus what the last 3 days add
            "why": explain_temperature("temp_mean", today, days["temp_mean"].iloc[-3:].values, steps),
            # how the average would feel with the usual humidity and wind of that date
            "feels_like": feels_like(temps["temp_mean"]["forecast"], normal("humidity", day), normal("wind_speed", day)),
        }
        # for a past day, the real weather is known too
        if show_real and day.date() <= LAST_PAST_DAY + datetime.timedelta(days=1):
            item["real_max"] = float(DATA.loc[day, "temp_max"])
            item["real_min"] = float(DATA.loc[day, "temp_min"])
            item["real_rain"] = float(DATA.loc[day, "precipitation"])
            item["real_mean"] = float(DATA.loc[day, "temp_mean"])
        forecast.append(item)
    return forecast


def to_unit(value, unit):
    # °C to the unit the user picked, rounded for the chart
    if value is None:
        return None
    if unit == "F":
        value = value * 9 / 5 + 32
    return round(value, 1)


def chart_data(days, last_forecast_day, unit, show_real):
    # the numbers for the Conditions chart: the last 21 known days, then the model's path to the last forecast day
    past = days.iloc[-21:]
    today = days.index[-1]
    future_days = pd.date_range(today + pd.Timedelta(days=1), pd.Timestamp(last_forecast_day), freq="D")
    last_3 = days["temp_mean"].iloc[-3:].values

    future = [forecast_temperature("temp_mean", today, last_3, step) for step in range(1, len(future_days) + 1)]
    data = {
        "unit": "°" + unit,
        "labels": [day.strftime("%d %b") for day in past.index] + [day.strftime("%d %b") for day in future_days],
        "known": len(past),
        "temp": [to_unit(v, unit) for v in past["temp_mean"]] + [None] * len(future_days),
        "feels": [to_unit(feels_like(t, h, w), unit) for t, h, w in zip(past["temp_mean"], past["humidity"], past["wind_speed"])]
                 + [to_unit(feels_like(f["forecast"], normal("humidity", d), normal("wind_speed", d)), unit) for f, d in zip(future, future_days)],
        "forecast": [None] * (len(past) - 1) + [to_unit(past["temp_mean"].iloc[-1], unit)] + [to_unit(f["forecast"], unit) for f in future],
        "low": [None] * len(past) + [to_unit(f["lower"], unit) for f in future],
        "high": [None] * len(past) + [to_unit(f["upper"], unit) for f in future],
        "usual": [to_unit(expected_for_date("temp_mean", d), unit) for d in list(past.index) + list(future_days)],
        "humidity": [round(v, 1) for v in past["humidity"]] + [None] * len(future_days),
        "humidity_usual": [round(normal("humidity", d), 1) for d in list(past.index) + list(future_days)],
        "wind": [round(v * 3.6, 1) for v in past["wind_speed"]] + [None] * len(future_days),
        "wind_usual": [round(normal("wind_speed", d) * 3.6, 1) for d in list(past.index) + list(future_days)],
        "pressure": [round(v * 10, 1) for v in past["pressure"]] + [None] * len(future_days),
        "pressure_usual": [round(normal("pressure", d) * 10, 1) for d in list(past.index) + list(future_days)],
        "rain": [round(v, 1) for v in past["precipitation"]] + [None] * len(future_days),
        "real": None,
    }
    # for a past day, the real temperature of the forecast days is known too
    if show_real:
        real = [to_unit(DATA.loc[d, "temp_mean"], unit) if d in DATA.index else None for d in future_days]
        data["real"] = [None] * len(past) + real
    return data


def storm_signs(result):
    # the three signs the 9.5 rule looks at, on the last known day
    return [
        {"name": "Rainy season (October to April)", "on": result["in_season"]},
        {"name": "Rain on the last known day (1 mm or more)", "on": result["rain_today"]},
        {"name": "Pressure falling since the day before", "on": result["pressure_change"] < 0},
    ]


def season_bars():
    # Task 4's storms (2016-2025) by month
    counts = MODEL["storms_by_month"]
    most = max(counts.values())
    return [{"month": calendar.month_abbr[m], "count": counts[m], "height": round(100 * counts[m] / most)} for m in range(1, 13)]


def unit_links(request):
    # the same page in °C and in °F
    links = {}
    for unit in ["C", "F"]:
        params = request.GET.copy()
        params["unit"] = unit
        links[unit] = "?" + params.urlencode()
    return links


def model_info():
    return {"trained_on": MODEL["trained_on"], "test_mae": MODEL["test_mae"]}


def home(request):
    # the main page: the app fills in the weather itself, from NASA POWER or from a past day
    unit = "F" if request.GET.get("unit") == "F" else "C"
    mode = "past" if request.GET.get("mode") == "past" else "latest"
    past_form = PastDayForm(request.GET if mode == "past" else None)
    days = None
    error = None

    if mode == "past":
        if past_form.is_valid():
            days = history_from_csv(past_form.cleaned_data["day"])
            first_day = days.index[-1] + pd.Timedelta(days=1)
    else:
        today = timezone.localdate()
        try:
            days = history_from_nasa(today)
            first_day = today + datetime.timedelta(days=1)
        except WeatherDataError as problem:
            error = str(problem)

    context = {
        "unit": unit,
        "unit_links": unit_links(request),
        "mode": mode,
        "past_form": past_form,
        "error": error,
        "storms": history.STORMS,
        "storm_summary": history.STORM_SUMMARY,
        "pre_storm": history.PRE_STORM,
        "season": season_bars(),
        "very_hot_by_year": history.VERY_HOT_BY_YEAR,
        "hot_first_decade": history.HOT_FIRST_DECADE,
        "hot_last_decade": history.HOT_LAST_DECADE,
        "model_info": model_info(),
    }

    if days is not None:
        result = analyze(days, target_day=first_day)
        # rain, storm and heat chances are for the day after the last known day,
        # so they only mean "tomorrow" when that day is the one being forecast
        warnings_current = result["steps"] == 1
        result["next_day"] = result["today"] + datetime.timedelta(days=1)
        result["storm"]["look"] = chance_level(result["storm"]["chance"], 2, 10)
        result["rain"]["look"] = chance_level(result["rain"]["chance"], 10, 30)
        for heat_day in result["very_hot"]:
            heat_day["percent"] = round(100 * heat_day["chance"])
        result["any_very_hot"] = any(heat_day["warning"] for heat_day in result["very_hot"])

        context.update({
            "latest": latest_conditions(days),
            "days_behind": (timezone.localdate() - result["today"]).days,
            "result": result,
            "warnings_current": warnings_current,
            "signs": storm_signs(result),
            "forecast": five_day_forecast(days, first_day, result["rain"]["chance"] if warnings_current else None, mode == "past"),
            "chart": chart_data(days, pd.Timestamp(first_day) + pd.Timedelta(days=FORECAST_DAYS - 1), unit, mode == "past"),
            "happened": what_happened(result["today"]) if mode == "past" else None,
            # the last 3 days, ready to try on the What if tab
            "what_if": {"today": result["today"].isoformat(), **{name: round(float(value), 2) for name, value in zip(["temp_2_days_ago", "temp_yesterday", "temp_today"], days["temp_mean"].iloc[-3:])}},
        })

    return render(request, "forecast/home.html", context)


def manual(request):
    # the What if tab: change the last three days and see tomorrow's mean temperature
    unit = "F" if request.GET.get("unit") == "F" else "C"
    result = None
    if request.method == "POST":
        form = ManualForm(request.POST)
        if form.is_valid():
            inputs = form.cleaned_data
            values = [inputs["temp_2_days_ago"], inputs["temp_yesterday"], inputs["temp_today"]]
            result = forecast_temperature("temp_mean", inputs["today"], values)
            result["day"] = inputs["today"] + datetime.timedelta(days=1)
            result["normal"] = float(normal("temp_mean", result["day"]))
            result["difference"] = result["forecast"] - result["normal"]
            result["level"] = temperature_level(result["forecast"])
    else:
        # the main page can send the last known days here, so the form starts filled in
        form = ManualForm(initial=request.GET.dict() or None)

    return render(request, "forecast/manual.html", {
        "form": form,
        "result": result,
        "unit": unit,
        "unit_links": unit_links(request),
        "model_info": model_info(),
    })


def outlook(request):
    # the Storm outlook page: what the storms of 2016-2025 say about the coming seasons
    unit = "F" if request.GET.get("unit") == "F" else "C"
    today = timezone.localdate()

    # the rainy season that is running now, or the next one (it starts in October)
    start_year = today.year if today.month >= 5 else today.year - 1
    this_month = datetime.date(today.year, today.month, 1)
    months = []
    for item in history.MONTH_OUTLOOK:
        year = start_year if item["month"] >= 10 else start_year + 1
        first_day = datetime.date(year, item["month"], 1)
        months.append({
            **item,
            "name": calendar.month_name[item["month"]],
            "year": year,
            "now": first_day == this_month,
            "past": first_day < this_month,
            "look": chance_level(item["chance"], 20, 35),
        })

    # storms in a whole season: about 2.5 on average, one by one, so the counts follow a Poisson spread
    per_season = history.STORMS_PER_YEAR
    none = math.exp(-per_season)
    season_chances = {
        "none": 100 * none,
        "one_or_more": 100 * (1 - none),
        "three_or_more": 100 * (1 - none * (1 + per_season + per_season ** 2 / 2)),
    }

    # the warning ladder (9.5): the chance of a storm tomorrow for each situation today
    storm_table = MODEL["storm_chance"]
    usual = 100 * sum(row["Storms tomorrow"] for row in storm_table.values()) / sum(row["Days"] for row in storm_table.values())
    ladder = []
    for name, row in storm_table.items():
        ladder.append({
            "name": name,
            "days": row["Days"],
            "storms": row["Storms tomorrow"],
            "chance": row["Chance (%)"],
            "times": row["Chance (%)"] / usual,
            "look": chance_level(row["Chance (%)"], 2, 10),
            "width": round(row["Chance (%)"] / 25 * 100),
        })

    return render(request, "forecast/outlook.html", {
        "unit": unit,
        "unit_links": unit_links(request),
        "season_label": f"October {start_year} to April {start_year + 1}",
        "months": months,
        "per_season": per_season,
        "season_chances": season_chances,
        "seasons": history.SEASONS,
        "ladder": ladder,
        "usual": usual,
        "storm_summary": history.STORM_SUMMARY,
        "pre_storm": history.PRE_STORM,
        "storms_by_year": history.STORMS_BY_YEAR,
        "first_half": history.FIRST_HALF_PER_YEAR,
        "second_half": history.SECOND_HALF_PER_YEAR,
        "heat": history.HEAT_PROJECTION,
        "hot_first_decade": history.HOT_FIRST_DECADE,
        "hot_last_decade": history.HOT_LAST_DECADE,
        "model_info": model_info(),
    })