from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

import fakeredis.aioredis
import pytest
from inkforge_agents.execution.callbacks import (
    ExecutionCallbackClient,
    ExecutionCallbackError,
)
from inkforge_agents.execution.journal import AsyncJournalRedis, RedisExecutionJournal
from inkforge_agents.execution.replayer import TerminalCallbackReplayer
from inkforge_contracts.execution import (
    ExecutionCallbackReceipt,
    ExecutionStepFailure,
    ExecutionStepProgress,
    ExecutionStepResult,
)

from .support import execution_request, execution_result, rehash_request


class ScriptedCallbacks:
    def __init__(
        self,
        outcomes: list[
            Literal["accepted", "duplicate", "stale", "superseded"]
            | ExecutionCallbackError
        ],
    ) -> None:
        self._outcomes = outcomes
        self.result_hashes: list[str] = []
        self.delivered = asyncio.Event()

    async def send_progress(
        self,
        progress: ExecutionStepProgress,
    ) -> ExecutionCallbackReceipt:
        raise AssertionError(f"replayer 不得发送 progress：{progress.progressId}")

    async def send_result(
        self,
        result: ExecutionStepResult,
    ) -> ExecutionCallbackReceipt:
        self.result_hashes.append(result.resultHash)
        return self._next(result)

    async def send_failure(
        self,
        failure: ExecutionStepFailure,
    ) -> ExecutionCallbackReceipt:
        self.result_hashes.append(failure.resultHash)
        return self._next(failure)

    def _next(
        self,
        terminal: ExecutionStepResult | ExecutionStepFailure,
    ) -> ExecutionCallbackReceipt:
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, ExecutionCallbackError):
            raise outcome
        self.delivered.set()
        return ExecutionCallbackReceipt(
            protocolVersion="2.0",
            runId=terminal.runId,
            stepId=terminal.stepId,
            jobId=terminal.jobId,
            fencingToken=terminal.fencingToken,
            requestHash=terminal.requestHash,
            status=outcome,
            receivedAt=datetime.now(UTC),
        )


def _journal(prefix: str) -> RedisExecutionJournal:
    return RedisExecutionJournal(
        cast(AsyncJournalRedis, fakeredis.aioredis.FakeRedis()),
        prefix=prefix,
    )


async def _terminal(journal: RedisExecutionJournal) -> ExecutionStepResult:
    request = execution_request()
    result = execution_result(request)
    await journal.accept(request, result.resolvedModel.model_dump(mode="json"))
    await journal.record_terminal(request, result)
    return result


@pytest.mark.asyncio
async def test_core_committed_but_receipt_lost_replays_same_result_hash() -> None:
    journal = _journal("test:replayer:lost-receipt")
    result = await _terminal(journal)
    callbacks = ScriptedCallbacks(
        [
            ExecutionCallbackError(
                "EXECUTION_CALLBACK_UNAVAILABLE",
                retryable=True,
            ),
            "duplicate",
        ]
    )
    replayer = TerminalCallbackReplayer(
        journal,
        cast(ExecutionCallbackClient, callbacks),
        retry_base_seconds=0,
    )

    outcome = await replayer.deliver_immediately(result.stepId, max_attempts=2)

    assert outcome == "delivered"
    assert callbacks.result_hashes == [result.resultHash, result.resultHash]
    assert (await journal.require(result.stepId)).callback_delivery == "delivered"


@pytest.mark.asyncio
@pytest.mark.parametrize("receipt_status", ["accepted", "duplicate", "superseded"])
async def test_all_valid_terminal_receipts_end_replay(
    receipt_status: Literal["accepted", "duplicate", "superseded"],
) -> None:
    journal = _journal(f"test:replayer:{receipt_status}")
    result = await _terminal(journal)
    callbacks = ScriptedCallbacks([receipt_status])
    replayer = TerminalCallbackReplayer(
        journal,
        cast(ExecutionCallbackClient, callbacks),
    )

    outcome = await replayer.deliver_immediately(result.stepId)

    assert outcome == "delivered"
    assert (await journal.require(result.stepId)).callback_delivery == "delivered"


@pytest.mark.asyncio
async def test_stale_terminal_receipt_keeps_payload_until_new_fence_refences_it() -> None:
    journal = _journal("test:replayer:stale-refence-race")
    request = execution_request()
    result = execution_result(request)
    await journal.accept(request, result.resolvedModel.model_dump(mode="json"))
    await journal.record_terminal(request, result)
    callbacks = ScriptedCallbacks(["stale", "accepted"])
    replayer = TerminalCallbackReplayer(
        journal,
        cast(ExecutionCallbackClient, callbacks),
        retry_base_seconds=30,
    )

    first = await replayer.deliver_immediately(result.stepId)
    waiting = await journal.require(result.stepId)

    assert first == "retry"
    assert waiting.callback_delivery == "pending"
    assert waiting.terminal is not None

    newer = request.model_copy(update={"jobId": "job-2", "fencingToken": 2})
    decision = await journal.accept_with_disposition(
        newer,
        result.resolvedModel.model_dump(mode="json"),
    )
    second = await replayer.deliver_immediately(result.stepId)

    assert decision.refenced is True
    assert second == "delivered"
    delivered = await journal.require(result.stepId)
    assert delivered.callback_delivery == "delivered"
    assert delivered.terminal is None
    assert delivered.job_id == "job-2"
    assert delivered.fencing_token == 2


