import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.domain.availability import Interval, compute_slots, local_to_utc
from app.models.tables import (
    Appointment,
    AppointmentStatus,
    Doctor,
    DoctorService,
    Service,
    TimeOff,
    WorkingHours,
)


def _interval(r: Range[datetime]) -> Interval:
    assert r.lower is not None and r.upper is not None
    return Interval(r.lower, r.upper)


ACTIVE = (AppointmentStatus.booked, AppointmentStatus.confirmed)


async def load_bookable(
    session: AsyncSession, doctor_id: uuid.UUID, service_id: uuid.UUID
) -> tuple[Doctor, Service]:
    doctor = await session.get(Doctor, doctor_id)
    service = await session.get(Service, service_id)
    if doctor is None or not doctor.is_active:
        raise AppError("DOCTOR_NOT_FOUND", "Doctor not found", 404)
    if service is None or not service.is_active:
        raise AppError("SERVICE_NOT_FOUND", "Service not found", 404)
    link = await session.get(DoctorService, (doctor_id, service_id))
    if link is None:
        raise AppError("SERVICE_NOT_OFFERED", "This doctor does not provide the service", 422)
    return doctor, service


async def available_slots(
    session: AsyncSession,
    *,
    doctor_id: uuid.UUID,
    service: Service,
    day: date,
    tz: ZoneInfo,
    min_notice: timedelta,
    now: datetime | None = None,
) -> list[datetime]:
    now = now or datetime.now(UTC)
    day_start = local_to_utc(day, datetime.min.time(), tz)
    day_end = local_to_utc(day + timedelta(days=1), datetime.min.time(), tz)
    wh = (
        (
            await session.execute(
                select(WorkingHours).where(
                    WorkingHours.doctor_id == doctor_id, WorkingHours.weekday == day.weekday()
                )
            )
        )
        .scalars()
        .all()
    )
    window = Range(day_start, day_end, bounds="[)")
    offs = (
        (
            await session.execute(
                select(TimeOff).where(
                    TimeOff.doctor_id == doctor_id, TimeOff.during.overlaps(window)
                )
            )
        )
        .scalars()
        .all()
    )
    appts = (
        (
            await session.execute(
                select(Appointment).where(
                    Appointment.doctor_id == doctor_id,
                    Appointment.status.in_(ACTIVE),
                    Appointment.during.overlaps(window),
                )
            )
        )
        .scalars()
        .all()
    )
    return compute_slots(
        day=day,
        tz=tz,
        working=[(w.start_time, w.end_time) for w in wh],
        time_off=[_interval(o.during) for o in offs],
        busy=[_interval(a.during) for a in appts],
        duration=timedelta(minutes=service.duration_minutes),
        now=now,
        min_notice=min_notice,
    )
