"""Thumbnail generation for the web UI.

These guard the property that made the preview usable on a big shoot: the UI
pulls thumbnails for what it draws, and each one decodes at a reduced scale
instead of unpacking a 24MP original."""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from facesort.gui import thumbs


def _jpeg(path, size=(4000, 3000), color=(120, 60, 200)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="JPEG", quality=80)
    return path


def _decode(uri: str) -> Image.Image:
    assert uri.startswith("data:image/jpeg;base64,")
    raw = base64.b64decode(uri.split(",", 1)[1])
    return Image.open(io.BytesIO(raw))


@pytest.fixture(autouse=True)
def _clear_cache():
    thumbs._CACHE.clear()
    thumbs._BIG_CACHE.clear()
    yield
    thumbs._CACHE.clear()
    thumbs._BIG_CACHE.clear()


def test_thumbnail_is_bounded_by_requested_size(tmp_path):
    im = _decode(thumbs.data_uri(_jpeg(tmp_path / "a.jpg"), size=200))
    assert max(im.size) == 200
    assert im.size == (200, 150)  # aspect preserved


def test_large_preview_is_bigger_than_a_grid_thumb(tmp_path):
    p = _jpeg(tmp_path / "a.jpg")
    assert max(_decode(thumbs.data_uri(p, size=1600)).size) == 1600


def test_decodes_at_reduced_scale(tmp_path, monkeypatch):
    """The draft pass is the whole speedup; assert it is actually requested."""
    seen = []
    real = thumbs._imageio.apply_draft

    def spy(im, max_side):
        seen.append(max_side)
        return real(im, max_side)

    monkeypatch.setattr(thumbs._imageio, "apply_draft", spy)
    thumbs.data_uri(_jpeg(tmp_path / "a.jpg"), size=200)
    assert seen == [200]


def test_face_crop_decodes_full_size(tmp_path, monkeypatch):
    """`box` is in original-image pixels, so a crop must not be scaled under it."""
    seen = []
    monkeypatch.setattr(thumbs._imageio, "apply_draft",
                        lambda im, max_side: seen.append(max_side))
    thumbs.data_uri(_jpeg(tmp_path / "a.jpg"), size=120, box=(100, 100, 500, 500))
    assert seen == [None]


def test_unreadable_file_returns_none(tmp_path):
    bad = tmp_path / "broken.jpg"
    bad.write_bytes(b"not an image")
    assert thumbs.data_uri(bad, size=200) is None


def test_many_covers_every_path_and_caches(tmp_path):
    paths = [_jpeg(tmp_path / f"{i}.jpg", size=(800, 600)) for i in range(5)]
    out = thumbs.many(paths, size=100, workers=2)
    assert set(out) == {str(p) for p in paths}
    assert all(v and v.startswith("data:image/jpeg") for v in out.values())

    # Second pass is served from cache: no decoding at all.
    hits = 0

    def boom(*a, **kw):
        nonlocal hits
        hits += 1
        raise AssertionError("cached thumbnails must not be re-decoded")

    import PIL.Image as _pil
    orig_open = _pil.open
    try:
        _pil.open = boom
        again = thumbs.many(paths, size=100, workers=2)
    finally:
        _pil.open = orig_open
    assert again == out
    assert hits == 0


def test_grid_cache_evicts_oldest(tmp_path, monkeypatch):
    monkeypatch.setattr(thumbs, "_MAX_CACHE", 2)
    for i in range(4):
        thumbs.data_uri(_jpeg(tmp_path / f"{i}.jpg", size=(400, 300)), size=64)
    assert len(thumbs._CACHE) == 2


def test_big_previews_are_capped_separately(tmp_path, monkeypatch):
    """Full-screen previews are ~300KB each; only a few are worth holding."""
    monkeypatch.setattr(thumbs, "_MAX_BIG_CACHE", 2)
    for i in range(4):
        thumbs.data_uri(_jpeg(tmp_path / f"{i}.jpg", size=(1200, 900)), size=800)
    assert len(thumbs._BIG_CACHE) == 2
    assert not thumbs._CACHE
