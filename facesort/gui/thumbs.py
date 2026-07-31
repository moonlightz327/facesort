"""Thumbnail generation as base64 data URIs for the web UI.

Two things matter here, both learned from 5000-photo shoots:

  * **Decode scaled.** A grid thumbnail is 200px; fully decoding a 6000x4000
    JPEG to get there costs ~10x more than asking libjpeg for a 1/8-scale DCT
    pass. `core.imageio` already does this for analysis; the same trick applies
    verbatim to thumbnails (98ms -> 31ms per photo measured there).
  * **Never generate more than the page shows.** Building one thumbnail per plan
    item up front meant the preview of a 5000-photo shoot decoded 5000 originals
    before the first pixel appeared. The UI now asks for the thumbnails it is
    about to draw, in batches, through `many()`.

Caches are split by purpose: hundreds of small grid thumbs are worth keeping,
a handful of full-screen previews (~300KB each) are not.
"""

from __future__ import annotations

import base64
import io
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Iterable, Optional

from PIL import Image, ImageOps

# imageio registers the HEIF opener on import; keep that side effect.
from ..core import imageio as _imageio

# Grid thumbnails: small, reused constantly while scrolling.
_CACHE: "OrderedDict[tuple, str]" = OrderedDict()
_MAX_CACHE = 4000
# Full-screen previews: big, viewed one at a time. Keeping a few makes
# arrow-key paging through a group feel instant without holding 100s of MB.
_BIG_CACHE: "OrderedDict[tuple, str]" = OrderedDict()
_MAX_BIG_CACHE = 12
# Above this, a request counts as a "big" preview rather than a grid thumb.
_BIG_SIZE = 400

_LOCK = Lock()


def _key(path: Path, box: Optional[tuple], size: int) -> tuple:
    try:
        st = path.stat()
        return (str(path), st.st_mtime_ns, st.st_size, box, size)
    except OSError:
        return (str(path), 0, 0, box, size)


def _cache_for(size: int) -> tuple["OrderedDict[tuple, str]", int]:
    return (_BIG_CACHE, _MAX_BIG_CACHE) if size > _BIG_SIZE else (_CACHE, _MAX_CACHE)


def _cache_get(size: int, key: tuple) -> Optional[str]:
    cache, _ = _cache_for(size)
    with _LOCK:
        hit = cache.get(key)
        if hit is not None:
            cache.move_to_end(key)
        return hit


def _cache_put(size: int, key: tuple, uri: str) -> None:
    cache, limit = _cache_for(size)
    with _LOCK:
        cache[key] = uri
        cache.move_to_end(key)
        while len(cache) > limit:
            cache.popitem(last=False)


def _encode(im: Image.Image, size: int, box, pad: float, quality: int) -> str:
    if box is not None:
        x1, y1, x2, y2 = box
        bw, bh = x2 - x1, y2 - y1
        x1 = max(0, x1 - bw * pad); y1 = max(0, y1 - bh * pad)
        x2 = min(im.width, x2 + bw * pad); y2 = min(im.height, y2 + bh * pad)
        im = im.crop((int(x1), int(y1), int(x2), int(y2)))
    im.thumbnail((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def data_uri(
    path: Path,
    size: int = 240,
    box: Optional[tuple[float, float, float, float]] = None,
    pad: float = 0.35,
    quality: int = 82,
) -> Optional[str]:
    """Return a `data:image/jpeg;base64,...` thumbnail, or None if unreadable.

    `box` (x1,y1,x2,y2) crops to a face region with `pad` margin. RAW files use
    their embedded preview. The source is decoded at the smallest scale that
    still covers `size` (or the crop), so this stays cheap on 24MP originals."""
    path = Path(path)
    k = _key(path, box, size)
    hit = _cache_get(size, k)
    if hit is not None:
        return hit
    # `box` arrives in full-resolution pixels (that is the contract everywhere
    # outside core.imageio), so a crop decodes at full size to keep the
    # coordinates valid. Only the uncropped case — the grid, the lightbox, the
    # thousands-of-photos case — takes the scaled-decode fast path.
    decode_side = None if box is not None else size
    try:
        if _imageio.is_raw_file(path):
            bgr = _imageio.load_image_bgr(path, max_side=decode_side)
            im = Image.fromarray(bgr[:, :, ::-1])  # BGR -> RGB
        else:
            with Image.open(path) as opened:
                _imageio.apply_draft(opened, decode_side)
                im = ImageOps.exif_transpose(opened).convert("RGB")
        uri = _encode(im, size, box, pad, quality)
    except Exception:
        return None
    _cache_put(size, k, uri)
    return uri


def many(
    paths: Iterable[Path],
    size: int = 200,
    workers: int = 0,
) -> dict[str, Optional[str]]:
    """Generate thumbnails for `paths` in parallel, keyed by the path string.

    Decoding releases the GIL, so this scales with the same small pool the
    analyze stage uses. Cache hits are served without touching the pool."""
    from ..core.parallel import map_values

    paths = [Path(p) for p in paths]
    todo: list[Path] = []
    out: dict[str, Optional[str]] = {}
    for p in paths:
        hit = _cache_get(size, _key(p, None, size))
        if hit is not None:
            out[str(p)] = hit
        else:
            todo.append(p)
    if todo:
        for p, uri in zip(todo, map_values(lambda q: data_uri(q, size=size), todo,
                                           workers=workers)):
            out[str(p)] = uri
    return out
