"""The HTTP surface, including what it refuses.

TestClient is used without its context manager on purpose: entering it would run
the lifespan, which starts the scheduler and a generation thread. These tests
are about the request path.
"""
from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from glanceboard.config import ConfigError
from glanceboard.pipeline import build_board, render_to_file
from glanceboard.server import create_app

from .conftest import SAMPLE_DAY

TOKEN = "test-token-that-is-long-enough-1234"


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))


@pytest.fixture
def client_with_board(settings, sample_ics, sample_weather):
    board = build_board(settings, day=SAMPLE_DAY, ical_bytes=sample_ics,
                        weather_payload=sample_weather)
    render_to_file(board, settings)
    from glanceboard.pipeline import _write_state

    _write_state(settings, {"hash": board.content_hash(), "day": SAMPLE_DAY.isoformat(),
                            "generated_at": board.generated_at.isoformat()})
    return TestClient(create_app(settings)), board


# ─── Authentication ─────────────────────────────────────────────

def test_display_refuses_an_anonymous_request(client):
    assert client.get("/display").status_code == 401


def test_check_refuses_an_anonymous_request(client):
    assert client.get("/display/check").status_code == 401


def test_display_refuses_a_wrong_token(client):
    response = client.get("/display", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


def test_a_bearer_token_is_accepted(client_with_board):
    client, _ = client_with_board
    response = client.get("/display", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_the_query_parameter_fallback_is_accepted(client_with_board):
    """BusyBox wget on an old Kindle cannot always set a header."""
    client, _ = client_with_board
    assert client.get(f"/display?token={TOKEN}").status_code == 200


def test_healthz_needs_no_token(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_server_refuses_to_start_without_a_token(settings):
    naked = dataclasses.replace(settings, display_token=None)
    with pytest.raises(ConfigError):
        create_app(naked)


def test_a_short_token_is_rejected(settings):
    weak = dataclasses.replace(settings, display_token="short")
    with pytest.raises(ConfigError):
        create_app(weak)


def test_local_development_can_opt_out(settings):
    """GB_ALLOW_NO_TOKEN exists for a laptop, and must be explicit."""
    local = dataclasses.replace(settings, display_token=None, allow_no_token=True)
    client = TestClient(create_app(local))
    assert client.get("/display").status_code == 404  # reachable, just nothing rendered


# ─── Responses ──────────────────────────────────────────────────

def test_display_is_404_before_the_first_render(client):
    response = client.get("/display", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 404


def test_check_reports_the_current_hash(client_with_board):
    client, board = client_with_board
    payload = client.get("/display/check", headers={"Authorization": f"Bearer {TOKEN}"}).json()
    assert payload["hash"] == board.content_hash()
    assert payload["has_image"] is True


def test_an_unchanged_board_answers_304(client_with_board):
    """This is what lets the device skip a redraw and go back to sleep."""
    client, _ = client_with_board
    headers = {"Authorization": f"Bearer {TOKEN}"}
    first = client.get("/display", headers=headers)
    etag = first.headers["etag"]

    second = client.get("/display", headers={**headers, "If-None-Match": etag})
    assert second.status_code == 304


def test_there_is_no_configuration_endpoint(client):
    """The upstream project served its API key from GET /api/config."""
    for path in ("/api/config", "/config", "/api/status", "/openapi.json", "/docs"):
        assert client.get(path).status_code in (401, 404), path


def test_configuration_cannot_be_written_over_http(client):
    assert client.post("/api/config", json={"ical_url": "x"}).status_code in (404, 405)


# ─── Startup ────────────────────────────────────────────────────

def test_startup_regenerates_even_when_todays_board_exists(settings, monkeypatch):
    """A restart usually means the configuration changed; refetch and find out."""
    from glanceboard import server
    from glanceboard.pipeline import _write_state

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.image_path.write_bytes(b"not really a png")
    _write_state(settings, {"hash": "old", "day": "2026-08-30"})

    calls = []
    monkeypatch.setattr(server, "generate", lambda s: calls.append(s))

    server._generate_at_startup(settings)
    assert calls, "startup skipped the regeneration"


def test_a_failing_generation_does_not_take_the_scheduler_down(settings, monkeypatch):
    from glanceboard import server

    def explode(_settings):
        raise RuntimeError("calendar exploded")

    monkeypatch.setattr(server, "generate", explode)
    server._safe_generate(settings)  # must not raise


def test_a_token_in_the_query_string_is_redacted_from_the_access_log():
    """The device may have to send it there; the log must not keep it."""
    import logging

    from glanceboard.server import RedactQueryToken

    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s - %s %s", None, None)
    record.args = ("127.0.0.1:1", "GET", "/display?token=super-secret-value")
    RedactQueryToken().filter(record)
    assert "super-secret-value" not in str(record.args)
    assert "token=REDACTED" in str(record.args)


def test_redaction_leaves_ordinary_paths_alone():
    import logging

    from glanceboard.server import RedactQueryToken

    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s", None, None)
    record.args = ("127.0.0.1:1", "GET", "/display/check")
    RedactQueryToken().filter(record)
    assert record.args[2] == "/display/check"
