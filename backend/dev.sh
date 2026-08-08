#!/usr/bin/env bash
#
# Start the NekoSalesAI development server.
#
#   ./dev.sh
#
# Applies migrations, seeds demo data, then serves with autoreload on
# http://127.0.0.1:8000. Safe to run repeatedly — migrations and seeding are
# both idempotent.

set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
PYTHON=".venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "No virtualenv found at .venv"
    echo "Create it first:"
    echo "    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

echo "==> Applying database migrations"
.venv/bin/alembic upgrade head

echo "==> Seeding demo data"
"$PYTHON" -m app.seed

echo "==> Starting server on http://${HOST}:${PORT}"
exec "$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
