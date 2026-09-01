from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import replace
from types import MappingProxyType
from typing import Literal

import pytest
from inkforge_agents.execution.executor import (
    ExecutionCapabilityError,
    StatelessExecutionStepExecutor,
    _retry_delay_seconds,
)
from inkforge_agents.execution.registry import load_execution_registry
from inkforge_agents.providers.base import (
    ModelStructuredOutputRoute,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
    ModelUsageDiagnostics,
    ProviderTransportError,
)
from inkforge_agents.providers.fake import FakeModelProvider
from inkforge_agents.runtime.model_runtime import ModelRuntime

from .support import (
    answer_question_request,
    execution_request,
    rehash_request,
    review_request,
)


class RecordingModel:
    provider_name = "fake"
    model_name = "fake"

    def __init__(
        self,
        *,
        result: ModelTurnResult | None = None,
        supports_idempotency: bool = True,
        block: bool = False,
    ) -> None:
        self.supports_request_idempotency = supports_idempotency
        if supports_idempotency:
            self.provider_name = "fake"
            self.model_name = "fake"
            self.transport_profile = "transport.fake.v1"
            self.endpoint_profile = "endpoint.local-fake.v1"
            self.capability_version = "capability.fake.structured-output.v1"
        else:
            self.provider_name = "openai_compatible"
            self.model_name = "deepseek-v4-flash"
            self.transport_profile = "transport.deepseek-v4.v1"
            self.endpoint_profile = "endpoint.deepseek-official.v1"
            self.capability_version = "capability.deepseek-v4.chat-json.v1"
        self._result = result
        self._block = block
        self.requests: list[ModelTurnRequest] = []

    def supports_structured_output(self, route: ModelStructuredOutputRoute) -> bool:
        expected = (
            "responses_json_schema_v1"
            if self.transport_profile == "transport.fake.v1"
            else "chat_json_output_v1"
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

        async def complete() -> ModelTurnResult:
            if self._block:
                await asyncio.Event().wait()
            return self._result or await FakeModelProvider().complete_turn(request)

        if provider_timeout_seconds is None:
            return attempt, await complete()
        async with asyncio.timeout(provider_timeout_seconds):
            return attempt, await complete()


def _executor(model: RecordingModel) -> StatelessExecutionStepExecutor:
    return StatelessExecutionStepExecutor(
        model,
        max_output_tokens=10_000,
        retry_base_seconds=0,
    )


@pytest.mark.asyncio
async def test_generation_uses_one_strict_call_and_passes_provider_idempotency_key() -> None:
    registry = load_execution_registry(environment="test")
    request = execution_request()
    model = RecordingModel()
    executor = _executor(model)
    resolved = executor.resolve(request, registry)
    model_request = executor.build_model_request(request, resolved)
    attempts = 0

    async def begin_attempt() -> int:
        nonlocal attempts
        attempts += 1
        return attempts

    outcome = await executor.call_provider(
        request,
        model_request,
        begin_attempt=begin_attempt,
        cancel_event=asyncio.Event(),
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)

    assert terminal.resultKind == "output"
    assert terminal.output is not None
    assert terminal.output["replacement"] == "模拟选区替换文本"
    assert terminal.output["contentSha256"] == hashlib.sha256(
        "模拟选区替换文本".encode()
    ).hexdigest()
    assert attempts == 1
    assert len(model.requests) == 1
    assert model.requests[0].requestIdempotencyKey == request.idempotencyKey
    assert model.requests[0].tools == []
    assert model.requests[0].structuredOutput is not None
    prompt_envelope = json.loads(model.requests[0].messages[1].content)
    assert prompt_envelope["outputSchema"]["sha256"] == request.outputSchema.sha256


@pytest.mark.asyncio
async def test_answer_question_uses_exact_no_reasoning_single_step_contract() -> None:
    registry = load_execution_registry(environment="test")
    request = answer_question_request(registry)
    model = RecordingModel()
    executor = _executor(model)
    resolved = executor.resolve(request, registry)
    model_request = executor.build_model_request(request, resolved)

    outcome = await executor.call_provider(
        request,
        model_request,
        begin_attempt=_one_attempt,
        cancel_event=asyncio.Event(),
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)

    assert terminal.resultKind == "output"
    assert terminal.output == {"answer": "模拟模型已依据冻结章节证据回答问题。"}
    assert terminal.usage.reasoningTokens == 0
    assert request.purpose == "generation"
    assert request.lane == "interactive"
    assert request.artifactId is None
    assert resolved.rubric_version is None
    assert model_request.tools == []
    assert model_request.parallelToolCalls is False
    assert model_request.policy.thinkingMode == "disabled"
    assert model_request.thinkingMode == "disabled"
    assert len(model.requests) == 1


def test_answer_question_rejects_non_catalog_input_and_execution_identity() -> None:
    registry = load_execution_registry(environment="test")
    executor = _executor(RecordingModel())
    request = answer_question_request(registry)

    extra_input = rehash_request(
        request.model_copy(
            update={
                "input": {
                    "userInstruction": "问题",
                    "selectedAgents": ["编辑"],
                }
            }
        )
    )
    with pytest.raises(ExecutionCapabilityError, match="只含完整"):
        executor.resolve(extra_input, registry)

    artifact_bound = rehash_request(
        request.model_copy(
            update={"artifactId": "artifact-1", "artifactRevision": 1}
        )
    )
    with pytest.raises(ExecutionCapabilityError, match="不能绑定"):
        executor.resolve(artifact_bound, registry)

    no_novel = rehash_request(request.model_copy(update={"novelId": None}))
    with pytest.raises(ExecutionCapabilityError, match="novelId"):
        executor.resolve(no_novel, registry)

    wrong_lane = rehash_request(request.model_copy(update={"lane": "creative"}))
    with pytest.raises(ExecutionCapabilityError, match="lane"):
        executor.resolve(wrong_lane, registry)


@pytest.mark.asyncio
async def test_reviewer_profile_produces_evidence_evaluation_without_tool_loop() -> None:
    registry = load_execution_registry(environment="test")
    request = review_request(registry)
    model = RecordingModel()
    executor = _executor(model)
    resolved = executor.resolve(request, registry)
    model_request = executor.build_model_request(request, resolved)

    outcome = await executor.call_provider(
        request,
        model_request,
        begin_attempt=_one_attempt,
        cancel_event=asyncio.Event(),
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)

    assert terminal.resultKind == "evaluation"
    assert terminal.evaluation is not None
    assert terminal.evaluation.contentVerdict == "pass"
    assert terminal.evaluation.findings == []
    assert terminal.evaluation.artifactId == "artifact-1"
    assert len(model.requests) == 1


def test_generation_and_two_reviewers_use_distinct_hash_bound_system_prompts() -> None:
    registry = load_execution_registry(environment="test")
    executor = _executor(RecordingModel())
    generation = execution_request()
    consistency = review_request(registry, profile_key="reviewer.consistency.v1")
    editorial = review_request(registry, profile_key="reviewer.editorial.v1")

    requests = [
        executor.build_model_request(value, executor.resolve(value, registry))
        for value in (generation, consistency, editorial)
    ]
    prompts = [value.messages[0].content for value in requests]

    assert len(set(prompts)) == 3
    for request, prompt in zip((generation, consistency, editorial), prompts, strict=True):
        reference = request.modelProfile.promptProfile
        definition = registry.prompt_profiles[reference.name]
        assert hashlib.sha256(prompt.encode("utf-8")).hexdigest() == reference.sha256
        assert definition.system_prompt == prompt


def test_unknown_operation_and_budget_drift_fail_before_provider() -> None:
    registry = load_execution_registry(environment="test")
    executor = _executor(RecordingModel())
    request = execution_request()

    with pytest.raises(ExecutionCapabilityError, match="Operation handler"):
        executor.resolve(
            request.model_copy(update={"operation": "write_chapter"}),
            registry,
        )

    drifted = request.model_copy(
        update={"budget": request.budget.model_copy(update={"maxCompletionTokens": 7_999})}
    )
    with pytest.raises(ExecutionCapabilityError, match="Step Budget"):
        executor.resolve(drifted, registry)

    prompt = request.modelProfile.promptProfile.model_copy(update={"sha256": "0" * 64})
    prompt_drift = rehash_request(request.model_copy(update={
        "modelProfile": request.modelProfile.model_copy(update={"promptProfile": prompt})
    }))
    with pytest.raises(ExecutionCapabilityError, match="Prompt Profile"):
        executor.resolve(prompt_drift, registry)

    unauthorized_model = RecordingModel()
    unauthorized_model.provider_name = "unregistered"
    unauthorized_executor = _executor(unauthorized_model)
    with pytest.raises(ExecutionCapabilityError, match="Deployment Profile"):
        unauthorized_executor.resolve(request, registry)


def test_inflight_request_uses_retained_versioned_refs_after_operation_downline() -> None:
    registry = load_execution_registry(environment="test")
    request = review_request(registry, dispatch_mode="running_recovery")
    downlined = replace(registry, operations=MappingProxyType({}))

    resolved = _executor(RecordingModel()).resolve(request, downlined)

    assert resolved.profile.key == request.modelProfile.profile
    assert resolved.prompt_profile.key == request.modelProfile.promptProfile.name
    assert resolved.output_schema.key == request.outputSchema.name
    assert resolved.rubric_version == "rubric.chapter_selection.review.v1"

    answer = answer_question_request(
        registry,
        dispatch_mode="running_recovery",
    )
    resolved_answer = _executor(RecordingModel()).resolve(answer, downlined)
    assert resolved_answer.profile.key == "editor.answer.v1"
    assert resolved_answer.output_schema.key == "output.chat_answer.v1"
    assert resolved_answer.rubric_version is None


@pytest.mark.asyncio
async def test_timeout_after_provider_start_is_model_outcome_unknown() -> None:
    registry = load_execution_registry(environment="test")
    request = execution_request()
    timeout_request = request.model_copy(
        update={"budget": request.budget.model_copy(update={"maxWallClockSeconds": 1})}
    )
    model = RecordingModel(block=True, supports_idempotency=False)
    executor = _executor(model)
    resolved = executor.resolve(request, registry)
    model_request = executor.build_model_request(request, resolved)

    outcome = await executor.call_provider(
        timeout_request,
        model_request,
        begin_attempt=_one_attempt,
        cancel_event=asyncio.Event(),
    )
    terminal = executor.terminal_from_outcome(timeout_request, resolved, outcome)

    assert terminal.errorCategory == "model_outcome_unknown"
    assert terminal.errorCode == "MODEL_OUTCOME_UNKNOWN"
    assert terminal.outcomeUnknown is True
    assert terminal.usage.wallTimeMillis <= 1_000
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_initial_lane_queue_does_not_consume_provider_wall_clock() -> None:
    class CapacityProvider:
        billable = False
        provider_name = "fake"
        model_name = "fake"
        transport_profile = "transport.fake.v1"
        endpoint_profile = "endpoint.local-fake.v1"
        capability_version = "capability.fake.structured-output.v1"
        supports_request_idempotency = True

        def __init__(self) -> None:
            self.blocker_started = asyncio.Event()
            self.release_blocker = asyncio.Event()

        def supports_structured_output(self, route: ModelStructuredOutputRoute) -> bool:
            return route == "responses_json_schema_v1"

        async def complete_turn(self, model_request: ModelTurnRequest) -> ModelTurnResult:
            if model_request.messages[0].content == "占用唯一模型槽":
                self.blocker_started.set()
                await self.release_blocker.wait()
            return await FakeModelProvider().complete_turn(model_request)

    provider = CapacityProvider()
    runtime = ModelRuntime(provider, max_concurrency=1)  # type: ignore[arg-type]
    executor = StatelessExecutionStepExecutor(
        runtime,
        max_output_tokens=10_000,
        retry_base_seconds=0,
    )
    registry = load_execution_registry(environment="test")
    request = execution_request()
    request = request.model_copy(
        update={"budget": request.budget.model_copy(update={"maxWallClockSeconds": 1})}
    )
    resolved = executor.resolve(execution_request(), registry)
    model_request = executor.build_model_request(execution_request(), resolved)
    blocker_request = ModelTurnRequest(
        messages=[{"role": "user", "content": "占用唯一模型槽"}],
        tools=[],
        maxOutputTokens=64,
        policy={"policyId": "test", "thinkingMode": "disabled"},
    )
    blocker = asyncio.create_task(runtime.run_turn(blocker_request, lane="interactive"))
    await asyncio.wait_for(provider.blocker_started.wait(), timeout=1)
    attempts = 0

    async def begin_attempt() -> int:
        nonlocal attempts
        attempts += 1
        return attempts

    pending = asyncio.create_task(
        executor.call_provider(
            request,
            model_request,
            begin_attempt=begin_attempt,
            cancel_event=asyncio.Event(),
        )
    )
    try:
        await asyncio.sleep(1.05)
        assert attempts == 0
        assert pending.done() is False
        provider.release_blocker.set()
        outcome = await asyncio.wait_for(pending, timeout=1)
    finally:
        provider.release_blocker.set()
        await blocker

    assert outcome.failure_category is None
    assert outcome.provider_attempts == 1
    assert outcome.elapsed_millis < 1_000


@pytest.mark.asyncio
async def test_invalid_structure_and_usage_budget_become_failures() -> None:
    registry = load_execution_registry(environment="test")
    request = execution_request()
    invalid_hash_result = ModelTurnResult(
        content="",
        toolCalls=[],
        structuredOutput={"replacement": "改写", "contentSha256": "0" * 64},
        usage=ModelUsage(
            promptTokens=100,
            cachedTokens=0,
            completionTokens=20,
            totalTokens=120,
        ),
        diagnostics=ModelUsageDiagnostics(
            promptCacheMissTokens=100,
            reasoningTokens=10,
        ),
        finishReason="stop",
    )
    model = RecordingModel(result=invalid_hash_result)
    executor = _executor(model)
    resolved = executor.resolve(request, registry)
    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_one_attempt,
        cancel_event=asyncio.Event(),
    )
    invalid_terminal = executor.terminal_from_outcome(request, resolved, outcome)

    assert invalid_terminal.errorCode == "MODEL_OUTPUT_SCHEMA_INVALID"

    oversized = invalid_hash_result.model_copy(
        update={
            "structuredOutput": (
                await FakeModelProvider().complete_turn(
                    executor.build_model_request(request, resolved)
                )
            ).structuredOutput,
            "usage": ModelUsage(
                promptTokens=100,
                cachedTokens=0,
                completionTokens=8_001,
                totalTokens=8_101,
            ),
            "diagnostics": ModelUsageDiagnostics(
                promptCacheMissTokens=100,
                reasoningTokens=4_001,
            ),
        }
    )
    budget_executor = _executor(RecordingModel(result=oversized))
    budget_outcome = await budget_executor.call_provider(
        request,
        budget_executor.build_model_request(request, resolved),
        begin_attempt=_one_attempt,
        cancel_event=asyncio.Event(),
    )
    budget_terminal = budget_executor.terminal_from_outcome(
        request,
        resolved,
        budget_outcome,
    )
    assert budget_terminal.errorCode == "STEP_BUDGET_EXCEEDED"
    assert budget_terminal.errorCategory == "validation"
    assert budget_terminal.usage.completionTokens == 8_001

    cancelled_terminal = budget_executor.terminal_from_outcome(
        request,
        resolved,
        budget_outcome,
        cancel_request_id="cancel-budget-0001",
    )
    assert cancelled_terminal.errorCode == "STEP_BUDGET_EXCEEDED"
    assert cancelled_terminal.errorCategory == "cancelled"
    assert cancelled_terminal.cancelRequestId == "cancel-budget-0001"


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", ["", "   ", "\n\t", "\u3000"])
async def test_blank_generation_replacement_is_a_deterministic_failure(
    replacement: str,
) -> None:
    request = execution_request()
    result = ModelTurnResult(
        content="",
        toolCalls=[],
        structuredOutput={"replacement": replacement},
        usage=ModelUsage(
            promptTokens=100,
            cachedTokens=0,
            completionTokens=20,
            totalTokens=120,
        ),
        diagnostics=ModelUsageDiagnostics(
            promptCacheMissTokens=100,
            reasoningTokens=10,
        ),
        finishReason="stop",
    )
    executor = _executor(RecordingModel(result=result))
    resolved = executor.resolve(
        request,
        load_execution_registry(environment="test"),
    )

    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_one_attempt,
        cancel_event=asyncio.Event(),
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)

    assert terminal.errorCode == "MODEL_OUTPUT_PROTOCOL_INVALID"
    assert terminal.errorCategory == "validation"


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", ["", "   ", "\n\t", "\u3000"])
async def test_blank_chat_answer_is_a_deterministic_failure(answer: str) -> None:
    registry = load_execution_registry(environment="test")
    request = answer_question_request(registry)
    result = ModelTurnResult(
        content="",
        toolCalls=[],
        structuredOutput={"answer": answer},
        usage=ModelUsage(
            promptTokens=100,
            cachedTokens=0,
            completionTokens=20,
            totalTokens=120,
        ),
        diagnostics=ModelUsageDiagnostics(
            promptCacheMissTokens=100,
            reasoningTokens=0,
        ),
        finishReason="stop",
    )
    executor = _executor(RecordingModel(result=result))
    resolved = executor.resolve(request, registry)

    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_one_attempt,
        cancel_event=asyncio.Event(),
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)

    assert terminal.errorCode == "MODEL_OUTPUT_PROTOCOL_INVALID"
    assert terminal.errorCategory == "validation"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "structured_output",
    [
        {},
        {"answer": 1},
        {"answer": "回答", "review": "禁止夹带"},
    ],
)
async def test_chat_answer_rejects_non_schema_output(
    structured_output: dict[str, object],
) -> None:
    registry = load_execution_registry(environment="test")
    request = answer_question_request(registry)
    result = ModelTurnResult(
        content="",
        toolCalls=[],
        structuredOutput=structured_output,
        usage=ModelUsage(
            promptTokens=100,
            cachedTokens=0,
            completionTokens=20,
            totalTokens=120,
        ),
        diagnostics=ModelUsageDiagnostics(
            promptCacheMissTokens=100,
            reasoningTokens=0,
        ),
        finishReason="stop",
    )
    executor = _executor(RecordingModel(result=result))
    resolved = executor.resolve(request, registry)

    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_one_attempt,
        cancel_event=asyncio.Event(),
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)

    assert terminal.errorCode == "MODEL_OUTPUT_SCHEMA_INVALID"


