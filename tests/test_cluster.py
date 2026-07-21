"""Sample-free clustering tests with fabricated embeddings of known geometry.
No insightface."""

from __future__ import annotations

import numpy as np

from facesort.core.cluster import build_cluster_library, greedy_cluster
from tests.conftest import unit, vec_with_sim


def test_three_separated_groups_form_three_clusters():
    # Three orthogonal directions => three well-separated clusters.
    embs = []
    for base in (unit(0), unit(1), unit(2)):
        embs += [vec_with_sim(base, 0.95, 10), vec_with_sim(base, 0.95, 11), base]
    labels = greedy_cluster(embs, threshold=0.5)
    assert len(set(labels)) == 3
    # Each consecutive triple shares a label.
    assert labels[0] == labels[1] == labels[2]
    assert labels[3] == labels[4] == labels[5]
    assert labels[0] != labels[3]


def test_singletons_stay_separate_below_threshold():
    embs = [unit(0), unit(1), unit(2), unit(3)]  # mutually orthogonal
    labels = greedy_cluster(embs, threshold=0.5)
    assert len(set(labels)) == 4


def test_library_named_by_photo_count_desc():
    # Cluster A appears in 3 photos, cluster B in 1 photo.
    a = unit(0)
    b = unit(1)
    face_embeddings = [a, a, a, b]
    photo_of_face = [0, 1, 2, 3]  # 4 distinct photos
    library, names = build_cluster_library(face_embeddings, photo_of_face, threshold=0.5)
    assert set(names.values()) == {"人物1", "人物2"}
    # The 3-photo cluster must be 人物1 (ranked first).
    counts = {}
    labels = greedy_cluster(face_embeddings, 0.5)
    for lab, name in names.items():
        counts[name] = sum(1 for l in labels if l == lab)
    assert counts["人物1"] == 3
    assert "人物1" in library.people and "人物2" in library.people


def test_min_cluster_photos_drops_noise():
    a = unit(0)
    b = unit(1)
    face_embeddings = [a, a, b]  # a in 2 photos, b in 1
    photo_of_face = [0, 1, 2]
    library, names = build_cluster_library(
        face_embeddings, photo_of_face, threshold=0.5, min_cluster_photos=2)
    assert set(names.values()) == {"人物1"}  # b's singleton cluster dropped
    assert len(library.people) == 1


def test_empty_input_yields_empty_library():
    library, names = build_cluster_library([], [], threshold=0.5)
    assert names == {} and not library.people
