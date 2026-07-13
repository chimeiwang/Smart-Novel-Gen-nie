from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import fakeredis.aioredis
import pytest
from inkforge_agents.queue.consumer import QueueConsumer
from inkforge_agents.queue.repository import QueueJob, RedisRunQueue


def job(job_id: str) -> QueueJob:
    return QueueJob(
        jobId=job_id,
        kind="writing",
        runId=f"run-{job_id}",
        taskId=f"task-{job_id}",
        novelId="novel-1",
        userId="user-1",
        priority=10,
        payload={},
        createdAt=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_consumer_runs_one_job_at_a_time_and_acknowledges() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    await queue.enqueue(job("one"))
    await queue.enqueue(job("two"))
    active = 0
    maximum = 0

    async def handler(current: QueueJob) -> None:
        nonlocal active, maximum
        del current
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        active -= 1

    consumer = QueueConsumer(queue, {"writing": handler})
    assert await consumer.run_once() is True
    assert await consumer.run_once() is True
    assert maximum == 1
    assert await queue.status("one") == "completed"
    assert await queue.status("two") == "completed"


@pytest.mark.asyncio
async def test_consumer_retries_recoverable_failure_then_marks_terminal_failure() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    await queue.enqueue(job("retry"))
    attempts = 0

    async def handler(current: QueueJob) -> None:
        nonlocal attempts
        del current
        attempts += 1
        raise RuntimeError("暂时失败")

    consumer = QueueConsumer(
        queue,
        {"writing": handler},
        max_attempts=2,
        retry_delay=timedelta(0),
    )
    assert await consumer.run_once() is True
    assert await queue.status("retry") == "queued"
    assert await consumer.run_once() is True
    assert await queue.status("retry") == "failed"


@pytest.mark.asyncio
async def test_consumer_does_not_retry_non_retryable_failure() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    await queue.enqueue(job("no-retry"))
    attempts = 0

    class NonRetryableJobError(RuntimeError):
        retryable = False

    async def handler(current: QueueJob) -> None:
        nonlocal attempts
        del current
        attempts += 1
        raise NonRetryableJobError("失败已上报")

    consumer = QueueConsumer(queue, {"writing": handler})

    assert await consumer.run_once() is True
    assert attempts == 1
    assert await queue.status("no-retry") == "failed"


@pytest.mark.asyncio
async def test_consumer_graceful_stop_does_not_cancel_active_job() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    await queue.enqueue(job("slow"))
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(current: QueueJob) -> None:
        del current
        started.set()
        await release.wait()

    consumer = QueueConsumer(queue, {"writing": handler}, poll_interval=0.01)
    task = asyncio.create_task(consumer.run())
    await started.wait()
    consumer.request_stop()
    await asyncio.sleep(0)
    assert task.done() is False
    release.set()
    await task
    assert await queue.status("slow") == "completed"
