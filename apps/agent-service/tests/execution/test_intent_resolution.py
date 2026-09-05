from __future__ import annotations

import asyncio
import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
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

_CONTRACT_ROOT = Path(__file__).resolve().parents[4] / "contracts" / "agent-execution"


def _asset_entry_sha256(filename: str, collection: str, key: str) -> str:
    document = json.loads((_CONTRACT_ROOT / filename).read_text(encoding="utf-8"))
    entry = next(item for item in document[collection] if item["key"] == key)
    encoded = json.dumps(
        entry,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
                ("rewrite_scene", "改写场景并返回完整正文"),
                ("review_chapter", "审阅章节"),
            ]
        ],
    }


def _context_v2():
    context = _context()
    context["availableOperations"] += [
        {"operation": operation, "description": description,
         "targetType": "chapter", "scopeKind": scope}
        for operation, description, scope in [
            ("create_lore", "为当前小说新建设定候选", "novel"),
            ("revise_lore", "为当前小说修改设定候选", "novel"),
            ("create_outline", "为当前小说创建大纲候选", "novel"),
            ("revise_outline", "为当前小说修改大纲候选", "novel"),
            ("manage_foreshadowing", "围绕当前章节管理伏笔候选", "chapter"),
        ]
    ]
    return context


def _enabled_registry():
    registry = load_execution_registry(environment="test")
    keys = {"long_serial." + item["operation"] for item in _context_v2()["availableOperations"]}
    assert all(registry.operations[key].v2_enabled for key in keys)
    return registry


def _request(*, mode="initial", clarifications=None, context=None, profile_key=None):
    registry = load_execution_registry(environment="test")
    resolved = registry.resolve_system_purpose("resolve_intent", "long_serial")
    profile = (
        resolved.model_profile if profile_key is None else registry.profiles[profile_key]
    )
    schema, budget = resolved.output_schema, resolved.step_budget
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


def _with_profile(request, profile):
    return request.model_copy(
        update={
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
            )
        }
    )


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
    registry = load_execution_registry(environment="test")
    resolved = registry.resolve_system_purpose("resolve_intent", "long_serial")
    assert resolved.definition.workflows == ("long_serial",)
    assert resolved.model_profile.key == "system.intent_resolver.v3"
    assert resolved.model_profile.version == 3
    assert resolved.model_profile.prompt_profile.key == "prompt.system.intent_resolver.v3"
    assert resolved.model_profile.prompt_profile.version == 3
    assert resolved.model_profile.prompt_profile.sha256 == (
        "a0f495e7f011eb8f8f0741a3b4e643bfb4d821a7cf62f29e422ac038ff9217e4"
    )
    assert (
        resolved.model_profile.deployment_profile_key
        == "deployment.system.intent_resolver.v3"
    )
    assert resolved.model_profile.reasoning_mode == "disabled"
    assert registry.profiles["system.intent_resolver.v1"].version == 1
    assert (
        registry.profiles["system.intent_resolver.v1"].prompt_profile.sha256
        == "4ebf30f06de85e21db42275f10e88a9ce309ee037dfebfd0fc921bfc77796f63"
    )
    assert _asset_entry_sha256(
        "prompt-profile-registry.v1.json", "prompts", "prompt.system.intent_resolver.v1"
    ) == "011648acbdbcf2daa527d4e91e3ba0997d233277e9777f645a1f4262d244d204"
    assert _asset_entry_sha256(
        "profile-registry.v1.json", "profiles", "system.intent_resolver.v1"
    ) == "883cb9744409af7517388ad0898247da972a69758533ba1698c5c1aea4372a4b"
    assert _asset_entry_sha256(
        "deployment-profile-registry.v1.json",
        "profiles",
        "deployment.system.intent_resolver.v1",
    ) == "efa051bc34fb0635907955053e1e291c059be124b0d739b0bc1acc69883531a4"
    assert _asset_entry_sha256(
        "prompt-profile-registry.v1.json", "prompts", "prompt.system.intent_resolver.v2"
    ) == "56ed2867b9705ea39f46aafb5b92d4cb2b7b5cbf2b8ea6b6e27d4e919f099de2"
    assert _asset_entry_sha256(
        "profile-registry.v1.json", "profiles", "system.intent_resolver.v2"
    ) == "aef6ad93b934b2b798a2c1c0ad23931e705d079960e23b56603a02f80675f4e7"
    assert _asset_entry_sha256(
        "deployment-profile-registry.v1.json", "profiles", "deployment.system.intent_resolver.v2"
    ) == "76316fc115a688759e339e7fe43cc8c136fe474ce2ed74c7366f8c38e1a8f9b5"
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


