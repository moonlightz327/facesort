"""Renaming auto-detected clusters before anything is written to disk."""

import numpy as np

from facesort.core.matcher import SampleLibrary
from facesort.core.pipeline import apply_cluster_names
from tests.conftest import unit


def _library(names):
    """SampleLibrary with one centroid per name, plus the id->name map."""
    lib = SampleLibrary()
    mapping = {}
    for i, n in enumerate(names):
        lib.add(n, unit(i))
        mapping[i] = n
    return lib, mapping


def test_no_overrides_returns_library_untouched():
    lib, names = _library(["人物1", "人物2"])
    out_lib, out_names = apply_cluster_names(lib, names, {})
    assert out_lib is lib
    assert out_names == names


def test_rename_applies_to_library_and_name_map():
    lib, names = _library(["人物1", "人物2"])
    out_lib, out_names = apply_cluster_names(lib, names, {"人物1": "张三"})
    assert set(out_lib.people) == {"张三", "人物2"}
    assert out_names == {0: "张三", 1: "人物2"}
    # The embedding travels with the rename.
    assert np.allclose(out_lib.people["张三"][0], unit(0))


def test_blank_and_identical_names_are_ignored():
    lib, names = _library(["人物1", "人物2"])
    out_lib, out_names = apply_cluster_names(
        lib, names, {"人物1": "   ", "人物2": "人物2"})
    assert out_lib is lib
    assert out_names == names


def test_two_clusters_named_the_same_are_merged():
    """Naming 人物1 and 人物3 both 张三 means they are one person."""
    lib, names = _library(["人物1", "人物2", "人物3"])
    out_lib, out_names = apply_cluster_names(
        lib, names, {"人物1": "张三", "人物3": "张三"})
    assert set(out_lib.people) == {"张三", "人物2"}
    # Both centroids are kept as samples of that person.
    assert out_lib.people["张三"].shape == (2, 512)
    assert out_names == {0: "张三", 1: "人物2", 2: "张三"}


def test_names_are_sanitized_for_use_as_folder_names():
    lib, names = _library(["人物1"])
    out_lib, out_names = apply_cluster_names(lib, names, {"人物1": "张三/李四"})
    assert "/" not in out_names[0]
    assert list(out_lib.people) == [out_names[0]]
