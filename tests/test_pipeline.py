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


def test_a_source_failure_never_logs_the_whole_response(settings, monkeypatch, caplog):
    """A feed answering with a sign-in page must not put an HTML document in the log."""
    monkeypatch.setenv("GB_ICAL_URL", "https://example.invalid/share")
    settings = type(settings).from_env()

    huge = "<html>" + "x" * 50_000 + "</html>"

    def explode(*args, **kwargs):
        raise ValueError(f"Content line could not be parsed into parts: {huge!r}")

    monkeypatch.setattr("glanceboard.calendar_feed.fetch_ical", explode)

    with caplog.at_level("WARNING"):
        board = build_board(settings, day=SAMPLE_DAY)

    assert board.calendar_ok is False
    assert all(len(record.getMessage()) < 400 for record in caplog.records)


def test_a_redesign_changes_the_hash_even_when_the_day_has_not(settings, sample_ics, monkeypatch):
    """Otherwise a new layout reaches the device only when the calendar moves."""
    board = build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics)
    before = board.content_hash()

    monkeypatch.setattr("glanceboard.__version__", "99.0.0")
    assert board.content_hash() != before


def test_a_source_that_fails_once_is_retried(settings, monkeypatch, sample_weather):
    """Open-Meteo answered 503 once and the board went six hours without weather."""
    monkeypatch.setenv("GB_LAT", "45.46")
    monkeypatch.setenv("GB_LON", "9.19")
    settings = type(settings).from_env()
    monkeypatch.setattr(pipeline, "RETRY_BACKOFF_SECONDS", 0)

    attempts = []

    def flaky(*args, **kwargs):
        attempts.append(1)
        if len(attempts) < 2:
            raise requests.HTTPError("503 Service Unavailable")
        return sample_weather

    monkeypatch.setattr("glanceboard.weather.fetch_weather_payload", flaky)

    board = build_board(settings, day=SAMPLE_DAY)
    assert len(attempts) == 2
    assert board.weather_ok is True
    assert board.weather.temp_max == 28.4


def test_a_source_that_stays_down_gives_up_and_degrades(settings, monkeypatch):
    monkeypatch.setenv("GB_LAT", "45.46")
    monkeypatch.setenv("GB_LON", "9.19")
    settings = type(settings).from_env()
    monkeypatch.setattr(pipeline, "RETRY_BACKOFF_SECONDS", 0)

    attempts = []

    def always_down(*args, **kwargs):
        attempts.append(1)
        raise requests.HTTPError("503 Service Unavailable")

    monkeypatch.setattr("glanceboard.weather.fetch_weather_payload", always_down)

    board = build_board(settings, day=SAMPLE_DAY)
    assert len(attempts) == pipeline.SOURCE_ATTEMPTS
    assert board.weather_ok is False
    assert board.weather is None


def test_the_calendar_is_retried_too(settings, monkeypatch, sample_ics):
    monkeypatch.setenv("GB_ICAL_URL", "https://example.invalid/feed.ics")
    settings = type(settings).from_env()
    monkeypatch.setattr(pipeline, "RETRY_BACKOFF_SECONDS", 0)

    attempts = []

    def flaky(*args, **kwargs):
        attempts.append(1)
        if len(attempts) < 2:
            raise requests.ConnectionError("connection reset")
        return sample_ics

    monkeypatch.setattr("glanceboard.calendar_feed.fetch_ical", flaky)

    board = build_board(settings, day=SAMPLE_DAY)
    assert len(attempts) == 2
    assert board.calendar_ok is True
    assert len(board.events) == 6


# ─── Illustration ───────────────────────────────────────────────

def test_without_a_key_there_is_simply_no_illustration(settings):
    """Not configured is a state, not a failure: the board is what it was."""
    assert pipeline.illustration_for(settings, SAMPLE_DAY) == (None, None, None)


def test_an_empty_photo_library_is_not_an_error(settings, monkeypatch):
    monkeypatch.setenv("GB_GEMINI_API_KEY", "k")
    settings = type(settings).from_env()
    assert pipeline.illustration_for(settings, SAMPLE_DAY) == (None, None, None)


def test_a_failing_model_leaves_the_board_intact(settings, monkeypatch, sample_ics):
    """The picture is the only thing a failure may cost."""
    from PIL import Image

    monkeypatch.setenv("GB_GEMINI_API_KEY", "k")
    monkeypatch.setenv("GB_PHOTO_DIR", str(settings.output_dir / "photos"))
    settings = type(settings).from_env()
    settings.photo_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), "white").save(settings.photo_dir / "a.jpg")

    def explode(*args, **kwargs):
        raise RuntimeError("the model is down")

    monkeypatch.setattr("glanceboard.illustration.illustrate", explode)

    image, key, photo = pipeline.illustration_for(settings, SAMPLE_DAY)
    assert (image, key, photo) == (None, None, None)

    board = build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics)
    path = render_to_file(board, settings, illustration=image)
    assert path.exists()


def test_the_illustration_is_part_of_the_hash(settings, monkeypatch, sample_ics):
    """An illustration that failed at five and arrived at noon must reach the
    device, and only a changed hash makes it redraw."""
    from PIL import Image

    monkeypatch.setenv("GB_GEMINI_API_KEY", "k")
    monkeypatch.setenv("GB_PHOTO_DIR", str(settings.output_dir / "photos"))
    settings = type(settings).from_env()
    settings.photo_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), "white").save(settings.photo_dir / "a.jpg")

    monkeypatch.setattr(
        pipeline, "build_board",
        lambda *a, **k: build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics),
    )

    monkeypatch.setattr(pipeline, "illustration_for", lambda *a, **k: (None, None, None))
    without = generate(settings, force=True)["hash"]

    picture = Image.new("L", (16, 16), 128)
    monkeypatch.setattr(pipeline, "illustration_for", lambda *a, **k: (picture, "abc123", None))
    with_picture = generate(settings, force=True)["hash"]

    assert with_picture != without


def test_the_state_records_whether_the_day_had_a_picture(settings, monkeypatch, sample_ics):
    monkeypatch.setattr(
        pipeline, "build_board",
        lambda *a, **k: build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics),
    )
    monkeypatch.setattr(pipeline, "illustration_for", lambda *a, **k: (None, None, None))
    state = generate(settings, force=True)
    assert state["illustration"] is False


def test_the_side_is_remembered_between_renders(settings, monkeypatch):
    """Without a picture there is nothing to measure, so the layout stays put."""
    from glanceboard.pipeline import _write_state, text_side_for

    _write_state(settings, {"text_side": "right"})
    assert text_side_for(settings, None) == "right"


def test_the_ink_decides_when_the_model_says_nothing(settings, monkeypatch):
    from PIL import Image, ImageDraw

    from glanceboard.pipeline import text_side_for

    busy_left = Image.new("L", (200, 100), 255)
    ImageDraw.Draw(busy_left).rectangle((0, 0, 100, 100), fill=0)
    assert text_side_for(settings, busy_left) == "right"


def test_switching_it_off_freezes_the_layout(settings, monkeypatch):
    from PIL import Image, ImageDraw

    from glanceboard.pipeline import _write_state, text_side_for

    monkeypatch.setenv("GB_ADAPTIVE_LAYOUT", "0")
    settings = type(settings).from_env()
    _write_state(settings, {"text_side": "left"})

    busy_left = Image.new("L", (200, 100), 255)
    ImageDraw.Draw(busy_left).rectangle((0, 0, 100, 100), fill=0)
    assert text_side_for(settings, busy_left) == "left"
