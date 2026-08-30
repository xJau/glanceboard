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

"""iCal feed reading.

This module is the privacy boundary. The feed carries client data — locations,
notes, attendee addresses — and none of it crosses out of `parse_ical`. Only
title, start, end and the all-day flag are kept, so no downstream consumer
(renderer today, model payload in phase 2) can leak what it never received.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import recurring_ical_events
import requests
from icalendar import Calendar as ICalendar

from .models import Event

log = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")
UNTITLED = "(senza titolo)"

#: How much of the body to inspect when deciding whether it is a calendar at all.
_SNIFF_BYTES = 2048


class NotACalendarError(RuntimeError):
    """The URL answered, but with something that is not an iCalendar feed."""


def fetch_ical(url: str, timeout: int = 20) -> bytes:
    """Download the raw .ics body.

    Raises requests.RequestException on a transport failure, and
    NotACalendarError when the server answers with something that is not a
    calendar — which in practice means a sign-in page, because the URL is a
    share link rather than the feed's own secret address.
    """
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "glanceboard-kindle/0.1"},
    )
    response.raise_for_status()

    body = response.content
    if b"BEGIN:VCALENDAR" not in body[:_SNIFF_BYTES]:
        content_type = response.headers.get("content-type", "unknown")
        raise NotACalendarError(
            f"the feed returned {content_type} rather than an iCalendar "
            f"({len(body)} bytes, no BEGIN:VCALENDAR). If this is Google "
            "Calendar, use the secret address in iCal format — the long URL "
            "ending in /basic.ics — not a share or browser link."
        )
    return body


def parse_ical(raw: bytes, day: date, tz: ZoneInfo) -> tuple[Event, ...]:
    """Expand the calendar for `day` and reduce each entry to an Event.

    Recurrences are expanded by `recurring_ical_events`, so weekly client slots
    appear on every occurrence rather than only on their first.
    """
    calendar = ICalendar.from_ical(raw)
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    end = start + timedelta(days=1)

    events: list[Event] = []
    for component in recurring_ical_events.of(calendar).between(start, end):
        event = _to_event(component, tz)
        if event is not None:
            events.append(event)

    return tuple(sorted(events, key=_sort_key))


def _to_event(component, tz: ZoneInfo) -> Event | None:
    """Reduce one iCal component. Everything not named here is discarded."""
    title = _clean_title(component.get("summary"))

    dtstart = component.get("dtstart")
    dtend = component.get("dtend")
    if dtstart is None:
        return None

    raw_start = dtstart.dt
    all_day = not isinstance(raw_start, datetime)

    if all_day:
        return Event(title=title, start=None, end=None, all_day=True)

    start = _to_local(raw_start, tz)
    end = _to_local(dtend.dt, tz) if dtend is not None and isinstance(dtend.dt, datetime) else None
    return Event(title=title, start=start, end=end, all_day=False)


def _to_local(value: datetime, tz: ZoneInfo) -> datetime:
    """Naive timestamps in a feed are read as local time; aware ones convert."""
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def _clean_title(raw) -> str:
    if raw is None:
        return UNTITLED
    title = _WHITESPACE.sub(" ", str(raw)).strip()
    return title or UNTITLED


def _sort_key(event: Event) -> tuple[int, str]:
    """All-day entries first, then chronological, then alphabetical."""
    if event.all_day or event.start is None:
        return (0, event.title.casefold())
    return (1, event.start.isoformat())


def events_for_day(url: str, day: date, tz: ZoneInfo, timeout: int = 20) -> tuple[Event, ...]:
    """Fetch + parse in one step. Raises on network or parse failure."""
    return parse_ical(fetch_ical(url, timeout=timeout), day, tz)
