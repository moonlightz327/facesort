"""App-managed people library persisted on disk so a photographer's samples
survive across sessions. Layout mirrors what the core pipeline already expects:

    <app_support>/FaceSort/people/<person>/<copied sample photos>

The GUI copies chosen sample photos in here; `samples_dir` for the pipeline is
just this `people/` directory, so no core changes are needed."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..core.imageio import is_image_file
from ..core.templates import sanitize_component


def app_support_dir() -> Path:
    """Per-user data directory, platform-appropriate."""
    import os
    import sys
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "FaceSort"
    elif sys.platform == "win32":
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        base = Path(root) / "FaceSort"
    else:
        root = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        base = Path(root) / "FaceSort"
    base.mkdir(parents=True, exist_ok=True)
    return base


class PeopleLibrary:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else (app_support_dir() / "people")
        self.root.mkdir(parents=True, exist_ok=True)

    def _person_dir(self, name: str) -> Path:
        safe = sanitize_component(name.strip())
        if not safe:
            raise ValueError("人名不能为空")
        return self.root / safe

    def list_people(self) -> list[dict]:
        people = []
        for d in sorted(p for p in self.root.iterdir() if p.is_dir()):
            samples = sorted(str(f) for f in d.iterdir()
                             if f.is_file() and is_image_file(f))
            people.append({"name": d.name, "samples": samples})
        return people

    def add_person(self, name: str) -> str:
        d = self._person_dir(name)
        d.mkdir(parents=True, exist_ok=True)
        return d.name

    def remove_person(self, name: str) -> None:
        d = self._person_dir(name)
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)

    def add_samples(self, name: str, source_paths: list[str]) -> list[str]:
        """Copy chosen photos into the person's folder (never move originals).
        Returns the list of destination paths for the newly added samples."""
        d = self._person_dir(name)
        d.mkdir(parents=True, exist_ok=True)
        added: list[str] = []
        for src in source_paths:
            src_p = Path(src)
            if not src_p.is_file() or not is_image_file(src_p):
                continue
            dst = d / src_p.name
            n = 0
            while dst.exists():
                n += 1
                dst = d / f"{src_p.stem}-{n}{src_p.suffix}"
            shutil.copy2(src_p, dst)
            added.append(str(dst))
        return added

    def remove_sample(self, sample_path: str) -> None:
        p = Path(sample_path)
        # Only allow deleting inside the managed library.
        if self.root in p.resolve().parents and p.is_file():
            p.unlink()

    def is_empty(self) -> bool:
        return not any(
            d.is_dir() and any(is_image_file(f) for f in d.iterdir() if f.is_file())
            for d in self.root.iterdir()
        )
