"""Persisted app settings.

Everything the user configures in the 设置 page lives here, so preferences and
(most importantly) a pre-installed recognition model survive a restart instead
of being re-chosen on every launch.

Stored as JSON next to the people library:

    <app_support>/FaceSort/settings.json
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .library import app_support_dir

# Only these keys are persisted; anything else in an incoming payload is
# ignored so a stale or hand-edited file cannot inject arbitrary config.
DEFAULTS: dict[str, Any] = {
    "threshold": 0.40,
    "multiPerson": "primary",
    "folderTemplate": "{person}",
    "fileTemplate": "{orig_name}{ext}",
    "minFace": 40,
    "move": False,
    "groupSubfolders": False,
    "workers": 0,          # 0 = auto
    "decodeMaxSide": 1400,  # 0 = full-resolution decode
    "modelUrl": "",        # optional custom download source
}

_lock = threading.Lock()


def settings_path() -> Path:
    return app_support_dir() / "settings.json"


def load() -> dict[str, Any]:
    """Stored settings merged over the defaults. Never raises: a corrupt file
    falls back to defaults rather than blocking startup."""
    out = dict(DEFAULTS)
    p = settings_path()
    try:
        with _lock:
            raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in DEFAULTS and type(v) is type(DEFAULTS[k]):
                    out[k] = v
                elif k in DEFAULTS and isinstance(DEFAULTS[k], float):
                    try:
                        out[k] = float(v)
                    except (TypeError, ValueError):
                        pass
    except (OSError, ValueError):
        pass
    return out


def save(values: dict[str, Any]) -> dict[str, Any]:
    """Merge `values` into the stored settings and write them back."""
    current = load()
    for k, v in (values or {}).items():
        if k in DEFAULTS:
            current[k] = v
    p = settings_path()
    try:
        with _lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(p)
    except OSError:
        pass  # a read-only home shouldn't break the session
    return current


def reset() -> dict[str, Any]:
    try:
        settings_path().unlink(missing_ok=True)
    except OSError:
        pass
    return dict(DEFAULTS)
