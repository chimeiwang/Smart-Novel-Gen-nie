from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import fakeredis.aioredis
import pytest
from inkforge_agents.clients.core import CoreServiceError
from inkforge_agents.queue.consumer import QueueConsumer
from inkforge_agents.queue.repository import JobKind, QueueJob, RedisRunQueue
from redis.exceptions import ResponseError


def job(
    job_id: str,
    *,
    novel_id: str = "novel-1",
    kind: JobKind = "writing",
) -> QueueJob:
    return QueueJob(
        jobId=job_id,
        kind=kind,
        runId=f"run-{job_id}",
        taskId=f"task-{job_id}",
        novelId=novel_id,
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
@pytest.mark.parametrize(
    ("max_concurrency", "expected_maximum"),
    [(1, 1), (2, 2), (3, 3)],
)
async def test_consumer_limits_parallel_jobs(
    max_concurrency: int,
    expected_maximum: int,
) -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    job_ids = ("one", "two", "three", "four")
    for index, job_id in enumerate(job_ids):
        await queue.enqueue(job(job_id, novel_id=f"novel-{index}"))
    active = 0
    started = 0
    maximum = 0
    capacity_reached = asyncio.Event()
    all_finished = asyncio.Event()
    release = asyncio.Event()

    async def handler(current: QueueJob) -> None:
        nonlocal active, started, maximum
        del current
        active += 1
        started += 1
        maximum = max(maximum, active)
        if started == expected_maximum:
            capacity_reached.set()
        await release.wait()
        active -= 1
        if started == len(job_ids) and active == 0:
            all_finished.set()

    consumer = QueueConsumer(
        queue,
        {"writing": handler},
        max_concurrency=max_concurrency,
        poll_interval=0.001,
    )
    consumer_task = asyncio.create_task(consumer.run())
    try:
        await asyncio.wait_for(capacity_reached.wait(), timeout=1)
        await asyncio.sleep(0.01)
        assert started == expected_maximum
        assert maximum == expected_maximum
        release.set()
        await asyncio.wait_for(all_finished.wait(), timeout=1)
    finally:
        release.set()
        consumer.request_stop()
        await asyncio.wait_for(consumer_task, timeout=1)

    for job_id in job_ids:
        assert await queue.status(job_id) == "completed"


@pytest.mark.asyncio
async def test_consumer_serializes_same_project_without_blocking_other_project() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    await queue.enqueue(job("a-1-writing", novel_id="novel-a", kind="writing"))
    await queue.enqueue(job("a-2-quality", novel_id="novel-a", kind="quality"))
    await queue.enqueue(job("a-3-rag", novel_id="novel-a", kind="rag"))
    await queue.enqueue(job("b-writing", novel_id="novel-b", kind="writing"))
    await queue.enqueue(job("c-quality", novel_id="novel-c", kind="quality"))
    active_projects: set[str] = set()
    first_a_started = asyncio.Event()
    second_a_started = asyncio.Event()
    third_a_started = asyncio.Event()
    b_started = asyncio.Event()
    c_started = asyncio.Event()
    release_initial = asyncio.Event()

    async def handler(current: QueueJob) -> None:
        assert current.novelId not in active_projects
        active_projects.add(current.novelId)
        try:
            if current.jobId == "a-1-writing":
                first_a_started.set()
                await release_initial.wait()
            elif current.jobId == "a-2-quality":
                second_a_started.set()
            elif current.jobId == "a-3-rag":
                third_a_started.set()
            elif current.jobId == "b-writing":
                b_started.set()
                await release_initial.wait()
            else:
                c_started.set()
                await release_initial.wait()
        finally:
            active_projects.remove(current.novelId)

    consumer = QueueConsumer(
        queue,
        {"writing": handler, "quality": handler, "rag": handler},
        max_concurrency=3,
        poll_interval=0.001,
        project_deferral_delay=timedelta(milliseconds=5),
    )
    consumer_task = asyncio.create_task(consumer.run())
    try:
        await asyncio.wait_for(first_a_started.wait(), timeout=1)
        await asyncio.wait_for(b_started.wait(), timeout=1)
        await asyncio.wait_for(c_started.wait(), timeout=1)
        await asyncio.sleep(0.02)
        assert second_a_started.is_set() is False
        assert third_a_started.is_set() is False

        release_initial.set()
        await asyncio.wait_for(second_a_started.wait(), timeout=1)
        await asyncio.wait_for(third_a_started.wait(), timeout=1)
    finally:
        release_initial.set()
        consumer.request_stop()
        await asyncio.wait_for(consumer_task, timeout=1)

    assert await queue.status("a-1-writing") == "completed"
    assert await queue.status("a-2-quality") == "completed"
    assert await queue.status("a-3-rag") == "completed"
    assert await queue.status("b-writing") == "completed"
    assert await queue.status("c-quality") == "completed"


@pytest.mark.asyncio
async def test_consumer_drains_claimed_job_before_supervisor_failure() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    for index, job_id in enumerate(("bad", "slow", "third")):
        await queue.enqueue(job(job_id, novel_id=f"novel-{index}"))
    slow_started = asyncio.Event()
    release_slow = asyncio.Event()
    third_started = asyncio.Event()

    async def handler(current: QueueJob) -> None:
        if current.jobId == "bad":
            await slow_started.wait()
            raise TypeError("模拟并发槽程序错误")
        if current.jobId == "slow":
            slow_started.set()
            await release_slow.wait()
            return
        third_started.set()

    consumer = QueueConsumer(
        queue,
        {"writing": handler},
        max_concurrency=2,
        poll_interval=0.001,
    )
    consumer_task = asyncio.create_task(consumer.run())
    await asyncio.wait_for(slow_started.wait(), timeout=1)
    await asyncio.sleep(0.01)

    assert third_started.is_set() is False
    assert consumer_task.done() is False
    assert consumer.is_healthy() is False

    release_slow.set()
    with pytest.raises(TypeError, match="模拟并发槽程序错误"):
        await asyncio.wait_for(consumer_task, timeout=1)

    assert await queue.status("bad") == "failed"
    assert await queue.status("slow") == "completed"
    assert await queue.status("third") == "queued"

    restarted = asyncio.create_task(consumer.run())
    await asyncio.wait_for(third_started.wait(), timeout=1)
    assert consumer.is_healthy() is True
    consumer.request_stop()
    await asyncio.wait_for(restarted, timeout=1)
    assert await queue.status("third") == "completed"


@pytest.mark.asyncio
async def test_consumer_retries_recoverable_failure_then_marks_terminal_failure() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    await queue.enqueue(job("retry"))
    attempts = 0

    class RetryableJobError(RuntimeError):
        retryable = True

    async def handler(current: QueueJob) -> None:
        nonlocal attempts
        del current
        attempts += 1
        raise RetryableJobError("暂时失败")

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
async def test_consumer_maps_core_recoverable_false_to_terminal_failure() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    await queue.enqueue(job("core-non-recoverable"))
    attempts = 0

    async def handler(current: QueueJob) -> None:
        nonlocal attempts
        del current
        attempts += 1
        raise CoreServiceError("核心服务拒绝请求", recoverable=False)

    consumer = QueueConsumer(
        queue,
        {"writing": handler},
        max_attempts=3,
        retry_delay=timedelta(0),
    )

    assert await consumer.run_once() is True
    assert attempts == 1
    assert await queue.status("core-non-recoverable") == "failed"


@pytest.mark.asyncio
async def test_consumer_propagates_unknown_type_error_from_handler() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    await queue.enqueue(job("programming-error"))

    async def handler(current: QueueJob) -> None:
        del current
        raise TypeError("模拟程序契约错误")

    consumer = QueueConsumer(queue, {"writing": handler})

    with pytest.raises(TypeError, match="模拟程序契约错误"):
        await consumer.run_once()

    assert await queue.status("programming-error") == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ValueError("值处理错误"),
        RuntimeError("未知运行错误"),
        KeyError("缺少字段"),
    ],
)
async def test_consumer_propagates_job_errors_without_retry_contract(
    error: Exception,
) -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    await queue.enqueue(job("unknown-job-error"))

    async def handler(current: QueueJob) -> None:
        del current
        raise error

    consumer = QueueConsumer(queue, {"writing": handler})

    with pytest.raises(type(error)):
        await consumer.run_once()

    assert await queue.status("unknown-job-error") == "failed"


