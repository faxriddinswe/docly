import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID, clinic_id: uuid.UUID | None, role: str | None, is_superadmin: bool) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "cid": str(clinic_id) if clinic_id else None,
        "role": role,
        "sa": is_superadmin,
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_minutes),
        "typ": "access",
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    payload: dict[str, Any] = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def new_refresh_token() -> tuple[str, str]:
    """Returns (raw token for the client, sha256 hash for the DB). Raw is never stored."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_manage_token(appointment_id: uuid.UUID, clinic_id: uuid.UUID) -> str:
    """Capability token handed to the patient so they can view/cancel/reschedule one booking."""
    s = get_settings()
    exp = datetime.now(UTC) + timedelta(days=90)
    payload = {"aid": str(appointment_id), "cid": str(clinic_id), "typ": "manage", "exp": exp}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_manage_token(token: str) -> tuple[uuid.UUID, uuid.UUID]:
    payload: dict[str, Any] = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    if payload.get("typ") != "manage":
        raise jwt.InvalidTokenError("wrong token type")
    return uuid.UUID(payload["aid"]), uuid.UUID(payload["cid"])


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_link_token(patient_id: uuid.UUID, clinic_id: uuid.UUID, ttl_hours: int = 72) -> str:
    """Telegram /start payloads allow max 64 chars of [A-Za-z0-9_-]: 36 payload bytes + 12 MAC bytes = 64."""
    exp = int((datetime.now(UTC) + timedelta(hours=ttl_hours)).timestamp())
    body = patient_id.bytes + clinic_id.bytes + exp.to_bytes(4, "big")
    key = get_settings().jwt_secret.encode()
    mac = hmac.new(key, b"tglink" + body, hashlib.sha256).digest()[:12]
    return _b64(body) + _b64(mac)


def parse_link_token(token: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Returns (patient_id, clinic_id) or None if malformed/forged/expired."""
    if len(token) != 64:
        return None
    try:
        body, mac = _unb64(token[:48]), _unb64(token[48:])
    except ValueError:
        return None
    key = get_settings().jwt_secret.encode()
    good = hmac.new(key, b"tglink" + body, hashlib.sha256).digest()[:12]
    if len(body) != 36 or not hmac.compare_digest(mac, good):
        return None
    if int.from_bytes(body[32:], "big") < datetime.now(UTC).timestamp():
        return None
    return uuid.UUID(bytes=body[:16]), uuid.UUID(bytes=body[16:32])
