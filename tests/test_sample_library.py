"""build_sample_library tolerance for half-set-up sample folders.

The GUI lets you create a person before giving them photos; such an empty
folder used to abort every later run with ConfigError, which is what made saved
people feel unusable."""

import numpy as np
import pytest

from facesort.core.imageio import ImageReadError
from facesort.core.models import ConfigError, Face, PhotoAnalysis
from facesort.core.pipeline import build_sample_library
from tests.conftest import unit


class FakeEngine:
    """Returns a face per photo, keyed by filename, without touching pixels."""

    def __init__(self, faces_by_name=None, unreadable=()):
        self.faces_by_name = faces_by_name or {}
        self.unreadable = set(unreadable)

    def analyze(self, path, max_side=None):
        if path.name in self.unreadable:
            raise ImageReadError(f"corrupt: {path.name}")
        n = self.faces_by_name.get(path.name, 1)
        faces = [
            Face(bbox=(0, 0, 100 - i * 10, 100 - i * 10), embedding=unit(i))
            for i in range(n)
        ]
        return PhotoAnalysis(path=path, width=1000, height=800, faces=faces)


def _person(root, name, files):
    d = root / name
    d.mkdir(parents=True)
    for f in files:
        (d / f).write_bytes(b"")
    return d


def test_person_without_samples_is_skipped_not_fatal(tmp_path):
    _person(tmp_path, "张三", ["a.jpg"])
    _person(tmp_path, "李四", [])  # created in the GUI, no photos yet

    lib = build_sample_library(FakeEngine(), tmp_path)

    assert set(lib.people) == {"张三"}
    assert any("李四" in w for w in lib.warnings)


def test_person_whose_photos_have_no_face_is_skipped(tmp_path):
    _person(tmp_path, "张三", ["a.jpg"])
    _person(tmp_path, "李四", ["b.jpg"])

    lib = build_sample_library(FakeEngine(faces_by_name={"b.jpg": 0}), tmp_path)

    assert set(lib.people) == {"张三"}
    assert any("未检测到人脸" in w for w in lib.warnings)


def test_unreadable_sample_is_skipped_with_a_warning(tmp_path):
    _person(tmp_path, "张三", ["good.jpg", "broken.jpg"])

    lib = build_sample_library(FakeEngine(unreadable=["broken.jpg"]), tmp_path)

    assert lib.people["张三"].shape == (1, 512)
    assert any("无法读取" in w for w in lib.warnings)


def test_all_people_empty_is_still_a_hard_error(tmp_path):
    _person(tmp_path, "张三", [])
    _person(tmp_path, "李四", [])

    with pytest.raises(ConfigError) as e:
        build_sample_library(FakeEngine(), tmp_path)
    # The message names who is missing samples so the user can fix it.
    assert "张三" in str(e.value) and "李四" in str(e.value)


def test_multi_face_sample_uses_the_largest_face_and_warns(tmp_path):
    _person(tmp_path, "张三", ["group.jpg"])

    lib = build_sample_library(FakeEngine(faces_by_name={"group.jpg": 3}), tmp_path)

    assert lib.people["张三"].shape == (1, 512)
    assert np.allclose(lib.people["张三"][0], unit(0))  # biggest bbox
    assert any("取最大人脸" in w for w in lib.warnings)


@pytest.mark.parametrize("workers", [1, 4])
def test_parallel_workers_do_not_change_the_library(tmp_path, workers):
    _person(tmp_path, "张三", [f"{i}.jpg" for i in range(6)])

    lib = build_sample_library(FakeEngine(), tmp_path, workers=workers)

    assert lib.people["张三"].shape == (6, 512)
