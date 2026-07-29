"""Image loading (JPEG/PNG/HEIC/TIFF/WebP + camera RAW) and EXIF datetime.
No insightface.

Loading can decode at a reduced size (`max_side`). Detection runs at 640x640 no
matter how big the file is, so fully decoding a 24MP JPEG is mostly wasted work:
libjpeg can scale by 1/2, 1/4 or 1/8 during the DCT pass almost for free.
Measured on 6000x4000 shots: 98ms -> 31ms per photo, with detection completely
unaffected (it downscales to the same 640x640 either way) and recognition
embeddings drifting by <0.5% cosine.

Callers get the scale factor back so bounding boxes can be mapped to original
image coordinates - everything outside this module and the engine keeps working
in full-resolution pixels."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

STD_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".webp"}
# Common camera RAW formats. Recognition uses the embedded JPEG preview.
RAW_EXTS = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2",
            ".pef", ".srw", ".raw"}
IMAGE_EXTS = STD_IMAGE_EXTS | RAW_EXTS

EXIF_DATETIME_ORIGINAL = 36867  # DateTimeOriginal
EXIF_DATETIME = 306


class ImageReadError(Exception):
    pass


def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def is_raw_file(path: Path) -> bool:
    return path.suffix.lower() in RAW_EXTS


def _apply_draft(im: Image.Image, max_side: Optional[int]) -> None:
    """Ask libjpeg to decode at a reduced DCT scale (1/2, 1/4, 1/8).

    A no-op for non-JPEG formats and for images already smaller than `max_side`.
    PIL guarantees the result is still at least `max_side` on both axes, so a
    6000x4000 frame with max_side=1600 comes back as 3000x2000 rather than
    something too small to crop a usable face from."""
    if not max_side or max_side <= 0:
        return
    try:
        im.draft("RGB", (max_side, max_side))
    except Exception:
        pass  # format doesn't support it; full decode is still correct


def _load_raw_bgr(path: Path, max_side: Optional[int] = None) -> tuple[np.ndarray, float]:
    """Extract a RAW file's embedded preview (fast, full-size on modern cameras)
    for recognition; fall back to a downscaled full decode if there is none.

    Returns (bgr, scale) where scale maps decoded coords back to the preview's
    full size."""
    import rawpy

    try:
        with rawpy.imread(str(path)) as raw:
            try:
                thumb = raw.extract_thumb()
            except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
                thumb = None
            if thumb is not None and thumb.format == rawpy.ThumbFormat.JPEG:
                with Image.open(io.BytesIO(thumb.data)) as im:
                    full_w = im.width
                    _apply_draft(im, max_side)
                    decoded_w = im.width
                    im = ImageOps.exif_transpose(im)
                    arr = np.asarray(im.convert("RGB"))
                    scale = (full_w / decoded_w) if decoded_w else 1.0
                    return arr[:, :, ::-1].copy(), scale
            elif thumb is not None and thumb.format == rawpy.ThumbFormat.BITMAP:
                arr = np.asarray(Image.fromarray(thumb.data).convert("RGB"))
            else:
                arr = raw.postprocess(use_camera_wb=True, half_size=True)
    except Exception as e:
        raise ImageReadError(f"无法读取 RAW 图片 {path}: {e}") from e
    return arr[:, :, ::-1].copy(), 1.0  # RGB -> BGR


def load_image_bgr_scaled(
    path: Path, max_side: Optional[int] = None
) -> tuple[np.ndarray, float]:
    """Load an image as BGR, optionally decoding at reduced size.

    Returns `(bgr, scale)`; multiply coordinates measured on `bgr` by `scale` to
    get original-image pixels. `scale` is 1.0 whenever no reduction happened."""
    path = Path(path)
    if is_raw_file(path):
        return _load_raw_bgr(path, max_side)
    try:
        with Image.open(path) as im:
            # Measure before exif_transpose so a 90-degree rotation cannot swap
            # the axes out from under the ratio; draft scales both uniformly.
            full_w = im.width
            _apply_draft(im, max_side)
            decoded_w = im.width
            im = ImageOps.exif_transpose(im)
            rgb = im.convert("RGB")
            arr = np.asarray(rgb)
    except Exception as e:  # PIL raises many types for truncated/corrupt files
        raise ImageReadError(f"无法读取图片 {path}: {e}") from e
    scale = (full_w / decoded_w) if decoded_w else 1.0
    return arr[:, :, ::-1].copy(), scale  # RGB -> BGR


def load_image_bgr(path: Path, max_side: Optional[int] = None) -> np.ndarray:
    """Load any supported image as a BGR uint8 array (insightface convention),
    honoring EXIF orientation. Raises ImageReadError on corrupt files (edge #7)."""
    return load_image_bgr_scaled(path, max_side)[0]


def get_photo_datetime(path: Path) -> tuple[datetime, bool]:
    """(datetime, from_exif). EXIF DateTimeOriginal first; fall back to file
    mtime (edge #11)."""
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            raw = None
            try:
                raw = exif.get_ifd(0x8769).get(EXIF_DATETIME_ORIGINAL)  # Exif IFD
            except Exception:
                pass
            if not raw:
                raw = exif.get(EXIF_DATETIME_ORIGINAL) or exif.get(EXIF_DATETIME)
            if raw:
                return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S"), True
    except Exception:
        pass
    return datetime.fromtimestamp(path.stat().st_mtime), False
