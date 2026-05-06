from collections.abc import AsyncGenerator
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends

from app.core.config import get_settings


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """Yield a Redis client for the duration of a request.

    Yields:
        Redis: An async Redis client connected to the configured instance.
    """
    settings = get_settings()
    client: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]
        settings.redis_url, encoding="utf-8", decode_responses=True
    )
    try:
        yield client
    finally:
        await client.aclose()


RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]
