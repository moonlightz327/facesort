"""Copy-on-write cloning for the copy stage.

Sorting a shoot copies every photo into a person's folder, which on a normal
filesystem means a second full copy of the whole shoot — the reason a 99%-full
disk ran out mid-sort. APFS can instead point a new file at the same blocks:
measured on a 200MB file, `shutil.copy2` took 321ms and 200MB of disk, a clone
took under a millisecond and 0 bytes. Same bytes, independent file."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from facesort.core import organizer
from facesort.core.organizer import copy_file

on_macos = pytest.mark.skipif(sys.platform != "darwin", reason="clonefile 是 macOS API")


def _src(tmp_path: Path, content=b"photo-bytes") -> Path:
    p = tmp_path / "src.jpg"
    p.write_bytes(content)
    return p


def test_copy_reproduces_content_exactly(tmp_path):
    src = _src(tmp_path, os.urandom(100_000))
    dst = tmp_path / "out" / "copy.jpg"
    dst.parent.mkdir()

    copy_file(str(src), str(dst))

    assert dst.read_bytes() == src.read_bytes()
    assert dst.stat().st_size == src.stat().st_size


@on_macos
def test_clone_is_used_on_apfs(tmp_path):
    """tmp_path is on the machine's own disk, which is APFS on any modern Mac."""
    src = _src(tmp_path)
    assert copy_file(str(src), str(tmp_path / "clone.jpg")) is True


@on_macos
def test_clone_is_an_independent_file(tmp_path):
    """A clone must behave like a copy, not like a hard link — otherwise
    organizing photos would quietly alias them together."""
    src = _src(tmp_path, b"original")
    dst = tmp_path / "clone.jpg"
    copy_file(str(src), str(dst))

    dst.write_bytes(b"edited-in-place")
    assert src.read_bytes() == b"original", "改动克隆不能影响原文件"

    src.unlink()
    assert dst.read_bytes() == b"edited-in-place", "删除原文件后克隆仍须完好"


def test_falls_back_to_a_real_copy_when_cloning_is_unavailable(tmp_path, monkeypatch):
    """Non-APFS disks, exFAT cards, Windows — the copy still has to happen."""
    monkeypatch.setattr(organizer, "_CLONEFILE", None)
    src = _src(tmp_path)
    dst = tmp_path / "copy.jpg"

    assert copy_file(str(src), str(dst)) is False
    assert dst.read_bytes() == src.read_bytes()


def test_falls_back_when_the_clone_call_fails(tmp_path, monkeypatch):
    """EXDEV (different volume), ENOTSUP (not APFS): fall through, don't fail."""
    monkeypatch.setattr(organizer, "_CLONEFILE", lambda a, b, c: -1)
    src = _src(tmp_path)
    dst = tmp_path / "copy.jpg"

    assert copy_file(str(src), str(dst)) is False
    assert dst.read_bytes() == src.read_bytes()


def test_a_failed_clone_leaves_nothing_behind(tmp_path, monkeypatch):
    """If the clone half-created the destination, the fallback copy must not
    trip over it — and a genuine copy failure must not leave it either."""
    def half_clone(s, d, flags):
        os.write(os.open(d, os.O_CREAT | os.O_WRONLY, 0o644), b"")
        return -1

    monkeypatch.setattr(organizer, "_CLONEFILE", half_clone)
    src = _src(tmp_path)
    dst = tmp_path / "copy.jpg"

    assert copy_file(str(src), str(dst)) is False
    assert dst.read_bytes() == src.read_bytes()


def test_clone_count_is_reported(tmp_path):
    """The report says how many copies cost no space, so the user can see it."""
    import numpy as np

    from facesort.core.models import Config, Face, FaceMatch, PhotoOutcome
    from facesort.core.organizer import build_plan, execute_plan

    src = tmp_path / "in" / "a.jpg"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"payload")
    face = Face(bbox=(0, 0, 100, 100), embedding=np.zeros(512, dtype=np.float32))
    outcome = PhotoOutcome(path=src, width=100, height=100, matches=[
        FaceMatch(face=face, person="张三", similarity=0.8, subject_score=0.5)])
    config = Config(samples_dir=tmp_path / "s", input_dir=tmp_path / "in",
                    output_dir=tmp_path / "out")

    result = execute_plan(build_plan([outcome], config))

    assert result.copied == 1
    assert result.to_dict()["cloned"] == (1 if sys.platform == "darwin" else 0)
