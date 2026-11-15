import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.tables import Appointment, AppointmentStatus, Clinic, Notification, Patient
from app.services import audit, scheduling

TRANSITIONS: dict[AppointmentStatus, set[AppointmentStatus]] = {
    AppointmentStatus.booked: {
        AppointmentStatus.confirmed,
        AppointmentStatus.cancelled,
        AppointmentStatus.completed,
        AppointmentStatus.no_show,
    },
    AppointmentStatus.confirmed: {
        AppointmentStatus.cancelled,
        AppointmentStatus.completed,
        AppointmentStatus.no_show,
    },
    AppointmentStatus.completed: set(),
    AppointmentStatus.cancelled: set(),
    AppointmentStatus.no_show: set(),
}


def _is_overlap_violation(exc: IntegrityError) -> bool:
    sqlstate = getattr(exc.orig, "sqlstate", None)
    return sqlstate == "23P01" or "appointments_no_overlap" in str(exc)


async def _upsert_patient(session: AsyncSession, clinic_id: uuid.UUID, phone: str, full_name: str) -> uuid.UUID:
    stmt = (
        pg_insert(Patient)
        .values(clinic_id=clinic_id, phone=phone, full_name=full_name)
        .on_conflict_do_update(index_elements=["clinic_id", "phone"], set_={"full_name": full_name})
        .returning(Patient.id)
    )
    return (await session.execute(stmt)).scalar_one()


async def _assert_slot_free_and_valid(
    session: AsyncSession,
    *,
    clinic: Clinic,
    doctor_id: uuid.UUID,
    service_id: uuid.UUID,
    starts_at: datetime,
    min_notice: timedelta,
) -> tuple[datetime, datetime]:
    """Service-layer validation: hours, time off, duration grid, notice, past, existing bookings."""
    _, service = await scheduling.load_bookable(session, doctor_id, service_id)
    tz = ZoneInfo(clinic.timezone)
    starts_at = starts_at.astimezone(UTC)
    slots = await scheduling.available_slots(
        session,
        doctor_id=doctor_id,
        service=service,
        day=starts_at.astimezone(tz).date(),
        tz=tz,
        min_notice=min_notice,
    )
    if starts_at not in slots:
        raise AppError("SLOT_UNAVAILABLE", "This time is not available", 409)
    return starts_at, starts_at + timedelta(minutes=service.duration_minutes)


async def create_appointment(
    session: AsyncSession,
    *,
    clinic: Clinic,
    doctor_id: uuid.UUID,
    service_id: uuid.UUID,
    starts_at: datetime,
    phone: str,
    full_name: str,
    min_notice: timedelta,
    actor_user_id: uuid.UUID | None,
) -> Appointment:
    start, end = await _assert_slot_free_and_valid(
        session,
        clinic=clinic,
        doctor_id=doctor_id,
        service_id=service_id,
        starts_at=starts_at,
        min_notice=min_notice,
    )
    patient_id = await _upsert_patient(session, clinic.id, phone, full_name)
    appt = Appointment(
        clinic_id=clinic.id,
        doctor_id=doctor_id,
        service_id=service_id,
        patient_id=patient_id,
        during=Range(start, end, bounds="[)"),
        status=AppointmentStatus.booked,
    )
    try:
        async with session.begin_nested():  # savepoint: a lost race must not poison the transaction
            session.add(appt)
            await session.flush()
    except IntegrityError as exc:
        if _is_overlap_violation(exc):
            # The DB exclusion constraint is the source of truth for double booking.
            raise AppError("SLOT_TAKEN", "This slot was just taken, please pick another", 409) from exc
        raise
    await audit.record(
        session,
        clinic_id=clinic.id,
        actor_user_id=actor_user_id,
        action="appointment.create",
        entity="appointment",
        entity_id=appt.id,
        data={"starts_at": start.isoformat()},
    )
    return appt


async def reschedule(
    session: AsyncSession,
    *,
    clinic: Clinic,
    appt: Appointment,
    new_start: datetime,
    min_notice: timedelta,
    actor_user_id: uuid.UUID | None,
) -> Appointment:
    if appt.status not in (AppointmentStatus.booked, AppointmentStatus.confirmed):
        raise AppError("INVALID_STATE", "Only active appointments can be rescheduled", 409)
    start, end = await _assert_slot_free_and_valid(
        session,
        clinic=clinic,
        doctor_id=appt.doctor_id,
        service_id=appt.service_id,
        starts_at=new_start,
        min_notice=min_notice,
    )
    try:
        async with session.begin_nested():
            appt.during = Range(start, end, bounds="[)")
            appt.status = AppointmentStatus.booked  # must be re-confirmed
            await session.flush()
    except IntegrityError as exc:
        if _is_overlap_violation(exc):
            raise AppError("SLOT_TAKEN", "This slot was just taken, please pick another", 409) from exc
        raise
    # Old reminders were for the old time: clear them so new ones can be scheduled.
    await session.execute(delete(Notification).where(Notification.appointment_id == appt.id))
    await audit.record(
        session,
        clinic_id=clinic.id,
        actor_user_id=actor_user_id,
        action="appointment.reschedule",
        entity="appointment",
        entity_id=appt.id,
        data={"starts_at": start.isoformat()},
    )
    return appt


async def change_status(
    session: AsyncSession,
    *,
    appt: Appointment,
    new_status: AppointmentStatus,
    actor_user_id: uuid.UUID | None,
) -> Appointment:
    if new_status not in TRANSITIONS[appt.status]:
        raise AppError("INVALID_TRANSITION", f"Cannot go from {appt.status.value} to {new_status.value}", 409)
    old = appt.status
    appt.status = new_status
    await session.flush()
    await audit.record(
        session,
        clinic_id=appt.clinic_id,
        actor_user_id=actor_user_id,
        action="appointment.status",
        entity="appointment",
        entity_id=appt.id,
        data={"from": old.value, "to": new_status.value},
    )
    return appt


async def get_appointment(session: AsyncSession, clinic_id: uuid.UUID, appt_id: uuid.UUID) -> Appointment:
    appt = (
        await session.execute(select(Appointment).where(Appointment.clinic_id == clinic_id, Appointment.id == appt_id))
    ).scalar_one_or_none()
    if appt is None:
        raise AppError("NOT_FOUND", "Appointment not found", 404)
    return appt
