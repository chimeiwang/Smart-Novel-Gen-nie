"""文风画像保持逐节纯文本调用；完整来源、原始输出和 journal 不截断。"""

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
from inkforge_contracts.style_execution import StylePortraitContextV2, StylePortraitSectionOutput
from pydantic import ValidationError

from .support import execution_request, rehash_request
from .test_executor import RecordingModel
from .test_service import RecordingCallbacks, _journal


def portrait_registry(*, enabled=True):
    registry = load_execution_registry(environment="test")
    return replace(
        registry,
        operations=MappingProxyType(
            {
                key: replace(value, v2_enabled=enabled) if key == "style.portrait" else value
                for key, value in registry.operations.items()
            }
        ),
    )


def portrait_context(*, section=None):
    references = [
        {
            "referenceId": "ref-1",
            "filename": "素材一.txt",
            "charCount": 4,
            "content": "\ufeff 正文😀\r\n",
            "contentSha256": hashlib.sha256("\ufeff 正文😀\r\n".encode()).hexdigest(),
        },
        {
            "referenceId": "ref-2",
            "filename": "素材二.txt",
            "charCount": 2,
            "content": "\n 第二\n",
            "contentSha256": hashlib.sha256("\n 第二\n".encode()).hexdigest(),
        },
    ]
    source = "\n\n".join(
        f"参考资料：{value['filename']}\n\n{value['content']}" for value in references
    )
    return {
        "styleId": "style-1",
        "mode": "full" if section is None else "section",
        "section": section,
        "references": references,
        "originalCharCount": 6,
        "sourceTextSha256": hashlib.sha256(source.encode()).hexdigest(),
    }


def portrait_request(section="creativeMethodology", *, single=False, source=None):
    registry = portrait_registry()
    operation = registry.resolve("style", "portrait")
    profile, schema, budget = (
        operation.generator_profile,
        operation.output_schema,
        operation.generator_step_budget,
    )
    context = source or portrait_context(section=section if single else None)
    item = EvidenceItem(
        id="portrait-item",
        bundleId="portrait-bundle",
        ordinal=1,
        resourceType="style_portrait_context",
        resourceId="style-1",
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
        policyVersion="evidence.style.portrait.v1",
        manifest=manifest,
        manifestSha256=canonical_execution_sha256(
            manifest.model_dump(mode="json", exclude_none=True)
        ),
        totalBytes=item.byteCount,
        items=[item],
    )
    return rehash_request(
        execution_request().model_copy(
            update={
                "novelId": None,
                "workflow": "style",
                "operation": "portrait",
                "purpose": "generation",
                "lane": "batch_media",
                "input": {"section": section},
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


class PortraitModel(RecordingModel):
    def supports_structured_output(self, route):
        return route == "plain_text_v1"


def response(**changes):
    return ModelTurnResult(
        content=" \n完整画像😀\n ",
        toolCalls=[],
        finishReason="stop",
        usage=ModelUsage(promptTokens=100, cachedTokens=0, completionTokens=20, totalTokens=120),
    ).model_copy(update=changes)


async def execute(result, *, section="creativeMethodology", single=False):
    request = portrait_request(section, single=single)
    model = PortraitModel(result=result)
    executor = StatelessExecutionStepExecutor(model, max_output_tokens=10000, retry_base_seconds=0)
    resolved = executor.resolve(request, portrait_registry())

    async def attempt():
        return 1

    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=attempt,
        cancel_event=asyncio.Event(),
    )
    return executor.terminal_from_outcome(request, resolved, outcome), model


@pytest.mark.parametrize(
    "section",
    [
        "creativeMethodology",
        "uniqueMarkers",
        "generationStyle",
        "expressionFeatures",
        "styleTraits",
    ],
)
@pytest.mark.asyncio
async def test_each_section_is_one_plain_text_call_with_same_complete_source(section):
    terminal, model = await execute(response(), section=section)
    assert len(model.requests) == 1
    request = model.requests[0]
    assert (
        request.tools == []
        and request.structuredOutput is None
        and request.requiredToolName is None
    )
    assert request.policy.thinkingMode == "disabled"
    assert len(request.messages) == 2
    assert "outputSchema" not in request.messages[1].content
    assert request.messages[1].content.endswith(
        StylePortraitContextV2.model_validate(portrait_context()).source_text
    )
    assert terminal.output == {"content": " \n完整画像😀\n "}
    assert terminal.novelId is None
    assert '"novelId":null' in terminal.model_dump_json()
    assert terminal.usage.protocolCorrections == 0
    assert terminal.resolvedModel.structuredOutputRoute == "plain_text_v1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"finishReason": "length"},
        {"finishReason": "content_filter"},
        {"finishReason": "unknown"},
        {"finishReason": "tool_calls"},
        {"content": " \u0085\n "},
        {"toolCalls": [ModelToolCall(id="one", name="fake", arguments={})]},
        {
            "invalidToolCallCount": 1,
            "invalidToolCallNames": ["未知工具"],
            "invalidToolCallCodes": ["json_decode_error"],
            "invalidToolCallArgumentCharacterCounts": [10],
        },
    ],
)
async def test_incomplete_empty_or_tool_outputs_never_complete_or_correct(changes):
    terminal, model = await execute(response(**changes))
    assert terminal.errorCode != "MODEL_TOOL_PROTOCOL_CORRECTION_REQUIRED"
    assert terminal.retryable is False
    assert len(model.requests) == 1


