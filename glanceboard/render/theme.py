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

"""Typography, tones and Italian date vocabulary.

The typeface is Nunito — rounded terminals, generous counters — chosen to sit
next to the storybook illustration phase 2 will add rather than against it. It is
vendored in the repo rather than looked up on the system: a Mac and a Debian
container do not carry the same faces, and a layout you iterate on locally has to
be the layout that reaches the device.

Every tone is a multiple of 17, so the palette already lives on the panel's
16-level grid and quantization never shifts a fill.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONT_FILE = "Nunito[wght].ttf"

# Weight axis values used by the layout.
REGULAR = 400
MEDIUM = 500
SEMIBOLD = 600
BOLD = 700
HEAVY = 800

# Tones. The page is a shade off white and the cards are white, which gives the
# layout a little depth without a single drop shadow — e-ink has no use for one.
PAPER = 238
PLATE = 255
HAIRLINE = 187
MUTED = 119
INK_SOFT = 68
INK = 0


class FontMissingError(RuntimeError):
    """The vendored typeface is not where the configuration says it is."""


class Fonts:
    """Loads one variable font and instantiates it per size and weight."""

    def __init__(self, font_dir: Path):
        self.path = Path(font_dir) / FONT_FILE
        if not self.path.exists():
            raise FontMissingError(
                f"Font not found at {self.path}. It ships with the repo in "
                "assets/fonts/; set GB_FONT_DIR if it lives elsewhere."
            )

    @lru_cache(maxsize=64)
    def get(self, size: int, weight: int = REGULAR) -> ImageFont.FreeTypeFont:
        font = ImageFont.truetype(str(self.path), size)
        try:
            font.set_variation_by_axes([float(weight)])
        except OSError:
            # FreeType without variable-font support: fall back to the default
            # instance rather than failing the whole render.
            pass
        return font


WEEKDAYS = (
    "lunedì",
    "martedì",
    "mercoledì",
    "giovedì",
    "venerdì",
    "sabato",
    "domenica",
)

MONTHS = (
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
)


def weekday_name(day: date) -> str:
    """'martedì' — from an explicit table, never from the system locale."""
    return WEEKDAYS[day.weekday()]


def month_name(day: date) -> str:
    return MONTHS[day.month - 1]


def banner_date(day: date) -> str:
    """'Martedì 1 settembre' — what the ribbon across the top says."""
    return f"{weekday_name(day).capitalize()} {day.day} {month_name(day)}"


def long_date(day: date) -> str:
    """'1 settembre 2026'."""
    return f"{day.day} {month_name(day)} {day.year}"
