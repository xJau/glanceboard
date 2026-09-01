"""Rendering: panel fit, determinism, and the layout's failure modes."""
from __future__ import annotations

import io
from datetime import date, datetime

import pytest
from PIL import Image, ImageDraw

from glanceboard.config import REPO_ROOT
from glanceboard.models import Board, Event, Weather
from glanceboard.render import render_board
from glanceboard.render.board import _fit_rows, _wrap_first_then_full
from glanceboard.render.grayscale import levels_used, quantize
from glanceboard.render.icons import glyph_for
from glanceboard.render.layout import Layout
from glanceboard.render.theme import PAPER, Fonts

from .conftest import ROME

FONT_DIR = REPO_ROOT / "assets" / "fonts"
# Landscape: the board is composed wide and rotated on the way to the panel.
SIZES = [(1448, 1072), (1648, 1236)]
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
    first = _to_png(render_board(board, 1448, 1072, FONT_DIR))
    second = _to_png(render_board(board, 1448, 1072, FONT_DIR))
    assert first == second


def test_an_empty_day_still_renders():
    image = render_board(make_board([], WEATHER), 1448, 1072, FONT_DIR)
    assert image.size == (1448, 1072)


def test_a_board_without_weather_still_renders():
    image = render_board(make_board([timed(9, "Consulenza")], None, weather_ok=False),
                         1448, 1072, FONT_DIR)
    assert image.size == (1448, 1072)


def test_an_unreachable_calendar_still_renders():
    image = render_board(make_board([], WEATHER, calendar_ok=False), 1448, 1072, FONT_DIR)
    assert image.size == (1448, 1072)


def test_an_out_of_range_panel_share_is_rejected():
    with pytest.raises(ValueError):
        Layout(1448, 1072, art_fraction=0.9)


def test_the_cards_stay_inside_the_frame():
    layout = Layout(1448, 1072)
    for rect in (layout.banner, layout.agenda, layout.art, layout.weather):
        assert rect.left >= layout.frame_outer + layout.frame_gap
        assert rect.right <= 1448 - layout.frame_outer - layout.frame_gap
        assert rect.top >= layout.frame_outer + layout.frame_gap
        assert rect.bottom <= 1072 - layout.frame_outer - layout.frame_gap


# ─── Weather glyphs ─────────────────────────────────────────────

@pytest.mark.parametrize("code,expected", [
    (0, "clear"),
    (2, "mostly_clear"),
    (3, "cloud"),
    (45, "fog"),
    (63, "rain"),
    (75, "snow"),
    (95, "storm"),
    (4242, "cloud"),  # an unknown code still draws something
])
def test_weather_codes_map_to_a_glyph(code, expected):
    assert glyph_for(code) == expected


@pytest.mark.parametrize("code", [0, 2, 3, 45, 63, 75, 95])
def test_every_glyph_draws_without_raising(code):
    image = render_board(
        make_board([], Weather(10.0, 20.0, "°C", "x", code)), 1448, 1072, FONT_DIR
    )
    assert image.size == (1448, 1072)


# ─── Text fitting units ─────────────────────────────────────────

@pytest.fixture
def draw_and_font():
    image = Image.new("L", (1448, 1072), 255)
    return ImageDraw.Draw(image), Fonts(FONT_DIR).get(44)


def test_wrap_keeps_a_short_title_on_one_line(draw_and_font):
    draw, font = draw_and_font
    assert _wrap_first_then_full(draw, "— Palestra", font, 800, 800, 2) == ["— Palestra"]


def test_wrap_uses_the_full_width_after_the_first_line(draw_and_font):
    """The first line is short because the time sits beside it."""
    draw, font = draw_and_font
    lines = _wrap_first_then_full(draw, "— Riunione settimanale con il team", font,
                                  200, 900, 2)
    assert len(lines) == 2
    assert draw.textlength(lines[0], font=font) <= 200
    assert draw.textlength(lines[1], font=font) <= 900


def test_wrap_ellipsises_a_title_that_will_not_fit(draw_and_font):
    draw, font = draw_and_font
    lines = _wrap_first_then_full(draw, "Sopralluogo cantiere " * 12, font, 600, 600, 2)
    assert len(lines) == 2
    assert lines[-1].endswith("…")


def test_wrap_breaks_a_single_word_longer_than_the_column(draw_and_font):
    draw, font = draw_and_font
    lines = _wrap_first_then_full(draw, "A" * 200, font, 300, 300, 2)
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


def test_every_theme_tone_already_sits_on_the_grid():
    """A tone off the grid would shift when quantized, which is a silent bug."""
    from glanceboard.render import theme

    for name in ("PAPER", "PLATE", "HAIRLINE", "MUTED", "INK_SOFT", "INK"):
        assert getattr(theme, name) % 17 == 0, name


