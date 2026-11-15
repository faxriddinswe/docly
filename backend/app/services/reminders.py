"""Idempotent reminder scanner (24h and 2h before an appointment).

Idempotency: notifications has UNIQUE(appointment_id, kind). We *claim* the (appointment, kind) row with
INSERT ... ON CONFLICT DO NOTHING before sending; a concurrent/second scan gets no row and skips.
Staleness: the scan only reads CURRENT appointment state (active status, current start time) under a row lock,
and rescheduling deletes old notification rows, so cancelled/moved appointments never get stale reminders.
If the send fails the claim is removed so the next scan retries (at-most-once on a crash between claim and send).
"""

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import system_session
from app.models.tables import (
    Appointment,
    AppointmentStatus,
    Clinic,
    Doctor,
    Notification,
    Patient,
)
from app.services.telegram import Button, Transport

log = logging.getLogger(__name__)

KIND_24H = "reminder_24h"
KIND_2H = "reminder_2h"


def confirm_data(appointment_id: object) -> str:
    return f"c:{appointment_id}"


def cancel_data(appointment_id: object) -> str:
    return f"x:{appointment_id}"


def reminder_text(clinic: Clinic, doctor: Doctor, start: datetime, kind: str) -> str:
    local = start.astimezone(ZoneInfo(clinic.timezone))
    when = "ertaga" if kind == KIND_24H else "bugun"
    return (
        f"Eslatma: {when} soat {local:%H:%M} da ({local:%d.%m.%Y}) {clinic.name} klinikasida "
        f"{doctor.full_name} qabuliga yozilgansiz."
    )


async def _due_appointment_ids(
    session: AsyncSession, now: datetime, kind: str, lead: timedelta, tolerance: timedelta
) -> list[object]:
    # reminder is due when now ∈ [start - lead, start - lead + tolerance]  <=>  start ∈ [now+lead-tol, now+lead]
    lo, hi = now + lead - tolerance, now + lead
    rows = await session.execute(
        select(Appointment.id)
        .join(Patient, Patient.id == Appointment.patient_id)
        .where(
            Appointment.status.in_([AppointmentStatus.booked, AppointmentStatus.confirmed]),
            Patient.telegram_chat_id.is_not(None),
            func.lower(Appointment.during).between(lo, hi),
        )
    )
    return list(rows.scalars().all())


async def _process_one(
    appointment_id: object,
    now: datetime,
    kind: str,
    lead: timedelta,
    tol: timedelta,
    transport: Transport,
) -> bool:
    async with system_session() as s:
        # Row lock + current-state re-read: a concurrent cancel/reschedule either happened (we skip)
        # or waits until we commit.
        appt = (
            await s.execute(
                select(Appointment).where(Appointment.id == appointment_id).with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if appt is None or appt.status not in (
            AppointmentStatus.booked,
            AppointmentStatus.confirmed,
        ):
            return False
        assert appt.during.lower is not None
        start = appt.during.lower
        if not (now + lead - tol <= start <= now + lead):
            return False  # moved since the candidate query
        patient = await s.get(Patient, appt.patient_id)
        if patient is None or patient.telegram_chat_id is None:
            return False
        claim = (
            await s.execute(
                pg_insert(Notification)
                .values(clinic_id=appt.clinic_id, appointment_id=appt.id, kind=kind)
                .on_conflict_do_nothing(index_elements=["appointment_id", "kind"])
                .returning(Notification.id)
            )
        ).scalar_one_or_none()
        if claim is None:
            return False  # already sent / being sent
        clinic = await s.get(Clinic, appt.clinic_id)
        doctor = await s.get(Doctor, appt.doctor_id)
        assert clinic is not None and doctor is not None
        try:
            await transport.send_message(
                patient.telegram_chat_id,
                reminder_text(clinic, doctor, start, kind),
                [
                    Button("✅ Tasdiqlash", confirm_data(appt.id)),
                    Button("❌ Bekor qilish", cancel_data(appt.id)),
                ],
            )
        except Exception:
            log.exception("reminder send failed; will retry on next scan")
            await s.execute(delete(Notification).where(Notification.id == claim))
            return False
        await s.execute(update(Notification).where(Notification.id == claim).values(sent_at=now))
        return True


async def run_reminder_scan(transport: Transport, now: datetime | None = None) -> int:
    """Send all due reminders. Returns the number sent. Safe to run concurrently / repeatedly."""
    now = now or datetime.now(UTC)
    cfg = get_settings()
    plans = [
        (KIND_24H, timedelta(hours=24), timedelta(minutes=cfg.reminder_24h_tolerance_minutes)),
        (KIND_2H, timedelta(hours=2), timedelta(minutes=cfg.reminder_2h_tolerance_minutes)),
    ]
    sent = 0
    for kind, lead, tol in plans:
        async with system_session() as s:
            ids = await _due_appointment_ids(s, now, kind, lead, tol)
        for appt_id in ids:
            if await _process_one(appt_id, now, kind, lead, tol, transport):
                sent += 1
    return sent
