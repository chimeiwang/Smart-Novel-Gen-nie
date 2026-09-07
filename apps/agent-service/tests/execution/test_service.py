from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Any, Literal, cast

import fakeredis.aioredis
import pytest
from inkforge_agents.execution.callbacks import (
    ExecutionCallbackClient,
    ExecutionCallbackError,
)
from inkforge_agents.execution.executor import (
    ExecutionCapabilityError,
    ResolvedExecutionStep,
    StatelessExecutionStepExecutor,
)
from inkforge_agents.execution.journal import (
    AcceptDecision,
    AsyncJournalRedis,
    ExecutionJournalConflictError,
    ExecutionJournalError,
    JournalEntry,
    RedisExecutionJournal,
)
from inkforge_agents.execution.registry import load_execution_registry
from inkforge_agents.execution.service import (
    ExecutionAdmissionSaturatedError,
    ExecutionService,
    ExecutionServiceUnavailableError,
)
from inkforge_agents.providers.base import (
    ModelStructuredOutputRoute,
    ModelTurnRequest,
    ModelTurnResult,
)
from inkforge_agents.providers.fake import FakeModelProvider
from inkforge_contracts.execution import (
    ExecutionCallbackReceipt,
    ExecutionStepFailure,
    ExecutionStepProgress,
    ExecutionStepRequest,
    ExecutionStepResult,
    ResolvedModelRef,
    calculate_resolved_model_fingerprint,
)
from pydantic import JsonValue

from .support import (
    answer_question_request,
    execution_cancel,
    execution_request,
    execution_result,
    rehash_request,
)


class RecordingModel:
    provider_name = "fake"
    model_name = "fake"
    transport_profile = "transport.fake.v1"
    endpoint_profile = "endpoint.local-fake.v1"
    capability_version = "capability.fake.structured-output.v1"

    def __init__(
        self,
        *,
        supports_idempotency: bool = True,
        block: bool = False,
    ) -> None:
        self.supports_request_idempotency = supports_idempotency
        if not supports_idempotency:
            self.provider_name = "openai_compatible"
            self.model_name = "deepseek-v4-flash"
            self.transport_profile = "transport.deepseek-v4.v1"
            self.endpoint_profile = "endpoint.deepseek-official.v1"
            self.capability_version = "capability.deepseek-v4.chat-json.v1"
        self._block = block
        self.requests: list[ModelTurnRequest] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    def supports_structured_output(self, route: ModelStructuredOutputRoute) -> bool:
        expected = (
            "responses_json_schema_v1" if self.provider_name == "fake" else "chat_json_output_v1"
        )
        return route == expected

    async def run_execution_turn(
        self,
        request: ModelTurnRequest,
        *,
        before_provider: Callable[[], Awaitable[int]],
        lane: Literal["interactive", "creative", "batch_media"] = "interactive",
        reviewer: bool = False,
        provider_timeout_seconds: float | None = None,
    ) -> tuple[int, ModelTurnResult]:
        del lane, reviewer
        attempt = await before_provider()
        self.requests.append(request)
        self.started.set()

        async def complete() -> ModelTurnResult:
            if self._block:
                await self.release.wait()
            return await FakeModelProvider().complete_turn(request)

        if provider_timeout_seconds is None:
            return attempt, await complete()
        async with asyncio.timeout(provider_timeout_seconds):
            return attempt, await complete()


class RecordingCallbacks:
    def __init__(self, *, terminal_retryable_failures: int = 0) -> None:
        self._terminal_retryable_failures = terminal_retryable_failures
        self.progress: list[ExecutionStepProgress] = []
        self.results: list[ExecutionStepResult] = []
        self.failures: list[ExecutionStepFailure] = []
        self.terminal_attempts = 0

    async def send_progress(
        self,
        progress: ExecutionStepProgress,
    ) -> ExecutionCallbackReceipt:
        self.progress.append(progress)
        return _receipt(progress)

    async def send_result(
        self,
        result: ExecutionStepResult,
    ) -> ExecutionCallbackReceipt:
        self.terminal_attempts += 1
        if self.terminal_attempts <= self._terminal_retryable_failures:
            raise ExecutionCallbackError(
                "EXECUTION_CALLBACK_UNAVAILABLE",
                retryable=True,
            )
        self.results.append(result)
        return _receipt(result)

    async def send_failure(
        self,
        failure: ExecutionStepFailure,
    ) -> ExecutionCallbackReceipt:
        self.terminal_attempts += 1
        if self.terminal_attempts <= self._terminal_retryable_failures:
            raise ExecutionCallbackError(
                "EXECUTION_CALLBACK_UNAVAILABLE",
                retryable=True,
            )
        self.failures.append(failure)
        return _receipt(failure)


class FailingAttemptJournal(RedisExecutionJournal):
    async def begin_provider_attempt(self, request: ExecutionStepRequest) -> int:
        raise RuntimeError("模拟 provider 前 Redis AOF 写入失败")


class FailingAcceptJournal(RedisExecutionJournal):
    async def accept_with_disposition(
        self,
        request: ExecutionStepRequest,
        resolved_model: Mapping[str, JsonValue],
        *,
        now: datetime | None = None,
    ) -> AcceptDecision:
        del request, resolved_model, now
        raise ExecutionJournalError("模拟首次 journal 持久化失败")


class FailingTerminalJournal(RedisExecutionJournal):
    async def record_terminal(
        self,
        request: ExecutionStepRequest,
        terminal: ExecutionStepResult | ExecutionStepFailure,
    ) -> JournalEntry:
        del request, terminal
        raise ExecutionJournalError("模拟终态 journal 持久化失败")


class MissingProviderKeyJournal(RedisExecutionJournal):
    async def begin_provider_attempt(self, request: ExecutionStepRequest) -> int:
        attempt = await super().begin_provider_attempt(request)
        redis = cast(Any, self._redis)
        await redis.hdel(self._key(request.stepId), "provider_idempotency_key")
        return attempt


class OrderedJournal(RedisExecutionJournal):
    def __init__(
        self,
        redis: AsyncJournalRedis,
        *,
        prefix: str,
        events: list[str],
    ) -> None:
        super().__init__(redis, prefix=prefix)
        self._events = events

    async def accept_with_disposition(
        self,
        request: ExecutionStepRequest,
        resolved_model: Mapping[str, JsonValue],
        *,
        now: datetime | None = None,
    ) -> AcceptDecision:
        decision = await super().accept_with_disposition(
            request,
            resolved_model,
            now=now,
        )
        self._events.append("journal:accepted")
        return decision

    async def mark_started(
        self,
        request: ExecutionStepRequest,
        *,
        now: datetime | None = None,
    ) -> JournalEntry:
        entry = await super().mark_started(request, now=now)
        self._events.append("journal:started")
        return entry

    async def begin_provider_attempt(self, request: ExecutionStepRequest) -> int:
        attempt = await super().begin_provider_attempt(request)
        self._events.append("journal:provider_attempt")
        return attempt


