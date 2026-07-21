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


def build_cluster_library(
    face_embeddings: list[np.ndarray],
    photo_of_face: list[int],
    threshold: float,
    name_prefix: str = "人物",
    min_cluster_photos: int = 1,
) -> tuple[SampleLibrary, dict[int, str]]:
    """Cluster faces, drop clusters seen in fewer than `min_cluster_photos`
    distinct photos, then name the rest `人物1..N` ordered by photo count (desc).
    Returns (library of centroids, cluster_id -> name)."""
    if not face_embeddings:
        return SampleLibrary(), {}
    labels = greedy_cluster(face_embeddings, threshold)

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
