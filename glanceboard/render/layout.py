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

Every dimension derives from width and height, so the same layout renders on a
1072x1448 Paperwhite 3/4 and a 1236x1648 Paperwhite 5/6 without a second set of
numbers. The illustration band is reserved here in phase 1 even though nothing
draws into it yet: when the AI image arrives it lands in an area the rest of the
layout has already accounted for, instead of forcing a re-layout.
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

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)


class Layout:
    """Resolution-independent metrics for one canvas size."""

    def __init__(self, width: int, height: int, art_fraction: float = 0.30):
        if width < 200 or height < 200:
            raise ValueError(f"Canvas too small to lay out: {width}x{height}")
        if not 0.0 <= art_fraction <= 0.6:
            raise ValueError(f"art_fraction must be between 0 and 0.6, got {art_fraction}")
        self.width = width
        self.height = height
        self.art_fraction = art_fraction

        self.margin = round(0.055 * width)
        content_left = self.margin
        content_right = width - self.margin

        header_height = round(0.115 * height)
        footer_height = round(0.030 * height)
        art_height = round(art_fraction * height)

        self.header = Rect(content_left, self.margin, content_right, self.margin + header_height)
        self.rule_y = self.header.bottom + round(0.010 * height)
        self.rule_thickness = max(2, round(0.0035 * width))

        self.footer = Rect(
            content_left,
            height - self.margin - footer_height,
            content_right,
            height - self.margin,
        )
        self.art = Rect(
            content_left,
            self.footer.top - round(0.012 * height) - art_height,
            content_right,
            self.footer.top - round(0.012 * height),
        )
        self.agenda = Rect(
            content_left,
            self.rule_y + self.rule_thickness + round(0.026 * height),
            content_right,
            self.art.top - round(0.018 * height),
        )

        # Agenda row metrics
        self.time_column = round(0.21 * self.agenda.width)
        self.row_padding = round(0.012 * height)
        self.separator_thickness = max(1, round(0.0012 * height))
        self.line_spacing = round(0.006 * height)

        # Type scale, driven by width so line lengths stay constant in characters
        self.size_weekday = round(0.078 * width)
        self.size_date = round(0.038 * width)
        self.size_temp = round(0.062 * width)
        self.size_condition = round(0.028 * width)
        self.size_time = round(0.038 * width)
        self.size_time_end = round(0.026 * width)
        self.size_title = round(0.040 * width)
        self.size_note = round(0.030 * width)
        self.size_footer = round(0.021 * width)

    @property
    def title_column(self) -> int:
        """Width available to an event title, after the time column."""
        return self.agenda.width - self.time_column
