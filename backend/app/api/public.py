import uuid
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import AppError
from app.db import system_session, tenant_session
from app.models.tables import Clinic, Doctor, DoctorService, Service
from app.schemas.scheduling import DoctorOut, PublicClinicOut, ServiceOut, SlotsOut
from app.services import scheduling

router = APIRouter(prefix="/public", tags=["public"])


async def resolve_clinic(slug: str) -> Clinic:
    """Public slug -> clinic. Uses the explicit system scope because there is no tenant yet."""
    async with system_session() as s:
        clinic = (await s.execute(select(Clinic).where(Clinic.slug == slug.lower()))).scalar_one_or_none()
    if clinic is None or not clinic.is_active:
        raise AppError("CLINIC_NOT_FOUND", "Clinic not found", 404)
    return clinic


@router.get("/{slug}", response_model=PublicClinicOut)
async def public_clinic(slug: str) -> PublicClinicOut:
    clinic = await resolve_clinic(slug)
    async with tenant_session(clinic.id) as db:
        services = (
            (
                await db.execute(
                    select(Service).where(Service.clinic_id == clinic.id, Service.is_active).order_by(Service.name)
                )
            )
            .scalars()
            .all()
        )
        doctors = (
            (
                await db.execute(
                    select(Doctor).where(Doctor.clinic_id == clinic.id, Doctor.is_active).order_by(Doctor.full_name)
                )
            )
            .scalars()
            .all()
        )
        links = (await db.execute(select(DoctorService))).scalars().all()
        by_doc: dict[uuid.UUID, list[uuid.UUID]] = {}
        for link in links:
            by_doc.setdefault(link.doctor_id, []).append(link.service_id)
        return PublicClinicOut(
            name=clinic.name,
            slug=clinic.slug,
            timezone=clinic.timezone,
            services=[ServiceOut.model_validate(s) for s in services],
            doctors=[
                DoctorOut(
                    id=d.id,
                    full_name=d.full_name,
                    specialty=d.specialty,
                    is_active=d.is_active,
                    service_ids=by_doc.get(d.id, []),
                )
                for d in doctors
            ],
        )


@router.get("/{slug}/availability", response_model=SlotsOut)
async def availability(
    slug: str, doctor_id: uuid.UUID = Query(), service_id: uuid.UUID = Query(), date: date = Query()
) -> SlotsOut:
    clinic = await resolve_clinic(slug)
    tz = ZoneInfo(clinic.timezone)
    async with tenant_session(clinic.id) as db:
        _, service = await scheduling.load_bookable(db, doctor_id, service_id)
        slots = await scheduling.available_slots(
            db,
            doctor_id=doctor_id,
            service=service,
            day=date,
            tz=tz,
            min_notice=timedelta(minutes=get_settings().min_booking_notice_minutes),
        )
    return SlotsOut(date=date.isoformat(), timezone=clinic.timezone, slots=slots)
