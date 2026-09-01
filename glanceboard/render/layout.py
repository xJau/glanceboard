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

"""Geometry of the board, expressed as fractions of the canvas.

Landscape composition, following the shape of the original Glanceboard: a ribbon
across the top, the day's list on the left, the weather down in the corner, and
an illustration panel on the right that phase 2 fills.

Every dimension derives from width and height, so the same layout renders at
1448×1072 and at any other landscape panel without a second set of numbers.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def centre_x(self) -> int:
        return (self.left + self.right) // 2

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

    def inset(self, amount: int) -> "Rect":
        return Rect(self.left + amount, self.top + amount,
                    self.right - amount, self.bottom - amount)


class Layout:
    """Resolution-independent metrics for one canvas size."""

    def __init__(self, width: int, height: int, art_fraction: float = 0.34):
        if width < 200 or height < 200:
            raise ValueError(f"Canvas too small to lay out: {width}x{height}")
        if not 0.0 <= art_fraction <= 0.6:
            raise ValueError(f"art_fraction must be between 0 and 0.6, got {art_fraction}")

        self.width = width
        self.height = height
        self.art_fraction = art_fraction

        short_side = min(width, height)

        # The frame: two lines just inside the edge, like a mount board.
        self.frame_outer = round(0.022 * short_side)
        self.frame_gap = round(0.011 * short_side)
        self.frame_stroke = max(2, round(0.004 * short_side))
        self.corner_radius = round(0.030 * short_side)

        padding = round(0.042 * short_side)
        self.content = Rect(
            self.frame_outer + self.frame_gap + padding,
            self.frame_outer + self.frame_gap + padding,
            width - self.frame_outer - self.frame_gap - padding,
            height - self.frame_outer - self.frame_gap - padding,
        )

        # Ribbon across the top, centred.
        banner_height = round(0.120 * height)
        banner_width = round(0.58 * width)
        self.banner = Rect(
            self.content.centre_x - banner_width // 2,
            self.content.top,
            self.content.centre_x + banner_width // 2,
            self.content.top + banner_height,
        )
        self.banner_notch = round(banner_height * 0.30)

        gutter = round(0.030 * short_side)
        columns_top = self.banner.bottom + round(0.040 * height)
        left_width = round((1.0 - art_fraction) * self.content.width) - gutter

        # The agenda takes the whole left column. In landscape the canvas is
        # short, and the list is the thing that needs the height.
        self.agenda = Rect(
            self.content.left,
            columns_top,
            self.content.left + left_width,
            self.content.bottom,
        )

        # Right column: the illustration panel above, weather in the corner
        # below it — the position it holds in the original.
        # The weather is a glance, not a panel: a smaller card leaves the
        # illustration the room it deserves. The block inside it shrinks its
        # icon to fit whatever height is left, so this stays a free choice.
        weather_height = round(0.185 * height)
        self.weather = Rect(
            self.agenda.right + gutter,
            self.content.bottom - weather_height,
            self.content.right,
            self.content.bottom,
        )

        # Nothing is drawn in the art panel in phase 1; it exists so the picture,
        # when it arrives, lands in space the rest of the layout has accounted for.
        self.art = Rect(
            self.agenda.right + gutter,
            columns_top,
            self.content.right,
            self.weather.top - gutter,
        )

        # The timestamp is a caption in the margin below the cards, not a card.
        self.footer = Rect(
            self.content.left,
            self.content.bottom,
            self.content.right,
            height - self.frame_outer - self.frame_gap,
        )

        # Cards
        self.plate_radius = round(0.026 * short_side)
        self.plate_padding = round(0.030 * short_side)
        self.plate_stroke = max(2, round(0.0035 * short_side))

        # Agenda rows
        self.bullet_radius = max(3, round(0.007 * short_side))
        self.bullet_gap = round(0.022 * short_side)
        self.row_padding = round(0.013 * short_side)
        self.line_spacing = round(0.008 * short_side)

        # Type scale, driven by the short side so the proportions hold across
        # panel sizes.
        self.size_banner = round(0.070 * short_side)
        self.size_heading = round(0.032 * short_side)
        self.size_time = round(0.040 * short_side)
        self.size_title = round(0.040 * short_side)
        self.size_note = round(0.034 * short_side)
        self.size_temp = round(0.070 * short_side)
        self.size_condition = round(0.030 * short_side)
        self.size_range = round(0.026 * short_side)
        self.size_footer = round(0.026 * short_side)

        self.icon_size = round(0.105 * short_side)

    @property
    def agenda_text(self) -> Rect:
        """The area inside the agenda card, after its padding."""
        return self.agenda.inset(self.plate_padding)

    @property
    def row_text_width(self) -> int:
        return self.agenda_text.width - self.bullet_radius * 2 - self.bullet_gap
