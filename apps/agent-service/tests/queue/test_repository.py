from datetime import UTC, datetime, timedelta
from typing import cast

import fakeredis.aioredis
import pytest
from inkforge_agents.queue.repository import JobStatus, QueueJob, RedisRunQueue


def job(job_id: str, *, priority: int = 10) -> QueueJob:
    return QueueJob(
        jobId=job_id,
        kind="writing",
        runId=f"run-{job_id}",
        taskId=f"task-{job_id}",
        novelId="novel-1",
        userId="user-1",
        priority=priority,
        payload={"resume": False},
        createdAt=datetime.now(UTC),
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
