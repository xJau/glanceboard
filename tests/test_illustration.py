"""The image model: what is sent, what comes back, and what is never sent."""
from __future__ import annotations

import base64
import io

import pytest
import requests
from PIL import Image

from glanceboard import illustration


@pytest.fixture
def photo(tmp_path):
    path = tmp_path / "casa.jpg"
    Image.new("RGB", (64, 48), "white").save(path)
    return path


def _reply_with_image(size=(32, 24)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "gray").save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [
                {"inlineData": {"mimeType": "image/png", "data": encoded}}
            ]}}]}

    return Response


def test_the_request_carries_the_style_and_the_photo_and_nothing_else(photo, tmp_path, monkeypatch):
    """A model must never be in a position to restate an appointment."""
    captured = {}

    def fake_post(url, params=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _reply_with_image()()

    monkeypatch.setattr(requests, "post", fake_post)
    illustration.illustrate(photo, api_key="k", cache_dir=tmp_path / "cache")

    parts = captured["json"]["contents"][0]["parts"]
    assert len(parts) == 2, "only the instruction and the photograph"
    assert "text" in parts[0] and "inline_data" in parts[1]

    sent = parts[0]["text"]
    for leak in ("09:00", "Consulenza", "appuntamento", "calendario", "Rossi"):
        assert leak.lower() not in sent.lower()


def test_the_style_prompt_can_be_replaced(photo, tmp_path, monkeypatch):
    captured = {}

    def fake_post(url, params=None, json=None, timeout=None):
        captured["json"] = json
        return _reply_with_image()()

    monkeypatch.setattr(requests, "post", fake_post)
    illustration.illustrate(photo, api_key="k", cache_dir=tmp_path / "cache",
                            style_prompt="Solo linee, niente ombre.")
    assert captured["json"]["contents"][0]["parts"][0]["text"] == "Solo linee, niente ombre."


def test_the_result_is_grayscale(photo, tmp_path, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: _reply_with_image()())
    image = illustration.illustrate(photo, api_key="k", cache_dir=tmp_path / "cache")
    assert image.mode == "L"


def test_the_second_call_comes_from_the_cache(photo, tmp_path, monkeypatch):
    """Three regenerations a day must not be three invoices."""
    calls = []

    def counting_post(*args, **kwargs):
        calls.append(1)
        return _reply_with_image()()

    monkeypatch.setattr(requests, "post", counting_post)
    cache = tmp_path / "cache"

    illustration.illustrate(photo, api_key="k", cache_dir=cache)
    illustration.illustrate(photo, api_key="k", cache_dir=cache)
    assert len(calls) == 1


def test_a_different_style_is_a_different_cache_entry(photo, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: (calls.append(1), _reply_with_image()())[1])
    cache = tmp_path / "cache"

    illustration.illustrate(photo, api_key="k", cache_dir=cache, style_prompt="uno")
    illustration.illustrate(photo, api_key="k", cache_dir=cache, style_prompt="due")
    assert len(calls) == 2


def test_an_unreachable_model_raises(photo, tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(requests, "post", explode)
    with pytest.raises(illustration.IllustrationError):
        illustration.illustrate(photo, api_key="k", cache_dir=tmp_path / "cache")


def test_a_response_without_an_image_raises(photo, tmp_path, monkeypatch):
    class TextOnly:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "I cannot do that"}]}}]}

    monkeypatch.setattr(requests, "post", lambda *a, **k: TextOnly())
    with pytest.raises(illustration.IllustrationError):
        illustration.illustrate(photo, api_key="k", cache_dir=tmp_path / "cache")


def test_bytes_that_are_not_an_image_raise(photo, tmp_path, monkeypatch):
    class Garbage:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [
                {"inlineData": {"data": base64.b64encode(b"not an image").decode()}}
            ]}}]}

    monkeypatch.setattr(requests, "post", lambda *a, **k: Garbage())
    with pytest.raises(illustration.IllustrationError):
        illustration.illustrate(photo, api_key="k", cache_dir=tmp_path / "cache")


def test_the_api_key_never_appears_in_the_body(photo, tmp_path, monkeypatch):
    """It belongs in the query string, where the transport keeps it out of logs
    we control — never in a payload that might be echoed back in an error."""
    captured = {}

    def fake_post(url, params=None, json=None, timeout=None):
        captured["params"] = params
        captured["json"] = json
        return _reply_with_image()()

    monkeypatch.setattr(requests, "post", fake_post)
    illustration.illustrate(photo, api_key="segretissima", cache_dir=tmp_path / "cache")

    assert captured["params"]["key"] == "segretissima"
    assert "segretissima" not in str(captured["json"])


def test_a_release_does_not_throw_away_the_cache(photo, tmp_path):
    """Keying on the package version meant every release re-bought every
    illustration. What the picture depends on is the photo, the prompt and the
    model — nothing else."""
    prompt = illustration.build_prompt("uno stile")
    first = illustration.cache_key(photo, prompt, "m")
    assert first == illustration.cache_key(photo, prompt, "m")
    assert first != illustration.cache_key(photo, illustration.build_prompt("altro"), "m")
    assert first != illustration.cache_key(photo, prompt, "modello-diverso")


def test_the_same_photo_in_two_styles_is_two_entries(photo, tmp_path, monkeypatch):
    """Which is what lets a pairing already drawn simply be found again."""
    from glanceboard import styles

    calls = []
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: (calls.append(1), _reply_with_image()())[1])
    cache = tmp_path / "cache"

    illustration.illustrate(photo, api_key="k", cache_dir=cache,
                            style_prompt=styles.prompt_for("fumetto"))
    illustration.illustrate(photo, api_key="k", cache_dir=cache,
                            style_prompt=styles.prompt_for("western"))
    assert len(calls) == 2

    # Coming round again costs nothing.
    illustration.illustrate(photo, api_key="k", cache_dir=cache,
                            style_prompt=styles.prompt_for("fumetto"))
    assert len(calls) == 2
