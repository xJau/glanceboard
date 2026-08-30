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
phase 2 the model fills the illustration band and nothing else, so an
appointment time can never be something a model guessed at, and a failed
generation costs the board its picture rather than its content.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from ..models import Board, Event
from . import theme
from .grayscale import quantize
from .layout import Layout

ELLIPSIS = "…"
MAX_TITLE_LINES = 2

EMPTY_LABEL = "Nessuna cosa in agenda"
CALENDAR_ERROR_LABEL = "Calendario non raggiungibile"
WEATHER_ERROR_LABEL = "meteo non disponibile"
ALL_DAY_LABEL = "tutto il giorno"


def render_board(
    board: Board,
    width: int,
    height: int,
    font_dir: Path,
    max_events: int = 12,
    art_fraction: float = 0.30,
    debug_regions: bool = False,
) -> Image.Image:
    """Render `board` and return a 16-level grayscale image."""
    layout = Layout(width, height, art_fraction=art_fraction)
    fonts = theme.Fonts(font_dir)

    image = Image.new("L", (width, height), theme.PAPER)
    draw = ImageDraw.Draw(image)

    _draw_header(draw, layout, fonts, board)
    _draw_rule(draw, layout)
    _draw_agenda(draw, layout, fonts, board, max_events)
    _draw_footer(draw, layout, fonts, board)

    if debug_regions:
        _draw_debug_regions(draw, layout)

    return quantize(image)


# ─── Header ─────────────────────────────────────────────────────

def _draw_header(draw: ImageDraw.ImageDraw, layout: Layout, fonts: theme.Fonts, board: Board) -> None:
    weekday_font = fonts.get(layout.size_weekday, theme.BOLD)
    date_font = fonts.get(layout.size_date, theme.REGULAR)
    temp_font = fonts.get(layout.size_temp, theme.SEMIBOLD)
    condition_font = fonts.get(layout.size_condition, theme.REGULAR)

    weekday = theme.weekday_name(board.day).capitalize()
    draw.text((layout.header.left, layout.header.top), weekday, font=weekday_font,
              fill=theme.INK, anchor="lt")

    weekday_height = _text_height(draw, weekday, weekday_font)
    date_y = layout.header.top + weekday_height + layout.line_spacing
    draw.text((layout.header.left, date_y), theme.long_date(board.day), font=date_font,
              fill=theme.INK_SOFT, anchor="lt")

    temps = _temperature_label(board)
    draw.text((layout.header.right, layout.header.top), temps, font=temp_font,
              fill=theme.INK, anchor="rt")

    condition = board.weather.condition if board.weather else "—"
    temps_height = _text_height(draw, temps, temp_font)
    draw.text((layout.header.right, layout.header.top + temps_height + layout.line_spacing),
              condition, font=condition_font, fill=theme.MUTED, anchor="rt")


def _temperature_label(board: Board) -> str:
    """'12° / 24°', with an em dash for whatever the API did not return."""
    if board.weather is None:
        return "—"
    degree = board.weather.unit_symbol[0]  # the scale letter lives in the condition line
    low = _round_temp(board.weather.temp_min)
    high = _round_temp(board.weather.temp_max)
    if low is None and high is None:
        return "—"
    low_text = f"{low}{degree}" if low is not None else "—"
    high_text = f"{high}{degree}" if high is not None else "—"
    return f"{low_text} / {high_text}"


def _round_temp(value: float | None) -> int | None:
    return None if value is None else round(value)


def _draw_rule(draw: ImageDraw.ImageDraw, layout: Layout) -> None:
    draw.rectangle(
        (layout.header.left, layout.rule_y,
         layout.header.right, layout.rule_y + layout.rule_thickness - 1),
        fill=theme.INK,
    )


# ─── Agenda ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class Density:
    """One way of spending vertical space on a row.

    A busy day compacts before it starts dropping appointments: losing the end
    time is a smaller loss than losing the fact that a client is coming at six.
    """

    time_font: object
    end_font: object
    title_font: object
    note_font: object
    padding: int
    line_spacing: int
    show_end: bool


