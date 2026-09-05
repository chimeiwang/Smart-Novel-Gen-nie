"""四项中短篇的真实 v2 资产与单 Step 执行；关闭路径使用隔离 fixture。"""

import asyncio
import hashlib
import json
from dataclasses import replace
from types import MappingProxyType

import pytest
from inkforge_agents.execution.executor import (
    ExecutionCapabilityError,
    StatelessExecutionStepExecutor,
)
from inkforge_agents.execution.registry import load_execution_registry
from inkforge_agents.execution.service import ExecutionService
from inkforge_agents.execution.short_medium import SHORT_MEDIUM_HANDLERS
from inkforge_agents.providers.base import ModelTurnResult, ModelUsage
from inkforge_contracts.execution import (
    EvidenceBundle,
    EvidenceItem,
    EvidenceManifest,
    EvidenceManifestItem,
    ModelProfileRef,
    OutputSchemaRef,
    PromptProfileRef,
    StepBudget,
    canonical_execution_json_bytes,
    canonical_execution_sha256,
)
from inkforge_contracts.short_medium_execution import ShortMediumContextV2

from .support import execution_cancel, execution_request, rehash_request
from .test_executor import RecordingModel
from .test_service import RecordingCallbacks, _journal


def _hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _registry():
    return load_execution_registry(environment="test")


def _disabled_registry():
    registry = load_execution_registry(environment="test")
    return replace(
        registry,
        operations=MappingProxyType(
            {
                key: replace(value, v2_enabled=False) if value.workflow == "short_medium" else value
                for key, value in registry.operations.items()
            }
        ),
    )


def _context(operation, target):
    value = dict.fromkeys(ShortMediumContextV2.model_fields)
    manuscript = operation != "generate_outline"
    value.update(
        workflow="short_medium",
        operation=operation,
        documentType="manuscript" if manuscript else "outline",
        chapterId="chapter-1" if manuscript else None,
        targetTotalWordCount=target,
        userInstruction=" 完整指令\n",
    )
    if operation in {"generate_outline", "generate_manuscript"}:
        value.update(sourceKind="opening", sourceText=" 固定开头😀\n")
    if manuscript:
        value.update(
            sourceOutlineVersionId="outline-1",
            sourceOutlineContent=" 蓝图全文\n",
            sourceOutlineContentHash=_hash(" 蓝图全文\n"),
        )
    if operation in {"replace_selection", "full_check"}:
        value.update(baseVersionId="base-1", baseContent="前😀后", baseContentHash=_hash("前😀后"))
    if operation == "replace_selection":
        value.update(
            selectionStart=1,
            selectionEnd=2,
            selectedText="😀",
            selectedTextHash=_hash("😀"),
            contextBefore="前",
            contextAfter="后",
        )
    return value


def _bundle(operation, context, prior):
    rows = [("short_medium_context", "novel-1", context)] + [
        (
            "short_medium_segment",
            producer,
            {"index": index, "content": content, "contentSha256": _hash(content)},
        )
        for index, producer, content in prior
    ]
    items = [
        EvidenceItem(
            id=f"item-{ordinal}",
            bundleId="bundle-short",
            ordinal=ordinal,
            resourceType=kind,
            resourceId=identity,
            exists=True,
            contentType="json",
            contentJson=value,
            contentSha256=canonical_execution_sha256(value),
            byteCount=len(canonical_execution_json_bytes(value)),
        )
        for ordinal, (kind, identity, value) in enumerate(rows, 1)
    ]
    manifest = EvidenceManifest(
        bundleId="bundle-short",
        bundleVersion=len(prior) + 1,
        itemCount=len(items),
        items=[
            EvidenceManifestItem(
                itemId=item.id,
                **item.model_dump(exclude={"id", "bundleId", "contentJson", "contentText"}),
            )
            for item in items
        ],
    )
    return EvidenceBundle(
        id="bundle-short",
        runId="run-1",
        version=len(prior) + 1,
        policyVersion=f"evidence.short_medium.{SHORT_MEDIUM_HANDLERS[operation][2]}.v1",
        manifest=manifest,
        manifestSha256=canonical_execution_sha256(
            manifest.model_dump(mode="json", exclude_none=True)
        ),
        totalBytes=sum(item.byteCount for item in items),
        items=items,
    )


