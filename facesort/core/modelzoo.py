"""Recognition-model provisioning.

insightface downloads buffalo_l straight from github.com release assets, which
times out on many mainland networks (the ConnectTimeout users hit). This module
takes that job over: it checks for an already-installed model, then a copy
bundled with the app, then downloads from a list of mirrors with real timeouts
and progress — and can always fall back to a zip the user supplies by hand.

Layout is exactly what insightface expects, so once the files are in place
`FaceAnalysis(name="buffalo_l")` finds them and never reaches the network:

    ~/.insightface/models/buffalo_l/{det_10g,w600k_r50,...}.onnx

No insightface import here (keeps this usable before the model exists)."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Callable, Optional

MODEL_NAME = "buffalo_l"
ZIP_SIZE = 288621354  # bytes, official v0.7 asset — used only as a sanity hint

# Detection + recognition are the only modules FaceEngine enables; the other
# three (landmark/genderage) ship in the same zip and are ignored at load time.
REQUIRED_FILES = ("det_10g.onnx", "w600k_r50.onnx")

_GH_PATH = "deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"

# Tried in order. The mirrors are GitHub release proxies that work from networks
# where github.com itself is unreachable; all three serve the identical asset.
SOURCES: list[dict[str, str]] = [
    {"id": "ghfast", "label": "国内加速镜像 (ghfast.top)",
     "url": f"https://ghfast.top/https://github.com/{_GH_PATH}"},
    {"id": "ghproxy", "label": "国内加速镜像 (gh-proxy.com)",
     "url": f"https://gh-proxy.com/https://github.com/{_GH_PATH}"},
    {"id": "github", "label": "GitHub 官方源",
     "url": f"https://github.com/{_GH_PATH}"},
]

CONNECT_TIMEOUT = 15.0   # fail fast on an unreachable host instead of hanging
READ_TIMEOUT = 60.0

ProgressFn = Callable[[dict], None]


class ModelError(Exception):
    """Model is unavailable and we could not fix it automatically."""


class ModelCancelled(ModelError):
    pass


# ---- locations ---------------------------------------------------------


def model_root() -> Path:
    """Where insightface looks for models (honors its INSIGHTFACE_HOME)."""
    home = os.environ.get("INSIGHTFACE_HOME") or str(Path.home() / ".insightface")
    return Path(home) / "models"


def model_dir() -> Path:
    return model_root() / MODEL_NAME


def is_installed(directory: Optional[Path] = None) -> bool:
    d = Path(directory) if directory else model_dir()
    return d.is_dir() and all((d / f).is_file() for f in REQUIRED_FILES)


def bundled_dir() -> Optional[Path]:
    """A model shipped inside the app bundle, if the build included one.

    Packaging can drop the extracted `buffalo_l/` next to the frozen app (see
    packaging/FaceSort.spec); when present the first run needs no network."""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates += [Path(meipass) / "models" / MODEL_NAME, Path(meipass) / MODEL_NAME]
    here = Path(__file__).resolve().parent.parent  # facesort/
    candidates += [here / "models" / MODEL_NAME, here.parent / "models" / MODEL_NAME]
    env = os.environ.get("FACESORT_MODEL_DIR")
    if env:
        candidates.insert(0, Path(env))
    for c in candidates:
        if is_installed(c):
            return c
    return None


def sources() -> list[dict[str, str]]:
    """Download sources, with a user-supplied URL taking priority."""
    custom = os.environ.get("FACESORT_MODEL_URL")
    if custom:
        return [{"id": "custom", "label": "自定义地址", "url": custom}] + SOURCES
    return list(SOURCES)


def status() -> dict:
    """What the UI needs to decide whether to offer a download."""
    return {
        "installed": is_installed(),
        "bundled": bundled_dir() is not None,
        "modelDir": str(model_dir()),
        "sources": [{"id": s["id"], "label": s["label"]} for s in sources()],
        "sizeMB": round(ZIP_SIZE / 1e6),
    }


# ---- install paths -----------------------------------------------------


def _install_from_dir(src: Path, on_progress: Optional[ProgressFn] = None) -> Path:
    dst = model_dir()
    if on_progress:
        on_progress({"phase": "copy", "percent": 50.0,
                     "detail": "正在从应用内置副本安装模型…"})
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=str(dst.parent), prefix=".buffalo_l-"))
    try:
        for f in src.iterdir():
            if f.is_file():
                shutil.copy2(f, tmp / f.name)
        _swap_in(tmp, dst)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dst


def _swap_in(staged: Path, dst: Path) -> None:
    """Replace dst with staged as close to atomically as the filesystem allows."""
    if dst.exists():
        backup = dst.with_name(dst.name + ".old")
        shutil.rmtree(backup, ignore_errors=True)
        dst.rename(backup)
        try:
            staged.rename(dst)
        except OSError:
            backup.rename(dst)
            raise
        shutil.rmtree(backup, ignore_errors=True)
    else:
        staged.rename(dst)


def install_from_zip(zip_path: Path, on_progress: Optional[ProgressFn] = None) -> Path:
    """Install from a buffalo_l.zip the user downloaded themselves.

    Accepts both zip layouts seen in the wild: files at the root, or nested
    under a `buffalo_l/` directory."""
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise ModelError(f"找不到文件: {zip_path}")
    dst = model_dir()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if on_progress:
        on_progress({"phase": "extract", "percent": 100.0,
                     "detail": "正在解压模型（约 289MB，请稍候）…"})
    tmp = Path(tempfile.mkdtemp(dir=str(dst.parent), prefix=".buffalo_l-"))
    try:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp)
        except zipfile.BadZipFile as e:
            raise ModelError(f"文件不是有效的 zip 压缩包: {zip_path.name} ({e})") from e
        staged = _find_model_files(tmp)
        if staged is None:
            raise ModelError(
                f"压缩包里没有找到模型文件（需要 {', '.join(REQUIRED_FILES)}），"
                "请确认下载的是 buffalo_l.zip"
            )
        if staged != tmp:
            # Flatten a nested buffalo_l/ directory to the layout insightface wants.
            flat = Path(tempfile.mkdtemp(dir=str(dst.parent), prefix=".buffalo_l-"))
            for f in staged.iterdir():
                if f.is_file():
                    shutil.move(str(f), str(flat / f.name))
            shutil.rmtree(tmp, ignore_errors=True)
            tmp = flat
        _swap_in(tmp, dst)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dst


def _find_model_files(root: Path) -> Optional[Path]:
    """Directory inside `root` that holds the required onnx files."""
    if all((root / f).is_file() for f in REQUIRED_FILES):
        return root
    for d in root.rglob("*"):
        if d.is_dir() and all((d / f).is_file() for f in REQUIRED_FILES):
            return d
    return None


def download(source_id: Optional[str] = None,
             on_progress: Optional[ProgressFn] = None,
             cancel: Optional[threading.Event] = None) -> Path:
    """Fetch the model zip, trying each mirror until one works.

    `on_progress` receives {phase, source, attempt, attempts, done, total,
    percent, bytesPerSec, etaSeconds, detail}; phase is connect/download/
    extract/done. Raises ModelError listing every source that failed."""
    import urllib.error
    import urllib.request

    import time

    picked = sources()
    if source_id:
        picked = [s for s in picked if s["id"] == source_id] or picked

    dst = model_dir()
    dst.parent.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    attempts = len(picked)

    for index, src in enumerate(picked, start=1):
        if cancel is not None and cancel.is_set():
            raise ModelCancelled("已取消下载")
        tmp_zip = dst.parent / f".{MODEL_NAME}.part"
        base = {"source": src["label"], "attempt": index, "attempts": attempts}
        try:
            if on_progress:
                on_progress({**base, "phase": "connect", "done": 0,
                             "total": ZIP_SIZE, "percent": 0.0,
                             "detail": f"正在连接 {src['label']}…"})
            req = urllib.request.Request(
                src["url"], headers={"User-Agent": "FaceSort/1.0"})
            # urlopen's timeout is per socket operation, so it covers both the
            # connect and each read — an unreachable mirror fails in seconds.
            with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT) as resp:
                total = int(resp.headers.get("Content-Length") or 0) or ZIP_SIZE
                done = 0
                started = time.monotonic()
                last_emit = 0.0
                with open(tmp_zip, "wb") as fh:
                    while True:
                        if cancel is not None and cancel.is_set():
                            raise ModelCancelled("已取消下载")
                        chunk = resp.read(1 << 18)
                        if not chunk:
                            break
                        fh.write(chunk)
                        done += len(chunk)
                        now = time.monotonic()
                        # Throttle to ~5 updates/sec; every one crosses into JS.
                        if on_progress and (now - last_emit > 0.2 or done >= total):
                            last_emit = now
                            elapsed = max(now - started, 1e-6)
                            speed = done / elapsed
                            remaining = max(total - done, 0)
                            on_progress({
                                **base, "phase": "download",
                                "done": done, "total": total,
                                "percent": (done / total * 100.0) if total else 0.0,
                                "bytesPerSec": speed,
                                "etaSeconds": (remaining / speed) if speed > 0 else None,
                            })
            if done == 0:
                raise ModelError("下载内容为空")
            # install_from_zip is the real validation: a proxy that answers with
            # an HTML error page fails there as "not a valid zip", which is more
            # reliable than any size threshold.
            result = install_from_zip(tmp_zip, on_progress=on_progress)
            tmp_zip.unlink(missing_ok=True)
            return result
        except ModelCancelled:
            tmp_zip.unlink(missing_ok=True)
            raise
        except (urllib.error.URLError, OSError, ModelError, TimeoutError) as e:
            tmp_zip.unlink(missing_ok=True)
            reason = getattr(e, "reason", None) or e
            failures.append(f"{src['label']}: {reason}")
            continue

    raise ModelError(
        "所有下载源都失败了：\n  " + "\n  ".join(failures)
        + "\n\n可以改用「手动导入模型」：自行下载 buffalo_l.zip 后在界面里选择该文件。"
    )


def ensure_model(on_progress: Optional[ProgressFn] = None,
                 cancel: Optional[threading.Event] = None,
                 auto_download: bool = True) -> Path:
    """Guarantee the model is on disk. Order: installed -> bundled -> download."""
    if is_installed():
        return model_dir()
    bundled = bundled_dir()
    if bundled is not None:
        return _install_from_dir(bundled, on_progress=on_progress)
    if not auto_download:
        raise ModelError("识别模型尚未安装")
    return download(on_progress=on_progress, cancel=cancel)
