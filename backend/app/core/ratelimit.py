from app.core.errors import AppError
from app.core.redis import get_redis


async def rate_limit(key: str, limit: int, window_seconds: int) -> None:
    """Fixed-window counter in Redis. Raises 429 RATE_LIMITED when exceeded."""
    r = get_redis()
    k = f"rl:{key}"
    n = await r.incr(k)
    if n == 1:
        await r.expire(k, window_seconds)
    if n > limit:
        ttl = await r.ttl(k)
        raise AppError(
            "RATE_LIMITED", "Too many requests, try again later", 429, {"retry_after": max(ttl, 1)}
        )
