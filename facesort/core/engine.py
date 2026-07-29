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

from .imageio import load_image_bgr_scaled
from .models import Face, PhotoAnalysis


class FaceEngine:
    def __init__(self, det_size: tuple[int, int] = (640, 640), ctx_id: int = 0):
        self.det_size = det_size
        self.ctx_id = ctx_id
        self._app = None
        self._load_lock = threading.Lock()

    def _ensure_loaded(self, on_model_progress: Optional[Callable[[dict], None]] = None,
                       cancel: Optional[threading.Event] = None):
        if self._app is not None:
            return self._app
        with self._load_lock:
            if self._app is not None:
                return self._app
            # Provision the model ourselves rather than letting insightface hit
            # github.com directly — that download has no timeout and strands the
            # user on an unreachable network.
            from .modelzoo import ensure_model

            ensure_model(on_progress=on_model_progress, cancel=cancel)

            # Building the onnx sessions takes a couple of seconds; say so
            # instead of leaving the UI on a blank "preparing" state.
            if on_model_progress:
                on_model_progress({"phase": "load", "percent": 100.0,
                                   "detail": "正在加载识别模型…"})

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

    def analyze(self, path: Path, max_side: Optional[int] = None) -> PhotoAnalysis:
        """Detect + embed all faces in one image. Raises ImageReadError for
        unreadable files.

        `max_side` decodes large JPEGs at a reduced size (see imageio); results
        still come back in original-image pixels, so callers never need to know
        it happened."""
        path = Path(path)
        img, scale = load_image_bgr_scaled(path, max_side)
        return self.analyze_array(img, path=path, scale=scale)

    def analyze_array(self, img_bgr: np.ndarray, path: Path,
                      scale: float = 1.0) -> PhotoAnalysis:
        """`scale` maps coordinates in `img_bgr` back to the original image, so
        bboxes and dimensions stay in full-resolution pixels regardless of the
        size the image was decoded at. Keeps min_face, subject scoring and the
        GUI's face crops working in the units they already assume."""
        app = self._ensure_loaded()
        h, w = img_bgr.shape[:2]
        faces = []
        for f in app.get(img_bgr):
            emb = getattr(f, "normed_embedding", None)
            if emb is None:
                emb = f.embedding / np.linalg.norm(f.embedding)
            x1, y1, x2, y2 = [float(v) * scale for v in f.bbox]
            faces.append(Face(
                bbox=(x1, y1, x2, y2),
                embedding=np.asarray(emb, dtype=np.float32),
                det_score=float(getattr(f, "det_score", 1.0)),
            ))
        return PhotoAnalysis(path=path, width=round(w * scale),
                             height=round(h * scale), faces=faces)
