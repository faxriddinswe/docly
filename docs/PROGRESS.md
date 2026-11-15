# PROGRESS

## CURRENT STATE / NEXT STEP
- Project name: **Docly** (owner-chosen; replaces "Nexto" in the spec).
- Done: Phases 0-6 (backend features + frontend).
- NEXT: Phase 7 — hardening: global rate limiting, structured request logs, refuse fake OTP sender in prod, load test (k6/locust) with README table,
  nightly pg_dump backup + tested restore. Then Phase 8 deploy (Dockerfiles, prod compose, edge caddy, deploy.sh, CI/CD), Phase 9 final docs.
- Frontend has no automated tests yet (only tsc/eslint/next build + a manual browser run); consider Playwright.

## Log
- 2026-11-15 Phase 0: env checked (see ENVIRONMENT.md). Installed uv 0.13.8 + Python 3.12.16 user-level.
  `ruff check`: clean; `mypy app`: no issues; `pytest`: 2 passed; `docker compose up`: postgres+redis healthy;
  `/ready` returned `{"status":"ready"}`.
- 2026-11-15 Phase 1: models + Alembic 305c428b06be (btree_gist, exclusion constraint, RLS with FORCE, role docly_app).
  `alembic upgrade head / downgrade base / upgrade head` OK; seed ran; pytest: 5 passed (real Postgres 16 via testcontainers).
- 2026-11-15 Phase 2: auth (argon2, JWT access, hashed rotating refresh with reuse detection), staff + superadmin endpoints,
  migration 0002 (refresh_tokens.clinic_id). ruff clean, mypy clean, pytest: 15 passed. Fixed along the way: asyncpg needs
  real datetime/time objects (not strings); server-side column defaults needed for raw SQL inserts; family revocation must
  commit before the 401 is raised.
- 2026-11-15 Phase 3: doctors/services/working-hours/time-off CRUD, pure domain.availability (9 unit tests), /public/{slug} and
  /public/{slug}/availability. ruff+mypy clean; pytest: 41 passed (incl. 13 parametrized cross-tenant endpoint checks).
- 2026-11-15 Phase 4: public booking (OTP via Redis, fake sender; Eskiz sender written but unverified), staff appointments, patients,
  manage-token cancel/reschedule, status transitions, audit. pytest: 51 passed. Concurrency: 12 parallel requests -> exactly one 201.
  Finding: in-process ASGI requests serialize enough that the service pre-check catches losers, so a second test uses an
  asyncio.Barrier inside the real availability check to force a true race decided only by the PG exclusion constraint (10 racers -> 1x201, 9x SLOT_TAKEN).
- 2026-11-15 Phase 5: Transport interface (+Fake, Aiogram), 64-char HMAC deep-link token, bot flow (/start, confirm/cancel callbacks authorised by chat id),
  reminder scanner with claim-then-send idempotency + row lock, ARQ worker (cron every minute). pytest: 60 passed (x2 runs, stable).
  Found+fixed: test pollution (shared DB) -> truncate per test; candidate query must test lower(during) in window, not range overlap.
- 2026-11-15 Phase 6: stats endpoint (+test), CORS, ManageOut (clinic slug/tz for patient reschedule), dev-only OTP hint endpoint (not registered when ENV=prod).
  Frontend: Next.js 16 (cacheComponents disabled, output standalone), TanStack Query, openapi-typescript types, public wizard, manage page, dashboard
  (calendar day/week grid, appointments, doctors+hours+time off+services, patients, stats), superadmin page. `tsc`, `eslint`, `next build`: clean.
  Manual browser run (Chrome): public booking end-to-end -> appears in dashboard calendar. Bug found by that run and fixed: auth fetch wrapper treated /auth/me as
  public (no bearer) -> 401 loop. NOT browser-tested yet: signup, doctors editor, time off, superadmin, week view, mobile widths, reschedule on manage page.
