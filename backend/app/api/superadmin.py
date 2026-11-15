import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import Principal, get_superadmin
from app.core.errors import AppError
from app.db import system_session
from app.models.tables import Clinic
from app.schemas.clinic import ClinicOut
from app.schemas.common import Page
from app.services import audit

router = APIRouter(prefix="/admin", tags=["superadmin"])


@router.get("/clinics", response_model=Page[ClinicOut])
async def list_clinics(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: Principal = Depends(get_superadmin),
) -> Page[ClinicOut]:
    async with system_session() as s:
        total = (await s.execute(select(func.count()).select_from(Clinic))).scalar_one()
        rows = (
            (
                await s.execute(
                    select(Clinic).order_by(Clinic.created_at).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        items = [ClinicOut.model_validate(c) for c in rows]
    return Page(items=items, total=total, limit=limit, offset=offset)


async def _set_active(clinic_id: uuid.UUID, active: bool, actor: Principal) -> ClinicOut:
    async with system_session() as s:
        clinic = await s.get(Clinic, clinic_id)
        if clinic is None:
            raise AppError("NOT_FOUND", "Clinic not found", 404)
        clinic.is_active = active
        await audit.record(
            s,
            clinic_id=clinic_id,
            actor_user_id=actor.user_id,
            action="clinic.activate" if active else "clinic.suspend",
            entity="clinic",
            entity_id=clinic_id,
        )
        return ClinicOut.model_validate(clinic)


@router.post("/clinics/{clinic_id}/suspend", response_model=ClinicOut)
async def suspend(clinic_id: uuid.UUID, p: Principal = Depends(get_superadmin)) -> ClinicOut:
    return await _set_active(clinic_id, False, p)


@router.post("/clinics/{clinic_id}/activate", response_model=ClinicOut)
async def activate(clinic_id: uuid.UUID, p: Principal = Depends(get_superadmin)) -> ClinicOut:
    return await _set_active(clinic_id, True, p)
