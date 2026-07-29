"""Reduced-size decoding must stay invisible to the rest of the pipeline.

Detection runs at 640x640 whatever the input size, so decoding a 24MP JPEG at
half size is nearly free. The contract that makes it safe: coordinates handed
back are always in ORIGINAL image pixels, so min_face, subject scoring and the
GUI's face crops keep working in the units they already assume."""

import numpy as np
import pytest
from PIL import Image

from facesort.core.engine import FaceEngine
from facesort.core.imageio import load_image_bgr, load_image_bgr_scaled
from facesort.core.models import Face, PhotoAnalysis


def _jpeg(tmp_path, size=(4000, 3000), name="big.jpg"):
    p = tmp_path / name
    arr = np.random.randint(0, 255, (size[1], size[0], 3), dtype=np.uint8)
    Image.fromarray(arr).save(p, quality=80)
    return p


def test_no_max_side_decodes_full_size(tmp_path):
    p = _jpeg(tmp_path)
    arr, scale = load_image_bgr_scaled(p, None)
    assert (arr.shape[1], arr.shape[0]) == (4000, 3000)
    assert scale == 1.0


def test_max_side_halves_a_large_jpeg(tmp_path):
    p = _jpeg(tmp_path)
    arr, scale = load_image_bgr_scaled(p, 1400)
    # libjpeg scales by powers of two; 4000x3000 -> 2000x1500 keeps both axes
    # >= 1400. (This is why the default is 1400 and not 1600: at 1600 the 3000px
    # axis would fall short and a very common 12MP file would not shrink at all.)
    assert (arr.shape[1], arr.shape[0]) == (2000, 1500)
    assert scale == pytest.approx(2.0)


def test_default_1400_shrinks_common_camera_sizes(tmp_path):
    for w, h, expect in ((6000, 4000, (3000, 2000)),   # 24MP
                         (5472, 3648, (2736, 1824)),   # 20MP
                         (4000, 3000, (2000, 1500))):  # 12MP
        p = _jpeg(tmp_path, size=(w, h), name=f"{w}x{h}.jpg")
        arr, scale = load_image_bgr_scaled(p, 1400)
        assert (arr.shape[1], arr.shape[0]) == expect, f"{w}x{h}"
        assert scale == pytest.approx(2.0)


def test_never_reduces_past_half_at_the_default(tmp_path):
    """1/4 measurably hurts embeddings (0.988 vs 0.998 cosine), so the default
    must not reach it for any realistic photo size."""
    p = _jpeg(tmp_path, size=(6000, 4000), name="huge.jpg")
    arr, scale = load_image_bgr_scaled(p, 1400)
    assert scale == pytest.approx(2.0)


def test_scale_maps_decoded_coords_back_to_the_original(tmp_path):
    p = _jpeg(tmp_path)
    arr, scale = load_image_bgr_scaled(p, 1400)
    assert arr.shape[1] * scale == pytest.approx(4000)
    assert arr.shape[0] * scale == pytest.approx(3000)


def test_small_image_is_never_upscaled_and_scale_stays_one(tmp_path):
    p = _jpeg(tmp_path, size=(800, 600), name="small.jpg")
    arr, scale = load_image_bgr_scaled(p, 1400)
    assert (arr.shape[1], arr.shape[0]) == (800, 600)
    assert scale == 1.0


def test_png_ignores_max_side(tmp_path):
    """draft() is a JPEG feature; other formats must still decode correctly."""
    p = tmp_path / "a.png"
    Image.fromarray(np.zeros((2000, 2000, 3), dtype=np.uint8)).save(p)
    arr, scale = load_image_bgr_scaled(p, 500)
    assert (arr.shape[1], arr.shape[0]) == (2000, 2000)
    assert scale == 1.0


def test_load_image_bgr_keeps_its_single_return_value(tmp_path):
    p = _jpeg(tmp_path, size=(1000, 800))
    arr = load_image_bgr(p)
    assert arr.ndim == 3 and arr.shape[2] == 3


class FakeApp:
    """Stands in for insightface: reports one face at fixed decoded coords."""

    def __init__(self, bbox=(100.0, 50.0, 200.0, 150.0)):
        self.bbox = bbox
        self.seen_shape = None

    def get(self, img):
        self.seen_shape = img.shape[:2]

        class F:
            pass

        f = F()
        f.bbox = np.array(self.bbox, dtype=np.float32)
        f.normed_embedding = np.ones(512, dtype=np.float32) / np.sqrt(512)
        f.det_score = 0.9
        return [f]


def test_analyze_array_rescales_bbox_and_dimensions_to_original():
    engine = FaceEngine()
    engine._app = FakeApp()
    decoded = np.zeros((1500, 2000, 3), dtype=np.uint8)  # half of 4000x3000

    a = engine.analyze_array(decoded, path="x.jpg", scale=2.0)

    assert (a.width, a.height) == (4000, 3000)
    assert a.faces[0].bbox == (200.0, 100.0, 400.0, 300.0)
    # min_face compares against original pixels, so the face must measure 200.
    assert a.faces[0].min_side == 200.0


def test_scale_one_leaves_coordinates_untouched():
    engine = FaceEngine()
    engine._app = FakeApp()
    img = np.zeros((3000, 4000, 3), dtype=np.uint8)

    a = engine.analyze_array(img, path="x.jpg", scale=1.0)

    assert (a.width, a.height) == (4000, 3000)
    assert a.faces[0].bbox == (100.0, 50.0, 200.0, 150.0)


def test_analyze_reports_original_size_when_decoding_reduced(tmp_path):
    """End to end through the real decoder with a stubbed detector."""
    p = _jpeg(tmp_path)
    engine = FaceEngine()
    fake = FakeApp()
    engine._app = fake

    a = engine.analyze(p, max_side=1400)

    assert fake.seen_shape == (1500, 2000)      # detector saw the small copy
    assert (a.width, a.height) == (4000, 3000)  # caller sees the original
    assert a.faces[0].bbox == (200.0, 100.0, 400.0, 300.0)
