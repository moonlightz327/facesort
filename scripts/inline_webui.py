#!/usr/bin/env python
"""Post-build step: inline the hashed JS/CSS bundles into a single self-contained
static/index.html. WKWebView (pywebview) is finicky about loading ES-module
sub-resources over the local http server; inlining sidesteps all MIME/CORS
concerns and makes packaging a single file trivial."""

from __future__ import annotations

import re
import sys
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "facesort" / "gui" / "static"


def main() -> int:
    index = STATIC / "index.html"
    if not index.exists():
        print(f"未找到 {index}，请先 npm run build", file=sys.stderr)
        return 1
    html = index.read_text(encoding="utf-8")

    def inline_script(m: re.Match) -> str:
        src = m.group("src")
        js = (STATIC / src.lstrip("./")).read_text(encoding="utf-8")
        return f"<script type=\"module\">\n{js}\n</script>"

    def inline_css(m: re.Match) -> str:
        href = m.group("href")
        css = (STATIC / href.lstrip("./")).read_text(encoding="utf-8")
        return f"<style>\n{css}\n</style>"

    html = re.sub(r'<script type="module"[^>]*\bsrc="(?P<src>[^"]+)"[^>]*></script>',
                  inline_script, html)
    html = re.sub(r'<link[^>]*\brel="stylesheet"[^>]*\bhref="(?P<href>[^"]+)"[^>]*>',
                  inline_css, html)

    index.write_text(html, encoding="utf-8")
    # Drop the now-inlined asset files so only index.html ships.
    assets = STATIC / "assets"
    if assets.is_dir():
        for f in assets.iterdir():
            f.unlink()
        assets.rmdir()
    size_kb = len(html.encode("utf-8")) / 1024
    print(f"已内联为单文件 index.html（{size_kb:.0f} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
