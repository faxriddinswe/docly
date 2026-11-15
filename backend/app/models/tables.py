import enum
import uuid
from datetime import datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE, ExcludeConstraint, Range
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedMixin, IdMixin


class Role(enum.StrEnum):
    owner = "owner"
    admin = "admin"
    doctor = "doctor"


class AppointmentStatus(enum.StrEnum):
    booked = "booked"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


def _enum(e: type[enum.StrEnum], name: str) -> SAEnum:
    return SAEnum(e, name=name, values_callable=lambda x: [m.value for m in x])


def _fk(target: str) -> Mapped[uuid.UUID]:
    return mapped_column(PGUUID(as_uuid=True), ForeignKey(target, ondelete="CASCADE"), index=True)


class Clinic(Base, IdMixin, CreatedMixin):
    __tablename__ = "clinics"
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    timezone: Mapped[str] = mapped_column(String(64), server_default="Asia/Tashkent")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class User(Base, IdMixin, CreatedMixin):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    is_superadmin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class ClinicMembership(Base, IdMixin, CreatedMixin):
    __tablename__ = "clinic_memberships"
    __table_args__ = (UniqueConstraint("clinic_id", "user_id"),)
    clinic_id: Mapped[uuid.UUID] = _fk("clinics.id")
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    role: Mapped[Role] = mapped_column(_enum(Role, "role"))


class RefreshToken(Base, IdMixin, CreatedMixin):
    __tablename__ = "refresh_tokens"
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Doctor(Base, IdMixin, CreatedMixin):
    __tablename__ = "doctors"
    clinic_id: Mapped[uuid.UUID] = _fk("clinics.id")
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    full_name: Mapped[str] = mapped_column(String(200))
    specialty: Mapped[str] = mapped_column(String(120), server_default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Service(Base, IdMixin, CreatedMixin):
    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="duration_positive"),
        CheckConstraint("price_minor >= 0", name="price_nonneg"),
    )
    clinic_id: Mapped[uuid.UUID] = _fk("clinics.id")
    name: Mapped[str] = mapped_column(String(200))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price_minor: Mapped[int] = mapped_column(Integer)  # integer minor units (tiyin)
    currency: Mapped[str] = mapped_column(String(3), server_default="UZS")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class DoctorService(Base):
    __tablename__ = "doctor_services"
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), primary_key=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), primary_key=True
    )
    clinic_id: Mapped[uuid.UUID] = _fk("clinics.id")


class WorkingHours(Base, IdMixin):
    """Several intervals per weekday are allowed (e.g. 09-13 and 14-18)."""

    __tablename__ = "working_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("start_time < end_time", name="start_before_end"),
    )
    clinic_id: Mapped[uuid.UUID] = _fk("clinics.id")
    doctor_id: Mapped[uuid.UUID] = _fk("doctors.id")
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0 = Monday
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)


class TimeOff(Base, IdMixin):
    __tablename__ = "time_off"
    clinic_id: Mapped[uuid.UUID] = _fk("clinics.id")
    doctor_id: Mapped[uuid.UUID] = _fk("doctors.id")
    during: Mapped[Range[datetime]] = mapped_column(TSTZRANGE)
    reason: Mapped[str] = mapped_column(String(200), server_default="")


class Patient(Base, IdMixin, CreatedMixin):
    __tablename__ = "patients"
    __table_args__ = (UniqueConstraint("clinic_id", "phone"),)
    clinic_id: Mapped[uuid.UUID] = _fk("clinics.id")
    phone: Mapped[str] = mapped_column(String(20))
    full_name: Mapped[str] = mapped_column(String(200))
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)


class Appointment(Base, IdMixin, CreatedMixin):
    __tablename__ = "appointments"
    __table_args__ = (
        ExcludeConstraint(
            ("doctor_id", "="),
            ("during", "&&"),
            using="gist",
            where=text("status IN ('booked','confirmed')"),
            name="appointments_no_overlap",
        ),
    )
    clinic_id: Mapped[uuid.UUID] = _fk("clinics.id")
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT"), index=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("services.id", ondelete="RESTRICT")
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), index=True
    )
    during: Mapped[Range[datetime]] = mapped_column(TSTZRANGE)
    status: Mapped[AppointmentStatus] = mapped_column(
        _enum(AppointmentStatus, "appointment_status"), server_default="booked"
    )


class Notification(Base, IdMixin, CreatedMixin):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("appointment_id", "kind"),)
    clinic_id: Mapped[uuid.UUID] = _fk("clinics.id")
    appointment_id: Mapped[uuid.UUID] = _fk("appointments.id")
    kind: Mapped[str] = mapped_column(String(32))  # reminder_24h | reminder_2h
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base, IdMixin):
    __tablename__ = "audit_log"
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
