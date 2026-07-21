#!/usr/bin/env python
"""Generate the FaceSort app icon: an indigo rounded-square with camera focus
brackets around a simple smiley. Outputs a 1024px master PNG, a macOS .icns,
and a Windows .ico. Drawn at 4x and downscaled for crisp anti-aliased edges."""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
PACK = ROOT / "packaging"
S = 4  # supersample factor
N = 1024 * S


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _gradient(size: int, c0, c1) -> Image.Image:
    """Diagonal (top-left -> bottom-right) linear gradient."""
    grad = Image.new("RGB", (size, size))
    px = grad.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            px[x, y] = _lerp(c0, c1, t)
    return grad


def _rounded_mask(size: int, radius: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def build() -> Image.Image:
    # Background: indigo gradient in a rounded square.
    bg = _gradient(N, (129, 140, 248), (67, 56, 202))  # indigo-400 -> indigo-800
    icon = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    icon.paste(bg, (0, 0), _rounded_mask(N, int(0.225 * N)))

    d = ImageDraw.Draw(icon)
    white = (255, 255, 255, 240)

    # Camera focus brackets: four L-shaped corners inset from the edges.
    inset = int(0.245 * N)
    arm = int(0.145 * N)
    th = int(0.032 * N)          # bracket thickness
    r = th // 2
    lo, hi = inset, N - inset

    def hbar(x1, x2, y):
        d.rounded_rectangle([x1, y - r, x2, y + r], radius=r, fill=white)

    def vbar(x, y1, y2):
        d.rounded_rectangle([x - r, y1, x + r, y2], radius=r, fill=white)

    # top-left
    hbar(lo, lo + arm, lo); vbar(lo, lo, lo + arm)
    # top-right
    hbar(hi - arm, hi, lo); vbar(hi, lo, lo + arm)
    # bottom-left
    hbar(lo, lo + arm, hi); vbar(lo, hi - arm, hi)
    # bottom-right
    hbar(hi - arm, hi, hi); vbar(hi, hi - arm, hi)

    # Smiley inside the frame.
    cx, cy = N // 2, int(N * 0.5)
    eye_r = int(0.045 * N)
    eye_dx = int(0.115 * N)
    eye_y = cy - int(0.075 * N)
    for sx in (-1, 1):
        ex = cx + sx * eye_dx
        d.ellipse([ex - eye_r, eye_y - eye_r, ex + eye_r, eye_y + eye_r], fill=white)

    # Smile: thick rounded arc.
    smile_r = int(0.135 * N)
    smile_cy = cy - int(0.01 * N)
    sw = int(0.038 * N)
    box = [cx - smile_r, smile_cy - smile_r, cx + smile_r, smile_cy + smile_r]
    d.arc(box, start=25, end=155, fill=white, width=sw)
    # Round the smile ends.
    for ang in (25, 155):
        a = math.radians(ang)
        ex = cx + smile_r * math.cos(a)
        ey = smile_cy + smile_r * math.sin(a)
        d.ellipse([ex - sw / 2, ey - sw / 2, ex + sw / 2, ey + sw / 2], fill=white)

    return icon.resize((1024, 1024), Image.LANCZOS)


def make_icns(png1024: Path, out: Path) -> bool:
    if not shutil.which("iconutil"):
        return False
    iconset = PACK / "FaceSort.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)
    master = Image.open(png1024)
    specs = [(16, ""), (16, "@2x"), (32, ""), (32, "@2x"), (128, ""),
             (128, "@2x"), (256, ""), (256, "@2x"), (512, ""), (512, "@2x")]
    for base, suffix in specs:
        px = base * (2 if suffix else 1)
        master.resize((px, px), Image.LANCZOS).save(iconset / f"icon_{base}x{base}{suffix}.png")
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)
    shutil.rmtree(iconset)
    return True


def make_ico(png1024: Path, out: Path) -> None:
    Image.open(png1024).save(out, sizes=[(16, 16), (24, 24), (32, 32),
                                         (48, 48), (64, 64), (128, 128), (256, 256)])


def main() -> int:
    ASSETS.mkdir(exist_ok=True)
    PACK.mkdir(exist_ok=True)
    icon = build()
    png = ASSETS / "icon_1024.png"
    icon.save(png)
    print(f"wrote {png}")
    if make_icns(png, PACK / "FaceSort.icns"):
        print(f"wrote {PACK / 'FaceSort.icns'}")
    else:
        print("iconutil 不可用，跳过 .icns", file=sys.stderr)
    make_ico(png, PACK / "FaceSort.ico")
    print(f"wrote {PACK / 'FaceSort.ico'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
