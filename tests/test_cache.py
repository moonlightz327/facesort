"""Embedding cache tests: key = (path, mtime_ns, size); hit/miss, invalidation,
embedding round-trip. No insightface."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from facesort.core.cache import EmbeddingCache
from facesort.core.models import Face, PhotoAnalysis


def _analysis(path: Path) -> PhotoAnalysis:
    emb = np.arange(512, dtype=np.float32) / 512.0
    face = Face(bbox=(1.0, 2.0, 3.0, 4.0), embedding=emb, det_score=0.99)
    return PhotoAnalysis(path=path, width=640, height=480, faces=[face])


def test_put_then_get_roundtrips_embedding(tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")
    with EmbeddingCache(tmp_path / "c.sqlite") as cache:
        analysis = _analysis(img)
        cache.put(img, analysis)
        got = cache.get(img)
    assert got is not None
    assert got.width == 640 and got.height == 480
    assert len(got.faces) == 1
    np.testing.assert_allclose(got.faces[0].embedding, analysis.faces[0].embedding)
    assert got.faces[0].bbox == (1.0, 2.0, 3.0, 4.0)


def test_miss_on_absent_file(tmp_path):
    with EmbeddingCache(tmp_path / "c.sqlite") as cache:
        assert cache.get(tmp_path / "nope.jpg") is None
        assert cache.misses == 0  # OSError path returns before counting


def test_hit_and_miss_counters(tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")
    with EmbeddingCache(tmp_path / "c.sqlite") as cache:
        assert cache.get(img) is None  # miss (not stored yet)
        assert cache.misses == 1
        cache.put(img, _analysis(img))
        assert cache.get(img) is not None
        assert cache.hits == 1


def test_invalidated_when_file_content_changes(tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"short")
    with EmbeddingCache(tmp_path / "c.sqlite") as cache:
        cache.put(img, _analysis(img))
        assert cache.get(img) is not None
        # Change size -> key changes -> miss.
        img.write_bytes(b"a much longer content than before")
        assert cache.get(img) is None


def test_invalidated_when_mtime_changes(tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"same-size")
    with EmbeddingCache(tmp_path / "c.sqlite") as cache:
        cache.put(img, _analysis(img))
        st = img.stat()
        # Same content/size but newer mtime -> miss.
        future = st.st_mtime + 100
        os.utime(img, (future, future))
        assert cache.get(img) is None


def test_persists_across_reopen(tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")
    db = tmp_path / "c.sqlite"
    with EmbeddingCache(db) as cache:
        cache.put(img, _analysis(img))
    with EmbeddingCache(db) as cache2:
        assert cache2.get(img) is not None


def test_no_face_photo_cached(tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")
    with EmbeddingCache(tmp_path / "c.sqlite") as cache:
        cache.put(img, PhotoAnalysis(path=img, width=10, height=10, faces=[]))
        got = cache.get(img)
    assert got is not None and got.faces == []