def test_intent_v3_model_envelope_uses_all_frozen_descriptions_and_scopes():
    request = _request(context=_context_v2())
    executor = _executor(RecordingModel())
    resolved = executor.resolve(request, _enabled_registry())
    model_request = executor.build_model_request(request, resolved)

    assert model_request.messages[0].content == resolved.prompt_profile.system_prompt
    assert model_request.policy.policyId == "system.intent_resolver.v3"
    assert "availableOperations" in model_request.messages[0].content
    assert "description" in model_request.messages[0].content
    assert "scopeKind" in model_request.messages[0].content
    assert "不得默默扩大为整本小说" in model_request.messages[0].content
    assert "answer_question 表示" not in model_request.messages[0].content
    envelope = json.loads(model_request.messages[1].content)
    context = envelope["evidenceBundle"]["items"][0]["contentJson"]
    assert context["availableOperations"] == _context_v2()["availableOperations"]


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_resolver_keeps_original_prompt_and_chapter_context(version):
    key = f"system.intent_resolver.v{version}"
    request = _request(profile_key=key)
    executor = _executor(RecordingModel())
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    model_request = executor.build_model_request(request, resolved)
    assert model_request.policy.policyId == key
    assert model_request.messages[0].content == resolved.prompt_profile.system_prompt
    assert "scopeKind 明确" not in model_request.messages[0].content
    assert json.loads(model_request.messages[1].content)["evidenceBundle"]["items"][0][
        "contentJson"
    ] == _context()


@pytest.mark.parametrize("mode", ["initial", "pending_recovery", "running_recovery"])
@pytest.mark.parametrize(
    "profile_key",
    ["system.intent_resolver.v1", "system.intent_resolver.v2", "system.intent_resolver.v3"],
)
def test_intent_accepts_only_complete_retained_frozen_profile_tuples(mode, profile_key):
    resolved = _executor(RecordingModel()).resolve(
        _request(mode=mode, profile_key=profile_key),
        load_execution_registry(environment="test"),
    )
    assert resolved.profile.key == profile_key


@pytest.mark.parametrize("mode", ["initial", "pending_recovery", "running_recovery"])
def test_intent_rejects_arbitrary_versioned_profile_alias(mode):
    registry = load_execution_registry(environment="test")
    legacy = registry.profiles["system.intent_resolver.v1"]
    alias = replace(legacy, key="system.intent_resolver.v99", version=99)
    registry_with_alias = replace(
        registry,
        profiles=MappingProxyType({**registry.profiles, alias.key: alias}),
    )
    request = _request(mode=mode, profile_key="system.intent_resolver.v1")
    request = request.model_copy(
        update={
            "modelProfile": request.modelProfile.model_copy(
                update={"profile": alias.key, "version": alias.version}
            )
        }
    )
    with pytest.raises(ExecutionCapabilityError):
        _executor(RecordingModel()).resolve(request, registry_with_alias)


@pytest.mark.parametrize("mode", ["initial", "pending_recovery", "running_recovery"])
@pytest.mark.parametrize(
    ("profile_key", "prompt_key", "deployment_key"),
    [
        (
            "system.intent_resolver.v1",
            "prompt.system.intent_resolver.v2",
            "deployment.system.intent_resolver.v1",
        ),
        (
            "system.intent_resolver.v1",
            "prompt.system.intent_resolver.v1",
            "deployment.system.intent_resolver.v2",
        ),
        (
            "system.intent_resolver.v2",
            "prompt.system.intent_resolver.v1",
            "deployment.system.intent_resolver.v2",
        ),
        (
            "system.intent_resolver.v2",
            "prompt.system.intent_resolver.v2",
            "deployment.system.intent_resolver.v1",
        ),
        (
            "system.intent_resolver.v3",
            "prompt.system.intent_resolver.v2",
            "deployment.system.intent_resolver.v3",
        ),
        (
            "system.intent_resolver.v3",
            "prompt.system.intent_resolver.v3",
            "deployment.system.intent_resolver.v2",
        ),
        (
            "system.intent_resolver.v2",
            "prompt.system.intent_resolver.v3",
            "deployment.system.intent_resolver.v2",
        ),
    ],
)
def test_intent_rejects_cross_version_prompt_or_deployment_tuple(
    mode, profile_key, prompt_key, deployment_key
):
    registry = load_execution_registry(environment="test")
    crossed = replace(
        registry.profiles[profile_key],
        prompt_profile=registry.prompt_profiles[prompt_key],
        deployment_profile_key=deployment_key,
    )
    registry_with_crossed_profile = replace(
        registry,
        profiles=MappingProxyType({**registry.profiles, profile_key: crossed}),
    )
    request = _with_profile(_request(mode=mode, profile_key=profile_key), crossed)
    with pytest.raises(ExecutionCapabilityError):
        _executor(RecordingModel()).resolve(request, registry_with_crossed_profile)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["initial", "pending_recovery", "running_recovery"])
@pytest.mark.parametrize(
    "operation",
    ["answer_question", "plan_chapter", "write_chapter", "rewrite_scene", "review_chapter", None],
)
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


