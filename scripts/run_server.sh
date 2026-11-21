#!/usr/bin/env bash
# Start the FastAPI app (serves web/ and /api/*). Usage: bash scripts/run_server.sh
# Environment: HOST (default 127.0.0.1), PORT (default 8000), PYTHON.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1 && python3 -c "import sys" >/dev/null 2>&1; then PY=python3; else PY=python; fi
fi
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
cd "$ROOT"
echo "Serving on http://$HOST:$PORT/  (API: /api/health, /api/indicators, /api/values)"
exec "$PY" -I -m uvicorn app:app --app-dir "$ROOT/src" --host "$HOST" --port "$PORT"
