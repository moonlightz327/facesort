"""SQLite embedding cache. Key = (absolute path, mtime_ns, size)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import numpy as np

from .models import Face, PhotoAnalysis

_SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    path     TEXT NOT NULL,
    mtime_ns INTEGER NOT NULL,
    size     INTEGER NOT NULL,
    width    INTEGER NOT NULL,
    height   INTEGER NOT NULL,
    UNIQUE(path, mtime_ns, size)
);
CREATE TABLE IF NOT EXISTS faces (
    photo_id  INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    idx       INTEGER NOT NULL,
    x1 REAL NOT NULL, y1 REAL NOT NULL, x2 REAL NOT NULL, y2 REAL NOT NULL,
    det_score REAL NOT NULL,
    embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_faces_photo ON faces(photo_id);
"""


class EmbeddingCache:
    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(path: Path) -> tuple[str, int, int]:
        p = Path(path).resolve()
        st = p.stat()
        return (str(p), st.st_mtime_ns, st.st_size)

    def get(self, path: Path) -> Optional[PhotoAnalysis]:
        """Return cached analysis, or None on miss (file changed => miss)."""
        try:
            key, mtime_ns, size = self._key(path)
        except OSError:
            return None
        row = self._conn.execute(
            "SELECT id, width, height FROM photos WHERE path=? AND mtime_ns=? AND size=?",
            (key, mtime_ns, size),
        ).fetchone()
        if row is None:
            self.misses += 1
            return None
        photo_id, width, height = row
        faces = []
        for x1, y1, x2, y2, det_score, blob in self._conn.execute(
            "SELECT x1, y1, x2, y2, det_score, embedding FROM faces WHERE photo_id=? ORDER BY idx",
            (photo_id,),
        ):
            emb = np.frombuffer(blob, dtype=np.float32).copy()
            faces.append(Face(bbox=(x1, y1, x2, y2), embedding=emb, det_score=det_score))
        self.hits += 1
        return PhotoAnalysis(path=Path(path), width=width, height=height, faces=faces)

    def put(self, path: Path, analysis: PhotoAnalysis) -> None:
        key, mtime_ns, size = self._key(path)
        with self._conn:
            # Drop stale rows for the same path (older mtime/size).
            self._conn.execute("DELETE FROM photos WHERE path=?", (key,))
            cur = self._conn.execute(
                "INSERT INTO photos (path, mtime_ns, size, width, height) VALUES (?,?,?,?,?)",
                (key, mtime_ns, size, analysis.width, analysis.height),
            )
            photo_id = cur.lastrowid
            for idx, f in enumerate(analysis.faces):
                emb = np.asarray(f.embedding, dtype=np.float32)
                self._conn.execute(
                    "INSERT INTO faces (photo_id, idx, x1, y1, x2, y2, det_score, embedding)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (photo_id, idx, *[float(v) for v in f.bbox], float(f.det_score),
                     emb.tobytes()),
                )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "EmbeddingCache":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