def _densities(layout: Layout, fonts: theme.Fonts) -> tuple[Density, ...]:
    comfortable = Density(
        time_font=fonts.get(layout.size_time, theme.SEMIBOLD),
        end_font=fonts.get(layout.size_time_end, theme.REGULAR),
        title_font=fonts.get(layout.size_title, theme.REGULAR),
        note_font=fonts.get(layout.size_note, theme.REGULAR),
        padding=layout.row_padding,
        line_spacing=layout.line_spacing,
        show_end=True,
    )
    snug = Density(
        time_font=comfortable.time_font,
        end_font=comfortable.end_font,
        title_font=comfortable.title_font,
        note_font=comfortable.note_font,
        padding=max(2, round(layout.row_padding * 0.6)),
        line_spacing=max(2, round(layout.line_spacing * 0.8)),
        show_end=True,
    )
    compact = Density(
        time_font=fonts.get(round(layout.size_time * 0.86), theme.SEMIBOLD),
        end_font=fonts.get(round(layout.size_time_end * 0.86), theme.REGULAR),
        title_font=fonts.get(round(layout.size_title * 0.86), theme.REGULAR),
        note_font=fonts.get(round(layout.size_note * 0.86), theme.REGULAR),
        padding=max(2, round(layout.row_padding * 0.55)),
        line_spacing=max(2, round(layout.line_spacing * 0.7)),
        show_end=False,
    )
    return (comfortable, snug, compact)


def _draw_agenda(
    draw: ImageDraw.ImageDraw,
    layout: Layout,
    fonts: theme.Fonts,
    board: Board,
    max_events: int,
) -> None:
    if not board.calendar_ok:
        _draw_agenda_note(draw, layout, fonts, CALENDAR_ERROR_LABEL)
        return
    if not board.events:
        _draw_agenda_note(draw, layout, fonts, EMPTY_LABEL)
        return

    events = list(board.events[:max_events])
    hidden = len(board.events) - len(events)

    density, heights, fitted = _choose_density(draw, layout, fonts, events, hidden)

    y = layout.agenda.top
    for index in range(fitted):
        _draw_row(draw, layout, density, events[index], y)
        y += heights[index]
        if index < fitted - 1:
            draw.rectangle(
                (layout.agenda.left, y, layout.agenda.right, y + layout.separator_thickness - 1),
                fill=theme.HAIRLINE,
            )

    left_out = hidden + (len(events) - fitted)
    if left_out > 0:
        label = f"+{left_out} altri" if left_out > 1 else "+1 altro"
        draw.text((layout.agenda.left, y + density.padding), label,
                  font=density.note_font, fill=theme.MUTED, anchor="lt")


def _choose_density(draw, layout: Layout, fonts: theme.Fonts, events: list[Event], hidden: int):
    """Pick the loosest density that shows every event; else the tightest one."""
    best = None
    for density in _densities(layout, fonts):
        heights = [_row_height(draw, layout, density, event) for event in events]
        note_height = _text_height(draw, "+0 altri", density.note_font) + density.padding
        reserve = note_height if hidden else 0

        fitted = _fit_rows(heights, layout.agenda.height, reserve)
        if fitted < len(events):
            # Something will be left over, so the note needs its space after all.
            fitted = _fit_rows(heights, layout.agenda.height, note_height)

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
    text_top = top + density.padding
    title_x = layout.agenda.left + layout.time_column

    if event.all_day:
        label_lines = _wrap(draw, ALL_DAY_LABEL, density.end_font,
                            layout.time_column - density.line_spacing, 2)
        label_height = _text_height(draw, ALL_DAY_LABEL, density.end_font)
        for line_index, line in enumerate(label_lines):
            draw.text((layout.agenda.left, text_top + line_index * (label_height + density.line_spacing)),
                      line, font=density.end_font, fill=theme.MUTED, anchor="lt")
    else:
        draw.text((layout.agenda.left, text_top), event.start_label, font=density.time_font,
                  fill=theme.INK, anchor="lt")
        if density.show_end and event.end_label:
            end_y = text_top + _text_height(draw, event.start_label, density.time_font) + density.line_spacing
            draw.text((layout.agenda.left, end_y), event.end_label, font=density.end_font,
                      fill=theme.MUTED, anchor="lt")

    lines = _wrap(draw, event.title, density.title_font, layout.title_column, MAX_TITLE_LINES)
    line_height = _text_height(draw, "Ag", density.title_font)
    for line_index, line in enumerate(lines):
        draw.text((title_x, text_top + line_index * (line_height + density.line_spacing)),
                  line, font=density.title_font, fill=theme.INK, anchor="lt")


