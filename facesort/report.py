"""Run report: JSON (report.json) + human-readable stdout summary."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import __version__
from .core.models import ACT_SKIP, CAT_GROUP, CAT_NO_FACE, CAT_PERSON, CAT_UNRECOGNIZED, Config, Plan


def build_report(
    config: Config,
    plan: Plan,
    exec_result,
    photos_total: int,
    analyzed: int,
    cache_hits: int,
    elapsed: float,
    analyze_elapsed: float,
    cancelled: bool = False,
) -> dict[str, Any]:
    persons: Counter[str] = Counter()
    no_face = unrecognized = group = 0
    for item in plan.items:
        if item.category == CAT_PERSON and item.person:
            persons[item.person] += 1
        elif item.category == CAT_NO_FACE:
            no_face += 1
        elif item.category == CAT_UNRECOGNIZED:
            unrecognized += 1
        elif item.category == CAT_GROUP:
            group += 1

    report: dict[str, Any] = {
        "version": __version__,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": config.dry_run,
        "cancelled": cancelled,
        "config": config.to_dict(),
        "totals": {
            "photos_found": photos_total,
            "plan_items": len(plan.items),
            "skipped_files": len(plan.skipped_files),
            "multi_person_photos": plan.multi_person_photos,
        },
        "persons": dict(sorted(persons.items(), key=lambda kv: (-kv[1], kv[0]))),
        "no_face": no_face,
        "unrecognized": unrecognized,
        "group": group,
        "skipped": plan.skipped_files,
        "ambiguous": plan.ambiguous,
        "date_fallback_mtime": plan.date_fallback,
        "warnings": plan.warnings,
        "performance": {
            "elapsed_sec": round(elapsed, 2),
            "analyze_elapsed_sec": round(analyze_elapsed, 2),
            "inferred": analyzed,
            "cache_hits": cache_hits,
            "photos_per_sec": round(photos_total / analyze_elapsed, 2) if analyze_elapsed > 0 else None,
        },
        "execution": exec_result.to_dict() if exec_result is not None else None,
    }
    if plan.multi_person_photos and config.multi_person == "primary":
        report["hint"] = (
            f"共有 {plan.multi_person_photos} 张多人照片按主体归类（primary），"
            "如需每人一份或统一放入合影，可用 --multi-person all / group 重跑（有缓存，秒级）"
        )
    return report


def write_report(report: dict[str, Any], output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def format_summary(report: dict[str, Any]) -> str:
    """Human-readable summary table for stdout."""
    lines: list[str] = []
    add = lines.append
    add("")
    add("=" * 56)
    add("FaceSort 运行摘要" + ("（dry-run，未动任何文件）" if report["dry_run"] else ""))
    if report.get("cancelled"):
        add("** 本次运行被取消，已完成部分保留 **")
    add("=" * 56)

    rows: list[tuple[str, str]] = []
    for person, n in report["persons"].items():
        rows.append((person, str(n)))
    rows.append(("_未识别", str(report["unrecognized"])))
    rows.append(("_无人脸", str(report["no_face"])))
    if report["group"]:
        rows.append(("_合影", str(report["group"])))
    rows.append(("跳过(非图片/损坏)", str(report["totals"]["skipped_files"])))

    width = max(len(r[0]) for r in rows) + 2
    add(f"{'分类':<{width}}张数")
    add("-" * 56)
    for name, n in rows:
        add(f"{name:<{width}}{n}")
    add("-" * 56)

    perf = report["performance"]
    add(f"照片总数: {report['totals']['photos_found']}  推理: {perf['inferred']}  缓存命中: {perf['cache_hits']}")
    add(f"耗时: {perf['elapsed_sec']}s（分析 {perf['analyze_elapsed_sec']}s"
        + (f", {perf['photos_per_sec']} 张/秒" if perf.get("photos_per_sec") else "") + ")")
    if report.get("execution"):
        ex = report["execution"]
        add(f"执行: 复制 {ex['copied']}  移动 {ex['moved']}  幂等跳过 {ex['skipped_existing']}"
            + (f"  错误 {len(ex['errors'])}" if ex["errors"] else ""))
    if report["ambiguous"]:
        add(f"歧义匹配 {len(report['ambiguous'])} 处（前两名相似度差 < 阈值），建议人工复核，详见 report.json")
    if report["date_fallback_mtime"]:
        add(f"{len(report['date_fallback_mtime'])} 张照片无 EXIF 拍摄时间，{{date}} 已回退文件修改时间")
    for w in report["warnings"]:
        add(f"警告: {w}")
    if report.get("hint"):
        add(f"提示: {report['hint']}")
    add("=" * 56)
    return "\n".join(lines)
