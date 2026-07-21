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
) -> SampleLibrary:
    """samples/<person>/*.jpg -> library. Multiple faces in a sample photo:
    take the largest and warn (edge #5). Empty samples dir or a person dir
    with no valid face: hard error before anything is touched (edge #6)."""
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
    for i, person_dir in enumerate(person_dirs):
        person = person_dir.name
        images = sorted(p for p in person_dir.rglob("*") if p.is_file() and is_image_file(p))
        count = 0
        for img_path in images:
            analysis = cache.get(img_path) if cache is not None else None
            if analysis is None:
                try:
                    analysis = engine.analyze(img_path)
                except ImageReadError as e:
                    library.warnings.append(f"样本图片无法读取，跳过: {img_path} ({e})")
                    continue
                if cache is not None:
                    cache.put(img_path, analysis)
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
            raise ConfigError(
                f"人物 '{person}' 的样本目录 {person_dir} 没有任何有效人脸样本，请检查后重试"
            )
        _emit(on_progress, ProgressEvent(
            stage="samples", done=i + 1, total=total, current=person,
            detail={"samples": count},
        ))
    library.validate()
    return library


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
        library = build_sample_library(engine, config.samples_dir, cache, on_progress)
        matcher = Matcher(library, threshold=config.threshold,
                          ambiguity_margin=config.ambiguity_margin)

        # 2. Scan + pair same-stem RAW+JPEG shots into single units
        photos, skipped = scan_photos(config.input_dir, config.output_dir)
        units = pair_photos(photos)
        _emit(on_progress, ProgressEvent(stage="scan", done=len(photos), total=len(photos),
                                         detail={"skipped": len(skipped), "units": len(units)}))

        # 3. Analyze (cache-first) + match, cancellable between shots
        outcomes: list[PhotoOutcome] = []
        analyzed = 0
        cancelled = False
        total_units = len(units)
        for i, (path, sidecars) in enumerate(units):
            if _check_cancel(cancel):
                cancelled = True
                break
            analysis = cache.get(path)
            was_cached = analysis is not None
            if analysis is None:
                try:
                    analysis = engine.analyze(path)
                except ImageReadError as e:
                    skipped.append({"path": str(path), "reason": f"图片损坏或无法读取: {e}"})
                    _emit(on_progress, ProgressEvent(
                        stage="analyze", done=i + 1, total=total_units, current=str(path),
                        detail={"error": str(e)}))
                    continue
                cache.put(path, analysis)
                analyzed += 1
            outcome = matcher.match_photo(analysis, config)
            outcome.sidecars = sidecars
            outcomes.append(outcome)
            _emit(on_progress, ProgressEvent(
                stage="analyze", done=i + 1, total=total_units, current=str(path),
                detail={
                    "faces": len(outcome.matches),
                    "persons": [m.person for m in outcome.matched],
                    "similarities": [round(m.similarity, 3) for m in outcome.matches],
                    "cached": was_cached,
                    "sidecars": len(sidecars),
                }))
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

        # Pass 1: analyze every shot; collect faces for clustering.
        analyses: list[tuple[PhotoAnalysis, list[Path]]] = []
        face_embeddings: list = []
        photo_of_face: list[int] = []
        analyzed = 0
        cancelled = False
        total_units = len(units)
        for i, (path, sidecars) in enumerate(units):
            if _check_cancel(cancel):
                cancelled = True
                break
            analysis = cache.get(path)
            if analysis is None:
                try:
                    analysis = engine.analyze(path)
                except ImageReadError as e:
                    skipped.append({"path": str(path), "reason": f"图片损坏或无法读取: {e}"})
                    continue
                cache.put(path, analysis)
                analyzed += 1
            idx = len(analyses)
            analyses.append((analysis, sidecars))
            for f in analysis.faces:
                if f.min_side >= config.min_face:
                    face_embeddings.append(f.embedding)
                    photo_of_face.append(idx)
            _emit(on_progress, ProgressEvent(
                stage="analyze", done=i + 1, total=total_units, current=str(path),
                detail={"faces": len(analysis.faces)}))
        analyze_elapsed = time.monotonic() - t0

        # Cluster the collected faces into 人物1..N.
        library, names = build_cluster_library(face_embeddings, photo_of_face, cthr)
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
            plan.warnings.insert(0, f"聚类模式：自动分出 {len(names)} 个人物分组"
                                    "（人物1、人物2…），可在输出目录按需重命名文件夹")
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