class OrderedCallbacks(RecordingCallbacks):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self._events = events

    async def send_progress(
        self,
        progress: ExecutionStepProgress,
    ) -> ExecutionCallbackReceipt:
        receipt = await super().send_progress(progress)
        self._events.append(f"core:{progress.phase}")
        return receipt


class RejectedPreparingCallbacks(RecordingCallbacks):
    async def send_progress(
        self,
        progress: ExecutionStepProgress,
    ) -> ExecutionCallbackReceipt:
        self.progress.append(progress)
        raise ExecutionCallbackError("EXECUTION_CALLBACK_REJECTED", retryable=False)


class CancelledPreparingCallbacks(RecordingCallbacks):
    def __init__(self, *, phase: str = "preparing", outcome: str = "stale") -> None:
        super().__init__()
        self.phase = phase
        self.outcome = outcome
        self.preparing_entered = asyncio.Event()
        self.release_preparing = asyncio.Event()

    async def send_progress(
        self,
        progress: ExecutionStepProgress,
    ) -> ExecutionCallbackReceipt:
        self.progress.append(progress)
        if progress.phase == self.phase:
            self.preparing_entered.set()
            await self.release_preparing.wait()
            if self.outcome != "stale":
                raise ExecutionCallbackError(
                    "EXECUTION_CALLBACK_UNAVAILABLE",
                    retryable=self.outcome == "retry_exhausted",
                )
            return _receipt(progress, status="stale")
        return _receipt(progress)


class RetryableProgressCallbacks(RecordingCallbacks):
    def __init__(self, *, phase: str, accept_first: int = 0) -> None:
        super().__init__()
        self._phase = phase
        self._accept_first = accept_first
        self._matching_calls = 0
        self.exhausted = asyncio.Event()

    async def send_progress(
        self,
        progress: ExecutionStepProgress,
    ) -> ExecutionCallbackReceipt:
        self.progress.append(progress)
        if progress.phase != self._phase:
            return _receipt(progress)
        self._matching_calls += 1
        if self._matching_calls <= self._accept_first:
            return _receipt(progress)
        if self._matching_calls >= self._accept_first + 2:
            self.exhausted.set()
        raise ExecutionCallbackError("EXECUTION_CALLBACK_UNAVAILABLE", retryable=True)


class StaleHeartbeatCallbacks(RecordingCallbacks):
    def __init__(self) -> None:
        super().__init__()
        self._waiting_calls = 0
        self.stale_seen = asyncio.Event()

    async def send_progress(
        self,
        progress: ExecutionStepProgress,
    ) -> ExecutionCallbackReceipt:
        self.progress.append(progress)
        if progress.phase == "waiting_provider":
            self._waiting_calls += 1
            if self._waiting_calls > 1:
                self.stale_seen.set()
                return _receipt(progress, status="stale")
        return _receipt(progress)


class RejectedHeartbeatCallbacks(RecordingCallbacks):
    def __init__(self) -> None:
        super().__init__()
        self._waiting_calls = 0
        self.rejected_seen = asyncio.Event()

    async def send_progress(
        self,
        progress: ExecutionStepProgress,
    ) -> ExecutionCallbackReceipt:
        self.progress.append(progress)
        if progress.phase == "waiting_provider":
            self._waiting_calls += 1
            if self._waiting_calls > 1:
                self.rejected_seen.set()
                raise ExecutionCallbackError(
                    "EXECUTION_CALLBACK_REJECTED",
                    retryable=False,
                )
        return _receipt(progress)


class FailingBuildExecutor(StatelessExecutionStepExecutor):
    def build_model_request(
        self,
        request: ExecutionStepRequest,
        resolved: ResolvedExecutionStep,
    ) -> ModelTurnRequest:
        del request, resolved
        raise ExecutionCapabilityError("模拟本地输入预算失败")


def _journal(
    *,
    journal_type: type[RedisExecutionJournal] = RedisExecutionJournal,
    prefix: str = "test:service",
) -> RedisExecutionJournal:
    return journal_type(
        cast(AsyncJournalRedis, fakeredis.aioredis.FakeRedis()),
        prefix=prefix,
    )


def _service(
    *,
    journal: RedisExecutionJournal,
    model: RecordingModel,
    callbacks: RecordingCallbacks,
    pending_backlog_limit: int = 100,
    max_active_executions: int = 3,
    progress_interval_seconds: float = 60,
    executor: StatelessExecutionStepExecutor | None = None,
) -> ExecutionService:
    return ExecutionService(
        journal=journal,
        registry=load_execution_registry(environment="test"),
        executor=executor
        or StatelessExecutionStepExecutor(model, max_output_tokens=10_000, retry_base_seconds=0),
        callbacks=cast(ExecutionCallbackClient, callbacks),
        progress_interval_seconds=progress_interval_seconds,
        callback_retry_base_seconds=0,
        progress_attempts=2,
        terminal_callback_attempts=3,
        pending_backlog_limit=pending_backlog_limit,
        max_active_executions=max_active_executions,
    )


@pytest.mark.asyncio
async def test_duplicate_submit_does_not_repeat_model_call() -> None:
    journal = _journal(prefix="test:service:duplicate")
    model = RecordingModel()
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request()

    first, duplicate = await asyncio.gather(
        service.submit(request),
        service.submit(request),
    )
    await service.wait_idle()

    assert first.requestHash == duplicate.requestHash == request.requestHash
    assert len(model.requests) == 1
    assert len(callbacks.results) == 1
    assert (await journal.require(request.stepId)).callback_delivery == "delivered"


@pytest.mark.asyncio
async def test_answer_question_runs_through_journal_progress_and_terminal_callback() -> None:
    journal = _journal(prefix="test:service:answer")
    model = RecordingModel()
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    registry = load_execution_registry(environment="test")
    request = answer_question_request(registry)

    accepted = await service.submit(request)
    await service.wait_idle()

    assert accepted.resolvedModel.reasoningMode == "disabled"
    assert [item.phase for item in callbacks.progress] == [
        "preparing",
        "waiting_provider",
        "validating",
        "reporting",
    ]
    assert len(callbacks.results) == 1
    result = callbacks.results[0]
    assert result.output == {"answer": "模拟模型已依据冻结章节证据回答问题。"}
    assert result.usage.providerAttempts == 1
    assert result.usage.reasoningTokens == 0
    assert len(model.requests) == 1
    assert model.requests[0].tools == []
    entry = await journal.require(request.stepId)
    assert entry.callback_delivery == "delivered"
    assert entry.terminal is None