def _row_height(draw, layout: Layout, density: Density, event: Event) -> int:
    line_height = _text_height(draw, "Ag", density.title_font)
    title_lines = len(_wrap(draw, event.title, density.title_font, layout.title_column, MAX_TITLE_LINES))
    title_height = title_lines * line_height + (title_lines - 1) * density.line_spacing

    if event.all_day:
        label_lines = len(_wrap(draw, ALL_DAY_LABEL, density.end_font,
                                layout.time_column - density.line_spacing, 2))
        label_height = _text_height(draw, ALL_DAY_LABEL, density.end_font)
        time_height = label_lines * label_height + (label_lines - 1) * density.line_spacing
    else:
        time_height = _text_height(draw, event.start_label, density.time_font)
        if density.show_end and event.end_label:
            time_height += density.line_spacing + _text_height(draw, event.end_label, density.end_font)

    return max(title_height, time_height) + 2 * density.padding


def _draw_agenda_note(draw, layout: Layout, fonts: theme.Fonts, text: str) -> None:
    font = fonts.get(layout.size_note, theme.REGULAR)
    draw.text((layout.agenda.left, layout.agenda.top + layout.agenda.height // 3),
              text, font=font, fill=theme.MUTED, anchor="lt")


# ─── Footer ─────────────────────────────────────────────────────

def _draw_footer(draw, layout: Layout, fonts: theme.Fonts, board: Board) -> None:
    font = fonts.get(layout.size_footer, theme.REGULAR)
    draw.text((layout.footer.left, layout.footer.bottom),
              f"aggiornato {board.generated_at:%H:%M}",
              font=font, fill=theme.MUTED, anchor="ls")

    if not board.weather_ok:
        draw.text((layout.footer.right, layout.footer.bottom), WEATHER_ERROR_LABEL,
                  font=font, fill=theme.MUTED, anchor="rs")


def _draw_debug_regions(draw, layout: Layout) -> None:
    for rect in (layout.header, layout.agenda, layout.art, layout.footer):
        draw.rectangle(rect.as_tuple(), outline=theme.HAIRLINE, width=2)


# ─── Text helpers ───────────────────────────────────────────────

def _text_height(draw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text or "Ag", font=font, anchor="lt")
    return box[3] - box[1]


def _wrap(draw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    """Greedy word wrap, ellipsised once it runs out of lines.

    A single word longer than the column is broken mid-word rather than allowed
    to run past the margin — client names and system-generated titles are both
    capable of producing one.
    """
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        if _fits(draw, candidate, font, max_width):
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        if len(lines) == max_lines:
            return _ellipsise(draw, lines, font, max_width, remainder=True)
        if _fits(draw, word, font, max_width):
            current = word
            continue

        # A word wider than the column: keep slicing until the tail fits, so no
        # fragment can be left over-wide by a single break.
        remainder = word
        while remainder and not _fits(draw, remainder, font, max_width):
            head, remainder = _break_word(draw, remainder, font, max_width)
            lines.append(head)
            if len(lines) == max_lines:
                return _ellipsise(draw, lines, font, max_width, remainder=True)
        current = remainder

    if current:
        if len(lines) == max_lines:
            return _ellipsise(draw, lines, font, max_width, remainder=True)
        lines.append(current)
    return lines


def _fits(draw, text: str, font, max_width: int) -> bool:
    return draw.textlength(text, font=font) <= max_width


def _break_word(draw, word: str, font, max_width: int) -> tuple[str, str]:
    for cut in range(len(word) - 1, 0, -1):
        if _fits(draw, word[:cut], font, max_width):
            return word[:cut], word[cut:]
    return word[:1], word[1:]


def _ellipsise(draw, lines: list[str], font, max_width: int, remainder: bool) -> list[str]:
    """Append an ellipsis to the last line, trimming it until it fits."""
    if not remainder or not lines:
        return lines
    last = lines[-1]
    while last and not _fits(draw, last + ELLIPSIS, font, max_width):
        last = last[:-1]
    lines[-1] = last.rstrip() + ELLIPSIS
    return lines
