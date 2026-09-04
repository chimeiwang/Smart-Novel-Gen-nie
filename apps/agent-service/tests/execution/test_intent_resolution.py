from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType

import pytest
from inkforge_agents.execution.executor import ExecutionCapabilityError, ProviderCallOutcome
from inkforge_agents.execution.registry import load_execution_registry
from inkforge_agents.providers.base import ModelTurnResult, ModelUsage, ModelUsageDiagnostics
from inkforge_contracts.execution import (
    ModelProfileRef,
    OutputSchemaRef,
    PromptProfileRef,
    StepBudget,
)

from .support import execution_request, rehash_request
from .test_chapter_plan import _context_item, _with_evidence
from .test_executor import RecordingModel, _executor, _one_attempt


def _context():
    return {
        "workflow": "long_serial",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "chapterTitle": "当前章节😀",
        "availableOperations": [
            {
                "operation": operation,
                "description": description,
                "targetType": "chapter",
                "scopeKind": "chapter",
            }
            for operation, description in [
                ("answer_question", "回答章节问题"),
                ("plan_chapter", "规划章节"),
                ("write_chapter", "生成完整正文"),
            ]
        ],
    }


def _request(*, mode="initial", clarifications=None, context=None):
    registry = load_execution_registry(environment="test")
    resolved = registry.resolve_system_purpose("resolve_intent", "long_serial")
    profile, schema, budget = resolved.model_profile, resolved.output_schema, resolved.step_budget
    base = execution_request()
    candidate = base.model_copy(
        update={
            "operation": None,
            "purpose": "resolve_intent",
            "lane": "interactive",
            "dispatchMode": mode,
            "input": {
                "userInstruction": "  请帮助处理当前章节😀\n",
                "clarifications": clarifications or [],
            },
            "artifactId": None,
            "artifactRevision": None,
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
            "evidenceBundle": base.evidenceBundle.model_copy(
                update={"policyVersion": "evidence.system.intent.v1"}
            ),
        }
    )
    return _with_evidence(
        candidate,
        [
            _context_item(
                resourceType="intent_context",
                metadata={"role": "intent_context"},
                contentJson=context or _context(),
            )
        ],
    )


def _output(operation="answer_question"):
    return {
        "workflow": "long_serial",
        "operation": operation,
        "confidence": 0.96,
        "targetType": None,
        "targetId": None,
        "scopeKind": None,
        "arguments": {},
        "clarification": None,
    }


def _result(output, *, finish="stop", input_tokens=1000):
    return ModelTurnResult(
        content="",
        toolCalls=[],
        structuredOutput=output,
        finishReason=finish,
        rawFinishReason=finish,
        usage=ModelUsage(
            promptTokens=input_tokens,
            cachedTokens=0,
            completionTokens=100,
            totalTokens=input_tokens + 100,
        ),
        diagnostics=ModelUsageDiagnostics(reasoningTokens=0, promptCacheMissTokens=input_tokens),
    )


def test_intent_system_has_complete_disabled_reasoning_assets_and_exact_budget():
    resolved = load_execution_registry(environment="test").resolve_system_purpose(
        "resolve_intent", "long_serial"
    )
    assert resolved.definition.workflows == ("long_serial",)
    assert resolved.model_profile.key == "system.intent_resolver.v1"
    assert resolved.model_profile.reasoning_mode == "disabled"
    assert (
        resolved.step_budget.max_input_tokens
        == resolved.step_budget.max_prompt_cache_miss_tokens
        == 8000
    )
    assert (
        resolved.step_budget.max_completion_tokens
        == resolved.step_budget.max_visible_output_tokens
        == 1000
    )
    assert (
        resolved.step_budget.max_reasoning_tokens
        == resolved.step_budget.max_protocol_corrections
        == 0
    )
    assert resolved.step_budget.max_cost_micros == 50_000
    assert resolved.step_budget.max_wall_clock_seconds == 30
    assert resolved.step_budget.max_provider_retries == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["initial", "pending_recovery", "running_recovery"])
