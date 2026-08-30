"""Configuration parsing, including the settings that fail closed."""
from __future__ import annotations

import pytest

from glanceboard.config import ConfigError, Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    import os

    for name in list(os.environ):
        if name.startswith("GB_"):
            monkeypatch.delenv(name, raising=False)


def test_defaults_bind_to_localhost():
    """0.0.0.0 is the upstream default and is not this project's."""
    assert Settings.from_env().bind_host == "127.0.0.1"


def test_slots_are_parsed_sorted_and_deduplicated(monkeypatch):
    monkeypatch.setenv("GB_SLOTS", "18, 5,12, 5")
    assert Settings.from_env().slots == (5, 12, 18)


def test_an_impossible_slot_is_rejected(monkeypatch):
    monkeypatch.setenv("GB_SLOTS", "25")
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_an_unknown_timezone_is_rejected(monkeypatch):
    monkeypatch.setenv("GB_TIMEZONE", "Mars/Olympus")
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_the_reserved_band_fraction_is_bounded(monkeypatch):
    monkeypatch.setenv("GB_ART_FRACTION", "0.8")
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_a_secret_can_come_from_a_file(monkeypatch, tmp_path):
    """Docker and podman secrets arrive as files, not environment values."""
    secret = tmp_path / "ical_url"
    secret.write_text("https://example.invalid/private.ics\n", encoding="utf-8")
    monkeypatch.setenv("GB_ICAL_URL_FILE", str(secret))
    assert Settings.from_env().ical_url == "https://example.invalid/private.ics"


def test_an_unreadable_secret_file_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv("GB_ICAL_URL_FILE", str(tmp_path / "missing"))
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_serving_requires_a_long_token(monkeypatch):
    monkeypatch.setenv("GB_DISPLAY_TOKEN", "tooshort")
    with pytest.raises(ConfigError):
        Settings.from_env().require_serving_credentials()


def test_serving_accepts_a_long_token(monkeypatch):
    monkeypatch.setenv("GB_DISPLAY_TOKEN", "x" * 32)
    Settings.from_env().require_serving_credentials()  # does not raise


def test_paths_are_absolute_and_independent_of_the_working_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("GB_OUTPUT_DIR", str(tmp_path / "out"))
    settings = Settings.from_env()
    assert settings.image_path == tmp_path / "out" / "board.png"
    assert settings.font_dir.is_absolute()


def test_temperature_unit_is_validated(monkeypatch):
    monkeypatch.setenv("GB_TEMP_UNIT", "kelvin")
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_rotation_defaults_to_a_quarter_turn():
    """The canvas is landscape; the panel is not."""
    assert Settings.from_env().rotate == 90


def test_an_impossible_rotation_is_rejected(monkeypatch):
    monkeypatch.setenv("GB_ROTATE", "45")
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_rotation_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("GB_ROTATE", "0")
    assert Settings.from_env().rotate == 0
