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

"""Draws a Board onto a grayscale canvas.

Text is always drawn here, by PIL, at every stage of the project's life. In
phase 2 the model fills the illustration panel and nothing else, so an
appointment time can never be something a model guessed at, and a failed
generation costs the board its picture rather than its content.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from ..models import Board, Event
from . import icons, theme
from .grayscale import quantize
from .layout import Layout, Rect

ELLIPSIS = "…"
MAX_TITLE_LINES = 2

EMPTY_LABEL = "Niente in programma.\nGiornata libera."
CALENDAR_ERROR_LABEL = "Calendario non raggiungibile."
WEATHER_ERROR_LABEL = "meteo non disponibile"
ALL_DAY_LABEL = "tutto il giorno"
ALL_DAY_DASH = "—"
AGENDA_HEADING = "In programma oggi"
SEPARATOR = "—"


def render_board(
    board: Board,
    width: int,
    height: int,
    font_dir: Path,
    max_events: int = 12,
    art_fraction: float = 0.38,
    debug_regions: bool = False,
    illustration: Image.Image | None = None,
    art_wash: float = 0.62,
) -> Image.Image:
    """Render `board` and return a 16-level grayscale image.

    `illustration` fills the panel that phase 1 left empty. It is the only part
    of the board a model touches: everything else is drawn here, so a picture
    that fails to arrive costs the board its picture and nothing more.
    """
    layout = Layout(width, height, art_fraction=art_fraction)
    fonts = theme.Fonts(font_dir)

    image = Image.new("L", (width, height), theme.PAPER)
    draw = ImageDraw.Draw(image)

    if illustration is not None:
        _draw_illustration(image, layout, illustration, wash=art_wash)
        _veil(image, layout)
    _draw_frame(draw, layout)
    _draw_banner(draw, layout, fonts, board)
    _draw_agenda(draw, layout, fonts, board, max_events)
    _draw_weather(draw, layout, fonts, board)
    _draw_footer(draw, layout, fonts, board)

    if debug_regions:
        _draw_debug_regions(draw, layout)

    return quantize(image)


# ─── Illustration ───────────────────────────────────────────────


def _draw_illustration(canvas: Image.Image, layout: Layout, illustration: Image.Image,
                       wash: float = 0.62) -> None:
    """Lay the picture across the whole page, pale enough to read type over.

    Two steps, and both matter. The tonal range is stretched first, because a
    model's idea of black ink on cream lands in the middle greys. Then the
    whole thing is lifted towards the paper: on a panel with sixteen levels and
    no backlight, a picture at full strength and black text on top of it cannot
    both be legible, and the text is the part nobody may lose.
    """
    panel = layout.art
    if panel.width <= 0 or panel.height <= 0:
        return

    picture = ImageOps.autocontrast(illustration.convert("L"), cutoff=2)
    scale = max(panel.width / picture.width, panel.height / picture.height)
    resized = picture.resize(
        (max(1, round(picture.width * scale)), max(1, round(picture.height * scale))),
        Image.LANCZOS,
    )
    left = (resized.width - panel.width) // 2
    top = (resized.height - panel.height) // 2
    cropped = resized.crop((left, top, left + panel.width, top + panel.height))

    wash = min(max(wash, 0.0), 0.95)
    faded = cropped.point(lambda value: round(255 - (255 - value) * (1 - wash)))

    mask = Image.new("L", (panel.width, panel.height), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, panel.width - 1, panel.height - 1),
        radius=max(2, layout.corner_radius // 2), fill=255,
    )
    canvas.paste(faded, (panel.left, panel.top), mask)


def _veil(canvas: Image.Image, layout: Layout) -> None:
    """Lift the areas that carry text further towards the paper.

    The picture is whatever the day's photograph became, and no wash strong
    enough to guarantee contrast everywhere would leave a picture worth having.
    So the two regions that carry type — the list and the corner — are lifted a
    little more, with a blurred mask so the edge reads as light falling off
    rather than as a box drawn on top.
    """
    veil = Image.new("L", canvas.size, 0)
    painter = ImageDraw.Draw(veil)
    pad = layout.plate_padding
    for rect in (layout.agenda, layout.weather, layout.footer):
        painter.rounded_rectangle(
            (rect.left - pad, rect.top - pad, rect.right + pad, rect.bottom + pad),
            radius=layout.corner_radius, fill=110,
        )
    # A wide blur: with a sparse drawing the veil is the thing you notice if
    # its edge is anywhere near crisp.
    veil = veil.filter(ImageFilter.GaussianBlur(pad * 2))
    canvas.paste(Image.new("L", canvas.size, theme.PAPER), (0, 0), veil)


# ─── Frame ──────────────────────────────────────────────────────

def _draw_frame(draw: ImageDraw.ImageDraw, layout: Layout) -> None:
    """A double rule just inside the edge, like the mount of a framed print."""
    outer = Rect(layout.frame_outer, layout.frame_outer,
                 layout.width - layout.frame_outer - 1,
                 layout.height - layout.frame_outer - 1)
    inner = outer.inset(layout.frame_gap)

    draw.rounded_rectangle(outer.as_tuple(), radius=layout.corner_radius,
                           outline=theme.INK, width=layout.frame_stroke)
    draw.rounded_rectangle(inner.as_tuple(), radius=max(2, layout.corner_radius // 2),
                           outline=theme.INK_SOFT, width=max(1, layout.frame_stroke // 2))


# ─── Banner ─────────────────────────────────────────────────────


def _draw_banner(draw: ImageDraw.ImageDraw, layout: Layout, fonts: theme.Fonts,
                 board: Board) -> None:
    """A ribbon bowed downwards, the way a banner hangs from its two ends.

    The band curves; the type stays level. Setting the letters along the arc
    would mean rotating each one, and rotated glyphs on a sixteen-grey panel
    come out ragged — the curve reads perfectly well from the shape alone.
    """
    banner = layout.banner
    outline = _banner_outline(banner, layout.banner_notch, layout.banner_bow)

    draw.polygon(outline, fill=theme.PLATE)
    _polygon_outline(draw, outline, layout.plate_stroke)

    text = theme.banner_date(board.day)
    inner_width = banner.width - 2 * layout.banner_notch - layout.plate_padding
    font = _fitted_font(draw, text, fonts, layout.size_banner, theme.HEAVY, inner_width)
    # The middle of the band is wherever the bow has taken it.
    draw.text((banner.centre_x, (banner.top + banner.bottom) // 2 + layout.banner_bow),
              text, font=font, fill=theme.INK, anchor="mm")


def _banner_outline(banner: Rect, notch: int, bow: int, steps: int = 48) -> list[tuple[int, int]]:
    """The bowed band, as a closed polygon: top edge, right chevron, bottom
    edge back, left chevron.

    `bow` is signed: negative arches the middle upwards, positive lets it sag.
    """
    left, right = banner.left, banner.right
    span = max(1, right - left)

    def dip(x: int) -> float:
        # A half sine: nothing at the ends, the full bow in the middle.
        return bow * math.sin(math.pi * (x - left) / span)

    top = [(x, round(banner.top + dip(x)))
           for x in (left + round(i * span / steps) for i in range(steps + 1))]
    bottom = [(x, round(banner.bottom + dip(x))) for x, _ in reversed(top)]

    right_mid = (round(right - notch),
                 round((banner.top + banner.bottom) / 2 + dip(right)))
    left_mid = (round(left + notch),
                round((banner.top + banner.bottom) / 2 + dip(left)))

    return top + [right_mid] + bottom + [left_mid]


def _polygon_outline(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]],
                     width: int) -> None:
    draw.line(points + [points[0]], fill=theme.INK, width=width, joint="curve")


# ─── Agenda ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class Density:
    """One way of spending vertical space on a row.

    A busy day compacts before it starts dropping appointments: a tighter line
    is a smaller loss than not knowing a client is coming at six.
    """

    time_font: object
    title_font: object
    note_font: object
    padding: int
    line_spacing: int


def _densities(layout: Layout, fonts: theme.Fonts) -> tuple[Density, ...]:
    comfortable = Density(
        time_font=fonts.get(layout.size_time, theme.BOLD),
        title_font=fonts.get(layout.size_title, theme.REGULAR),
        note_font=fonts.get(layout.size_note, theme.REGULAR),
        padding=layout.row_padding,
        line_spacing=layout.line_spacing,
    )
    snug = Density(
        time_font=comfortable.time_font,
        title_font=comfortable.title_font,
        note_font=comfortable.note_font,
        padding=max(2, round(layout.row_padding * 0.6)),
        line_spacing=max(2, round(layout.line_spacing * 0.75)),
    )
    compact = Density(
        time_font=fonts.get(round(layout.size_time * 0.86), theme.BOLD),
        title_font=fonts.get(round(layout.size_title * 0.86), theme.REGULAR),
        note_font=fonts.get(round(layout.size_note * 0.86), theme.REGULAR),
        padding=max(2, round(layout.row_padding * 0.5)),
        line_spacing=max(2, round(layout.line_spacing * 0.6)),
    )
    return (comfortable, snug, compact)



def _draw_agenda(draw: ImageDraw.ImageDraw, layout: Layout, fonts: theme.Fonts,
                 board: Board, max_events: int) -> None:
    """A timetable, not a card: hours in a column, a rule, then the entries."""
    area = layout.agenda_text
    heading_font = fonts.get(layout.size_heading, theme.BOLD)
    draw.text((layout.agenda.left, layout.agenda.top), AGENDA_HEADING.upper(),
              font=heading_font, fill=theme.INK_SOFT, anchor="lt")

    heading_bottom = layout.agenda.top + _text_height(draw, AGENDA_HEADING, heading_font)
    list_top = heading_bottom + layout.line_spacing * 5

    if not board.calendar_ok:
        _draw_agenda_note(draw, layout, fonts, CALENDAR_ERROR_LABEL, list_top)
        return
    if not board.events:
        _draw_agenda_note(draw, layout, fonts, EMPTY_LABEL, list_top)
        return

    events = list(board.events[:max_events])
    hidden = len(board.events) - len(events)
    available = layout.agenda.bottom - list_top

    density, heights, fitted = _choose_density(draw, layout, fonts, events, hidden, available)

    y = list_top
    for index in range(fitted):
        _draw_row(draw, layout, density, events[index], y)
        y += heights[index]

    # The rule spans only the entries it holds together.
    rule_x = layout.agenda.left + layout.time_column
    draw.line((rule_x, list_top, rule_x, y - density.padding),
              fill=theme.INK_SOFT, width=max(1, layout.plate_stroke // 2))

    left_out = hidden + (len(events) - fitted)
    if left_out > 0:
        label = f"e altri {left_out} appuntamenti" if left_out > 1 else "e un altro appuntamento"
        draw.text((rule_x + layout.agenda_rule_gap, y + density.padding), label,
                  font=density.note_font, fill=theme.MUTED, anchor="lt")


def _choose_density(draw, layout: Layout, fonts: theme.Fonts, events: list[Event],
                    hidden: int, available: int):
    """Pick the loosest density that shows every event; else the tightest one."""
    best = None
    for density in _densities(layout, fonts):
        heights = [_row_height(draw, layout, density, event) for event in events]
        note_height = _text_height(draw, "e altri 2", density.note_font) + density.padding
        reserve = note_height if hidden else 0

        fitted = _fit_rows(heights, available, reserve)
        if fitted < len(events):
            fitted = _fit_rows(heights, available, note_height)

        best = (density, heights, fitted)
        if fitted == len(events) and not hidden:
            break
    return best


def _fit_rows(heights: list[int], available: int, reserve: int) -> int:
    """How many rows fit in `available` pixels, keeping `reserve` free at the end."""
    budget = available - reserve
    used = 0
    for count, height in enumerate(heights):
        if used + height > budget:
            return count
        used += height
    return len(heights)



def _draw_row(draw, layout: Layout, density: Density, event: Event, top: int) -> None:
    """Hour right-aligned against the rule, title left-aligned after it."""
    rule_x = layout.agenda.left + layout.time_column
    text_left = rule_x + layout.agenda_rule_gap
    ascent, descent = density.title_font.getmetrics()
    line_height = ascent + descent
    baseline = top + density.padding + ascent

    time_label, time_font = _time_label(event, density)
    draw.text((rule_x - layout.agenda_rule_gap, baseline), time_label,
              font=time_font, fill=theme.INK, anchor="rs")

    for offset, line in enumerate(_row_lines(draw, layout, density, event)):
        draw.text((text_left, baseline + offset * (line_height + density.line_spacing)),
                  line, font=density.title_font, fill=theme.INK, anchor="ls")


def _time_label(event: Event, density: Density):
    """All-day entries get a dash.

    The column is sized for `09:00`; `tutto il giorno` ran out of it and off the
    page. A dash is what a timetable uses for "no fixed hour", and it costs
    nothing to read.
    """
    if event.all_day:
        return ALL_DAY_DASH, density.time_font
    return event.start_label, density.time_font



def _row_lines(draw, layout: Layout, density: Density, event: Event) -> list[str]:
    width = layout.agenda.right - (layout.agenda.left + layout.time_column
                                   + layout.agenda_rule_gap)
    return _wrap_first_then_full(
        draw, event.title, density.title_font, width, width, MAX_TITLE_LINES,
    )


def _row_height(draw, layout: Layout, density: Density, event: Event) -> int:
    ascent, descent = density.title_font.getmetrics()
    lines = _row_lines(draw, layout, density, event)
    return ((ascent + descent) * len(lines)
            + density.line_spacing * (len(lines) - 1)
            + density.padding * 2)


def _draw_agenda_note(draw, layout: Layout, fonts: theme.Fonts, text: str, top: int) -> None:
    font = fonts.get(layout.size_note, theme.REGULAR)
    area = layout.agenda_text
    line_height = _text_height(draw, "Ag", font)
    for index, line in enumerate(text.split("\n")):
        draw.text((area.left, top + index * (line_height + layout.line_spacing)),
                  line, font=font, fill=theme.MUTED, anchor="lt")


# ─── Weather ────────────────────────────────────────────────────

def _weather_metrics(draw, layout: Layout, fonts: theme.Fonts, condition: str):
    """Icon size and total block height for the weather card.

    The icon is derived from the room the two text lines leave rather than
    fixed, so a short card cannot push *minima 20°* out through its bottom edge.
    """
    area = layout.weather.inset(layout.plate_padding)
    condition_font = _fitted_font(draw, condition, fonts, layout.size_condition,
                                  theme.REGULAR, area.width)
    range_font = fonts.get(layout.size_range, theme.REGULAR)

    condition_height = _text_height(draw, condition, condition_font)
    range_height = _text_height(draw, "minima 0°", range_font)
    text_block = (layout.line_spacing * 3 + condition_height + range_height)

    icon_size = max(round(layout.icon_size * 0.5),
                    min(layout.icon_size, area.height - text_block))
    return icon_size, icon_size + text_block, condition_font, range_font



def _draw_weather(draw, layout: Layout, fonts: theme.Fonts, board: Board) -> None:
    """No plate and no border: the picture is the background, and a box drawn
    on top of it would be one frame too many."""
    area = layout.weather
    temp_font = fonts.get(layout.size_temp, theme.HEAVY)
    high = _format_temp(board.weather.temp_max if board.weather else None,
                        board.weather.unit_symbol if board.weather else "°C")
    condition = board.weather.condition if board.weather else WEATHER_ERROR_LABEL
    code = board.weather.weather_code if board.weather else 3

    condition_font = _fitted_font(draw, condition, fonts, layout.size_condition,
                                  theme.REGULAR, area.width)
    range_font = fonts.get(layout.size_range, theme.REGULAR)

    temp_height = _text_height(draw, high, temp_font)
    icon = min(layout.icon_size, temp_height)

    # Icon and temperature on one line, right-aligned to the margin.
    temp_width = draw.textlength(high, font=temp_font)
    row_top = area.bottom - temp_height - _text_height(draw, condition, condition_font) \
        - _text_height(draw, "minima 0°", range_font) - layout.line_spacing * 2
    icons.draw_weather(draw, round(area.right - temp_width - layout.bullet_gap - icon),
                       row_top, icon, code)
    draw.text((area.right, row_top), high, font=temp_font, fill=theme.INK, anchor="rt")

    condition_y = row_top + temp_height + layout.line_spacing
    draw.text((area.right, condition_y), condition, font=condition_font,
              fill=theme.INK_SOFT, anchor="rt")

    if board.weather and board.weather.temp_min is not None:
        low = _format_temp(board.weather.temp_min, board.weather.unit_symbol)
        draw.text((area.right,
                   condition_y + _text_height(draw, condition, condition_font)
                   + layout.line_spacing),
                  f"minima {low}", font=range_font, fill=theme.MUTED, anchor="rt")


def _format_temp(value: float | None, unit_symbol: str) -> str:
    if value is None:
        return "—"
    return f"{round(value)}{unit_symbol[0]}"


# ─── Footer ─────────────────────────────────────────────────────

def _draw_footer(draw, layout: Layout, fonts: theme.Fonts, board: Board) -> None:
    font = fonts.get(layout.size_footer, theme.REGULAR)
    parts = [f"aggiornato alle {board.generated_at:%H:%M}"]
    if not board.weather_ok:
        parts.append(WEATHER_ERROR_LABEL)
    # Left, opposite the weather: on the right the two ran into each other.
    draw.text((layout.footer.left, (layout.footer.top + layout.footer.bottom) // 2),
              " · ".join(parts), font=font, fill=theme.MUTED, anchor="lm")


def _draw_debug_regions(draw, layout: Layout) -> None:
    for rect in (layout.banner, layout.agenda, layout.art, layout.weather, layout.footer):
        draw.rectangle(rect.as_tuple(), outline=theme.MUTED, width=2)


# ─── Drawing helpers ────────────────────────────────────────────

def _plate(draw, layout: Layout, rect: Rect) -> None:
    """A card: paper-white, rounded, with a thin outline."""
    draw.rounded_rectangle(rect.as_tuple(), radius=layout.plate_radius,
                           fill=theme.PLATE, outline=theme.INK_SOFT,
                           width=layout.plate_stroke)


def _dotted_rule(draw, left: int, right: int, y: int, thickness: int) -> None:
    """A dotted rule reads softer than a solid one, and hides banding better."""
    step = thickness * 4
    x = left
    while x < right:
        draw.rectangle((x, y, min(x + thickness, right), y + thickness - 1),
                       fill=theme.HAIRLINE)
        x += step


# ─── Text helpers ───────────────────────────────────────────────

def _fitted_font(draw, text: str, fonts: theme.Fonts, size: int, weight: int,
                 max_width: int):
    """Step the size down until the text fits — a long weekday must not overflow."""
    while size > 8:
        font = fonts.get(size, weight)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size = round(size * 0.94)
    return fonts.get(8, weight)


def _text_height(draw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text or "Ag", font=font, anchor="lt")
    return box[3] - box[1]


def _shorten(draw, text: str, font, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + ELLIPSIS, font=font) > max_width:
        text = text[:-1]
    return text.rstrip() + ELLIPSIS


def _wrap_first_then_full(draw, text: str, font, first_width: int, full_width: int,
                          max_lines: int) -> list[str]:
    """Wrap where the first line is shorter, because the time sits beside it."""
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = ""
    width = first_width

    for word in words:
        candidate = f"{current} {word}".strip()
        if _fits(draw, candidate, font, width):
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
            width = full_width
        if len(lines) == max_lines:
            return _ellipsise(draw, lines, font, full_width)
        if _fits(draw, word, font, width):
            current = word
            continue

        remainder = word
        while remainder and not _fits(draw, remainder, font, width):
            head, remainder = _break_word(draw, remainder, font, width)
            lines.append(head)
            width = full_width
            if len(lines) == max_lines:
                return _ellipsise(draw, lines, font, full_width)
        current = remainder

    if current:
        if len(lines) == max_lines:
            return _ellipsise(draw, lines, font, full_width)
        lines.append(current)
    return lines


def _fits(draw, text: str, font, max_width: int) -> bool:
    return draw.textlength(text, font=font) <= max_width


def _break_word(draw, word: str, font, max_width: int) -> tuple[str, str]:
    for cut in range(len(word) - 1, 0, -1):
        if _fits(draw, word[:cut], font, max_width):
            return word[:cut], word[cut:]
    return word[:1], word[1:]


def _ellipsise(draw, lines: list[str], font, max_width: int) -> list[str]:
    """Append an ellipsis to the last line, trimming it until it fits."""
    if not lines:
        return lines
    last = lines[-1]
    while last and not _fits(draw, last + ELLIPSIS, font, max_width):
        last = last[:-1]
    lines[-1] = last.rstrip() + ELLIPSIS
    return lines
