"""End-to-end pipeline: samples -> scan -> analyze(+cache) -> match -> plan
-> execute. Supports per-photo progress callbacks and a cancel event so a GUI
can drive it later."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .cache import EmbeddingCache
from .imageio import ImageReadError, get_photo_datetime, is_image_file
from .matcher import Matcher, SampleLibrary
from .models import (
    Config,
    ConfigError,
    PhotoAnalysis,
    PhotoOutcome,
    Plan,
    ProgressCallback,
    ProgressEvent,
)
from .organizer import ExecResult, build_plan, execute_plan


class CancelledError(Exception):
    pass


@dataclass
class PipelineResult:
    plan: Plan
    exec_result: Optional[ExecResult]      # None in dry-run
    report: dict[str, Any]
    cancelled: bool = False


def _emit(cb: Optional[ProgressCallback], event: ProgressEvent) -> None:
    if cb is not None:
        cb(event)


def _check_cancel(cancel: Optional[threading.Event]) -> bool:
    return cancel is not None and cancel.is_set()


def build_sample_library(
    engine,
    samples_dir: Path,
    cache: Optional[EmbeddingCache] = None,
    on_progress: Optional[ProgressCallback] = None,
    workers: int = 0,
) -> SampleLibrary:
    """samples/<person>/*.jpg -> library. Multiple faces in a sample photo:
    take the largest and warn (edge #5).

    A person with no usable sample is skipped with a warning rather than
    aborting the run: the GUI lets you create a person before giving them
    photos, and one such placeholder used to make every later run fail. Only an
    entirely empty library is fatal (edge #6)."""
    samples_dir = Path(samples_dir)
    if not samples_dir.is_dir():
        raise ConfigError(f"样本目录不存在: {samples_dir}")
    person_dirs = sorted(
        d for d in samples_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )
    if not person_dirs:
        raise ConfigError(f"样本目录 {samples_dir} 下没有人物子目录（目录名即人名）")

    library = SampleLibrary()
    total = len(person_dirs)
    empty_people: list[str] = []
    for i, person_dir in enumerate(person_dirs):
        person = person_dir.name
        images = sorted(p for p in person_dir.rglob("*") if p.is_file() and is_image_file(p))
        count = 0
        for img_path, analysis, exc, _cached in _analyze_many(
            engine, images, cache=cache, workers=workers
        ):
            if exc is not None:
                library.warnings.append(f"样本图片无法读取，跳过: {img_path} ({exc})")
                continue
            if not analysis.faces:
                library.warnings.append(f"样本图片未检测到人脸，跳过: {img_path}")
                continue
            face = max(analysis.faces, key=lambda f: f.area)
            if len(analysis.faces) > 1:
                library.warnings.append(
                    f"样本图片 {img_path} 检测到 {len(analysis.faces)} 张人脸，取最大人脸作为 {person} 的样本"
                )
            library.add(person, face.embedding)
            count += 1
        if count == 0:
            empty_people.append(person)
            library.warnings.append(
                f"人物 '{person}' 还没有可用的人脸样本，本次跳过（请为 TA 添加清晰正脸样本）"
            )
        _emit(on_progress, ProgressEvent(
            stage="samples", done=i + 1, total=total, current=person,
            detail={"samples": count},
        ))
    if not library.people:
        detail = "、".join(empty_people) if empty_people else "无"
        raise ConfigError(
            f"没有任何人物拥有可用的人脸样本（已登记但缺样本: {detail}），"
            "请先添加清晰的正脸样本照片"
        )
    return library


def _analyze_many(engine, paths, cache=None, workers: int = 0, cancel=None):
    """Cache-first analysis of `paths`, yielding `(path, analysis, exception,
    was_cached)` in input order.

    Decode + inference run on a small thread pool; the cache is consulted inside
    the worker (EmbeddingCache is lock-guarded). Only ImageReadError is handed
    back per photo — anything else is a real bug and propagates."""
    from .parallel import imap_ordered

    def work(path: Path):
        if cache is not None:
            hit = cache.get(path)
            if hit is not None:
                return hit, True
        analysis = engine.analyze(path)
        if cache is not None:
            cache.put(path, analysis)
        return analysis, False

    for path, result, exc in imap_ordered(work, paths, workers=workers, cancel=cancel):
        if exc is not None:
            if isinstance(exc, ImageReadError):
                yield path, None, exc, False
                continue
            raise exc
        analysis, was_cached = result
        yield path, analysis, None, was_cached


def scan_photos(input_dir: Path, output_dir: Path) -> tuple[list[Path], list[dict[str, str]]]:
    """Recursively find images under input_dir, excluding output_dir (edge #9)
    and hidden files. Returns (photos, skipped_non_images)."""
    input_dir = Path(input_dir).resolve()
    output_dir = Path(output_dir).resolve()
    photos: list[Path] = []
    skipped: list[dict[str, str]] = []
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue
        rp = path.resolve()
        if rp == output_dir or output_dir in rp.parents:
            continue
        if path.name.startswith("."):
            continue
        if is_image_file(path):
            photos.append(path)
        else:
            skipped.append({"path": str(path), "reason": f"非支持的图片格式 ({path.suffix or '无扩展名'})"})
    return photos, skipped


def pair_photos(photos: list[Path]) -> list[tuple[Path, list[Path]]]:
    """Group same-stem RAW+JPEG shots into one unit. Returns (primary, sidecars):
    when a shot exists as both RAW and a standard image, the standard image is the
    primary (analyzed) and the RAW rides along to the same destination (edge:
    RAW+JPEG pair). Standard-only and RAW-only files are their own units."""
    from .imageio import is_raw_file

    groups: dict[tuple[str, str], list[Path]] = {}
    order: list[tuple[str, str]] = []
    for p in photos:
        key = (str(p.parent), p.stem.lower())
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(p)

    units: list[tuple[Path, list[Path]]] = []
    for key in order:
        members = groups[key]
        raws = [m for m in members if is_raw_file(m)]
        stds = [m for m in members if not is_raw_file(m)]
        if stds and raws:
            # Prefer a JPEG as the primary; the rest (RAW + any extra std) follow.
            stds.sort(key=lambda p: (p.suffix.lower() not in (".jpg", ".jpeg"), p.name))
            primary, rest = stds[0], stds[1:] + raws
            units.append((primary, rest))
        else:
            members_sorted = sorted(members, key=lambda p: p.name)
            units.append((members_sorted[0], members_sorted[1:]))
    return units


def run_pipeline(
    config: Config,
    engine=None,
    on_progress: Optional[ProgressCallback] = None,
    cancel: Optional[threading.Event] = None,
) -> PipelineResult:
    from .. import report as report_mod

    t0 = time.monotonic()
    if engine is None:
        from .engine import FaceEngine

        engine = FaceEngine()

    config.input_dir = Path(config.input_dir).resolve()
    config.output_dir = Path(config.output_dir).resolve()
    if config.input_dir == config.output_dir:
        raise ConfigError("输出目录不能与输入目录相同")
    if config.multi_person not in ("primary", "all", "group"):
        raise ConfigError(f"--multi-person 必须是 primary/all/group，收到: {config.multi_person}")

    cache_path = config.cache_path or (config.output_dir / ".facesort_cache.sqlite")

    with EmbeddingCache(cache_path) as cache:
        # 1. Sample library (hard errors surface before any file operation)
        library = build_sample_library(engine, config.samples_dir, cache, on_progress,
                                       workers=config.workers)
        matcher = Matcher(library, threshold=config.threshold,
                          ambiguity_margin=config.ambiguity_margin)

        # 2. Scan + pair same-stem RAW+JPEG shots into single units
        photos, skipped = scan_photos(config.input_dir, config.output_dir)
        units = pair_photos(photos)
        _emit(on_progress, ProgressEvent(stage="scan", done=len(photos), total=len(photos),
                                         detail={"skipped": len(skipped), "units": len(units)}))

        # 3. Analyze (cache-first, parallel) + match, cancellable between shots
        outcomes: list[PhotoOutcome] = []
        analyzed = 0
        done = 0
        cancelled = False
        total_units = len(units)
        sidecars_of = {path: sidecars for path, sidecars in units}
        for path, analysis, exc, was_cached in _analyze_many(
            engine, [p for p, _ in units], cache=cache,
            workers=config.workers, cancel=cancel,
        ):
            done += 1
            if exc is not None:
                skipped.append({"path": str(path), "reason": f"图片损坏或无法读取: {exc}"})
                _emit(on_progress, ProgressEvent(
                    stage="analyze", done=done, total=total_units, current=str(path),
                    detail={"error": str(exc)}))
                continue
            if not was_cached:
                analyzed += 1
            sidecars = sidecars_of.get(path, [])
            outcome = matcher.match_photo(analysis, config)
            outcome.sidecars = sidecars
            outcomes.append(outcome)
            _emit(on_progress, ProgressEvent(
                stage="analyze", done=done, total=total_units, current=str(path),
                detail={
                    "faces": len(outcome.matches),
                    "persons": [m.person for m in outcome.matched],
                    "similarities": [round(m.similarity, 3) for m in outcome.matches],
                    "cached": was_cached,
                    "sidecars": len(sidecars),
                }))
        cancelled = _check_cancel(cancel)
        analyze_elapsed = time.monotonic() - t0

        # 4. Plan
        plan = build_plan(outcomes, config, skipped_files=skipped,
                          datetime_fn=get_photo_datetime)
        plan.warnings = library.warnings + plan.warnings
        _emit(on_progress, ProgressEvent(stage="plan", done=len(plan.items),
                                         total=len(plan.items)))

        # 5. Execute (skipped entirely in dry-run)
        exec_result: Optional[ExecResult] = None
        if not config.dry_run and not cancelled:
            exec_result = execute_plan(plan, on_progress=on_progress, cancel=cancel)
            cancelled = cancelled or exec_result.cancelled

        elapsed = time.monotonic() - t0
        report = report_mod.build_report(
            config=config, plan=plan, exec_result=exec_result,
            photos_total=len(photos), analyzed=analyzed,
            cache_hits=cache.hits, elapsed=elapsed,
            analyze_elapsed=analyze_elapsed, cancelled=cancelled,
        )

    if not config.dry_run:
        report_mod.write_report(report, config.output_dir)

    return PipelineResult(plan=plan, exec_result=exec_result, report=report,
                          cancelled=cancelled)


def apply_cluster_names(
    library: SampleLibrary,
    names: dict[int, str],
    overrides: dict[str, str],
) -> tuple[SampleLibrary, dict[int, str]]:
    """Rename auto-detected clusters (`人物1` -> `张三`) before planning.

    Blank overrides are ignored, names are sanitized to be usable as folder
    names, and two clusters mapped to the same name are merged into one person
    (naming 人物1 and 人物3 both `张三` means they are the same person)."""
    from .templates import sanitize_component

    clean: dict[str, str] = {}
    for old, new in overrides.items():
        safe = sanitize_component(str(new or "").strip())
        if safe and safe != old:
            clean[old] = safe
    if not clean:
        return library, names

    new_names = {cid: clean.get(old, old) for cid, old in names.items()}
    merged = SampleLibrary(warnings=list(library.warnings))
    for old, mat in library.people.items():
        target = clean.get(old, old)
        for row in mat:
            merged.add(target, row)
    return merged, new_names


def run_cluster_pipeline(
    config: Config,
    engine=None,
    on_progress: Optional[ProgressCallback] = None,
    cancel: Optional[threading.Event] = None,
    cluster_threshold: Optional[float] = None,
) -> PipelineResult:
    """Sample-free mode: analyze every photo, cluster the faces into 人物1..N, then
    reuse the normal match/plan/execute path with those cluster centroids as a
    synthetic sample library. `samples_dir` is ignored here."""
    from .. import report as report_mod
    from .cluster import build_cluster_library
    from .matcher import Matcher

    t0 = time.monotonic()
    if engine is None:
        from .engine import FaceEngine
        engine = FaceEngine()

    config.input_dir = Path(config.input_dir).resolve()
    config.output_dir = Path(config.output_dir).resolve()
    if config.input_dir == config.output_dir:
        raise ConfigError("输出目录不能与输入目录相同")
    cthr = cluster_threshold if cluster_threshold is not None else config.threshold
    cache_path = config.cache_path or (config.output_dir / ".facesort_cache.sqlite")

    with EmbeddingCache(cache_path) as cache:
        photos, skipped = scan_photos(config.input_dir, config.output_dir)
        units = pair_photos(photos)
        _emit(on_progress, ProgressEvent(stage="scan", done=len(photos), total=len(photos),
                                         detail={"skipped": len(skipped), "units": len(units)}))

        # Pass 1: analyze every shot; collect faces for clustering. Results come
        # back in input order, so the clustering below stays deterministic even
        # though the analysis itself runs in parallel.
        analyses: list[tuple[PhotoAnalysis, list[Path]]] = []
        face_embeddings: list = []
        photo_of_face: list[int] = []
        analyzed = 0
        done = 0
        cancelled = False
        total_units = len(units)
        sidecars_of = {path: sidecars for path, sidecars in units}
        for path, analysis, exc, was_cached in _analyze_many(
            engine, [p for p, _ in units], cache=cache,
            workers=config.workers, cancel=cancel,
        ):
            done += 1
            if exc is not None:
                skipped.append({"path": str(path), "reason": f"图片损坏或无法读取: {exc}"})
                continue
            if not was_cached:
                analyzed += 1
            idx = len(analyses)
            analyses.append((analysis, sidecars_of.get(path, [])))
            for f in analysis.faces:
                if f.min_side >= config.min_face:
                    face_embeddings.append(f.embedding)
                    photo_of_face.append(idx)
            _emit(on_progress, ProgressEvent(
                stage="analyze", done=done, total=total_units, current=str(path),
                detail={"faces": len(analysis.faces)}))
        cancelled = _check_cancel(cancel)
        analyze_elapsed = time.monotonic() - t0

        # Cluster the collected faces into 人物1..N, then apply any names the
        # user typed in the preview so folders are written correctly the first
        # time instead of being renamed afterwards.
        library, names = build_cluster_library(face_embeddings, photo_of_face, cthr)
        if config.cluster_names:
            library, names = apply_cluster_names(library, names, config.cluster_names)
        matcher = None
        if library.people:
            matcher = Matcher(library, threshold=cthr,
                              ambiguity_margin=config.ambiguity_margin)

        # Pass 2: assign each shot to its cluster(s), reuse plan/execute.
        outcomes: list[PhotoOutcome] = []
        for analysis, sidecars in analyses:
            if matcher is not None:
                outcome = matcher.match_photo(analysis, config)
            else:
                outcome = PhotoOutcome(path=analysis.path, width=analysis.width,
                                       height=analysis.height, matches=[])
            outcome.sidecars = sidecars
            outcomes.append(outcome)

        plan = build_plan(outcomes, config, skipped_files=skipped,
                          datetime_fn=get_photo_datetime)
        if names:
            renamed = sum(1 for n in names.values() if not n.startswith("人物"))
            note = f"聚类模式：自动分出 {len(set(names.values()))} 个人物分组"
            note += f"，其中 {renamed} 个已按你填写的名字命名" if renamed else \
                    "（人物1、人物2…），可在预览页或整理完成后重命名"
            plan.warnings.insert(0, note)
        _emit(on_progress, ProgressEvent(stage="plan", done=len(plan.items),
                                         total=len(plan.items)))

        exec_result: Optional[ExecResult] = None
        if not config.dry_run and not cancelled:
            exec_result = execute_plan(plan, on_progress=on_progress, cancel=cancel)
            cancelled = cancelled or exec_result.cancelled

        elapsed = time.monotonic() - t0
        report = report_mod.build_report(
            config=config, plan=plan, exec_result=exec_result,
            photos_total=len(photos), analyzed=analyzed,
            cache_hits=cache.hits, elapsed=elapsed,
            analyze_elapsed=analyze_elapsed, cancelled=cancelled,
        )
        report["clusters"] = len(names)

    if not config.dry_run:
        report_mod.write_report(report, config.output_dir)

    return PipelineResult(plan=plan, exec_result=exec_result, report=report,
                          cancelled=cancelled)
