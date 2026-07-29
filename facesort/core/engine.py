"""FaceEngine: insightface buffalo_l (SCRFD detection + ArcFace embedding).
Models are lazily loaded on first use; the rest of the codebase talks to this
class only through PhotoAnalysis/Face dataclasses.

`analyze`/`analyze_array` are safe to call from several threads once the engine
is loaded: onnxruntime sessions are thread-safe, and `_ensure_loaded` runs one
warm-up inference so insightface's internal anchor cache is populated before any
worker touches it."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .imageio import load_image_bgr
from .models import Face, PhotoAnalysis


class FaceEngine:
    def __init__(self, det_size: tuple[int, int] = (640, 640), ctx_id: int = 0):
        self.det_size = det_size
        self.ctx_id = ctx_id
        self._app = None
        self._load_lock = threading.Lock()

    def _ensure_loaded(self, on_model_progress: Optional[Callable[[dict], None]] = None):
        if self._app is not None:
            return self._app
        with self._load_lock:
            if self._app is not None:
                return self._app
            # Provision the model ourselves rather than letting insightface hit
            # github.com directly — that download has no timeout and strands the
            # user on an unreachable network.
            from .modelzoo import ensure_model

            ensure_model(on_progress=on_model_progress)

            # Imported here so that importing facesort never requires insightface
            # (matcher/organizer/templates/cache stay engine-free).
            from insightface.app import FaceAnalysis

            app = FaceAnalysis(
                name="buffalo_l",
                allowed_modules=["detection", "recognition"],
                providers=["CPUExecutionProvider"],
            )
            app.prepare(ctx_id=self.ctx_id, det_size=self.det_size)
            # One dummy pass populates SCRFD's anchor-center cache while we are
            # still single-threaded, so parallel workers only ever read it.
            try:
                app.get(np.zeros((self.det_size[1], self.det_size[0], 3), dtype=np.uint8))
            except Exception:
                pass
            self._app = app
        return self._app

    def analyze(self, path: Path) -> PhotoAnalysis:
        """Detect + embed all faces in one image. Raises ImageReadError for
        unreadable files."""
        img = load_image_bgr(Path(path))
        return self.analyze_array(img, path=Path(path))

    def analyze_array(self, img_bgr: np.ndarray, path: Path) -> PhotoAnalysis:
        app = self._ensure_loaded()
        h, w = img_bgr.shape[:2]
        faces = []
        for f in app.get(img_bgr):
            emb = getattr(f, "normed_embedding", None)
            if emb is None:
                emb = f.embedding / np.linalg.norm(f.embedding)
            x1, y1, x2, y2 = [float(v) for v in f.bbox]
            faces.append(Face(
                bbox=(x1, y1, x2, y2),
                embedding=np.asarray(emb, dtype=np.float32),
                det_score=float(getattr(f, "det_score", 1.0)),
            ))
        return PhotoAnalysis(path=path, width=w, height=h, faces=faces)
