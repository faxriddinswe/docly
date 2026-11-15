import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_db, get_staff, require_roles
from app.core.errors import AppError
from app.models.tables import Doctor, DoctorService, Service, TimeOff, WorkingHours
from app.repositories import ScopedRepo
from app.schemas.common import Page
from app.schemas.scheduling import (
    DoctorIn,
    DoctorOut,
    DoctorPatch,
    DoctorServicesIn,
    ServiceIn,
    ServiceOut,
    ServicePatch,
    TimeOffIn,
    TimeOffOut,
    WorkingHoursIn,
    WorkingInterval,
)
from app.services import audit

router = APIRouter(tags=["scheduling"])
WRITE = require_roles("owner", "admin")


def _cid(p: Principal) -> uuid.UUID:
    assert p.clinic_id is not None
    return p.clinic_id


async def _doctor_or_404(db: AsyncSession, p: Principal, doctor_id: uuid.UUID) -> Doctor:
    repo: ScopedRepo[Doctor] = ScopedRepo(db, Doctor, _cid(p))
    d = await repo.get(doctor_id)
    if d is None:
        raise AppError("NOT_FOUND", "Doctor not found", 404)
    return d


async def _doctor_out(db: AsyncSession, d: Doctor) -> DoctorOut:
    ids = (await db.execute(select(DoctorService.service_id).where(DoctorService.doctor_id == d.id))).scalars().all()
    return DoctorOut(
        id=d.id,
        full_name=d.full_name,
        specialty=d.specialty,
        is_active=d.is_active,
        service_ids=list(ids),
    )


