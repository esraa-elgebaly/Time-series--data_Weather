# a quick check of the app's models before building the page: the same answers as the notebook, and the live NASA data
import datetime

import pandas as pd

from forecast.ml import analyze
from forecast.weather_data import WeatherDataError, history_from_csv, history_from_nasa

# 1. the example days saved by the notebook (Step 14): the app must give the same numbers
print("1. Same answers as the notebook?")
check_days = pd.read_csv("ml_models/app_check_days.csv", index_col=0, parse_dates=True)
for today, row in check_days.iterrows():
    result = analyze(history_from_csv(today))
    temperature = result["temperature"]
    print(today.date(),
          "| mean", round(row["temp_mean_forecast"], 2), "vs", round(temperature["temp_mean"]["forecast"], 2),
          "| max", round(row["temp_max_forecast"], 2), "vs", round(temperature["temp_max"]["forecast"], 2),
          "| min", round(row["temp_min_forecast"], 2), "vs", round(temperature["temp_min"]["forecast"], 2),
          "| very hot in 1 day", round(row["very_hot_chance_1"], 2), "vs", round(result["very_hot"][0]["chance"], 2))

# 2. the latest days from NASA POWER, as the app will use them
print("\n2. Latest data from NASA POWER")
today = datetime.date.today()
try:
    history = history_from_nasa(today)
    result = analyze(history, target_day=today + datetime.timedelta(days=1))
    print("Latest NASA day:", result["today"], "| forecast for:", result["target_day"])
    print(history.tail(3).round(2))
    for column, values in result["temperature"].items():
        print(column, round(values["forecast"], 1), "°C, most likely", round(values["lower"], 1), "to", round(values["upper"], 1))
    print("Rain chance:", round(result["rain"]["chance"], 1), "% | storm chance:", round(result["storm"]["chance"], 1), "%")
except WeatherDataError as problem:
    print(problem)