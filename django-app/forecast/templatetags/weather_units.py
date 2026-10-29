# small helpers for the page: show temperatures in °C or °F
from django import template

register = template.Library()


@register.filter
def temp(value, unit):
    # a temperature, in the unit the user picked, with the unit written next to it
    if unit == "F":
        value = value * 9 / 5 + 32
    return f"{value:.1f}°{unit}"


@register.filter
def temp_change(value, unit):
    # a difference between two temperatures (no +32 for °F, only the scale changes)
    if unit == "F":
        value = value * 9 / 5
    return f"{abs(value):.1f}°{unit}"