"""一致性终检只消费冻结正文，每个显式纠正拥有独立模型边界。"""

import asyncio
import hashlib
import json
from dataclasses import replace
from types import MappingProxyType

import httpx
import pytest
from inkforge_agents.config import Settings
from inkforge_agents.execution.executor import (
    ExecutionCapabilityError,
    ProviderModelRuntimeAdapter,
    StatelessExecutionStepExecutor,
)
from inkforge_agents.execution.registry import load_execution_registry
from inkforge_agents.execution.service import ExecutionService
from inkforge_agents.providers.base import ModelToolCall, ModelTurnResult, ModelUsage
from inkforge_agents.providers.deepseek_v4 import DeepSeekV4Provider
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
from inkforge_contracts.quality_execution import QualityContextV2, QualityStepInput
from pydantic import ValidationError

from .support import execution_request, rehash_request
from .test_executor import RecordingModel
from .test_service import RecordingCallbacks, _journal


def quality_registry():
    registry = load_execution_registry(environment="test")
    return replace(
        registry,
        operations=MappingProxyType(
            {
                key: replace(value, v2_enabled=True) if key == "quality.consistency" else value
                for key, value in registry.operations.items()
            }
        ),
    )


def quality_request(*, correction=False):
    registry = quality_registry()
    operation = registry.resolve("quality", "consistency")
    system = registry.resolve_system_purpose("protocol_correction", "quality")
    profile = system.model_profile if correction else operation.generator_profile
    schema = operation.output_schema
    budget = system.step_budget if correction else operation.generator_step_budget
    context = {
        "checkId": "check-1",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "chapterContent": " 正文😀\n",
        "chapterContentSha256": hashlib.sha256(" 正文😀\n".encode()).hexdigest(),
        "sourceUpdatedAt": "2026-09-05T01:00:00Z",
        "message": None,
        "sourceTaskId": None,
    }
    item = EvidenceItem(
        id="quality-item",
        bundleId="quality-bundle",
        ordinal=1,
        resourceType="quality_context",
        resourceId="check-1",
        exists=True,
        contentType="json",
        contentJson=context,
        contentSha256=canonical_execution_sha256(context),
        byteCount=len(canonical_execution_json_bytes(context)),
    )
    manifest = EvidenceManifest(
        bundleId=item.bundleId,
        bundleVersion=1,
        itemCount=1,
        items=[
            EvidenceManifestItem(
                itemId=item.id,
                **item.model_dump(exclude={"id", "bundleId", "contentJson", "contentText"}),
            )
        ],
    )
    bundle = EvidenceBundle(
        id=item.bundleId,
        runId="run-1",
        version=1,
        policyVersion="evidence.quality.consistency.v1",
        manifest=manifest,
        manifestSha256=canonical_execution_sha256(
            manifest.model_dump(mode="json", exclude_none=True)
        ),
        totalBytes=item.byteCount,
        items=[item],
    )
    input_value = {"userInstruction": "检查本章一致性"}
    if correction:
        input_value.update(
            failedStepId="generation-1",
            failedResultHash="a" * 64,
            failureCode="MODEL_TOOL_PROTOCOL_CORRECTION_REQUIRED",
        )
    return rehash_request(
        execution_request().model_copy(
            update={
                "workflow": "quality",
                "operation": "consistency",
                "purpose": "protocol_correction" if correction else "generation",
                "lane": "interactive",
                "input": input_value,
                "evidenceBundle": bundle,
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
    )


class QualityModel(RecordingModel):
    def supports_structured_output(self, route):
        return route == "quality_strict_tool_v1"


def report():
    return {
        "scores": {
            key: 80
            for key in [
                "characterConsistency",
                "worldRuleConsistency",
                "timelineConsistency",
                "causalityConsistency",
                "foreshadowingConsistency",
            ]
        },
        "qualityGate": "revise",
        "issues": [],
        "report": " 完整报告😀\n",
        "rewriteBrief": None,
    }


def result(**changes):
    value = ModelTurnResult(
        content="不接受供应商旁白",
        toolCalls=[ModelToolCall(id="call-1", name="submit_quality_report", arguments=report())],
        finishReason="tool_calls",
        usage=ModelUsage(promptTokens=100, cachedTokens=20, completionTokens=20, totalTokens=120),
    )
    return value.model_copy(update=changes)


async def execute(response, *, correction=False):
    request = quality_request(correction=correction)
    model = QualityModel(result=response)
    executor = StatelessExecutionStepExecutor(model, max_output_tokens=10000, retry_base_seconds=0)
    resolved = executor.resolve(request, quality_registry())
    model_request = executor.build_model_request(request, resolved)

    async def attempt():
        return 1

    outcome = await executor.call_provider(
        request, model_request, begin_attempt=attempt, cancel_event=asyncio.Event()
    )
    return executor.terminal_from_outcome(request, resolved, outcome), model


@pytest.mark.asyncio
@pytest.mark.parametrize("correction", [False, True])
async def test_quality_one_call_returns_original_report_without_reviewer(correction):
    terminal, model = await execute(result(), correction=correction)
    assert terminal.resultKind == "output"
    assert terminal.output == report()
    assert terminal.usage.inputTokens == 100
    assert terminal.usage.protocolCorrections == 0
    assert len(model.requests) == 1
    request = model.requests[0]
    assert request.structuredOutput is None
    assert [(tool.name, tool.strict) for tool in request.tools] == [("submit_quality_report", True)]
    assert request.policy.thinkingMode == "disabled"
    assert terminal.resolvedModel.structuredOutputRoute == "quality_strict_tool_v1"
    assert (
        json.loads(request.messages[-1].content)["evidenceBundle"]["items"][0]["contentJson"][
            "chapterContent"
        ]
        == " 正文😀\n"
    )


@pytest.mark.asyncio
async def test_quality_invalid_arguments_requests_separate_correction_without_persisting_raw():
    invalid = result(
        toolCalls=[],
        invalidToolCallCount=1,
        invalidToolCallNames=["submit_quality_report"],
        invalidToolCallCodes=["json_decode_error"],
        invalidToolCallArgumentCharacterCounts=[999],
    )
    first, model = await execute(invalid)
    assert first.errorCode == "MODEL_TOOL_PROTOCOL_CORRECTION_REQUIRED"
    assert first.retryable is False and first.outcomeUnknown is False
    assert first.usage.inputTokens == 100
    assert len(model.requests) == 1
    assert "不接受供应商旁白" not in first.model_dump_json()
    second, model = await execute(invalid, correction=True)
    assert second.errorCode == "MODEL_TOOL_PROTOCOL_RECOVERY_FAILED"
    assert len(model.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "finish", ["length", "content_filter", "insufficient_system_resource", "unknown", "stop"]
)
async def test_quality_incomplete_or_conflicting_completion_never_requests_correction(finish):
    terminal, _ = await execute(result(finishReason=finish))
    assert terminal.errorCode != "MODEL_TOOL_PROTOCOL_CORRECTION_REQUIRED"


@pytest.mark.asyncio
async def test_quality_shared_pydantic_preserves_numeric_conversion_and_rejects_blank_report():
    converted = report()
    converted["scores"]["characterConsistency"] = "81"
    terminal, _ = await execute(
        result(
            toolCalls=[ModelToolCall(id="one", name="submit_quality_report", arguments=converted)]
        )
    )
    assert terminal.output["scores"]["characterConsistency"] == 81
    converted["report"] = " \n"
    failed, _ = await execute(
        result(
            toolCalls=[ModelToolCall(id="one", name="submit_quality_report", arguments=converted)]
        )
    )
    assert failed.errorCode == "MODEL_TOOL_PROTOCOL_CORRECTION_REQUIRED"


def test_quality_frozen_context_and_correction_binding_are_strict():
    context = quality_request().evidenceBundle.items[0].contentJson
    assert QualityContextV2.model_validate(context).chapterContent == " 正文😀\n"
    with pytest.raises(ValidationError):
        QualityContextV2.model_validate(context | {"chapterContent": "改变"})
    with pytest.raises(ValidationError):
        QualityStepInput.model_validate({"userInstruction": "检查", "failedStepId": "one"})
    executor = StatelessExecutionStepExecutor(QualityModel(), max_output_tokens=10000)
    registry = quality_registry()
    registry = replace(
        registry,
        operations=MappingProxyType(
            {
                key: replace(value, v2_enabled=False) if key == "quality.consistency" else value
                for key, value in registry.operations.items()
            }
        ),
    )
    with pytest.raises(ExecutionCapabilityError):
        executor.resolve(quality_request(), registry)


@pytest.mark.asyncio
async def test_quality_unreliable_usage_never_authorizes_another_step():
    for usage in [
        ModelUsage(promptTokens=1, cachedTokens=2, completionTokens=20, totalTokens=21),
        ModelUsage(promptTokens=100, completionTokens=20, totalTokens=121),
    ]:
        failed, _ = await execute(result(usage=usage, toolCalls=[]))
        assert failed.errorCode == "MODEL_USAGE_INVALID"


@pytest.mark.asyncio
async def test_quality_deterministic_closure_is_counted_without_extra_model_call():
    terminal, model = await execute(
        result(
            recoveredToolCallCount=1,
            recoveredToolCallCodes=["append_container_closers"],
            recoveredToolCallAppendedContainerCounts=[2],
        )
    )
    assert terminal.resultKind == "output"
    assert terminal.usage.protocolCorrections == 1
    assert len(model.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("correction", [False, True])
async def test_quality_terminal_journal_replay_does_not_repeat_provider(correction):
    request = quality_request(correction=correction)
    model = QualityModel(result=result())
    callbacks = RecordingCallbacks(terminal_retryable_failures=2)
    journal = _journal(prefix=f"test:quality:terminal:{correction}")
    service = ExecutionService(
        journal=journal,
        registry=quality_registry(),
        executor=StatelessExecutionStepExecutor(model, max_output_tokens=10000),
        callbacks=callbacks,
        callback_retry_base_seconds=0,
        terminal_callback_attempts=3,
    )
    await service.submit(request)
    await service.wait_idle()
    assert len(model.requests) == 1
    assert len(callbacks.results) == 1
    frozen = (await journal.require(request.stepId)).terminal
    second_model = QualityModel()
    restarted = ExecutionService(
        journal=journal,
        registry=quality_registry(),
        executor=StatelessExecutionStepExecutor(second_model, max_output_tokens=10000),
        callbacks=RecordingCallbacks(),
        callback_retry_base_seconds=0,
    )
    await restarted.submit(request)
    await restarted.wait_idle()
    assert second_model.requests == []
    assert (await journal.require(request.stepId)).terminal == frozen


@pytest.mark.asyncio
async def test_quality_missing_running_correction_journal_fails_unknown_without_model():
    request = quality_request(correction=True).model_copy(
        update={"dispatchMode": "running_recovery"}
    )
    model, callbacks = QualityModel(), RecordingCallbacks()
    service = ExecutionService(
        journal=_journal(prefix="test:quality:missing"),
        registry=quality_registry(),
        executor=StatelessExecutionStepExecutor(model, max_output_tokens=10000),
        callbacks=callbacks,
    )
    await service.submit(request)
    await service.wait_idle()
    assert model.requests == []
    assert callbacks.failures[0].errorCode == "MODEL_OUTCOME_UNKNOWN"


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", [False, True])
async def test_quality_executor_uses_beta_http_once_and_never_serializes_invalid_arguments(
    malformed,
):
    calls = []
    raw = '{"report":"禁止持久化的坏参数' if malformed else json.dumps(report(), ensure_ascii=False)

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": "不可持久化的供应商旁白",
                            "tool_calls": [
                                {
                                    "id": "quality-call-1",
                                    "type": "function",
                                    "function": {"name": "submit_quality_report", "arguments": raw},
                                }
                            ],
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "prompt_cache_hit_tokens": 0,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = DeepSeekV4Provider(
            Settings.model_validate(
                {
                    "environment": "test",
                    "model_provider": "openai_compatible",
                    "openai_compatibility_profile": "deepseek_v4",
                    "openai_api_key": "quality-test-key",
                    "openai_base_url": "https://api.deepseek.com",
                    "openai_model": "deepseek-v4-flash",
                }
            ),
            client=client,
        )
        executor = StatelessExecutionStepExecutor(
            ProviderModelRuntimeAdapter(provider), max_output_tokens=10000
        )
        request = quality_request()
        resolved = executor.resolve(request, quality_registry())

        async def attempt():
            return 1

        outcome = await executor.call_provider(
            request,
            executor.build_model_request(request, resolved),
            begin_attempt=attempt,
            cancel_event=asyncio.Event(),
        )
        terminal = executor.terminal_from_outcome(request, resolved, outcome)
    assert len(calls) == 1
    assert str(calls[0].url) == "https://api.deepseek.com/beta/chat/completions"
    wire = json.loads(calls[0].content)
    assert "response_format" not in wire
    assert wire["tool_choice"]["function"]["name"] == "submit_quality_report"
    assert wire["tools"][0]["function"]["strict"] is True
    assert terminal.resolvedModel.endpointProfile == "endpoint.deepseek-strict-official.v1"
    if malformed:
        assert terminal.errorCode == "MODEL_TOOL_PROTOCOL_CORRECTION_REQUIRED"
    else:
        assert terminal.output == report()
    assert "禁止持久化" not in terminal.model_dump_json()
    assert "不可持久化" not in terminal.model_dump_json()


def test_quality_pending_recovery_uses_retained_assets_even_when_current_system_is_retired():
    request = quality_request(correction=True).model_copy(
        update={"dispatchMode": "pending_recovery"}
    )
    registry = load_execution_registry(environment="test")
    registry = replace(
        registry,
        system_purposes=MappingProxyType(
            {
                key: replace(value, supported=False)
                for key, value in registry.system_purposes.items()
            }
        ),
    )
    executor = StatelessExecutionStepExecutor(QualityModel(), max_output_tokens=10000)
    resolved = executor.resolve(request, registry)
    assert resolved.purpose == "protocol_correction"
    assert resolved.profile.key == "system.quality_protocol_corrector.v2"
