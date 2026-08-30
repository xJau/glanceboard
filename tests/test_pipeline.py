"""Pipeline behaviour: degradation, atomic writes, change detection."""
from __future__ import annotations

import json

import pytest
import requests

from glanceboard import pipeline
from glanceboard.pipeline import build_board, generate, load_state, render_to_file

from .conftest import SAMPLE_DAY


def test_builds_a_board_from_supplied_data(settings, sample_ics, sample_weather):
    board = build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics,
                        weather_payload=sample_weather)
    assert len(board.events) == 6
    assert board.weather.temp_max == 28.4
    assert board.calendar_ok and board.weather_ok


def test_an_unreachable_calendar_degrades_instead_of_raising(settings, monkeypatch):
    monkeypatch.setenv("GB_ICAL_URL", "https://example.invalid/feed.ics")
    settings = type(settings).from_env()

    def explode(*args, **kwargs):
        raise requests.ConnectionError("no route to host")

    monkeypatch.setattr("glanceboard.calendar_feed.fetch_ical", explode)

    board = build_board(settings, day=SAMPLE_DAY)
    assert board.calendar_ok is False
    assert board.events == ()


def test_malformed_ical_degrades_instead_of_raising(settings):
    board = build_board(settings, day=SAMPLE_DAY, ical_bytes=b"this is not a calendar")
    assert board.calendar_ok is False


def test_unreachable_weather_degrades_instead_of_raising(settings, monkeypatch):
    monkeypatch.setenv("GB_LAT", "45.46")
    monkeypatch.setenv("GB_LON", "9.19")
    settings = type(settings).from_env()

    def explode(*args, **kwargs):
        raise requests.Timeout("took too long")

    monkeypatch.setattr("glanceboard.weather.fetch_weather_payload", explode)

    board = build_board(settings, day=SAMPLE_DAY)
    assert board.weather_ok is False
    assert board.weather is None


def test_render_writes_a_png(settings, sample_ics, sample_weather):
    board = build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics,
                        weather_payload=sample_weather)
    path = render_to_file(board, settings)
    assert path.exists()
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_leaves_no_temporary_files_behind(settings, sample_ics):
    board = build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics)
    render_to_file(board, settings)
    assert list(settings.output_dir.glob("*.tmp")) == []


def test_a_failed_render_keeps_the_previous_png(settings, sample_ics, monkeypatch):
    board = build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics)
    good = render_to_file(board, settings)
    original = good.read_bytes()

    def explode(*args, **kwargs):
        raise RuntimeError("renderer blew up")

    monkeypatch.setattr("glanceboard.pipeline.render_board", explode)
    with pytest.raises(RuntimeError):
        render_to_file(board, settings)

    assert good.read_bytes() == original
    assert list(settings.output_dir.glob("*.tmp")) == []


def test_an_unchanged_board_is_not_re_rendered(settings, sample_ics, sample_weather, monkeypatch):
    """The Kindle skips a redraw on an unchanged hash, so the hash must be stable."""
    def fixed_board(*args, **kwargs):
        return build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics,
                           weather_payload=sample_weather)

    monkeypatch.setattr(pipeline, "build_board", fixed_board)

    first = generate(settings)
    written_at = settings.image_path.stat().st_mtime_ns

    second = generate(settings)
    assert second["hash"] == first["hash"]
    assert settings.image_path.stat().st_mtime_ns == written_at, "PNG was rewritten needlessly"


def test_forcing_regenerates_even_when_unchanged(settings, sample_ics, monkeypatch):
    monkeypatch.setattr(
        pipeline, "build_board",
        lambda *a, **k: build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics),
    )
    generate(settings)
    state = generate(settings, force=True)
    assert state["events"] == 6


def test_state_is_written_as_readable_json(settings, sample_ics, monkeypatch):
    monkeypatch.setattr(
        pipeline, "build_board",
        lambda *a, **k: build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics),
    )
    generate(settings)
    state = json.loads(settings.state_path.read_text(encoding="utf-8"))
    assert state["day"] == SAMPLE_DAY.isoformat()
    assert load_state(settings)["hash"] == state["hash"]


def test_missing_state_reads_as_empty(settings):
    assert load_state(settings) == {}


def test_the_board_is_rotated_for_the_portrait_panel(settings, sample_ics):
    """Composed landscape, delivered in the orientation the panel expects."""
    board = build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics)
    path = render_to_file(board, settings)

    from PIL import Image

    with Image.open(path) as image:
        assert settings.rotate == 90
        assert image.size == (settings.height, settings.width)


def test_rotation_can_be_overridden_for_previewing(settings, sample_ics):
    board = build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics)
    path = render_to_file(board, settings, rotate=0)

    from PIL import Image

    with Image.open(path) as image:
        assert image.size == (settings.width, settings.height)
