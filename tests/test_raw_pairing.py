"""RAW support: extension recognition, same-stem RAW+JPEG pairing, and that a
sidecar RAW lands in the same folder as its JPEG. No insightface / no rawpy."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from facesort.core.imageio import IMAGE_EXTS, is_image_file, is_raw_file
from facesort.core.models import Config, Face, FaceMatch, PhotoOutcome
from facesort.core.organizer import build_plan
from facesort.core.pipeline import pair_photos


def test_raw_extensions_recognized():
    assert is_raw_file(Path("a.CR3")) and is_raw_file(Path("b.nef"))
    assert is_image_file(Path("a.cr2"))  # RAW counts as an image for scanning
    assert not is_raw_file(Path("a.jpg"))
    assert {".cr3", ".nef", ".arw", ".dng"} <= IMAGE_EXTS


def test_pair_raw_and_jpeg_same_stem():
    photos = [Path("/p/IMG_1.CR3"), Path("/p/IMG_1.JPG"), Path("/p/IMG_2.jpg")]
    units = pair_photos(photos)
    by_primary = {u[0].name: [s.name for s in u[1]] for u in units}
    # IMG_1: JPEG is primary, RAW is the sidecar; IMG_2: standalone.
    assert by_primary["IMG_1.JPG"] == ["IMG_1.CR3"]
    assert by_primary["IMG_2.jpg"] == []
    assert len(units) == 2


def test_pair_raw_only_is_its_own_unit():
    units = pair_photos([Path("/p/IMG_9.arw")])
    assert units == [(Path("/p/IMG_9.arw"), [])]


def test_same_stem_different_dirs_not_paired():
    units = pair_photos([Path("/a/IMG.CR2"), Path("/b/IMG.jpg")])
    assert len(units) == 2
    assert all(u[1] == [] for u in units)


def _outcome_with_sidecar(primary: Path, sidecar: Path) -> PhotoOutcome:
    m = FaceMatch(face=Face(bbox=(0, 0, 100, 100), embedding=np.zeros(512, dtype=np.float32)),
                  person="张三", similarity=0.7, subject_score=0.5)
    return PhotoOutcome(path=primary, width=1000, height=800, matches=[m], sidecars=[sidecar])


def test_sidecar_raw_follows_jpeg_to_same_folder(tmp_path):
    jpg = tmp_path / "in" / "IMG_1.jpg"
    raw = tmp_path / "in" / "IMG_1.CR3"
    for p in (jpg, raw):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    cfg = Config(samples_dir=tmp_path / "s", input_dir=tmp_path / "in",
                 output_dir=tmp_path / "out")
    plan = build_plan([_outcome_with_sidecar(jpg, raw)], cfg)
    assert len(plan.items) == 2
    folders = {Path(i.dst).parent.name for i in plan.items}
    names = sorted(Path(i.dst).name for i in plan.items)
    assert folders == {"张三"}          # both in the same person folder
    assert names == ["IMG_1.CR3", "IMG_1.jpg"]  # each keeps its own name


def test_sidecar_move_mode_moves_both_once(tmp_path):
    jpg = tmp_path / "in" / "IMG_1.jpg"
    raw = tmp_path / "in" / "IMG_1.CR3"
    for p in (jpg, raw):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    cfg = Config(samples_dir=tmp_path / "s", input_dir=tmp_path / "in",
                 output_dir=tmp_path / "out", move=True)
    plan = build_plan([_outcome_with_sidecar(jpg, raw)], cfg)
    from facesort.core.models import ACT_MOVE
    assert [i.action for i in plan.items] == [ACT_MOVE, ACT_MOVE]  # each moved once