@pytest.mark.asyncio
async def test_consumer_purges_expired_terminal_tombstones() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    queue = RedisRunQueue(redis, prefix="test:queue")
    now = datetime.now(UTC)
    await queue.enqueue(job("expired-terminal"))
    claim = await queue.claim(
        visibility_timeout=timedelta(seconds=30),
        now=now,
    )
    assert claim is not None
    await queue.acknowledge(
        claim,
        status="completed",
        now=now - timedelta(days=8),
    )
    consumer = QueueConsumer(
        queue,
        {"writing": lambda _job: asyncio.sleep(0)},
        terminal_purge_interval=60,
        clock=lambda: now,
    )

    assert await consumer.run_once() is False
    assert await queue.status("expired-terminal") is None


@pytest.mark.asyncio
async def test_consumer_run_propagates_unknown_loop_error() -> None:
    class BrokenQueue:
        terminal_retention = timedelta(days=7)

        async def purge_terminal(self, *args, **kwargs):
            del args, kwargs
            return 0

        async def recover_expired(self):
            raise TypeError("模拟循环程序错误")

    consumer = QueueConsumer(
        BrokenQueue(),  # type: ignore[arg-type]
        {},
        poll_interval=0.001,
        infrastructure_retry_base=0.001,
        infrastructure_retry_max=0.002,
    )

    with pytest.raises(TypeError, match="模拟循环程序错误"):
        await asyncio.wait_for(consumer.run(), timeout=0.1)


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


