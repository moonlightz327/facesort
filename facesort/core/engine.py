"""FaceEngine: insightface buffalo_l (SCRFD detection + ArcFace embedding).
Models are lazily loaded on first use; the rest of the codebase talks to this
class only through PhotoAnalysis/Face dataclasses."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .imageio import load_image_bgr
from .models import Face, PhotoAnalysis


class FaceEngine:
    def __init__(self, det_size: tuple[int, int] = (640, 640), ctx_id: int = 0):
        self.det_size = det_size
        self.ctx_id = ctx_id
        self._app = None

    def _ensure_loaded(self):
        if self._app is None:
            # Imported here so that importing facesort never requires insightface
            # (matcher/organizer/templates/cache stay engine-free).
            from insightface.app import FaceAnalysis

            app = FaceAnalysis(
                name="buffalo_l",
                allowed_modules=["detection", "recognition"],
                providers=["CPUExecutionProvider"],
            )
            app.prepare(ctx_id=self.ctx_id, det_size=self.det_size)
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
