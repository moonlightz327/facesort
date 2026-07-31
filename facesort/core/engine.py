"""FaceEngine: insightface buffalo_l (SCRFD detection + ArcFace embedding).
Models are lazily loaded on first use; the rest of the codebase talks to this
class only through PhotoAnalysis/Face dataclasses.

`analyze`/`analyze_array` are safe to call from several threads once the engine
is loaded: onnxruntime sessions are thread-safe, and `_ensure_loaded` runs one
warm-up inference so insightface's internal anchor cache is populated before any
worker touches it.

Inference runs on Apple's Neural Engine / GPU via CoreML where that exists, and
on the CPU everywhere else. Measured on an M-series Mac with a 24MP six-face
frame: 515ms/photo on CPU, 61ms on CoreML — 8.4x, and identical results
(embeddings agree to cosine 0.9998, bounding boxes and detection scores are
bit-identical). It is by far the largest speedup available to this app, because
detection and embedding are ~85% of the wall clock and everything else in the
analyze path is already native code."""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .imageio import load_image_bgr_scaled
from .models import Face, PhotoAnalysis

# Compiling the ONNX graphs for CoreML takes ~10s. Cached on disk it drops to
# ~0.4s, which is quicker than the CPU provider's own startup — so the
# acceleration costs one slow first launch and nothing after that.
_COREML_CACHE_DIRNAME = "coreml_cache"


def coreml_available() -> bool:
    """True on Apple Silicon with a working CoreML execution provider."""
    if sys.platform != "darwin":
        return False
    try:
        import onnxruntime as ort
        return "CoreMLExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


def _coreml_cache_dir() -> Optional[str]:
    from .modelzoo import model_root
    try:
        d = model_root() / _COREML_CACHE_DIRNAME
        d.mkdir(parents=True, exist_ok=True)
        return str(d)
    except OSError:
        return None  # no cache: still correct, just a slow load every launch


class FaceEngine:
    def __init__(self, det_size: tuple[int, int] = (640, 640), ctx_id: int = 0,
                 use_gpu: bool = True):
        self.det_size = det_size
        self.ctx_id = ctx_id
        # Opt-out rather than opt-in: the fallback below already covers a
        # machine where CoreML misbehaves, so the fast path is the default and
        # this exists for the user who hits something we did not anticipate.
        self.use_gpu = use_gpu
        self.provider: Optional[str] = None  # which one actually loaded
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

            self._app = self._build_app(on_model_progress)
            # Terminal event: without it the UI's model panel never clears and
            # covers the analyze progress bar for the rest of the run.
            if on_model_progress:
                on_model_progress({"phase": "done"})
        return self._app

    def _build_app(self, on_model_progress: Optional[Callable[[dict], None]] = None):
        """Build the insightface app on the fastest provider that works.

        CoreML is tried first and the CPU is the fallback, not a second opinion:
        if anything about the accelerated path fails — an old macOS, a driver
        quirk, a model op CoreML will not take — the run continues on the CPU
        rather than failing. A photographer waiting on a shoot should never see
        a hardware-acceleration error."""
        # Imported here so that importing facesort never requires insightface
        # (matcher/organizer/templates/cache stay engine-free).
        from insightface.app import FaceAnalysis

        attempts: list[tuple[str, list[str], Optional[list[dict]]]] = []
        if self.use_gpu and coreml_available():
            cache = _coreml_cache_dir()
            attempts.append((
                "CoreML",
                ["CoreMLExecutionProvider", "CPUExecutionProvider"],
                [{"ModelCacheDirectory": cache} if cache else {}, {}],
            ))
        attempts.append(("CPU", ["CPUExecutionProvider"], None))

        last_error: Optional[Exception] = None
        for label, providers, options in attempts:
            if label == "CoreML" and on_model_progress:
                # The first launch compiles the graphs for the Neural Engine,
                # which is slow enough to look like a hang if unannounced.
                on_model_progress({"phase": "load", "percent": 100.0,
                                   "detail": "正在为 Apple 芯片优化识别模型（首次较慢，之后会很快）…"})
            try:
                kwargs = {"providers": providers}
                if options is not None:
                    kwargs["provider_options"] = options
                app = FaceAnalysis(name="buffalo_l",
                                   allowed_modules=["detection", "recognition"],
                                   **kwargs)
                app.prepare(ctx_id=self.ctx_id, det_size=self.det_size)
                # One dummy pass populates SCRFD's anchor-center cache while we
                # are still single-threaded, so parallel workers only ever read
                # it — and it forces any lazy provider setup to happen here,
                # where the fallback below can still catch it.
                app.get(np.zeros((self.det_size[1], self.det_size[0], 3), dtype=np.uint8))
                self.provider = label
                return app
            except Exception as e:  # noqa: BLE001 - deliberate fallback
                last_error = e
                continue
        raise last_error if last_error else RuntimeError("无法加载识别模型")

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
