# Where the weather days come from: the project's CSV (past days) or NASA POWER (the latest days)
import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .ml import HISTORY_DAYS

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "cairo_weather_clean.csv"

# loaded once, when Django starts
DATA = pd.read_csv(CSV_PATH, index_col="date", parse_dates=True).asfreq("D")

# a past day needs HISTORY_DAYS before it, and a next day to compare with
FIRST_PAST_DAY = (DATA.index[0] + pd.Timedelta(days=HISTORY_DAYS - 1)).date()
LAST_PAST_DAY = (DATA.index[-1] - pd.Timedelta(days=1)).date()

# the same request as in the Task 4 notebook
NASA_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
LATITUDE = 30.0444
LONGITUDE = 31.2357
NASA_NAMES = {
    "T2M": "temp_mean",
    "T2M_MAX": "temp_max",
    "T2M_MIN": "temp_min",
    "PRECTOTCORR": "precipitation",
    "RH2M": "humidity",
    "WS2M": "wind_speed",
    "PS": "pressure",
}


class WeatherDataError(Exception):
    # a clear message for the page when the data cannot be loaded
    pass


def history_from_csv(day):
    # the HISTORY_DAYS days up to a past day, from the project's clean data
    day = pd.Timestamp(day)
    return DATA.loc[day - pd.Timedelta(days=HISTORY_DAYS - 1):day]


def what_happened(day):
    # the real weather on the day after a past day, and very hot days in the 3 days after it
    next_day = pd.Timestamp(day) + pd.Timedelta(days=1)
    real = DATA.loc[next_day]
    next_3_days = DATA.loc[next_day:next_day + pd.Timedelta(days=2), "temp_max"]
    return {
        "date": next_day.date(),
        "temp_max": float(real["temp_max"]),
        "temp_mean": float(real["temp_mean"]),
        "temp_min": float(real["temp_min"]),
        "rain_mm": float(real["precipitation"]),
        "storm": bool(real["precipitation"] >= 10),
        "very_hot_days": [d.date() for d in next_3_days[next_3_days > 40.1].index],
    }


def fill_short_gaps(series, max_days=3):
    # same as the Task 4 cleaning: fill a gap of up to 3 days from the days around it
    missing = series.isnull()
    gap_length = missing.groupby((~missing).cumsum()).transform("sum")
    return series.where(~(missing & (gap_length <= max_days)), series.interpolate(method="time"))


@lru_cache(maxsize=4)
def history_from_nasa(today):
    # the latest days from NASA POWER (several days behind today); kept for the day, so NASA is asked once a day
    start = today - datetime.timedelta(days=HISTORY_DAYS + 15)
    params = {
        "parameters": ",".join(NASA_NAMES),
        "community": "AG",
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start": start.strftime("%Y%m%d"),
        "end": today.strftime("%Y%m%d"),
        "format": "JSON",
    }
    try:
        response = requests.get(NASA_URL, params=params, timeout=30)
        response.raise_for_status()
        values = response.json()["properties"]["parameter"]
    except (requests.RequestException, ValueError, KeyError):
        raise WeatherDataError("NASA POWER could not be reached. Check your internet connection, or pick a past day instead.")

    # one row per day, with the project's column names; -999 means "not available yet"
    days = pd.DataFrame(values).rename(columns=NASA_NAMES)
    days.index = pd.to_datetime(days.index, format="%Y%m%d")
    days.index.name = "date"
    days = days.replace(-999, np.nan).asfreq("D")

    # drop the newest days NASA has not filled yet, then fill short gaps like Task 4
    days = days.loc[:days.dropna().index[-1]]
    for column in days.columns:
        days[column] = fill_short_gaps(days[column])

    days = days.iloc[-HISTORY_DAYS:]
    if len(days) < HISTORY_DAYS or days.isnull().any().any():
        raise WeatherDataError("NASA POWER sent incomplete data for the last months. Please try again later, or pick a past day instead.")
    return days