import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.tables import AppointmentStatus


class PublicBookingIn(BaseModel):
    doctor_id: uuid.UUID
    service_id: uuid.UUID
    starts_at: datetime
    phone: str
    full_name: str = Field(min_length=2, max_length=200)
    otp_code: str = Field(min_length=4, max_length=8)

    @field_validator("starts_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("starts_at must include a timezone offset")
        return v


class StaffBookingIn(BaseModel):
    doctor_id: uuid.UUID
    service_id: uuid.UUID
    starts_at: datetime
    phone: str
    full_name: str = Field(min_length=2, max_length=200)

    @field_validator("starts_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("starts_at must include a timezone offset")
        return v


class OtpRequestIn(BaseModel):
    phone: str


class RescheduleIn(BaseModel):
    starts_at: datetime

    @field_validator("starts_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("starts_at must include a timezone offset")
        return v


class StatusIn(BaseModel):
    status: AppointmentStatus


class AppointmentOut(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    doctor_name: str
    service_id: uuid.UUID
    service_name: str
    patient_id: uuid.UUID
    patient_name: str
    patient_phone: str
    starts_at: datetime
    ends_at: datetime
    status: AppointmentStatus


class PublicBookingOut(BaseModel):
    appointment: AppointmentOut
    manage_token: str
    telegram_link: str | None = None


class PatientOut(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: str
    created_at: datetime
