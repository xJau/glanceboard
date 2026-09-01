"""The photo library: one picture a day, rotating, remembered."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from PIL import Image

from glanceboard import photos


@pytest.fixture
def library(tmp_path):
    """Four photographs and a file that is not one."""
    directory = tmp_path / "photos"
    directory.mkdir()
    for name in ("a.jpg", "b.png", "c.jpeg", "d.webp"):
        Image.new("RGB", (8, 8), "white").save(directory / name)
    (directory / "notes.txt").write_text("not a photo", encoding="utf-8")
    return directory


def test_only_images_count(library):
    names = [path.name for path in photos.available(library)]
    assert names == ["a.jpg", "b.png", "c.jpeg", "d.webp"]
    assert "notes.txt" not in names


def test_a_missing_directory_is_empty_not_an_error(tmp_path):
    assert photos.available(tmp_path / "nothing-here") == []


def test_an_empty_library_raises(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(photos.NoPhotosError):
        photos.photo_for_day(empty, date(2026, 9, 1), tmp_path / "state.json")


def test_the_same_day_always_gets_the_same_photo(library, tmp_path):
    """The board regenerates three times a day; the picture must not move."""
    state = tmp_path / "state.json"
    day = date(2026, 9, 1)
    first = photos.photo_for_day(library, day, state)
    assert photos.photo_for_day(library, day, state) == first
    assert photos.photo_for_day(library, day, state) == first


def test_the_next_day_gets_the_next_photo(library, tmp_path):
    state = tmp_path / "state.json"
    day = date(2026, 9, 1)
    first = photos.photo_for_day(library, day, state)
    second = photos.photo_for_day(library, day + timedelta(days=1), state)
    assert second != first

    order = [path.name for path in photos.available(library)]
    assert order.index(second.name) == (order.index(first.name) + 1) % len(order)


def test_the_rotation_covers_the_library_before_repeating(library, tmp_path):
    state = tmp_path / "state.json"
    day = date(2026, 9, 1)
    picked = [photos.photo_for_day(library, day + timedelta(days=n), state).name
              for n in range(4)]
    assert sorted(picked) == ["a.jpg", "b.png", "c.jpeg", "d.webp"]


def test_a_deleted_photo_does_not_break_the_rotation(library, tmp_path):
    state = tmp_path / "state.json"
    day = date(2026, 9, 1)
    chosen = photos.photo_for_day(library, day, state)
    chosen.unlink()

    # Same day, but the remembered photo is gone: something else must arrive.
    replacement = photos.photo_for_day(library, day, state)
    assert replacement.exists()
    assert replacement != chosen


def test_an_unwritable_state_file_still_yields_a_photo(library, tmp_path):
    """Losing the rotation is cosmetic. Losing the picture is not."""
    directory = tmp_path / "unwritable"
    directory.mkdir()
    directory.chmod(0o500)
    try:
        picked = photos.photo_for_day(library, date(2026, 9, 1), directory / "state.json")
        assert picked.exists()
    finally:
        directory.chmod(0o700)
