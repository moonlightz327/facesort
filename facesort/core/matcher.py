"""Sample library matching + subject scoring. Pure logic, no insightface."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from .models import (
    Config,
    ConfigError,
    Face,
    FaceMatch,
    PhotoAnalysis,
    PhotoOutcome,
    SubjectWeights,
)

# Gaussian sigma for the center score: at 1/3 offset (rule of thirds) the score
# is still ~0.76 instead of the 0.67 a linear falloff would give.
CENTER_SIGMA = 0.45


def _normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


@dataclass
class SampleLibrary:
    """person -> (n_samples, 512) L2-normalized embedding matrix."""

    people: dict[str, np.ndarray] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def add(self, person: str, embedding: np.ndarray) -> None:
        emb = _normalize(embedding)[None, :]
        if person in self.people:
            self.people[person] = np.vstack([self.people[person], emb])
        else:
            self.people[person] = emb

    def validate(self) -> None:
        if not self.people:
            raise ConfigError("样本库为空：samples 目录下没有任何有效的人物样本")


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(_normalize(a), _normalize(b)))


def subject_score(
    face: Face,
    similarity: float,
    img_width: int,
    img_height: int,
    max_face_area: float,
    weights: SubjectWeights,
) -> float:
    """SPEC §5: score = w_area*面积分 + w_center*中心分(高斯衰减) + w_sim*相似度分."""
    area_score = face.area / max_face_area if max_face_area > 0 else 0.0

    cx, cy = face.center
    half_w, half_h = img_width / 2.0, img_height / 2.0
    dx = (cx - half_w) / half_w if half_w > 0 else 0.0
    dy = (cy - half_h) / half_h if half_h > 0 else 0.0
    # Normalized distance: 0 at center, 1 at image corner.
    dist = math.hypot(dx, dy) / math.sqrt(2.0)
    center_score = math.exp(-(dist ** 2) / (2.0 * CENTER_SIGMA ** 2))

    sim_score = max(0.0, min(1.0, similarity))

    return weights.area * area_score + weights.center * center_score + weights.sim * sim_score


class Matcher:
    def __init__(
        self,
        library: SampleLibrary,
        threshold: float = 0.40,
        ambiguity_margin: float = 0.05,
    ):
        library.validate()
        self.library = library
        self.threshold = threshold
        self.ambiguity_margin = ambiguity_margin

    def match_face(self, face: Face) -> FaceMatch:
        """Per-person similarity = max over that person's samples (robust to a
        bad sample). Best person wins if above threshold; top-2 within margin
        and both above threshold => ambiguous (edge case #4)."""
        emb = _normalize(face.embedding)
        scored: list[tuple[str, float]] = [
            (person, float(np.max(mat @ emb))) for person, mat in self.library.people.items()
        ]
        scored.sort(key=lambda t: t[1], reverse=True)

        best_person, best_sim = scored[0]
        second_person, second_sim = scored[1] if len(scored) > 1 else (None, 0.0)

        if best_sim < self.threshold:
            return FaceMatch(face=face, person=None, similarity=best_sim,
                             second_person=second_person, second_similarity=second_sim)

        ambiguous = (
            second_person is not None
            and second_sim >= self.threshold
            and (best_sim - second_sim) < self.ambiguity_margin
        )
        return FaceMatch(
            face=face,
            person=best_person,
            similarity=best_sim,
            second_person=second_person,
            second_similarity=second_sim,
            ambiguous=ambiguous,
        )

    def match_photo(self, analysis: PhotoAnalysis, config: Config) -> PhotoOutcome:
        """Filter tiny faces (edge case #3), match each face, compute subject
        scores for matched faces (SPEC §5: only matched faces compete)."""
        kept = [f for f in analysis.faces if f.min_side >= config.min_face]
        ignored = len(analysis.faces) - len(kept)

        matches = [self.match_face(f) for f in kept]

        max_area = max((f.area for f in kept), default=0.0)
        for m in matches:
            if m.person is not None:
                m.subject_score = subject_score(
                    m.face, m.similarity, analysis.width, analysis.height,
                    max_area, config.weights,
                )

        return PhotoOutcome(
            path=analysis.path,
            width=analysis.width,
            height=analysis.height,
            matches=matches,
            ignored_small_faces=ignored,
        )
