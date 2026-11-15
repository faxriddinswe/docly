# RUNBOOK

## Local development
`docker compose up -d` (Postgres on 127.0.0.1:5442, Redis on 6390) -> `cd backend && uv sync && uv run alembic upgrade head && uv run python -m app.seed`
-> `uv run uvicorn app.main:app` ; `cd frontend && pnpm install && pnpm dev` (needs `NEXT_PUBLIC_API_URL`, default http://localhost:8000).
Seed logins (fake data): `owner@smile.example` / `owner@chilonzor.example`, password `demo-password-123`, clinics `smile-dental`, `chilonzor-medical`.
Create a platform superadmin: `SUPERADMIN_PASSWORD=... uv run python -m app.create_superadmin you@example.com`.
Worker: `uv run arq app.worker.WorkerSettings`; bot: `uv run python -m app.bot.main` (needs TELEGRAM_BOT_TOKEN).

## Production (on the server, in /opt/docly)
Alias: `dc() { COMPOSE_PROJECT_NAME=docly IMAGE_TAG=latest docker compose --env-file .env.prod -f docker-compose.prod.yml "$@"; }`
- status `dc ps`; logs `dc logs -f --tail=100 api` (JSON lines with `request_id`); stop `dc stop`; start `dc up -d`.
- Find one request across services: `dc logs api | grep <request_id>` (the id is also returned in the `x-request-id` header).

## Backups
Nightly 02:00 UTC (`backup` service) -> volume `backups`, newest 7 kept. Manual: `dc exec backup sh /backup.sh once`.
Copy a dump out: `docker cp docly-backup-1:/backups/<file> .` .
**Restore (tested locally)**: restore into a NEW database first, verify, then switch deliberately:
`dc exec -T postgres createdb -U docly docly_restore && dc exec -T backup sh -c 'pg_restore --no-owner -h postgres -U docly -d docly_restore /backups/<file>'`
then compare counts (`select count(*) ...` with `set_config('app.system','on',true)` because of FORCE RLS) and only then point the app at it / rename databases.
Local test result: dump -> scratch DB -> equal row counts, `appointments_no_overlap` and 11 RLS policies present.

## Rotate secrets
- JWT_SECRET: edit `.env.prod`, `dc up -d api worker`. All access tokens and manage/Telegram links become invalid (users log in again; refresh tokens survive - they are random DB values).
- DB passwords: `ALTER ROLE docly_app PASSWORD '...'` / `ALTER ROLE docly PASSWORD '...'` via `dc exec postgres psql -U docly`, update `.env.prod`, `dc up -d`.
- Eskiz/Telegram: update the values in `.env.prod`, `dc up -d --force-recreate api worker bot`.

## Common failures
| Symptom | Cause / fix |
|---|---|
| api restarts, log "JWT_SECRET must be set" / "OTP_SENDER=fake is not allowed" / "default dev password" | prod guard in `Settings.validate_prod`; fix `.env.prod` |
| `/ready` 503 | Postgres or Redis unhealthy: `dc ps`, `dc logs postgres redis` |
| 429 RATE_LIMITED for real users behind one NAT | per-IP limits (300/min global, 20/min login); raise `RATE_LIMIT_PER_MINUTE` etc. in the api env |
| Patients get no OTP | `OTP_SENDER=eskiz` needs valid `ESKIZ_*` (BLOCKERS B1); check api logs |
| No Telegram reminders | needs `TELEGRAM_BOT_TOKEN` + `bot` profile + patient linked via deep link; worker logs "reminders sent: N" |
| Booking 409 SLOT_TAKEN | expected when two people pick the same slot; the UI sends the patient back to pick another |
| Caddy cert not issued | DNS A record must point to the server and ports 80/443 reachable |
| Migration fails | `dc logs migrate`; the stack does not start the api until `migrate` exits 0 |
