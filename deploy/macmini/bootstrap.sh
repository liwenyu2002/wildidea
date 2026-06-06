#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$APP_DIR"

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .

mkdir -p data outputs/web

if [[ ! -f .env ]]; then
  cp deploy/macmini/wildidea.env.example .env
  echo "Created .env from deploy/macmini/wildidea.env.example. Fill API keys before starting."
fi

.venv/bin/python - <<'PY'
from wildidea.web.database import init_db
init_db()
print("Database initialized.")
PY

echo
echo "Bootstrap complete."
echo "Start locally with: deploy/macmini/start.sh"
echo "Hermes upstream: http://127.0.0.1:8000"
