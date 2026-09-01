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

"""Filling the photo library from a public Google Photos album.

This is the fragile part of the project, deliberately kept at arm's length.

The official route is closed: Google removed the read-only Library API scopes in
March 2025, shared-album endpoints answer 403, and the Picker API that replaced
them needs a human to choose photos every time — no use to a job that runs at
five in the morning. What is left is the public share page, which carries the
image URLs in an inline script. That is not a documented interface and Google
can change it whenever they like.

So the library and its source are separate. This module only ever adds files to
a directory; everything downstream reads that directory and knows nothing about
where the pictures came from. When this breaks — and one day it will — the board
keeps showing the photographs already on disk, and the log says what happened.
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

import requests

log = logging.getLogger(__name__)

#: Google serves photo bytes from this host; the share page mentions each one.
_PHOTO_URL = re.compile(r'https://lh3\.googleusercontent\.com/[A-Za-z0-9_\-/.]+')

#: Avatars and UI chrome live on the same host. Album photos carry the `/pw/`
#: prefix, which is a narrow enough filter to keep profile pictures out.
_LOOKS_LIKE_A_PHOTO = re.compile(r'/pw/')

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}


class AlbumError(RuntimeError):
    """The album could not be read."""


def photo_urls(html: str, size: int = 1600) -> list[str]:
    """Every photo in a share page, largest-size URLs, in page order.

    Pure: the network is somebody else's problem, so this can be tested against
    a saved page.
    """
    seen: list[str] = []
    for match in _PHOTO_URL.findall(html):
        base = match.split("=")[0]
        if not _LOOKS_LIKE_A_PHOTO.search(base):
            continue
        url = f"{base}=w{size}"
        if url not in seen:
            seen.append(url)
    return seen


def sync(
    album_url: str,
    photo_dir: Path,
    limit: int = 60,
    size: int = 1600,
    timeout: int = 30,
) -> int:
    """Download any photo from the album that is not already on disk.

    Returns how many arrived. Raises AlbumError if the album cannot be read at
    all — the caller decides whether that matters, and here it never does.
    """
    try:
        page = requests.get(album_url, headers=BROWSER_HEADERS, timeout=timeout)
        page.raise_for_status()
    except requests.RequestException as exc:
        raise AlbumError(f"the album page could not be fetched: {exc}") from exc

    urls = photo_urls(page.text, size=size)
    if not urls:
        raise AlbumError(
            "no photos found on the album page — either the album is not "
            "public, or Google changed the page and this needs revisiting"
        )

    directory = Path(photo_dir)
    directory.mkdir(parents=True, exist_ok=True)

    added = 0
    for url in urls[:limit]:
        target = directory / f"{_name_for(url)}.jpg"
        if target.exists():
            continue
        try:
            _download(url, target, timeout)
        except (requests.RequestException, OSError) as exc:
            log.warning("Skipping one photo: %s", exc)
            continue
        added += 1

    log.info("Album: %d photos listed, %d new", len(urls), added)
    return added


def _name_for(url: str) -> str:
    """A stable filename for a photo, so a second sync recognises it.

    Google's own identifier is long and full of characters a filesystem would
    rather not see; its digest is neither.
    """
    return hashlib.sha256(url.split("=")[0].encode("utf-8")).hexdigest()[:20]


def _download(url: str, target: Path, timeout: int) -> None:
    response = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout, stream=True)
    response.raise_for_status()

    partial = target.with_suffix(".part")
    with partial.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            handle.write(chunk)

    # Only a file that is actually an image gets a name the library will read.
    with partial.open("rb") as handle:
        if handle.read(3) != b"\xff\xd8\xff":
            partial.unlink(missing_ok=True)
            raise OSError(f"{url} did not return a JPEG")

    partial.replace(target)
