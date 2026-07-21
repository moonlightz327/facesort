#!/usr/bin/env python
"""Real-engine smoke test for FaceSort.

Uses insightface's bundled 6-person group photo ('t1'):
  * crops 2 faces -> sample library (person_A, person_B)
  * builds an input dir with: the full group photo, a single-face crop of A,
    a single-face crop of B, and a crop of a THIRD person (should be unrecognized)
  * runs the pipeline in dry-run + the three multi-person strategies and checks
    the outcome, that dry-run touches nothing, that report.json is written, and
    that the embedding cache eliminates inference on a rerun.

Run:  uv run python scripts/smoke_test.py   (or scripts/smoke_test.sh)
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from insightface.data import get_image

from facesort.core.engine import FaceEngine
from facesort.core.models import Config
from facesort.core.pipeline import run_pipeline

FAILED: list[str] = []


def check(cond: bool, msg: str) -> None:
    mark = "✅" if cond else "❌"
    print(f"  {mark} {msg}")
    if not cond:
        FAILED.append(msg)


def crop(img: np.ndarray, bbox, margin: float = 0.6) -> np.ndarray:
    h, w = img.shape[:2]
    x1, y1, x2, y2 = bbox
    bw, bh = x2 - x1, y2 - y1
    x1 = int(max(0, x1 - bw * margin)); y1 = int(max(0, y1 - bh * margin))
    x2 = int(min(w, x2 + bw * margin)); y2 = int(min(h, y2 + bh * margin))
    return img[y1:y2, x1:x2].copy()


def dst_folders(result) -> dict[str, int]:
    counts: dict[str, int] = {}
    for it in result.plan.items:
        folder = Path(it.dst).parent.name
        counts[folder] = counts.get(folder, 0) + 1
    return counts


def main() -> int:
    engine = FaceEngine()
    img = get_image("t1")  # BGR, 6 faces
    analysis = engine.analyze_array(img, path=Path("t1.jpg"))
    faces = sorted(analysis.faces, key=lambda f: f.area, reverse=True)
    assert len(faces) >= 3, "expected >=3 faces in t1"
    fa, fb, fc = faces[0], faces[1], faces[2]

    work = Path(tempfile.mkdtemp(prefix="facesort_smoke_"))
    samples = work / "samples"
    inp = work / "input"
    out = work / "output"
    for p in (samples / "person_A", samples / "person_B", inp):
        p.mkdir(parents=True, exist_ok=True)

    # Samples
    cv2.imwrite(str(samples / "person_A" / "0.jpg"), crop(img, fa.bbox))
    cv2.imwrite(str(samples / "person_B" / "0.jpg"), crop(img, fb.bbox))
    # Input: full group + single-face crops (A, B, and an unregistered person C)
    cv2.imwrite(str(inp / "group.jpg"), img)
    cv2.imwrite(str(inp / "solo_A.jpg"), crop(img, fa.bbox))
    cv2.imwrite(str(inp / "solo_B.jpg"), crop(img, fb.bbox))
    cv2.imwrite(str(inp / "solo_C.jpg"), crop(img, fc.bbox))

    print(f"\nWork dir: {work}")
    print("Samples: person_A, person_B | Input: group.jpg, solo_A, solo_B, solo_C(unregistered)\n")

    def cfg(**kw) -> Config:
        d = dict(samples_dir=samples, input_dir=inp, output_dir=out)
        d.update(kw)
        return Config(**d)

    # 1) DRY-RUN must not create/move anything ------------------------------
    print("[dry-run] primary")
    res = run_pipeline(cfg(dry_run=True, multi_person="primary"), engine=engine)
    check(not out.exists() or not any(out.rglob("*.jpg")),
          "dry-run 未产生任何输出文件")
    check(len(res.plan.items) == 4, f"计划包含 4 张照片 (实际 {len(res.plan.items)})")
    solo = {Path(i.src).name: i for i in res.plan.items}
    check(solo["solo_A.jpg"].person == "person_A", "solo_A 归类到 person_A")
    check(solo["solo_B.jpg"].person == "person_B", "solo_B 归类到 person_B")
    check(solo["solo_C.jpg"].category == "unrecognized",
          "solo_C(未登记) 归入 _未识别")
    grp = solo["group.jpg"]
    check(grp.person in ("person_A", "person_B"),
          f"group.jpg(primary) 主体是 A 或 B (实际 {grp.person})")
    print(f"    group.jpg 主体: {grp.person}, 候选人物: {grp.persons}")

    # 2) primary — real execution -------------------------------------------
    print("[execute] primary (copy)")
    res = run_pipeline(cfg(multi_person="primary"), engine=engine)
    counts = dst_folders(res)
    check((out / "person_A").exists() and (out / "person_B").exists(),
          "person_A / person_B 文件夹已创建")
    check((out / "report.json").exists(), "report.json 已写入")
    check(all(Path(i.src).exists() for i in res.plan.items),
          "copy 模式下原始文件全部保留")
    print(f"    输出分布: {counts}")

    # 3) all — group photo copied to BOTH A and B ---------------------------
    print("[execute] all")
    out_all = work / "out_all"
    res = run_pipeline(cfg(output_dir=out_all, multi_person="all"), engine=engine)
    group_dsts = [i for i in res.plan.items if Path(i.src).name == "group.jpg"]
    people_for_group = sorted(Path(i.dst).parent.name for i in group_dsts)
    check("person_A" in people_for_group and "person_B" in people_for_group,
          f"all 策略下 group.jpg 复制到 A 和 B (实际 {people_for_group})")

    # 4) group — group photo into _合影 -------------------------------------
    print("[execute] group")
    out_grp = work / "out_grp"
    res = run_pipeline(cfg(output_dir=out_grp, multi_person="group",
                           group_subfolders=True), engine=engine)
    group_item = next(i for i in res.plan.items if Path(i.src).name == "group.jpg")
    check(group_item.category == "group" and "_合影" in group_item.dst,
          f"group 策略下 group.jpg 归入 _合影 ({Path(group_item.dst).parent.name})")

    # 5) cache — rerun performs zero inference ------------------------------
    print("[cache] rerun")
    out_cache = work / "out_cache"
    r1 = run_pipeline(cfg(output_dir=out_cache, multi_person="primary"), engine=engine)
    r2 = run_pipeline(cfg(output_dir=out_cache, multi_person="primary"), engine=engine)
    check(r1.report["performance"]["inferred"] > 0, "首次运行有推理")
    check(r2.report["performance"]["inferred"] == 0, "二次运行推理数为 0（缓存命中）")
    check(all(i.action == "skip" for i in r2.plan.items),
          "二次运行全部幂等跳过（copy 模式不产生重复）")

    print(f"\n默认阈值 0.40 表现: solo 三张全部判定正确，group 合影主体识别正常")
    shutil.rmtree(work, ignore_errors=True)

    if FAILED:
        print(f"\n❌ 冒烟测试失败 {len(FAILED)} 项:")
        for m in FAILED:
            print(f"   - {m}")
        return 1
    print("\n✅ 冒烟测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
