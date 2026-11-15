import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_db, get_staff, require_roles
from app.core.errors import AppError
from app.core.security import hash_password
from app.models.tables import Clinic, ClinicMembership, Role, User
from app.repositories import ScopedRepo
from app.schemas.clinic import ClinicOut, StaffCreate, StaffOut
from app.schemas.common import Page
from app.services import audit

router = APIRouter(tags=["clinic"])


@router.get("/clinic", response_model=ClinicOut)
async def get_clinic(
    p: Principal = Depends(get_staff), db: AsyncSession = Depends(get_db)
) -> Clinic:
    clinic = await db.get(Clinic, p.clinic_id)
    if clinic is None:
        raise AppError("NOT_FOUND", "Clinic not found", 404)
    return clinic


def _staff_out(m: ClinicMembership, u: User) -> StaffOut:
    return StaffOut(
        membership_id=m.id, user_id=u.id, email=u.email, full_name=u.full_name, role=m.role.value
    )


@router.get("/staff", response_model=Page[StaffOut])
async def list_staff(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    p: Principal = Depends(require_roles("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> Page[StaffOut]:
    assert p.clinic_id is not None
    total = (
        await db.execute(
            select(func.count())
            .select_from(ClinicMembership)
            .where(ClinicMembership.clinic_id == p.clinic_id)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(ClinicMembership, User)
            .join(User, User.id == ClinicMembership.user_id)
            .where(ClinicMembership.clinic_id == p.clinic_id)
            .order_by(ClinicMembership.created_at)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return Page(items=[_staff_out(m, u) for m, u in rows], total=total, limit=limit, offset=offset)


@router.post("/staff", response_model=StaffOut, status_code=201)
async def create_staff(
    body: StaffCreate,
    p: Principal = Depends(require_roles("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> StaffOut:
    assert p.clinic_id is not None
    if body.role == "admin" and p.role != "owner":
        raise AppError("FORBIDDEN", "Only the owner can create admins", 403)
    email = body.email.lower()
    if (await db.execute(select(User.id).where(User.email == email))).first():
        raise AppError("EMAIL_TAKEN", "Email already registered", 409)
    user = User(email=email, password_hash=hash_password(body.password), full_name=body.full_name)
    db.add(user)
    await db.flush()
    repo: ScopedRepo[ClinicMembership] = ScopedRepo(db, ClinicMembership, p.clinic_id)
    m = await repo.add(user_id=user.id, role=Role(body.role))
    await audit.record(
        db,
        clinic_id=p.clinic_id,
        actor_user_id=p.user_id,
        action="staff.create",
        entity="clinic_membership",
        entity_id=m.id,
        data={"role": body.role},
    )
    return _staff_out(m, user)


@router.delete("/staff/{membership_id}", status_code=204)
async def delete_staff(
    membership_id: uuid.UUID,
    p: Principal = Depends(require_roles("owner")),
    db: AsyncSession = Depends(get_db),
) -> None:
    assert p.clinic_id is not None
    repo: ScopedRepo[ClinicMembership] = ScopedRepo(db, ClinicMembership, p.clinic_id)
    m = await repo.get(membership_id)
    if m is None:
        raise AppError("NOT_FOUND", "Staff member not found", 404)
    if m.role == Role.owner:
        raise AppError("FORBIDDEN", "The owner cannot be removed", 403)
    await repo.delete(m)
    await audit.record(
        db,
        clinic_id=p.clinic_id,
        actor_user_id=p.user_id,
        action="staff.delete",
        entity="clinic_membership",
        entity_id=membership_id,
    )