@pytest.mark.asyncio
async def test_answer_question_preserves_unexpected_reasoning_usage_and_fails_budget() -> None:
    registry = load_execution_registry(environment="test")
    request = answer_question_request(registry)
    result = ModelTurnResult(
        content="",
        toolCalls=[],
        structuredOutput={"answer": "完整回答"},
        usage=ModelUsage(
            promptTokens=100,
            cachedTokens=0,
            completionTokens=20,
            totalTokens=120,
        ),
        diagnostics=ModelUsageDiagnostics(
            promptCacheMissTokens=100,
            reasoningTokens=1,
        ),
        finishReason="stop",
    )
    executor = _executor(RecordingModel(result=result))
    resolved = executor.resolve(request, registry)

    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_one_attempt,
        cancel_event=asyncio.Event(),
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)

    assert terminal.errorCode == "STEP_BUDGET_EXCEEDED"
    assert terminal.usage.reasoningTokens == 1


@pytest.mark.asyncio
async def test_ambiguous_connection_error_retries_only_with_provider_idempotency() -> None:
    registry = load_execution_registry(environment="test")
    request = execution_request()

    class ConnectionModel(RecordingModel):
        async def run_execution_turn(
            self,
            model_request: ModelTurnRequest,
            *,
            before_provider: Callable[[], Awaitable[int]],
            **_: object,
        ) -> tuple[int, ModelTurnResult]:
            attempt = await before_provider()
            self.requests.append(model_request)
            if len(self.requests) == 1:
                raise ProviderTransportError(
                    code="connection_error",
                    statusCode=None,
                    requestId=None,
                )
            return attempt, await FakeModelProvider().complete_turn(model_request)

    unsafe_model = ConnectionModel(supports_idempotency=False)
    unsafe_executor = _executor(unsafe_model)
    unsafe_resolved = unsafe_executor.resolve(request, registry)
    unsafe_outcome = await unsafe_executor.call_provider(
        request,
        unsafe_executor.build_model_request(request, unsafe_resolved),
        begin_attempt=_incrementing_attempts(),
        cancel_event=asyncio.Event(),
    )
    unsafe_terminal = unsafe_executor.terminal_from_outcome(
        request,
        unsafe_resolved,
        unsafe_outcome,
    )

    assert unsafe_terminal.errorCode == "MODEL_OUTCOME_UNKNOWN"
    assert len(unsafe_model.requests) == 1

    safe_model = ConnectionModel(supports_idempotency=True)
    safe_executor = _executor(safe_model)
    safe_resolved = safe_executor.resolve(request, registry)
    safe_outcome = await safe_executor.call_provider(
        request,
        safe_executor.build_model_request(request, safe_resolved),
        begin_attempt=_incrementing_attempts(),
        cancel_event=asyncio.Event(),
    )
    safe_terminal = safe_executor.terminal_from_outcome(
        request,
        safe_resolved,
        safe_outcome,
    )

    assert safe_terminal.resultKind == "output"
    assert len(safe_model.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "status_code"),
    [("timeout_error", None), ("http_error", 500)],
)
async def test_non_idempotent_timeout_or_5xx_is_unknown_without_retry(
    code: Literal["timeout_error", "http_error"],
    status_code: int | None,
) -> None:
    registry = load_execution_registry(environment="test")
    request = execution_request()

    class FailingModel(RecordingModel):
        async def run_execution_turn(
            self,
            model_request: ModelTurnRequest,
            *,
            before_provider: Callable[[], Awaitable[int]],
            **_: object,
        ) -> tuple[int, ModelTurnResult]:
            await before_provider()
            self.requests.append(model_request)
            raise ProviderTransportError(
                code=code,
                statusCode=status_code,
                requestId=None,
            )

    model = FailingModel(supports_idempotency=False)
    executor = _executor(model)
    resolved = executor.resolve(request, registry)
    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_incrementing_attempts(),
        cancel_event=asyncio.Event(),
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)

    assert terminal.errorCode == "MODEL_OUTCOME_UNKNOWN"
    assert terminal.outcomeUnknown is True
    assert terminal.usage.providerAttempts == 1
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_non_idempotent_429_is_the_only_automatic_retry() -> None:
    registry = load_execution_registry(environment="test")
    request = execution_request()

    class RateLimitedOnceModel(RecordingModel):
        async def run_execution_turn(
            self,
            model_request: ModelTurnRequest,
            *,
            before_provider: Callable[[], Awaitable[int]],
            **_: object,
        ) -> tuple[int, ModelTurnResult]:
            attempt = await before_provider()
            self.requests.append(model_request)
            if len(self.requests) == 1:
                raise ProviderTransportError(
                    code="http_error",
                    statusCode=429,
                    requestId=None,
                )
            return attempt, await FakeModelProvider().complete_turn(model_request)

    model = RateLimitedOnceModel(supports_idempotency=False)
    executor = _executor(model)
    resolved = executor.resolve(request, registry)
    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_incrementing_attempts(),
        cancel_event=asyncio.Event(),
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)

    assert terminal.resultKind == "output"
    assert terminal.usage.providerAttempts == 2
    assert len(model.requests) == 2