@pytest.mark.parametrize("operation", ["answer_question", "plan_chapter", "write_chapter", None])
async def test_intent_uses_one_no_tool_call_and_returns_proposed_command(mode, operation):
    request = _request(
        mode=mode,
        clarifications=[
            {
                "decisionStepId": "decision-1",
                "prompt": "要规划还是正文？",
                "userMessage": "  请保留完整回答😀\n",
            }
        ],
    )
    output = (
        _output(operation)
        if operation
        else {
            "workflow": None,
            "operation": None,
            "confidence": 0.2,
            "clarification": {"code": "intent.unclear", "prompt": "请明确希望得到规划还是正文。"},
        }
    )
    model = RecordingModel(result=_result(output))
    executor = _executor(model)
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    model_request = executor.build_model_request(request, resolved)
    outcome = await executor.call_provider(
        request, model_request, begin_attempt=_one_attempt, cancel_event=asyncio.Event()
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)
    assert terminal.resultKind == "proposed_command"
    assert terminal.proposedCommand.operation == operation
    assert terminal.output is None and terminal.evaluation is None
    assert terminal.usage.providerAttempts == len(model.requests) == 1
    assert model_request.tools == [] and model_request.policy.thinkingMode == "disabled"
    assert model_request.maxOutputTokens == 1000
    envelope = json.loads(model_request.messages[1].content)
    assert envelope["operation"] is None and envelope["input"] == request.input


@pytest.mark.parametrize("mode", ["initial", "pending_recovery", "running_recovery"])
def test_intent_retained_rejects_profile_budget_scope_and_input_tampering(mode):
    request = _request(mode=mode)
    executor = _executor(RecordingModel())
    registry = load_execution_registry(environment="test")
    mutations = [
        {"operation": "answer_question"},
        {"workflow": "quality"},
        {"lane": "creative"},
        {"artifactId": "artifact-1", "artifactRevision": 1},
        {"input": {"userInstruction": "文本", "extra": "禁止"}},
        {"budget": request.budget.model_copy(update={"maxProtocolCorrections": 1})},
        {"modelProfile": request.modelProfile.model_copy(update={"reasoningMode": "bounded"})},
        {"outputSchema": request.outputSchema.model_copy(update={"sha256": "a" * 64})},
    ]
    for update in mutations:
        with pytest.raises(ExecutionCapabilityError):
            executor.resolve(request.model_copy(update=update), registry)


@pytest.mark.parametrize("corruption", ["target", "args", "operation", "extra", "missing", "both"])
def test_intent_invalid_output_cannot_become_business_command(corruption):
    request = _request()
    output = _output()
    if corruption == "target":
        output |= {"targetType": "chapter", "targetId": "other"}
    elif corruption == "args":
        output["arguments"] = {"userInstruction": "模型改写指令"}
    elif corruption == "operation":
        output["operation"] = "create_lore"
    elif corruption == "extra":
        output["content"] = "模型不能生成正文"
    elif corruption == "missing":
        output.pop("confidence")
    else:
        output["clarification"] = {"code": "intent.unclear", "prompt": "同时夹带问题"}
    executor = _executor(RecordingModel())
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    terminal = executor.terminal_from_outcome(
        request, resolved, ProviderCallOutcome(_result(output), 1, 1)
    )
    assert terminal.errorCategory == "validation"


def test_intent_recovery_keeps_retained_contract_but_initial_rejects_retired_purpose():
    registry = load_execution_registry(environment="test")
    disabled = replace(
        registry,
        system_purposes=MappingProxyType(
            {
                **registry.system_purposes,
                "resolve_intent": replace(
                    registry.system_purposes["resolve_intent"], supported=False
                ),
            }
        ),
    )
    executor = _executor(RecordingModel())
    with pytest.raises(ExecutionCapabilityError):
        executor.resolve(_request(), disabled)
    assert executor.resolve(_request(mode="pending_recovery"), disabled).purpose == "resolve_intent"


@pytest.mark.parametrize("mode", ["pending_recovery", "running_recovery"])
def test_intent_recovery_ignores_new_purpose_references_but_requires_retained_tuple(mode):
    registry = load_execution_registry(environment="test")
    updated = replace(
        registry,
        system_purposes=MappingProxyType(
            {
                **registry.system_purposes,
                "resolve_intent": replace(
                    registry.system_purposes["resolve_intent"],
                    supported=False,
                    model_profile_key="plot.chapter_plan.v1",
                    output_schema_key="output.beat_plan.v1",
                    step_budget_key="step_budget.long_serial.plan_chapter.generator.v1",
                ),
            }
        ),
    )
    executor = _executor(RecordingModel())
    assert executor.resolve(_request(mode=mode), updated).purpose == "resolve_intent"
    removed = replace(
        updated,
        profiles=MappingProxyType(
            {
                key: value
                for key, value in updated.profiles.items()
                if key != "system.intent_resolver.v1"
            }
        ),
    )
    with pytest.raises(ExecutionCapabilityError):
        executor.resolve(_request(mode=mode), removed)