@pytest.mark.asyncio
async def test_new_fence_delivery_winning_old_http_stale_does_not_break_replayer() -> None:
    journal = _journal("test:replayer:refence-delivered-wins")
    request = execution_request()
    result = execution_result(request)
    resolved = result.resolvedModel.model_dump(mode="json")
    await journal.accept(request, resolved)
    await journal.record_terminal(request, result)
    newer = request.model_copy(update={"jobId": "job-2", "fencingToken": 2})

    class RefenceWinsCallbacks(ScriptedCallbacks):
        def __init__(self) -> None:
            super().__init__([])

        async def send_result(
            self,
            terminal: ExecutionStepResult,
        ) -> ExecutionCallbackReceipt:
            self.result_hashes.append(terminal.resultHash)
            await journal.accept_with_disposition(newer, resolved)
            newer_claim = await journal.claim_callback(newer.stepId, force=True)
            assert newer_claim is not None
            await journal.mark_callback_delivered(
                step_id=newer.stepId,
                request_hash=newer.requestHash,
                result_hash=terminal.resultHash,
                claim_token=newer_claim.claim_token,
            )
            return ExecutionCallbackReceipt(
                protocolVersion="2.0",
                runId=terminal.runId,
                stepId=terminal.stepId,
                jobId=terminal.jobId,
                fencingToken=terminal.fencingToken,
                requestHash=terminal.requestHash,
                status="stale",
                receivedAt=datetime.now(UTC),
            )

    callbacks = RefenceWinsCallbacks()
    replayer = TerminalCallbackReplayer(
        journal,
        cast(ExecutionCallbackClient, callbacks),
    )

    outcome = await replayer.deliver_immediately(result.stepId)

    assert outcome == "delivered"
    delivered = await journal.require(result.stepId)
    assert delivered.callback_delivery == "delivered"
    assert delivered.result_hash == result.resultHash
    assert delivered.terminal is None
    assert delivered.job_id == "job-2"
    assert delivered.fencing_token == 2


@pytest.mark.asyncio
async def test_definitive_4xx_is_isolated_as_rejected_without_hot_retry() -> None:
    journal = _journal("test:replayer:rejected")
    result = await _terminal(journal)
    callbacks = ScriptedCallbacks(
        [ExecutionCallbackError("EXECUTION_CALLBACK_REJECTED", retryable=False)]
    )
    replayer = TerminalCallbackReplayer(
        journal,
        cast(ExecutionCallbackClient, callbacks),
    )

    outcome = await replayer.deliver_immediately(result.stepId, max_attempts=5)
    backlog = await journal.backlog()

    assert outcome == "rejected"
    assert len(callbacks.result_hashes) == 1
    assert backlog.callback_pending == 0
    assert backlog.callback_rejected == 1
    assert (await journal.require(result.stepId)).callback_delivery == "rejected"


@pytest.mark.asyncio
async def test_replayer_restart_reclaims_expired_lease_without_model_execution() -> None:
    journal = _journal("test:replayer:restart")
    result = await _terminal(journal)
    crashed_claim = await journal.claim_callback(
        result.stepId,
        now=datetime.now(UTC) - timedelta(seconds=10),
        lease=timedelta(seconds=1),
        force=True,
    )
    callbacks = ScriptedCallbacks(["duplicate"])
    restarted = TerminalCallbackReplayer(
        journal,
        cast(ExecutionCallbackClient, callbacks),
        claim_lease=timedelta(seconds=1),
    )

    outcome = await restarted.deliver_immediately(result.stepId)

    assert crashed_claim is not None
    assert outcome == "delivered"
    assert callbacks.result_hashes == [result.resultHash]


@pytest.mark.asyncio
async def test_background_replayer_drains_terminal_without_admission_or_model() -> None:
    journal = _journal("test:replayer:background")
    result = await _terminal(journal)
    callbacks = ScriptedCallbacks(["accepted"])
    replayer = TerminalCallbackReplayer(
        journal,
        cast(ExecutionCallbackClient, callbacks),
        poll_interval_seconds=0.01,
    )
    task = asyncio.create_task(replayer.run())
    try:
        await asyncio.wait_for(callbacks.delivered.wait(), timeout=1)
    finally:
        replayer.request_stop()
        await asyncio.wait_for(task, timeout=1)

    assert callbacks.result_hashes == [result.resultHash]
    assert (await journal.require(result.stepId)).callback_delivery == "delivered"


