#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

# Runs migrations as a one-shot bootstrap step against the configured DATABASE_URL.
docker compose run --rm core-svc python -m app.bootstrap

echo "Database bootstrap complete (alembic upgrade head)."
