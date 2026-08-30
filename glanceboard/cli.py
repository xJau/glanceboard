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

"""Command line entry point.

`render` exists so the layout can be iterated on without starting the server or
touching the live calendar: point it at a fixture, look at the PNG, change a
number, run it again.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import platform
import secrets
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from .config import REPO_ROOT, ConfigError, Settings
from .pipeline import build_board, render_to_file

SAMPLE_DIR = REPO_ROOT / "assets" / "sample"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="glanceboard", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    render = sub.add_parser("render", help="render a PNG and exit")
    render.add_argument("--out", type=Path, help="output path (default: $GB_OUTPUT_DIR/board.png)")
    render.add_argument("--date", help="day to render, YYYY-MM-DD (default: today)")
    render.add_argument("--size", help="canvas size, e.g. 1072x1448 (default: from env)")
    render.add_argument("--ics", type=Path, help="read a local .ics instead of the live feed")
    render.add_argument("--weather-json", type=Path,
                        help="read a saved Open-Meteo response instead of calling the API")
    render.add_argument("--sample", action="store_true",
                        help="use the bundled sample calendar and weather (no network, no config)")
    render.add_argument("--debug-regions", action="store_true",
                        help="outline the layout regions")
    render.add_argument("--open", dest="open_after", action="store_true",
                        help="open the PNG in the system viewer when done")

    serve = sub.add_parser("serve", help="run the HTTP server")
    serve.add_argument("--reload", action="store_true", help="uvicorn autoreload (development)")

    sub.add_parser("token", help="print a fresh GB_DISPLAY_TOKEN value")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "token":
        print(secrets.token_urlsafe(32))
        return 0

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.command == "serve":
        return _serve(settings, reload=args.reload)
    return _render(settings, args)


def _render(settings: Settings, args) -> int:
    if args.size:
        try:
            width, height = (int(part) for part in args.size.lower().split("x", 1))
        except ValueError:
            print(f"--size must look like 1072x1448, got {args.size!r}", file=sys.stderr)
            return 2
        settings = dataclasses.replace(settings, width=width, height=height)

    day = None
    if args.date:
        try:
            day = date.fromisoformat(args.date)
        except ValueError:
            print(f"--date must be YYYY-MM-DD, got {args.date!r}", file=sys.stderr)
            return 2

    ics_path = args.ics
    weather_path = args.weather_json
    if args.sample:
        ics_path = ics_path or SAMPLE_DIR / "day.ics"
        weather_path = weather_path or SAMPLE_DIR / "weather.json"
        # The sample calendar is written around a fixed date so it always has
        # something to show.
        day = day or _sample_day(ics_path)

    ical_bytes = ics_path.read_bytes() if ics_path else None
    weather_payload = json.loads(weather_path.read_text(encoding="utf-8")) if weather_path else None

    board = build_board(
        settings, day=day, ical_bytes=ical_bytes, weather_payload=weather_payload
    )
    target = render_to_file(
        board, settings, path=args.out, debug_regions=args.debug_regions
    )

    print(
        f"{target}  {settings.width}x{settings.height}  "
        f"{len(board.events)} eventi  hash={board.content_hash()}"
    )
    if not board.calendar_ok:
        print("  ⚠ calendario non raggiungibile", file=sys.stderr)
    if not board.weather_ok:
        print("  ⚠ meteo non disponibile", file=sys.stderr)

    if args.open_after:
        _open(target)
    return 0


def _sample_day(ics_path: Path) -> date:
    """The date the bundled sample is written for, taken from its first DTSTART."""
    for line in ics_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("DTSTART"):
            value = line.split(":", 1)[1].strip()
            try:
                return datetime.strptime(value[:8], "%Y%m%d").date()
            except ValueError:
                continue
    return date.today()


def _open(path: Path) -> None:
    opener = {"Darwin": "open", "Linux": "xdg-open"}.get(platform.system())
    if not opener:
        return
    try:
        subprocess.run([opener, str(path)], check=False)
    except OSError:
        pass


def _serve(settings: Settings, reload: bool = False) -> int:
    import uvicorn

    try:
        settings.require_serving_credentials()
    except ConfigError as exc:
        print(f"Refusing to start: {exc}", file=sys.stderr)
        return 2

    uvicorn.run(
        "glanceboard.server:create_app_from_env",
        factory=True,
        host=settings.bind_host,
        port=settings.port,
        reload=reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
