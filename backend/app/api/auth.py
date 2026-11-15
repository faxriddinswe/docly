from fastapi import APIRouter, Depends

from app.api.deps import Principal, get_principal
from app.core.errors import AppError
from app.db import system_session
from app.models.tables import (
    Role,  # noqa: F401
    User,
)
from app.schemas.auth import LoginIn, MeOut, RefreshIn, SignupIn, TokenOut
from app.services import auth as svc

router = APIRouter(prefix="/auth", tags=["auth"])


def _out(pair: svc.TokenPair) -> TokenOut:
    return TokenOut(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        clinic_id=pair.clinic_id,
        role=pair.role,
    )


@router.post("/signup", response_model=TokenOut, status_code=201)
async def signup(body: SignupIn) -> TokenOut:
    async with system_session() as s:
        user, clinic = await svc.signup_clinic(
            s,
            clinic_name=body.clinic_name,
            slug=body.slug,
            email=body.email,
            password=body.password,
            full_name=body.full_name,
            timezone=body.timezone,
        )
        pair = await svc.issue_tokens(s, user, clinic.id, Role.owner)
    return _out(pair)


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn) -> TokenOut:
    async with system_session() as s:
        user, clinic, role = await svc.authenticate(
            s, email=body.email, password=body.password, clinic_slug=body.clinic_slug
        )
        pair = await svc.issue_tokens(s, user, clinic.id if clinic else None, role)
    return _out(pair)


@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn) -> TokenOut:
    reused = False
    pair = None
    async with system_session() as s:
        try:
            pair = await svc.rotate_refresh(s, body.refresh_token)
        except svc.TokenReusedError:
            reused = True  # leave the block normally so the family revocation commits
    if reused or pair is None:
        raise AppError("TOKEN_REUSED", "Refresh token reuse detected; session revoked", 401)
    return _out(pair)


@router.post("/logout", status_code=204)
async def logout(body: RefreshIn) -> None:
    async with system_session() as s:
        await svc.revoke_refresh(s, body.refresh_token)


@router.get("/me", response_model=MeOut)
async def me(p: Principal = Depends(get_principal)) -> MeOut:
    async with system_session() as s:
        user = await s.get(User, p.user_id)
    if user is None or not user.is_active:
        raise AppError("UNAUTHENTICATED", "User not found", 401)
    return MeOut(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        clinic_id=p.clinic_id,
        role=p.role,
        is_superadmin=p.is_superadmin,
    )
