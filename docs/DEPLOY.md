# DEPLOY

**Status: NOT deployed to a public server** (no `.env.deploy`; see BLOCKERS B3). What follows is what exists and what was actually verified.

## Topology (shared VPS)
Shared edge Caddy (`/opt/edge`, docker network `edge`, `import` of `/opt/edge/sites/*.caddy`) -> `deploy/docly.caddy` routes
`/api/*` (prefix stripped) to `docly-api:8000` and everything else to `docly-web:3000`. Compose project `docly` (`deploy/docker-compose.prod.yml`):
postgres, redis, migrate (one-shot), api, worker, frontend, backup, and `bot` (profile `telegram`, only when a bot token is set).
No host ports are published; `restart: unless-stopped`, healthchecks, named volumes, json-file log rotation (10 MB x 3), memory limits
(api 384m, worker 256m, postgres 384m, redis 128m, frontend 192m, bot 128m, backup 64m: these are ceilings).

## Commands
- Deploy: `cp .env.deploy.example .env.deploy` (fill in) then `scripts/deploy.sh`. Dry run: `DRY_RUN=1 scripts/deploy.sh`.
- Smoke test any URL: `scripts/smoke.sh https://docly.example.com` (read-only; `--write` creates a throwaway clinic, local/staging only).
- Secrets are generated on the server on first deploy into `/opt/docly/.env.prod` (mode 600) and never leave it.

## What was verified (2026-11-15, local machine, not the VPS)
Images built (`docly-api` 489 MB, `docly-web` 296 MB). Prod compose started as project `docly-prodtest` behind a throwaway Caddy on a private docker network:
all services healthy (api, worker via `arq --check`, frontend, postgres, redis); `migrate` exited 0 using the owner DB role while the app ran as the
non-superuser `docly_app` (RLS enforced) with `ENV=prod`; `scripts/smoke.sh http://localhost:8088 --write` -> **SMOKE OK (11/11 checks)**; in-stack backup
ran. Idle memory: api 74 MiB, worker 55, frontend 34, postgres 22, redis 4 (~190 MiB total, far below the ~900 MB target; limits kept as headroom).
The throwaway stack, network and volumes were removed afterwards.
Caddy snippet validated with real Caddy (`caddy validate`: Valid configuration).

## NOT verified
Remote steps of `deploy.sh` against a real server (edge creation, image shipping, Caddy reload on a shared edge, automatic TLS, rollback path),
GitHub Actions workflows (never run: no remote), real Eskiz SMS and Telegram.

## Rollback
`deploy.sh` tags the previous images `:prev` before shipping and, if the public smoke test fails, redeploys `IMAGE_TAG=prev` automatically.
Manual: `cd /opt/docly && IMAGE_TAG=prev COMPOSE_PROJECT_NAME=docly docker compose --env-file .env.prod -f docker-compose.prod.yml up -d`.
DB migrations are forward-only in prod; a rollback of a schema change needs `alembic downgrade` run deliberately (see RUNBOOK).

## CI/CD (`.github/workflows/ci.yml`)
PR + main: backend (ruff, mypy, pytest with testcontainers), frontend (tsc, eslint, build), OpenAPI/TS types in sync. main only: build+push images to GHCR;
deploy job runs only if `DEPLOY_HOST` and `DEPLOY_SSH_KEY` secrets exist (presence checked in a separate job because `secrets` cannot be used in `if:`).
