from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert "x-request-id" in r.headers


async def test_error_format() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/nope")
    assert r.status_code == 404
    assert set(r.json()["error"]) == {"code", "message", "details"}