def short_request(operation="generate_outline", *, target=15000, index=0, prior=(), context=None):
    registry = _registry()
    resolved = registry.resolve("short_medium", operation)
    profile, schema, budget = (
        resolved.generator_profile,
        resolved.output_schema,
        resolved.generator_step_budget,
    )
    source = context or _context(operation, target)
    count = (target + 14999) // 15000 if operation == "generate_manuscript" else 1
    request = execution_request().model_copy(
        update={
            "workflow": "short_medium",
            "operation": operation,
            "lane": resolved.operation.lane,
            "input": {"segmentIndex": index, "segmentCount": count},
            "evidenceBundle": _bundle(operation, source, prior),
            "modelProfile": ModelProfileRef(
                profile=profile.key,
                version=profile.version,
                reasoningMode=profile.reasoning_mode,
                deploymentProfileKey=profile.deployment_profile_key,
                promptProfile=PromptProfileRef(
                    name=profile.prompt_profile.key,
                    version=profile.prompt_profile.version,
                    sha256=profile.prompt_profile.sha256,
                ),
            ),
            "outputSchema": OutputSchemaRef(
                name=schema.key,
                version=schema.version,
                sha256=schema.sha256,
                jsonSchema=schema.json_schema_value(),
            ),
            "budget": StepBudget(
                maxModelCalls=budget.max_model_calls,
                maxInputTokens=budget.max_input_tokens,
                maxPromptCacheMissTokens=budget.max_prompt_cache_miss_tokens,
                maxCompletionTokens=budget.max_completion_tokens,
                maxReasoningTokens=budget.max_reasoning_tokens,
                maxVisibleOutputTokens=budget.max_visible_output_tokens,
                maxCostMicros=budget.max_cost_micros,
                maxWallClockSeconds=budget.max_wall_clock_seconds,
                maxProviderRetries=budget.max_provider_retries,
                maxProtocolCorrections=budget.max_protocol_corrections,
            ),
        }
    )
    return rehash_request(request)


async def _attempt():
    return 1


def _executor(model=None):
    return StatelessExecutionStepExecutor(
        model or RecordingModel(), max_output_tokens=40000, retry_base_seconds=0
    )


@pytest.mark.parametrize("operation", SHORT_MEDIUM_HANDLERS)
@pytest.mark.asyncio
async def test_four_operations_call_once_and_materialize_full_text_hash(operation):
    request = short_request(operation)
    field = (
        "replacement"
        if operation == "replace_selection"
        else "text"
        if operation == "full_check"
        else "content"
    )
    text = " \n😀完整输出\n "
    result = ModelTurnResult(
        content="",
        toolCalls=[],
        structuredOutput={field: text},
        finishReason="stop",
        usage=ModelUsage(promptTokens=100, completionTokens=20, totalTokens=120),
    )
    model = RecordingModel(result=result)
    executor = _executor(model)
    resolved = executor.resolve(request, _registry())
    model_request = executor.build_model_request(request, resolved)
    outcome = await executor.call_provider(
        request, model_request, begin_attempt=_attempt, cancel_event=asyncio.Event()
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)
    assert terminal.output == {field: text, f"{field}Sha256": _hash(text)}
    assert len(model.requests) == 1
    assert model_request.tools == []
    assert model_request.policy.thinkingMode == (
        "disabled" if operation == "full_check" else "enabled"
    )
    assert request.purpose == "generation"
    assert request.artifactId is None


@pytest.mark.parametrize("operation", SHORT_MEDIUM_HANDLERS)
def test_disabled_catalog_still_rejects_without_provider(operation):
    model = RecordingModel()
    with pytest.raises(ExecutionCapabilityError):
        _executor(model).resolve(short_request(operation), _disabled_registry())
    assert model.requests == []


@pytest.mark.parametrize("operation", SHORT_MEDIUM_HANDLERS)
@pytest.mark.parametrize("bad_value", ["", 1, None])
@pytest.mark.asyncio
async def test_missing_empty_or_non_text_provider_output_is_rejected(operation, bad_value):
    request = short_request(operation)
    field = (
        "replacement"
        if operation == "replace_selection"
        else "text"
        if operation == "full_check"
        else "content"
    )
    model = RecordingModel(
        result=ModelTurnResult(
            content="",
            toolCalls=[],
            structuredOutput={field: bad_value},
            finishReason="stop",
            usage=ModelUsage(promptTokens=100, completionTokens=20, totalTokens=120),
        )
    )
    executor = _executor(model)
    resolved = executor.resolve(request, _registry())
    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_attempt,
        cancel_event=asyncio.Event(),
    )
    assert (
        executor.terminal_from_outcome(request, resolved, outcome).errorCode
        == "MODEL_OUTPUT_SCHEMA_INVALID"
    )


