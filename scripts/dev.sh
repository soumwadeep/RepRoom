#!/usr/bin/env bash
# Run the session API locally with the real detector.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
VENV="$ROOT/.venv/bin/python"

if [[ ! -x "$VENV" ]]; then
  echo "no venv at $VENV -- run scripts/setup.sh first" >&2
  exit 1
fi

echo "API      http://localhost:${PORT:-8420}"
echo "capture  http://localhost:${PORT:-8420}/capture"
echo "TV polls http://$(ipconfig getifaddr en0 2>/dev/null || echo 127.0.0.1):${PORT:-8420}/session/<id>"
echo

cd "$ROOT/services/session-api"
exec "$VENV" -m uvicorn app:app --host 0.0.0.0 --port "${PORT:-8420}" --log-level info
