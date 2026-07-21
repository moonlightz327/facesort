"""FaceSort CLI (typer): `facesort run` and `facesort inspect`."""

from __future__ import annotations

import json
import signal
import threading
from pathlib import Path
from typing import Optional

import typer

from . import __version__, report as report_mod
from .core.models import Config, ConfigError, ProgressEvent, SubjectWeights
from .core.templates import TemplateError

app = typer.Typer(
    add_completion=False,
    help="FaceSort（分图）：按人物样本自动把照片归入以人名命名的文件夹。",
    no_args_is_help=True,
)


def _progress_printer(verbose: bool):
    def on_progress(ev: ProgressEvent) -> None:
        if ev.stage == "samples":
            typer.echo(f"[样本 {ev.done}/{ev.total}] {ev.current}: {ev.detail['samples']} 张有效样本")
        elif ev.stage == "scan":
            typer.echo(f"[扫描] 找到 {ev.total} 张图片，跳过 {ev.detail['skipped']} 个非图片文件")
        elif ev.stage == "analyze":
            d = ev.detail or {}
            if "error" in d:
                typer.echo(f"[分析 {ev.done}/{ev.total}] {ev.current}  跳过: {d['error']}")
            else:
                persons = [p for p in d.get("persons", []) if p]
                tag = "缓存" if d.get("cached") else "推理"
                who = ", ".join(persons) if persons else ("无匹配" if d.get("faces") else "无人脸")
                typer.echo(f"[分析 {ev.done}/{ev.total}|{tag}] {Path(ev.current).name}: {who}")
        elif ev.stage == "execute" and verbose:
            d = ev.detail or {}
            typer.echo(f"[执行 {ev.done}/{ev.total}] {d.get('action')} -> {d.get('dst')}")

    return on_progress


@app.command()
def run(
    samples: Path = typer.Option(..., "--samples", help="样本库目录（子目录名=人名）"),
    input_dir: Path = typer.Option(..., "--input", help="待整理照片目录（递归扫描）"),
    output: Optional[Path] = typer.Option(None, "--output", help="输出目录，默认 <input>/_sorted"),
    threshold: float = typer.Option(0.40, "--threshold", help="余弦相似度阈值（保守默认 0.40）"),
    multi_person: str = typer.Option("primary", "--multi-person", help="多人照片策略: primary/all/group"),
    folder_template: str = typer.Option("{person}", "--folder-template", help="文件夹命名模板"),
    file_template: str = typer.Option("{orig_name}{ext}", "--file-template", help="文件命名模板"),
    move: bool = typer.Option(False, "--move", help="移动而非复制（默认复制）"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印归类计划，不动任何文件"),
    min_face: int = typer.Option(40, "--min-face", help="最小人脸边长（像素），过滤背景小脸"),
    weights: Optional[str] = typer.Option(None, "--weights", help="主体评分权重，如 'area=0.45,center=0.25,sim=0.30'"),
    no_face_dir: str = typer.Option("_无人脸", "--no-face-dir", help="无人脸照片文件夹名"),
    unknown_dir: str = typer.Option("_未识别", "--unknown-dir", help="未识别照片文件夹名"),
    group_dir: str = typer.Option("_合影", "--group-dir", help="合影文件夹名（group 策略）"),
    group_subfolders: bool = typer.Option(False, "--group-subfolders", help="合影内按人名组合建子文件夹（张三+李四）"),
    cache: Optional[Path] = typer.Option(None, "--cache", help="SQLite 缓存路径，默认 <output>/.facesort_cache.sqlite"),
    plan_json: bool = typer.Option(False, "--plan-json", help="dry-run 时以 JSON 输出计划（默认表格）"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="打印每个执行动作"),
):
    """一条命令完成整理：分析 -> 匹配 -> 计划 -> 执行（或 dry-run 只看计划）。"""
    from .core.pipeline import run_pipeline  # lazy: keeps --help fast

    try:
        config = Config(
            samples_dir=samples,
            input_dir=input_dir,
            output_dir=(output or (input_dir / "_sorted")),
            threshold=threshold,
            multi_person=multi_person,
            folder_template=folder_template,
            file_template=file_template,
            move=move,
            dry_run=dry_run,
            min_face=min_face,
            weights=SubjectWeights.parse(weights) if weights else SubjectWeights(),
            no_face_dir=no_face_dir,
            unknown_dir=unknown_dir,
            group_dir=group_dir,
            group_subfolders=group_subfolders,
            cache_path=cache,
        )

        cancel = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: cancel.set())  # Ctrl-C: 优雅停止，保留已完成部分

        result = run_pipeline(config, on_progress=_progress_printer(verbose), cancel=cancel)
    except (ConfigError, TemplateError) as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    if dry_run:
        typer.echo("")
        typer.secho("== 归类计划（dry-run，未动任何文件）==", bold=True)
        if plan_json:
            typer.echo(json.dumps(result.plan.to_dict(), ensure_ascii=False, indent=2))
        else:
            for item in result.plan.items:
                sim = f" sim={item.similarity:.2f}" if item.similarity is not None else ""
                typer.echo(f"  [{item.action}] {item.src}\n      -> {item.dst}{sim}  ({item.reason})")
            for s in result.plan.skipped_files:
                typer.echo(f"  [skip] {s['path']}  ({s['reason']})")

    typer.echo(report_mod.format_summary(result.report))
    if not dry_run:
        typer.echo(f"report.json 已写入: {config.output_dir / 'report.json'}")
    if result.cancelled:
        raise typer.Exit(code=130)


