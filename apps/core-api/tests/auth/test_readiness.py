from __future__ import annotations

import asyncio

import pytest
from inkforge_core.auth.readiness import RedisReadiness


class RecoveringRedis:
    def __init__(self) -> None:
        self.result: bool | Exception = True

    async def ping(self) -> bool:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class SlowRedis:
    async def ping(self) -> bool:
        await asyncio.sleep(0.1)
        return True


@pytest.mark.asyncio
async def test_redis_readiness_reports_disconnect_and_recovery() -> None:
    redis = RecoveringRedis()
    readiness = RedisReadiness(redis, timeout_seconds=0.05)

    redis.result = ConnectionError("连接失败")
    assert await readiness.check() is False
    redis.result = True
    assert await readiness.check() is True


@pytest.mark.asyncio
async def test_redis_readiness_times_out_as_failed() -> None:
    readiness = RedisReadiness(SlowRedis(), timeout_seconds=0.001)
    assert await readiness.check() is False
