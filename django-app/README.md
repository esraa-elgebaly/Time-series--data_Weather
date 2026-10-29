# Cairo Weather & Storm Watch

A Django web app that forecasts tomorrow's weather in Cairo and shows the signs that came before the city's storms. It is built on 36 years of NASA POWER daily data (1990–2025) and the models from Task 4 and Task 5 (time series forecasting) of the NiCST ML Mentorship Program.

**Live app:** _add your Render link here_

![Forecast page](screenshots/forecast.png)

## What the app does

The app fills in the weather itself. The user never has to type yesterday's temperature.

**Forecast tab**
- **Latest NASA data:** downloads the newest days from NASA POWER and forecasts tomorrow. NASA publishes Cairo's daily data about a week late, so the page says how many days back its newest day is, and the ranges are wider.
- **A past day (1990–2025):** takes the days from the project's data, forecasts the next day, and shows **what really happened**.
- **Weather information:** the last known day: temperature, feels like, max, min, humidity, wind, pressure and its change, rain.
- **Tomorrow:** max, average and min with a 95 % range, and the chance of rain, a storm and a very hot day.
- **Conditions:** pick one of 5 days to see its forecast, how it feels, and **why the model gives that number** (the usual value for the date plus what the last 3 days add). A chart shows temperature (actual or feels like), humidity, wind, pressure or rain.
- **Storm watch:** the storm signs on the last known day, and the pattern of the 3 days before Cairo's 25 storms.
- **How accurate is the model?:** the errors on the test years 2023–2025.
- **Storm season, very hot days by year, storm history:** every storm, with the signs on the day before it.

**Storm outlook tab:** what the storms of 2016–2025 say about the coming seasons: the chance of a storm in each month, how many storms a season brings, the warning ladder, and the trend of very hot days up to 2030. It also says plainly what cannot be known: the exact day of a storm months ahead.

**What if? tab:** change the last 3 days and see how tomorrow's average would change. Every value is checked against what Cairo has seen in that month since 1990.

**°C / °F** switch on every page.

| Storm outlook | Invalid input | Mobile |
|---|---|---|
| ![Storm outlook](screenshots/outlook.png) | ![Errors](screenshots/errors.png) | ![Mobile](screenshots/mobile.png) |

## The models

| Question | Model | Learned on | Result on the test years 2023–2025 |
|---|---|---|---|
| Tomorrow's average temperature | SARIMAX: ARIMA(3,0,0) + yearly season (3 sine/cosine pairs) + trend | 1990–2022 | 0.94 °C average error (tomorrow = today: 1.04 °C) |
| Tomorrow's max temperature | the same model | 1990–2022 | 1.38 °C (tomorrow = today: 1.48 °C) |
| Tomorrow's min temperature | the same model | 1990–2022 | 1.12 °C (tomorrow = today: 1.23 °C) |
| Very hot day (max > 40.1 °C) in 1, 2, 3 days | logistic regression, 12 inputs | 1990–2019 | caught 72 of 93 very hot days one day ahead |
| Storm tomorrow (rain ≥ 10 mm) | rule: rain today + falling pressure | 2016–2025 | 20 % chance after these signs, 30 times the usual |
| Rain tomorrow (≥ 1 mm) | what followed rain days and dry days | 2016–2025 | 41 % after a rain day, 5 % after a dry day (rainy season) |

![Accuracy](screenshots/accuracy.png)

The model file `ml_models/weather_model.pkl` (about 30 KB) holds only the learned numbers. The app rebuilds the models from them, and nothing is trained again.

## The app gives the same answers as the notebook

The Task 5 notebook (Step 14) checked the saved file against the notebook on every test day (difference: 0.0) and saved example days to `ml_models/app_check_days.csv`. The test `ModelMatchesNotebookTest` runs these days through the app:

| Today | Average: notebook | Average: app | Max: notebook | Max: app |
|---|---|---|---|---|
| 2023-01-15 | 12.45 | 12.45 | 19.12 | 19.12 |
| 2023-04-10 | 21.39 | 21.39 | 29.75 | 29.75 |
| 2024-07-20 | 32.63 | 32.63 | 40.58 | 40.58 |
| 2025-10-05 | 24.90 | 24.90 | 32.21 | 32.21 |
| 2023-01-22 (day before a storm) | 12.91 | 12.91 | 20.41 | 20.41 |

## Input checks

| Input | Rule |
|---|---|
| Past day | from 30 Apr 1990 to 30 Dec 2025 |
| Any field | must not be empty |
| Temperatures | must be a number, from 0 to 40 °C |
| Temperatures | must be possible for the month: within 3 °C of the coldest and warmest mean seen in that month since 1990 |
| Two days in a row | at most 12 °C apart |

## Run it on your computer

You need Python 3.12 or newer.

```bash
git clone https://github.com/<your-username>/cairo-weather-django.git
cd cairo-weather-django
```

Windows (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

Then:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000.

## Run the tests

```bash
python manage.py test forecast
```

19 tests check that the app matches the notebook, that NASA's data is read like the project's data, that bad inputs give the right message, and that every page shows what it should.

`python check_models.py` prints the notebook and app numbers side by side and tries a live NASA download.

## Put it online (Render)

1. Push the project to GitHub.
2. On Render: **New → Web Service**, connect the repository.
3. Build command: `pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate`
4. Start command: `gunicorn weather_site.wsgi`
5. Environment variables: `DJANGO_DEBUG=False` and `DJANGO_SECRET_KEY` (a long random value).

Render gives its address to the app in `RENDER_EXTERNAL_HOSTNAME`, and `settings.py` adds it to the allowed hosts.

## Project structure

```
cairo-weather-django/
├── manage.py
├── requirements.txt
├── .python-version
├── check_models.py               notebook vs app numbers, and a live NASA test
├── data/
│   └── cairo_weather_clean.csv   the project's clean daily data, 1990–2025
├── ml_models/
│   ├── weather_model.pkl         the saved models (from the Task 5 notebook)
│   └── app_check_days.csv        notebook answers used to check the app
├── weather_site/                 Django settings and main URLs
├── forecast/                     the Django app
│   ├── ml.py                     loads the models once and forecasts (no Django code)
│   ├── weather_data.py           the days from the CSV or from NASA POWER
│   ├── history.py                storm patterns, outlook and accuracy from the data
│   ├── forms.py                  inputs and their checks
│   ├── views.py                  connects the data, the models and the pages
│   ├── urls.py
│   ├── tests.py
│   ├── templatetags/weather_units.py   °C / °F
│   ├── templates/forecast/       base, home, outlook, manual
│   └── static/forecast/          style.css, conditions.js
└── screenshots/
```

## Limits

- NASA POWER publishes Cairo's daily data about a week late, so the "latest" forecast starts several days back and its ranges are wide. Rain, storm and heat warnings need the day before, so they are shown for past days only.
- 12 of the 25 storms of 2016–2025 started after a dry day with no sign in daily data. The exact day of a storm cannot be known months ahead.
- The model forecasts temperature only. Rain and storm chances are what followed similar days in 2016–2025.

## Built with

Django 6.1, statsmodels, pandas, NumPy, joblib, requests, WhiteNoise, gunicorn, Bootstrap 5, Bootstrap Icons, Chart.js.