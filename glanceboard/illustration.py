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

"""The one place that talks to an image model.

A photo from the library goes out, an illustration comes back, and the result
is cached on disk so a day costs a single call however many times the board is
regenerated.

Two things this module deliberately does not do. It never sees the calendar:
the request carries a style instruction and a photograph, so an appointment
cannot reach a model even by accident. And it never decides what happens when
it fails — it raises, and the pipeline treats a missing illustration the way it
treats missing weather.
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging
import mimetypes
from pathlib import Path

import requests
from PIL import Image

log = logging.getLogger(__name__)

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

DEFAULT_MODEL = "gemini-2.5-flash-image"

DEFAULT_STYLE_PROMPT = (
    "Redraw this photograph as a pen-and-ink line drawing for a children's "
    "storybook. Confident black outlines describe every shape; shadows are "
    "cross-hatching and stippling, never grey fill. Leave large areas of the "
    "cream paper completely untouched — the drawing should read as ink on an "
    "empty page, not as a tonal picture. Keep the composition and the subjects "
    "recognisable. Monochrome, no colour, no photographic shading, no soft "
    "gradients. No text, no lettering, no border, no frame."
)
"""The style, written for a panel with sixteen greys and text drawn on top.

An earlier version asked for "soft ink linework with gentle, flat shading" and
got exactly that: tonal masses that turned to mud once washed back far enough
for black type to read over them. Insisting on outlines, hatching and untouched
paper produces a drawing that is mostly empty — which is what lets the wash be
gentle and the picture still be visible.
"""


class IllustrationError(RuntimeError):
    """The model did not return a usable picture."""


def build_prompt(style_prompt: str | None = None) -> str:
    """The full instruction sent alongside the photo.

    Kept as its own function so a test can assert what does — and does not —
    end up in it.
    """
    return (style_prompt or DEFAULT_STYLE_PROMPT).strip()


def cache_key(photo: Path, prompt: str, model: str, version: str) -> str:
    """Identifies a rendering of one photo in one style by one model."""
    digest = hashlib.sha256()
    digest.update(Path(photo).read_bytes())
    digest.update(prompt.encode("utf-8"))
    digest.update(model.encode("utf-8"))
    digest.update(version.encode("utf-8"))
    return digest.hexdigest()[:16]


def illustrate(
    photo: Path,
    api_key: str,
    cache_dir: Path,
    model: str = DEFAULT_MODEL,
    style_prompt: str | None = None,
    version: str = "1",
    timeout: int = 90,
) -> Image.Image:
    """Return the illustrated version of `photo`, from cache when possible.

    Raises IllustrationError if the model cannot be reached or answers with
    something that is not an image.
    """
    prompt = build_prompt(style_prompt)
    key = cache_key(photo, prompt, model, version)
    cached = Path(cache_dir) / f"{key}.png"

    if cached.exists():
        try:
            with Image.open(cached) as image:
                log.info("Illustration for %s served from cache", photo.name)
                return image.copy()
        except OSError:
            log.warning("Cached illustration %s is unreadable; regenerating", cached)

    image = _request(photo, prompt, api_key, model, timeout)

    cached.parent.mkdir(parents=True, exist_ok=True)
    try:
        image.save(cached, format="PNG")
    except OSError as exc:
        # A cache that cannot be written costs money, not correctness.
        log.warning("Could not cache the illustration: %s", exc)

    return image


SUBJECT_PROMPT = (
    "Look at this photograph. Which half of the frame do the main subjects — "
    "people, animals, or the object the picture is about — mostly occupy? "
    "Answer with exactly one word: left, right, or centre. Nothing else."
)


def subject_side(
    photo: Path,
    api_key: str,
    cache_dir: Path,
    model: str = "gemini-flash-lite-latest",
    timeout: int = 30,
) -> str | None:
    """Which half of the photograph its subjects occupy, per the model.

    Returns "left", "right", or None — including for "centre", which is not an
    answer the layout can act on. Cached beside the illustration: this is asked
    once per photograph, not once per render.

    Never raises. A missing opinion is not a failure; the ink count decides.

    The default is a `-latest` alias on purpose. A pinned version was the first
    thing to break here — `gemini-2.5-flash` answers "no longer available to
    new users" to a key issued this week — and for a one-word classification
    the alias's drift matters far less than being locked out.
    """
    marker = Path(cache_dir) / f"{_photo_digest(photo)}.side"
    if marker.exists():
        cached = marker.read_text(encoding="utf-8").strip()
        return cached or None

    try:
        answer = _ask(photo, SUBJECT_PROMPT, api_key, model, timeout).strip().lower()
    except Exception as exc:
        log.info("No subject reading for %s: %s", photo.name, exc)
        return None

    side = next((word for word in ("left", "right") if word in answer), None)
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        marker.write_text(side or "", encoding="utf-8")
    except OSError:
        pass
    log.info("Subject of %s reads as %s", photo.name, side or "centre or unclear")
    return side


def _photo_digest(photo: Path) -> str:
    return hashlib.sha256(Path(photo).read_bytes()).hexdigest()[:16]


def _ask(photo: Path, prompt: str, api_key: str, model: str, timeout: int) -> str:
    """One question about a picture, answered in text."""
    body = _post(photo, prompt, api_key, model, timeout)
    for candidate in body.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            if part.get("text"):
                return part["text"]
    raise IllustrationError("the model answered with no text")


def _post(photo: Path, prompt: str, api_key: str, model: str, timeout: int) -> dict:
    mime = mimetypes.guess_type(str(photo))[0] or "image/jpeg"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime,
                            "data": base64.b64encode(Path(photo).read_bytes()).decode("ascii"),
                        }
                    },
                ]
            }
        ]
    }
    try:
        response = requests.post(
            f"{API_ROOT}/{model}:generateContent",
            params={"key": api_key},
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise IllustrationError(f"the model could not be reached: {exc}") from exc
    except ValueError as exc:
        raise IllustrationError(f"the model returned unreadable JSON: {exc}") from exc


def _request(photo: Path, prompt: str, api_key: str, model: str, timeout: int) -> Image.Image:
    body = _post(photo, prompt, api_key, model, timeout)
    data = _first_image(body)
    if data is None:
        raise IllustrationError("the response carried no image")

    try:
        with Image.open(io.BytesIO(base64.b64decode(data))) as image:
            return image.convert("L")
    except (OSError, ValueError) as exc:
        raise IllustrationError(f"the returned bytes are not an image: {exc}") from exc


def _first_image(body: dict) -> str | None:
    """Pull the first inline image out of a generateContent response."""
    for candidate in body.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return inline["data"]
    return None
