#!/usr/bin/env bash
# Run the session API over HTTPS so a phone browser will hand over its camera.
#
# A browser only grants getUserMedia to a secure origin. http://192.168.x.x on a
# laptop is fine, but on a phone it is not -- which is the single most annoying
# constraint in this whole build, and the reason this script exists. Self-signed
# certs mean one tap through a warning on the phone.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
VENV="$ROOT/.venv/bin/python"
CERT_DIR="$ROOT/.tls"
PORT="${PORT:-8420}"

if [[ ! -x "$VENV" ]]; then
  echo "no venv at $VENV -- run scripts/setup.sh first" >&2
  exit 1
fi

mkdir -p "$CERT_DIR"
HOST="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1)"

if [[ ! -f "$CERT_DIR/key.pem" || -z "$(openssl x509 -in "$CERT_DIR/cert.pem" -noout -checkend 86400 2>/dev/null)" ]]; then
  echo "issuing a self-signed certificate for $HOST"
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" \
    -days 30 -subj "/CN=$HOST" \
    -addext "subjectAltName=IP:$HOST,DNS:localhost" >/dev/null 2>&1
fi

echo
echo "  on this Mac          https://localhost:$PORT/capture"
echo "  on your phone        https://$HOST:$PORT/capture"
echo "  on the Fire TV app   https://$HOST:$PORT   (self-signed: set REPROOM_INSECURE_TLS=1)"
echo
echo "Expect a certificate warning on the phone. Accept it once, then load the page."

cd "$ROOT/services/session-api"
exec "$VENV" -m uvicorn app:app \
  --host 0.0.0.0 --port "$PORT" \
  --ssl-keyfile "$CERT_DIR/key.pem" --ssl-certfile "$CERT_DIR/cert.pem"