# ---- doctors -------------------------------------------------------------------------
@router.get("/doctors", response_model=Page[DoctorOut])
async def list_doctors(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    p: Principal = Depends(get_staff),
    db: AsyncSession = Depends(get_db),
) -> Page[DoctorOut]:
    cid = _cid(p)
    total = (await db.execute(select(func.count()).select_from(Doctor).where(Doctor.clinic_id == cid))).scalar_one()
    rows = (
        (
            await db.execute(
                select(Doctor).where(Doctor.clinic_id == cid).order_by(Doctor.full_name).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return Page(items=[await _doctor_out(db, d) for d in rows], total=total, limit=limit, offset=offset)


@router.post("/doctors", response_model=DoctorOut, status_code=201)
async def create_doctor(body: DoctorIn, p: Principal = Depends(WRITE), db: AsyncSession = Depends(get_db)) -> DoctorOut:
    repo: ScopedRepo[Doctor] = ScopedRepo(db, Doctor, _cid(p))
    d = await repo.add(**body.model_dump())
    await audit.record(
        db,
        clinic_id=_cid(p),
        actor_user_id=p.user_id,
        action="doctor.create",
        entity="doctor",
        entity_id=d.id,
    )
    return await _doctor_out(db, d)


@router.get("/doctors/{doctor_id}", response_model=DoctorOut)
async def get_doctor(
    doctor_id: uuid.UUID, p: Principal = Depends(get_staff), db: AsyncSession = Depends(get_db)
) -> DoctorOut:
    return await _doctor_out(db, await _doctor_or_404(db, p, doctor_id))


@router.patch("/doctors/{doctor_id}", response_model=DoctorOut)
async def patch_doctor(
    doctor_id: uuid.UUID,
    body: DoctorPatch,
    p: Principal = Depends(WRITE),
    db: AsyncSession = Depends(get_db),
) -> DoctorOut:
    d = await _doctor_or_404(db, p, doctor_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(d, k, v)
    await audit.record(
        db,
        clinic_id=_cid(p),
        actor_user_id=p.user_id,
        action="doctor.update",
        entity="doctor",
        entity_id=d.id,
        data=body.model_dump(exclude_unset=True),
    )
    return await _doctor_out(db, d)


@router.delete("/doctors/{doctor_id}", status_code=204)
async def deactivate_doctor(
    doctor_id: uuid.UUID, p: Principal = Depends(WRITE), db: AsyncSession = Depends(get_db)
) -> None:
    """Soft delete: appointment history must keep referencing the doctor."""
    d = await _doctor_or_404(db, p, doctor_id)
    d.is_active = False
    await audit.record(
        db,
        clinic_id=_cid(p),
        actor_user_id=p.user_id,
        action="doctor.deactivate",
        entity="doctor",
        entity_id=d.id,
    )


@router.put("/doctors/{doctor_id}/services", response_model=DoctorOut)
async def set_doctor_services(
    doctor_id: uuid.UUID,
    body: DoctorServicesIn,
    p: Principal = Depends(WRITE),
    db: AsyncSession = Depends(get_db),
) -> DoctorOut:
    d = await _doctor_or_404(db, p, doctor_id)
    found = set(
        (await db.execute(select(Service.id).where(Service.clinic_id == _cid(p), Service.id.in_(body.service_ids))))
        .scalars()
        .all()
    )
    if found != set(body.service_ids):
        raise AppError("NOT_FOUND", "One or more services not found", 404)
    await db.execute(delete(DoctorService).where(DoctorService.doctor_id == d.id))
    for sid in found:
        db.add(DoctorService(doctor_id=d.id, service_id=sid, clinic_id=_cid(p)))
    await db.flush()
    await audit.record(
        db,
        clinic_id=_cid(p),
        actor_user_id=p.user_id,
        action="doctor.set_services",
        entity="doctor",
        entity_id=d.id,
        data={"service_ids": [str(x) for x in found]},
    )
    return await _doctor_out(db, d)


# ---- services ------------------------------------------------------------------------
async def _service_or_404(db: AsyncSession, p: Principal, service_id: uuid.UUID) -> Service:
    repo: ScopedRepo[Service] = ScopedRepo(db, Service, _cid(p))
    s = await repo.get(service_id)
    if s is None:
        raise AppError("NOT_FOUND", "Service not found", 404)
    return s


@router.get("/services", response_model=Page[ServiceOut])
async def list_services(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    p: Principal = Depends(get_staff),
    db: AsyncSession = Depends(get_db),
) -> Page[ServiceOut]:
    cid = _cid(p)
    total = (await db.execute(select(func.count()).select_from(Service).where(Service.clinic_id == cid))).scalar_one()
    rows = (
        (
            await db.execute(
                select(Service).where(Service.clinic_id == cid).order_by(Service.name).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return Page(items=[ServiceOut.model_validate(s) for s in rows], total=total, limit=limit, offset=offset)


@router.post("/services", response_model=ServiceOut, status_code=201)
async def create_service(body: ServiceIn, p: Principal = Depends(WRITE), db: AsyncSession = Depends(get_db)) -> Service:
    repo: ScopedRepo[Service] = ScopedRepo(db, Service, _cid(p))
    s = await repo.add(**body.model_dump())
    await audit.record(
        db,
        clinic_id=_cid(p),
        actor_user_id=p.user_id,
        action="service.create",
        entity="service",
        entity_id=s.id,
    )
    return s


@router.get("/services/{service_id}", response_model=ServiceOut)
async def get_service(
    service_id: uuid.UUID, p: Principal = Depends(get_staff), db: AsyncSession = Depends(get_db)
) -> Service:
    return await _service_or_404(db, p, service_id)


@router.patch("/services/{service_id}", response_model=ServiceOut)
async def patch_service(
    service_id: uuid.UUID,
    body: ServicePatch,
    p: Principal = Depends(WRITE),
    db: AsyncSession = Depends(get_db),
) -> Service:
    s = await _service_or_404(db, p, service_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await audit.record(
        db,
        clinic_id=_cid(p),
        actor_user_id=p.user_id,
        action="service.update",
        entity="service",
        entity_id=s.id,
        data=body.model_dump(exclude_unset=True),
    )
    return s


@router.delete("/services/{service_id}", status_code=204)
async def deactivate_service(
    service_id: uuid.UUID, p: Principal = Depends(WRITE), db: AsyncSession = Depends(get_db)
) -> None:
    s = await _service_or_404(db, p, service_id)
    s.is_active = False
    await audit.record(
        db,
        clinic_id=_cid(p),
        actor_user_id=p.user_id,
        action="service.deactivate",
        entity="service",
        entity_id=s.id,
    )


# ---- working hours -------------------------------------------------------------------
def _check_no_overlap(intervals: list[WorkingInterval]) -> None:
    by_day: dict[int, list[WorkingInterval]] = {}
    for i in intervals:
        by_day.setdefault(i.weekday, []).append(i)
    for day in by_day.values():
        day.sort(key=lambda x: x.start_time)
        for a, b in zip(day, day[1:], strict=False):
            if b.start_time < a.end_time:
                raise AppError("OVERLAPPING_HOURS", "Working intervals overlap on the same weekday", 422)


@router.get("/doctors/{doctor_id}/working-hours", response_model=list[WorkingInterval])
async def get_working_hours(
    doctor_id: uuid.UUID, p: Principal = Depends(get_staff), db: AsyncSession = Depends(get_db)
) -> list[WorkingInterval]:
    d = await _doctor_or_404(db, p, doctor_id)
    rows = (
        (
            await db.execute(
                select(WorkingHours)
                .where(WorkingHours.doctor_id == d.id)
                .order_by(WorkingHours.weekday, WorkingHours.start_time)
            )
        )
        .scalars()
        .all()
    )
    return [WorkingInterval(weekday=r.weekday, start_time=r.start_time, end_time=r.end_time) for r in rows]


@router.put("/doctors/{doctor_id}/working-hours", response_model=list[WorkingInterval])
async def replace_working_hours(
    doctor_id: uuid.UUID,
    body: WorkingHoursIn,
    p: Principal = Depends(WRITE),
    db: AsyncSession = Depends(get_db),
) -> list[WorkingInterval]:
    d = await _doctor_or_404(db, p, doctor_id)
    _check_no_overlap(body.intervals)
    await db.execute(delete(WorkingHours).where(WorkingHours.doctor_id == d.id))
    for i in body.intervals:
        db.add(
            WorkingHours(
                clinic_id=_cid(p),
                doctor_id=d.id,
                weekday=i.weekday,
                start_time=i.start_time,
                end_time=i.end_time,
            )
        )
    await db.flush()
    await audit.record(
        db,
        clinic_id=_cid(p),
        actor_user_id=p.user_id,
        action="working_hours.replace",
        entity="doctor",
        entity_id=d.id,
        data={"count": len(body.intervals)},
    )
    return body.intervals


# ---- time off ------------------------------------------------------------------------
def _off_out(t: TimeOff) -> TimeOffOut:
    assert t.during.lower is not None and t.during.upper is not None
    return TimeOffOut(
        id=t.id,
        doctor_id=t.doctor_id,
        starts_at=t.during.lower,
        ends_at=t.during.upper,
        reason=t.reason,
    )


@router.get("/doctors/{doctor_id}/time-off", response_model=list[TimeOffOut])
async def list_time_off(
    doctor_id: uuid.UUID, p: Principal = Depends(get_staff), db: AsyncSession = Depends(get_db)
) -> list[TimeOffOut]:
    d = await _doctor_or_404(db, p, doctor_id)
    rows = (await db.execute(select(TimeOff).where(TimeOff.doctor_id == d.id).order_by(TimeOff.during))).scalars().all()
    return [_off_out(t) for t in rows]


@router.post("/doctors/{doctor_id}/time-off", response_model=TimeOffOut, status_code=201)
async def create_time_off(
    doctor_id: uuid.UUID,
    body: TimeOffIn,
    p: Principal = Depends(WRITE),
    db: AsyncSession = Depends(get_db),
) -> TimeOffOut:
    d = await _doctor_or_404(db, p, doctor_id)
    during: Range[datetime] = Range(body.starts_at, body.ends_at, bounds="[)")
    repo: ScopedRepo[TimeOff] = ScopedRepo(db, TimeOff, _cid(p))
    extra: dict[str, Any] = {"doctor_id": d.id, "during": during, "reason": body.reason}
    t = await repo.add(**extra)
    await audit.record(
        db,
        clinic_id=_cid(p),
        actor_user_id=p.user_id,
        action="time_off.create",
        entity="time_off",
        entity_id=t.id,
    )
    return _off_out(t)


@router.delete("/time-off/{time_off_id}", status_code=204)
async def delete_time_off(
    time_off_id: uuid.UUID, p: Principal = Depends(WRITE), db: AsyncSession = Depends(get_db)
) -> None:
    repo: ScopedRepo[TimeOff] = ScopedRepo(db, TimeOff, _cid(p))
    t = await repo.get(time_off_id)
    if t is None:
        raise AppError("NOT_FOUND", "Time off not found", 404)
    await repo.delete(t)
    await audit.record(
        db,
        clinic_id=_cid(p),
        actor_user_id=p.user_id,
        action="time_off.delete",
        entity="time_off",
        entity_id=time_off_id,
    )
