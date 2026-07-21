"""Plan building and plan execution. Strict plan/execute separation:
build_plan() produces a complete, JSON-serializable Plan; dry-run just prints
it; execute_plan() only consumes it. No insightface imports."""

from __future__ import annotations

import os
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from . import templates
from .models import (
    ACT_COPY,
    ACT_MOVE,
    ACT_SKIP,
    CAT_GROUP,
    CAT_NO_FACE,
    CAT_PERSON,
    CAT_UNRECOGNIZED,
    Config,
    Plan,
    PlanItem,
    PhotoOutcome,
    ProgressCallback,
    ProgressEvent,
)

# (datetime, from_exif). Injected so tests need no PIL/EXIF.
DatetimeFn = Callable[[Path], tuple[datetime, bool]]


def _mtime_datetime(path: Path) -> tuple[datetime, bool]:
    return datetime.fromtimestamp(path.stat().st_mtime), False


def _unique_persons_by_score(outcome: PhotoOutcome) -> list[str]:
    """Matched persons, deduped, ordered by best subject score (desc)."""
    best: dict[str, float] = {}
    for m in outcome.matched:
        if m.person not in best or m.subject_score > best[m.person]:
            best[m.person] = m.subject_score
    return sorted(best, key=lambda p: best[p], reverse=True)


def _person_similarity(outcome: PhotoOutcome, person: str) -> float:
    return max((m.similarity for m in outcome.matched if m.person == person), default=0.0)


class _DestResolver:
    """Resolves destination collisions across disk state and the plan itself.
    Never overwrites (edge #8); identical src already at a candidate slot means
    the item is skipped, keeping reruns idempotent (edge #10)."""

    def __init__(self) -> None:
        self._planned: set[str] = set()

    def resolve(self, folder: Path, filename: str, src: Path) -> tuple[Path, bool]:
        """Return (destination, already_there)."""
        stem, ext = os.path.splitext(filename)
        try:
            src_size = src.stat().st_size
        except OSError:
            src_size = -1
        n = 0
        while True:
            name = filename if n == 0 else f"{stem}-{n}{ext}"
            cand = folder / name
            key = str(cand)
            if key in self._planned:
                n += 1
                continue
            if cand.exists():
                try:
                    if cand.stat().st_size == src_size:
                        self._planned.add(key)
                        return cand, True  # same file already in place -> skip
                except OSError:
                    pass
                n += 1
                continue
            self._planned.add(key)
            return cand, False


