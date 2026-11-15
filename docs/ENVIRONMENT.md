# Environment
Ubuntu 26.04, git 2.53.0, system Python 3.14.4 (project uses 3.12.16 via uv 0.13.8, installed user-level from PyPI `uv`),
Node 26.13.1, npm 11.20.0, pnpm 12.18.0, Docker 29.9.3, Compose 5.7.1.
Dependencies are pinned by `backend/uv.lock`. Dev compose uses host ports 5442 (Postgres) and 6390 (Redis) because
5432/5433 are used by other services on this machine. Other containers on this host are not touched.
