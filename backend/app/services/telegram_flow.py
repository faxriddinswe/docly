"""Framework-independent bot logic (the aiogram handlers are thin wrappers around these)."""

import uuid

from sqlalchemy import select

from app.core.errors import AppError
from app.core.security import parse_link_token
from app.db import system_session, tenant_session
from app.models.tables import Appointment, AppointmentStatus, Patient
from app.services import booking


async def handle_start(payload: str, chat_id: int) -> str:
    parsed = parse_link_token(payload.strip())
    if parsed is None:
        return "Havola yaroqsiz yoki muddati tugagan. Iltimos, klinika saytidan yangi havola oling."
    patient_id, clinic_id = parsed
    async with tenant_session(clinic_id) as s:
        patient = (
            await s.execute(select(Patient).where(Patient.id == patient_id, Patient.clinic_id == clinic_id))
        ).scalar_one_or_none()
        if patient is None:
            return "Bemor topilmadi."
        patient.telegram_chat_id = chat_id
        name = patient.full_name
    return f"Rahmat, {name}! Endi qabul haqida eslatmalarni shu yerda olasiz."


async def handle_callback(data: str, chat_id: int) -> str:
    action, _, raw_id = data.partition(":")
    try:
        appt_id = uuid.UUID(raw_id)
    except ValueError:
        return "Noto'g'ri amal."
    if action not in ("c", "x"):
        return "Noto'g'ri amal."
    async with system_session() as s:  # identify the tenant first; the mutation then runs tenant-scoped
        row = (
            await s.execute(
                select(Appointment.clinic_id, Patient.telegram_chat_id)
                .join(Patient, Patient.id == Appointment.patient_id)
                .where(Appointment.id == appt_id)
            )
        ).first()
    # Only the linked patient's chat may act on the appointment.
    if row is None or row[1] != chat_id:
        return "Bu qabul sizga tegishli emas."
    clinic_id: uuid.UUID = row[0]
    target = AppointmentStatus.confirmed if action == "c" else AppointmentStatus.cancelled
    async with tenant_session(clinic_id) as s:
        appt = await booking.get_appointment(s, clinic_id, appt_id)
        try:
            await booking.change_status(s, appt=appt, new_status=target, actor_user_id=None)
        except AppError:
            return "Bu qabulni endi o'zgartirib bo'lmaydi."
    return "Qabul tasdiqlandi ✅" if target == AppointmentStatus.confirmed else "Qabul bekor qilindi."