@app.command()
def cluster(
    input_dir: Path = typer.Option(..., "--input", help="待整理照片目录（递归扫描）"),
    output: Optional[Path] = typer.Option(None, "--output", help="输出目录，默认 <input>/_clustered"),
    threshold: float = typer.Option(0.40, "--threshold", help="聚类相似度阈值（越高分得越细）"),
    multi_person: str = typer.Option("primary", "--multi-person", help="多人照片策略: primary/all/group"),
    folder_template: str = typer.Option("{person}", "--folder-template", help="文件夹命名模板（人物N 为 {person}）"),
    file_template: str = typer.Option("{orig_name}{ext}", "--file-template", help="文件命名模板"),
    move: bool = typer.Option(False, "--move", help="移动而非复制（默认复制）"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印计划，不动任何文件"),
    min_face: int = typer.Option(40, "--min-face", help="最小人脸边长（像素）"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="打印每个执行动作"),
):
    """无样本模式：自动把长相相同的人聚成「人物1/人物2…」文件夹，之后可自行改名。"""
    from .core.pipeline import run_cluster_pipeline

    try:
        config = Config(
            samples_dir=input_dir,  # ignored in cluster mode
            input_dir=input_dir,
            output_dir=(output or (input_dir / "_clustered")),
            threshold=threshold,
            multi_person=multi_person,
            folder_template=folder_template,
            file_template=file_template,
            move=move,
            dry_run=dry_run,
            min_face=min_face,
        )
        cancel = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: cancel.set())
        result = run_cluster_pipeline(config, on_progress=_progress_printer(verbose), cancel=cancel)
    except (ConfigError, TemplateError) as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    if dry_run:
        typer.echo("")
        typer.secho(f"== 聚类计划：{result.report.get('clusters', 0)} 个人物分组（dry-run）==", bold=True)
        for item in result.plan.items:
            typer.echo(f"  [{item.action}] {Path(item.src).name} -> {item.dst}")
    typer.echo(report_mod.format_summary(result.report))
    if not dry_run:
        typer.echo(f"共分出 {result.report.get('clusters', 0)} 个人物分组，report.json 已写入: {config.output_dir / 'report.json'}")
    if result.cancelled:
        raise typer.Exit(code=130)


@app.command()
def inspect(
    photo: Path = typer.Argument(..., help="要调试的照片路径"),
    samples: Optional[Path] = typer.Option(None, "--samples", help="样本库目录（提供则输出与每个人的相似度）"),
    min_face: int = typer.Option(0, "--min-face", help="最小人脸边长过滤（默认不过滤）"),
):
    """调试单张照片：打印检测到的人脸（bbox/置信度）与对样本库的相似度。"""
    from .core.engine import FaceEngine
    from .core.matcher import Matcher, SampleLibrary, subject_score
    from .core.models import SubjectWeights
    from .core.pipeline import build_sample_library

    engine = FaceEngine()
    try:
        analysis = engine.analyze(photo)
    except Exception as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    typer.echo(f"图片: {photo}  ({analysis.width}x{analysis.height})")
    typer.echo(f"检测到 {len(analysis.faces)} 张人脸")

    matcher = None
    if samples is not None:
        try:
            library = build_sample_library(engine, samples)
        except ConfigError as e:
            typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        matcher = Matcher(library)

    weights = SubjectWeights()
    max_area = max((f.area for f in analysis.faces), default=0.0)
    for i, face in enumerate(analysis.faces):
        x1, y1, x2, y2 = face.bbox
        small = " [< min-face，将被忽略]" if min_face and face.min_side < min_face else ""
        typer.echo(f"\n人脸 #{i}: bbox=({x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}) "
                   f"尺寸={face.width:.0f}x{face.height:.0f} 置信度={face.det_score:.3f}{small}")
        if matcher is not None:
            emb = face.embedding
            import numpy as np

            from .core.matcher import _normalize

            sims = sorted(
                ((p, float(np.max(mat @ _normalize(emb)))) for p, mat in matcher.library.people.items()),
                key=lambda t: t[1], reverse=True,
            )
            for person, sim in sims:
                mark = " <- 超过阈值 0.40" if sim >= 0.40 else ""
                typer.echo(f"    {person}: {sim:.4f}{mark}")
            score = subject_score(face, sims[0][1], analysis.width, analysis.height, max_area, weights)
            typer.echo(f"    主体评分(若匹配): {score:.4f}")


@app.command()
def gui():
    """打开图形界面（面向普通用户，无需命令行）。"""
    from .gui.app import launch
    launch()


@app.command()
def version():
    """打印版本号。"""
    typer.echo(f"facesort {__version__}")


if __name__ == "__main__":
    app()
