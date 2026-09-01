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

"""The hands the photographs can be drawn by.

One style a day, rotating alongside the photographs, so the same picture comes
back in a different register rather than looking like yesterday. Nothing here
needs a cache of its own: an illustration is keyed by photograph *and* prompt,
so a pairing already drawn is simply found, and one that has not been drawn
costs a call the first time and nothing afterwards.

Every style carries the same three constraints, because they are what make a
drawing survive the panel rather than the screen: monochrome, ink rather than
tone, and large areas of paper left alone. A style that fills the page with
grey is unreadable behind text at any wash.
"""
from __future__ import annotations

from datetime import date

CONSTRAINTS = (
    " Monochrome black ink on cream paper, no colour. Shadows are hatching or "
    "stippling, never grey fill. Leave large areas of the paper completely "
    "untouched. Keep the composition and the subjects recognisable. "
    "No text, no lettering, no border, no frame."
)

STYLES: dict[str, str] = {
    "libro": (
        "Redraw this photograph as a pen-and-ink illustration for a children's "
        "storybook: confident outlines, warm and gentle, the kind of drawing "
        "that sits beside a bedtime story."
    ),
    "fumetto": (
        "Redraw this photograph as a comic-book panel: bold varying-weight ink "
        "outlines, dramatic angles, halftone dot shading in the shadows, the "
        "look of a printed comic page."
    ),
    "western": (
        "Redraw this photograph as a nineteenth-century wood engraving from the "
        "American frontier: fine parallel burin lines, high contrast, the look "
        "of an old newspaper cut or a wanted poster."
    ),
    "fantascienza": (
        "Redraw this photograph as a retro science-fiction pulp illustration: "
        "clean technical linework, bold geometric shapes, dramatic contrast, "
        "the look of a 1950s magazine cover drawn in ink."
    ),
    "acquaforte": (
        "Redraw this photograph as an etching: dense cross-hatching for the "
        "darks, bare paper for the lights, the plate-printed look of an "
        "old master print."
    ),
    "giapponese": (
        "Redraw this photograph as a Japanese sumi-e brush drawing: few "
        "confident strokes, enormous empty space, the subject suggested rather "
        "than described."
    ),
}

DEFAULT_ROTATION = ("libro", "fumetto", "western", "fantascienza", "acquaforte", "giapponese")


class UnknownStyleError(ValueError):
    """A style was asked for by a name nobody defines."""


def prompt_for(name: str) -> str:
    """The full instruction for one style, constraints included."""
    try:
        return STYLES[name] + CONSTRAINTS
    except KeyError:
        raise UnknownStyleError(
            f"No style called {name!r}. Known: {', '.join(sorted(STYLES))}"
        ) from None


def rotation(names: str | None = None) -> tuple[str, ...]:
    """The styles in play, from a comma-separated list or all of them."""
    if not names:
        return DEFAULT_ROTATION
    chosen = tuple(part.strip() for part in names.split(",") if part.strip())
    for name in chosen:
        if name not in STYLES:
            raise UnknownStyleError(
                f"No style called {name!r}. Known: {', '.join(sorted(STYLES))}"
            )
    return chosen or DEFAULT_ROTATION


def style_for_day(day: date, names: str | None = None) -> str:
    """Which hand draws today.

    Taken from the date rather than from stored state, so it advances on its
    own and two devices sharing a library stay in step. The photograph rotates
    separately, which means a given pairing only comes round after both wheels
    have turned all the way — six photographs and six styles is thirty-six days
    before anything repeats.
    """
    styles = rotation(names)
    return styles[day.toordinal() % len(styles)]
