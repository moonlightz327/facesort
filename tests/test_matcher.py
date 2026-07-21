import math

import numpy as np
import pytest

from facesort.core.matcher import (
    CENTER_SIGMA,
    Matcher,
    SampleLibrary,
    cosine_similarity,
    subject_score,
)
from facesort.core.models import Config, ConfigError, Face, PhotoAnalysis, SubjectWeights

from conftest import unit, vec_with_sim


def make_library(**people_embeddings) -> SampleLibrary:
    lib = SampleLibrary()
    for person, embs in people_embeddings.items():
        for e in embs:
            lib.add(person, e)
    return lib


def face_at(x1, y1, x2, y2, emb) -> Face:
    return Face(bbox=(x1, y1, x2, y2), embedding=emb)


def base_config(**kw) -> Config:
    from pathlib import Path

    defaults = dict(samples_dir=Path("s"), input_dir=Path("i"), output_dir=Path("o"))
    defaults.update(kw)
    return Config(**defaults)


class TestMatchFace:
    def test_above_threshold_matches(self):
        lib = make_library(A=[unit(0)], B=[unit(1)])
        m = Matcher(lib, threshold=0.40)
        face = face_at(0, 0, 100, 100, vec_with_sim(unit(0), 0.75, 2))
        result = m.match_face(face)
        assert result.person == "A"
        assert result.similarity == pytest.approx(0.75, abs=1e-5)
        assert not result.ambiguous

    def test_below_threshold_no_match(self):
        lib = make_library(A=[unit(0)])
        m = Matcher(lib, threshold=0.40)
        face = face_at(0, 0, 100, 100, vec_with_sim(unit(0), 0.35, 2))
        result = m.match_face(face)
        assert result.person is None
        assert result.similarity == pytest.approx(0.35, abs=1e-5)

    def test_exact_threshold_matches(self):
        lib = make_library(A=[unit(0)])
        m = Matcher(lib, threshold=0.40)
        result = m.match_face(face_at(0, 0, 10, 10, vec_with_sim(unit(0), 0.40, 2)))
        assert result.person == "A"

    def test_max_over_samples_beats_bad_sample(self):
        # Person A has one good and one bad sample; max wins (P1 #13 semantics)
        good = unit(0)
        bad = unit(3)
        lib = make_library(A=[bad, good], B=[unit(1)])
        m = Matcher(lib, threshold=0.40)
        result = m.match_face(face_at(0, 0, 10, 10, vec_with_sim(good, 0.8, 2)))
        assert result.person == "A"
        assert result.similarity == pytest.approx(0.8, abs=1e-5)

    def test_ambiguous_when_top2_close_and_both_above_threshold(self):
        # Face has sim 0.60 to A and 0.58 to B -> ambiguous (edge #4)
        e = (0.60 * unit(0) + 0.58 * unit(1)).astype(np.float32)
        e = e / np.linalg.norm(e)
        # cosines are proportional after normalization; compute exact
        lib = make_library(A=[unit(0)], B=[unit(1)])
        m = Matcher(lib, threshold=0.40, ambiguity_margin=0.05)
        result = m.match_face(face_at(0, 0, 10, 10, e))
        assert result.person == "A"
        assert result.ambiguous
        assert result.second_person == "B"

    def test_not_ambiguous_when_gap_large(self):
        e = (0.70 * unit(0) + 0.45 * unit(1)).astype(np.float32)
        lib = make_library(A=[unit(0)], B=[unit(1)])
        m = Matcher(lib, threshold=0.40, ambiguity_margin=0.05)
        result = m.match_face(face_at(0, 0, 10, 10, e))
        assert result.person == "A"
        assert not result.ambiguous

    def test_not_ambiguous_when_second_below_threshold(self):
        # top=0.42, second=0.39: close but second under threshold -> not ambiguous
        v = (0.42 * unit(0) + 0.39 * unit(1)).astype(np.float32)
        v = v + math.sqrt(max(0.0, 1 - float(np.dot(v, v)))) * unit(2)
        lib = make_library(A=[unit(0)], B=[unit(1)])
        m = Matcher(lib, threshold=0.40, ambiguity_margin=0.05)
        result = m.match_face(face_at(0, 0, 10, 10, v))
        assert result.person == "A"
        assert result.similarity == pytest.approx(0.42, abs=1e-4)
        assert result.second_similarity == pytest.approx(0.39, abs=1e-4)
        assert not result.ambiguous

    def test_empty_library_rejected(self):
        with pytest.raises(ConfigError):
            Matcher(SampleLibrary())


