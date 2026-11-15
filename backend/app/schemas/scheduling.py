import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DoctorIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    specialty: str = Field(default="", max_length=120)
    user_id: uuid.UUID | None = None


class DoctorPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    specialty: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None


class DoctorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    specialty: str
    is_active: bool
    service_ids: list[uuid.UUID] = []


class ServiceIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    duration_minutes: int = Field(gt=0, le=480)
    price_minor: int = Field(ge=0)
    currency: str = Field(default="UZS", min_length=3, max_length=3)


class ServicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    duration_minutes: int | None = Field(default=None, gt=0, le=480)
    price_minor: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    duration_minutes: int
    price_minor: int
    currency: str
    is_active: bool


class DoctorServicesIn(BaseModel):
    service_ids: list[uuid.UUID]


class WorkingInterval(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0 = Monday")
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def _ordered(self) -> "WorkingInterval":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class WorkingHoursIn(BaseModel):
    intervals: list[WorkingInterval]


class TimeOffIn(BaseModel):
    starts_at: datetime
    ends_at: datetime
    reason: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def _valid(self) -> "TimeOffIn":
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("datetimes must include a timezone offset")
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        return self


class TimeOffOut(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    reason: str


class SlotsOut(BaseModel):
    date: str
    timezone: str
    slots: list[datetime]


class PublicClinicOut(BaseModel):
    name: str
    slug: str
    timezone: str
    services: list[ServiceOut]
    doctors: list[DoctorOut]
