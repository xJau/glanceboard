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

"""Weather glyphs, drawn as outlines rather than set as emoji.

An emoji would arrive as a colour bitmap, quantize into a grey smudge, and vary
with whatever font happened to be installed. These are a few dozen strokes each,
identical on every machine, and they scale with the panel.
"""
from __future__ import annotations

from PIL import ImageDraw

from . import theme

# WMO interpretation codes grouped by what they should look like.
_GROUPS: tuple[tuple[str, frozenset[int]], ...] = (
    ("clear", frozenset({0})),
    ("mostly_clear", frozenset({1, 2})),
    ("cloud", frozenset({3})),
    ("fog", frozenset({45, 48})),
    ("rain", frozenset({51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82})),
    ("snow", frozenset({71, 73, 75, 77, 85, 86})),
    ("storm", frozenset({95, 96, 99})),
)


def glyph_for(weather_code: int) -> str:
    for name, codes in _GROUPS:
        if weather_code in codes:
            return name
    return "cloud"


def draw_weather(draw: ImageDraw.ImageDraw, left: int, top: int, size: int,
                 weather_code: int) -> None:
    """Draw the glyph for `weather_code` inside a `size`-square box."""
    stroke = max(2, round(size * 0.055))
    glyph = glyph_for(weather_code)

    if glyph == "clear":
        _sun(draw, left, top, size, stroke)
    elif glyph == "mostly_clear":
        _sun(draw, left, top, round(size * 0.62), stroke)
        _cloud(draw, left, top + round(size * 0.30), size, stroke)
    elif glyph == "cloud":
        _cloud(draw, left, top + round(size * 0.16), size, stroke)
    elif glyph == "fog":
        _cloud(draw, left, top + round(size * 0.02), round(size * 0.92), stroke)
        _fog_lines(draw, left, top + round(size * 0.66), size, stroke)
    elif glyph == "rain":
        _cloud(draw, left, top, size, stroke)
        _drops(draw, left, top + round(size * 0.62), size, stroke)
    elif glyph == "snow":
        _cloud(draw, left, top, size, stroke)
        _flakes(draw, left, top + round(size * 0.62), size, stroke)
    else:
        _cloud(draw, left, top, size, stroke)
        _bolt(draw, left, top + round(size * 0.52), size)


def _sun(draw, left: int, top: int, size: int, stroke: int) -> None:
    radius = round(size * 0.22)
    cx = left + size // 2
    cy = top + size // 2
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                 outline=theme.INK, width=stroke)

    ray_inner = radius + round(size * 0.09)
    ray_outer = radius + round(size * 0.22)
    # Eight rays: the four square ones, then the four diagonals at 0.7 of the
    # offset so they end on the same circle.
    offsets = (
        (0, -1), (0, 1), (-1, 0), (1, 0),
        (-0.7, -0.7), (0.7, -0.7), (-0.7, 0.7), (0.7, 0.7),
    )
    for dx, dy in offsets:
        draw.line(
            (cx + dx * ray_inner, cy + dy * ray_inner,
             cx + dx * ray_outer, cy + dy * ray_outer),
            fill=theme.INK, width=stroke,
        )


def _cloud(draw, left: int, top: int, size: int, stroke: int) -> None:
    """Three overlapping discs on a flat base, filled so rays do not show through."""
    width = size
    base_y = top + round(size * 0.60)
    left_r = round(width * 0.17)
    mid_r = round(width * 0.23)
    right_r = round(width * 0.15)

    left_c = (left + round(width * 0.24), base_y - left_r + stroke)
    mid_c = (left + round(width * 0.47), base_y - mid_r - round(size * 0.04))
    right_c = (left + round(width * 0.72), base_y - right_r + stroke)

    body = (left + round(width * 0.16), base_y - round(size * 0.16),
            left + round(width * 0.86), base_y)

    for centre, radius in ((left_c, left_r), (mid_c, mid_r), (right_c, right_r)):
        draw.ellipse((centre[0] - radius, centre[1] - radius,
                      centre[0] + radius, centre[1] + radius),
                     fill=theme.PLATE, outline=theme.INK, width=stroke)
    draw.rounded_rectangle(body, radius=round(size * 0.08),
                           fill=theme.PLATE, outline=theme.INK, width=stroke)
    # Erase the seams the outlines left inside the body.
    draw.rounded_rectangle(
        (body[0] + stroke, body[1] - round(size * 0.10),
         body[2] - stroke, body[3] - stroke),
        radius=round(size * 0.06), fill=theme.PLATE,
    )
    draw.line((body[0] + round(size * 0.02), body[3],
               body[2] - round(size * 0.02), body[3]),
              fill=theme.INK, width=stroke)


def _drops(draw, left: int, top: int, size: int, stroke: int) -> None:
    for index in range(3):
        x = left + round(size * (0.30 + index * 0.18))
        draw.line((x, top, x - round(size * 0.06), top + round(size * 0.20)),
                  fill=theme.INK, width=stroke)


def _flakes(draw, left: int, top: int, size: int, stroke: int) -> None:
    arm = round(size * 0.07)
    for index in range(3):
        cx = left + round(size * (0.30 + index * 0.18))
        cy = top + round(size * 0.10)
        draw.line((cx - arm, cy, cx + arm, cy), fill=theme.INK, width=stroke)
        draw.line((cx, cy - arm, cx, cy + arm), fill=theme.INK, width=stroke)


def _fog_lines(draw, left: int, top: int, size: int, stroke: int) -> None:
    for index in range(3):
        y = top + index * round(size * 0.12)
        inset = round(size * 0.16) + (index % 2) * round(size * 0.08)
        draw.line((left + inset, y, left + size - inset, y),
                  fill=theme.INK, width=stroke)


def _bolt(draw, left: int, top: int, size: int) -> None:
    x = left + round(size * 0.42)
    draw.polygon(
        [
            (x + round(size * 0.06), top),
            (x - round(size * 0.08), top + round(size * 0.20)),
            (x + round(size * 0.02), top + round(size * 0.20)),
            (x - round(size * 0.06), top + round(size * 0.40)),
            (x + round(size * 0.14), top + round(size * 0.16)),
            (x + round(size * 0.04), top + round(size * 0.16)),
        ],
        fill=theme.INK,
    )
