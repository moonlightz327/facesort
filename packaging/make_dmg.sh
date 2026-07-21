#!/usr/bin/env bash
# Package dist/FaceSort.app into a drag-to-install dist/FaceSort.dmg.
set -euo pipefail
cd "$(dirname "$0")/.."

APP="dist/FaceSort.app"
DMG="dist/FaceSort.dmg"
VOL="FaceSort"

[ -d "$APP" ] || { echo "先构建 app：./packaging/build_app.sh" >&2; exit 1; }

STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"   # drag-to-install target
rm -f "$DMG"
hdiutil create -volname "$VOL" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"
echo "==> 完成：$DMG ($(du -h "$DMG" | cut -f1))"