@pytest.mark.parametrize("operation", SHORT_MEDIUM_HANDLERS)
@pytest.mark.asyncio
async def test_pure_whitespace_keeps_existing_minimum_one_semantics(operation):
    request = short_request(operation)
    field = (
        "replacement"
        if operation == "replace_selection"
        else "text"
        if operation == "full_check"
        else "content"
    )
    model = RecordingModel(
        result=ModelTurnResult(
            content="",
            toolCalls=[],
            structuredOutput={field: " \n "},
            finishReason="stop",
            usage=ModelUsage(promptTokens=100, completionTokens=20, totalTokens=120),
        )
    )
    executor = _executor(model)
    resolved = executor.resolve(request, _registry())
    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_attempt,
        cancel_event=asyncio.Event(),
    )
    assert executor.terminal_from_outcome(request, resolved, outcome).output[field] == " \n "


def test_complete_input_over_budget_fails_without_truncation_or_provider():
    source = _context("generate_outline", 15000)
    source["sourceText"] = "完整素材" * 40000
    request = short_request(context=source)
    model = RecordingModel()
    executor = _executor(model)
    resolved = executor.resolve(request, _registry())
    with pytest.raises(ExecutionCapabilityError, match="完整模型输入"):
        executor.build_model_request(request, resolved)
    assert request.evidenceBundle.items[0].contentJson["sourceText"] == source["sourceText"]
    assert model.requests == []


@pytest.mark.parametrize(("target", "count"), [(15000, 1), (15001, 2), (80000, 6)])
def test_segment_boundaries_and_complete_prefix_survive_request(target, count):
    prior = tuple(
        (index, f"producer-{index}", f"第{index}段\n" + "原文😀" * 3000)
        for index in range(count - 1)
    )
    request = short_request("generate_manuscript", target=target, index=count - 1, prior=prior)
    executor = _executor()
    resolved = executor.resolve(request, _registry())
    envelope = json.loads(executor.build_model_request(request, resolved).messages[1].content)
    assert envelope["input"] == {"segmentIndex": count - 1, "segmentCount": count}
    items = envelope["evidenceBundle"]["items"]
    assert [item["contentJson"]["content"] for item in items[1:]] == [row[2] for row in prior]
    assert items[0]["contentJson"] == _context("generate_manuscript", target)
    prompt = resolved.prompt_profile.system_prompt
    for phrase in [
        "空分隔符",
        "不重复已完成内容",
        "完整 baseContent",
        "sourceKind=opening",
        "sourceKind=ending",
        "不截断场景",
    ]:
        assert phrase in prompt


@pytest.mark.parametrize(
    "prior",
    [(), ((1, "p-1", "缺失"),), ((0, "step-1", "自己"),), ((0, "p-1", "一"), (1, "p-1", "二"))],
)
def test_missing_reordered_or_invalid_producer_prefix_rejected(prior):
    request = short_request(
        "generate_manuscript", target=80000, index=max(1, len(prior)), prior=prior
    )
    with pytest.raises(ExecutionCapabilityError):
        _executor().resolve(request, _registry())


@pytest.mark.parametrize(
    ("finish", "code"),
    [
        ("length", "MODEL_OUTPUT_TRUNCATED"),
        ("content_filter", "MODEL_OUTPUT_FILTERED"),
        ("tool_calls", "MODEL_FINISH_REASON_INVALID"),
        ("unknown", "MODEL_FINISH_REASON_INVALID"),
    ],
)
@pytest.mark.asyncio
async def test_bad_finish_never_becomes_a_continuation(finish, code):
    request = short_request("generate_manuscript")
    model = RecordingModel(
        result=ModelTurnResult(
            content="",
            toolCalls=[],
            structuredOutput={"content": "半段"},
            finishReason=finish,
            usage=ModelUsage(promptTokens=100, completionTokens=20, totalTokens=120),
        )
    )
    executor = _executor(model)
    resolved = executor.resolve(request, _registry())
    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_attempt,
        cancel_event=asyncio.Event(),
    )
    assert executor.terminal_from_outcome(request, resolved, outcome).errorCode == code
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_cancel_before_provider_is_zero_call_and_retained_recovery_is_exact():
    request = short_request(
        "generate_manuscript", target=15001, index=1, prior=((0, "producer-0", "完整首段"),)
    )
    executor = _executor()
    retained = request.model_copy(update={"dispatchMode": "pending_recovery"})
    resolved = executor.resolve(retained, load_execution_registry(environment="test"))
    cancel = asyncio.Event()
    cancel.set()
    outcome = await executor.call_provider(
        retained,
        executor.build_model_request(retained, resolved),
        begin_attempt=_attempt,
        cancel_event=cancel,
    )
    assert outcome.provider_attempts == 0
    assert (
        executor.terminal_from_outcome(
            retained, resolved, outcome, cancel_request_id="cancel-1"
        ).errorCode
        == "RUN_CANCELLED"
    )


