"""Parsing the feed: expansion, ordering, timezones."""
from __future__ import annotations

from datetime import date

import pytest

from glanceboard.calendar_feed import UNTITLED, parse_ical

from .conftest import ROME, SAMPLE_DAY

MINIMAL = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//IT
BEGIN:VEVENT
UID:no-title@test
DTSTAMP:20260825T090000Z
DTSTART:20260901T080000Z
DTEND:20260901T090000Z
END:VEVENT
END:VCALENDAR
"""


def test_parses_every_event_of_the_day(sample_ics):
    events = parse_ical(sample_ics, SAMPLE_DAY, ROME)
    assert len(events) == 6


def test_all_day_events_come_first_then_chronological(sample_ics):
    events = parse_ical(sample_ics, SAMPLE_DAY, ROME)
    assert events[0].all_day is True
    timed = [event.start_label for event in events if not event.all_day]
    assert timed == sorted(timed)
    assert timed[0] == "09:00"


def test_utc_timestamps_are_converted_to_the_configured_zone(sample_ics):
    events = parse_ical(sample_ics, SAMPLE_DAY, ROME)
    rossi = next(e for e in events if e.title.startswith("Consulenza"))
    # 07:00Z in September is 09:00 in Rome (CEST).
    assert rossi.start_label == "09:00"
    assert rossi.end_label == "10:00"


def test_recurring_events_are_expanded(sample_ics):
    """The weekly meeting starts on 4 August but must appear on 1 September."""
    events = parse_ical(sample_ics, SAMPLE_DAY, ROME)
    assert any(e.title == "Riunione settimanale team" for e in events)


def test_a_day_with_no_occurrences_is_empty(sample_ics):
    thursday = date(2026, 9, 3)
    assert parse_ical(sample_ics, thursday, ROME) == ()


def test_all_day_event_has_no_times(sample_ics):
    events = parse_ical(sample_ics, SAMPLE_DAY, ROME)
    all_day = events[0]
    assert all_day.start is None and all_day.end is None
    assert all_day.start_label == "" and all_day.end_label == ""


def test_event_without_a_summary_gets_a_placeholder():
    events = parse_ical(MINIMAL, SAMPLE_DAY, ROME)
    assert events[0].title == UNTITLED


def test_a_sign_in_page_is_rejected_as_not_a_calendar(monkeypatch):
    """A share link answers 200 with HTML. That must not reach the parser."""
    import requests

    from glanceboard import calendar_feed

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        content = b"<!doctype html><html><head><title>Sign in</title></head>" * 40

        def raise_for_status(self):
            return None

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse())

    with pytest.raises(calendar_feed.NotACalendarError) as error:
        calendar_feed.fetch_ical("https://example.invalid/share")

    assert "basic.ics" in str(error.value), "the error should say how to fix it"


def test_a_real_feed_is_accepted(monkeypatch, sample_ics):
    import requests

    from glanceboard import calendar_feed

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/calendar"}
        content = sample_ics

        def raise_for_status(self):
            return None

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse())
    assert calendar_feed.fetch_ical("https://example.invalid/private.ics") == sample_ics
