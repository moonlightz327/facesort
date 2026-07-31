"""Sample-free mode end to end, with a fake engine so no model is needed.

Covers the reported 「五六个人分出一百多号」: only confident faces get to define
a group, and a face seen once does not become a folder — but no photo is lost to
either rule, because every face is still matched against the surviving groups."""

from __future__ import annotations

import numpy as np
import pytest

from facesort.core.models import Config, Face, PhotoAnalysis
from facesort.core.pipeline import run_cluster_pipeline
from tests.conftest import unit


class ScriptedEngine:
    """Returns exactly the faces a test asks for, per filename."""

    def __init__(self, faces_by_name):
        self.faces_by_name = faces_by_name

    def analyze(self, path, max_side=None):
        faces = [
            Face(bbox=(0, 0, 200, 200), embedding=emb, det_score=det)
            for emb, det in self.faces_by_name.get(path.name, [])
        ]
        return PhotoAnalysis(path=path, width=1000, height=800, faces=faces)


def _shoot(tmp_path, names):
    src = tmp_path / "in"
    src.mkdir(parents=True, exist_ok=True)
    for n in names:
        (src / n).write_bytes(b"x")
    return src


def _config(tmp_path, **kw):
    defaults = dict(
        samples_dir=tmp_path / "s",
        input_dir=tmp_path / "in",
        output_dir=tmp_path / "out",
        threshold=0.5,
        dry_run=True,
        workers=1,
    )
    defaults.update(kw)
    return Config(**defaults)


def _folders(result):
    """person -> photo count, from the plan."""
    out = {}
    for item in result.plan.items:
        key = item.person or item.category
        out[key] = out.get(key, 0) + 1
    return out


def test_one_off_faces_do_not_each_become_a_folder(tmp_path):
    """Two people in many frames, plus five strangers seen once each."""
    a, b = unit(0), unit(1)
    script = {}
    names = []
    for i in range(6):
        script[f"a{i}.jpg"] = [(a, 0.9)]
        script[f"b{i}.jpg"] = [(b, 0.9)]
        names += [f"a{i}.jpg", f"b{i}.jpg"]
    for i in range(5):
        script[f"x{i}.jpg"] = [(unit(20 + i), 0.9)]  # a different stranger each
        names.append(f"x{i}.jpg")
    _shoot(tmp_path, names)

    result = run_cluster_pipeline(_config(tmp_path, cluster_min_photos=2),
                                  engine=ScriptedEngine(script))

    folders = _folders(result)
    people = [k for k in folders if k.startswith("人物")]
    assert len(people) == 2, f"应只分出 2 个人物分组，实际 {sorted(folders)}"
    assert folders["unrecognized"] == 5, "路人应归入未识别，而不是各占一个文件夹"


def test_min_photos_one_restores_the_old_behaviour(tmp_path):
    """The knob is real: set it to 1 and every face groups again."""
    a = unit(0)
    script = {"a0.jpg": [(a, 0.9)], "a1.jpg": [(a, 0.9)]}
    names = ["a0.jpg", "a1.jpg"]
    for i in range(4):
        script[f"x{i}.jpg"] = [(unit(20 + i), 0.9)]
        names.append(f"x{i}.jpg")
    _shoot(tmp_path, names)

    result = run_cluster_pipeline(_config(tmp_path, cluster_min_photos=1),
                                  engine=ScriptedEngine(script))

    people = [k for k in _folders(result) if k.startswith("人物")]
    assert len(people) == 5


def test_weak_detections_do_not_seed_groups_but_still_get_placed(tmp_path):
    """A blurry face must not invent a person — and must not be thrown away
    either: if it looks like someone the shoot already knows, it goes to them."""
    a = unit(0)
    script = {
        "a0.jpg": [(a, 0.95)],
        "a1.jpg": [(a, 0.95)],
        "a2.jpg": [(a, 0.95)],
        "blurry.jpg": [(a, 0.40)],           # same person, weak detection
        "junk.jpg": [(unit(30), 0.40)],      # weak detection of nobody
    }
    _shoot(tmp_path, list(script))

    result = run_cluster_pipeline(
        _config(tmp_path, cluster_min_photos=2, cluster_min_det=0.65),
        engine=ScriptedEngine(script))

    by_src = {item.src.split("/")[-1]: item for item in result.plan.items}
    assert by_src["blurry.jpg"].person == "人物1", "低置信度但确实是同一个人，应归到 TA"
    assert by_src["junk.jpg"].person is None
    people = {i.person for i in result.plan.items if i.person}
    assert people == {"人物1"}


def test_falls_back_to_all_faces_when_none_are_confident(tmp_path):
    """A soft-focus set must still group; some grouping beats none."""
    a = unit(0)
    script = {f"a{i}.jpg": [(a, 0.52)] for i in range(4)}  # all below the gate
    _shoot(tmp_path, list(script))

    result = run_cluster_pipeline(
        _config(tmp_path, cluster_min_photos=2, cluster_min_det=0.65),
        engine=ScriptedEngine(script))

    assert {i.person for i in result.plan.items} == {"人物1"}


def test_dropped_clusters_are_explained_in_the_warnings(tmp_path):
    a = unit(0)
    script = {"a0.jpg": [(a, 0.9)], "a1.jpg": [(a, 0.9)], "x.jpg": [(unit(9), 0.9)]}
    _shoot(tmp_path, list(script))

    result = run_cluster_pipeline(_config(tmp_path, cluster_min_photos=2),
                                  engine=ScriptedEngine(script))

    assert any("_未识别" in w for w in result.plan.warnings), \
        "少分出的组必须有解释，否则看起来像照片丢了"
