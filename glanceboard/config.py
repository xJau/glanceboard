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

"""Configuration, read from the environment only.

Every path is configurable and nothing is resolved relative to the current
working directory, so the same code runs from a laptop checkout and from
/app in a container. Secrets are never written to disk by this process and
never served over HTTP.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_WIDTH = 1072   # Kindle Paperwhite 4 (10th gen, 6"). PW5/PW6: 1236x1648.
DEFAULT_HEIGHT = 1448
DEFAULT_TIMEZONE = "Europe/Rome"
DEFAULT_SLOTS = (5, 12, 18)


class ConfigError(RuntimeError):
    """Raised when the environment cannot produce a usable configuration."""


def _env(name: str, default: str | None = None) -> str | None:
    """Read NAME, or NAME_FILE pointing at a file (docker/podman secrets)."""
    file_var = os.environ.get(f"{name}_FILE")
    if file_var:
        try:
            return Path(file_var).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigError(f"{name}_FILE is set but unreadable: {exc}") from exc
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _env_float(name: str) -> float | None:
    raw = _env(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _env_fraction(name: str, default: float) -> float:
    """A 0..0.6 share of the canvas height, used for the reserved art band."""
    raw = _env(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number between 0 and 0.6, got {raw!r}") from exc
    if not 0.0 <= value <= 0.6:
        raise ConfigError(f"{name} must be between 0 and 0.6, got {value}")
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_slots(raw: str | None) -> tuple[int, ...]:
    if not raw:
        return DEFAULT_SLOTS
    slots = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            hour = int(chunk)
        except ValueError as exc:
            raise ConfigError(f"GB_SLOTS must be comma-separated hours, got {raw!r}") from exc
        if not 0 <= hour <= 23:
            raise ConfigError(f"GB_SLOTS hour out of range: {hour}")
        slots.append(hour)
    return tuple(sorted(set(slots)))


@dataclass(frozen=True)
class Settings:
    ical_url: str | None
    timezone: str
    latitude: float | None
    longitude: float | None
    temp_unit: str
    width: int
    height: int
    output_dir: Path
    font_dir: Path
    slots: tuple[int, ...]
    display_token: str | None
    bind_host: str
    port: int
    request_timeout: int
    max_events: int
    art_fraction: float
    allow_no_token: bool
    tzinfo: ZoneInfo = field(compare=False, repr=False, default=None)  # type: ignore[assignment]

    @property
    def image_path(self) -> Path:
        return self.output_dir / "board.png"

    @property
    def state_path(self) -> Path:
        return self.output_dir / "state.json"

    @classmethod
    def from_env(cls) -> "Settings":
        tz_name = _env("GB_TIMEZONE", DEFAULT_TIMEZONE)
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"Unknown GB_TIMEZONE: {tz_name!r}") from exc

        temp_unit = (_env("GB_TEMP_UNIT", "celsius") or "celsius").lower()
        if temp_unit not in {"celsius", "fahrenheit"}:
            raise ConfigError("GB_TEMP_UNIT must be 'celsius' or 'fahrenheit'")

        output_dir = Path(_env("GB_OUTPUT_DIR", str(REPO_ROOT / "data"))).expanduser()
        font_dir = Path(_env("GB_FONT_DIR", str(REPO_ROOT / "assets" / "fonts"))).expanduser()

        return cls(
            ical_url=_env("GB_ICAL_URL"),
            timezone=tz_name,
            latitude=_env_float("GB_LAT"),
            longitude=_env_float("GB_LON"),
            temp_unit=temp_unit,
            width=_env_int("GB_WIDTH", DEFAULT_WIDTH),
            height=_env_int("GB_HEIGHT", DEFAULT_HEIGHT),
            output_dir=output_dir,
            font_dir=font_dir,
            slots=_parse_slots(_env("GB_SLOTS")),
            display_token=_env("GB_DISPLAY_TOKEN"),
            bind_host=_env("GB_BIND_HOST", "127.0.0.1"),
            port=_env_int("GB_PORT", 8000),
            request_timeout=_env_int("GB_REQUEST_TIMEOUT", 20),
            max_events=_env_int("GB_MAX_EVENTS", 12),
            art_fraction=_env_fraction("GB_ART_FRACTION", 0.30),
            allow_no_token=_env_bool("GB_ALLOW_NO_TOKEN", False),
            tzinfo=tz,
        )

    def require_serving_credentials(self) -> None:
        """Fail closed: refuse to serve the display without a token.

        Cloudflare Access sits in front in production, but the server must not
        depend on it. If Access is misconfigured, bypassed, or the box is
        reached over the LAN, this token is what still says no.
        """
        if self.allow_no_token:
            return
        if not self.display_token or len(self.display_token) < 24:
            raise ConfigError(
                "GB_DISPLAY_TOKEN must be set to a random string of at least 24 "
                "characters before the server will serve the display. "
                "Generate one with: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\" "
                "— or set GB_ALLOW_NO_TOKEN=1 for local development only."
            )
