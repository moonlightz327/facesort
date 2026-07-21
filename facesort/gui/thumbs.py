"""Thumbnail generation as base64 data URIs for the web UI. Cached on
(path, mtime_ns, size) so a grid of hundreds of photos is cheap to redraw."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps

# imageio registers the HEIF opener on import; keep that side effect.
from ..core import imageio as _imageio

_CACHE: dict[tuple, str] = {}
_MAX_CACHE = 4000


def _key(path: Path, box: Optional[tuple], size: int) -> tuple:
    try:
        st = path.stat()
        return (str(path), st.st_mtime_ns, st.st_size, box, size)
    except OSError:
        return (str(path), 0, 0, box, size)


def _encode(im: Image.Image, size: int, box, pad: float) -> str:
    if box is not None:
        x1, y1, x2, y2 = box
        bw, bh = x2 - x1, y2 - y1
        x1 = max(0, x1 - bw * pad); y1 = max(0, y1 - bh * pad)
        x2 = min(im.width, x2 + bw * pad); y2 = min(im.height, y2 + bh * pad)
        im = im.crop((int(x1), int(y1), int(x2), int(y2)))
    im.thumbnail((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def data_uri(
    path: Path,
    size: int = 240,
    box: Optional[tuple[float, float, float, float]] = None,
    pad: float = 0.35,
) -> Optional[str]:
    """Return a `data:image/jpeg;base64,...` thumbnail, or None if unreadable.
    `box` (x1,y1,x2,y2) crops to a face region with `pad` margin. RAW files use
    their embedded preview."""
    path = Path(path)
    k = _key(path, box, size)
    hit = _CACHE.get(k)
    if hit is not None:
        return hit
    try:
        if _imageio.is_raw_file(path):
            bgr = _imageio.load_image_bgr(path)  # embedded preview
            im = Image.fromarray(bgr[:, :, ::-1])  # BGR -> RGB
        else:
            with Image.open(path) as opened:
                im = ImageOps.exif_transpose(opened).convert("RGB")
        uri = _encode(im, size, box, pad)
    except Exception:
        return None
    if len(_CACHE) < _MAX_CACHE:
        _CACHE[k] = uri
    return uri