@pytest.mark.parametrize("mode", ["initial", "pending_recovery", "running_recovery"])
@pytest.mark.parametrize(
    "corruption", ["novel", "chapter", "workflow", "extra", "duplicate", "disabled"]
)
def test_intent_context_is_exact_owned_and_only_current_capabilities(mode, corruption):
    context = deepcopy(_context())
    if corruption == "novel":
        context["novelId"] = "other-novel"
    elif corruption == "chapter":
        context["chapterId"] = "other-chapter"
    elif corruption == "workflow":
        context["workflow"] = "quality"
    elif corruption == "extra":
        context["content"] = "不能夹带正文"
    elif corruption == "duplicate":
        context["availableOperations"][1] = context["availableOperations"][0]
    else:
        context["availableOperations"][0]["operation"] = "create_lore"
    with pytest.raises(ExecutionCapabilityError):
        _executor(RecordingModel()).resolve(
            _request(mode=mode, context=context), load_execution_registry(environment="test")
        )


def test_intent_result_preserves_clarification_and_rejects_unavailable_choice_or_workflow():
    context = _context()
    context["availableOperations"] = context["availableOperations"][:1]
    request = _request(context=context)
    executor = _executor(RecordingModel())
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    for output in [_output("plan_chapter"), _output() | {"workflow": "quality"}]:
        terminal = executor.terminal_from_outcome(
            request, resolved, ProviderCallOutcome(_result(output), 1, 1)
        )
        assert terminal.errorCategory == "validation"
    prompt = "  请问需要哪种处理？\r\n😀  "
    terminal = executor.terminal_from_outcome(
        request,
        resolved,
        ProviderCallOutcome(
            _result(
                {"confidence": 0.1, "clarification": {"code": "intent.unclear", "prompt": prompt}}
            ),
            1,
            1,
        ),
    )
    assert terminal.proposedCommand.clarification.prompt == prompt


def test_intent_exact_deployment_tuple_is_required_for_initial_and_recovery():
    for mode in ("initial", "pending_recovery", "running_recovery"):
        with pytest.raises(ExecutionCapabilityError):
            _executor(RecordingModel()).resolve(
                _request(mode=mode), load_execution_registry(environment="production")
            )
        resolved = _executor(RecordingModel(supports_idempotency=False)).resolve(
            _request(mode=mode), load_execution_registry(environment="production")
        )
        assert resolved.resolved_model.reasoningMode == "disabled"
        assert resolved.resolved_model.model == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_intent_service_preserves_preparing_journal_duplicate_and_terminal_replay():
    from .test_service import RecordingCallbacks, _journal, _service
    from .test_service import RecordingModel as ServiceModel

    journal = _journal(prefix="test:intent:duplicate")
    model = ServiceModel()
    callbacks = RecordingCallbacks(terminal_retryable_failures=2)
    service = _service(journal=journal, model=model, callbacks=callbacks)
    request = rehash_request(
        _request().model_copy(
            update={"input": {"userInstruction": "【隔离意图:plan_chapter】", "clarifications": []}}
        )
    )
    first, duplicate = await asyncio.gather(service.submit(request), service.submit(request))
    await service.wait_idle()
    assert first.requestHash == duplicate.requestHash == request.requestHash
    assert [value.phase for value in callbacks.progress] == [
        "preparing",
        "waiting_provider",
        "validating",
        "reporting",
    ]
    assert len(model.requests) == len(callbacks.results) == 1
    assert callbacks.terminal_attempts == 3
    assert callbacks.results[0].proposedCommand.operation == "plan_chapter"
    assert (await journal.require(request.stepId)).callback_delivery == "delivered"
    restarted = _service(journal=journal, model=model, callbacks=callbacks)
    await restarted.submit(request)
    await restarted.wait_idle()
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_intent_running_recovery_missing_journal_never_repeats_provider():
    from .test_service import RecordingCallbacks, _journal, _service
    from .test_service import RecordingModel as ServiceModel

    model, callbacks = ServiceModel(), RecordingCallbacks()
    service = _service(
        journal=_journal(prefix="test:intent:missing"), model=model, callbacks=callbacks
    )
    await service.submit(_request(mode="running_recovery"))
    await service.wait_idle()
    assert model.requests == []
    assert callbacks.failures[0].errorCode == "MODEL_OUTCOME_UNKNOWN"


@pytest.mark.asyncio
async def test_intent_provider_before_cancel_and_large_input_are_zero_call():
    request = _request()
    model = RecordingModel()
    executor = _executor(model)
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    cancelled = asyncio.Event()
    cancelled.set()
    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_one_attempt,
        cancel_event=cancelled,
    )
    assert outcome.provider_attempts == 0 and model.requests == []
    oversized = rehash_request(
        request.model_copy(
            update={"input": {"userInstruction": "完整文本😀" * 2000, "clarifications": []}}
        )
    )
    with pytest.raises(ExecutionCapabilityError):
        executor.build_model_request(oversized, resolved)