@pytest.mark.asyncio
async def test_saturation_rejects_only_new_work_without_journal_but_allows_replay_and_cancel() -> (
    None
):
    journal = _journal(prefix="test:service:admission")
    model = RecordingModel(block=True)
    callbacks = RecordingCallbacks()
    service = _service(
        journal=journal,
        model=model,
        callbacks=callbacks,
        max_active_executions=1,
    )
    active = execution_request()
    replay = rehash_request(
        execution_request(job_id="job-replay").model_copy(
            update={"stepId": "step-replay", "idempotencyKey": "idem-replay"}
        )
    )
    replay_terminal = execution_result(replay)
    await journal.accept(
        replay,
        replay_terminal.resolvedModel.model_dump(mode="json"),
    )
    await journal.mark_started(replay)
    await journal.begin_provider_attempt(replay)
    await journal.record_terminal(replay, replay_terminal)

    await service.submit(active)
    await asyncio.wait_for(model.started.wait(), timeout=1)

    duplicate = await service.submit(active)
    replayed = await service.submit(replay)
    fresh = rehash_request(
        execution_request(job_id="job-fresh").model_copy(
            update={"stepId": "step-fresh", "idempotencyKey": "idem-fresh"}
        )
    )
    with pytest.raises(ExecutionAdmissionSaturatedError):
        await service.submit(fresh)

    assert duplicate.stepId == active.stepId
    assert replayed.stepId == replay.stepId
    assert await journal.get(fresh.stepId) is None
    health = await service.health()
    assert health.ready is True
    assert health.admission_active == 1
    assert health.admission_capacity == 1
    assert health.admission_saturated is True

    cancelled = await service.cancel(execution_cancel(active))
    assert cancelled.status == "accepted"
    await service.wait_idle()
    assert (await service.health()).admission_active == 0


@pytest.mark.asyncio
async def test_provider_starts_only_after_preparing_receipt_and_started_journal() -> None:
    events: list[str] = []
    journal = OrderedJournal(
        cast(AsyncJournalRedis, fakeredis.aioredis.FakeRedis()),
        prefix="test:service:ordered",
        events=events,
    )

    class OrderedModel(RecordingModel):
        async def run_execution_turn(
            self,
            request: ModelTurnRequest,
            *,
            before_provider: Callable[[], Awaitable[int]],
            **_: object,
        ) -> tuple[int, ModelTurnResult]:
            attempt = await before_provider()
            events.append("provider:called")
            self.requests.append(request)
            return attempt, await FakeModelProvider().complete_turn(request)

    model = OrderedModel()
    service = _service(
        journal=journal,
        model=model,
        callbacks=OrderedCallbacks(events),
    )

    await service.submit(execution_request())
    await service.wait_idle()

    assert events[:6] == [
        "journal:accepted",
        "core:preparing",
        "journal:started",
        "core:waiting_provider",
        "journal:provider_attempt",
        "provider:called",
    ]


@pytest.mark.asyncio
async def test_local_model_request_validation_fails_before_preparing_and_quota() -> None:
    journal = _journal(prefix="test:service:local-validation")
    model = RecordingModel()
    callbacks = RecordingCallbacks()
    executor = FailingBuildExecutor(model, max_output_tokens=10_000)
    service = _service(
        journal=journal,
        model=model,
        callbacks=callbacks,
        executor=executor,
    )
    request = execution_request()

    await service.submit(request)
    await service.wait_idle()

    entry = await journal.require(request.stepId)
    assert callbacks.progress == []
    assert model.requests == []
    assert entry.state == "failure"
    assert entry.provider_attempts == 0
    assert callbacks.failures[0].errorCode == "STEP_INPUT_BUDGET_EXCEEDED"


@pytest.mark.asyncio
async def test_preparing_callback_rejection_prevents_paid_model_call() -> None:
    journal = _journal(prefix="test:service:preparing-rejected")
    model = RecordingModel()
    callbacks = RejectedPreparingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request()

    await service.submit(request)
    await service.wait_idle()

    assert model.requests == []
    assert len(callbacks.failures) == 1
    assert callbacks.failures[0].errorCode == "EXECUTION_PROGRESS_REJECTED"
    entry = await journal.require(request.stepId)
    assert entry.state == "failure"
    assert entry.provider_attempts == 0


@pytest.mark.asyncio
async def test_preparing_retry_exhaustion_keeps_accepted_journal_for_lease_recovery() -> None:
    journal = _journal(prefix="test:service:preparing-retry")
    model = RecordingModel()
    callbacks = RetryableProgressCallbacks(phase="preparing")
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request()

    await service.submit(request)
    await service.wait_idle()

    entry = await journal.require(request.stepId)
    assert entry.state == "accepted"
    assert entry.provider_attempts == 0
    assert entry.terminal is None
    assert model.requests == []
    assert callbacks.failures == []


@pytest.mark.asyncio
async def test_waiting_provider_retry_exhaustion_keeps_started_zero_attempt_recoverable() -> None:
    journal = _journal(prefix="test:service:waiting-retry")
    model = RecordingModel()
    callbacks = RetryableProgressCallbacks(phase="waiting_provider")
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request()

    await service.submit(request)
    await service.wait_idle()

    entry = await journal.require(request.stepId)
    assert entry.state == "started"
    assert entry.provider_attempts == 0
    assert entry.provider_idempotency_key is None
    assert entry.terminal is None
    assert model.requests == []
    assert callbacks.failures == []


@pytest.mark.asyncio
async def test_heartbeat_retry_exhaustion_does_not_abort_inflight_provider() -> None:
    journal = _journal(prefix="test:service:heartbeat-retry")
    model = RecordingModel(block=True)
    callbacks = RetryableProgressCallbacks(
        phase="waiting_provider",
        accept_first=1,
    )
    service = _service(
        journal=journal,
        model=model,
        callbacks=callbacks,
        progress_interval_seconds=0.01,
    )

    await service.submit(execution_request())
    await asyncio.wait_for(model.started.wait(), timeout=1)
    await asyncio.wait_for(callbacks.exhausted.wait(), timeout=1)
    model.release.set()
    await service.wait_idle()

    assert len(model.requests) == 1
    assert len(callbacks.results) == 1
    assert callbacks.failures == []


@pytest.mark.asyncio
async def test_stale_heartbeat_stops_old_fence_provider_and_persists_stale_terminal() -> None:
    journal = _journal(prefix="test:service:heartbeat-stale")
    model = RecordingModel(block=True)
    callbacks = StaleHeartbeatCallbacks()
    service = _service(
        journal=journal,
        model=model,
        callbacks=callbacks,
        progress_interval_seconds=0.01,
    )
    request = execution_request()

    await service.submit(request)
    await asyncio.wait_for(model.started.wait(), timeout=1)
    await asyncio.wait_for(callbacks.stale_seen.wait(), timeout=1)
    await asyncio.wait_for(service.wait_idle(), timeout=1)

    entry = await journal.require(request.stepId)
    assert callbacks.results == []
    assert callbacks.failures[0].errorCode == "STALE_EXECUTION_FENCE"
    assert entry.state == "failure"
    assert entry.provider_attempts == 1


@pytest.mark.asyncio
async def test_rejected_heartbeat_after_provider_attempt_converges_outcome_unknown() -> None:
    journal = _journal(prefix="test:service:heartbeat-rejected")
    model = RecordingModel(block=True)
    callbacks = RejectedHeartbeatCallbacks()
    service = _service(
        journal=journal,
        model=model,
        callbacks=callbacks,
        progress_interval_seconds=0.01,
    )
    request = execution_request()

    await service.submit(request)
    await asyncio.wait_for(model.started.wait(), timeout=1)
    await asyncio.wait_for(callbacks.rejected_seen.wait(), timeout=1)
    await asyncio.wait_for(service.wait_idle(), timeout=1)

    entry = await journal.require(request.stepId)
    assert callbacks.results == []
    assert callbacks.failures[0].errorCode == "MODEL_OUTCOME_UNKNOWN"
    assert callbacks.failures[0].outcomeUnknown is True
    assert entry.provider_attempts == 1


