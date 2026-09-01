"""Reading a public Google Photos share page.

The page is not a documented interface, so these tests pin the two things that
matter: what is pulled out of a page shaped like the real one, and that a
failure at any point is survivable.
"""
from __future__ import annotations

import pytest
import requests

from glanceboard import album

# The shape the real page has: photo URLs scattered through an inline script,
# each repeated at several sizes, mixed in with avatars on the same host.
SHARE_PAGE = """
<!doctype html><html><head><title>Album</title></head><body>
<script>AF_initDataCallback({key:'ds:1', data:[[
["AF1QipMPHOTOONE","https://lh3.googleusercontent.com/pw/AP1Gcz-one=w2048-h1536",2048,1536],
["AF1QipMPHOTOTWO","https://lh3.googleusercontent.com/pw/AP1Gcz-two=w1024-h768",1024,768],
["avatar","https://lh3.googleusercontent.com/a/ACg8ocK-profile=s64-c",64,64],
["AF1QipMPHOTOONE","https://lh3.googleusercontent.com/pw/AP1Gcz-one=w400-h300",400,300]
]]});</script>
</body></html>
"""

JPEG = b"\xff\xd8\xff" + b"0" * 512


def test_only_album_photos_are_taken():
    urls = album.photo_urls(SHARE_PAGE)
    assert len(urls) == 2, "the profile picture came along"
    assert all("/pw/" in url for url in urls)


def test_each_photo_appears_once_at_the_size_we_asked_for():
    urls = album.photo_urls(SHARE_PAGE, size=1600)
    assert urls == [
        "https://lh3.googleusercontent.com/pw/AP1Gcz-one=w1600",
        "https://lh3.googleusercontent.com/pw/AP1Gcz-two=w1600",
    ]


def test_page_order_is_kept():
    first, second = album.photo_urls(SHARE_PAGE)
    assert first.endswith("one=w1600") and second.endswith("two=w1600")


def test_sync_downloads_what_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(requests, "get", _fake_get(SHARE_PAGE))
    assert album.sync("https://photos.app.goo.gl/x", tmp_path) == 2
    assert len(list(tmp_path.glob("*.jpg"))) == 2


def test_a_second_sync_downloads_nothing(tmp_path, monkeypatch):
    """Names derive from the photo's own URL, so the second pass recognises it."""
    monkeypatch.setattr(requests, "get", _fake_get(SHARE_PAGE))
    album.sync("https://photos.app.goo.gl/x", tmp_path)
    assert album.sync("https://photos.app.goo.gl/x", tmp_path) == 0


def test_the_limit_is_honoured(tmp_path, monkeypatch):
    monkeypatch.setattr(requests, "get", _fake_get(SHARE_PAGE))
    assert album.sync("https://photos.app.goo.gl/x", tmp_path, limit=1) == 1


def test_something_that_is_not_a_jpeg_is_discarded(tmp_path, monkeypatch):
    """An error page served where an image was expected must not enter the
    library, where it would later fail at the renderer instead."""
    monkeypatch.setattr(requests, "get", _fake_get(SHARE_PAGE, body=b"<html>oops</html>"))
    assert album.sync("https://photos.app.goo.gl/x", tmp_path) == 0
    assert list(tmp_path.glob("*.jpg")) == []
    assert list(tmp_path.glob("*.part")) == []


def test_one_bad_photo_does_not_stop_the_others(tmp_path, monkeypatch):
    calls = []

    def get(url, **kwargs):
        if url.startswith("https://photos"):
            return _Response(SHARE_PAGE)
        calls.append(url)
        if len(calls) == 1:
            raise requests.ConnectionError("reset")
        return _Response(body=JPEG)

    monkeypatch.setattr(requests, "get", get)
    assert album.sync("https://photos.app.goo.gl/x", tmp_path) == 1


def test_an_unreachable_album_raises(tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise requests.Timeout("slow")

    monkeypatch.setattr(requests, "get", explode)
    with pytest.raises(album.AlbumError):
        album.sync("https://photos.app.goo.gl/x", tmp_path)


def test_the_pipeline_survives_an_album_that_will_not_load(settings, monkeypatch):
    """The library is separate from its source for exactly this reason."""
    from glanceboard import pipeline

    monkeypatch.setenv("GB_PHOTO_ALBUM_URL", "https://photos.app.goo.gl/x")
    monkeypatch.setenv("GB_GEMINI_API_KEY", "k")
    settings = type(settings).from_env()

    def explode(*args, **kwargs):
        raise album.AlbumError("Google changed the page")

    monkeypatch.setattr(album, "sync", explode)
    # No photos either, so this returns nothing — but it must not raise.
    assert pipeline.illustration_for(
        settings, __import__("datetime").date(2026, 9, 1)) == (None, None, None)


class _Response:
    url = "https://photos.google.com/share/AF1Qip?key=x"

    def __init__(self, text: str = "", body: bytes = b""):
        self.text = text
        self._body = body

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=1):
        yield self._body


def _fake_get(page: str, body: bytes = JPEG):
    def get(url, **kwargs):
        if url.startswith("https://photos"):
            return _Response(page)
        return _Response(body=body)

    return get


def test_a_short_link_says_what_to_use_instead(tmp_path, monkeypatch):
    """photos.app.goo.gl serves a page only a browser can follow, and its
    emptiness looks exactly like a private album unless we say otherwise."""
    class ShortLink(_Response):
        url = "https://photos.app.goo.gl/abc123"

    monkeypatch.setattr(requests, "get", lambda *a, **k: ShortLink("<html>shell</html>"))
    with pytest.raises(album.AlbumError) as error:
        album.sync("https://photos.app.goo.gl/abc123", tmp_path)

    message = str(error.value)
    assert "photos.google.com/share" in message
    assert "browser" in message


def test_a_long_link_with_no_photos_blames_the_sharing_instead(tmp_path, monkeypatch):
    class LongLink(_Response):
        url = "https://photos.google.com/share/AF1Qip?key=x"

    monkeypatch.setattr(requests, "get", lambda *a, **k: LongLink("<html>nothing</html>"))
    with pytest.raises(album.AlbumError) as error:
        album.sync("https://photos.google.com/share/AF1Qip?key=x", tmp_path)
    assert "anyone with the link" in str(error.value)


def test_the_request_does_not_pretend_to_be_a_browser():
    """Claiming to be Chrome gets a JavaScript shell with no photos in it.
    An honest user agent gets the server-rendered page — this cost an hour to
    find, and a rewritten header would cost it again."""
    agent = album.REQUEST_HEADERS["User-Agent"]
    assert "glanceboard" in agent
    for browser in ("Chrome", "Safari", "AppleWebKit", "Mozilla"):
        assert browser not in agent
