"""Engine + per-transaction tenant context.

Every request runs in ONE transaction. `SET LOCAL` (set_config(..., true)) scopes the
tenant to that transaction only, so pooled connections can never leak a tenant.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _maker
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
        _maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def reset_engine() -> None:
    global _engine, _maker
    if _engine is not None:
        await _engine.dispose()
    _engine = _maker = None


def _sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _maker is not None
    return _maker


@asynccontextmanager
async def tenant_session(clinic_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    async with _sessionmaker()() as session, session.begin():
        await session.execute(text("SELECT set_config('app.current_clinic_id', :c, true)"), {"c": str(clinic_id)})
        yield session


@asynccontextmanager
async def system_session() -> AsyncIterator[AsyncSession]:
    """Explicit RLS escape hatch: auth lookups, public slug resolution, background jobs."""
    async with _sessionmaker()() as session, session.begin():
        await session.execute(text("SELECT set_config('app.system', 'on', true)"))
        yield session
