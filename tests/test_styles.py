"""The rotation of hands the photographs are drawn by."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from glanceboard import styles


def test_every_style_carries_the_constraints():
    """Monochrome, ink rather than tone, paper left alone. A style that fills
    the page with grey is unreadable behind text at any wash."""
    for name in styles.STYLES:
        prompt = styles.prompt_for(name)
        assert "Monochrome" in prompt
        assert "untouched" in prompt
        assert "No text" in prompt


def test_a_style_actually_says_something_of_its_own():
    assert "comic" in styles.prompt_for("fumetto").lower()
    assert "engraving" in styles.prompt_for("western").lower()
    assert "science-fiction" in styles.prompt_for("fantascienza").lower()


def test_an_unknown_style_names_the_ones_that_exist():
    with pytest.raises(styles.UnknownStyleError) as error:
        styles.prompt_for("acquerello")
    assert "libro" in str(error.value)


def test_the_hand_changes_every_day():
    days = [date(2026, 9, 1) + timedelta(days=n) for n in range(6)]
    chosen = [styles.style_for_day(day) for day in days]
    assert len(set(chosen)) == 6, "a day should not repeat inside one turn of the wheel"


def test_the_wheel_comes_back_round():
    first = styles.style_for_day(date(2026, 9, 1))
    later = styles.style_for_day(date(2026, 9, 1) + timedelta(days=len(styles.DEFAULT_ROTATION)))
    assert first == later


def test_the_same_day_always_gets_the_same_hand():
    """Taken from the date, not from stored state: two devices sharing a
    library stay in step, and a wiped state file changes nothing."""
    day = date(2026, 9, 3)
    assert styles.style_for_day(day) == styles.style_for_day(day)


def test_the_rotation_can_be_narrowed():
    assert styles.rotation("fumetto,western") == ("fumetto", "western")
    chosen = {styles.style_for_day(date(2026, 9, 1) + timedelta(days=n), "fumetto,western")
              for n in range(6)}
    assert chosen == {"fumetto", "western"}


def test_a_typo_in_the_rotation_is_refused():
    with pytest.raises(styles.UnknownStyleError):
        styles.rotation("fumetto,futurista")


def test_an_empty_setting_means_all_of_them():
    assert styles.rotation(None) == styles.DEFAULT_ROTATION
    assert styles.rotation("") == styles.DEFAULT_ROTATION
