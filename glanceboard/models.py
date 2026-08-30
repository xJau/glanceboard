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

"""Data model for a day's board.

These structures are the *only* representation of calendar data that exists
downstream of the iCal parser. Client-identifying fields (location, description,
attendees, organizer, UID) are dropped inside the parser and are therefore
absent by construction, not by a filtering step someone has to remember to call.
Anything built from a Board — a rendered PNG today, an AI payload in phase 2 —
is safe for the same reason.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Event:
    """A calendar entry reduced to what the board is allowed to know."""

    title: str
    start: datetime | None  # local time; None for all-day entries
    end: datetime | None
    all_day: bool

    @property
    def start_label(self) -> str:
        """Left-column label: 'HH:MM' for timed events, empty for all-day."""
        if self.all_day or self.start is None:
            return ""
        return self.start.strftime("%H:%M")

    @property
    def end_label(self) -> str:
        if self.all_day or self.end is None:
            return ""
        return self.end.strftime("%H:%M")


@dataclass(frozen=True)
class Weather:
    """Daily weather summary. Only what the header band displays."""

    temp_min: float | None
    temp_max: float | None
    unit_symbol: str
    condition: str
    weather_code: int


@dataclass(frozen=True)
class Board:
    """Everything the renderer needs, and nothing else."""

    day: date
    events: tuple[Event, ...]
    weather: Weather | None
    generated_at: datetime
    calendar_ok: bool = True
    weather_ok: bool = True

    def to_dict(self) -> dict:
        """JSON-safe dict. This is what a phase-2 model payload is built from."""
        return {
            "day": self.day.isoformat(),
            "events": [
                {
                    "title": e.title,
                    "start": e.start.isoformat() if e.start else None,
                    "end": e.end.isoformat() if e.end else None,
                    "all_day": e.all_day,
                }
                for e in self.events
            ],
            "weather": asdict(self.weather) if self.weather else None,
            "calendar_ok": self.calendar_ok,
            "weather_ok": self.weather_ok,
        }

    def content_hash(self) -> str:
        """Stable hash of the board's *content*.

        Excludes generated_at so that regenerating an unchanged day produces an
        unchanged hash — that is what lets the Kindle skip a redraw.
        """
        payload = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