def test_source_hash_order_metadata_count_and_original_python_whitespace_are_preserved():
    context = portrait_context()
    model = StylePortraitContextV2.model_validate(context)
    assert model.originalCharCount == 6
    assert "\ufeff 正文😀\r\n" in model.source_text
    for changes in [
        {"originalCharCount": 7},
        {"sourceTextSha256": "0" * 64},
        {"references": list(reversed(context["references"]))},
    ]:
        with pytest.raises(ValidationError):
            StylePortraitContextV2.model_validate(context | changes)
    assert StylePortraitSectionOutput(content="\ufeff").content == "\ufeff"
    with pytest.raises(ValidationError):
        StylePortraitSectionOutput(content=" \u0085\n")


def test_single_section_and_null_novel_binding_are_exact():
    request = portrait_request("uniqueMarkers", single=True)
    executor = StatelessExecutionStepExecutor(PortraitModel(), max_output_tokens=10000)
    for changes in [
        {"novelId": "style:style-1"},
        {"input": {"section": "styleTraits"}},
        {"purpose": "protocol_correction"},
        {"input": {"section": "uniqueMarkers", "content": "伪造"}},
    ]:
        with pytest.raises(ExecutionCapabilityError):
            executor.resolve(
                rehash_request(request.model_copy(update=changes)), portrait_registry()
            )
    with pytest.raises(ExecutionCapabilityError):
        executor.resolve(request, portrait_registry(enabled=False))
    retained = request.model_copy(update={"dispatchMode": "pending_recovery"})
    assert (
        executor.resolve(retained, portrait_registry(enabled=False)).profile.key
        == "style.portrait.v2"
    )


@pytest.mark.asyncio
async def test_completed_plain_text_replays_after_restart_without_provider():
    request = portrait_request()
    model, callbacks = (
        PortraitModel(result=response()),
        RecordingCallbacks(terminal_retryable_failures=2),
    )
    journal = _journal(prefix="test:portrait:replay")
    service = ExecutionService(
        journal=journal,
        registry=portrait_registry(),
        executor=StatelessExecutionStepExecutor(model, max_output_tokens=10000),
        callbacks=callbacks,
        callback_retry_base_seconds=0,
        terminal_callback_attempts=3,
    )
    await service.submit(request)
    await service.wait_idle()
    assert len(model.requests) == 1 and len(callbacks.results) == 1
    assert callbacks.results[0].novelId is None
    replay_model = PortraitModel()
    restarted = ExecutionService(
        journal=journal,
        registry=portrait_registry(),
        executor=StatelessExecutionStepExecutor(replay_model, max_output_tokens=10000),
        callbacks=RecordingCallbacks(),
    )
    await restarted.submit(request)
    await restarted.wait_idle()
    assert replay_model.requests == []


