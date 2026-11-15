# Decisions
## D1 Project name
Docly (owner message during Phase 0). Caddy snippet will be deploy/docly.caddy.
## D2 Tooling
uv for Python (lockfile, fast, official Astral package from PyPI); Python 3.12 as required by spec though system has 3.14.
Dev DB/Redis host ports 5442/6390 to avoid collisions. mypy strict on app.domain and app.services only, per spec.
