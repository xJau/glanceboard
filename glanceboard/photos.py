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

"""The photo library: which picture the day gets.

A local directory, whatever fills it. Keeping the library separate from its
source is what lets a fetcher fail without the board noticing: the pictures
already on disk are still there.

One photo per day, chosen once and remembered. The board regenerates at every
slot, and neither paying three times nor watching the picture change at lunch
is what anyone wants.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


class NoPhotosError(RuntimeError):
    """The library is empty, or is not there at all."""


def available(photo_dir: Path) -> list[Path]:
    """Every usable photo, in a stable order."""
    directory = Path(photo_dir)
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in SUFFIXES
    )


def photo_for_day(photo_dir: Path, day: date, state_path: Path) -> Path:
    """The photo for `day`, picked once and then remembered.

    Rotates through the library without repeating: the next photo is the one
    after yesterday's, so adding pictures does not reshuffle the queue and
    removing one does not skip a turn.
    """
    photos = available(photo_dir)
    if not photos:
        raise NoPhotosError(f"No usable photos in {photo_dir}")

    state = _load(state_path)
    chosen = state.get("photo")
    if state.get("day") == day.isoformat() and chosen:
        already = Path(photo_dir) / chosen
        if already.exists():
            return already

    names = [path.name for path in photos]
    if chosen in names:
        index = (names.index(chosen) + 1) % len(names)
    else:
        # Nothing remembered, or the remembered photo is gone: start from the
        # day itself, so two devices with the same library do not begin in
        # lockstep and a wiped state file does not always pick the same picture.
        index = day.toordinal() % len(names)

    picked = photos[index]
    _save(state_path, {"day": day.isoformat(), "photo": picked.name})
    log.info("Photo for %s: %s (%d in the library)", day, picked.name, len(photos))
    return picked


def _load(state_path: Path) -> dict:
    try:
        return json.loads(Path(state_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(state_path: Path, state: dict) -> None:
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError as exc:
        # Losing the rotation is a cosmetic problem: the day still gets a photo.
        log.warning("Could not record the chosen photo: %s", exc)
