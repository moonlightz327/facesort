"""report.json must never be the thing that sinks a finished run.

Found by the 2000-photo stress run on a nearly full disk: every photo had
already been copied and the run then died writing its report, losing the record
of which files failed — the one thing the user needed at that point."""

from __future__ import annotations

import json

import pytest

from facesort.report import write_report


def test_report_is_written(tmp_path):
    report = {"version": "test", "warnings": []}
    path = write_report(report, tmp_path / "out")
    assert path is not None and path.name == "report.json"
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == "test"
    assert report["report_written"] is True


def test_full_disk_does_not_lose_the_run(tmp_path, monkeypatch):
    report = {"version": "test", "warnings": [], "execution": {"copied": 4813}}

    def no_space(*a, **kw):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("pathlib.Path.write_text", no_space)
    path = write_report(report, tmp_path / "out")

    assert path is None
    assert report["report_written"] is False
    assert any("写入失败" in w for w in report["warnings"])
    # The run's own numbers survive for the caller to show.
    assert report["execution"]["copied"] == 4813


def test_unwritable_directory_does_not_raise(tmp_path, monkeypatch):
    def denied(*a, **kw):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr("pathlib.Path.mkdir", denied)
    assert write_report({"warnings": []}, tmp_path / "nope") is None
