"""Wake-up scheduling."""
from __future__ import annotations

import dataclasses
from datetime import datetime

from glanceboard.schedule import next_slot

from .conftest import ROME


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 1, hour, minute, tzinfo=ROME)


def test_returns_the_next_slot_later_today(settings):
    settings = dataclasses.replace(settings, slots=(5, 12, 18))
    assert next_slot(settings, at(6, 30)) == at(12)


def test_rolls_over_to_tomorrows_first_slot(settings):
    settings = dataclasses.replace(settings, slots=(5, 12, 18))
    assert next_slot(settings, at(19)) == at(5).replace(day=2)


def test_a_slot_exactly_now_is_not_the_next_one(settings):
    """Waking at the instant of generation would race the renderer."""
    settings = dataclasses.replace(settings, slots=(5, 12, 18))
    assert next_slot(settings, at(12)) == at(18)


def test_a_single_slot_a_day_still_works(settings):
    settings = dataclasses.replace(settings, slots=(5,))
    assert next_slot(settings, at(9)) == at(5).replace(day=2)
