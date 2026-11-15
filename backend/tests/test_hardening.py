import json
import logging
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import Settings, get_settings
from tests.helpers import PASSWORD, signup


async def test_global_rate_limit_returns_429_in_standard_format(client: AsyncClient, monkeypatch: Any) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "5")
    get_settings.cache_clear()
    codes = [(await client.get("/public/nope-clinic")).status_code for _ in range(8)]
    assert codes[:5] == [404] * 5 and codes[5:] == [429] * 3
    r = await client.get("/public/nope-clinic")
    assert r.json()["error"]["code"] == "RATE_LIMITED" and "retry_after" in r.json()["error"]["details"]
    assert (await client.get("/health")).status_code == 200  # health checks are exempt
    monkeypatch.delenv("RATE_LIMIT_PER_MINUTE")
    get_settings.cache_clear()


async def test_login_brute_force_is_throttled(client: AsyncClient, monkeypatch: Any) -> None:
    monkeypatch.setenv("AUTH_RATE_LIMIT_PER_MINUTE", "4")
    get_settings.cache_clear()
    a = await signup(client)  # counts as 1 auth call
    codes = []
    for _ in range(5):
        r = await client.post("/auth/login", json={"email": a["email"], "password": "wrong-password-x"})
        codes.append(r.status_code)
    assert codes == [401, 401, 401, 429, 429]
    monkeypatch.delenv("AUTH_RATE_LIMIT_PER_MINUTE")
    get_settings.cache_clear()


async def test_access_log_is_json_with_request_id(client: AsyncClient, caplog: pytest.LogCaptureFixture) -> None:
    from app.core.logging import JsonFormatter

    with caplog.at_level(logging.INFO, logger="docly.access"):
        r = await client.get("/public/nope-clinic", headers={"x-request-id": "req-abc-123"})
    assert r.headers["x-request-id"] == "req-abc-123"
    rec = next(x for x in caplog.records if x.name == "docly.access")
    line = json.loads(JsonFormatter().format(rec))
    assert line["request_id"] == "req-abc-123"
    assert line["method"] == "GET" and line["path"] == "/public/nope-clinic" and line["status"] == 404
    assert "duration_ms" in line


def test_production_refuses_unsafe_config() -> None:
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        Settings(env="prod", otp_sender="eskiz").validate_prod()
    with pytest.raises(RuntimeError, match="OTP_SENDER"):
        Settings(env="prod", jwt_secret="x" * 40, otp_sender="fake").validate_prod()
    Settings(env="prod", jwt_secret="x" * 40, otp_sender="eskiz").validate_prod()  # ok


async def test_login_ok_not_affected_by_normal_use(client: AsyncClient) -> None:
    a = await signup(client)
    r = await client.post("/auth/login", json={"email": a["email"], "password": PASSWORD})
    assert r.status_code == 200