async def execute_deepseek_wire(responses):
    calls = []

    def respond(request):
        calls.append(request)
        response = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(response, Exception):
            raise response
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = DeepSeekV4Provider(
            Settings.model_validate(
                {
                    "environment": "test",
                    "model_provider": "openai_compatible",
                    "openai_compatibility_profile": "deepseek_v4",
                    "openai_api_key": "portrait-test-key",
                    "openai_base_url": "https://api.deepseek.com",
                    "openai_model": "deepseek-v4-flash",
                }
            ),
            client=client,
        )
        executor = StatelessExecutionStepExecutor(
            ProviderModelRuntimeAdapter(provider), max_output_tokens=10000, retry_base_seconds=0
        )
        request = portrait_request()
        resolved = executor.resolve(request, portrait_registry())

        attempts = 0

        async def attempt():
            nonlocal attempts
            attempts += 1
            return attempts

        outcome = await executor.call_provider(
            request,
            executor.build_model_request(request, resolved),
            begin_attempt=attempt,
            cancel_event=asyncio.Event(),
        )
        terminal = executor.terminal_from_outcome(request, resolved, outcome)
    return terminal, calls


def deepseek_wire_response(*, content=" 原始画像\n", finish="stop", **message):
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": finish,
                    "message": {"role": "assistant", "content": content, **message},
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


@pytest.mark.asyncio
async def test_deepseek_plain_text_route_has_no_json_or_beta_request():
    terminal, calls = await execute_deepseek_wire([deepseek_wire_response()])
    assert terminal.output == {"content": " 原始画像\n"}
    assert len(calls) == 1 and str(calls[0].url) == "https://api.deepseek.com/chat/completions"
    payload = json.loads(calls[0].content)
    assert not {"response_format", "tools", "tool_choice"} & payload.keys()
    assert payload["thinking"] == {"type": "disabled"}


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["\ufeff", " \n\ufeff\r\n ", '{"不是结构化请求": true}'])
async def test_deepseek_preserves_bom_and_json_looking_text_without_interpretation(content):
    terminal, calls = await execute_deepseek_wire([deepseek_wire_response(content=content)])
    assert terminal.output == {"content": content}
    assert terminal.usage.providerAttempts == len(calls) == 1
    assert terminal.usage.protocolCorrections == 0
    assert terminal.resolvedModel.endpointProfile == "endpoint.deepseek-official.v1"
    assert terminal.resolvedModel.capabilityVersion == "capability.deepseek-v4.plain-text.v1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_response", "error_code"),
    [
        (deepseek_wire_response(content=" \t\n\r\u0085\u3000"), "MODEL_OUTPUT_PROTOCOL_INVALID"),
        (deepseek_wire_response(finish="length"), "MODEL_OUTPUT_TRUNCATED"),
        (deepseek_wire_response(finish="content_filter"), "MODEL_OUTPUT_FILTERED"),
        (deepseek_wire_response(finish="未知原因"), "MODEL_FINISH_REASON_INVALID"),
        (
            deepseek_wire_response(
                tool_calls=[
                    {
                        "id": "unexpected-tool",
                        "type": "function",
                        "function": {"name": "供应商不可信名称", "arguments": '{"坏参数原文'},
                    }
                ]
            ),
            "MODEL_OUTPUT_PROTOCOL_INVALID",
        ),
        (
            httpx.Response(200, content="非 JSON 供应商原文"),
            "MODEL_PROVIDER_PROTOCOL_INVALID",
        ),
    ],
)
async def test_deepseek_unusable_wire_output_is_one_terminal_failure(provider_response, error_code):
    terminal, calls = await execute_deepseek_wire([provider_response])
    assert terminal.errorCode == error_code
    assert terminal.usage.providerAttempts == len(calls) == 1
    assert terminal.usage.protocolCorrections == 0
    assert terminal.retryable is False
    serialized = terminal.model_dump_json()
    for forbidden in ["供应商不可信名称", "坏参数原文", "非 JSON 供应商原文", "原始画像"]:
        assert forbidden not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_response", "error_code", "attempts"),
    [
        (httpx.Response(400, content="供应商拒绝原文"), "MODEL_PROVIDER_REJECTED", 1),
        (httpx.Response(429, content="供应商限流原文"), "MODEL_PROVIDER_RETRY_EXHAUSTED", 3),
        (httpx.ReadTimeout("供应商超时原文"), "MODEL_OUTCOME_UNKNOWN", 1),
    ],
)
async def test_plain_text_transport_keeps_existing_retry_and_unknown_outcome_boundary(
    provider_response, error_code, attempts
):
    terminal, calls = await execute_deepseek_wire([provider_response])
    assert terminal.errorCode == error_code
    assert terminal.usage.providerAttempts == len(calls) == attempts
    assert terminal.usage.protocolCorrections == 0
    assert terminal.usage.usageStatus == "unknown"
    assert terminal.outcomeUnknown is (error_code == "MODEL_OUTCOME_UNKNOWN")
    assert "供应商" not in terminal.model_dump_json()
    assert len({request.content for request in calls}) == 1


