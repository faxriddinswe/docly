import uuid
from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_db, get_staff, require_roles
from app.api.public import resolve_clinic
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.core.redis import get_redis
from app.core.security import create_manage_token, decode_manage_token, make_link_token
from app.db import system_session, tenant_session
from app.models.tables import Appointment, AppointmentStatus, Clinic, Doctor, Patient, Service
from app.schemas.booking import (
    AppointmentOut,
    ManageOut,
    OtpRequestIn,
    PatientOut,
    PublicBookingIn,
    PublicBookingOut,
    RescheduleIn,
    StaffBookingIn,
    StatusIn,
)
from app.schemas.common import Page
from app.services import booking as svc
from app.services import otp

public = APIRouter(prefix="/public", tags=["public-booking"])
staff = APIRouter(tags=["appointments"])
WRITE = require_roles("owner", "admin")


def _notice() -> timedelta:
    return timedelta(minutes=get_settings().min_booking_notice_minutes)


def _ip(request: Request) -> str:  # same rule as main._client_ip
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


async def _out(db: AsyncSession, a: Appointment) -> AppointmentOut:
    d = await db.get(Doctor, a.doctor_id)
    s = await db.get(Service, a.service_id)
    p = await db.get(Patient, a.patient_id)
    assert d and s and p and a.during.lower and a.during.upper
    return AppointmentOut(
        id=a.id,
        doctor_id=d.id,
        doctor_name=d.full_name,
        service_id=s.id,
        service_name=s.name,
        patient_id=p.id,
        patient_name=p.full_name,
        patient_phone=p.phone,
        starts_at=a.during.lower,
        ends_at=a.during.upper,
        status=a.status,
    )


# ---------------------------------------------------------------- public (patients)
@public.post("/{slug}/otp", status_code=204)
async def request_otp(slug: str, body: OtpRequestIn, request: Request) -> None:
    await resolve_clinic(slug)
    phone = otp.normalize_phone(body.phone)
    await rate_limit(f"otp:phone:{phone}", 3, 600)
    await rate_limit(f"otp:ip:{_ip(request)}", get_settings().otp_ip_limit, 600)
    r = get_redis()
    await otp.request_code(r, otp.get_sender(r), phone)


@public.post("/{slug}/bookings", response_model=PublicBookingOut, status_code=201)
async def public_book(slug: str, body: PublicBookingIn, request: Request) -> PublicBookingOut:
    clinic = await resolve_clinic(slug)
    phone = otp.normalize_phone(body.phone)
    await rate_limit(f"book:ip:{_ip(request)}", get_settings().book_ip_limit, 600)
    await otp.verify_code(get_redis(), phone, body.otp_code)
    async with tenant_session(clinic.id) as db:
        appt = await svc.create_appointment(
            db,
            clinic=clinic,
            doctor_id=body.doctor_id,
            service_id=body.service_id,
            starts_at=body.starts_at,
            phone=phone,
            full_name=body.full_name.strip(),
            min_notice=_notice(),
            actor_user_id=None,
        )
        out = await _out(db, appt)
    username = get_settings().telegram_bot_username
    link = f"https://t.me/{username}?start={make_link_token(appt.patient_id, clinic.id)}" if username else None
    return PublicBookingOut(appointment=out, manage_token=create_manage_token(appt.id, clinic.id), telegram_link=link)


async def _manage_out(db: AsyncSession, clinic: Clinic, a: Appointment) -> ManageOut:
    base = await _out(db, a)
    return ManageOut(**base.model_dump(), clinic_name=clinic.name, clinic_slug=clinic.slug, timezone=clinic.timezone)


async def _manage_ctx(token: str) -> tuple[Clinic, uuid.UUID]:
    try:
        appt_id, clinic_id = decode_manage_token(token)
    except (jwt.PyJWTError, ValueError) as exc:
        raise AppError("INVALID_TOKEN", "Invalid or expired link", 401) from exc
    async with system_session() as s:
        clinic = await s.get(Clinic, clinic_id)
    if clinic is None or not clinic.is_active:
        raise AppError("CLINIC_NOT_FOUND", "Clinic not found", 404)
    return clinic, appt_id


@public.get("/manage/{token}", response_model=ManageOut)
async def manage_get(token: str) -> ManageOut:
    clinic, appt_id = await _manage_ctx(token)
    async with tenant_session(clinic.id) as db:
        return await _manage_out(db, clinic, await svc.get_appointment(db, clinic.id, appt_id))


@public.post("/manage/{token}/cancel", response_model=ManageOut)
async def manage_cancel(token: str) -> ManageOut:
    clinic, appt_id = await _manage_ctx(token)
    async with tenant_session(clinic.id) as db:
        a = await svc.get_appointment(db, clinic.id, appt_id)
        await svc.change_status(db, appt=a, new_status=AppointmentStatus.cancelled, actor_user_id=None)
        return await _manage_out(db, clinic, a)


@public.post("/manage/{token}/reschedule", response_model=ManageOut)
async def manage_reschedule(token: str, body: RescheduleIn) -> ManageOut:
    clinic, appt_id = await _manage_ctx(token)
    async with tenant_session(clinic.id) as db:
        a = await svc.get_appointment(db, clinic.id, appt_id)
        await svc.reschedule(
            db,
            clinic=clinic,
            appt=a,
            new_start=body.starts_at,
            min_notice=_notice(),
            actor_user_id=None,
        )
        return await _manage_out(db, clinic, a)


