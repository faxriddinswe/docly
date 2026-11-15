"""One-time codes for public patients (identified by phone only).

OtpSender is an interface: FakeOtpSender is used in dev/tests (no SMS cost); EskizOtpSender is the
real transport (needs credentials -> docs/BLOCKERS.md). Codes are stored hashed in Redis with a TTL.
"""

import hashlib
import hmac
import re
import secrets
from typing import Protocol

import httpx
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.errors import AppError

PHONE_RE = re.compile(r"^\+998\d{9}$")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("998") and not digits.startswith("+"):
        digits = "+" + digits
    if len(digits) == 9 and digits.isdigit():
        digits = "+998" + digits
    if not PHONE_RE.match(digits):
        raise AppError("INVALID_PHONE", "Phone must look like +998901234567", 422)
    return digits


class OtpSender(Protocol):
    async def send(self, phone: str, code: str) -> None: ...


class FakeOtpSender:
    """Keeps the last code per phone in Redis for dev UIs and tests. Never used in prod."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def send(self, phone: str, code: str) -> None:
        await self.redis.set(f"otp:outbox:{phone}", code, ex=600)


class EskizOtpSender:
    BASE = "https://notify.eskiz.uz/api"

    def __init__(self, email: str, password: str, sender: str) -> None:
        self.email, self.password, self.sender = email, password, sender

    async def send(self, phone: str, code: str) -> None:
        async with httpx.AsyncClient(timeout=10) as c:
            login = await c.post(
                f"{self.BASE}/auth/login", data={"email": self.email, "password": self.password}
            )
            login.raise_for_status()
            token = login.json()["data"]["token"]
            r = await c.post(
                f"{self.BASE}/message/sms/send",
                headers={"Authorization": f"Bearer {token}"},
                data={
                    "mobile_phone": phone.lstrip("+"),
                    "message": f"Docly code: {code}",
                    "from": self.sender,
                },
            )
            r.raise_for_status()


def get_sender(redis: Redis) -> OtpSender:
    s = get_settings()
    if s.otp_sender == "eskiz":
        return EskizOtpSender(s.eskiz_email, s.eskiz_password, s.eskiz_from)
    return FakeOtpSender(redis)


def _digest(phone: str, code: str) -> str:
    return hashlib.sha256(f"{get_settings().jwt_secret}:{phone}:{code}".encode()).hexdigest()


async def request_code(redis: Redis, sender: OtpSender, phone: str) -> None:
    code = f"{secrets.randbelow(1_000_000):06d}"
    ttl = get_settings().otp_ttl_seconds
    await redis.set(f"otp:code:{phone}", _digest(phone, code), ex=ttl)
    await redis.delete(f"otp:attempts:{phone}")
    await sender.send(phone, code)


async def verify_code(redis: Redis, phone: str, code: str) -> None:
    """Single use; limited attempts so a 6-digit code cannot be brute-forced."""
    attempts = await redis.incr(f"otp:attempts:{phone}")
    await redis.expire(f"otp:attempts:{phone}", get_settings().otp_ttl_seconds)
    if attempts > get_settings().otp_max_attempts:
        await redis.delete(f"otp:code:{phone}")
        raise AppError("OTP_LOCKED", "Too many wrong codes; request a new one", 429)
    stored = await redis.get(f"otp:code:{phone}")
    if stored is None or not hmac.compare_digest(stored, _digest(phone, code)):
        raise AppError("OTP_INVALID", "Invalid or expired code", 422)
    await redis.delete(f"otp:code:{phone}", f"otp:attempts:{phone}")
