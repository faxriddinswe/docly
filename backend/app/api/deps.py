import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db import tenant_session
from app.models.tables import Clinic

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    clinic_id: uuid.UUID | None
    role: str | None
    is_superadmin: bool


async def get_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal:
    if creds is None:
        raise AppError("UNAUTHENTICATED", "Missing bearer token", 401)
    try:
        c = decode_access_token(creds.credentials)
    except jwt.PyJWTError as exc:
        raise AppError("UNAUTHENTICATED", "Invalid or expired token", 401) from exc
    return Principal(
        user_id=uuid.UUID(c["sub"]),
        clinic_id=uuid.UUID(c["cid"]) if c.get("cid") else None,
        role=c.get("role"),
        is_superadmin=bool(c.get("sa")),
    )


async def get_staff(p: Principal = Depends(get_principal)) -> Principal:
    if p.clinic_id is None or p.role is None:
        raise AppError("FORBIDDEN", "Clinic staff only", 403)
    return p


def require_roles(*roles: str) -> Callable[[Principal], Principal]:
    def dep(p: Principal = Depends(get_staff)) -> Principal:
        if p.role not in roles:
            raise AppError("FORBIDDEN", "Insufficient role", 403)
        return p

    return dep


async def get_superadmin(p: Principal = Depends(get_principal)) -> Principal:
    if not p.is_superadmin:
        raise AppError("FORBIDDEN", "Superadmin only", 403)
    return p


async def get_db(p: Principal = Depends(get_staff)) -> AsyncIterator[AsyncSession]:
    """Tenant-scoped session: RLS context is the token's clinic, never a request field."""
    assert p.clinic_id is not None
    async with tenant_session(p.clinic_id) as session:
        active = (
            await session.execute(select(Clinic.is_active).where(Clinic.id == p.clinic_id))
        ).scalar_one_or_none()
        if not active:
            raise AppError("CLINIC_SUSPENDED", "This clinic is suspended", 403)
        yield session
