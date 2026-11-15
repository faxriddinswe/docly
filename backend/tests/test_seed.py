from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.seed import seed


async def test_seed_creates_two_clinics_idempotently(pg_urls: dict[str, str], monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("MIGRATION_DATABASE_URL", pg_urls["owner"])
    get_settings.cache_clear()
    await seed()
    await seed()
    eng = create_async_engine(pg_urls["owner"])
    async with eng.begin() as conn:
        await conn.execute(text("SELECT set_config('app.system','on',true)"))
        n = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM clinics WHERE slug IN ('smile-dental','chilonzor-medical')"
                )
            )
        ).scalar_one()
    await eng.dispose()
    get_settings.cache_clear()
    assert n == 2
