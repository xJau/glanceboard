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

"""HTTP surface: three endpoints, all read-only.

There is no configuration endpoint and no dashboard. Settings arrive through the
environment and stay there. The upstream project served its whole config —
API key included — from an unauthenticated GET; nothing here can grow back into
that, because nothing here can read a secret out to a client.

Cloudflare Access sits in front of this in production. The token check below is
deliberately independent of it: if Access is misconfigured, disabled, or the
host is reached directly over the LAN, this is what still refuses.
"""
from __future__ import annotations

import logging
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from .config import Settings
from .pipeline import generate, load_state
from .schedule import next_slot

log = logging.getLogger(__name__)


def _client_token(request: Request) -> str | None:
    """Read the token from a header, or from the query string as a fallback.

    The header is the right place. The query parameter exists because BusyBox
    wget on an old Kindle cannot always add one, and a token in a URL to a host
    we control is a better outcome than an unauthenticated endpoint.
    """
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    header_token = request.headers.get("x-glanceboard-token")
    if header_token:
        return header_token.strip()
    return request.query_params.get("token")


def create_app(settings: Settings) -> FastAPI:
    settings.require_serving_credentials()
    scheduler_holder: dict[str, object] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        _schedule(settings, scheduler_holder)
        yield
        scheduler = scheduler_holder.pop("scheduler", None)
        if scheduler is not None:
            scheduler.shutdown(wait=False)

    app = FastAPI(
        title="Glanceboard Kindle",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    def require_token(request: Request) -> None:
        if settings.allow_no_token and not settings.display_token:
            return
        supplied = _client_token(request)
        expected = settings.display_token or ""
        if not supplied or not secrets.compare_digest(supplied, expected):
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid display token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        """Unauthenticated liveness for the container healthcheck.

        Says nothing about the calendar, the weather or the token — only that
        the process is up.
        """
        return JSONResponse({"status": "ok"})

    @app.get("/display/check", dependencies=[Depends(require_token)])
    def display_check() -> JSONResponse:
        """Cheap poll: has the board changed, and when should the device wake?

        `now_epoch` and `next_refresh_epoch` are returned as a pair so the device
        can sleep for their difference without trusting its own clock.
        """
        state = load_state(settings)
        now = datetime.now(settings.tzinfo)
        return JSONResponse(
            {
                "hash": state.get("hash"),
                "day": state.get("day"),
                "generated_at": state.get("generated_at"),
                "has_image": settings.image_path.exists(),
                "width": state.get("width", settings.width),
                "height": state.get("height", settings.height),
                "now_epoch": int(now.timestamp()),
                "next_refresh_epoch": int(next_slot(settings, now).timestamp()),
            }
        )

    @app.get("/display", dependencies=[Depends(require_token)])
    def display(request: Request) -> Response:
        """The PNG the Kindle draws."""
        if not settings.image_path.exists():
            raise HTTPException(status_code=404, detail="No board has been rendered yet")

        state = load_state(settings)
        etag = f'"{state.get("hash", "unknown")}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})

        return FileResponse(
            settings.image_path,
            media_type="image/png",
            headers={"ETag": etag, "Cache-Control": "no-cache"},
        )

    return app


def _schedule(settings: Settings, holder: dict) -> None:
    """Regenerate at each configured slot, and once at startup if needed."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler(timezone=settings.tzinfo)
    for hour in settings.slots:
        scheduler.add_job(
            _safe_generate,
            CronTrigger(hour=hour, minute=0, timezone=settings.tzinfo),
            args=[settings],
            id=f"slot-{hour:02d}",
            misfire_grace_time=1800,
            coalesce=True,
        )
    scheduler.start()
    holder["scheduler"] = scheduler
    log.info("Scheduled slots at %s (%s)",
             ", ".join(f"{h:02d}:00" for h in settings.slots), settings.timezone)

    # A container that has just started, or one that was down over a slot,
    # should not wait until tomorrow morning to have something to show.
    threading.Thread(target=_generate_if_stale, args=(settings,), daemon=True).start()


def _generate_if_stale(settings: Settings) -> None:
    state = load_state(settings)
    today = datetime.now(settings.tzinfo).date().isoformat()
    if settings.image_path.exists() and state.get("day") == today:
        return
    _safe_generate(settings)


def _safe_generate(settings: Settings) -> None:
    """Scheduler entry point: a failed run must not kill the scheduler."""
    try:
        generate(settings)
    except Exception:
        log.exception("Board generation failed; keeping the previous PNG")


def create_app_from_env() -> FastAPI:
    """ASGI factory. Used as `glanceboard.server:create_app_from_env` with
    uvicorn's --factory, so importing this module never reads the environment
    or refuses to load for want of a token."""
    return create_app(Settings.from_env())
