# PROGRESS

## CURRENT STATE / NEXT STEP
- Project name: **Docly** (owner-chosen; replaces "Nexto" in the spec).
- Done: Phases 0-8 (backend, frontend, hardening, deploy artifacts). Prod stack verified LOCALLY only; NOT deployed (BLOCKERS B3).
- NEXT (Phase 9, not done): README.md (problem, features, screenshots in docs/screenshots, Mermaid, design decisions, one-command run,
  load-test table: 2743 req, 0 failures, p95 38 ms, p99 92 ms, local/indicative), docs/uz/LEARN.md (Uzbek, per phase + 3 interview Q&A),
  final full test run (last: 67 passed), final report in Uzbek.
- Browser-verified so far: public booking, login, calendar, signup, doctor create + services + hours UI (save hours/time off/week view/mobile NOT checked).
- Frontend has no automated tests.

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
- 2026-11-15 Phase 7: global per-IP + login/signup rate limits (Redis, fail-open if Redis is down), JSON access logs with request_id, prod config guards
  (refuses default JWT secret / fake OTP / default DB password), runtime DB role password from APP_DB_PASSWORD (migration edited in place: pre-release).
  Backup: infra/backup/backup.sh (custom-format pg_dump, keeps newest N: ran 5x with KEEP=3 -> 3 files). Restore TESTED: restored dump into scratch DB
  `docly_restore_test`, row counts equal to live (clinics 2, users 2, doctors 2, appointments 1, working_hours 20), exclusion constraint + 11 RLS policies present; scratch DB dropped.
  Load test (locust, 50 users, 60 s, local, 1 uvicorn worker): 2743 requests, 0 failures, p50 15 ms, p95 38 ms, p99 92 ms, ~46 req/s (bounded by user think time).
  BUG FOUND by the barrier race test (failed 3/3 runs): concurrent inserts into the GiST exclusion constraint can raise 40P01 deadlock_detected (-> would be HTTP 500).
  Fix: pg_advisory_xact_lock per doctor before insert/reschedule + treat 40P01 like 23P01 (-> 409 SLOT_TAKEN). Race test then passed 4/4 runs; full suite green.
