"""Execution-provider selection for the recognition model.

Measured on an M-series Mac, a 24MP six-face frame: 515ms/photo on the CPU
provider, 61ms on CoreML — 8.4x, with embeddings agreeing to cosine 0.9998 and
identical boxes and detection scores. The rules that make that safe to turn on
by default are what these tests hold: try the fast path, and never let it be the
reason a run fails."""

from __future__ import annotations

import sys

import numpy as np
import pytest

from facesort.core import engine as engine_mod
from facesort.core.engine import FaceEngine


class FakeApp:
    def __init__(self, providers, provider_options=None, fail=False, **kw):
        self.providers = providers
        self.provider_options = provider_options
        self._fail = fail

    def prepare(self, **kw):
        pass

    def get(self, img):
        if self._fail:
            raise RuntimeError("CoreML compile failed")
        return []


@pytest.fixture
def fake_insightface(monkeypatch):
    """Intercept FaceAnalysis and record how each attempt was constructed."""
    calls: list[dict] = []
    failing: set[str] = set()

    def factory(name=None, allowed_modules=None, providers=None,
                provider_options=None, **kw):
        calls.append({"providers": list(providers or []),
                      "options": provider_options})
        fail = any(p in failing for p in (providers or []))
        return FakeApp(providers, provider_options, fail=fail)

    import insightface.app as ia
    monkeypatch.setattr(ia, "FaceAnalysis", factory)
    return calls, failing


def test_prefers_coreml_when_available(monkeypatch, fake_insightface):
    calls, _failing = fake_insightface
    monkeypatch.setattr(engine_mod, "coreml_available", lambda: True)

    e = FaceEngine()
    e._build_app()

    assert e.provider == "CoreML"
    assert calls[0]["providers"][0] == "CoreMLExecutionProvider"
    assert "CPUExecutionProvider" in calls[0]["providers"], "必须保留 CPU 兜底"


def test_compiled_model_is_cached_on_disk(monkeypatch, fake_insightface):
    """~10s of graph compilation, once, instead of on every launch."""
    calls, _failing = fake_insightface
    monkeypatch.setattr(engine_mod, "coreml_available", lambda: True)

    FaceEngine()._build_app()

    assert calls[0]["options"][0].get("ModelCacheDirectory")


def test_falls_back_to_cpu_when_coreml_fails(monkeypatch, fake_insightface):
    """A machine where the accelerated path breaks still sorts photos."""
    calls, failing = fake_insightface
    failing.add("CoreMLExecutionProvider")
    monkeypatch.setattr(engine_mod, "coreml_available", lambda: True)

    e = FaceEngine()
    e._build_app()

    assert e.provider == "CPU"
    assert len(calls) == 2
    assert calls[1]["providers"] == ["CPUExecutionProvider"]


def test_use_gpu_false_goes_straight_to_cpu(monkeypatch, fake_insightface):
    calls, _failing = fake_insightface
    monkeypatch.setattr(engine_mod, "coreml_available", lambda: True)

    e = FaceEngine(use_gpu=False)
    e._build_app()

    assert e.provider == "CPU"
    assert len(calls) == 1


def test_cpu_only_platform_needs_no_coreml(monkeypatch, fake_insightface):
    calls, _failing = fake_insightface
    monkeypatch.setattr(engine_mod, "coreml_available", lambda: False)

    e = FaceEngine()
    e._build_app()

    assert e.provider == "CPU"
    assert calls[0]["providers"] == ["CPUExecutionProvider"]


def test_total_failure_still_raises(monkeypatch, fake_insightface):
    """Falling back is not the same as swallowing: if nothing loads, say so."""
    calls, failing = fake_insightface
    failing.update({"CoreMLExecutionProvider", "CPUExecutionProvider"})
    monkeypatch.setattr(engine_mod, "coreml_available", lambda: True)

    with pytest.raises(RuntimeError):
        FaceEngine()._build_app()


def test_coreml_availability_is_false_off_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert engine_mod.coreml_available() is False
