"""Image loading (JPEG/PNG/HEIC/TIFF/WebP + camera RAW) and EXIF datetime.
No insightface."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

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


def _load_raw_bgr(path: Path) -> np.ndarray:
    """Extract a RAW file's embedded preview (fast, full-size on modern cameras)
    for recognition; fall back to a downscaled full decode if there is none."""
    import rawpy

    try:
        with rawpy.imread(str(path)) as raw:
            try:
                thumb = raw.extract_thumb()
            except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
                thumb = None
            if thumb is not None and thumb.format == rawpy.ThumbFormat.JPEG:
                with Image.open(io.BytesIO(thumb.data)) as im:
                    im = ImageOps.exif_transpose(im)
                    arr = np.asarray(im.convert("RGB"))
            elif thumb is not None and thumb.format == rawpy.ThumbFormat.BITMAP:
                arr = np.asarray(Image.fromarray(thumb.data).convert("RGB"))
            else:
                arr = raw.postprocess(use_camera_wb=True, half_size=True)
    except Exception as e:
        raise ImageReadError(f"无法读取 RAW 图片 {path}: {e}") from e
    return arr[:, :, ::-1].copy()  # RGB -> BGR


def load_image_bgr(path: Path) -> np.ndarray:
    """Load any supported image as a BGR uint8 array (insightface convention),
    honoring EXIF orientation. Raises ImageReadError on corrupt files (edge #7)."""
    if is_raw_file(path):
        return _load_raw_bgr(path)
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            rgb = im.convert("RGB")
            arr = np.asarray(rgb)
    except Exception as e:  # PIL raises many types for truncated/corrupt files
        raise ImageReadError(f"无法读取图片 {path}: {e}") from e
    return arr[:, :, ::-1].copy()  # RGB -> BGR


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
