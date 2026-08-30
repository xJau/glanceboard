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

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

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
) -> Image.Image:
    """Render `board` and return a 16-level grayscale image."""
    layout = Layout(width, height, art_fraction=art_fraction)
    fonts = theme.Fonts(font_dir)

    image = Image.new("L", (width, height), theme.PAPER)
    draw = ImageDraw.Draw(image)

    _draw_frame(draw, layout)
    _draw_banner(draw, layout, fonts, board)
    _draw_agenda(draw, layout, fonts, board, max_events)
    _draw_weather(draw, layout, fonts, board)
    _draw_footer(draw, layout, fonts, board)

    if debug_regions:
        _draw_debug_regions(draw, layout)

    return quantize(image)


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
    """A ribbon with notched ends carrying the date."""
    banner = layout.banner
    notch = layout.banner_notch
    stroke = layout.plate_stroke

    draw.polygon(
        [
            (banner.left, banner.top),
            (banner.right, banner.top),
            (banner.right - notch, banner.centre_x * 0 + (banner.top + banner.bottom) // 2),
            (banner.right, banner.bottom),
            (banner.left, banner.bottom),
            (banner.left + notch, (banner.top + banner.bottom) // 2),
        ],
        fill=theme.PLATE, outline=theme.INK,
    )
    # Redraw the outline thicker: polygon() only strokes a single pixel.
    _polygon_outline(
        draw,
        [
            (banner.left, banner.top),
            (banner.right, banner.top),
            (banner.right - notch, (banner.top + banner.bottom) // 2),
            (banner.right, banner.bottom),
            (banner.left, banner.bottom),
            (banner.left + notch, (banner.top + banner.bottom) // 2),
        ],
        stroke,
    )

    text = theme.banner_date(board.day)
    inner_width = banner.width - 2 * notch - layout.plate_padding
    font = _fitted_font(draw, text, fonts, layout.size_banner, theme.HEAVY, inner_width)
    draw.text((banner.centre_x, (banner.top + banner.bottom) // 2),
              text, font=font, fill=theme.INK, anchor="mm")


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
    _plate(draw, layout, layout.agenda)

    area = layout.agenda_text
    heading_font = fonts.get(layout.size_heading, theme.BOLD)
    draw.text((area.left, area.top), AGENDA_HEADING.upper(), font=heading_font,
              fill=theme.MUTED, anchor="lt")

    heading_bottom = area.top + _text_height(draw, AGENDA_HEADING, heading_font)
    _dotted_rule(draw, area.left, area.right, heading_bottom + layout.line_spacing * 2,
                 layout.plate_stroke)
    list_top = heading_bottom + layout.line_spacing * 4

    if not board.calendar_ok:
        _draw_agenda_note(draw, layout, fonts, CALENDAR_ERROR_LABEL, list_top)
        return
    if not board.events:
        _draw_agenda_note(draw, layout, fonts, EMPTY_LABEL, list_top)
        return

    events = list(board.events[:max_events])
    hidden = len(board.events) - len(events)
    available = area.bottom - list_top

    density, heights, fitted = _choose_density(draw, layout, fonts, events, hidden, available)

    y = list_top
    for index in range(fitted):
        _draw_row(draw, layout, density, events[index], y)
        y += heights[index]

    left_out = hidden + (len(events) - fitted)
    if left_out > 0:
        label = f"e altri {left_out} appuntamenti" if left_out > 1 else "e un altro appuntamento"
        draw.text((area.left, y + density.padding), label,
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
    """`• 09:00 — Consulenza Rossi`, wrapped under the time when it runs long."""
    area = layout.agenda_text
    text_left = area.left + layout.bullet_radius * 2 + layout.bullet_gap
    ascent, descent = density.title_font.getmetrics()
    line_height = ascent + descent

    baseline = top + density.padding + ascent
    draw.ellipse(
        (area.left, baseline - ascent // 2 - layout.bullet_radius,
         area.left + layout.bullet_radius * 2, baseline - ascent // 2 + layout.bullet_radius),
        fill=theme.INK,
    )

    time_label, time_font = _time_label(event, density)
    draw.text((text_left, baseline), time_label, font=time_font,
              fill=theme.INK, anchor="ls")

    # Everything after the time is one string, so the dash sits on the same
    # baseline as the words around it rather than being placed on its own.
    title_x = (text_left + draw.textlength(time_label, font=time_font)
               + draw.textlength(" ", font=density.title_font))
    lines = _row_lines(draw, layout, density, event)

    draw.text((title_x, baseline), lines[0], font=density.title_font,
              fill=theme.INK, anchor="ls")
    for offset, line in enumerate(lines[1:], start=1):
        draw.text((text_left, baseline + offset * (line_height + density.line_spacing)),
                  line, font=density.title_font, fill=theme.INK, anchor="ls")


def _time_label(event: Event, density: Density):
    """All-day entries get the small muted face; their label is a long one."""
    if event.all_day:
        return ALL_DAY_LABEL, density.note_font
    return event.start_label, density.time_font


def _row_lines(draw, layout: Layout, density: Density, event: Event) -> list[str]:
    area = layout.agenda_text
    text_left = area.left + layout.bullet_radius * 2 + layout.bullet_gap
    time_label, time_font = _time_label(event, density)
    title_x = (text_left + draw.textlength(time_label, font=time_font)
               + draw.textlength(" ", font=density.title_font))

    return _wrap_first_then_full(
        draw, f"{SEPARATOR} {event.title}", density.title_font,
        max(0, area.right - title_x), area.right - text_left, MAX_TITLE_LINES,
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

def _draw_weather(draw, layout: Layout, fonts: theme.Fonts, board: Board) -> None:
    _plate(draw, layout, layout.weather)
    area = layout.weather.inset(layout.plate_padding)

    code = board.weather.weather_code if board.weather else 3
    temp_font = fonts.get(layout.size_temp, theme.HEAVY)
    condition_font = fonts.get(layout.size_condition, theme.REGULAR)
    range_font = fonts.get(layout.size_range, theme.REGULAR)

    high = _format_temp(board.weather.temp_max if board.weather else None,
                        board.weather.unit_symbol if board.weather else "°C")
    condition = board.weather.condition if board.weather else WEATHER_ERROR_LABEL

    text_width = max(draw.textlength(high, font=temp_font),
                     draw.textlength(condition, font=condition_font))
    group_width = min(area.width, layout.icon_size + layout.bullet_gap + text_width)
    group_left = area.left + max(0, (area.width - round(group_width)) // 2)

    icon_top = area.top + max(0, (area.height - layout.icon_size) // 2)
    icons.draw_weather(draw, group_left, icon_top, layout.icon_size, code)

    text_left = group_left + layout.icon_size + layout.bullet_gap
    draw.text((text_left, icon_top), high, font=temp_font, fill=theme.INK, anchor="lt")

    condition_y = icon_top + _text_height(draw, high, temp_font) + layout.line_spacing
    condition = _shorten(draw, condition, condition_font, area.right - text_left)
    draw.text((text_left, condition_y), condition, font=condition_font,
              fill=theme.INK_SOFT, anchor="lt")

    if board.weather and board.weather.temp_min is not None:
        low = _format_temp(board.weather.temp_min, board.weather.unit_symbol)
        range_y = condition_y + _text_height(draw, condition, condition_font) + layout.line_spacing
        draw.text((text_left, range_y), f"minima {low}", font=range_font,
                  fill=theme.MUTED, anchor="lt")


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
    draw.text((layout.footer.right, (layout.footer.top + layout.footer.bottom) // 2),
              " · ".join(parts), font=font, fill=theme.MUTED, anchor="rm")


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
