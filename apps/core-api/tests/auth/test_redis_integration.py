from __future__ import annotations

import asyncio

import fakeredis.aioredis
import pytest
from inkforge_core.auth.service import RedisRateLimiter
from inkforge_core.errors import ApiError


async def run_limit_attempt(
    limiter: RedisRateLimiter,
    action: str,
    client_identity: str,
    username: str,
) -> str:
    try:
        await limiter.check(  # type: ignore[arg-type]
            action,
            client_identity=client_identity,
            username=username,
        )
    except ApiError as exc:
        return exc.code
    return "ok"


@pytest.mark.asyncio
async def test_register_source_bucket_cannot_be_bypassed_with_new_usernames() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    limiter = RedisRateLimiter(redis, key_prefix="测试:注册来源:")

    results = await asyncio.gather(
        *[
            run_limit_attempt(limiter, "register", "198.51.100.10", f"user-{index}")
            for index in range(4)
        ]
    )

    assert results.count("ok") == 3
    assert results.count("RATE_LIMITED") == 1
    source_keys = await redis.keys("测试:注册来源:register:source:*")
    assert len(source_keys) == 1
    ttl_ms = await redis.pttl(source_keys[0])
    assert 0 < ttl_ms <= 3_600_000
    await redis.aclose()


@pytest.mark.asyncio
async def test_exceeded_source_bucket_does_not_create_rotated_account_keys() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    limiter = RedisRateLimiter(redis, key_prefix="测试:来源上界:")

    initial_results = [
        await run_limit_attempt(limiter, "register", "198.51.100.10", f"initial-{index}")
        for index in range(4)
    ]
    assert initial_results == ["ok", "ok", "ok", "RATE_LIMITED"]
    source_keys = await redis.keys("测试:来源上界:register:source:*")
    assert len(source_keys) == 1
    ttl_before_rotation = await redis.pttl(source_keys[0])

    rotated_results = [
        await run_limit_attempt(limiter, "register", "198.51.100.10", f"rotated-{index}")
        for index in range(100)
    ]

    assert set(rotated_results) == {"RATE_LIMITED"}
    account_keys = await redis.keys("测试:来源上界:register:account:*")
    all_keys = await redis.keys("测试:来源上界:*")
    ttl_after_rotation = await redis.pttl(source_keys[0])
    assert len(account_keys) == 3
    assert len(all_keys) == 4
    assert 0 < ttl_after_rotation <= ttl_before_rotation <= 3_600_000

    with pytest.raises(ApiError) as caught:
        await limiter.check(
            "register",
            client_identity="198.51.100.10",
            username="final-rotation",
        )
    assert caught.value.code == "RATE_LIMITED"
    assert caught.value.headers is not None
    retry_after = int(caught.value.headers["Retry-After"])
    assert 1 <= retry_after <= 3_600
    await redis.aclose()


@pytest.mark.asyncio
async def test_login_account_bucket_is_atomic_under_concurrency() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    limiter = RedisRateLimiter(redis, key_prefix="测试:登录账号:")

    results = await asyncio.gather(
        *[
            run_limit_attempt(limiter, "login", "198.51.100.10", "alice")
            for _ in range(6)
        ]
    )

    assert results.count("ok") == 5
    assert results.count("RATE_LIMITED") == 1
    account_keys = await redis.keys("测试:登录账号:login:account:*")
    assert len(account_keys) == 1
    ttl_ms = await redis.pttl(account_keys[0])
    assert 0 < ttl_ms <= 60_000
    await redis.aclose()
