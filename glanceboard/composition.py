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

"""Which half of the picture the text should stand on.

The board sets its list down one side of the page. Which side should depend on
the picture: text over an empty sky reads; text over somebody's face does not.

Two ways to decide, and the cheap one is the reliable one. Counting ink in each
half of the drawing is exact, costs nothing and cannot be wrong about what is
actually there. A model knows something the count does not — that a hatched sky
is busy but unimportant, while a face may be sparse and matter enormously — so
its opinion wins when it has one, and the count decides when it does not.
"""
from __future__ import annotations

import logging

from PIL import Image

log = logging.getLogger(__name__)

LEFT = "left"
RIGHT = "right"

#: Below this difference the two halves are as good as each other, and the
#: layout should stay where it is rather than flapping from day to day.
INDIFFERENCE = 0.04


def ink_by_half(illustration: Image.Image) -> tuple[float, float]:
    """How dark each half of the picture is, from 0 (blank) to 1 (solid)."""
    grey = illustration.convert("L")
    width, height = grey.size
    halves = (
        grey.crop((0, 0, width // 2, height)),
        grey.crop((width // 2, 0, width, height)),
    )
    return tuple(1.0 - (_mean(half) / 255.0) for half in halves)


def quieter_side(illustration: Image.Image, current: str = LEFT) -> str:
    """The side with less ink on it, or `current` when the two are alike.

    Keeping the previous side on a near-tie matters more than it sounds: a
    board that swaps its layout every morning on a hair's difference is harder
    to read than one that simply stays put.
    """
    left, right = ink_by_half(illustration)
    if abs(left - right) < INDIFFERENCE:
        return current
    return LEFT if left < right else RIGHT


def side_away_from(subject: str | None, illustration: Image.Image, current: str = LEFT) -> str:
    """Put the text opposite the subject, if we were told where it is.

    `subject` is what a model reported: "left", "right", or anything else —
    "centre", None, a shrug — in which case the ink decides.
    """
    if subject == LEFT:
        return RIGHT
    if subject == RIGHT:
        return LEFT
    return quieter_side(illustration, current)


def _mean(image: Image.Image) -> float:
    histogram = image.histogram()
    total = sum(histogram)
    if not total:
        return 255.0
    return sum(value * count for value, count in enumerate(histogram)) / total
