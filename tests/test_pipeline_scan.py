"""scan_photos tests: recursion, output-dir exclusion (edge #9), non-image
skipping, hidden-file skipping. No insightface."""

from __future__ import annotations

from pathlib import Path

from facesort.core.pipeline import scan_photos


def _touch(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_finds_images_recursively(tmp_path):
    inp = tmp_path / "in"
    _touch(inp / "a.jpg")
    _touch(inp / "sub" / "b.png")
    _touch(inp / "sub" / "deep" / "c.jpeg")
    photos, skipped = scan_photos(inp, tmp_path / "out")
    names = sorted(p.name for p in photos)
    assert names == ["a.jpg", "b.png", "c.jpeg"]


def test_excludes_output_dir_inside_input(tmp_path):
    inp = tmp_path / "in"
    _touch(inp / "a.jpg")
    out = inp / "_sorted"  # output nested inside input
    _touch(out / "张三" / "already.jpg")  # must NOT be picked up (edge #9)
    photos, _ = scan_photos(inp, out)
    names = sorted(p.name for p in photos)
    assert names == ["a.jpg"]


def test_non_images_are_skipped_and_reported(tmp_path):
    inp = tmp_path / "in"
    _touch(inp / "a.jpg")
    _touch(inp / "notes.txt")
    _touch(inp / "video.mov")
    photos, skipped = scan_photos(inp, tmp_path / "out")
    assert [p.name for p in photos] == ["a.jpg"]
    skipped_names = sorted(Path(s["path"]).name for s in skipped)
    assert skipped_names == ["notes.txt", "video.mov"]


def test_hidden_files_ignored(tmp_path):
    inp = tmp_path / "in"
    _touch(inp / "a.jpg")
    _touch(inp / ".DS_Store")
    _touch(inp / ".hidden.jpg")
    photos, _ = scan_photos(inp, tmp_path / "out")
    assert [p.name for p in photos] == ["a.jpg"]