@pytest.mark.parametrize(
    "definition_update",
    [
        {"workflows": ("quality",)},
        {"lane": "creative"},
        {"evidence_policy": "evidence.system.summary.v1"},
        {"parent_operations": ("long_serial.answer_question",)},
    ],
)
def test_intent_v1_initial_still_requires_current_system_purpose_binding(definition_update):
    registry = load_execution_registry(environment="test")
    altered = replace(
        registry,
        system_purposes=MappingProxyType(
            {
                **registry.system_purposes,
                "resolve_intent": replace(
                    registry.system_purposes["resolve_intent"], **definition_update
                ),
            }
        ),
    )
    with pytest.raises(ExecutionCapabilityError):
        _executor(RecordingModel()).resolve(
            _request(profile_key="system.intent_resolver.v1"), altered
        )


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
    legacy_request = _request(mode=mode, profile_key="system.intent_resolver.v1")
    assert executor.resolve(legacy_request, updated).purpose == "resolve_intent"
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
        executor.resolve(legacy_request, removed)


@pytest.mark.parametrize("mode", ["initial", "pending_recovery", "running_recovery"])
@pytest.mark.parametrize(
    "corruption", ["novel", "chapter", "workflow", "extra", "duplicate", "scope_mismatch"]
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


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["initial", "pending_recovery", "running_recovery"])
@pytest.mark.parametrize("option", _context_v2()["availableOperations"])
async def test_v3_resolver_selects_only_one_frozen_operation_without_authoring_scope(mode, option):
    request = _request(mode=mode, context=_context_v2())
    model = RecordingModel(result=_result(_output(option["operation"])))
    executor = _executor(model)
    resolved = executor.resolve(request, _enabled_registry())
    model_request = executor.build_model_request(request, resolved)
    outcome = await executor.call_provider(
        request, model_request, begin_attempt=_one_attempt, cancel_event=asyncio.Event()
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)
    assert terminal.resultKind == "proposed_command"
    assert terminal.proposedCommand.operation == option["operation"]
    assert terminal.proposedCommand.scopeKind is None
    assert terminal.proposedCommand.targetId is None
    assert terminal.proposedCommand.targetType is None
    assert terminal.proposedCommand.arguments == {}
    assert terminal.usage.providerAttempts == len(model.requests) == 1
    assert model_request.tools == []


@pytest.mark.parametrize("mode", ["initial", "pending_recovery", "running_recovery"])
@pytest.mark.parametrize("option", _context_v2()["availableOperations"])
def test_v3_resolver_rejects_wrong_default_scope_even_when_operation_is_enabled(mode, option):
    wrong_scope = "chapter" if option["scopeKind"] == "novel" else "novel"
    context = _context_v2() | {"availableOperations": [option | {"scopeKind": wrong_scope}]}
    with pytest.raises(ExecutionCapabilityError):
        _executor(RecordingModel()).resolve(
            _request(mode=mode, context=context), _enabled_registry()
        )


@pytest.mark.parametrize("mode", ["initial", "pending_recovery", "running_recovery"])
@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("option", _context_v2()["availableOperations"][5:])
def test_v3_scope_and_operations_never_expand_retained_resolver_authority(mode, version, option):
    context = _context_v2() | {"availableOperations": [option]}
    with pytest.raises(ExecutionCapabilityError):
        _executor(RecordingModel()).resolve(
            _request(mode=mode, context=context, profile_key=f"system.intent_resolver.v{version}"),
            _enabled_registry(),
        )


def test_v3_initial_requires_enabled_catalog_but_recovery_keeps_frozen_subset():
    enabled = _enabled_registry()
    disabled_key = "long_serial.create_lore"
    registry = replace(enabled, operations=MappingProxyType({
        **enabled.operations,
        disabled_key: replace(enabled.operations[disabled_key], v2_enabled=False),
    }))
    context = _context_v2()
    executor = _executor(RecordingModel())
    assert any(not registry.operations["long_serial." + item["operation"]].v2_enabled
               for item in context["availableOperations"])
    with pytest.raises(ExecutionCapabilityError):
        executor.resolve(_request(context=context), registry)
    for mode in ("pending_recovery", "running_recovery"):
        resolved = executor.resolve(_request(mode=mode, context=context), registry)
        assert resolved.purpose == "resolve_intent"
    option = context["availableOperations"][5]
    request = _request(context=context | {"availableOperations": [option]})
    resolved = executor.resolve(request, _enabled_registry())
    for unauthorized in ("write_chapter", "revise_lore", "rewrite_chapter_selection"):
        terminal = executor.terminal_from_outcome(
            request, resolved, ProviderCallOutcome(_result(_output(unauthorized)), 1, 1)
        )
        assert terminal.errorCategory == "validation"
    for field, value in (("scopeKind", "novel"), ("targetType", "novel"),
                         ("targetId", "novel-1"), ("arguments", {"scopeKind": "novel"})):
        terminal = executor.terminal_from_outcome(
            request, resolved, ProviderCallOutcome(_result(_output(option["operation"]) | {
                field: value,
            }), 1, 1)
        )
        assert terminal.errorCategory == "validation"


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
