"""What the JS bridge hands back to the page, and how often.

Both regressions these cover came from the same 5000-photo run: the preview sat
on 「正在生成分图方案」 for minutes after recognition had finished, and the
organize step parked at 4813/4813 with a dead 「取消」 button. Neither was slow
recognition — both were the payload builders decoding an original per photo,
and the progress firehose starving the WebView's main thread."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from facesort.core.models import Config, Face, FaceMatch, PhotoOutcome, ProgressEvent
from facesort.core.organizer import build_plan
from facesort.gui import api as api_mod


@pytest.fixture
def gui(tmp_path, monkeypatch):
    """An Api whose people library lives in tmp_path, not the real home dir."""
    monkeypatch.setattr(api_mod, "PeopleLibrary",
                        lambda *a, **kw: SimpleNamespace(root=tmp_path / "people"))
    a = api_mod.Api()
    a._pushed = []
    monkeypatch.setattr(a, "_push", lambda event, payload: a._pushed.append((event, payload)))
    return a


def _photo(tmp_path: Path, name: str) -> Path:
    p = tmp_path / "in" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"pretend-jpeg")
    return p


def _outcome(path: Path, person: str, sim: float = 0.7, ambiguous=None) -> PhotoOutcome:
    face = Face(bbox=(0.0, 0.0, 100.0, 100.0), embedding=np.zeros(512, dtype=np.float32))
    m = FaceMatch(face=face, person=person, similarity=sim, subject_score=0.5)
    if ambiguous:
        m.ambiguous = True
        m.second_person, m.second_similarity = ambiguous
    return PhotoOutcome(path=path, width=1000, height=800, matches=[m])


def _result(tmp_path, outcomes):
    config = Config(samples_dir=tmp_path / "s", input_dir=tmp_path / "in",
                    output_dir=tmp_path / "out")
    plan = build_plan(outcomes, config)
    return SimpleNamespace(plan=plan, report={}), config


# ---------- payloads carry paths, not decoded images ----------

def test_group_plan_ships_no_thumbnails(gui, tmp_path):
    outcomes = [_outcome(_photo(tmp_path, f"a{i}.jpg"), "张三") for i in range(5)]
    result, config = _result(tmp_path, outcomes)

    grouped = gui._group_plan(result, config)

    items = [it for g in grouped["groups"] for it in g["items"]]
    assert len(items) == 5
    assert all("thumb" not in it for it in items), \
        "预览不能预先解码每张照片，否则大批量时要等好几分钟"
    assert all(Path(it["src"]).exists() for it in items)


def test_ambiguous_payload_ships_no_thumbnails(gui, tmp_path):
    outcomes = [_outcome(_photo(tmp_path, f"a{i}.jpg"), "张三", ambiguous=("李四", 0.68))
                for i in range(3)]
    result, config = _result(tmp_path, outcomes)

    payload = gui._ambiguous_payload(result, config)

    assert len(payload) == 3
    assert all("thumb" not in a for a in payload)
    assert all(a["candidates"] == ["张三", "李四"] for a in payload)


def test_group_plan_does_not_touch_image_data(gui, tmp_path, monkeypatch):
    """The strongest form of the above: no decode call is made at all."""
    monkeypatch.setattr(api_mod.thumbs, "data_uri",
                        lambda *a, **kw: pytest.fail("预览阶段不应解码照片"))
    outcomes = [_outcome(_photo(tmp_path, f"a{i}.jpg"), "张三") for i in range(3)]
    result, config = _result(tmp_path, outcomes)
    gui._group_plan(result, config)


# ---------- on-demand images ----------

def test_thumbs_batch_is_capped_and_size_clamped(gui, monkeypatch):
    seen = {}

    def fake_many(paths, size=200, workers=0):
        seen["n"] = len(list(paths))
        seen["size"] = size
        return {}

    monkeypatch.setattr(api_mod.thumbs, "many", fake_many)
    gui.thumbs([f"/p/{i}.jpg" for i in range(500)], size=99999)
    assert seen["n"] == api_mod._THUMB_BATCH_MAX
    assert seen["size"] == 400


def test_image_data_reports_unreadable_photo(gui, tmp_path):
    r = gui.image_data(str(tmp_path / "nope.jpg"))
    assert r["ok"] is False and r["error"]


# ---------- progress throttling ----------

def _events(cb, stage, n, total=None, detail=None):
    for i in range(n):
        cb(ProgressEvent(stage=stage, done=i + 1, total=total or n,
                         current=f"/p/{i}.jpg", detail=detail))


def test_progress_is_rate_limited(gui, monkeypatch):
    """One push per copied file saturated the WebView thread — the same thread
    that delivers 「取消」 back to Python, which is why the button did nothing.

    5000 files copied over 25s should cost ~15 pushes/s, not 5000."""
    now = [0.0]
    monkeypatch.setattr(api_mod.time, "monotonic", lambda: now[0])
    cb = gui._progress_cb()

    for i in range(5000):
        now[0] += 0.005  # 5ms per file
        cb(ProgressEvent(stage="execute", done=i + 1, total=5000,
                         current=f"/p/{i}.jpg"))

    pushed = len(gui._pushed)
    assert pushed <= 15 * 25 + 2, f"推送了 {pushed} 条，节流没生效"
    assert pushed >= 15 * 25 * 0.8, f"只推送了 {pushed} 条，进度会看起来卡顿"


def test_final_event_of_a_stage_always_lands(gui, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(api_mod.time, "monotonic", lambda: now[0])
    cb = gui._progress_cb()

    _events(cb, "execute", 500)

    last = gui._pushed[-1][1]
    assert (last["done"], last["total"]) == (500, 500), "进度条必须停在完整的 N/N"


def test_tally_counts_every_photo_despite_dropped_frames(gui, monkeypatch):
    """The live tally accumulates off all events, not the sampled ones."""
    now = [0.0]
    monkeypatch.setattr(api_mod.time, "monotonic", lambda: now[0])
    cb = gui._progress_cb()

    _events(cb, "analyze", 100, detail={"persons": ["张三"]})
    _events(cb, "analyze", 40, detail={"persons": ["张三", "李四"]})

    tally = dict(gui._pushed[-1][1]["tally"])
    assert tally == {"张三": 140, "李四": 40}


def test_a_new_stage_is_never_dropped(gui, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(api_mod.time, "monotonic", lambda: now[0])
    cb = gui._progress_cb()

    _events(cb, "analyze", 50)
    cb(ProgressEvent(stage="plan", done=3, total=3))
    cb(ProgressEvent(stage="finalize", done=0, total=1))

    stages = [p["stage"] for _e, p in gui._pushed]
    assert "plan" in stages and "finalize" in stages
