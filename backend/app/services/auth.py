import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.models.tables import Clinic, ClinicMembership, RefreshToken, Role, User

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,60}$")
RESERVED_SLUGS = {"admin", "api", "auth", "health", "ready", "public", "login", "signup", "docs"}


class TokenReusedError(AppError):
    """Raised after the family is revoked; the CALLER must commit before surfacing it."""

    def __init__(self) -> None:
        super().__init__("TOKEN_REUSED", "Refresh token reuse detected; session revoked", 401)


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    clinic_id: uuid.UUID | None
    role: str | None


async def signup_clinic(
    session: AsyncSession,
    *,
    clinic_name: str,
    slug: str,
    email: str,
    password: str,
    full_name: str,
    timezone: str | None = None,
) -> tuple[User, Clinic]:
    slug = slug.lower()
    if not SLUG_RE.match(slug) or slug in RESERVED_SLUGS:
        raise AppError("INVALID_SLUG", "Slug must be 3-61 chars: a-z, 0-9, '-'", 422)
    email = email.strip().lower()
    if (await session.execute(select(User.id).where(User.email == email))).first():
        raise AppError("EMAIL_TAKEN", "Email already registered", 409)
    if (await session.execute(select(Clinic.id).where(Clinic.slug == slug))).first():
        raise AppError("SLUG_TAKEN", "Clinic address is taken", 409)
    clinic = Clinic(name=clinic_name, slug=slug, timezone=timezone or get_settings().default_timezone)
    user = User(email=email, password_hash=hash_password(password), full_name=full_name)
    session.add_all([clinic, user])
    try:
        await session.flush()
        session.add(ClinicMembership(clinic_id=clinic.id, user_id=user.id, role=Role.owner))
        await session.flush()
    except IntegrityError as exc:  # concurrent signup with same email/slug
        raise AppError("CONFLICT", "Email or clinic address already taken", 409) from exc
    return user, clinic


async def authenticate(
    session: AsyncSession, *, email: str, password: str, clinic_slug: str | None
) -> tuple[User, Clinic | None, Role | None]:
    user = (await session.execute(select(User).where(User.email == email.strip().lower()))).scalar_one_or_none()
    # Same error for unknown user / bad password / inactive: no account enumeration.
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Invalid email or password", 401)
    if user.is_superadmin and clinic_slug is None:
        return user, None, None
    rows = (
        await session.execute(
            select(Clinic, ClinicMembership.role)
            .join(ClinicMembership, ClinicMembership.clinic_id == Clinic.id)
            .where(ClinicMembership.user_id == user.id)
        )
    ).all()
    if clinic_slug:
        rows = [r for r in rows if r[0].slug == clinic_slug.lower()]
    if not rows:
        raise AppError("INVALID_CREDENTIALS", "Invalid email or password", 401)
    if len(rows) > 1:
        raise AppError(
            "CLINIC_REQUIRED",
            "Multiple clinics; pass clinic_slug",
            400,
            [r[0].slug for r in rows],
        )
    clinic, role = rows[0][0], rows[0][1]
    if not clinic.is_active:
        raise AppError("CLINIC_SUSPENDED", "This clinic is suspended", 403)
    return user, clinic, role


async def issue_tokens(
    session: AsyncSession,
    user: User,
    clinic_id: uuid.UUID | None,
    role: Role | None,
    family_id: uuid.UUID | None = None,
) -> TokenPair:
    raw, hashed = new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            clinic_id=clinic_id,
            token_hash=hashed,
            family_id=family_id or uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(days=get_settings().refresh_token_days),
        )
    )
    await session.flush()
    access = create_access_token(user.id, clinic_id, role.value if role else None, user.is_superadmin)
    return TokenPair(access, raw, clinic_id, role.value if role else None)


async def rotate_refresh(session: AsyncSession, raw: str) -> TokenPair:
    """Refresh rotation: each token is single-use. Reusing an old one revokes the whole family."""
    tok = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw)).with_for_update()
        )
    ).scalar_one_or_none()
    if tok is None:
        raise AppError("INVALID_TOKEN", "Invalid refresh token", 401)
    now = datetime.now(UTC)
    if tok.revoked_at is not None:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == tok.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        raise TokenReusedError()
    if tok.expires_at < now:
        raise AppError("INVALID_TOKEN", "Refresh token expired", 401)
    user = (await session.execute(select(User).where(User.id == tok.user_id))).scalar_one()
    if not user.is_active:
        raise AppError("INVALID_TOKEN", "User disabled", 401)
    role: Role | None = None
    if tok.clinic_id is not None:
        row = (
            await session.execute(
                select(ClinicMembership.role, Clinic.is_active)
                .join(Clinic, Clinic.id == ClinicMembership.clinic_id)
                .where(
                    ClinicMembership.user_id == user.id,
                    ClinicMembership.clinic_id == tok.clinic_id,
                )
            )
        ).first()
        if row is None:
            raise AppError("INVALID_TOKEN", "Membership revoked", 401)
        if not row[1]:
            raise AppError("CLINIC_SUSPENDED", "This clinic is suspended", 403)
        role = row[0]
    tok.revoked_at = now
    return await issue_tokens(session, user, tok.clinic_id, role, family_id=tok.family_id)


async def revoke_refresh(session: AsyncSession, raw: str) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw), RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
