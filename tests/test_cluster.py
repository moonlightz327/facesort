"""Sample-free clustering tests with fabricated embeddings of known geometry.
No insightface."""

from __future__ import annotations

import numpy as np

from facesort.core.cluster import build_cluster_library, greedy_cluster, merge_similar
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


# ---------- over-segmentation (6 people -> 100+ folders) ----------

def _person_faces(rng, base, n, lo=0.30, hi=0.85):
    """`n` faces of one person: each similar to `base` but not identical, the
    way real shots of one face vary across pose, focus and light. The spread is
    wide on purpose — a frontal and a profile of the same person really do land
    only ~0.3 apart, which is what makes naive clustering shatter them."""
    out = []
    for _ in range(n):
        noise = rng.normal(0, 1, 512).astype(np.float32)
        noise -= float(np.dot(noise, base)) * base       # orthogonalize
        noise /= np.linalg.norm(noise)
        sim = rng.uniform(lo, hi)
        v = sim * base + np.sqrt(1 - sim * sim) * noise
        out.append((v / np.linalg.norm(v)).astype(np.float32))
    return out


def _six_people(seed=0, per_person=40):
    rng = np.random.default_rng(seed)
    bases = []
    for _ in range(6):
        b = rng.normal(0, 1, 512).astype(np.float32)
        bases.append(b / np.linalg.norm(b))
    embs, photo = [], []
    for i, b in enumerate(bases):
        for e in _person_faces(rng, b, per_person):
            embs.append(e)
            photo.append(len(embs))  # each face in its own photo
    return embs, photo


def test_merge_pass_rejoins_one_person_split_into_two_groups():
    """The split the greedy pass makes and cannot undo: the same person as two
    settled clusters, each big enough to survive the small-cluster filter, so
    they would otherwise ship as two 人物N folders."""
    rng = np.random.default_rng(3)
    base = rng.normal(0, 1, 512).astype(np.float32)
    base /= np.linalg.norm(base)
    half_a = _person_faces(rng, base, 12)
    half_b = _person_faces(rng, base, 12)
    embs = half_a + half_b
    labels = [0] * 12 + [1] * 12  # what the greedy pass left behind

    assert len(set(merge_similar(embs, labels, 0.5))) == 1


def test_six_people_do_not_become_a_hundred_folders():
    """End to end on the reported case: 6 people, plenty of pose variation."""
    embs, photo = _six_people()

    raw = len(set(greedy_cluster(embs, threshold=0.5)))
    _library, names = build_cluster_library(embs, photo, threshold=0.5,
                                            min_cluster_photos=2)

    assert raw > 50, f"这组数据没有触发过度切分（{raw} 组），测试失去意义"
    assert 1 <= len(names) <= 8, f"分出了 {len(names)} 个人物分组，应接近 6"


def test_merge_keeps_genuinely_different_people_apart():
    a, b, c = unit(0), unit(1), unit(2)  # mutually orthogonal => sim 0
    embs = [a, a, b, b, c, c]
    labels = merge_similar(embs, greedy_cluster(embs, 0.5), 0.5)
    assert len(set(labels)) == 3


def test_merge_is_a_no_op_on_a_single_cluster():
    embs = [unit(0), vec_with_sim(unit(0), 0.9, 5)]
    labels = greedy_cluster(embs, 0.5)
    assert merge_similar(embs, labels, 0.5) == labels


def test_singleton_clusters_are_dropped_not_named():
    """One stranger in the background of one frame is not a 人物N folder."""
    a = unit(0)
    embs = [a, a, a] + [unit(i) for i in range(10, 25)]  # 15 one-off faces
    photo = list(range(len(embs)))
    _library, names = build_cluster_library(embs, photo, threshold=0.5,
                                            min_cluster_photos=2)
    assert list(names.values()) == ["人物1"]