class TestSubjectScore:
    W = SubjectWeights(area=0.45, center=0.25, sim=0.30)

    def test_centered_max_area_face_scores_full_area_and_center(self):
        # Face centered in a 1000x1000 image, is the largest face
        f = face_at(400, 400, 600, 600, unit(0))
        score = subject_score(f, 1.0, 1000, 1000, f.area, self.W)
        # area=1, center dist=0 -> gauss=1, sim clamped to 1
        assert score == pytest.approx(0.45 * 1 + 0.25 * 1 + 0.30 * 1)

    def test_formula_exact(self):
        # 1000x800 image; face bbox (100,100,300,300): area 200*200
        f = face_at(100, 100, 300, 300, unit(0))
        max_area = 400 * 400
        sim = 0.62
        score = subject_score(f, sim, 1000, 800, max_area, self.W)
        area_score = (200 * 200) / max_area
        cx, cy = 200, 200
        dx = (cx - 500) / 500
        dy = (cy - 400) / 400
        dist = math.hypot(dx, dy) / math.sqrt(2)
        center_score = math.exp(-(dist**2) / (2 * CENTER_SIGMA**2))
        expected = 0.45 * area_score + 0.25 * center_score + 0.30 * sim
        assert score == pytest.approx(expected, rel=1e-9)

    def test_gaussian_decay_not_linear(self):
        # At normalized dist d the linear score would be 1-d; gaussian is softer
        # near center: at 1/3 offset the score stays high.
        f_third = face_at(0, 0, 10, 10, unit(0))  # center (5,5)
        # Build image so face center is at 1/3 offset from center on x only
        # image 600x600 -> center 300; face center at 400 => dx=100/300
        f = face_at(395, 295, 405, 305, unit(0))
        score_center_only = subject_score(f, 0.0, 600, 600, f.area, SubjectWeights(0, 1, 0))
        dx = (400 - 300) / 300
        d = math.hypot(dx, 0) / math.sqrt(2)
        assert score_center_only == pytest.approx(math.exp(-(d**2) / (2 * CENTER_SIGMA**2)))
        assert score_center_only > 1 - d  # softer than linear falloff

    def test_similarity_clamped_to_0_1(self):
        f = face_at(0, 0, 10, 10, unit(0))
        s_neg = subject_score(f, -0.5, 100, 100, f.area, SubjectWeights(0, 0, 1))
        assert s_neg == 0.0

    def test_weights_override(self):
        f = face_at(45, 45, 55, 55, unit(0))
        w = SubjectWeights(area=1.0, center=0.0, sim=0.0)
        assert subject_score(f, 0.5, 100, 100, f.area * 2, w) == pytest.approx(0.5)


class TestMatchPhoto:
    def test_min_face_filter(self):
        lib = make_library(A=[unit(0)])
        m = Matcher(lib, threshold=0.40)
        big = face_at(0, 0, 100, 100, vec_with_sim(unit(0), 0.8, 2))
        small = face_at(0, 0, 30, 30, vec_with_sim(unit(0), 0.9, 3))  # 30px < 40
        analysis = PhotoAnalysis(path=__import__("pathlib").Path("p.jpg"), width=500,
                                 height=500, faces=[big, small])
        outcome = m.match_photo(analysis, base_config(min_face=40))
        assert len(outcome.matches) == 1
        assert outcome.ignored_small_faces == 1

    def test_all_faces_too_small_is_no_face(self):
        lib = make_library(A=[unit(0)])
        m = Matcher(lib, threshold=0.40)
        small = face_at(0, 0, 20, 20, vec_with_sim(unit(0), 0.9, 2))
        analysis = PhotoAnalysis(path=__import__("pathlib").Path("p.jpg"), width=500,
                                 height=500, faces=[small])
        outcome = m.match_photo(analysis, base_config(min_face=40))
        assert outcome.matches == []
        assert outcome.ignored_small_faces == 1

    def test_primary_only_among_matched(self):
        """A big centered unmatched face must not out-score a matched face
        (SPEC §5: only matched faces compete)."""
        lib = make_library(A=[unit(0)])
        m = Matcher(lib, threshold=0.40)
        # Center: huge unmatched stranger; side: smaller matched A
        stranger = face_at(300, 300, 700, 700, vec_with_sim(unit(0), 0.1, 2))
        matched = face_at(50, 50, 200, 200, vec_with_sim(unit(0), 0.7, 3))
        analysis = PhotoAnalysis(path=__import__("pathlib").Path("p.jpg"), width=1000,
                                 height=1000, faces=[stranger, matched])
        outcome = m.match_photo(analysis, base_config())
        matched_faces = outcome.matched
        assert [mm.person for mm in matched_faces] == ["A"]
        assert matched_faces[0].subject_score > 0
        # Area score uses max area over ALL kept faces, so matched face area
        # is relative to the stranger's larger box
        assert matched_faces[0].subject_score < 1.0


def test_cosine_similarity_helper():
    assert cosine_similarity(unit(0), unit(0)) == pytest.approx(1.0)
    assert cosine_similarity(unit(0), unit(1)) == pytest.approx(0.0)
    assert cosine_similarity(unit(0) * 5, unit(0) * 3) == pytest.approx(1.0)  # normalizes
