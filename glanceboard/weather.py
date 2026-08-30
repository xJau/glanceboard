# Copyright 2026 Google LLC
# Copyright 2026 Glanceboard Kindle contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Daily weather from Open-Meteo (no API key, no account).

The board shows the day's minimum and maximum, not the current reading: at
05:00 the current temperature says nothing useful about what to wear.
"""
from __future__ import annotations

import logging
from datetime import date

import requests

from .models import Weather

log = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes, Italian labels.
WMO_CODES: dict[int, str] = {
    0: "Sereno",
    1: "Prevalentemente sereno",
    2: "Parzialmente nuvoloso",
    3: "Coperto",
    45: "Nebbia",
    48: "Nebbia con brina",
    51: "Pioviggine leggera",
    53: "Pioviggine",
    55: "Pioviggine intensa",
    56: "Pioviggine gelata",
    57: "Pioviggine gelata intensa",
    61: "Pioggia leggera",
    63: "Pioggia",
    65: "Pioggia intensa",
    66: "Pioggia gelata",
    67: "Pioggia gelata intensa",
    71: "Neve leggera",
    73: "Neve",
    75: "Neve intensa",
    77: "Granelli di neve",
    80: "Rovesci leggeri",
    81: "Rovesci",
    82: "Rovesci violenti",
    85: "Rovesci di neve",
    86: "Rovesci di neve intensi",
    95: "Temporale",
    96: "Temporale con grandine",
    99: "Temporale con grandine forte",
}


def fetch_weather_payload(
    latitude: float,
    longitude: float,
    day: date,
    timezone: str,
    temp_unit: str = "celsius",
    timeout: int = 20,
) -> dict:
    """Call Open-Meteo for a single day. Raises requests.RequestException."""
    response = requests.get(
        API_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "daily": "temperature_2m_max,temperature_2m_min,weather_code",
            "timezone": timezone,
            "temperature_unit": temp_unit,
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
        },
        timeout=timeout,
        headers={"User-Agent": "glanceboard-kindle/0.1"},
    )
    response.raise_for_status()
    return response.json()


def parse_weather(payload: dict, temp_unit: str = "celsius") -> Weather | None:
    """Turn an Open-Meteo response into a Weather, or None if it has no day."""
    daily = payload.get("daily") or {}
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    codes = daily.get("weather_code") or []

    if not highs and not lows:
        return None

    temp_max = highs[0] if highs else None
    temp_min = lows[0] if lows else None
    code = int(codes[0]) if codes and codes[0] is not None else 0

    return Weather(
        temp_min=temp_min,
        temp_max=temp_max,
        unit_symbol="°C" if temp_unit == "celsius" else "°F",
        condition=WMO_CODES.get(code, "—"),
        weather_code=code,
    )


def weather_for_day(
    latitude: float,
    longitude: float,
    day: date,
    timezone: str,
    temp_unit: str = "celsius",
    timeout: int = 20,
) -> Weather | None:
    """Fetch + parse in one step. Raises on network failure."""
    payload = fetch_weather_payload(
        latitude, longitude, day, timezone, temp_unit=temp_unit, timeout=timeout
    )
    return parse_weather(payload, temp_unit=temp_unit)