@pytest.mark.asyncio
async def test_terminal_callback_5xx_retries_without_remodelling() -> None:
    journal = _journal(prefix="test:service:callback-retry")
    model = RecordingModel()
    callbacks = RecordingCallbacks(terminal_retryable_failures=2)
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request()

    await service.submit(request)
    await service.wait_idle()

    assert len(model.requests) == 1
    assert callbacks.terminal_attempts == 3
    assert len(callbacks.results) == 1
    entry = await journal.require(request.stepId)
    assert entry.state == "result"
    assert entry.callback_delivery == "delivered"


@pytest.mark.asyncio
async def test_running_recovery_without_journal_freezes_unknown_without_model() -> None:
    journal = _journal(prefix="test:service:missing-recovery")
    model = RecordingModel()
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request(dispatch_mode="running_recovery")

    await service.submit(request)
    await service.wait_idle()

    assert model.requests == []
    assert len(callbacks.failures) == 1
    failure = callbacks.failures[0]
    assert failure.errorCategory == "model_outcome_unknown"
    assert failure.errorCode == "MODEL_OUTCOME_UNKNOWN"
    assert failure.outcomeUnknown is True
    assert (await journal.require(request.stepId)).state == "failure"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("supports_idempotency", "drop_provider_key"),
    [(False, False), (True, True)],
    ids=["provider不保证幂等", "journal未落供应商幂等键"],
)
async def test_unsafe_started_recovery_never_repeats_model(
    supports_idempotency: bool,
    drop_provider_key: bool,
) -> None:
    journal = _journal(
        journal_type=(MissingProviderKeyJournal if drop_provider_key else RedisExecutionJournal),
        prefix=f"test:service:unsafe:{supports_idempotency}",
    )
    model = RecordingModel(supports_idempotency=supports_idempotency)
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request(dispatch_mode="running_recovery")
    registry = load_execution_registry(environment="test")
    executor = StatelessExecutionStepExecutor(model, max_output_tokens=10_000)
    resolved = executor.resolve(request, registry)
    await journal.accept(
        request,
        resolved.resolved_model.model_dump(mode="json"),
    )
    await journal.mark_started(request)
    await journal.begin_provider_attempt(request)

    await service.submit(request)
    await service.wait_idle()

    assert model.requests == []
    assert len(callbacks.failures) == 1
    assert callbacks.failures[0].errorCode == "MODEL_OUTCOME_UNKNOWN"


@pytest.mark.asyncio
async def test_started_zero_attempt_recovery_is_safe_for_non_idempotent_provider() -> None:
    journal = _journal(prefix="test:service:started-zero-attempt")
    model = RecordingModel(supports_idempotency=False)
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request(dispatch_mode="running_recovery")
    registry = load_execution_registry(environment="test")
    executor = StatelessExecutionStepExecutor(model, max_output_tokens=10_000)
    resolved = executor.resolve(request, registry)
    await journal.accept(
        request,
        resolved.resolved_model.model_dump(mode="json"),
    )
    await journal.mark_started(request)

    await service.submit(request)
    await service.wait_idle()

    entry = await journal.require(request.stepId)
    assert len(model.requests) == 1
    assert len(callbacks.results) == 1
    assert entry.provider_attempts == 1
    assert entry.state == "result"


@pytest.mark.asyncio
async def test_started_recovery_uses_journal_frozen_structured_output_route() -> None:
    class DualRouteRecordingModel(RecordingModel):
        def supports_structured_output(
            self,
            route: ModelStructuredOutputRoute,
        ) -> bool:
            return route in {
                "responses_json_schema_v1",
                "chat_json_output_v1",
            }

    journal = _journal(prefix="test:service:frozen-route")
    model = DualRouteRecordingModel()
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request(dispatch_mode="running_recovery")
    registry = load_execution_registry(environment="test")
    executor = StatelessExecutionStepExecutor(model, max_output_tokens=10_000)
    current = executor.resolve(request, registry).resolved_model
    frozen_route: ModelStructuredOutputRoute = "chat_json_output_v1"
    frozen = ResolvedModelRef(
        deploymentProfileKey=current.deploymentProfileKey,
        deploymentFingerprint=calculate_resolved_model_fingerprint(
            deployment_profile_key=current.deploymentProfileKey,
            provider=current.provider,
            model=current.model,
            transport_profile=current.transportProfile,
            endpoint_profile=current.endpointProfile,
            structured_output_route=frozen_route,
            capability_version=current.capabilityVersion,
            reasoning_mode=current.reasoningMode,
            supports_request_idempotency=current.supportsRequestIdempotency,
        ),
        provider=current.provider,
        model=current.model,
        transportProfile=current.transportProfile,
        endpointProfile=current.endpointProfile,
        structuredOutputRoute=frozen_route,
        capabilityVersion=current.capabilityVersion,
        reasoningMode=current.reasoningMode,
        supportsRequestIdempotency=current.supportsRequestIdempotency,
    )
    await journal.accept(request, frozen.model_dump(mode="json"))
    await journal.mark_started(request)

    await service.submit(request)
    await service.wait_idle()

    assert len(model.requests) == 1
    assert model.requests[0].structuredOutput is not None
    assert model.requests[0].structuredOutput.route == frozen_route
    assert callbacks.failures == []
    assert callbacks.results[0].resolvedModel == frozen


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_attempts", "expected_code", "outcome_unknown"),
    [
        (0, "MODEL_PROFILE_UNAVAILABLE", False),
        (1, "MODEL_OUTCOME_UNKNOWN", True),
    ],
)
async def test_started_recovery_with_unavailable_frozen_deployment_converges_by_attempt(
    provider_attempts: int,
    expected_code: str,
    outcome_unknown: bool,
) -> None:
    journal = _journal(prefix=f"test:service:deployment-missing:{provider_attempts}")
    original_model = RecordingModel()
    request = execution_request(dispatch_mode="running_recovery")
    original_executor = StatelessExecutionStepExecutor(
        original_model,
        max_output_tokens=10_000,
    )
    resolved = original_executor.resolve(
        request,
        load_execution_registry(environment="test"),
    )
    await journal.accept(request, resolved.resolved_model.model_dump(mode="json"))
    await journal.mark_started(request)
    if provider_attempts:
        await journal.begin_provider_attempt(request)

    unavailable_model = RecordingModel()
    unavailable_model.model_name = "removed-deployment-model"
    callbacks = RecordingCallbacks()
    service = _service(
        journal=journal,
        model=unavailable_model,
        callbacks=callbacks,
    )

    await service.submit(request)
    await service.wait_idle()

    assert unavailable_model.requests == []
    assert callbacks.failures[0].errorCode == expected_code
    assert callbacks.failures[0].outcomeUnknown is outcome_unknown
    assert callbacks.failures[0].usage.providerAttempts == provider_attempts


