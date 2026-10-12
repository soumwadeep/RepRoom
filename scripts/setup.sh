#!/usr/bin/env bash
# One-time setup: venv, dependencies, pose models.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
VENV="$ROOT/.venv"

if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -e "$ROOT/packages/rep-engine[detect,dev]"
"$VENV/bin/pip" install -q fastapi "uvicorn[standard]" httpx pytest numpy pillow boto3

mkdir -p "$ROOT/models"
for name in lite full; do
  dest="$ROOT/models/pose_landmarker_${name}.task"
  if [[ ! -f "$dest" ]]; then
    url="https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_${name}/float16/1/pose_landmarker_${name}.task"
    echo "downloading ${name}"
    curl -fsSL -o "$dest" "$url"
  fi
done

echo
echo "ready. next:"
echo "  $VENV/bin/python -m pytest packages services     # 67 tests, no GPU needed"
echo "  scripts/dev.sh                                   # API on http://localhost:8420"
