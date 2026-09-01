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

#: Written for a 16-grey e-ink panel seen from across a room: shapes read at a
#: distance, fine gradients do not survive quantization, and the register has to
#: sit beside a rounded typeface and cream cards without fighting them.
DEFAULT_STYLE_PROMPT = (
    "Redraw this photograph as a warm children's storybook illustration. "
    "Soft ink linework with gentle, flat shading; keep the composition, the "
    "subjects and their arrangement recognisable. Monochrome — black ink on a "
    "cream page, no colour. Strong tonal contrast and clean silhouettes, no "
    "fine texture or subtle gradients, because this is displayed on a low "
    "contrast greyscale e-ink screen. No text, no lettering, no borders, "
    "no frame."
)


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


def _request(photo: Path, prompt: str, api_key: str, model: str, timeout: int) -> Image.Image:
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
        body = response.json()
    except requests.RequestException as exc:
        raise IllustrationError(f"the image model could not be reached: {exc}") from exc
    except ValueError as exc:
        raise IllustrationError(f"the image model returned unreadable JSON: {exc}") from exc

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