def test_plain_text_prompt_and_five_uncached_steps_match_frozen_assets():
    from inkforge_agents.runtime.portrait_prompts import (
        PORTRAIT_SECTION_INSTRUCTIONS,
        PORTRAIT_SYSTEM_PROMPT,
    )

    operation = portrait_registry().resolve("style", "portrait")
    assert operation.generator_profile.prompt_profile.system_prompt == PORTRAIT_SYSTEM_PROMPT
    assert list(PORTRAIT_SECTION_INSTRUCTIONS) == [
        "creativeMethodology",
        "uniqueMarkers",
        "generationStyle",
        "expressionFeatures",
        "styleTraits",
    ]
    for field in [
        "max_model_calls",
        "max_input_tokens",
        "max_prompt_cache_miss_tokens",
        "max_completion_tokens",
        "max_reasoning_tokens",
        "max_visible_output_tokens",
        "max_cost_micros",
        "max_wall_clock_seconds",
    ]:
        assert getattr(operation.generator_step_budget, field) * 5 == getattr(
            operation.operation.run_budget, field
        )
    assert operation.generator_step_budget.max_protocol_corrections == 0
    assert operation.operation.run_budget.max_protocol_correction_steps == 0


def test_over_budget_full_source_fails_without_sampling():
    content = "完整" * 30000
    source = portrait_context()
    source["references"] = [
        {
            "referenceId": "large-reference",
            "filename": "大文件.txt",
            "charCount": len(content),
            "content": content,
            "contentSha256": hashlib.sha256(content.encode()).hexdigest(),
        }
    ]
    source["originalCharCount"] = len(content)
    source["sourceTextSha256"] = hashlib.sha256(
        f"参考资料：大文件.txt\n\n{content}".encode()
    ).hexdigest()
    request = portrait_request(source=source)
    model = PortraitModel()
    executor = StatelessExecutionStepExecutor(model, max_output_tokens=10000)
    resolved = executor.resolve(request, portrait_registry())
    with pytest.raises(ExecutionCapabilityError, match="完整画像来源"):
        executor.build_model_request(request, resolved)
    assert model.requests == []


@pytest.mark.asyncio
async def test_missing_running_portrait_journal_never_reissues_model():
    request = portrait_request(single=True).model_copy(update={"dispatchMode": "running_recovery"})
    model, callbacks = PortraitModel(), RecordingCallbacks()
    service = ExecutionService(
        journal=_journal(prefix="test:portrait:unknown"),
        registry=portrait_registry(),
        executor=StatelessExecutionStepExecutor(model, max_output_tokens=10000),
        callbacks=callbacks,
    )
    await service.submit(request)
    await service.wait_idle()
    assert model.requests == []
    assert callbacks.failures[0].errorCode == "MODEL_OUTCOME_UNKNOWN"
    assert callbacks.failures[0].novelId is None
