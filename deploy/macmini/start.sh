#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$APP_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export WILDIDEA_DATABASE_URL="${WILDIDEA_DATABASE_URL:-sqlite:///$APP_DIR/data/wildidea.db}"
export WILDIDEA_OUTPUT_DIR="${WILDIDEA_OUTPUT_DIR:-$APP_DIR/outputs/web}"

exec "$APP_DIR/.venv/bin/python" -m uvicorn wildidea.web.app:app \
  --host "${WILDIDEA_HOST:-127.0.0.1}" \
  --port "${WILDIDEA_PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips '*'
