"""Shared dataclasses. No insightface imports here."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

# Plan item categories
CAT_PERSON = "person"          # matched a single person (or primary of multi)
CAT_NO_FACE = "no_face"        # no (usable) face detected
CAT_UNRECOGNIZED = "unrecognized"  # faces present but none matched
CAT_GROUP = "group"            # multi-person, group strategy

# Actions
ACT_COPY = "copy"
ACT_MOVE = "move"
ACT_SKIP = "skip"              # destination already holds this file (idempotent rerun)


class ConfigError(Exception):
    """Fatal setup problem (bad samples dir etc.) - abort before touching anything."""


@dataclass
class Face:
    """A detected face: bbox in pixels (x1, y1, x2, y2) + 512-d embedding."""

    bbox: tuple[float, float, float, float]
    embedding: np.ndarray
    det_score: float = 1.0

    @property
    def width(self) -> float:
        return max(0.0, self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> float:
        return max(0.0, self.bbox[3] - self.bbox[1])

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return ((self.bbox[0] + self.bbox[2]) / 2.0, (self.bbox[1] + self.bbox[3]) / 2.0)

    @property
    def min_side(self) -> float:
        return min(self.width, self.height)


@dataclass
class PhotoAnalysis:
    """Raw detection result for one image."""

    path: Path
    width: int
    height: int
    faces: list[Face] = field(default_factory=list)


@dataclass
class FaceMatch:
    """A face after matching against the sample library."""

    face: Face
    person: Optional[str]          # None = below threshold
    similarity: float              # best cosine similarity (over all persons/samples)
    second_person: Optional[str] = None
    second_similarity: float = 0.0
    ambiguous: bool = False        # top-2 both above threshold and diff < margin
    subject_score: float = 0.0     # filled for matched faces (primary strategy)


@dataclass
class PhotoOutcome:
    """One photo, fully analyzed and matched. Input to the organizer."""

    path: Path
    width: int
    height: int
    matches: list[FaceMatch] = field(default_factory=list)  # only faces >= min_face
    ignored_small_faces: int = 0
    # Companion files organized to the same destination as `path` (edge: a shot
    # exported as both RAW and JPEG). The primary (analyzed) file is `path`.
    sidecars: list[Path] = field(default_factory=list)

    @property
    def matched(self) -> list[FaceMatch]:
        return [m for m in self.matches if m.person is not None]


@dataclass
class SubjectWeights:
    area: float = 0.45
    center: float = 0.25
    sim: float = 0.30

    def to_dict(self) -> dict[str, float]:
        return {"area": self.area, "center": self.center, "sim": self.sim}

    @classmethod
    def parse(cls, text: str) -> "SubjectWeights":
        """Parse '0.45,0.25,0.30' or 'area=0.45,center=0.25,sim=0.30'."""
        parts = [p.strip() for p in text.split(",") if p.strip()]
        try:
            if all("=" in p for p in parts):
                kv = dict(p.split("=", 1) for p in parts)
                return cls(
                    area=float(kv.get("area", cls.area)),
                    center=float(kv.get("center", cls.center)),
                    sim=float(kv.get("sim", cls.sim)),
                )
            if len(parts) == 3:
                return cls(area=float(parts[0]), center=float(parts[1]), sim=float(parts[2]))
        except (ValueError, TypeError) as e:
            raise ConfigError(f"无法解析 --weights '{text}': {e}") from e
        raise ConfigError(
            f"无法解析 --weights '{text}'，格式: 'area=0.45,center=0.25,sim=0.30' 或 '0.45,0.25,0.30'"
        )


@dataclass
class Config:
    samples_dir: Path
    input_dir: Path
    output_dir: Path
    threshold: float = 0.40
    multi_person: str = "primary"          # primary | all | group
    folder_template: str = "{person}"
    file_template: str = "{orig_name}{ext}"
    move: bool = False
    dry_run: bool = False
    min_face: int = 40
    weights: SubjectWeights = field(default_factory=SubjectWeights)
    no_face_dir: str = "_无人脸"
    unknown_dir: str = "_未识别"
    group_dir: str = "_合影"
    group_subfolders: bool = False         # _合影/张三+李四/ subfolders
    ambiguity_margin: float = 0.05
    cache_path: Optional[Path] = None      # default: <output_dir>/.facesort_cache.sqlite

    def to_dict(self) -> dict[str, Any]:
        return {
            "samples_dir": str(self.samples_dir),
            "input_dir": str(self.input_dir),
            "output_dir": str(self.output_dir),
            "threshold": self.threshold,
            "multi_person": self.multi_person,
            "folder_template": self.folder_template,
            "file_template": self.file_template,
            "move": self.move,
            "dry_run": self.dry_run,
            "min_face": self.min_face,
            "weights": self.weights.to_dict(),
            "no_face_dir": self.no_face_dir,
            "unknown_dir": self.unknown_dir,
            "group_dir": self.group_dir,
            "group_subfolders": self.group_subfolders,
            "ambiguity_margin": self.ambiguity_margin,
        }


@dataclass
class PlanItem:
    src: str
    dst: str
    action: str                     # copy | move | skip
    category: str                   # person | no_face | unrecognized | group
    person: Optional[str] = None    # target person (primary person for multi)
    persons: list[str] = field(default_factory=list)  # all matched persons in the photo
    similarity: Optional[float] = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "src": self.src,
            "dst": self.dst,
            "action": self.action,
            "category": self.category,
            "person": self.person,
            "persons": list(self.persons),
            "similarity": round(self.similarity, 4) if self.similarity is not None else None,
            "reason": self.reason,
        }


@dataclass
class Plan:
    items: list[PlanItem] = field(default_factory=list)
    skipped_files: list[dict[str, str]] = field(default_factory=list)   # {path, reason}
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    date_fallback: list[str] = field(default_factory=list)  # photos where mtime was used for {date}
    warnings: list[str] = field(default_factory=list)
    multi_person_photos: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self.items],
            "skipped_files": list(self.skipped_files),
            "ambiguous": list(self.ambiguous),
            "date_fallback": list(self.date_fallback),
            "warnings": list(self.warnings),
            "multi_person_photos": self.multi_person_photos,
        }


@dataclass
class ProgressEvent:
    """Emitted per photo. stage: scan | analyze | plan | execute."""

    stage: str
    done: int
    total: int
    current: Optional[str] = None
    detail: Optional[dict[str, Any]] = None


ProgressCallback = Callable[[ProgressEvent], None]
