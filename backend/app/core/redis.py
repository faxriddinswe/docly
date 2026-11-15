import redis.asyncio as aioredis

from app.core.config import get_settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def reset_redis() -> None:
    global _client
    client, _client = _client, None
    if client is not None:
        try:
            await client.aclose()
        except RuntimeError:  # its event loop is already closed (test teardown): nothing left to close
            pass