def build_plan(
    outcomes: list[PhotoOutcome],
    config: Config,
    skipped_files: Optional[list[dict[str, str]]] = None,
    datetime_fn: DatetimeFn = _mtime_datetime,
) -> Plan:
    templates.validate_template(config.folder_template)
    templates.validate_template(config.file_template)

    plan = Plan(skipped_files=list(skipped_files or []))
    resolver = _DestResolver()
    folder_index: dict[str, int] = {}  # per-target-folder {index} counter
    needs_date = bool(
        {"date", "datetime"}
        & (templates.template_fields(config.folder_template)
           | templates.template_fields(config.file_template))
    )

    for outcome in outcomes:
        src = outcome.path
        # The analyzed file plus any companion files (e.g. the RAW next to a JPEG)
        # all follow the same classification to the same folder.
        sources = [outcome.path, *outcome.sidecars]
        persons = _unique_persons_by_score(outcome)

        # Ambiguity report entries (edge #4)
        for m in outcome.matches:
            if m.ambiguous:
                plan.ambiguous.append({
                    "photo": str(src),
                    "person": m.person,
                    "similarity": round(m.similarity, 4),
                    "second_person": m.second_person,
                    "second_similarity": round(m.second_similarity, 4),
                })

        date_str, datetime_str = "", ""
        if needs_date:
            dt, from_exif = datetime_fn(src)
            date_str = dt.strftime("%Y-%m-%d")
            datetime_str = dt.strftime("%Y-%m-%d_%H-%M-%S")
            if not from_exif:
                plan.date_fallback.append(str(src))  # edge #11

        def add_item(folder_rel: str, category: str, person: Optional[str],
                     similarity: float, reason: str, use_folder_template: bool,
                     action: Optional[str] = None) -> None:
            # Emit one plan item per source file (primary + sidecars), all into
            # the same folder; {orig_name}/{ext} differ per file, {index} advances.
            for s in sources:
                base_vars = dict(
                    persons="+".join(persons),
                    date=date_str,
                    datetime=datetime_str,
                    orig_name=s.stem,
                    ext=s.suffix,
                )
                folder_rel_s = folder_rel
                if use_folder_template:
                    folder_rel_s = templates.render(
                        config.folder_template, person=person or "",
                        similarity=similarity, index=0, **base_vars)
                folder = config.output_dir / folder_rel_s
                idx = folder_index.get(str(folder), 0) + 1
                folder_index[str(folder)] = idx
                filename = templates.render(
                    config.file_template, person=person or "",
                    similarity=similarity, index=idx, **base_vars)
                dst, already = resolver.resolve(folder, filename, s)
                plan.items.append(PlanItem(
                    src=str(s),
                    dst=str(dst),
                    action=ACT_SKIP if already else (action or (ACT_MOVE if config.move else ACT_COPY)),
                    category=category,
                    person=person,
                    persons=persons,
                    similarity=None if category == CAT_NO_FACE else similarity,
                    reason=("目标已存在相同文件，跳过（幂等）" if already else reason),
                ))

        if not outcome.matches:
            reason = "未检测到人脸" if outcome.ignored_small_faces == 0 else \
                f"仅有 {outcome.ignored_small_faces} 张小于 min-face={config.min_face}px 的人脸，视同无人脸"
            add_item(config.no_face_dir, CAT_NO_FACE, None, 0.0, reason, False)
            continue

        if not persons:
            best = max(m.similarity for m in outcome.matches)
            add_item(config.unknown_dir, CAT_UNRECOGNIZED, None, best,
                     f"检测到 {len(outcome.matches)} 张人脸，最高相似度 {best:.2f} 低于阈值 {config.threshold}",
                     False)
            continue

        if len(persons) == 1:
            person = persons[0]
            add_item("", CAT_PERSON, person, _person_similarity(outcome, person),
                     f"匹配到 {person}（相似度 {_person_similarity(outcome, person):.2f}）", True)
            continue

        # Multi-person photo (>= 2 distinct matched persons)
        plan.multi_person_photos += 1
        if config.multi_person == "primary":
            primary = persons[0]
            add_item("", CAT_PERSON, primary, _person_similarity(outcome, primary),
                     f"多人照片，主体评分最高者 {primary}（候选: {', '.join(persons)}）", True)
        elif config.multi_person == "all":
            # Copy to every matched person; in move mode the last item moves.
            for i, person in enumerate(persons):
                is_last = i == len(persons) - 1
                action = ACT_MOVE if (config.move and is_last) else ACT_COPY
                add_item("", CAT_PERSON, person, _person_similarity(outcome, person),
                         f"多人照片(all)，复制到每个匹配人物（{', '.join(persons)}）", True,
                         action=action)
        elif config.multi_person == "group":
            folder_rel = config.group_dir
            if config.group_subfolders:
                names = "+".join(templates.sanitize_component(p) for p in sorted(persons))
                folder_rel = os.path.join(folder_rel, names)
            add_item(folder_rel, CAT_GROUP, None,
                     max(_person_similarity(outcome, p) for p in persons),
                     f"多人照片(group)，归入合影（{', '.join(persons)}）", False)
        else:
            raise ValueError(f"未知 multi-person 策略: {config.multi_person}")

    return plan


@dataclass
class ExecResult:
    copied: int = 0
    moved: int = 0
    skipped_existing: int = 0
    errors: list[dict[str, str]] = None  # {src, dst, error}
    cancelled: bool = False

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def to_dict(self) -> dict:
        return {
            "copied": self.copied,
            "moved": self.moved,
            "skipped_existing": self.skipped_existing,
            "errors": list(self.errors),
            "cancelled": self.cancelled,
        }


def execute_plan(
    plan: Plan,
    on_progress: Optional[ProgressCallback] = None,
    cancel: Optional[threading.Event] = None,
) -> ExecResult:
    """Consume the plan. copy=shutil.copy2, move=shutil.move (cross-volume safe,
    edge #15). Checks cancel between items; completed work is kept."""
    result = ExecResult()
    total = len(plan.items)
    for i, item in enumerate(plan.items):
        if cancel is not None and cancel.is_set():
            result.cancelled = True
            break
        try:
            if item.action == ACT_SKIP:
                result.skipped_existing += 1
            else:
                dst = Path(item.dst)
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists():  # plan built earlier; never overwrite (edge #8)
                    raise FileExistsError(f"目标已存在，拒绝覆盖: {dst}")
                if item.action == ACT_COPY:
                    shutil.copy2(item.src, dst)
                    result.copied += 1
                elif item.action == ACT_MOVE:
                    shutil.move(item.src, str(dst))
                    result.moved += 1
                else:
                    raise ValueError(f"未知动作: {item.action}")
        except (OSError, ValueError) as e:
            result.errors.append({"src": item.src, "dst": item.dst, "error": str(e)})
        if on_progress is not None:
            on_progress(ProgressEvent(
                stage="execute", done=i + 1, total=total, current=item.src,
                detail={"dst": item.dst, "action": item.action},
            ))
    return result