@pytest.mark.asyncio
async def test_idempotent_started_recovery_reuses_persisted_provider_key() -> None:
    journal = _journal(prefix="test:service:safe-recovery")
    model = RecordingModel(supports_idempotency=True)
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request(dispatch_mode="running_recovery")
    registry = load_execution_registry(environment="test")
    executor = StatelessExecutionStepExecutor(model, max_output_tokens=10_000)
    resolved = executor.resolve(request, registry)
    await journal.accept(
        request,
        resolved.resolved_model.model_dump(mode="json"),
    )
    await journal.mark_started(request)
    assert await journal.begin_provider_attempt(request) == 1

    await service.submit(request)
    await service.wait_idle()

    assert len(model.requests) == 1
    assert model.requests[0].requestIdempotencyKey == request.idempotencyKey
    assert len(callbacks.results) == 1
    entry = await journal.require(request.stepId)
    assert entry.state == "result"
    assert entry.provider_attempts == 2
    assert entry.provider_idempotency_key == request.idempotencyKey


@pytest.mark.asyncio
async def test_new_fence_retags_and_replays_terminal_without_model() -> None:
    journal = _journal(prefix="test:service:refence")
    model = RecordingModel()
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    original = execution_request()
    await journal.accept(
        original,
        execution_result(original).resolvedModel.model_dump(mode="json"),
    )
    await journal.mark_started(original)
    await journal.begin_provider_attempt(original)
    await journal.record_terminal(original, execution_result(original))
    refenced = original.model_copy(update={"jobId": "job-2", "fencingToken": 2})

    await service.submit(refenced)
    await service.wait_idle()

    assert model.requests == []
    assert len(callbacks.results) == 1
    replayed = callbacks.results[0]
    assert replayed.jobId == "job-2"
    assert replayed.fencingToken == 2
    entry = await journal.require(original.stepId)
    assert entry.callback_delivery == "delivered"
    assert entry.terminal is None
    assert entry.job_id == "job-2"
    assert entry.fencing_token == 2


@pytest.mark.asyncio
async def test_delivered_terminal_refence_uses_compact_tombstone_without_replay() -> None:
    journal = _journal(prefix="test:service:delivered-refence")
    model = RecordingModel()
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    original = execution_request()

    await service.submit(original)
    await service.wait_idle()
    assert len(callbacks.results) == 1
    assert (await journal.require(original.stepId)).terminal is None

    refenced = original.model_copy(update={"jobId": "job-2", "fencingToken": 2})
    await service.submit(refenced)
    await service.wait_idle()

    assert len(model.requests) == 1
    assert len(callbacks.results) == 1
    compact = await journal.require(original.stepId)
    assert compact.callback_delivery == "delivered"
    assert compact.terminal is None
    assert compact.job_id == "job-2"


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["preparing", "waiting_provider"])
@pytest.mark.parametrize("outcome", ["stale", "rejected", "retry_exhausted"])
async def test_cancel_during_preparing_stale_receipt_persists_zero_attempt_terminal(
    phase: str,
    outcome: str,
) -> None:
    journal = _journal(prefix="test:service:cancel-preparing-stale")
    model = RecordingModel()
    callbacks = CancelledPreparingCallbacks(phase=phase, outcome=outcome)
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request()

    await service.submit(request)
    await asyncio.wait_for(callbacks.preparing_entered.wait(), timeout=1)
    before_cancel = await journal.require(request.stepId)
    assert before_cancel.state == ("accepted" if phase == "preparing" else "started")
    assert before_cancel.cancel_request_id is None
    accepted = await service.cancel(execution_cancel(request))
    assert accepted.status == "accepted"
    assert (await journal.require(request.stepId)).cancel_request_id == "cancel-1"
    callbacks.release_preparing.set()
    await service.wait_idle()

    entry = await journal.require(request.stepId)
    health = await service.health()
    redis = cast(Any, journal._redis)
    assert model.requests == []
    assert entry.provider_attempts == 0
    assert entry.provider_started_at is None
    assert {
        "state": entry.state,
        "callback_delivery": entry.callback_delivery,
        "active": await redis.zcard(journal._drain_active),
        "background_error": health.error_code,
    } == {
        "state": "failure",
        "callback_delivery": "delivered",
        "active": 0,
        "background_error": None,
    }
    assert len(callbacks.failures) == 1
    assert callbacks.failures[0].errorCode == "RUN_CANCELLED"
    assert callbacks.failures[0].cancelRequestId == "cancel-1"
    assert callbacks.failures[0].outcomeUnknown is False
    assert callbacks.failures[0].usage.providerAttempts == 0


@pytest.mark.asyncio
async def test_duplicate_cancel_recovers_accepted_cancel_without_active_task() -> None:
    journal = _journal(prefix="test:service:cancel-orphan-accepted")
    request = execution_request()
    resolved = execution_result(request).resolvedModel
    await journal.accept(request, resolved.model_dump(mode="json"))
    original = await journal.request_cancel(execution_cancel(request))
    assert original.status == "accepted"
    model = RecordingModel()
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)

    replayed = await service.cancel(execution_cancel(request))
    assert replayed.status == "already_cancelled"
    await service.wait_idle()

    entry = await journal.require(request.stepId)
    assert model.requests == []
    assert entry.provider_attempts == 0
    assert entry.provider_started_at is None
    assert entry.state == "failure"
    assert entry.callback_delivery == "delivered"
    assert await cast(Any, journal._redis).zcard(journal._drain_active) == 0
    assert len(callbacks.failures) == 1
    assert callbacks.failures[0].errorCode == "RUN_CANCELLED"
    assert callbacks.failures[0].cancelRequestId == "cancel-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize("novel_id", ["novel-1", None])
async def test_replayer_recovers_cancelled_zero_attempt_after_service_restart(
    started: bool,
    novel_id: str | None,
) -> None:
    journal = _journal(prefix=f"test:service:cancel-restart:{started}")
    request = rehash_request(execution_request().model_copy(update={"novelId": novel_id}))
    await journal.accept(request, execution_result(request).resolvedModel.model_dump(mode="json"))
    if started:
        await journal.mark_started(request)
    await journal.request_cancel(execution_cancel(request))

    class NotifyingCallbacks(RecordingCallbacks):
        delivered = asyncio.Event()

        async def send_failure(self, failure: ExecutionStepFailure) -> ExecutionCallbackReceipt:
            receipt = await super().send_failure(failure)
            self.delivered.set()
            return receipt

    model = RecordingModel()
    callbacks = NotifyingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    replay_task = asyncio.create_task(service.callback_replayer.run())
    try:
        await asyncio.wait_for(callbacks.delivered.wait(), timeout=1)
        await asyncio.wait_for(service.wait_idle(), timeout=1)
    finally:
        service.callback_replayer.request_stop()
        await asyncio.wait_for(replay_task, timeout=1)
        await service.close()
    entry = await journal.require(request.stepId)
    assert entry.state == "failure"
    assert entry.callback_delivery == "delivered"
    assert await cast(Any, journal._redis).zcard(journal._drain_active) == 0
    assert model.requests == []
    assert len(callbacks.failures) == 1
    assert callbacks.failures[0].usage.providerAttempts == 0
    assert callbacks.failures[0].novelId == novel_id


