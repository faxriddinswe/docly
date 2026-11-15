import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_db, require_roles
from app.models.tables import Appointment, AppointmentStatus, Clinic, Doctor

router = APIRouter(tags=["stats"])


class DayCount(BaseModel):
    date: date
    count: int


class DoctorLoad(BaseModel):
    doctor_id: uuid.UUID
    doctor_name: str
    appointments: int


class StatsOut(BaseModel):
    date_from: date
    date_to: date
    total: int
    per_day: list[DayCount]
    no_show_rate: float | None  # no_show / (completed + no_show); None when nothing finished yet
    busiest_doctors: list[DoctorLoad]


@router.get("/stats", response_model=StatsOut)
async def stats(
    date_from: date | None = None,
    date_to: date | None = Query(None, description="inclusive"),
    p: Principal = Depends(require_roles("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> StatsOut:
    assert p.clinic_id is not None
    clinic = await db.get(Clinic, p.clinic_id)
    assert clinic is not None
    today = datetime.now().date()
    d_to = date_to or today
    d_from = date_from or d_to - timedelta(days=29)
    tz = clinic.timezone
    local_day = cast(func.timezone(tz, func.lower(Appointment.during)), Date)
    base = [
        Appointment.clinic_id == p.clinic_id,
        local_day >= d_from,
        local_day <= d_to,
        Appointment.status != AppointmentStatus.cancelled,
    ]
    per_day = (
        await db.execute(select(local_day, func.count()).where(*base).group_by(local_day).order_by(local_day))
    ).all()
    counts = dict(
        (await db.execute(select(Appointment.status, func.count()).where(*base).group_by(Appointment.status))).all()
    )
    finished = counts.get(AppointmentStatus.completed, 0) + counts.get(AppointmentStatus.no_show, 0)
    rate = counts.get(AppointmentStatus.no_show, 0) / finished if finished else None
    busiest = (
        await db.execute(
            select(Doctor.id, Doctor.full_name, func.count(Appointment.id).label("n"))
            .join(Doctor, Doctor.id == Appointment.doctor_id)
            .where(*base)
            .group_by(Doctor.id, Doctor.full_name)
            .order_by(func.count(Appointment.id).desc())
            .limit(5)
        )
    ).all()
    return StatsOut(
        date_from=d_from,
        date_to=d_to,
        total=sum(counts.values()),
        per_day=[DayCount(date=d, count=c) for d, c in per_day],
        no_show_rate=rate,
        busiest_doctors=[DoctorLoad(doctor_id=i, doctor_name=n, appointments=c) for i, n, c in busiest],
    )
