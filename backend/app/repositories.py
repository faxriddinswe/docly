"""Application-level tenant scoping (layer 1; PostgreSQL RLS is layer 2).

The clinic_id comes from the authenticated principal, never from a request body.
"""

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

M = TypeVar("M")


class ScopedRepo(Generic[M]):  # noqa: UP046
    def __init__(self, session: AsyncSession, model: Any, clinic_id: uuid.UUID) -> None:
        self.session: AsyncSession = session
        self.model: Any = model
        self.clinic_id = clinic_id

    def _q(self) -> Any:
        return select(self.model).where(self.model.clinic_id == self.clinic_id)

    async def get(self, id_: uuid.UUID) -> M | None:
        res = await self.session.execute(self._q().where(self.model.id == id_))
        obj: M | None = res.scalar_one_or_none()
        return obj

    async def list(self, limit: int = 50, offset: int = 0) -> list[M]:
        res = await self.session.execute(self._q().limit(limit).offset(offset))
        return list(res.scalars().all())

    async def add(self, **fields: Any) -> M:
        fields.pop("clinic_id", None)  # never trust a caller-supplied tenant
        obj: M = self.model(clinic_id=self.clinic_id, **fields)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def delete(self, obj: M) -> None:
        await self.session.delete(obj)
        await self.session.flush()
