import datetime
from pathlib import Path
from unittest import mock

import pandas as pd
import requests
from django.test import SimpleTestCase

from .forms import ManualForm, PastDayForm
from .ml import analyze
from .weather_data import DATA, NASA_NAMES, WeatherDataError, history_from_csv, history_from_nasa

CHECK_FILE = Path(__file__).resolve().parent.parent / "ml_models" / "app_check_days.csv"


def fake_nasa_response(last_day, missing_days=2):
    # a NASA POWER answer built from the project's data, with the newest days not filled yet (-999)
    days = DATA.loc[last_day - pd.Timedelta(days=140):last_day]
    values = {}
    for code, column in NASA_NAMES.items():
        values[code] = {day.strftime("%Y%m%d"): float(value) for day, value in days[column].items()}
        for day in days.index[-missing_days:]:
            values[code][day.strftime("%Y%m%d")] = -999
    response = mock.Mock()
    response.json.return_value = {"properties": {"parameter": values}}
    return response


class ModelMatchesNotebookTest(SimpleTestCase):
    # the app must give the same answers as the notebook (Step 14) on the example days

    def test_same_numbers_as_notebook(self):
        check_days = pd.read_csv(CHECK_FILE, index_col=0, parse_dates=True)
        for today, row in check_days.iterrows():
            result = analyze(history_from_csv(today))
            print(today.date(), "| mean: notebook", round(row["temp_mean_forecast"], 2), "app", round(result["temperature"]["temp_mean"]["forecast"], 2))
            for column in ["temp_mean", "temp_max", "temp_min"]:
                for part in ["forecast", "lower", "upper"]:
                    self.assertAlmostEqual(result["temperature"][column][part], row[column + "_" + part], delta=0.001)
            for lead in [1, 2, 3]:
                self.assertAlmostEqual(result["very_hot"][lead - 1]["chance"], row["very_hot_chance_" + str(lead)], delta=0.001)


class NasaDataTest(SimpleTestCase):
    # the live data must look exactly like the project's data

    def setUp(self):
        # each test starts without NASA answers kept from another test
        history_from_nasa.cache_clear()

    def test_nasa_days_match_the_csv(self):
        with mock.patch("forecast.weather_data.requests.get", return_value=fake_nasa_response(pd.Timestamp("2025-12-31"))):
            history = history_from_nasa(datetime.date(2025, 12, 31))
        # the 2 days NASA has not filled are dropped
        self.assertEqual(history.index[-1], pd.Timestamp("2025-12-29"))
        same_days = DATA.loc[history.index, history.columns]
        self.assertAlmostEqual((history - same_days).abs().max().max(), 0, places=6)

    def test_nasa_not_reachable(self):
        with mock.patch("forecast.weather_data.requests.get", side_effect=requests.ConnectionError):
            with self.assertRaises(WeatherDataError):
                history_from_nasa(datetime.date(2025, 12, 31))


class FormValidationTest(SimpleTestCase):
    # bad or missing inputs must give a clear error on the right field

    def manual_form(self, **changes):
        good = {"today": "2024-07-20", "temp_2_days_ago": "31.03", "temp_yesterday": "31.56", "temp_today": "33.00"}
        return ManualForm(data={**good, **changes})

    def test_good_input_is_accepted(self):
        self.assertTrue(self.manual_form().is_valid())

    def test_empty_field(self):
        form = self.manual_form(temp_today="")
        self.assertFalse(form.is_valid())
        self.assertIn("Please enter a temperature.", form.errors["temp_today"])

    def test_text_instead_of_number(self):
        form = self.manual_form(temp_yesterday="hot")
        self.assertFalse(form.is_valid())
        self.assertIn("Please enter a number, for example 24.5.", form.errors["temp_yesterday"])

    def test_impossible_for_the_month(self):
        # 3, 1 and 7 °C at the start of May never happened in Cairo
        form = self.manual_form(today="2026-05-01", temp_2_days_ago="3", temp_yesterday="1", temp_today="7")
        self.assertFalse(form.is_valid())
        self.assertIn("temp_today", form.errors)

    def test_big_jump_between_days(self):
        form = self.manual_form(temp_today="20")
        self.assertFalse(form.is_valid())
        self.assertIn("temp_today", form.errors)

    def test_past_day_out_of_range(self):
        self.assertFalse(PastDayForm(data={"day": "1980-01-01"}).is_valid())
        self.assertFalse(PastDayForm(data={"day": "2030-01-01"}).is_valid())
        self.assertTrue(PastDayForm(data={"day": "2020-03-11"}).is_valid())


