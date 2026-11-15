import uuid
from collections.abc import Awaitable, Callable

import redis.asyncio as aioredis
from fastapi import FastAPI, Request, Response
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import AppError, install_error_handlers
from app.core.logging import request_id_var, setup_logging
from app.db import engine


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title=get_settings().project_name, version="0.1.0")
    install_error_handlers(app)

    @app.middleware("http")
    async def request_id_mw(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request_id_var.set(rid)
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            r = aioredis.Redis.from_url(get_settings().redis_url)
            try:
                await r.ping()
            finally:
                await r.aclose()
        except Exception as exc:
            raise AppError("NOT_READY", "Dependency unavailable", 503) from exc
        return {"status": "ready"}

    return app


app = create_app()
