"""JS <-> Python bridge exposed to the web UI via pywebview. Every method takes
and returns JSON-friendly values. Long operations (preview/organize) run on the
pywebview-provided thread and stream progress to the page through evaluate_js."""

from __future__ import annotations

import json
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..core.models import Config, ConfigError, SubjectWeights
from ..core.templates import TemplateError, render, validate_template
from . import thumbs
from .library import PeopleLibrary, app_support_dir

STRATEGIES = ["primary", "all", "group"]

FOLDER_PRESETS = [
    {"id": "person", "label": "人名", "folder": "{person}", "file": "{orig_name}{ext}"},
    {"id": "person_date_index", "label": "人名 / 日期_序号",
     "folder": "{person}", "file": "{date}_{index:03d}{ext}"},
    {"id": "date_person", "label": "日期 / 人名",
     "folder": "{date}/{person}", "file": "{orig_name}{ext}"},
    {"id": "person_index", "label": "人名 / 序号",
     "folder": "{person}", "file": "{index:03d}{ext}"},
]


class Api:
    def __init__(self) -> None:
        self.library = PeopleLibrary()
        self._engine = None
        self._window = None  # set by app.py after window creation
        self._cancel = threading.Event()
        self._busy = threading.Lock()

    # ---- infrastructure -------------------------------------------------
    def set_window(self, window) -> None:
        self._window = window

    def _engine_get(self):
        if self._engine is None:
            from ..core.engine import FaceEngine
            self._engine = FaceEngine()
        return self._engine

    def _push(self, event: str, payload: dict[str, Any]) -> None:
        if self._window is None:
            return
        msg = json.dumps({"event": event, **payload}, ensure_ascii=False)
        try:
            self._window.evaluate_js(f"window.__facesort_event({msg})")
        except Exception:
            pass

    # ---- startup --------------------------------------------------------
    def bootstrap(self) -> dict[str, Any]:
        """Initial state for the app: presets, strategies, saved people."""
        return {
            "strategies": STRATEGIES,
            "folderPresets": FOLDER_PRESETS,
            "people": self._people_payload(),
            "defaults": {
                "threshold": 0.40,
                "multiPerson": "primary",
                "folderTemplate": "{person}",
                "fileTemplate": "{orig_name}{ext}",
                "minFace": 40,
                "move": False,
            },
            "libraryPath": str(self.library.root),
        }

    def warm_up(self) -> dict[str, Any]:
        """Load the recognition model (first call downloads ~300MB). The UI calls
        this before the first analysis so it can show a one-time loading state."""
        self._engine_get()._ensure_loaded()
        return {"ready": True}

    # ---- people / samples ----------------------------------------------
    def _people_payload(self) -> list[dict[str, Any]]:
        out = []
        for person in self.library.list_people():
            samples = [{"path": p, "thumb": thumbs.data_uri(Path(p), size=120)}
                       for p in person["samples"]]
            out.append({"name": person["name"], "samples": samples})
        return out

    def list_people(self) -> list[dict[str, Any]]:
        return self._people_payload()

    def add_person(self, name: str) -> dict[str, Any]:
        try:
            real = self.library.add_person(name)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "name": real}

    def remove_person(self, name: str) -> dict[str, Any]:
        self.library.remove_person(name)
        return {"ok": True}

    def remove_sample(self, path: str) -> dict[str, Any]:
        self.library.remove_sample(path)
        return {"ok": True}

    def pick_sample_files(self) -> list[str]:
        if self._window is None:
            return []
        import webview
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True,
            file_types=("图片 (*.jpg;*.jpeg;*.png;*.heic;*.heif;*.tif;*.tiff;*.webp)",),
        )
        return list(result) if result else []

    def add_samples(self, name: str, paths: list[str]) -> dict[str, Any]:
        """Copy samples into the person's folder and report per-photo face
        detection so the UI can flag samples with no/multiple faces."""
        added = self.library.add_samples(name, paths)
        engine = self._engine_get()
        results = []
        for dst in added:
            info: dict[str, Any] = {"path": dst, "thumb": thumbs.data_uri(Path(dst), size=120)}
            try:
                analysis = engine.analyze(Path(dst))
            except Exception as e:
                info.update(faceCount=0, ok=False, warning=f"无法读取: {e}")
                results.append(info)
                continue
            info["faceCount"] = len(analysis.faces)
            if not analysis.faces:
                info.update(ok=False, warning="未检测到人脸，请换一张清晰正脸样本")
            else:
                largest = max(analysis.faces, key=lambda f: f.area)
                info["faceThumb"] = thumbs.data_uri(Path(dst), size=120, box=largest.bbox)
                info["ok"] = True
                if len(analysis.faces) > 1:
                    info["warning"] = f"检测到 {len(analysis.faces)} 张脸，将取最大的一张"
            results.append(info)
        return {"ok": True, "samples": results}

    # ---- folder pickers -------------------------------------------------
    def pick_folder(self, title: str = "选择文件夹") -> Optional[str]:
        if self._window is None:
            return None
        import webview
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

    # ---- naming preview -------------------------------------------------
    def preview_name(self, folder_template: str, file_template: str) -> dict[str, Any]:
        try:
            validate_template(folder_template)
            validate_template(file_template)
            variables = dict(
                person="张三", persons="张三+李四",
                date="2026-07-17", datetime="2026-07-17_15-30-00",
                orig_name="IMG_1234", ext=".jpg", index=1, similarity=0.87,
            )
            folder = render(folder_template, **variables)
            fname = render(file_template, **variables)
            return {"ok": True, "example": f"{folder}/{fname}"}
        except TemplateError as e:
            return {"ok": False, "error": str(e)}

    # ---- config helper --------------------------------------------------
    def _build_config(self, cfg: dict[str, Any], dry_run: bool) -> Config:
        input_dir = Path(cfg["inputDir"])
        default_sub = "_clustered" if cfg.get("mode") == "cluster" else "_sorted"
        output_dir = Path(cfg["outputDir"]) if cfg.get("outputDir") else (input_dir / default_sub)
        weights = cfg.get("weights")
        return Config(
            samples_dir=self.library.root,
            input_dir=input_dir,
            output_dir=output_dir,
            threshold=float(cfg.get("threshold", 0.40)),
            multi_person=cfg.get("multiPerson", "primary"),
            folder_template=cfg.get("folderTemplate", "{person}"),
            file_template=cfg.get("fileTemplate", "{orig_name}{ext}"),
            move=bool(cfg.get("move", False)),
            dry_run=dry_run,
            min_face=int(cfg.get("minFace", 40)),
            weights=SubjectWeights(**weights) if weights else SubjectWeights(),
            group_subfolders=bool(cfg.get("groupSubfolders", False)),
        )

    def _progress_cb(self):
        def cb(ev):
            self._push("progress", {
                "stage": ev.stage, "done": ev.done, "total": ev.total,
                "current": Path(ev.current).name if ev.current else None,
                "detail": ev.detail,
            })
        return cb

    # ---- preview (dry-run) & organize ----------------------------------
    def _run(self, config: Config, cfg: dict[str, Any]):
        """Dispatch to the sample-based or the sample-free clustering pipeline."""
        from ..core.pipeline import run_cluster_pipeline, run_pipeline
        engine = self._engine_get()
        cb = self._progress_cb()
        if cfg.get("mode") == "cluster":
            return run_cluster_pipeline(config, engine=engine, on_progress=cb, cancel=self._cancel)
        return run_pipeline(config, engine=engine, on_progress=cb, cancel=self._cancel)

    def preview(self, cfg: dict[str, Any]) -> dict[str, Any]:
        if not self._busy.acquire(blocking=False):
            return {"ok": False, "error": "已有任务在进行中"}
        try:
            self._cancel.clear()
            config = self._build_config(cfg, dry_run=True)
            result = self._run(config, cfg)
            grouped = self._group_plan(result, config)
            grouped["ok"] = True
            grouped["cancelled"] = result.cancelled
            grouped["clusters"] = result.report.get("clusters")
            return grouped
        except (ConfigError, TemplateError) as e:
            return {"ok": False, "error": str(e)}
        finally:
            self._busy.release()

    def organize(self, cfg: dict[str, Any]) -> dict[str, Any]:
        if not self._busy.acquire(blocking=False):
            return {"ok": False, "error": "已有任务在进行中"}
        try:
            self._cancel.clear()
            config = self._build_config(cfg, dry_run=False)
            result = self._run(config, cfg)
            return {
                "ok": True,
                "cancelled": result.cancelled,
                "report": result.report,
                "outputDir": str(config.output_dir),
                "ambiguous": self._ambiguous_payload(result, config),
            }
        except (ConfigError, TemplateError) as e:
            return {"ok": False, "error": str(e)}
        finally:
            self._busy.release()

    def cancel(self) -> dict[str, Any]:
        self._cancel.set()
        return {"ok": True}

    # ---- results helpers ------------------------------------------------
    def _group_plan(self, result, config: Config) -> dict[str, Any]:
        from ..core.models import CAT_GROUP, CAT_NO_FACE, CAT_PERSON, CAT_UNRECOGNIZED
        buckets: dict[str, dict[str, Any]] = {}
        order: list[str] = []

        def bucket(key: str, label: str, kind: str) -> dict[str, Any]:
            if key not in buckets:
                buckets[key] = {"key": key, "label": label, "kind": kind, "items": []}
                order.append(key)
            return buckets[key]

        for item in result.plan.items:
            if item.category == CAT_PERSON:
                b = bucket(f"p:{item.person}", item.person, "person")
            elif item.category == CAT_GROUP:
                b = bucket("group", config.group_dir, "group")
            elif item.category == CAT_UNRECOGNIZED:
                b = bucket("unknown", config.unknown_dir, "unrecognized")
            elif item.category == CAT_NO_FACE:
                b = bucket("noface", config.no_face_dir, "no_face")
            else:
                continue
            b["items"].append({
                "src": item.src,
                "thumb": thumbs.data_uri(Path(item.src), size=200),
                "name": Path(item.dst).name,
                "similarity": item.similarity,
                "persons": item.persons,
                "reason": item.reason,
            })

        groups = [buckets[k] for k in order]
        # People first (by count desc), then group/unrecognized/no_face last.
        rank = {"person": 0, "group": 1, "unrecognized": 2, "no_face": 3}
        groups.sort(key=lambda g: (rank[g["kind"]], -len(g["items"])))
        for g in groups:
            g["count"] = len(g["items"])
        return {
            "groups": groups,
            "total": len(result.plan.items),
            "multiPersonPhotos": result.plan.multi_person_photos,
            "ambiguous": self._ambiguous_payload(result, config),
            "warnings": result.plan.warnings,
            "skipped": result.plan.skipped_files,
            "config": config.to_dict(),
        }

    def _ambiguous_payload(self, result, config: Config) -> list[dict[str, Any]]:
        out = []
        for a in result.plan.ambiguous:
            out.append({
                **a,
                "thumb": thumbs.data_uri(Path(a["photo"]), size=200),
                "candidates": [a["person"], a["second_person"]],
            })
        return out

    # ---- post-hoc correction / finder ----------------------------------
    def reassign(self, src: str, to_person: str, output_dir: str,
                 move: bool = False) -> dict[str, Any]:
        """Put a photo into another person's folder after the fact (used for
        ambiguous-photo review). Copies the original by default."""
        import shutil
        from ..core.templates import sanitize_component
        src_p = Path(src)
        if not src_p.is_file():
            return {"ok": False, "error": "原文件不存在"}
        dst_dir = Path(output_dir) / sanitize_component(to_person)
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src_p.name
        n = 0
        while dst.exists():
            n += 1
            dst = dst_dir / f"{src_p.stem}-{n}{src_p.suffix}"
        try:
            if move:
                shutil.move(str(src_p), str(dst))
            else:
                shutil.copy2(src_p, dst)
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "dst": str(dst)}

    def save_cluster_as_person(self, output_dir: str, cluster_name: str,
                               new_name: str, count: int = 4) -> dict[str, Any]:
        """Turn a 人物N cluster into a saved person: copy a few of its photos into
        the sample library under `new_name` so later runs recognize them by name.
        Connects the sample-free clustering flow back to the sample library."""
        from ..core.imageio import is_image_file, is_raw_file
        new_name = (new_name or "").strip()
        if not new_name:
            return {"ok": False, "error": "名字不能为空"}
        src_dir = Path(output_dir) / cluster_name
        if not src_dir.is_dir():
            return {"ok": False, "error": f"找不到分组文件夹: {src_dir}"}
        # Prefer standard images (a RAW's embedded preview also works but is slower).
        imgs = [p for p in sorted(src_dir.iterdir())
                if p.is_file() and is_image_file(p) and not is_raw_file(p)]
        if not imgs:
            imgs = [p for p in sorted(src_dir.iterdir()) if p.is_file() and is_image_file(p)]
        if not imgs:
            return {"ok": False, "error": "该分组没有可用照片"}
        self.library.add_person(new_name)
        result = self.add_samples(new_name, [str(p) for p in imgs[:count]])
        added = [s for s in result.get("samples", []) if s.get("ok")]
        return {"ok": True, "name": new_name, "saved": len(added),
                "people": self._people_payload()}

    def open_path(self, path: str) -> dict[str, Any]:
        import sys
        p = Path(path)
        target = p if p.exists() else p.parent
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", str(target)], check=False)
            elif sys.platform == "win32":
                import os
                os.startfile(str(target))  # noqa: on Windows only
            else:
                subprocess.run(["xdg-open", str(target)], check=False)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}
