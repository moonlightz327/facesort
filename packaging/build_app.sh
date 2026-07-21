#!/usr/bin/env bash
# Build FaceSort.app: front-end -> single index.html, then PyInstaller bundle.
# Output: dist/FaceSort.app  (double-clickable; downloads the model on first use)
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> 构建前端"
( cd webui && npm install && npm run build )

echo "==> 打包 .app（PyInstaller）"
uv run pyinstaller packaging/FaceSort.spec --noconfirm --distpath dist --workpath build

echo "==> 自检（冻结环境加载模型并识别）"
FACESORT_SELFTEST=1 "dist/FaceSort.app/Contents/MacOS/FaceSort" 2>/dev/null | grep SELFTEST || {
  echo "自检失败：ML 栈在打包后未能正常运行" >&2; exit 1; }

rm -rf build
echo "==> 完成：dist/FaceSort.app"
