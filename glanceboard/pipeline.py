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

"""Sources → Board → PNG.

Every source failure degrades to a flag on the Board rather than an exception:
a device that wakes for four seconds and goes back to sleep must never find a
500 where the day's board should be. The previous good PNG also stays on disk
until a new one has been written in full.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

from . import __version__
from .config import Settings
from .models import Board
from .render import render_board

log = logging.getLogger(__name__)

#: A source that fails once gets a second chance. Open-Meteo answered 503 on an
#: ordinary afternoon and the board went without weather until the next slot,
#: six hours later — an outage of seconds costing a whole afternoon.
SOURCE_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 2

#: Parser errors quote the input they choked on. A feed that answers with a
#: sign-in page would otherwise put a whole HTML document — and whatever it
#: happens to contain — into the log.
MAX_LOGGED_ERROR = 200


def _brief(exc: Exception) -> str:
    text = " ".join(str(exc).split())
    return text if len(text) <= MAX_LOGGED_ERROR else text[:MAX_LOGGED_ERROR] + " […]"


def _with_retries(what: str, call):
    """Call `call`, retrying a couple of times before giving up.

    Returns (result, ok). Never raises: a source that stays down is a flag on
    the board, not an exception.
    """
    for attempt in range(1, SOURCE_ATTEMPTS + 1):
        try:
            return call(), True
        except Exception as exc:
            if attempt == SOURCE_ATTEMPTS:
                log.warning("%s unavailable after %d attempts: %s",
                            what, SOURCE_ATTEMPTS, _brief(exc))
                return None, False
            log.info("%s failed (attempt %d/%d): %s — retrying",
                     what, attempt, SOURCE_ATTEMPTS, _brief(exc))
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    return None, False


def build_board(
    settings: Settings,
    day: date | None = None,
    ical_bytes: bytes | None = None,
    weather_payload: dict | None = None,
) -> Board:
    """Collect the day's data. Never raises for a source being down.

    `ical_bytes` and `weather_payload` bypass the network — that is how the CLI
    iterates on layout against fixtures without touching the live feed.
    """
    from . import calendar_feed, weather as weather_module

    now = datetime.now(settings.tzinfo)
    day = day or now.date()

    events: tuple = ()
    calendar_ok = True
    if ical_bytes is not None:
        try:
            events = calendar_feed.parse_ical(ical_bytes, day, settings.tzinfo)
        except Exception as exc:  # malformed feed
            log.warning("Could not parse the supplied iCal data: %s", _brief(exc))
            calendar_ok = False
    elif settings.ical_url:
        fetched, calendar_ok = _with_retries(
            "Calendar",
            lambda: calendar_feed.events_for_day(
                settings.ical_url, day, settings.tzinfo, timeout=settings.request_timeout
            ),
        )
        events = fetched or ()
    else:
        log.warning("No GB_ICAL_URL configured; rendering an empty agenda")

    weather = None
    weather_ok = True
    if weather_payload is not None:
        weather = weather_module.parse_weather(weather_payload, settings.temp_unit)
        weather_ok = weather is not None
    elif settings.latitude is not None and settings.longitude is not None:
        weather, weather_ok = _with_retries(
            "Weather",
            lambda: weather_module.weather_for_day(
                settings.latitude,
                settings.longitude,
                day,
                settings.timezone,
                temp_unit=settings.temp_unit,
                timeout=settings.request_timeout,
            ),
        )
        weather_ok = weather_ok and weather is not None
    else:
        weather_ok = False

    return Board(
        day=day,
        events=events,
        weather=weather,
        generated_at=now,
        calendar_ok=calendar_ok,
        weather_ok=weather_ok,
    )


def illustration_for(settings: Settings, day: date):
    """The day's illustration, and the key identifying it.

    Returns (image, key), or (None, None) when illustration is switched off,
    unconfigured, out of photos, or the model would not answer. None of those
    is an error here: the board renders without a picture, exactly as it did
    before there was one.
    """
    if not settings.illustration_ready:
        return None, None

    from . import illustration as illustration_module
    from . import photos

    try:
        photo = photos.photo_for_day(settings.photo_dir, day, settings.photo_state_path)
    except photos.NoPhotosError as exc:
        log.info("No illustration: %s", _brief(exc))
        return None, None

    key = illustration_module.cache_key(
        photo,
        illustration_module.build_prompt(settings.style_prompt),
        settings.illustration_model,
        __version__,
    )

    image, ok = _with_retries(
        "Illustration",
        lambda: illustration_module.illustrate(
            photo,
            api_key=settings.gemini_api_key,
            cache_dir=settings.illustration_cache,
            model=settings.illustration_model,
            style_prompt=settings.style_prompt,
            version=__version__,
        ),
    )
    if not ok:
        return None, None
    return image, key


def render_to_file(
    board: Board,
    settings: Settings,
    path: Path | None = None,
    debug_regions: bool = False,
    rotate: int | None = None,
    illustration=None,
) -> Path:
    """Render and write the PNG atomically, so a reader never sees half a file."""
    image = render_board(
        board,
        width=settings.width,
        height=settings.height,
        font_dir=settings.font_dir,
        max_events=settings.max_events,
        art_fraction=settings.art_fraction,
        art_wash=settings.art_wash,
        illustration=illustration,
        debug_regions=debug_regions,
    )
    turns = settings.rotate if rotate is None else rotate
    if turns:
        # Composed in landscape, delivered in the panel's own orientation.
        image = image.rotate(turns, expand=True)
    target = Path(path) if path else settings.image_path
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, lambda handle: image.save(handle, format="PNG", optimize=True))
    return target


def generate(settings: Settings, day: date | None = None, force: bool = False) -> dict:
    """Build, render and record state. Returns the new state dictionary."""
    board = build_board(settings, day=day)
    illustration, illustration_key = illustration_for(settings, board.day)

    # The picture is part of what the device is looking at, so it belongs in
    # the hash. Without it, an illustration that failed at five and arrived at
    # noon would never reach a device that had already drawn the day.
    content_hash = board.content_hash()
    if illustration_key:
        content_hash = hashlib.sha256(
            f"{content_hash}:{illustration_key}".encode("utf-8")
        ).hexdigest()[:16]
    previous = load_state(settings)

    unchanged = (
        not force
        and previous.get("hash") == content_hash
        and settings.image_path.exists()
    )
    if unchanged:
        log.info("Board unchanged (hash=%s); keeping the existing PNG", content_hash)
        state = dict(previous)
        state["checked_at"] = board.generated_at.isoformat()
        _write_state(settings, state)
        return state

    render_to_file(board, settings, illustration=illustration)
    state = {
        "hash": content_hash,
        "day": board.day.isoformat(),
        "generated_at": board.generated_at.isoformat(),
        "checked_at": board.generated_at.isoformat(),
        "events": len(board.events),
        "calendar_ok": board.calendar_ok,
        "weather_ok": board.weather_ok,
        "illustration": bool(illustration_key),
        "width": settings.width,
        "height": settings.height,
    }
    _write_state(settings, state)
    log.info("Rendered board for %s (hash=%s, %d events)",
             board.day, content_hash, len(board.events))
    return state


def load_state(settings: Settings) -> dict:
    try:
        return json.loads(settings.state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(settings: Settings, state: dict) -> None:
    settings.state_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(
        settings.state_path,
        lambda handle: handle.write(json.dumps(state, indent=2).encode("utf-8")),
    )


def _atomic_write(target: Path, write) -> None:
    handle = tempfile.NamedTemporaryFile(dir=target.parent, delete=False, suffix=".tmp")
    try:
        with handle:
            write(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, target)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise
