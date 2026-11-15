import uuid

from pydantic import BaseModel, EmailStr, Field


class SignupIn(BaseModel):
    clinic_name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=3, max_length=61)
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    timezone: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    clinic_slug: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    clinic_id: uuid.UUID | None
    role: str | None


class MeOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    clinic_id: uuid.UUID | None
    role: str | None
    is_superadmin: bool
