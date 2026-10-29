import datetime

from django import forms

from .ml import MODEL
from .weather_data import FIRST_PAST_DAY, LAST_PAST_DAY

# allowed temperatures, the same range used to check the data in the notebook (0 to 40 °C)
LOW_TEMP, HIGH_TEMP = MODEL["temp_range"]

# the coldest and warmest mean temperature seen in each month since 1990, plus a small margin
MONTH_RANGE = MODEL["month_range"]
MONTH_MARGIN = 3

# a bigger change between two days in a row is almost surely a typing mistake
MAX_DAILY_JUMP = 12

FIRST_DAY = datetime.date(1990, 1, 3)
LAST_DAY = datetime.date(2030, 12, 30)


def date_input():
    return forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d")


class PastDayForm(forms.Form):
    # pick a past day; the app fills in the weather from the project's data
    day = forms.DateField(
        label="Day",
        error_messages={"required": "Please choose a day.", "invalid": "Please enter a valid date."},
        widget=date_input(),
    )

    def clean_day(self):
        day = self.cleaned_data["day"]
        if day < FIRST_PAST_DAY or day > LAST_PAST_DAY:
            raise forms.ValidationError(f"Please choose a day from {FIRST_PAST_DAY:%d %b %Y} to {LAST_PAST_DAY:%d %b %Y}.")
        return day


def temperature_field(label):
    # the same rules and messages for the three temperature inputs
    return forms.FloatField(
        label=label,
        min_value=LOW_TEMP,
        max_value=HIGH_TEMP,
        error_messages={
            "required": "Please enter a temperature.",
            "invalid": "Please enter a number, for example 24.5.",
            "min_value": f"Too low for Cairo. Use a value from {LOW_TEMP} to {HIGH_TEMP} °C.",
            "max_value": f"Too high for Cairo. Use a value from {LOW_TEMP} to {HIGH_TEMP} °C.",
        },
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "any", "placeholder": "e.g. 24.5"}),
    )


class ManualForm(forms.Form):
    # type the last three days yourself
    today = forms.DateField(
        label="Today's date",
        initial=datetime.date.today,
        error_messages={"required": "Please choose today's date.", "invalid": "Please enter a valid date."},
        widget=date_input(),
    )
    temp_2_days_ago = temperature_field("2 days ago")
    temp_yesterday = temperature_field("Yesterday")
    temp_today = temperature_field("Today")

    def clean_today(self):
        # only dates the model can handle
        today = self.cleaned_data["today"]
        if today < FIRST_DAY or today > LAST_DAY:
            raise forms.ValidationError(f"Please choose a date from {FIRST_DAY:%d %b %Y} to {LAST_DAY:%d %b %Y}.")
        return today

    def clean(self):
        cleaned_data = super().clean()
        today = cleaned_data.get("today")
        fields = ["temp_2_days_ago", "temp_yesterday", "temp_today"]
        values = [cleaned_data.get(name) for name in fields]

        # if a field already has its own error, there is nothing to compare
        if today is None or None in values:
            return cleaned_data

        # each value must be possible for its month in Cairo (no 3 °C in May)
        for days_back, name, value in zip([2, 1, 0], fields, values):
            day = today - datetime.timedelta(days=days_back)
            low = MONTH_RANGE[day.month]["min"]
            high = MONTH_RANGE[day.month]["max"]
            if value < low - MONTH_MARGIN or value > high + MONTH_MARGIN:
                self.add_error(name, f"In {day:%B}, Cairo's mean temperature has stayed between {low:.1f} and {high:.1f} °C since 1990. Please check this value.")

        # a huge jump between two days in a row is likely a typo
        if abs(values[1] - values[0]) > MAX_DAILY_JUMP and "temp_yesterday" not in self.errors:
            self.add_error("temp_yesterday", f"More than {MAX_DAILY_JUMP} °C away from the day before. Please check it.")
        if abs(values[2] - values[1]) > MAX_DAILY_JUMP and "temp_today" not in self.errors:
            self.add_error("temp_today", f"More than {MAX_DAILY_JUMP} °C away from yesterday. Please check it.")
        return cleaned_data

    def is_valid(self):
        # mark the inputs that have an error, so Bootstrap shows them in red
        valid = super().is_valid()
        for name in self.errors:
            if name in self.fields:
                self.fields[name].widget.attrs["class"] = "form-control is-invalid"
        return valid