class PageTest(SimpleTestCase):
    # the pages: a past day, the latest data, NASA down, °F, the explanation, accuracy, storm history, the outlook and What if

    def setUp(self):
        # each test starts without NASA answers kept from another test
        history_from_nasa.cache_clear()

    def test_past_day_shows_forecast_and_what_happened(self):
        response = self.client.get("/", {"mode": "past", "day": "2024-07-20"})
        self.assertContains(response, "Sunday 21 July 2024")
        self.assertContains(response, "What really happened")

    def test_latest_data(self):
        with mock.patch("forecast.weather_data.requests.get", return_value=fake_nasa_response(pd.Timestamp("2025-12-31"))):
            with mock.patch("forecast.views.timezone.localdate", return_value=datetime.date(2025, 12, 31)):
                response = self.client.get("/")
        self.assertContains(response, "Latest NASA data")
        self.assertContains(response, "Thursday 1 January 2026")
        # NASA's newest day is 2 days back here, so the warnings are not shown for tomorrow
        self.assertContains(response, "need the weather of the day before tomorrow")

    def test_nasa_down_shows_a_message(self):
        with mock.patch("forecast.weather_data.requests.get", side_effect=requests.ConnectionError):
            response = self.client.get("/")
        self.assertContains(response, "NASA POWER could not be reached")

    def test_fahrenheit(self):
        # 20 July 2024 had a mean of 33.0 °C, which is 91.4 °F, and the page must say °F
        response = self.client.get("/", {"mode": "past", "day": "2024-07-20", "unit": "F"})
        self.assertContains(response, "91.4°F")

    def test_why_this_forecast(self):
        # the explanation must add up: usual for the date + memory of the last days = the forecast
        response = self.client.get("/", {"mode": "past", "day": "2024-07-20"})
        self.assertContains(response, "Why the model says 32.6°C on average")
        self.assertContains(response, "Feels like")

    def test_accuracy_section(self):
        # the same test-year numbers as the notebook: 0.94 °C average error, 72 of 93 very hot days caught
        response = self.client.get("/", {"mode": "past", "day": "2024-07-20"})
        self.assertContains(response, "How accurate is the model?")
        self.assertContains(response, "±0.9°C")
        self.assertContains(response, "72 of 93")

    def test_storm_history_is_shown(self):
        response = self.client.get("/", {"mode": "past", "day": "2020-03-11"})
        self.assertContains(response, "Storm history")
        self.assertContains(response, "Thu 12 Mar 2020")

    def test_what_if_starts_filled_in(self):
        response = self.client.get("/manual/", {"today": "2024-07-20", "temp_2_days_ago": "31.03", "temp_yesterday": "31.56", "temp_today": "33.0"})
        self.assertContains(response, 'value="33.0"')

    def test_storm_outlook(self):
        # March had 6 storms in 10 years: a 45 % chance of at least one storm in a coming March
        response = self.client.get("/outlook/")
        self.assertContains(response, "Not the exact day.")
        self.assertContains(response, "45%")

    def test_manual_tab(self):
        good = {"today": "2024-07-20", "temp_2_days_ago": "31.03", "temp_yesterday": "31.56", "temp_today": "33.00"}
        self.assertContains(self.client.post("/manual/", good), "32.6°C")
        self.assertContains(self.client.post("/manual/", {**good, "temp_today": "55"}), "Too high for Cairo")