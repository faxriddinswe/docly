#!/usr/bin/env bash
# One-command local run: infra + migrations + seed + API (:8000) + web (:3000). Ctrl+C stops API/web.
set -euo pipefail
cd "$(dirname "$0")/.."
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
docker compose up -d --wait
(cd backend && "$UV" sync -q && "$UV" run alembic upgrade head && "$UV" run python -m app.seed)
(cd frontend && pnpm install --frozen-lockfile >/dev/null)
trap 'kill 0' EXIT
(cd backend && exec "$UV" run uvicorn app.main:app --port 8000) &
(cd frontend && exec pnpm dev -p 3000) &
wait
