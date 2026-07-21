"""Open the FaceSort window: a native macOS WKWebView (via pywebview) hosting
the built React app in facesort/gui/static/. The Python Api bridges to the core
pipeline."""

from __future__ import annotations

from pathlib import Path

from .api import Api

STATIC_DIR = Path(__file__).parent / "static"
INDEX = STATIC_DIR / "index.html"


def launch() -> None:
    import webview

    if not INDEX.exists():
        raise SystemExit(
            "前端尚未构建。请先运行:\n"
            "  cd webui && npm install && npm run build\n"
            f"（构建产物应输出到 {STATIC_DIR}）"
        )

    api = Api()
    window = webview.create_window(
        "FaceSort 分图",
        url=str(INDEX),
        js_api=api,
        width=1180,
        height=820,
        min_size=(920, 640),
    )
    api.set_window(window)
    webview.start(http_server=True)
