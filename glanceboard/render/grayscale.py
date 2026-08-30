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

"""16-level grayscale quantization for the Kindle's 4bpp panel.

The panel shows 16 grays. Antialiased text drawn in 8-bit and then snapped to
those 16 levels stays crisp; dithering text would not, so nothing here dithers.
"""
from __future__ import annotations

from PIL import Image

LEVELS = 16
STEP = 255 / (LEVELS - 1)  # 17.0

#: Lookup table mapping every 8-bit value to its nearest of the 16 levels.
_LUT = [round(round(value / STEP) * STEP) for value in range(256)]


def quantize(image: Image.Image) -> Image.Image:
    """Snap an 'L' image to the 16 grays the Kindle can actually show."""
    if image.mode != "L":
        image = image.convert("L")
    return image.point(_LUT)


def levels_used(image: Image.Image) -> set[int]:
    """Distinct gray values present. Used by tests to prove the panel fit."""
    if image.mode != "L":
        image = image.convert("L")
    return {value for value, count in enumerate(image.histogram()) if count}
