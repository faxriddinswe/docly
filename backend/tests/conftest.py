from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def pg_urls() -> Iterator[dict[str, str]]:
    """Real PostgreSQL 16 in a container, migrated with Alembic (no SQLite, no mocks)."""
    with PostgresContainer(
        "postgres:16-alpine", username="docly", password="docly", dbname="docly"
    ) as pg:
        host, port = pg.get_container_host_ip(), pg.get_exposed_port(5432)
        owner = f"postgresql+asyncpg://docly:docly@{host}:{port}/docly"
        app = f"postgresql+asyncpg://docly_app:docly_app@{host}:{port}/docly"
        env = {**os.environ, "MIGRATION_DATABASE_URL": owner, "DATABASE_URL": app}
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True
        )
        yield {"owner": owner, "app": app}


@pytest.fixture
async def owner_engine(pg_urls: dict[str, str]) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(pg_urls["owner"])
    yield eng
    await eng.dispose()


@pytest.fixture
async def app_engine(pg_urls: dict[str, str]) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(pg_urls["app"])
    yield eng
    await eng.dispose()


@pytest.fixture(scope="session", autouse=True)
def _env(pg_urls: dict[str, str]) -> Iterator[None]:
    """Point the application at the test containers."""
    from app.core.config import get_settings

    os.environ["DATABASE_URL"] = pg_urls["app"]
    os.environ["MIGRATION_DATABASE_URL"] = pg_urls["owner"]
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from httpx import ASGITransport

    from app.db import reset_engine
    from app.main import create_app

    await reset_engine()  # engine must belong to this test's event loop
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        yield c
    await reset_engine()