def _to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_every_weather_label_fits_its_card_without_shrinking():
    """A clipped or shrunk condition reads worse than a plainer word that fits."""
    from glanceboard.render.layout import Layout
    from glanceboard.render.theme import REGULAR
    from glanceboard.weather import WMO_CODES

    layout = Layout(1448, 1072)
    fonts = Fonts(FONT_DIR)
    font = fonts.get(layout.size_condition, REGULAR)
    draw = ImageDraw.Draw(Image.new("L", (1448, 1072)))

    available = layout.weather.width - 2 * layout.plate_padding

    too_wide = [label for label in set(WMO_CODES.values())
                if draw.textlength(label, font=font) > available]
    assert not too_wide, f"these labels do not fit the weather card: {too_wide}"


def test_the_font_cache_is_shared_between_renders():
    """Caching on the instance means every render re-reads the file."""
    first = Fonts(FONT_DIR).get(40, 400)
    second = Fonts(FONT_DIR).get(40, 400)
    assert first is second


def test_different_weights_are_different_faces():
    regular = Fonts(FONT_DIR).get(40, 400)
    bold = Fonts(FONT_DIR).get(40, 700)
    assert regular is not bold


def test_the_picture_is_washed_pale_enough_to_read_type_over():
    """The picture is the page now. Black text has to survive on top of it, on
    a panel with sixteen levels and no backlight — so nothing in the background
    may come out dark."""
    dark = Image.new("L", (400, 300), 0)
    image = render_board(make_board([], WEATHER), 1448, 1072, FONT_DIR, illustration=dark)
    layout = Layout(1448, 1072)

    # A patch the veil does not reach — right of the agenda, below the weather,
    # above the caption. Whatever the picture was, what lands there has to stay
    # light enough that type could be set on it.
    patch = image.crop(_bare_patch(layout))
    assert min(levels_used(patch)) >= 153, "the background is too dark for black type"


def _bare_patch(layout: Layout) -> tuple[int, int, int, int]:
    """A hundred pixels of page carrying neither text nor veil."""
    left = layout.agenda.right + 120
    top = layout.weather.bottom + 120
    return (left, top, left + 100, top + 100)


def test_a_lighter_wash_keeps_more_of_the_picture():
    dark = Image.new("L", (400, 300), 0)
    layout = Layout(1448, 1072)
    box = _bare_patch(layout)

    pale = render_board(make_board([], WEATHER), 1448, 1072, FONT_DIR,
                        illustration=dark, art_wash=0.85).crop(box)
    strong = render_board(make_board([], WEATHER), 1448, 1072, FONT_DIR,
                          illustration=dark, art_wash=0.45).crop(box)
    assert min(levels_used(strong)) < min(levels_used(pale))


def test_the_weather_stays_in_its_corner():
    """No card under it any more, so nothing stops it running into the agenda
    except the geometry."""
    layout = Layout(1448, 1072)
    assert layout.weather.left > layout.agenda.right - 1
    assert layout.weather.bottom <= layout.content.bottom


def test_the_illustration_is_stretched_to_use_the_panel_range():
    """A model's mid-greys are fine on a screen and mud on sixteen levels."""
    flat = Image.new("L", (200, 150), 128)
    for x in range(200):
        for y in range(150):
            flat.putpixel((x, y), 120 + (x % 16))  # a narrow band of greys

    image = render_board(make_board([], WEATHER), 1448, 1072, FONT_DIR, illustration=flat)
    layout = Layout(1448, 1072)
    panel = image.crop(layout.art.inset(layout.plate_stroke + 2).as_tuple())
    levels = levels_used(panel)

    assert min(levels) <= 34, "the darks never arrived"
    assert max(levels) >= 221, "the lights never arrived"




def test_the_layout_mirrors():
    """The list takes one side and the weather the opposite top corner, so the
    two never crowd each other whichever way round they are."""
    left = Layout(1448, 1072, text_side="left")
    right = Layout(1448, 1072, text_side="right")

    assert left.agenda.left < left.weather.left
    assert right.agenda.left > right.weather.left
    assert left.agenda.width == right.agenda.width


def test_both_sides_render():
    board = make_board([timed(9, "Consulenza")], WEATHER)
    for side in ("left", "right"):
        image = render_board(board, 1448, 1072, FONT_DIR, text_side=side)
        assert image.size == (1448, 1072)


def test_an_unknown_side_is_rejected():
    with pytest.raises(ValueError):
        Layout(1448, 1072, text_side="middle")


def test_the_timetable_mirrors_with_its_column():
    """A list moved right with its numbers still on the left leaves them
    stranded mid-page, pointing at nothing."""
    left = Layout(1448, 1072, text_side="left")
    right = Layout(1448, 1072, text_side="right")

    # The hours sit against the outer margin on either side.
    assert left.rule_x - left.agenda.left == left.time_column
    assert right.agenda.right - right.rule_x == right.time_column
    assert left.entry_width == right.entry_width
