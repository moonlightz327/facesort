"""Sample-free clustering: group unknown faces into 人物1/人物2/… so a shoot can
be sorted with no reference photos. Pure logic (embeddings in, labels out); the
pipeline turns cluster centroids into a synthetic SampleLibrary and reuses the
normal match/plan/execute path. No insightface."""

from __future__ import annotations

import numpy as np

from .matcher import SampleLibrary, _normalize


def greedy_cluster(embeddings: list[np.ndarray], threshold: float) -> list[int]:
    """Assign each embedding to a cluster by online centroid linkage: a face joins
    the most similar existing cluster if cosine similarity ≥ threshold, else starts
    a new one. Returns a cluster id per input embedding (order preserved).

    Order-dependent but stable and dependency-free; good enough for grouping a
    single shoot. Centroids are kept L2-normalized running means."""
    centroids: list[np.ndarray] = []
    counts: list[int] = []
    labels: list[int] = []
    for emb in embeddings:
        v = _normalize(emb)
        best, best_sim = -1, -1.0
        for i, c in enumerate(centroids):
            sim = float(np.dot(v, c))
            if sim > best_sim:
                best, best_sim = i, sim
        if best >= 0 and best_sim >= threshold:
            n = counts[best]
            merged = (centroids[best] * n + v) / (n + 1)
            centroids[best] = _normalize(merged)
            counts[best] = n + 1
            labels.append(best)
        else:
            centroids.append(v)
            counts.append(1)
            labels.append(len(centroids) - 1)
    return labels


def merge_similar(
    embeddings: list[np.ndarray],
    labels: list[int],
    threshold: float,
    max_rounds: int = 10000,
) -> list[int]:
    """Repeatedly merge the two most similar clusters until none are within
    `threshold`. Returns relabelled cluster ids (surviving ids are reused).

    The greedy pass decides on the centroid *as it stands at that moment*, so
    one person can end up as two sizeable groups: an early face misses their own
    young cluster by a hair, starts a second one, and nothing ever compares the
    two again once both have settled. This does compare them, and by then the
    decision is easy — two settled centroids of one person sit around 0.6-0.95
    cosine while two different people sit near 0.0, a far wider margin than
    individual faces ever give.

    This is the half of the over-segmentation fix that saves real groups. It
    does *not* rescue the long tail of one-face clusters thrown off by blurry or
    profile detections — a single face averages to nothing better than itself,
    which is why it failed to join anything in the first place. Those are what
    `min_cluster_photos` is for."""
    members: dict[int, list[int]] = {}
    order: list[int] = []
    for idx, lab in enumerate(labels):
        if lab not in members:
            members[lab] = []
            order.append(lab)
        members[lab].append(idx)
    if len(order) < 2:
        return list(labels)

    normed = [_normalize(e) for e in embeddings]
    cents = np.vstack([
        _normalize(np.mean([normed[i] for i in members[k]], axis=0)) for k in order
    ])
    counts = np.array([len(members[k]) for k in order], dtype=np.float64)
    alive = np.ones(len(order), dtype=bool)
    parent = {k: k for k in order}

    for _ in range(max_rounds):
        sims = cents @ cents.T
        np.fill_diagonal(sims, -1.0)
        dead = ~alive
        sims[dead, :] = -1.0
        sims[:, dead] = -1.0
        flat = int(np.argmax(sims))
        i, j = divmod(flat, sims.shape[1])
        if sims[i, j] < threshold:
            break
        # Weighted so a 200-photo cluster is not dragged around by a stray face.
        cents[i] = _normalize((cents[i] * counts[i] + cents[j] * counts[j])
                              / (counts[i] + counts[j]))
        counts[i] += counts[j]
        alive[j] = False
        parent[order[j]] = order[i]

    def root(lab: int) -> int:
        while parent[lab] != lab:
            lab = parent[lab]
        return lab

    return [root(lab) for lab in labels]


def build_cluster_library(
    face_embeddings: list[np.ndarray],
    photo_of_face: list[int],
    threshold: float,
    name_prefix: str = "人物",
    min_cluster_photos: int = 1,
    merge: bool = True,
) -> tuple[SampleLibrary, dict[int, str]]:
    """Cluster faces, merge clusters that turn out to be the same person, drop
    clusters seen in fewer than `min_cluster_photos` distinct photos, then name
    the rest `人物1..N` ordered by photo count (desc).

    Dropping the small clusters is not the same as dropping their photos: the
    pipeline matches every face against the surviving centroids afterwards, so a
    face from a discarded cluster still lands in a real person's folder if it
    belongs there, and in _未识别 if it does not. That is the right home for the
    one-off blurry stranger in the background of a single frame — a folder of
    their own is not."""
    if not face_embeddings:
        return SampleLibrary(), {}
    labels = greedy_cluster(face_embeddings, threshold)
    if merge:
        labels = merge_similar(face_embeddings, labels, threshold)

    photos_per_cluster: dict[int, set[int]] = {}
    members: dict[int, list[np.ndarray]] = {}
    for emb, lab, photo in zip(face_embeddings, labels, photo_of_face):
        photos_per_cluster.setdefault(lab, set()).add(photo)
        members.setdefault(lab, []).append(_normalize(emb))

    kept = [c for c, photos in photos_per_cluster.items()
            if len(photos) >= min_cluster_photos]
    kept.sort(key=lambda c: (-len(photos_per_cluster[c]), c))

    library = SampleLibrary()
    names: dict[int, str] = {}
    for rank, cid in enumerate(kept, start=1):
        name = f"{name_prefix}{rank}"
        names[cid] = name
        centroid = _normalize(np.mean(members[cid], axis=0))
        library.add(name, centroid)
    return library, names
