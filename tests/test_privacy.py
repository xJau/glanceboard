"""The parser is the privacy boundary — these tests are what hold it there.

The sample feed deliberately carries a client address, private notes, an
organiser and an attendee address. None of it may survive into a Board, because
a Board is what a phase-2 model payload will be built from.
"""
from __future__ import annotations

import dataclasses
import json

from glanceboard.calendar_feed import parse_ical
from glanceboard.models import Event
from glanceboard.pipeline import build_board

from .conftest import ROME, SAMPLE_DAY

SENSITIVE = (
    "Via Privata Cliente",
    "Milano",
    "preventivo",
    "bozza firmata",
    "m.rossi@example.invalid",
    "studio@example.invalid",
    "Google Meet",
    "sample-rossi@glanceboard",
)


def test_event_carries_only_the_four_permitted_fields():
    names = {field.name for field in dataclasses.fields(Event)}
    assert names == {"title", "start", "end", "all_day"}


def test_parsed_events_drop_every_sensitive_field(sample_ics):
    events = parse_ical(sample_ics, SAMPLE_DAY, ROME)
    dumped = json.dumps([dataclasses.asdict(e) for e in events], default=str)
    for secret in SENSITIVE:
        assert secret not in dumped, f"{secret!r} leaked out of the parser"


def test_serialised_board_drops_every_sensitive_field(settings, sample_ics, sample_weather):
    """to_dict() is the shape a model payload will take. It must be clean."""
    board = build_board(
        settings, day=SAMPLE_DAY, ical_bytes=sample_ics, weather_payload=sample_weather
    )
    payload = json.dumps(board.to_dict(), ensure_ascii=False)
    for secret in SENSITIVE:
        assert secret not in payload, f"{secret!r} reached the board payload"


def test_titles_are_preserved(settings, sample_ics):
    """Dropping fields must not turn into dropping the thing we came for."""
    board = build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics)
    titles = [event.title for event in board.events]
    assert "Call Bianchi SRL" in titles
    assert "Palestra" in titles