@pytest.mark.asyncio
async def test_idempotent_builtin_timeout_retries_with_same_request_key() -> None:
    registry = load_execution_registry(environment="test")
    request = execution_request()

    class TimeoutOnceModel(RecordingModel):
        async def run_execution_turn(
            self,
            model_request: ModelTurnRequest,
            *,
            before_provider: Callable[[], Awaitable[int]],
            **_: object,
        ) -> tuple[int, ModelTurnResult]:
            attempt = await before_provider()
            self.requests.append(model_request)
            if len(self.requests) == 1:
                raise TimeoutError
            return attempt, await FakeModelProvider().complete_turn(model_request)

    model = TimeoutOnceModel(supports_idempotency=True)
    executor = _executor(model)
    resolved = executor.resolve(request, registry)
    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_incrementing_attempts(),
        cancel_event=asyncio.Event(),
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)

    assert terminal.resultKind == "output"
    assert terminal.usage.providerAttempts == 2
    assert {item.requestIdempotencyKey for item in model.requests} == {request.idempotencyKey}


@pytest.mark.asyncio
async def test_unclassified_exception_after_attempt_is_outcome_unknown() -> None:
    registry = load_execution_registry(environment="test")
    request = execution_request()

    class InvalidAdapterModel(RecordingModel):
        async def run_execution_turn(
            self,
            model_request: ModelTurnRequest,
            *,
            before_provider: Callable[[], Awaitable[int]],
            **_: object,
        ) -> tuple[int, ModelTurnResult]:
            await before_provider()
            self.requests.append(model_request)
            raise ValueError("供应商返回无法可靠解析")

    model = InvalidAdapterModel(supports_idempotency=False)
    executor = _executor(model)
    resolved = executor.resolve(request, registry)
    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_incrementing_attempts(),
        cancel_event=asyncio.Event(),
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)

    assert terminal.errorCode == "MODEL_OUTCOME_UNKNOWN"
    assert terminal.outcomeUnknown is True
    assert terminal.usage.providerAttempts == 1


def test_retry_jitter_is_stable_and_request_scoped() -> None:
    first = _retry_delay_seconds(1.0, 2, "a" * 64)
    repeated = _retry_delay_seconds(1.0, 2, "a" * 64)
    another = _retry_delay_seconds(1.0, 2, "b" * 64)

    assert first == repeated
    assert 1.5 <= first <= 2.5
    assert another != first


async def _one_attempt() -> int:
    return 1


def _incrementing_attempts() -> Callable[[], Awaitable[int]]:
    value = 0

    async def next_attempt() -> int:
        nonlocal value
        value += 1
        return value

    return next_attempt
