# PROGRESS

## CURRENT STATE / NEXT STEP
- Project name: **Docly** (owner-chosen; replaces "Nexto" in the spec).
- Phase 0 done (skeleton, health endpoints, tooling, dev compose, CI file).
- NEXT: Phase 1 — data model, Alembic migrations (btree_gist, exclusion constraint, RLS), seed script.
- Not yet done in Phase 0: frontend skeleton (scheduled for Phase 6), CI never run remotely (no remote).

## Log
- 2026-11-15 Phase 0: env checked (see ENVIRONMENT.md). Installed uv 0.13.8 + Python 3.12.16 user-level.
  `ruff check`: clean; `mypy app`: no issues; `pytest`: 2 passed; `docker compose up`: postgres+redis healthy;
  `/ready` returned `{"status":"ready"}`.
