#!/usr/bin/env bash
# Real-engine smoke test. Downloads the buffalo_l model on first run (~300MB).
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run python scripts/smoke_test.py
