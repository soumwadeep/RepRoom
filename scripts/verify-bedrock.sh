#!/usr/bin/env bash
# Verify the Bedrock path against the real account, end to end.
#
# This exercises the same code the television uses -- the session API's cue
# endpoint -- rather than a parallel script that could pass while the product
# still falls back. If it prints "rules", that is the truth about the account and
# the reason line says why.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PY="$ROOT/.venv/bin/python"
BASE="${REPROOM_API:-http://127.0.0.1:8420}"
STARTED_OWN=0

if [[ ! -x "$PY" ]]; then
  echo "no venv at $PY -- run scripts/setup.sh" >&2
  exit 1
fi

if ! curl -fsS -m 2 "$BASE/health" >/dev/null 2>&1; then
  echo "no API at $BASE -- starting one on 127.0.0.1:8424 for this run"
  (cd "$ROOT/services/session-api" && "$PY" -m uvicorn app:app --host 127.0.0.1 --port 8424 \
    > /tmp/reproom_verify.log 2>&1 &)
  BASE="http://127.0.0.1:8424"
  STARTED_OWN=1
  for _ in $(seq 1 20); do
    sleep 1
    curl -fsS -m 2 "$BASE/health" >/dev/null 2>&1 && break
  done
fi

cleanup() {
  if [[ "$STARTED_OWN" == "1" ]]; then
    pkill -f "uvicorn app:app --host 127.0.0.1 --port 8424" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo
echo "=== 1. what the account will serve ==="
curl -fsS "$BASE/coach/status?probe=true" | "$PY" -m json.tool

echo
echo "=== 2. one real cue, through the endpoint the TV uses ==="
SID=$(curl -fsS -X POST "$BASE/session" -H 'content-type: application/json' \
  -d '{"exercise":"squat","view":"side"}' | "$PY" -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -fsS "$BASE/session/$SID/cue" | "$PY" -c "
import json, sys
cue = json.load(sys.stdin)
print('source :', cue['source'], '(label shown on the TV:', cue['label'] + ')')
print('model  :', cue['model'])
print('latency:', cue['latency_ms'], 'ms')
print('reason :', cue['reason'])
print('cue    :', cue['text'])
print()
print('VERIFIED against the live account' if cue['source'] == 'bedrock'
      else 'NOT YET: the account could not serve a cue, so this is the fallback path')
"
curl -fsS -X DELETE "$BASE/session/$SID" >/dev/null

echo
echo "=== 3. three more in a row, to see whether it holds ==="
SID=$(curl -fsS -X POST "$BASE/session" -H 'content-type: application/json' \
  -d '{"exercise":"squat","view":"side"}' | "$PY" -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
for _ in 1 2 3; do
  curl -fsS "$BASE/session/$SID/cue" | "$PY" -c "
import json, sys
c = json.load(sys.stdin)
print(f\"  {c['source']:7} {str(c['latency_ms']) + ' ms':>9}  {c['text'][:72]}\")"
done
curl -fsS -X DELETE "$BASE/session/$SID" >/dev/null
