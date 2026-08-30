"""Rendering: panel fit, determinism, and the layout's failure modes."""
from __future__ import annotations

import io
from datetime import date, datetime

import pytest
from PIL import Image, ImageDraw

from glanceboard.config import REPO_ROOT
from glanceboard.models import Board, Event, Weather
from glanceboard.render import render_board
from glanceboard.render.board import _fit_rows, _wrap
from glanceboard.render.grayscale import levels_used, quantize
from glanceboard.render.layout import Layout
from glanceboard.render.theme import Fonts

from .conftest import ROME

FONT_DIR = REPO_ROOT / "assets" / "fonts"
SIZES = [(1236, 1648), (1072, 1448)]
GENERATED_AT = datetime(2026, 9, 1, 5, 0, tzinfo=ROME)


def make_board(events=(), weather=None, **kwargs) -> Board:
    return Board(
        day=date(2026, 9, 1),
        events=tuple(events),
        weather=weather,
        generated_at=GENERATED_AT,
        **kwargs,
    )


def timed(hour: int, title: str) -> Event:
    start = datetime(2026, 9, 1, hour, 0, tzinfo=ROME)
    return Event(title=title, start=start, end=start.replace(hour=hour + 1), all_day=False)


WEATHER = Weather(temp_min=17.9, temp_max=28.4, unit_symbol="°C",
                  condition="Coperto", weather_code=3)


@pytest.mark.parametrize("width,height", SIZES)
def test_renders_at_the_supported_panel_sizes(width, height):
    image = render_board(make_board([timed(9, "Consulenza")], WEATHER),
                         width=width, height=height, font_dir=FONT_DIR)
    assert image.size == (width, height)
    assert image.mode == "L"


@pytest.mark.parametrize("width,height", SIZES)
def test_output_fits_the_panels_sixteen_grays(width, height):
    image = render_board(make_board([timed(9, "Consulenza")], WEATHER),
                         width=width, height=height, font_dir=FONT_DIR)
    levels = levels_used(image)
    assert len(levels) <= 16
    assert all(value % 17 == 0 for value in levels)


def test_the_same_board_renders_to_the_same_bytes():
    """Determinism is what makes the change-detection hash meaningful."""
    board = make_board([timed(9, "Consulenza"), timed(14, "Sopralluogo")], WEATHER)
    first = _to_png(render_board(board, 1236, 1648, FONT_DIR))
    second = _to_png(render_board(board, 1236, 1648, FONT_DIR))
    assert first == second


def test_an_empty_day_still_renders():
    image = render_board(make_board([], WEATHER), 1236, 1648, FONT_DIR)
    assert image.size == (1236, 1648)


def test_a_board_without_weather_still_renders():
    image = render_board(make_board([timed(9, "Consulenza")], None, weather_ok=False),
                         1236, 1648, FONT_DIR)
    assert image.size == (1236, 1648)


def test_an_unreachable_calendar_still_renders():
    image = render_board(make_board([], WEATHER, calendar_ok=False), 1236, 1648, FONT_DIR)
    assert image.size == (1236, 1648)


def test_a_crowded_day_stays_inside_the_reserved_bands():
    """Nothing may be drawn into the illustration band or past the footer."""
    events = [timed(hour, f"Appuntamento numero {hour} con nome lungo") for hour in range(7, 20)]
    image = render_board(make_board(events, WEATHER), 1236, 1648, FONT_DIR, max_events=13)
    layout = Layout(1236, 1648)

    art_band = image.crop((0, layout.art.top, image.width, layout.art.bottom))
    assert levels_used(art_band) == {255}, "something was drawn into the illustration band"


def test_the_reserved_band_can_be_resized():
    tall = Layout(1236, 1648, art_fraction=0.5)
    short = Layout(1236, 1648, art_fraction=0.1)
    assert tall.art.height > short.art.height
    assert tall.agenda.height < short.agenda.height


def test_an_out_of_range_reserved_band_is_rejected():
    with pytest.raises(ValueError):
        Layout(1236, 1648, art_fraction=0.9)


# ─── Text fitting units ─────────────────────────────────────────

@pytest.fixture
def draw_and_font():
    image = Image.new("L", (1236, 1648), 255)
    return ImageDraw.Draw(image), Fonts(FONT_DIR).get(48)


def test_wrap_keeps_a_short_title_on_one_line(draw_and_font):
    draw, font = draw_and_font
    assert _wrap(draw, "Palestra", font, 800, 2) == ["Palestra"]


def test_wrap_ellipsises_a_title_that_will_not_fit(draw_and_font):
    draw, font = draw_and_font
    lines = _wrap(draw, "Sopralluogo cantiere " * 12, font, 600, 2)
    assert len(lines) == 2
    assert lines[-1].endswith("…")


def test_wrap_breaks_a_single_word_longer_than_the_column(draw_and_font):
    draw, font = draw_and_font
    lines = _wrap(draw, "A" * 200, font, 300, 2)
    assert len(lines) == 2
    assert all(draw.textlength(line, font=font) <= 300 for line in lines)


def test_fit_rows_stops_before_overflowing():
    assert _fit_rows([100, 100, 100], available=250, reserve=0) == 2
    assert _fit_rows([100, 100, 100], available=250, reserve=60) == 1
    assert _fit_rows([100, 100], available=250, reserve=0) == 2


# ─── Quantization ───────────────────────────────────────────────

def test_quantize_snaps_to_the_sixteen_level_grid():
    source = Image.new("L", (16, 1))
    source.putdata(range(0, 256, 16))
    assert all(value % 17 == 0 for value in quantize(source).getdata())


def _to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