@pytest.mark.asyncio
async def test_parallel_consumer_stops_claiming_and_drains_active_jobs() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    job_ids = ("one", "two", "three", "four")
    for index, job_id in enumerate(job_ids):
        await queue.enqueue(job(job_id, novel_id=f"novel-{index}"))
    started: set[str] = set()
    capacity_reached = asyncio.Event()
    release = asyncio.Event()

    async def handler(current: QueueJob) -> None:
        started.add(current.jobId)
        if len(started) == 3:
            capacity_reached.set()
        await release.wait()

    consumer = QueueConsumer(
        queue,
        {"writing": handler},
        max_concurrency=3,
        poll_interval=0.001,
    )
    task = asyncio.create_task(consumer.run())
    await asyncio.wait_for(capacity_reached.wait(), timeout=1)
    consumer.request_stop()
    await asyncio.sleep(0)

    assert task.done() is False
    assert len(started) == 3

    release.set()
    await asyncio.wait_for(task, timeout=1)
    statuses = [await queue.status(job_id) for job_id in job_ids]
    assert statuses.count("completed") == 3
    assert statuses.count("queued") == 1


@pytest.mark.asyncio
async def test_consumer_cancels_handler_when_heartbeat_infrastructure_fails() -> None:
    inner = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    await inner.enqueue(job("heartbeat"))
    release = asyncio.Event()
    cancelled = asyncio.Event()

    class HeartbeatFailureQueue:
        @property
        def terminal_retention(self):
            return inner.terminal_retention

        async def purge_terminal(self, *args, **kwargs):
            return await inner.purge_terminal(*args, **kwargs)

        async def recover_expired(self):
            return await inner.recover_expired()

        async def claim(self, *, visibility_timeout):
            return await inner.claim(visibility_timeout=visibility_timeout)

        async def acknowledge(self, *args, **kwargs):
            return await inner.acknowledge(*args, **kwargs)

        async def retry(self, *args, **kwargs):
            return await inner.retry(*args, **kwargs)

        async def extend(self, *args, **kwargs):
            del args, kwargs
            raise ConnectionError("模拟 Redis 续租失败")

    async def handler(current: QueueJob) -> None:
        assert current.jobId == "heartbeat"
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    consumer = QueueConsumer(
        HeartbeatFailureQueue(),  # type: ignore[arg-type]
        {"writing": handler},
        visibility_timeout=timedelta(milliseconds=30),
        retry_delay=timedelta(0),
    )

    with pytest.raises(ConnectionError, match="模拟 Redis 续租失败"):
        await consumer.run_once()
    was_cancelled = cancelled.is_set()
    release.set()
    await asyncio.sleep(0)

    assert was_cancelled is True
    assert await inner.status("heartbeat") == "queued"


@pytest.mark.asyncio
async def test_consumer_treats_cancelled_lease_as_known_condition() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    await queue.enqueue(job("cancelled"))
    started = asyncio.Event()
    handler_cancelled = asyncio.Event()
    follow_up_completed = asyncio.Event()

    async def handler(current: QueueJob) -> None:
        if current.jobId == "after-cancel":
            follow_up_completed.set()
            return
        assert current.jobId == "cancelled"
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            handler_cancelled.set()
            raise

    consumer = QueueConsumer(
        queue,
        {"writing": handler},
        visibility_timeout=timedelta(milliseconds=30),
    )
    task = asyncio.create_task(consumer.run_once())
    await asyncio.wait_for(started.wait(), timeout=1)
    assert await queue.cancel("cancelled") is True

    assert await asyncio.wait_for(task, timeout=1) is True
    assert handler_cancelled.is_set() is True
    assert await queue.status("cancelled") == "cancelled"

    await queue.enqueue(job("after-cancel"))
    assert await consumer.run_once() is True
    assert follow_up_completed.is_set() is True
    assert await queue.status("after-cancel") == "completed"


