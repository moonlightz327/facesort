"""Organizer tests: plan building (conflict rename, idempotent skip, multi-person
strategies) and plan execution (copy/move). No insightface; faces are fabricated."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from facesort.core.models import (
    ACT_COPY,
    ACT_MOVE,
    ACT_SKIP,
    CAT_GROUP,
    CAT_NO_FACE,
    CAT_PERSON,
    CAT_UNRECOGNIZED,
    Config,
    Face,
    FaceMatch,
    PhotoOutcome,
)
from facesort.core.organizer import build_plan, execute_plan


def _face(x1=0.0, y1=0.0, x2=100.0, y2=100.0) -> Face:
    return Face(bbox=(x1, y1, x2, y2), embedding=np.zeros(512, dtype=np.float32))


def _match(person, similarity, subject_score=0.5, **bbox) -> FaceMatch:
    return FaceMatch(
        face=_face(**bbox),
        person=person,
        similarity=similarity,
        subject_score=subject_score,
    )


def _outcome(path: Path, matches, ignored=0) -> PhotoOutcome:
    return PhotoOutcome(path=path, width=1000, height=800, matches=matches,
                        ignored_small_faces=ignored)


def _config(tmp_path: Path, **kw) -> Config:
    defaults = dict(
        samples_dir=tmp_path / "s",
        input_dir=tmp_path / "in",
        output_dir=tmp_path / "out",
    )
    defaults.update(kw)
    return Config(**defaults)


def _touch(path: Path, content: bytes = b"data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ---------- plan building ----------

def test_no_face_goes_to_no_face_dir(tmp_path):
    p = _touch(tmp_path / "in" / "a.jpg")
    plan = build_plan([_outcome(p, [])], _config(tmp_path))
    assert len(plan.items) == 1
    item = plan.items[0]
    assert item.category == CAT_NO_FACE
    assert Path(item.dst).parent.name == "_无人脸"
    assert item.similarity is None


def test_faces_but_none_matched_goes_to_unrecognized(tmp_path):
    p = _touch(tmp_path / "in" / "a.jpg")
    out = _outcome(p, [_match(None, 0.20)])
    plan = build_plan([out], _config(tmp_path))
    assert plan.items[0].category == CAT_UNRECOGNIZED
    assert Path(plan.items[0].dst).parent.name == "_未识别"


def test_single_person_folder_named_by_person(tmp_path):
    p = _touch(tmp_path / "in" / "a.jpg")
    out = _outcome(p, [_match("张三", 0.7)])
    plan = build_plan([out], _config(tmp_path))
    item = plan.items[0]
    assert item.category == CAT_PERSON
    assert item.person == "张三"
    assert Path(item.dst).parent.name == "张三"
    assert Path(item.dst).name == "a.jpg"  # default file template = {orig_name}{ext}


def test_conflict_rename_appends_suffix(tmp_path):
    # Two different source files that would land on the same destination name.
    p1 = _touch(tmp_path / "in" / "sub1" / "a.jpg", b"one")
    p2 = _touch(tmp_path / "in" / "sub2" / "a.jpg", b"two-different")
    outs = [
        _outcome(p1, [_match("张三", 0.7)]),
        _outcome(p2, [_match("张三", 0.7)]),
    ]
    plan = build_plan(outs, _config(tmp_path))
    names = sorted(Path(i.dst).name for i in plan.items)
    assert names == ["a-1.jpg", "a.jpg"]
    assert all(i.action == ACT_COPY for i in plan.items)


def test_idempotent_skip_when_identical_file_already_present(tmp_path):
    src = _touch(tmp_path / "in" / "a.jpg", b"same-bytes")
    # Pre-place an identical-size file at the destination.
    _touch(tmp_path / "out" / "张三" / "a.jpg", b"same-bytes")
    out = _outcome(src, [_match("张三", 0.7)])
    plan = build_plan([out], _config(tmp_path))
    assert plan.items[0].action == ACT_SKIP
    assert "幂等" in plan.items[0].reason


def test_multi_person_primary_picks_highest_subject_score(tmp_path):
    p = _touch(tmp_path / "in" / "a.jpg")
    out = _outcome(p, [
        _match("张三", 0.6, subject_score=0.4),
        _match("李四", 0.6, subject_score=0.9),
    ])
    plan = build_plan([out], _config(tmp_path, multi_person="primary"))
    assert len(plan.items) == 1
    assert plan.items[0].person == "李四"
    assert plan.multi_person_photos == 1


def test_multi_person_all_copies_to_each(tmp_path):
    p = _touch(tmp_path / "in" / "a.jpg")
    out = _outcome(p, [
        _match("张三", 0.6, subject_score=0.9),
        _match("李四", 0.6, subject_score=0.4),
    ])
    plan = build_plan([out], _config(tmp_path, multi_person="all"))
    people = sorted(Path(i.dst).parent.name for i in plan.items)
    assert people == ["张三", "李四"]
    assert all(i.action == ACT_COPY for i in plan.items)


def test_multi_person_all_move_mode_moves_last_only(tmp_path):
    p = _touch(tmp_path / "in" / "a.jpg")
    out = _outcome(p, [
        _match("张三", 0.6, subject_score=0.9),
        _match("李四", 0.6, subject_score=0.4),
    ])
    plan = build_plan([out], _config(tmp_path, multi_person="all", move=True))
    actions = [i.action for i in plan.items]
    assert actions.count(ACT_MOVE) == 1  # original moved exactly once
    assert actions.count(ACT_COPY) == 1


def test_multi_person_group_goes_to_group_dir_with_subfolders(tmp_path):
    p = _touch(tmp_path / "in" / "a.jpg")
    out = _outcome(p, [
        _match("张三", 0.6, subject_score=0.9),
        _match("李四", 0.6, subject_score=0.4),
    ])
    plan = build_plan([out], _config(tmp_path, multi_person="group",
                                     group_subfolders=True))
    item = plan.items[0]
    assert item.category == CAT_GROUP
    assert Path(item.dst).parent.name == "张三+李四"  # sorted, sanitized
    assert Path(item.dst).parent.parent.name == "_合影"


def test_ambiguous_face_recorded_in_report(tmp_path):
    p = _touch(tmp_path / "in" / "a.jpg")
    m = FaceMatch(face=_face(), person="张三", similarity=0.62,
                  second_person="李四", second_similarity=0.60, ambiguous=True,
                  subject_score=0.5)
    plan = build_plan([_outcome(p, [m])], _config(tmp_path))
    assert len(plan.ambiguous) == 1
    assert plan.ambiguous[0]["person"] == "张三"
    assert plan.ambiguous[0]["second_person"] == "李四"


def test_folder_index_counter_per_folder(tmp_path):
    p1 = _touch(tmp_path / "in" / "one.jpg")
    p2 = _touch(tmp_path / "in" / "two.jpg")
    outs = [_outcome(p1, [_match("张三", 0.7)]), _outcome(p2, [_match("张三", 0.7)])]
    cfg = _config(tmp_path, file_template="{index:03d}{ext}")
    plan = build_plan(outs, cfg)
    names = sorted(Path(i.dst).name for i in plan.items)
    assert names == ["001.jpg", "002.jpg"]


def test_plan_is_json_serializable(tmp_path):
    import json
    p = _touch(tmp_path / "in" / "a.jpg")
    plan = build_plan([_outcome(p, [_match("张三", 0.7)])], _config(tmp_path))
    json.dumps(plan.to_dict())  # must not raise


# ---------- plan execution ----------

def test_execute_copy_leaves_source_intact(tmp_path):
    src = _touch(tmp_path / "in" / "a.jpg", b"payload")
    plan = build_plan([_outcome(src, [_match("张三", 0.7)])], _config(tmp_path))
    result = execute_plan(plan)
    assert result.copied == 1
    assert src.exists()  # copy mode: original untouched
    dst = Path(plan.items[0].dst)
    assert dst.exists() and dst.read_bytes() == b"payload"


def test_execute_move_removes_source(tmp_path):
    src = _touch(tmp_path / "in" / "a.jpg", b"payload")
    plan = build_plan([_outcome(src, [_match("张三", 0.7)])], _config(tmp_path, move=True))
    result = execute_plan(plan)
    assert result.moved == 1
    assert not src.exists()
    assert Path(plan.items[0].dst).exists()


def test_execute_never_overwrites_unplanned_existing(tmp_path):
    src = _touch(tmp_path / "in" / "a.jpg", b"new")
    plan = build_plan([_outcome(src, [_match("张三", 0.7)])], _config(tmp_path))
    # Create a DIFFERENT-size file at the destination AFTER planning.
    dst = Path(plan.items[0].dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(b"pre-existing-longer-content")
    result = execute_plan(plan)
    assert len(result.errors) == 1
    assert dst.read_bytes() == b"pre-existing-longer-content"  # preserved


def test_execute_cancel_stops_early(tmp_path):
    import threading
    outs = []
    for i in range(5):
        s = _touch(tmp_path / "in" / f"a{i}.jpg", f"c{i}".encode())
        outs.append(_outcome(s, [_match("张三", 0.7)]))
    plan = build_plan(outs, _config(tmp_path))
    ev = threading.Event()
    ev.set()  # cancel immediately
    result = execute_plan(plan, cancel=ev)
    assert result.cancelled
    assert result.copied == 0
