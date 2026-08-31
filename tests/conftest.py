"""Shared fixtures. Nothing here touches the network."""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from glanceboard.config import REPO_ROOT, Settings

SAMPLE_DIR = REPO_ROOT / "assets" / "sample"
SAMPLE_DAY = date(2026, 9, 1)
ROME = ZoneInfo("Europe/Rome")


@pytest.fixture(autouse=True)
def no_retry_backoff(monkeypatch):
    """Sources are retried in production; tests must not sit through the waits."""
    from glanceboard import pipeline

    monkeypatch.setattr(pipeline, "RETRY_BACKOFF_SECONDS", 0)


@pytest.fixture
def sample_ics() -> bytes:
    return (SAMPLE_DIR / "day.ics").read_bytes()


@pytest.fixture
def sample_weather() -> dict:
    return json.loads((SAMPLE_DIR / "weather.json").read_text(encoding="utf-8"))


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """A Settings pointing at a temporary output directory."""
    for name in list(os.environ):
        if name.startswith("GB_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GB_OUTPUT_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GB_TIMEZONE", "Europe/Rome")
    monkeypatch.setenv("GB_DISPLAY_TOKEN", "test-token-that-is-long-enough-1234")
    return Settings.from_env()


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 9, 1, 5, 0, tzinfo=ROME)