@pytest.mark.asyncio
async def test_cancel_recovery_skips_active_task_quarantine_and_nonzero_attempts() -> None:
    prefix = "test:service:cancel-recovery-exclusions"
    journal = _journal(prefix=prefix)
    request = execution_request()
    model = RecordingModel()
    callbacks = CancelledPreparingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    await service.submit(request)
    await callbacks.preparing_entered.wait()
    await service.cancel(execution_cancel(request))
    await service._recover_pending_cancellations()
    assert (await journal.require(request.stepId)).state == "accepted"
    assert callbacks.failures == []
    # 模拟旧进程在已收到取消后停止；新实例不能穿过 restore quarantine。
    await service.close()
    redis = cast(Any, journal._redis)
    await redis.set(f"{prefix}:restore:quarantine", "test-restore")
    recovered = _service(journal=journal, model=model, callbacks=RecordingCallbacks())
    await recovered._recover_pending_cancellations()
    await recovered.wait_idle()
    assert (await journal.require(request.stepId)).state == "accepted"
    await redis.delete(f"{prefix}:restore:quarantine")
    await recovered._recover_pending_cancellations()
    await recovered.wait_idle()
    assert (await journal.require(request.stepId)).callback_delivery == "delivered"

    called = rehash_request(
        request.model_copy(
            update={
                "stepId": "step-called",
                "jobId": "job-called",
                "idempotencyKey": "idem-called",
            }
        )
    )
    await journal.accept(called, execution_result(called).resolvedModel.model_dump(mode="json"))
    await journal.mark_started(called)
    await journal.begin_provider_attempt(called)
    await journal.request_cancel(execution_cancel(called))
    before = await journal.require(called.stepId)
    await recovered._recover_pending_cancellations()
    await recovered.wait_idle()
    assert await journal.require(called.stepId) == before
    assert model.requests == []


@pytest.mark.asyncio
async def test_concurrent_cancel_recovery_delivers_one_terminal_and_preserves_existing_result() -> (
    None
):
    journal = _journal(prefix="test:service:cancel-recovery-concurrent")
    request = execution_request()
    await journal.accept(request, execution_result(request).resolvedModel.model_dump(mode="json"))
    await journal.request_cancel(execution_cancel(request))
    model = RecordingModel()
    callbacks = RecordingCallbacks()
    first = _service(journal=journal, model=model, callbacks=callbacks)
    second = _service(journal=journal, model=model, callbacks=callbacks)
    await asyncio.gather(
        first._recover_pending_cancellations(), second._recover_pending_cancellations()
    )
    await asyncio.gather(first.wait_idle(), second.wait_idle())
    assert len(callbacks.failures) == 1
    assert (await journal.require(request.stepId)).callback_delivery == "delivered"
    assert (await first.health()).error_code is None
    assert (await second.health()).error_code is None
    assert model.requests == []

    complete = rehash_request(
        request.model_copy(
            update={
                "stepId": "step-complete",
                "jobId": "job-complete",
                "idempotencyKey": "idem-complete",
            }
        )
    )
    result = execution_result(complete)
    await journal.accept(complete, result.resolvedModel.model_dump(mode="json"))
    await journal.record_terminal(complete, result)
    before = await journal.require(complete.stepId)
    cancellation = await first.cancel(execution_cancel(complete))
    assert cancellation.status == "already_terminal"
    await first._recover_pending_cancellations()
    await first.wait_idle()
    assert await journal.require(complete.stepId) == before
    assert len(callbacks.failures) == 1


