# PROGRESS

## CURRENT STATE / NEXT STEP
- Project name: **Docly** (owner-chosen; replaces "Nexto" in the spec).
- Done: Phases 0-3 (skeleton, data model+RLS, auth/tenancy, scheduling core + availability).
- NEXT: Phase 4 — booking: public flow with fake OTP (Redis), constraint->409 SLOT_TAKEN, concurrency test, cancel/reschedule, audit.
  Add every new tenant endpoint to ENDPOINTS in backend/tests/test_isolation.py.
- Not done yet: frontend (Phase 6), CI never run remotely (no remote), no Redis usage yet.

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