@pytest.mark.asyncio
async def test_restore_quarantine_blocks_pending_http_then_replays_exactly_once() -> None:
    prefix = "test:replayer:restore-quarantine"
    redis = fakeredis.aioredis.FakeRedis()
    journal = RedisExecutionJournal(
        cast(AsyncJournalRedis, redis),
        prefix=prefix,
    )
    result = await _terminal(journal)
    callbacks = ScriptedCallbacks(["accepted"])
    replayer = TerminalCallbackReplayer(
        journal,
        cast(ExecutionCallbackClient, callbacks),
        poll_interval_seconds=0.01,
    )
    await redis.set(f"{prefix}:restore:quarantine", "restore-epoch")

    assert await replayer.deliver_immediately(result.stepId) is None
    task = asyncio.create_task(replayer.run())
    try:
        await asyncio.sleep(0.05)
        assert replayer.is_running is True
        assert task.done() is False
        assert callbacks.result_hashes == []
        pending = await journal.require(result.stepId)
        assert pending.callback_delivery == "pending"
        assert pending.terminal is not None

        await redis.delete(f"{prefix}:restore:quarantine")
        replayer.wake()
        await asyncio.wait_for(callbacks.delivered.wait(), timeout=1)
    finally:
        replayer.request_stop()
        await asyncio.wait_for(task, timeout=1)

    assert callbacks.result_hashes == [result.resultHash]
    delivered = await journal.require(result.stepId)
    assert delivered.callback_delivery == "delivered"
    assert delivered.terminal is None

    await redis.set(f"{prefix}:restore:quarantine", "restore-epoch-2")
    assert await replayer.deliver_immediately(result.stepId) is None
    assert callbacks.result_hashes == [result.resultHash]
    tombstone = await journal.require(result.stepId)
    assert tombstone.callback_delivery == "delivered"
    assert tombstone.terminal is None


@pytest.mark.asyncio
async def test_restore_marker_after_claim_returns_terminal_to_pending_without_http() -> None:
    prefix = "test:replayer:restore-after-claim"
    redis = fakeredis.aioredis.FakeRedis()
    journal = RedisExecutionJournal(
        cast(AsyncJournalRedis, redis),
        prefix=prefix,
    )
    result = await _terminal(journal)
    callbacks = ScriptedCallbacks(["accepted"])
    replayer = TerminalCallbackReplayer(
        journal,
        cast(ExecutionCallbackClient, callbacks),
    )
    claim = await journal.claim_callback(result.stepId, force=True)
    assert claim is not None
    await redis.set(f"{prefix}:restore:quarantine", "restore-epoch")

    outcome, _ = await replayer._deliver_claim(claim)  # noqa: SLF001

    assert outcome == "quarantined"
    assert callbacks.result_hashes == []
    pending = await journal.require(result.stepId)
    assert pending.callback_delivery == "pending"
    assert pending.terminal is not None
    assert (await journal.backlog()).callback_pending == 1


@pytest.mark.asyncio
async def test_slow_callback_does_not_preclaim_next_terminal_past_lease() -> None:
    prefix = "test:replayer:slow-single-claim"
    redis = fakeredis.aioredis.FakeRedis()
    journal = RedisExecutionJournal(
        cast(AsyncJournalRedis, redis),
        prefix=prefix,
    )
    first_request = execution_request()
    second_request = rehash_request(
        execution_request(job_id="job-2").model_copy(
            update={"stepId": "step-2", "idempotencyKey": "idem-2"}
        )
    )
    first = execution_result(first_request)
    second = execution_result(second_request)
    for request, result in ((first_request, first), (second_request, second)):
        await journal.accept(request, result.resolvedModel.model_dump(mode="json"))
        await journal.record_terminal(request, result)

    class SlowCallbacks(ScriptedCallbacks):
        def __init__(self) -> None:
            super().__init__(["accepted", "accepted"])
            self.first_started = asyncio.Event()
            self.release_first = asyncio.Event()
            self.second_delivered = asyncio.Event()
            self.step_ids: list[str] = []

        async def send_result(
            self,
            result: ExecutionStepResult,
        ) -> ExecutionCallbackReceipt:
            self.result_hashes.append(result.resultHash)
            self.step_ids.append(result.stepId)
            if len(self.step_ids) == 1:
                self.first_started.set()
                await self.release_first.wait()
            receipt = self._next(result)
            if len(self.step_ids) == 2:
                self.second_delivered.set()
            return receipt

    callbacks = SlowCallbacks()
    replayer = TerminalCallbackReplayer(
        journal,
        cast(ExecutionCallbackClient, callbacks),
        claim_lease=timedelta(milliseconds=10),
        poll_interval_seconds=0.01,
    )
    task = asyncio.create_task(replayer.run())
    try:
        await asyncio.wait_for(callbacks.first_started.wait(), timeout=1)
        await asyncio.sleep(0.03)

        assert len(callbacks.step_ids) == 1
        assert await redis.zcard(f"{prefix}:callbacks:leased") == 1
        assert await redis.zcard(f"{prefix}:callbacks:pending") == 1

        callbacks.release_first.set()
        await asyncio.wait_for(callbacks.second_delivered.wait(), timeout=1)
    finally:
        replayer.request_stop()
        callbacks.release_first.set()
        await asyncio.wait_for(task, timeout=1)

    assert len(callbacks.step_ids) == 2
    assert (await journal.require(first.stepId)).callback_delivery == "delivered"
    assert (await journal.require(second.stepId)).callback_delivery == "delivered"