@pytest.mark.asyncio
async def test_cancel_recovery_rechecks_fence_after_reading_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = _journal(prefix="test:service:cancel-recovery-fence")
    request = execution_request()
    resolved = execution_result(request).resolvedModel.model_dump(mode="json")
    await journal.accept(request, resolved)
    await journal.request_cancel(execution_cancel(request))
    candidate = await journal.require(request.stepId)
    new_request = request.model_copy(update={"jobId": "job-new", "fencingToken": 2})

    async def stale_candidates() -> tuple[JournalEntry, ...]:
        await journal.accept(new_request, resolved)
        return (candidate,)

    monkeypatch.setattr(journal, "cancelled_before_provider", stale_candidates)
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=RecordingModel(), callbacks=callbacks)
    await service._recover_pending_cancellations()
    await service.wait_idle()
    latest = await journal.require(request.stepId)
    assert latest.fencing_token == 2
    assert latest.job_id == "job-new"
    assert latest.state == "accepted"
    assert callbacks.failures == []
    assert (await service.health()).error_code is None


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["request_hash", "input_hash", "run_id", "novel_id", "job_id"])
async def test_cancel_recovery_rejects_logical_identity_corruption(
    field: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = _journal(prefix="test:service:cancel-corrupt-identity")
    request = execution_request()
    await journal.accept(request, execution_result(request).resolvedModel.model_dump(mode="json"))
    await journal.request_cancel(execution_cancel(request))
    candidate = await journal.require(request.stepId)

    async def stale_candidates() -> tuple[JournalEntry, ...]:
        await cast(Any, journal._redis).hset(
            journal._key(request.stepId),
            field,
            "b" * 64 if field.endswith("hash") else "changed",
        )
        return (candidate,)

    monkeypatch.setattr(journal, "cancelled_before_provider", stale_candidates)
    callbacks = RecordingCallbacks()
    model = RecordingModel()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    with pytest.raises(ExecutionJournalConflictError):
        await service._recover_pending_cancellations()
    assert callbacks.failures == []
    assert model.requests == []


@pytest.mark.asyncio
async def test_old_cancel_never_interrupts_newer_fence_active_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = _journal(prefix="test:service:cancel-new-owner")
    cancel_entered = asyncio.Event()
    release_cancel = asyncio.Event()
    newer_terminal_entered = asyncio.Event()
    release_newer_terminal = asyncio.Event()
    original_cancel = journal.request_cancel

    async def delayed_cancel(request: Any) -> Any:
        decision = await original_cancel(request)
        cancel_entered.set()
        await release_cancel.wait()
        return decision

    class BlockedNewerCallbacks(CancelledPreparingCallbacks):
        async def send_failure(self, failure: ExecutionStepFailure) -> ExecutionCallbackReceipt:
            if failure.fencingToken == 2:
                newer_terminal_entered.set()
                await release_newer_terminal.wait()
            return await super().send_failure(failure)

    callbacks = BlockedNewerCallbacks()
    model = RecordingModel()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request()
    await service.submit(request)
    await asyncio.wait_for(callbacks.preparing_entered.wait(), timeout=1)
    monkeypatch.setattr(journal, "request_cancel", delayed_cancel)
    old_cancel = asyncio.create_task(service.cancel(execution_cancel(request)))
    try:
        await asyncio.wait_for(cancel_entered.wait(), timeout=1)
        newer = request.model_copy(update={"jobId": "job-newer", "fencingToken": 2})
        await service.submit(newer)
        await asyncio.wait_for(newer_terminal_entered.wait(), timeout=1)
        newer_task = service._active[request.stepId].task
        release_cancel.set()
        assert (await asyncio.wait_for(old_cancel, timeout=1)).status == "accepted"
        assert service._active[request.stepId].task is newer_task
        assert not newer_task.done()
        release_newer_terminal.set()
        await asyncio.wait_for(service.wait_idle(), timeout=1)
        assert (await journal.require(request.stepId)).callback_delivery == "delivered"
        assert (await service.health()).error_code is None
        assert model.requests == []
    finally:
        release_cancel.set()
        release_newer_terminal.set()
        await old_cancel
        await service.close()


@pytest.mark.asyncio
async def test_explicit_duplicate_cancel_preserves_nonzero_attempt_unknown_usage() -> None:
    journal = _journal(prefix="test:service:cancel-called-explicit")
    request = execution_request()
    await journal.accept(request, execution_result(request).resolvedModel.model_dump(mode="json"))
    await journal.mark_started(request)
    await journal.begin_provider_attempt(request)
    await journal.request_cancel(execution_cancel(request))
    model = RecordingModel()
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    assert (await service.cancel(execution_cancel(request))).status == "already_cancelled"
    await service.wait_idle()
    assert model.requests == []
    assert len(callbacks.failures) == 1
    failure = callbacks.failures[0]
    assert failure.errorCategory == "cancelled"
    assert failure.outcomeUnknown is False
    assert failure.usage.usageStatus == "unknown"
    assert failure.usage.providerAttempts == 1
    assert failure.usage.inputTokens is None
    assert failure.usage.completionTokens is None
    assert failure.usage.costMicros is None
    assert (await journal.require(request.stepId)).provider_attempts == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("unknown_recovery", [False, True])
async def test_cancel_between_terminal_read_and_cas_preserves_unknown_usage(
    unknown_recovery: bool,
) -> None:
    class CancelAtTerminalJournal(RedisExecutionJournal):
        async def record_terminal(
            self,
            request: ExecutionStepRequest,
            terminal: ExecutionStepResult | ExecutionStepFailure,
        ) -> JournalEntry:
            if isinstance(terminal, ExecutionStepFailure) and terminal.cancelRequestId is None:
                await self.request_cancel(execution_cancel(request))
            return await super().record_terminal(request, terminal)

    journal = _journal(
        journal_type=CancelAtTerminalJournal, prefix="test:service:cancel-terminal-cas"
    )
    model = RecordingModel()
    callbacks = RejectedPreparingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request(dispatch_mode="running_recovery" if unknown_recovery else "initial")
    await service.submit(request)
    await service.wait_idle()
    assert model.requests == []
    assert len(callbacks.failures) == 1
    failure = callbacks.failures[0]
    assert failure.errorCode == "RUN_CANCELLED"
    assert failure.cancelRequestId == "cancel-1"
    assert failure.outcomeUnknown is False
    assert failure.usage.usageStatus == "unknown"
    assert failure.usage.inputTokens is None
    assert failure.usage.costMicros is None
    assert (await journal.require(request.stepId)).callback_delivery == "delivered"
    assert (await service.health()).error_code is None


@pytest.mark.asyncio
async def test_cancel_wins_provider_race_and_persists_cancelled_terminal() -> None:
    journal = _journal(prefix="test:service:cancel-race")
    model = RecordingModel(block=True)
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request()

    await service.submit(request)
    await asyncio.wait_for(model.started.wait(), timeout=1)
    accepted = await service.cancel(execution_cancel(request))
    await service.wait_idle()

    assert accepted.status == "accepted"
    assert len(model.requests) == 1
    assert callbacks.results == []
    assert len(callbacks.failures) == 1
    failure = callbacks.failures[0]
    assert failure.errorCategory == "cancelled"
    assert failure.errorCode == "RUN_CANCELLED"
    assert failure.cancelRequestId == "cancel-1"
    entry = await journal.require(request.stepId)
    assert entry.state == "failure"
    assert entry.cancel_request_id == "cancel-1"


@pytest.mark.asyncio
async def test_journal_attempt_failure_happens_before_provider_side_effect() -> None:
    journal = _journal(
        journal_type=FailingAttemptJournal,
        prefix="test:service:aof-failure",
    )
    model = RecordingModel()
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request()

    await service.submit(request)
    await service.wait_idle()

    assert model.requests == []
    assert len(callbacks.failures) == 1
    assert callbacks.failures[0].errorCode == "MODEL_PROVIDER_INTERNAL_ERROR"
    entry = await journal.require(request.stepId)
    assert entry.provider_attempts == 0
    assert entry.provider_idempotency_key is None


@pytest.mark.asyncio
async def test_accept_journal_failure_returns_no_acceptance_and_never_calls_model() -> None:
    journal = _journal(
        journal_type=FailingAcceptJournal,
        prefix="test:service:accept-failure",
    )
    model = RecordingModel()
    service = _service(
        journal=journal,
        model=model,
        callbacks=RecordingCallbacks(),
    )

    with pytest.raises(ExecutionJournalError):
        await service.submit(execution_request())

    assert model.requests == []


@pytest.mark.asyncio
async def test_terminal_journal_failure_never_sends_completion_callback() -> None:
    journal = _journal(
        journal_type=FailingTerminalJournal,
        prefix="test:service:terminal-failure",
    )
    model = RecordingModel()
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)

    await service.submit(execution_request())
    await service.wait_idle()

    assert len(model.requests) == 1
    assert callbacks.results == []
    assert callbacks.failures == []


@pytest.mark.asyncio
async def test_restored_backup_missing_running_step_never_repeats_provider_call() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    journal = RedisExecutionJournal(
        cast(AsyncJournalRedis, redis),
        prefix="test:service:restore-quarantine",
    )
    await redis.set(
        "test:service:restore-quarantine:restore:quarantine",
        "epoch=restore-1;snapshotSha256=" + "a" * 64,
    )
    model = RecordingModel(supports_idempotency=False)
    service = _service(
        journal=journal,
        model=model,
        callbacks=RecordingCallbacks(),
    )
    running_recovery = execution_request(dispatch_mode="running_recovery")

    with pytest.raises(ExecutionJournalError, match="RESTORE_QUARANTINED"):
        await service.submit(running_recovery)

    assert model.requests == []
    assert await journal.get(running_recovery.stepId) is None


