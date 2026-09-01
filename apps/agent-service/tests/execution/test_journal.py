from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast

import fakeredis.aioredis
import pytest
from inkforge_agents.execution.journal import (
    AsyncJournalRedis,
    ExecutionJournalConflictError,
    ExecutionJournalError,
    ExecutionJournalStaleFenceError,
    RedisExecutionJournal,
)

from .support import execution_cancel, execution_request, execution_result


def _journal() -> RedisExecutionJournal:
    return RedisExecutionJournal(
        cast(AsyncJournalRedis, fakeredis.aioredis.FakeRedis()),
        prefix="test:executions",
    )


@pytest.mark.asyncio
async def test_same_request_hash_reuses_frozen_resolved_model() -> None:
    journal = _journal()
    request = execution_request()
    first = await journal.accept(
        request,
        {"provider": "fake", "model": "model-a", "profile": "writer.v1"},
    )
    duplicate = await journal.accept(
        request,
        {"provider": "fake", "model": "model-b", "profile": "writer.v1"},
    )

    assert first.state == "accepted"
    assert duplicate.resolved_model == {
        "provider": "fake",
        "model": "model-a",
        "profile": "writer.v1",
    }


@pytest.mark.asyncio
async def test_different_request_hash_for_same_step_fails_closed() -> None:
    journal = _journal()
    await journal.accept(execution_request(), {"provider": "fake"})

    with pytest.raises(ExecutionJournalConflictError):
        await journal.accept(
            execution_request(input_value={"instruction": "另一条指令"}),
            {"provider": "fake"},
        )


@pytest.mark.asyncio
async def test_started_and_provider_attempt_are_persisted_before_terminal() -> None:
    journal = _journal()
    request = execution_request()
    await journal.accept(request, {"provider": "fake"})

    started = await journal.mark_started(
        request,
        now=datetime(2026, 9, 1, tzinfo=UTC),
    )
    provider_started_at = datetime(2026, 9, 1, 0, 0, 5, tzinfo=UTC)
    attempt = await journal.begin_provider_attempt(request, now=provider_started_at)

    assert started.state == "started"
    assert started.started_at == datetime(2026, 9, 1, tzinfo=UTC)
    assert attempt == 1
    entry = await journal.require(request.stepId)
    assert entry.provider_attempts == 1
    assert entry.provider_started_at == provider_started_at


@pytest.mark.asyncio
async def test_terminal_result_is_replayed_under_newer_fence_without_recomputation() -> None:
    journal = _journal()
    first_request = execution_request()
    await journal.accept(first_request, {"provider": "fake"})
    await journal.mark_started(first_request)
    await journal.begin_provider_attempt(first_request)
    await journal.record_terminal(first_request, execution_result(first_request))

    new_fence = first_request.model_copy(update={"jobId": "job-2", "fencingToken": 2})
    rebound = await journal.accept(new_fence, {"provider": "other"})

    assert rebound.state == "result"
    assert rebound.job_id == "job-2"
    assert rebound.fencing_token == 2
    assert rebound.terminal is not None
    assert rebound.terminal.resultHash == execution_result(first_request).resultHash
    assert rebound.terminal.jobId == "job-2"
    assert rebound.terminal.fencingToken == 2

    with pytest.raises(ExecutionJournalStaleFenceError):
        await journal.accept(first_request, {"provider": "fake"})


@pytest.mark.asyncio
async def test_cancel_requires_exact_identity_and_is_idempotent() -> None:
    journal = _journal()
    request = execution_request()
    await journal.accept(request, {"provider": "fake"})
    cancel = execution_cancel(request)

    accepted = await journal.request_cancel(cancel)
    duplicate = await journal.request_cancel(cancel)
    wrong_job = await journal.request_cancel(cancel.model_copy(update={"jobId": "wrong"}))

    assert accepted.status == "accepted"
    assert duplicate.status == "already_cancelled"
    assert wrong_job.status == "not_found"


