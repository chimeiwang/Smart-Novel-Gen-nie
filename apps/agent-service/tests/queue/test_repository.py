from datetime import UTC, datetime, timedelta
from typing import cast

import fakeredis.aioredis
import pytest
from inkforge_agents.queue.repository import JobStatus, QueueJob, RedisRunQueue


def job(
    job_id: str,
    *,
    priority: int = 10,
    created_at: datetime | None = None,
) -> QueueJob:
    return QueueJob(
        jobId=job_id,
        kind="writing",
        runId=f"run-{job_id}",
        taskId=f"task-{job_id}",
        novelId="novel-1",
        userId="user-1",
        priority=priority,
        payload={"resume": False},
        createdAt=created_at or datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_queue_orders_by_priority_and_is_idempotent() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")

    assert await queue.enqueue(job("low", priority=20)) is True
    assert await queue.enqueue(job("high", priority=0)) is True
    assert await queue.enqueue(job("high", priority=0)) is False

    first = await queue.claim(visibility_timeout=timedelta(seconds=30))
    second = await queue.claim(visibility_timeout=timedelta(seconds=30))
    assert first is not None and first.job.jobId == "high"
    assert second is not None and second.job.jobId == "low"


@pytest.mark.asyncio
async def test_queue_ack_requires_current_lease_and_duplicate_ack_is_safe() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    await queue.enqueue(job("one"))
    claim = await queue.claim(visibility_timeout=timedelta(seconds=30))
    assert claim is not None

    assert await queue.acknowledge(claim, status="completed") is True
    assert await queue.acknowledge(claim, status="completed") is False
    assert await queue.status("one") == "completed"


@pytest.mark.asyncio
async def test_terminal_ack_cleans_runtime_metadata_and_records_tombstone() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    queue = RedisRunQueue(redis, prefix="test:queue")
    await queue.enqueue(job("terminal-ack"))
    claim = await queue.claim(visibility_timeout=timedelta(seconds=30))
    assert claim is not None

    assert await queue.acknowledge(claim, status="completed") is True

    assert await redis.zscore("test:queue:ready", "terminal-ack") is None
    assert await redis.zscore("test:queue:processing", "terminal-ack") is None
    assert await redis.hget("test:queue:payloads", "terminal-ack") is None
    assert await redis.hget("test:queue:leases", "terminal-ack") is None
    assert await redis.hget("test:queue:attempts", "terminal-ack") is None
    assert await redis.hget("test:queue:scores", "terminal-ack") is None
    assert await redis.hget("test:queue:statuses", "terminal-ack") == b"completed"
    assert await redis.zscore("test:queue:terminal", "terminal-ack") is not None


@pytest.mark.asyncio
async def test_cancel_cleans_runtime_metadata_and_records_tombstone() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    queue = RedisRunQueue(redis, prefix="test:queue")
    await queue.enqueue(job("terminal-cancel"))
    claim = await queue.claim(visibility_timeout=timedelta(seconds=30))
    assert claim is not None

    assert await queue.cancel("terminal-cancel") is True

    assert await redis.zscore("test:queue:ready", "terminal-cancel") is None
    assert await redis.zscore("test:queue:processing", "terminal-cancel") is None
    assert await redis.hget("test:queue:payloads", "terminal-cancel") is None
    assert await redis.hget("test:queue:leases", "terminal-cancel") is None
    assert await redis.hget("test:queue:attempts", "terminal-cancel") is None
    assert await redis.hget("test:queue:scores", "terminal-cancel") is None
    assert await redis.hget("test:queue:statuses", "terminal-cancel") == b"cancelled"
    assert await redis.zscore("test:queue:terminal", "terminal-cancel") is not None


@pytest.mark.asyncio
async def test_purge_terminal_is_bounded_and_removes_expired_tombstones() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    queue = RedisRunQueue(redis, prefix="test:queue")
    terminal_at = datetime.now(UTC)
    for job_id in ("old-one", "old-two", "old-three"):
        await queue.enqueue(job(job_id))
        claim = await queue.claim(visibility_timeout=timedelta(seconds=30))
        assert claim is not None
        assert await queue.acknowledge(
            claim,
            status="completed",
            now=terminal_at,
        ) is True

    purged = await queue.purge_terminal(
        terminal_at + timedelta(seconds=1),
        limit=2,
    )

    assert purged == 2
    assert await redis.hlen("test:queue:statuses") == 1
    assert await redis.zcard("test:queue:terminal") == 1
    assert await queue.purge_terminal(
        terminal_at + timedelta(seconds=1),
        limit=2,
    ) == 1
    assert await redis.hlen("test:queue:statuses") == 0
    assert await redis.zcard("test:queue:terminal") == 0


def test_terminal_retention_defaults_to_seven_days_and_rejects_short_window() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")

    assert queue.terminal_retention == timedelta(days=7)
    with pytest.raises(ValueError, match="终态保留时间不能少于 24 小时"):
        RedisRunQueue(
            fakeredis.aioredis.FakeRedis(),
            prefix="test:short-retention",
            terminal_retention=timedelta(hours=23),
        )


@pytest.mark.asyncio
async def test_terminal_purge_rejects_unbounded_batch() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")

    with pytest.raises(ValueError, match="终态清理批次必须在 1 到 1000 之间"):
        await queue.purge_terminal(datetime.now(UTC), limit=1001)


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", ["completed", "failed", "cancelled"])
async def test_backfill_legacy_terminal_status_is_incremental_and_cleans_residue(
    terminal_status: str,
) -> None:
    redis = fakeredis.aioredis.FakeRedis()
    queue = RedisRunQueue(redis, prefix="test:queue")
    now = datetime.now(UTC)
    job_id = f"legacy-{terminal_status}"
    await redis.hset("test:queue:statuses", job_id, terminal_status)
    await redis.hset("test:queue:payloads", job_id, "legacy-payload")
    await redis.hset("test:queue:leases", job_id, "legacy-lease")
    await redis.hset("test:queue:attempts", job_id, 3)
    await redis.hset("test:queue:scores", job_id, 123)
    await redis.zadd("test:queue:ready", {job_id: 123})
    await redis.zadd("test:queue:processing", {job_id: 456})

    cursor, migrated = await queue.backfill_legacy_terminal(
        cursor=0,
        now=now,
        limit=10,
    )

    assert cursor == 0
    assert migrated == 1
    assert await redis.zscore("test:queue:terminal", job_id) == pytest.approx(
        now.timestamp() * 1000
    )
    assert await redis.hget("test:queue:statuses", job_id) is not None
    for key in ("payloads", "leases", "attempts", "scores"):
        assert await redis.hget(f"test:queue:{key}", job_id) is None
    assert await redis.zscore("test:queue:ready", job_id) is None
    assert await redis.zscore("test:queue:processing", job_id) is None


@pytest.mark.asyncio
async def test_backfill_legacy_terminal_rejects_unbounded_batch() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")

    with pytest.raises(ValueError, match="终态回填批次必须在 1 到 1000 之间"):
        await queue.backfill_legacy_terminal(cursor=0, limit=1001)


@pytest.mark.asyncio
async def test_expired_lease_is_recovered_and_stale_worker_cannot_ack() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    queue = RedisRunQueue(redis, prefix="test:queue")
    queued = job("recover")
    await queue.enqueue(queued)
    old = await queue.claim(
        visibility_timeout=timedelta(milliseconds=1),
        now=queued.createdAt,
    )
    assert old is not None

    recovered = await queue.recover_expired(now=queued.createdAt + timedelta(seconds=1))
    assert recovered == 1
    new = await queue.claim(visibility_timeout=timedelta(seconds=30))
    assert new is not None and new.job.jobId == "recover"
    assert new.leaseToken != old.leaseToken
    assert await queue.acknowledge(old, status="completed") is False


@pytest.mark.asyncio
async def test_recover_expired_terminalizes_running_job_when_score_is_missing() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    queue = RedisRunQueue(redis, prefix="test:queue")
    queued = job("missing-score")
    await queue.enqueue(queued)
    claim = await queue.claim(
        visibility_timeout=timedelta(milliseconds=1),
        now=queued.createdAt,
    )
    assert claim is not None
    await redis.hdel("test:queue:scores", queued.jobId)
    recovered_at = queued.createdAt + timedelta(seconds=1)

    assert await queue.recover_expired(now=recovered_at) == 0

    assert await queue.status(queued.jobId) == "failed"
    assert await redis.zscore("test:queue:processing", queued.jobId) is None
    assert await redis.hget("test:queue:leases", queued.jobId) is None
    assert await redis.hget("test:queue:payloads", queued.jobId) is None
    assert await redis.hget("test:queue:attempts", queued.jobId) is None
    assert await redis.zscore("test:queue:terminal", queued.jobId) == pytest.approx(
        recovered_at.timestamp() * 1000
    )


@pytest.mark.asyncio
async def test_force_enqueue_repairs_missing_ready_entry_without_duplicate_run() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    queue = RedisRunQueue(redis, prefix="test:queue")
    await queue.enqueue(job("lost"))
    await redis.zrem("test:queue:ready", "lost")

    assert await queue.claim(visibility_timeout=timedelta(seconds=30)) is None
    assert await queue.enqueue(job("lost"), force=True) is True
    claim = await queue.claim(visibility_timeout=timedelta(seconds=30))
    assert claim is not None and claim.job.jobId == "lost"


@pytest.mark.asyncio
async def test_future_high_priority_retry_does_not_block_due_lower_priority() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    queue = RedisRunQueue(redis, prefix="test:queue")
    now = datetime.now(UTC)
    await queue.enqueue(job("future-high", priority=0, created_at=now))
    high_claim = await queue.claim(
        visibility_timeout=timedelta(seconds=30),
        now=now,
    )
    assert high_claim is not None
    assert await queue.retry(
        high_claim,
        delay=timedelta(hours=1),
        now=now,
    ) is True
    await queue.enqueue(job("due-low", priority=10, created_at=now))

    claim = await queue.claim(
        visibility_timeout=timedelta(seconds=30),
        now=now,
    )

    assert claim is not None
    assert claim.job.jobId == "due-low"


@pytest.mark.asyncio
async def test_same_priority_claims_earliest_ready_time_first() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    now = datetime.now(UTC)
    await queue.enqueue(
        job("same-late", priority=5, created_at=now + timedelta(seconds=2))
    )
    await queue.enqueue(
        job("same-early", priority=5, created_at=now + timedelta(seconds=1))
    )

    claim = await queue.claim(
        visibility_timeout=timedelta(seconds=30),
        now=now + timedelta(seconds=3),
    )

    assert claim is not None
    assert claim.job.jobId == "same-early"


@pytest.mark.asyncio
async def test_retry_updates_score_used_by_lease_recovery() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    queue = RedisRunQueue(redis, prefix="test:queue")
    now = datetime.now(UTC)
    retry_at = now + timedelta(minutes=5)
    await queue.enqueue(job("retry-score", priority=7, created_at=now))
    claim = await queue.claim(
        visibility_timeout=timedelta(seconds=30),
        now=now,
    )
    assert claim is not None

    assert await queue.retry(
        claim,
        delay=timedelta(minutes=5),
        now=now,
    ) is True

    expected = 7 * 10_000_000_000_000 + int(retry_at.timestamp() * 1000)
    assert int(await redis.hget("test:queue:scores", "retry-score")) == expected


@pytest.mark.asyncio
async def test_claim_cleans_corrupt_candidate_and_continues_in_same_call() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    queue = RedisRunQueue(redis, prefix="test:queue")
    now = datetime.now(UTC)
    await queue.enqueue(job("corrupt", priority=0, created_at=now))
    await queue.enqueue(
        job("valid", priority=0, created_at=now + timedelta(milliseconds=1))
    )
    await redis.hdel("test:queue:payloads", "corrupt")

    claim = await queue.claim(
        visibility_timeout=timedelta(seconds=30),
        now=now + timedelta(seconds=1),
    )

    assert claim is not None
    assert claim.job.jobId == "valid"
    assert await redis.zscore("test:queue:ready", "corrupt") is None
    assert await redis.hget("test:queue:statuses", "corrupt") is None
    assert await redis.hget("test:queue:scores", "corrupt") is None


@pytest.mark.asyncio
async def test_claim_cleans_nonterminal_status_when_payload_is_missing() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    queue = RedisRunQueue(redis, prefix="test:queue")
    now = datetime.now(UTC)
    await queue.enqueue(job("corrupt-running", priority=0, created_at=now))
    await redis.hset("test:queue:statuses", "corrupt-running", "running")
    await redis.hdel("test:queue:payloads", "corrupt-running")

    assert await queue.claim(
        visibility_timeout=timedelta(seconds=30),
        now=now + timedelta(seconds=1),
    ) is None
    assert await redis.hget("test:queue:statuses", "corrupt-running") is None
    assert await redis.hget("test:queue:scores", "corrupt-running") is None


@pytest.mark.asyncio
async def test_claim_bounds_corrupt_candidate_cleanup_per_call() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    queue = RedisRunQueue(redis, prefix="test:queue")
    now = datetime.now(UTC)
    for index in range(101):
        job_id = f"corrupt-{index:03d}"
        await queue.enqueue(job(job_id, priority=0, created_at=now))
        await redis.hdel("test:queue:payloads", job_id)
    await queue.enqueue(job("valid-low", priority=10, created_at=now))

    first = await queue.claim(
        visibility_timeout=timedelta(seconds=30),
        now=now + timedelta(seconds=1),
    )
    second = await queue.claim(
        visibility_timeout=timedelta(seconds=30),
        now=now + timedelta(seconds=1),
    )

    assert first is None
    assert second is not None
    assert second.job.jobId == "valid-low"


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", ["completed", "failed", "cancelled"])
async def test_force_enqueue_never_reopens_terminal_job(terminal_status: str) -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    terminal_job = job(terminal_status)
    await queue.enqueue(terminal_job)
    claim = await queue.claim(visibility_timeout=timedelta(seconds=30))
    assert claim is not None
    await queue.acknowledge(claim, status=cast(JobStatus, terminal_status))

    assert await queue.enqueue(terminal_job, force=True) is False
    assert await queue.status(terminal_job.jobId) == terminal_status
    assert await queue.claim(visibility_timeout=timedelta(seconds=30)) is None


@pytest.mark.asyncio
async def test_cancel_removes_queued_or_running_job() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    await queue.enqueue(job("cancel"))

    assert await queue.cancel("cancel") is True
    assert await queue.status("cancel") == "cancelled"
    assert await queue.claim(visibility_timeout=timedelta(seconds=30)) is None