@pytest.mark.asyncio
async def test_inflight_provider_terminal_stays_pending_behind_restore_barrier() -> None:
    prefix = "test:service:inflight-restore-barrier"
    redis = fakeredis.aioredis.FakeRedis()
    journal = RedisExecutionJournal(
        cast(AsyncJournalRedis, redis),
        prefix=prefix,
    )
    model = RecordingModel(block=True)
    callbacks = RecordingCallbacks()
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = execution_request()

    await service.submit(request)
    await asyncio.wait_for(model.started.wait(), timeout=1)
    await redis.set(f"{prefix}:restore:quarantine", "restore-epoch")
    model.release.set()
    await service.wait_idle()

    pending = await journal.require(request.stepId)
    assert pending.state == "result"
    assert pending.callback_delivery == "pending"
    assert pending.terminal is not None
    assert callbacks.terminal_attempts == 0
    assert callbacks.results == []
    assert callbacks.failures == []
    quarantined = await service.health()
    assert quarantined.ready is False
    assert quarantined.journal_quarantined is True
    assert quarantined.error_code == "EXECUTION_JOURNAL_RESTORE_QUARANTINED"

    await redis.delete(f"{prefix}:restore:quarantine")
    outcome = await service.callback_replayer.deliver_immediately(request.stepId)
    recovered = await service.health()

    assert outcome == "delivered"
    assert callbacks.terminal_attempts == 1
    assert len(callbacks.results) == 1
    assert recovered.ready is True
    assert recovered.error_code is None
    assert recovered.journal_quarantined is False
    assert await service.callback_replayer.deliver_immediately(request.stepId) is None
    assert callbacks.terminal_attempts == 1


@pytest.mark.asyncio
async def test_rejected_callback_backlog_blocks_new_provider_work_but_keeps_terminal() -> None:
    journal = _journal(prefix="test:service:rejected-gate")
    blocked_request = execution_request()
    blocked_terminal = execution_result(blocked_request)
    await journal.accept(
        blocked_request,
        blocked_terminal.resolvedModel.model_dump(mode="json"),
    )
    await journal.record_terminal(blocked_request, blocked_terminal)
    await journal.mark_callback_rejected(
        step_id=blocked_request.stepId,
        request_hash=blocked_request.requestHash,
        result_hash=blocked_terminal.resultHash,
        error_code="EXECUTION_CALLBACK_REJECTED",
    )
    model = RecordingModel()
    service = _service(
        journal=journal,
        model=model,
        callbacks=RecordingCallbacks(),
    )
    fresh = rehash_request(
        execution_request(job_id="job-fresh").model_copy(
            update={"stepId": "step-fresh", "idempotencyKey": "idem-fresh"}
        )
    )

    health = await service.health()
    with pytest.raises(
        ExecutionServiceUnavailableError,
        match="EXECUTION_CALLBACK_REJECTED_BACKLOG",
    ):
        await service.submit(fresh)

    assert health.ready is False
    assert model.requests == []
    assert await journal.get(fresh.stepId) is None
    assert (await journal.require(blocked_request.stepId)).terminal is not None


@pytest.mark.asyncio
async def test_pending_callback_threshold_blocks_new_provider_work() -> None:
    journal = _journal(prefix="test:service:pending-gate")
    for index in range(2):
        terminal_request = rehash_request(
            execution_request(job_id=f"job-terminal-{index}").model_copy(
                update={
                    "stepId": f"step-terminal-{index}",
                    "idempotencyKey": f"idem-terminal-{index}",
                }
            )
        )
        terminal = execution_result(terminal_request)
        await journal.accept(
            terminal_request,
            terminal.resolvedModel.model_dump(mode="json"),
        )
        await journal.record_terminal(terminal_request, terminal)
    model = RecordingModel()
    service = _service(
        journal=journal,
        model=model,
        callbacks=RecordingCallbacks(),
        pending_backlog_limit=1,
    )
    fresh = rehash_request(
        execution_request(job_id="job-after-backlog").model_copy(
            update={"stepId": "step-after-backlog", "idempotencyKey": "idem-after"}
        )
    )

    with pytest.raises(
        ExecutionServiceUnavailableError,
        match="EXECUTION_CALLBACK_PENDING_BACKLOG",
    ):
        await service.submit(fresh)

    assert model.requests == []
    assert await journal.get(fresh.stepId) is None


@pytest.mark.asyncio
async def test_permanent_background_error_blocks_new_provider_work() -> None:
    journal = _journal(prefix="test:service:background-gate")
    model = RecordingModel()
    service = _service(
        journal=journal,
        model=model,
        callbacks=RecordingCallbacks(),
    )
    service._error_code = "EXECUTION_BACKGROUND_TASK_FAILED"  # noqa: SLF001

    with pytest.raises(
        ExecutionServiceUnavailableError,
        match="EXECUTION_BACKGROUND_TASK_FAILED",
    ):
        await service.submit(execution_request())

    assert model.requests == []
    assert (await service.health()).error_code == "EXECUTION_BACKGROUND_TASK_FAILED"


@pytest.mark.asyncio
async def test_replayer_supervisor_backoff_blocks_new_provider_work() -> None:
    journal = _journal(prefix="test:service:replayer-supervisor-gate")
    model = RecordingModel()
    service = _service(
        journal=journal,
        model=model,
        callbacks=RecordingCallbacks(),
    )
    service.set_background_health_check(lambda: False)

    with pytest.raises(
        ExecutionServiceUnavailableError,
        match="EXECUTION_CALLBACK_REPLAYER_UNHEALTHY",
    ):
        await service.submit(execution_request())

    assert model.requests == []
    assert (await service.health()).error_code == ("EXECUTION_CALLBACK_REPLAYER_UNHEALTHY")


@pytest.mark.asyncio
async def test_health_reports_pending_and_rejected_callback_backlog() -> None:
    journal = _journal(prefix="test:service:health")
    service = _service(
        journal=journal,
        model=RecordingModel(),
        callbacks=RecordingCallbacks(),
        pending_backlog_limit=1,
    )
    first = execution_request()
    second = rehash_request(first.model_copy(update={"stepId": "step-2"}))

    for request in (first, second):
        terminal = execution_result(request)
        await journal.accept(
            request,
            terminal.resolvedModel.model_dump(mode="json"),
        )
        await journal.record_terminal(request, terminal)

    pending = await service.health()
    assert pending.ready is False
    assert pending.callback_pending == 2
    assert pending.callback_rejected == 0
    assert pending.error_code == "EXECUTION_CALLBACK_PENDING_BACKLOG"

    first_terminal = execution_result(first)
    await journal.mark_callback_rejected(
        step_id=first.stepId,
        request_hash=first.requestHash,
        result_hash=first_terminal.resultHash,
        error_code="EXECUTION_CALLBACK_REJECTED",
    )
    rejected = await service.health()
    assert rejected.ready is False
    assert rejected.callback_pending == 1
    assert rejected.callback_rejected == 1
    assert rejected.error_code == "EXECUTION_CALLBACK_REJECTED_BACKLOG"


def _receipt(
    callback: ExecutionStepProgress | ExecutionStepResult | ExecutionStepFailure,
    *,
    status: Literal["accepted", "duplicate", "stale", "superseded"] = "accepted",
) -> ExecutionCallbackReceipt:
    return ExecutionCallbackReceipt(
        protocolVersion="2.0",
        runId=callback.runId,
        stepId=callback.stepId,
        jobId=callback.jobId,
        fencingToken=callback.fencingToken,
        requestHash=callback.requestHash,
        status=status,
        receivedAt=callback.occurredAt
        if isinstance(callback, ExecutionStepProgress)
        else callback.completedAt
        if isinstance(callback, ExecutionStepResult)
        else callback.failedAt,
    )
