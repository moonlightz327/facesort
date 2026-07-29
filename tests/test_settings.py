"""Persisted settings: what makes a machine stay configured across restarts."""

import json

import pytest

from facesort.gui import settings as app_settings


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "app_support_dir", lambda: tmp_path)
    return tmp_path


def test_defaults_when_nothing_saved(home):
    s = app_settings.load()
    assert s == app_settings.DEFAULTS
    assert not (home / "settings.json").exists()


def test_save_then_load_round_trip(home):
    app_settings.save({"workers": 4, "decodeMaxSide": 0})
    s = app_settings.load()
    assert s["workers"] == 4
    assert s["decodeMaxSide"] == 0
    # Untouched keys keep their defaults.
    assert s["threshold"] == app_settings.DEFAULTS["threshold"]


def test_save_merges_instead_of_replacing(home):
    app_settings.save({"workers": 2})
    app_settings.save({"minFace": 80})
    s = app_settings.load()
    assert s["workers"] == 2 and s["minFace"] == 80


def test_unknown_keys_are_not_persisted(home):
    """A hand-edited or stale file must not inject arbitrary config."""
    app_settings.save({"workers": 2, "evil": "rm -rf"})
    raw = json.loads((home / "settings.json").read_text())
    assert "evil" not in raw
    assert "evil" not in app_settings.load()


def test_corrupt_file_falls_back_to_defaults(home):
    (home / "settings.json").write_text("{ not json")
    assert app_settings.load() == app_settings.DEFAULTS


def test_wrong_types_in_file_are_ignored(home):
    (home / "settings.json").write_text(json.dumps({"workers": "lots", "minFace": 60}))
    s = app_settings.load()
    assert s["workers"] == app_settings.DEFAULTS["workers"]  # rejected
    assert s["minFace"] == 60                                # accepted


def test_int_threshold_is_coerced_to_float(home):
    (home / "settings.json").write_text(json.dumps({"threshold": 1}))
    assert app_settings.load()["threshold"] == pytest.approx(1.0)


def test_reset_removes_the_file(home):
    app_settings.save({"workers": 6})
    assert (home / "settings.json").exists()
    assert app_settings.reset() == app_settings.DEFAULTS
    assert not (home / "settings.json").exists()
    assert app_settings.load() == app_settings.DEFAULTS