@pytest.mark.asyncio
async def test_only_delivered_terminal_gets_retention_ttl() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    journal = RedisExecutionJournal(
        cast(AsyncJournalRedis, redis),
        prefix="test:durable",
        retention=timedelta(days=2),
    )
    request = execution_request()
    key = f"test:durable:{request.stepId}"

    await journal.accept(request, {"provider": "fake"})
    assert await redis.ttl(key) == -1
    await journal.mark_started(request)
    assert await redis.ttl(key) == -1
    await journal.begin_provider_attempt(request)
    terminal = execution_result(request)
    await journal.record_terminal(request, terminal)
    assert await redis.ttl(key) == -1
    assert (await journal.backlog()).callback_pending == 1

    await journal.mark_callback_rejected(
        step_id=request.stepId,
        request_hash=request.requestHash,
        result_hash=terminal.resultHash,
        error_code="EXECUTION_CALLBACK_REJECTED",
    )
    assert await redis.ttl(key) == -1
    assert (await journal.backlog()).callback_rejected == 1

    await journal.mark_callback_delivered(
        step_id=request.stepId,
        request_hash=request.requestHash,
        result_hash=terminal.resultHash,
    )
    assert await redis.ttl(key) == pytest.approx(2 * 24 * 60 * 60, abs=1)
    assert await redis.hget(key, "terminal_payload") is None
    compacted = await journal.require(request.stepId)
    assert compacted.state == "result"
    assert compacted.terminal is None
    assert (await journal.backlog()).callback_pending == 0
    assert (await journal.backlog()).callback_rejected == 0

    await journal.accept(request, {"provider": "other"})
    assert await redis.ttl(key) == pytest.approx(2 * 24 * 60 * 60, abs=1)


@pytest.mark.asyncio
async def test_due_callback_claim_is_atomic_across_replayers() -> None:
    journal = _journal()
    request = execution_request()
    await journal.accept(request, {"provider": "fake"})
    terminal = execution_result(request)
    await journal.record_terminal(request, terminal)

    first, second = await asyncio.gather(
        journal.claim_callback(request.stepId),
        journal.claim_callback(request.stepId),
    )

    claims = [claim for claim in (first, second) if claim is not None]
    assert len(claims) == 1
    assert claims[0].result_hash == terminal.resultHash
    assert (await journal.backlog()).callback_pending == 1


@pytest.mark.asyncio
async def test_expired_callback_claim_is_recovered_after_replayer_restart() -> None:
    journal = _journal()
    request = execution_request()
    await journal.accept(request, {"provider": "fake"})
    await journal.record_terminal(request, execution_result(request))
    claimed_at = datetime(2026, 9, 1, tzinfo=UTC)

    first = await journal.claim_callback(
        request.stepId,
        now=claimed_at,
        lease=timedelta(seconds=2),
        force=True,
    )
    before_expiry = await journal.claim_due_callbacks(
        now=claimed_at + timedelta(seconds=1),
        lease=timedelta(seconds=2),
    )
    after_expiry = await journal.claim_due_callbacks(
        now=claimed_at + timedelta(seconds=3),
        lease=timedelta(seconds=2),
    )

    assert first is not None
    assert before_expiry == ()
    assert len(after_expiry) == 1
    assert after_expiry[0].claim_token != first.claim_token


@pytest.mark.asyncio
async def test_retry_reschedule_honors_due_time_without_hot_loop() -> None:
    journal = _journal()
    request = execution_request()
    await journal.accept(request, {"provider": "fake"})
    await journal.record_terminal(request, execution_result(request))
    now = datetime(2026, 9, 1, tzinfo=UTC)
    claim = await journal.claim_callback(request.stepId, now=now, force=True)
    assert claim is not None
    due_at = now + timedelta(seconds=10)

    await journal.reschedule_callback(
        claim,
        error_code="EXECUTION_CALLBACK_UNAVAILABLE",
        next_attempt_at=due_at,
    )

    assert await journal.claim_due_callbacks(now=now + timedelta(seconds=9)) == ()
    assert len(await journal.claim_due_callbacks(now=due_at)) == 1


@pytest.mark.asyncio
async def test_restore_quarantine_fails_closed_before_new_model_work() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    journal = RedisExecutionJournal(
        cast(AsyncJournalRedis, redis),
        prefix="test:quarantine",
    )
    await redis.set("test:quarantine:restore:quarantine", "snapshot-sha")

    health = await journal.health()
    with pytest.raises(ExecutionJournalError, match="RESTORE_QUARANTINED"):
        await journal.ensure_available()

    assert health.connected is True
    assert health.persistence_ok is True
    assert health.quarantined is True
    assert health.ready is False


@pytest.mark.asyncio
async def test_ordinary_redis_loss_does_not_remove_execution_journal() -> None:
    ordinary_redis = fakeredis.aioredis.FakeRedis()
    execution_redis = fakeredis.aioredis.FakeRedis()
    journal = RedisExecutionJournal(
        cast(AsyncJournalRedis, execution_redis),
        prefix="test:independent-redis",
    )
    request = execution_request()
    result = execution_result(request)
    await ordinary_redis.set("ordinary:queue:job-1", "queued")
    await journal.accept(request, result.resolvedModel.model_dump(mode="json"))
    await journal.record_terminal(request, result)

    # 模拟可重建普通 Redis 重启并丢失全部内存数据；journal 使用另一 client/server。
    await ordinary_redis.flushall()
    assert await ordinary_redis.get("ordinary:queue:job-1") is None

    persisted = await journal.require(request.stepId)
    assert persisted.terminal == result
    assert (await journal.backlog()).callback_pending == 1
