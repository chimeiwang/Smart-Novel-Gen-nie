from __future__ import annotations

import asyncio
from typing import Protocol


class AsyncRedisPing(Protocol):
    async def ping(self) -> bool: ...


class RedisReadiness:
    """使用短超时探测认证限流所依赖的 Redis。"""

    def __init__(self, redis: AsyncRedisPing, *, timeout_seconds: float = 1.0) -> None:
        self._redis = redis
        self._timeout_seconds = timeout_seconds

    async def check(self) -> bool:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return bool(await self._redis.ping())
        except Exception:
            return False
