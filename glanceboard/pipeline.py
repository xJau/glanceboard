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

import json
import logging
import os
import tempfile
from datetime import date, datetime
from pathlib import Path

from .config import Settings
from .models import Board
from .render import render_board

log = logging.getLogger(__name__)

#: Parser errors quote the input they choked on. A feed that answers with a
#: sign-in page would otherwise put a whole HTML document — and whatever it
#: happens to contain — into the log.
MAX_LOGGED_ERROR = 200


def _brief(exc: Exception) -> str:
    text = " ".join(str(exc).split())
    return text if len(text) <= MAX_LOGGED_ERROR else text[:MAX_LOGGED_ERROR] + " […]"


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
        try:
            events = calendar_feed.events_for_day(
                settings.ical_url, day, settings.tzinfo, timeout=settings.request_timeout
            )
        except Exception as exc:
            log.warning("Calendar unavailable: %s", _brief(exc))
            calendar_ok = False
    else:
        log.warning("No GB_ICAL_URL configured; rendering an empty agenda")

    weather = None
    weather_ok = True
    if weather_payload is not None:
        weather = weather_module.parse_weather(weather_payload, settings.temp_unit)
        weather_ok = weather is not None
    elif settings.latitude is not None and settings.longitude is not None:
        try:
            weather = weather_module.weather_for_day(
                settings.latitude,
                settings.longitude,
                day,
                settings.timezone,
                temp_unit=settings.temp_unit,
                timeout=settings.request_timeout,
            )
            weather_ok = weather is not None
        except Exception as exc:
            log.warning("Weather unavailable: %s", _brief(exc))
            weather_ok = False
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


def render_to_file(
    board: Board,
    settings: Settings,
    path: Path | None = None,
    debug_regions: bool = False,
    rotate: int | None = None,
) -> Path:
    """Render and write the PNG atomically, so a reader never sees half a file."""
    image = render_board(
        board,
        width=settings.width,
        height=settings.height,
        font_dir=settings.font_dir,
        max_events=settings.max_events,
        art_fraction=settings.art_fraction,
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
    content_hash = board.content_hash()
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

    render_to_file(board, settings)
    state = {
        "hash": content_hash,
        "day": board.day.isoformat(),
        "generated_at": board.generated_at.isoformat(),
        "checked_at": board.generated_at.isoformat(),
        "events": len(board.events),
        "calendar_ok": board.calendar_ok,
        "weather_ok": board.weather_ok,
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
