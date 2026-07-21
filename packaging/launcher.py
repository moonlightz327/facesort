"""Frozen-app entry point: open the FaceSort GUI window.

If FACESORT_SELFTEST is set, run a headless check of the bundled ML stack
(onnxruntime + insightface load and run) instead of opening the window — used to
verify the packaged .app end-to-end."""

import os
import sys


def _selftest() -> int:
    from facesort.core.engine import FaceEngine

    eng = FaceEngine()
    # Run on insightface's bundled 6-person sample: exercises detection AND the
    # recognition embedding in the frozen context (proves the full ML path works).
    from insightface.data import get_image

    img = get_image("t1")
    analysis = eng.analyze_array(img, path="selftest")
    dim = int(analysis.faces[0].embedding.shape[0]) if analysis.faces else 0
    print(f"SELFTEST_OK faces={len(analysis.faces)} embedding_dim={dim}")
    return 0


def main() -> int:
    if os.environ.get("FACESORT_SELFTEST"):
        return _selftest()
    from facesort.gui.app import launch

    launch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
