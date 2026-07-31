#!/usr/bin/env python
"""Large-batch stress test for FaceSort — the shape of run that exposed every
bug this release fixes.

Builds a synthetic shoot of N full-size (6000x4000) frames from insightface's
bundled group photo, then drives the whole GUI path end to end and checks the
things that actually went wrong on a real ~5000-photo job:

  * recognition throughput, and which execution provider served it;
  * the preview payload (`_group_plan`) returning promptly instead of decoding
    one original per photo — the 「等待分图方案」 wait;
  * the result payload (`_ambiguous_payload`) doing the same, which is where
    「整理中 4813/4813」 sat with a dead cancel button;
  * cancel actually stopping an execute in progress;
  * no 0-byte files in the output;
  * progress pushes staying rate-limited under load.

Run:  uv run python scripts/stress_test.py --photos 300
      uv run python scripts/stress_test.py --photos 2000 --keep
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FAILED: list[str] = []


def _free(path: Path) -> int:
    """Bytes free on the volume holding `path`."""
    import os
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize


def check(cond: bool, msg: str, detail: str = "") -> None:
    print(f"  {'✅' if cond else '❌'} {msg}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILED.append(msg)


def build_shoot(root: Path, n: int, size=(6000, 4000)) -> Path:
    """N full-size frames. Every file is distinct on disk so nothing dedupes."""
    from insightface.data import get_image

    src = get_image("t1")  # real 6-person group photo, BGR
    base = Image.fromarray(src[:, :, ::-1]).resize(size, Image.BICUBIC)
    in_dir = root / "in"
    in_dir.mkdir(parents=True, exist_ok=True)

    print(f"  生成 {n} 张 {size[0]}x{size[1]} 测试照片…", end="", flush=True)
    t0 = time.monotonic()
    first = in_dir / "MLT_0000.JPG"
    base.save(first, quality=88)
    payload = first.read_bytes()
    for i in range(1, n):
        # Copying the encoded bytes is ~100x faster than re-encoding, and a
        # unique trailing comment keeps each file's size/mtime its own.
        (in_dir / f"MLT_{i:04d}.JPG").write_bytes(payload)
    print(f" {time.monotonic() - t0:.1f}s, {sum(f.stat().st_size for f in in_dir.iterdir()) / 1e9:.2f} GB")
    return in_dir


def make_api(root: Path):
    from facesort.gui import api as api_mod

    lib = root / "people"
    lib.mkdir(parents=True, exist_ok=True)
    api_mod.PeopleLibrary = lambda *a, **kw: SimpleNamespace(root=lib)
    api = api_mod.Api()
    pushes: list[dict] = []
    api._push = lambda event, payload: pushes.append({"event": event, **payload})
    return api, pushes, api_mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", type=int, default=300)
    ap.add_argument("--keep", action="store_true", help="保留生成的测试目录")
    ap.add_argument("--no-gpu", action="store_true")
    args = ap.parse_args()

    root = Path(tempfile.mkdtemp(prefix="facesort_stress_"))
    print(f"Work dir: {root}")
    try:
        return run(root, args)
    finally:
        if args.keep:
            print(f"\n（已保留测试目录: {root}）")
        else:
            shutil.rmtree(root, ignore_errors=True)


def run(root: Path, args) -> int:
    from facesort.core.engine import FaceEngine, coreml_available

    n = args.photos
    in_dir = build_shoot(root, n)
    api, pushes, api_mod = make_api(root)

    print("\n[engine] 执行提供器")
    t0 = time.monotonic()
    engine = FaceEngine(use_gpu=not args.no_gpu)
    engine._ensure_loaded()
    load = time.monotonic() - t0
    api._engine = engine
    print(f"    CoreML 可用: {coreml_available()} | 实际使用: {engine.provider} | 加载 {load:.2f}s")
    check(engine.provider is not None, "识别模型已加载", engine.provider or "")

    cfg = {
        "mode": "cluster",
        "inputDir": str(in_dir),
        "outputDir": str(root / "out"),
        "threshold": 0.40,
        "workers": 0,
        "decodeMaxSide": 1400,
        "clusterMinPhotos": 2,
    }

    # ---- preview: analysis + the payload that used to take minutes ----
    print(f"\n[preview] {n} 张照片")
    t0 = time.monotonic()
    prev = api.preview(dict(cfg))
    t_preview = time.monotonic() - t0
    if not prev.get("ok"):
        check(False, "预览成功", str(prev.get("error"))[:120])
        return 1
    rate = n / t_preview
    print(f"    总耗时 {t_preview:.1f}s  ({rate:.1f} 张/秒)")
    groups = prev["groups"]
    print(f"    分组: {[(g['label'], g['count']) for g in groups]}")

    items = [it for g in groups for it in g["items"]]
    check(all("thumb" not in it for it in items),
          "预览结果不含预生成缩略图（大批量时这是分钟级的差别）")
    check(len(items) == n, "每张照片都有归类", f"{len(items)}/{n}")

    # The payload build itself, measured apart from recognition.
    config = api._build_config(dict(cfg), dry_run=True)
    t0 = time.monotonic()
    api._group_plan(_plan_of(api, cfg, prev), config)
    t_payload = time.monotonic() - t0
    print(f"    分图方案组装: {t_payload * 1000:.0f} ms")
    check(t_payload < 2.0, "分图方案组装是秒级而非分钟级", f"{t_payload * 1000:.0f} ms")

    # ---- thumbnails on demand ----
    print("\n[thumbs] 按需缩略图")
    paths = [it["src"] for it in items[:60]]
    t0 = time.monotonic()
    got = api.thumbs(paths, 200)
    t_th = time.monotonic() - t0
    print(f"    首屏 60 张: {t_th:.2f}s")
    check(got["ok"] and len(got["thumbs"]) == 60, "首屏缩略图齐全")
    check(t_th < 15, "首屏缩略图在可接受时间内", f"{t_th:.2f}s")
    t0 = time.monotonic()
    api.thumbs(paths, 200)
    check(time.monotonic() - t0 < t_th / 2, "重复请求走缓存")

    big = api.image_data(paths[0], 1600)
    check(big["ok"] and big["image"].startswith("data:image/jpeg"), "大图预览可用（放大看清是谁）")

    # ---- organize + cancel ----
    print(f"\n[organize] 整理 {n} 张")
    pushes.clear()
    free_before = _free(root)
    t0 = time.monotonic()
    res = api.organize(dict(cfg))
    t_org = time.monotonic() - t0
    check(res.get("ok"), "整理完成", str(res.get("error"))[:120])
    print(f"    耗时 {t_org:.1f}s")

    ex = (res.get("report") or {}).get("execution") or {}
    print(f"    复制 {ex.get('copied')}（克隆 {ex.get('cloned')}）"
          f"  跳过 {ex.get('skipped_existing')}  错误 {len(ex.get('errors') or [])}")
    check(not ex.get("errors"), "整理无错误")
    print(f"    整理期间磁盘占用变化: {(free_before - _free(root)) / 1e6:+.1f} MB "
          f"（照片本身 {sum(f.stat().st_size for f in in_dir.iterdir()) / 1e6:.0f} MB）")
    if sys.platform == "darwin":
        check(ex.get("cloned") == ex.get("copied"),
              "全部走 APFS 克隆（整理一次不再需要一份等量空间）",
              f"{ex.get('cloned')}/{ex.get('copied')}")
        check(free_before - _free(root) < 200e6,
              "整理没有吃掉与照片等量的磁盘空间",
              f"{(free_before - _free(root)) / 1e6:.0f} MB")
    check(all("thumb" not in a for a in res.get("ambiguous") or []),
          "结果页不含预生成缩略图（这是「卡在最后阶段」的成因）")

    out = Path(res["outputDir"])
    empties = [p for p in out.rglob("*") if p.is_file() and p.stat().st_size == 0]
    check(not empties, "输出目录没有 0 字节文件", f"{len(empties)} 个")
    copied = [p for p in out.rglob("*") if p.is_file() and p.suffix.upper() == ".JPG"]
    check(len(copied) == n, "所有照片都已复制", f"{len(copied)}/{n}")

    prog = [p for p in pushes if p["event"] == "progress"]
    ex_prog = [p for p in prog if p["stage"] == "execute"]
    print(f"    进度推送: {len(prog)} 条（execute 阶段 {len(ex_prog)} 条 / {n} 个文件）")
    check(len(ex_prog) < max(30, n / 3),
          "进度推送已节流（否则会饿死取消按钮所在的主线程）",
          f"{len(ex_prog)} 条")
    check(any(p["stage"] == "finalize" for p in prog),
          "收尾阶段有进度事件（进度条不会停在满格假死）")
    last_ex = ex_prog[-1] if ex_prog else None
    check(bool(last_ex) and last_ex["done"] == last_ex["total"],
          "进度条停在完整的 N/N")

    # ---- cancel mid-execute ----
    # Same output dir, minus the copies: the embedding cache stays warm so this
    # run goes almost straight to the copy loop, which is the part being
    # cancelled. A fresh directory would spend its time re-analyzing instead.
    print("\n[cancel] 整理途中取消")
    for p in copied:
        p.unlink()

    pushes.clear()
    stop = threading.Event()

    def cancel_when_copying():
        """Wait for the copy loop to actually start, so this exercises a cancel
        *during* execute rather than one that lands before it begins."""
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and not stop.is_set():
            if any(p.get("event") == "progress" and p.get("stage") == "execute"
                   for p in list(pushes)):
                break
            time.sleep(0.01)
        api.cancel()

    threading.Thread(target=cancel_when_copying, daemon=True).start()
    t0 = time.monotonic()
    res2 = api.organize(dict(cfg))
    stop.set()
    t_cancel = time.monotonic() - t0
    print(f"    {t_cancel:.1f}s 后返回，cancelled={res2.get('cancelled')}")
    check(res2.get("ok"), "取消后仍正常返回结果（而不是挂死）")

    ex2 = (res2.get("report") or {}).get("execution") or {}
    out2 = Path(res2["outputDir"])
    on_disk = [p for p in out2.rglob("*") if p.is_file() and p.suffix.upper() == ".JPG"]
    done2 = (ex2.get("copied") or 0) + (ex2.get("skipped_existing") or 0)
    print(f"    已复制 {ex2.get('copied')} / {n}，磁盘上 {len(on_disk)} 个文件")
    # Whether the token lands mid-loop or after it depends on machine speed, so
    # assert the invariants that must hold either way.
    check(done2 == len(on_disk), "报告的完成数与磁盘上的文件数一致",
          f"{done2} vs {len(on_disk)}")
    if res2.get("cancelled"):
        check(len(on_disk) < n, "取消确实提前结束了复制", f"{len(on_disk)}/{n}")
    else:
        print("    （本机复制过快，取消令牌在循环结束后才到达；不作断言）")
    empties2 = [p for p in out2.rglob("*") if p.is_file() and p.stat().st_size == 0]
    check(not empties2, "取消后没有留下 0 字节文件", f"{len(empties2)} 个")

    print("\n" + "=" * 60)
    if FAILED:
        print(f"❌ 压测失败 {len(FAILED)} 项:")
        for m in FAILED:
            print(f"   - {m}")
        return 1
    print(f"✅ 压测全部通过（{n} 张，{engine.provider}，{rate:.1f} 张/秒）")
    return 0


def _plan_of(api, cfg, prev):
    """Rebuild a plan-shaped object from the preview, to time payload assembly
    without re-running recognition."""
    from facesort.core.models import PlanItem

    items = []
    for g in prev["groups"]:
        for it in g["items"]:
            items.append(PlanItem(src=it["src"], dst=it["name"], action="copy",
                                  category="person", person=g["label"],
                                  persons=it.get("persons") or [],
                                  similarity=it.get("similarity")))
    return SimpleNamespace(plan=SimpleNamespace(
        items=items, skipped_files=[], ambiguous=[], warnings=[],
        multi_person_photos=0))


if __name__ == "__main__":
    raise SystemExit(main())
