"""Open-Meteo response handling."""
from __future__ import annotations

from glanceboard.weather import parse_weather


def test_reads_the_days_minimum_and_maximum(sample_weather):
    weather = parse_weather(sample_weather)
    assert weather is not None
    assert weather.temp_min == 17.9
    assert weather.temp_max == 28.4
    assert weather.unit_symbol == "°C"


def test_maps_the_wmo_code_to_an_italian_label(sample_weather):
    assert parse_weather(sample_weather).condition == "Coperto"


def test_unknown_code_does_not_raise(sample_weather):
    sample_weather["daily"]["weather_code"] = [1234]
    weather = parse_weather(sample_weather)
    assert weather.condition == "—"


def test_fahrenheit_changes_the_unit_symbol(sample_weather):
    assert parse_weather(sample_weather, temp_unit="fahrenheit").unit_symbol == "°F"


def test_a_response_without_a_day_yields_nothing():
    assert parse_weather({"daily": {}}) is None
    assert parse_weather({}) is None


def test_a_missing_minimum_is_tolerated(sample_weather):
    sample_weather["daily"]["temperature_2m_min"] = []
    weather = parse_weather(sample_weather)
    assert weather.temp_min is None
    assert weather.temp_max == 28.4