# ---------------------------------------------------------------- staff
async def _clinic_of(db: AsyncSession, p: Principal) -> Clinic:
    clinic = await db.get(Clinic, p.clinic_id)
    assert clinic is not None
    return clinic


@staff.get("/appointments", response_model=Page[AppointmentOut])
async def list_appointments(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    doctor_id: uuid.UUID | None = None,
    status: AppointmentStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    p: Principal = Depends(get_staff),
    db: AsyncSession = Depends(get_db),
) -> Page[AppointmentOut]:
    assert p.clinic_id is not None
    q = select(Appointment).where(Appointment.clinic_id == p.clinic_id)
    if date_from:
        q = q.where(func.upper(Appointment.during) > date_from)
    if date_to:
        q = q.where(func.lower(Appointment.during) < date_to)
    if doctor_id:
        q = q.where(Appointment.doctor_id == doctor_id)
    if status:
        q = q.where(Appointment.status == status)
    if p.role == "doctor":  # doctors only see their own calendar
        q = q.where(Appointment.doctor_id.in_(select(Doctor.id).where(Doctor.user_id == p.user_id)))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(func.lower(Appointment.during)).limit(limit).offset(offset))).scalars().all()
    return Page(items=[await _out(db, a) for a in rows], total=total, limit=limit, offset=offset)


@staff.post("/appointments", response_model=AppointmentOut, status_code=201)
async def staff_book(
    body: StaffBookingIn, p: Principal = Depends(WRITE), db: AsyncSession = Depends(get_db)
) -> AppointmentOut:
    clinic = await _clinic_of(db, p)
    a = await svc.create_appointment(
        db,
        clinic=clinic,
        doctor_id=body.doctor_id,
        service_id=body.service_id,
        starts_at=body.starts_at,
        phone=otp.normalize_phone(body.phone),
        full_name=body.full_name.strip(),
        min_notice=timedelta(0),
        actor_user_id=p.user_id,
    )
    return await _out(db, a)


@staff.get("/appointments/{appointment_id}", response_model=AppointmentOut)
async def get_appointment(
    appointment_id: uuid.UUID, p: Principal = Depends(get_staff), db: AsyncSession = Depends(get_db)
) -> AppointmentOut:
    assert p.clinic_id is not None
    return await _out(db, await svc.get_appointment(db, p.clinic_id, appointment_id))


@staff.patch("/appointments/{appointment_id}/status", response_model=AppointmentOut)
async def set_status(
    appointment_id: uuid.UUID,
    body: StatusIn,
    p: Principal = Depends(get_staff),
    db: AsyncSession = Depends(get_db),
) -> AppointmentOut:
    assert p.clinic_id is not None
    a = await svc.get_appointment(db, p.clinic_id, appointment_id)
    await svc.change_status(db, appt=a, new_status=body.status, actor_user_id=p.user_id)
    return await _out(db, a)


@staff.post("/appointments/{appointment_id}/reschedule", response_model=AppointmentOut)
async def staff_reschedule(
    appointment_id: uuid.UUID,
    body: RescheduleIn,
    p: Principal = Depends(WRITE),
    db: AsyncSession = Depends(get_db),
) -> AppointmentOut:
    assert p.clinic_id is not None
    a = await svc.get_appointment(db, p.clinic_id, appointment_id)
    await svc.reschedule(
        db,
        clinic=await _clinic_of(db, p),
        appt=a,
        new_start=body.starts_at,
        min_notice=timedelta(0),
        actor_user_id=p.user_id,
    )
    return await _out(db, a)


@staff.get("/patients", response_model=Page[PatientOut])
async def list_patients(
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    p: Principal = Depends(get_staff),
    db: AsyncSession = Depends(get_db),
) -> Page[PatientOut]:
    assert p.clinic_id is not None
    stmt = select(Patient).where(Patient.clinic_id == p.clinic_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Patient.phone.ilike(like) | Patient.full_name.ilike(like))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(Patient.full_name).limit(limit).offset(offset))).scalars().all()
    items = [PatientOut(id=r.id, full_name=r.full_name, phone=r.phone, created_at=r.created_at) for r in rows]
    return Page(items=items, total=total, limit=limit, offset=offset)


@staff.get("/patients/{patient_id}/appointments", response_model=list[AppointmentOut])
async def patient_history(
    patient_id: uuid.UUID, p: Principal = Depends(get_staff), db: AsyncSession = Depends(get_db)
) -> list[AppointmentOut]:
    assert p.clinic_id is not None
    pt = (
        await db.execute(select(Patient).where(Patient.clinic_id == p.clinic_id, Patient.id == patient_id))
    ).scalar_one_or_none()
    if pt is None:
        raise AppError("NOT_FOUND", "Patient not found", 404)
    rows = (
        (
            await db.execute(
                select(Appointment)
                .where(Appointment.clinic_id == p.clinic_id, Appointment.patient_id == pt.id)
                .order_by(func.lower(Appointment.during).desc())
            )
        )
        .scalars()
        .all()
    )
    return [await _out(db, a) for a in rows]


if get_settings().env != "prod" and get_settings().otp_sender == "fake":

    @public.get("/dev/otp/{phone}", tags=["dev"])
    async def dev_last_otp(phone: str) -> dict[str, str | None]:
        """DEV ONLY (not registered when ENV=prod): lets the UI/tests read the fake-sent code."""
        code = await get_redis().get(f"otp:outbox:{otp.normalize_phone(phone)}")
        return {"code": code}