def test_budget_six_steps_fit_run_even_when_every_input_is_uncached():
    for operation in SHORT_MEDIUM_HANDLERS:
        resolved = _registry().resolve("short_medium", operation)
        step, run = resolved.generator_step_budget, resolved.operation.run_budget
        assert step.max_input_tokens == step.max_prompt_cache_miss_tokens
        count = 6 if operation == "generate_manuscript" else 1
        for field in (
            "max_model_calls",
            "max_input_tokens",
            "max_prompt_cache_miss_tokens",
            "max_completion_tokens",
            "max_reasoning_tokens",
            "max_visible_output_tokens",
            "max_cost_micros",
            "max_wall_clock_seconds",
        ):
            assert getattr(step, field) * count <= getattr(run, field)


def _short_service(journal, model, callbacks):
    return ExecutionService(
        journal=journal,
        registry=_registry(),
        executor=_executor(model),
        callbacks=callbacks,
        callback_retry_base_seconds=0,
        terminal_callback_attempts=3,
    )


@pytest.mark.asyncio
async def test_completed_segment_replays_after_service_restart_without_model():
    request = short_request("generate_manuscript", target=15001)
    output = ModelTurnResult(
        content="",
        toolCalls=[],
        structuredOutput={"content": " 完整首段😀\n"},
        finishReason="stop",
        usage=ModelUsage(promptTokens=100, completionTokens=20, totalTokens=120),
    )
    model = RecordingModel(result=output)
    journal = _journal(prefix="test:short:completed-replay")
    callbacks = RecordingCallbacks(terminal_retryable_failures=2)
    service = _short_service(journal, model, callbacks)
    await service.submit(request)
    await service.wait_idle()
    assert len(model.requests) == 1
    assert callbacks.terminal_attempts == 3
    assert len(callbacks.results) == 1
    persisted = await journal.require(request.stepId)
    assert persisted.state == "result"
    restarted_model = RecordingModel()
    restarted_callbacks = RecordingCallbacks()
    restarted = _short_service(journal, restarted_model, restarted_callbacks)
    await restarted.submit(request)
    await restarted.wait_idle()
    assert restarted_model.requests == []
    assert (await journal.require(request.stepId)).terminal == persisted.terminal


@pytest.mark.asyncio
async def test_missing_running_journal_is_unknown_without_regenerating_prior_segment():
    request = short_request(
        "generate_manuscript", target=15001, index=1, prior=((0, "producer-0", "已持久化首段"),)
    )
    request = request.model_copy(update={"dispatchMode": "running_recovery"})
    model, callbacks = RecordingModel(), RecordingCallbacks()
    journal = _journal(prefix="test:short:unknown-recovery")
    service = _short_service(journal, model, callbacks)
    await service.submit(request)
    await service.wait_idle()
    assert model.requests == []
    assert callbacks.failures[0].errorCode == "MODEL_OUTCOME_UNKNOWN"
    assert callbacks.failures[0].outcomeUnknown is True


@pytest.mark.asyncio
async def test_cancel_during_provider_uses_existing_journal_fence_and_unknown_usage():
    request = short_request("generate_manuscript")
    model, callbacks = RecordingModel(block=True), RecordingCallbacks()
    journal = _journal(prefix="test:short:cancel-running")
    service = _short_service(journal, model, callbacks)
    await service.submit(request)
    for _ in range(100):
        if model.requests:
            break
        await asyncio.sleep(0.001)
    assert len(model.requests) == 1
    await service.cancel(execution_cancel(request))
    await service.wait_idle()
    assert callbacks.results == []
    assert callbacks.failures[0].errorCode == "RUN_CANCELLED"
    assert callbacks.failures[0].cancelRequestId == "cancel-1"
    assert callbacks.failures[0].usage.providerAttempts == 1
    assert callbacks.failures[0].usage.usageStatus == "unknown"
    assert (await journal.require(request.stepId)).state == "failure"