@pytest.mark.asyncio
async def test_consumer_backfills_legacy_terminal_status_before_purge() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    queue = RedisRunQueue(redis, prefix="test:queue")
    now = datetime.now(UTC)
    await redis.hset("test:queue:statuses", "legacy", "completed")
    await redis.hset("test:queue:scores", "legacy", 123)
    consumer = QueueConsumer(queue, {}, clock=lambda: now)

    assert await consumer.run_once() is False

    assert await redis.zscore("test:queue:terminal", "legacy") == pytest.approx(
        now.timestamp() * 1000
    )
    assert await redis.hget("test:queue:scores", "legacy") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_method", ["recover_expired", "claim"])
async def test_consumer_recovers_after_one_queue_infrastructure_failure(
    failure_method: str,
) -> None:
    inner = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:queue")
    await inner.enqueue(job("recover"))
    handled = asyncio.Event()

    class FlakyQueue:
        def __init__(self) -> None:
            self.failed = False

        @property
        def terminal_retention(self):
            return inner.terminal_retention

        async def purge_terminal(self, *args, **kwargs):
            return await inner.purge_terminal(*args, **kwargs)

        async def recover_expired(self):
            if failure_method == "recover_expired" and not self.failed:
                self.failed = True
                raise ConnectionError("模拟 Redis 恢复租约失败")
            return await inner.recover_expired()

        async def claim(self, *, visibility_timeout):
            if failure_method == "claim" and not self.failed:
                self.failed = True
                raise ConnectionError("模拟 Redis 领取失败")
            return await inner.claim(visibility_timeout=visibility_timeout)

        async def acknowledge(self, *args, **kwargs):
            return await inner.acknowledge(*args, **kwargs)

        async def retry(self, *args, **kwargs):
            return await inner.retry(*args, **kwargs)

        async def extend(self, *args, **kwargs):
            return await inner.extend(*args, **kwargs)

    async def handler(current: QueueJob) -> None:
        assert current.jobId == "recover"
        handled.set()

    consumer = QueueConsumer(
        FlakyQueue(),  # type: ignore[arg-type]
        {"writing": handler},
        poll_interval=0.001,
        infrastructure_retry_base=0.001,
        infrastructure_retry_max=0.002,
    )
    task = asyncio.create_task(consumer.run())
    await asyncio.wait_for(handled.wait(), timeout=1)
    consumer.request_stop()
    await task

    assert await inner.status("recover") == "completed"


@pytest.mark.asyncio
async def test_consumer_propagates_redis_oom_to_supervisor() -> None:
    class OomQueue:
        terminal_retention = timedelta(days=7)

        async def purge_terminal(self, *args, **kwargs):
            del args, kwargs
            raise ResponseError("OOM command not allowed when used memory > maxmemory")

    consumer = QueueConsumer(
        OomQueue(),  # type: ignore[arg-type]
        {},
        infrastructure_retry_base=0.001,
        infrastructure_retry_max=0.002,
    )

    with pytest.raises(ResponseError, match="OOM"):
        await asyncio.wait_for(consumer.run(), timeout=0.05)


@pytest.mark.asyncio
async def test_consumer_propagates_persistent_infrastructure_failure() -> None:
    class OfflineQueue:
        terminal_retention = timedelta(days=7)

        def __init__(self) -> None:
            self.calls = 0

        async def purge_terminal(self, *args, **kwargs):
            del args, kwargs
            self.calls += 1
            raise ConnectionError("Redis 持续断开")

    queue = OfflineQueue()
    consumer = QueueConsumer(
        queue,  # type: ignore[arg-type]
        {},
        infrastructure_retry_base=0.001,
        infrastructure_retry_max=0.002,
        infrastructure_failure_threshold=2,
    )

    with pytest.raises(ConnectionError, match="Redis 持续断开"):
        await asyncio.wait_for(consumer.run(), timeout=0.05)

    assert queue.calls == 2
