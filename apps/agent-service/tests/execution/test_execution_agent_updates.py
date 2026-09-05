from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace
from types import MappingProxyType
from typing import Any, Literal

import pytest
from inkforge_agents.execution.executor import (
    ExecutionCapabilityError,
    ProviderCallOutcome,
    StatelessExecutionStepExecutor,
)
from inkforge_agents.execution.registry import ExecutionRegistry, load_execution_registry
from inkforge_agents.providers.base import ModelTurnResult, ModelUsage, ModelUsageDiagnostics
from inkforge_contracts import materialize_agent_updates_output
from inkforge_contracts.execution import (
    EvidenceItem,
    EvidenceManifest,
    EvidenceManifestItem,
    ExecutionStepRequest,
    ModelProfileRef,
    OutputSchemaRef,
    PromptProfileRef,
    StepBudget,
    canonical_execution_json_bytes,
    canonical_execution_sha256,
)

from .support import execution_request, rehash_request
from .test_executor import RecordingModel, _one_attempt

_OPERATIONS = (
    "create_lore",
    "revise_lore",
    "create_outline",
    "revise_outline",
    "manage_foreshadowing",
)
_GENERATOR_PROFILES = {
    "create_lore": "lore.generator.v2",
    "revise_lore": "lore.reviser.v2",
    "create_outline": "plot.outline_generator.v2",
    "revise_outline": "plot.outline_reviser.v2",
    "manage_foreshadowing": "plot.foreshadowing.v2",
}
_REVIEWER_PROFILES = {
    "create_lore": "reviewer.agent_updates_consistency.v1",
    "revise_lore": "reviewer.agent_updates_consistency.v1",
    "create_outline": "reviewer.agent_updates_editorial.v1",
    "revise_outline": "reviewer.agent_updates_editorial.v1",
    "manage_foreshadowing": "reviewer.agent_updates_consistency.v1",
}


def _provider_output() -> dict[str, Any]:
    return {
        "summary": " 原始说明 ",
        "updates": {
            "characters": [
                {
                    "action": "update",
                    "id": "character-1",
                    "background": None,
                }
            ],
            "worldSetting": "",
        },
    }


def _enabled_registry() -> ExecutionRegistry:
    registry = load_execution_registry(environment="test")
    operations = dict(registry.operations)
    for operation in _OPERATIONS:
        key = f"long_serial.{operation}"
        operations[key] = replace(operations[key], v2_enabled=True)
    return replace(registry, operations=MappingProxyType(operations))


def _json_item(
    *,
    item_id: str = "evidence-index-1",
    ordinal: int = 1,
    resource_type: str = "agent_updates_index",
    resource_id: str = "novel-1",
    content: Any | None = None,
    metadata: dict[str, Any] | None = None,
    range_value: dict[str, int] | None = None,
) -> EvidenceItem:
    value = (
        {
            "items": [
                {
                    "resourceType": "character",
                    "id": "character-1",
                    "name": "林舟",
                }
            ]
        }
        if content is None
        else content
    )
    encoded = canonical_execution_json_bytes(value)
    return EvidenceItem.model_validate(
        {
            "id": item_id,
            "bundleId": "bundle-1",
            "ordinal": ordinal,
            "resourceType": resource_type,
            "resourceId": resource_id,
            "exists": True,
            "contentType": "json",
            "contentJson": value,
            "contentSha256": canonical_execution_sha256(value),
            "byteCount": len(encoded),
            "range": range_value,
            "metadata": metadata
            or {
                "targetType": "novel",
                "targetId": resource_id,
                "roles": ["index"],
            },
        }
    )


def _text_item(text: str, *, ordinal: int = 2) -> EvidenceItem:
    encoded = text.encode("utf-8")
    return EvidenceItem.model_validate(
        {
            "id": f"evidence-text-{ordinal}",
            "bundleId": "bundle-1",
            "ordinal": ordinal,
            "resourceType": "character",
            "resourceId": "character-1",
            "exists": True,
            "contentType": "text",
            "contentText": text,
            "contentSha256": hashlib.sha256(encoded).hexdigest(),
            "byteCount": len(encoded),
            "metadata": {"role": "target"},
        }
    )


def _with_evidence(
    request: ExecutionStepRequest,
    items: list[EvidenceItem],
) -> ExecutionStepRequest:
    manifest = EvidenceManifest(
        bundleId=request.evidenceBundle.id,
        bundleVersion=request.evidenceBundle.version,
        itemCount=len(items),
        items=[
            EvidenceManifestItem(
                itemId=item.id,
                **item.model_dump(exclude={"id", "bundleId", "contentText", "contentJson"}),
            )
            for item in items
        ],
    )
    return rehash_request(
        request.model_copy(
            update={
                "evidenceBundle": request.evidenceBundle.model_copy(
                    update={
                        "items": items,
                        "manifest": manifest,
                        "manifestSha256": canonical_execution_sha256(
                            manifest.model_dump(mode="json", exclude_none=True)
                        ),
                        "totalBytes": sum(item.byteCount for item in items),
                    }
                )
            }
        )
    )


def _request(
    operation_name: str,
    *,
    reviewer: bool = False,
    revision: bool = False,
    dispatch_mode: Literal["initial", "pending_recovery", "running_recovery"] = "initial",
) -> ExecutionStepRequest:
    registry = _enabled_registry()
    operation = registry.resolve("long_serial", operation_name)
    profile = operation.reviewer_profiles[0] if reviewer else operation.generator_profile
    schema = operation.reviewer_output_schema if reviewer else operation.output_schema
    if schema is None:
        raise AssertionError("测试 Operation 缺少 Reviewer output")
    budget = (
        operation.reviewer_step_budgets[profile.key]
        if reviewer
        else operation.generator_step_budget
    )
    candidate = materialize_agent_updates_output(_provider_output())
    input_value: dict[str, Any] = {"userInstruction": "  调整冻结资料😀\r\n"}
    artifact_id: str | None = None
    artifact_revision: int | None = None
    if revision:
        artifact_id = "artifact-updates-1"
        artifact_revision = 2
        input_value |= {
            "originalUserInstruction": "最初的完整资料要求",
            "previousCandidate": {
                "artifactId": artifact_id,
                "artifactRevision": artifact_revision,
                "summary": candidate["summary"],
                "updates": candidate["updates"],
            },
        }
    if reviewer:
        artifact_id = "artifact-updates-1"
        artifact_revision = 2
        input_value = {
            "task": {
                "workflow": "long_serial",
                "operation": operation_name,
                "target": {"type": "chapter", "id": "chapter-1"},
                "scope": {"kind": "chapter", "chapterId": "chapter-1"},
                "userInstruction": "  调整冻结资料😀\r\n",
                "rubricVersion": "rubric.agent_updates.review.v1",
            },
            "candidate": candidate,
        }
    base = execution_request(dispatch_mode=dispatch_mode)
    request = base.model_copy(
        update={
            "operation": operation_name,
            "purpose": "review" if reviewer else "generation",
            "lane": (
                operation.operation.review_policy.lane if reviewer else operation.operation.lane
            ),
            "input": input_value,
            "artifactId": artifact_id,
            "artifactRevision": artifact_revision,
            "evidenceBundle": base.evidenceBundle.model_copy(
                update={
                    "policyVersion": (
                        operation.operation.review_policy.evidence_policy
                        if reviewer
                        else operation.operation.evidence_policy
                    )
                }
            ),
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
    return _with_evidence(request, [_json_item()])


def _executor(model: RecordingModel) -> StatelessExecutionStepExecutor:
    return StatelessExecutionStepExecutor(
        model,
        max_output_tokens=20_000,
        retry_base_seconds=0,
    )


def _outcome(
    output: dict[str, Any],
    *,
    reasoning_tokens: int = 6,
) -> ProviderCallOutcome:
    return ProviderCallOutcome(
        result=ModelTurnResult(
            content="",
            toolCalls=[],
            structuredOutput=output,
            usage=ModelUsage(
                promptTokens=123,
                cachedTokens=23,
                completionTokens=40,
                totalTokens=163,
            ),
            diagnostics=ModelUsageDiagnostics(
                promptCacheMissTokens=100,
                reasoningTokens=reasoning_tokens,
            ),
            finishReason="stop",
            rawFinishReason="stop",
        ),
        provider_attempts=1,
        elapsed_millis=17,
    )


def _finding(request: ExecutionStepRequest) -> dict[str, Any]:
    item = request.evidenceBundle.items[0]
    return {
        "dimension": "agent_updates.local",
        "severity": "warning",
        "claim": "资料状态需要进一步对齐。",
        "candidateRange": None,
        "evidence": [
            {
                "evidenceItemId": item.id,
                "contentSha256": item.contentSha256,
                "range": None,
            }
        ],
        "suggestion": "保持原字段存在性并修正冲突。",
        "confidence": 0.9,
    }


def test_five_operations_remain_catalog_disabled_and_make_no_provider_call() -> None:
    registry = load_execution_registry(environment="test")
    model = RecordingModel()
    executor = _executor(model)

    for operation in _OPERATIONS:
        assert registry.operations[f"long_serial.{operation}"].v2_enabled is False
        with pytest.raises(ExecutionCapabilityError, match="Catalog"):
            executor.resolve(_request(operation), registry)

    assert model.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("operation_name", _OPERATIONS)
async def test_five_generation_steps_use_one_call_and_presence_aware_result(
    operation_name: str,
) -> None:
    registry = _enabled_registry()
    request = _request(operation_name)
    model = RecordingModel(
        result=_outcome(_provider_output()).result,
    )
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
    assert terminal.output == materialize_agent_updates_output(_provider_output())
    assert set(terminal.output["updates"]) == {"characters", "worldSetting"}
    assert terminal.output["updates"]["characters"][0] == {
        "action": "update",
        "id": "character-1",
        "background": None,
    }
    assert resolved.profile.key == _GENERATOR_PROFILES[operation_name]
    assert model_request.tools == []
    assert model_request.parallelToolCalls is False
    assert model_request.policy.thinkingMode == "enabled"
    assert len(model.requests) == 1


def test_generation_build_keeps_long_evidence_complete_under_frozen_budget() -> None:
    request = _request("revise_lore")
    long_text = " 完整旧资料😀\r\n" * 1_500 + "不可丢失的末尾"
    request = _with_evidence(request, [_json_item(), _text_item(long_text)])
    executor = _executor(RecordingModel())
    resolved = executor.resolve(request, _enabled_registry())

    model_request = executor.build_model_request(request, resolved)
    envelope = json.loads(model_request.messages[1].content)

    assert request.budget.maxInputTokens == 80_000
    assert request.budget.maxPromptCacheMissTokens == 80_000
    assert envelope["evidenceBundle"]["items"][1]["contentText"] == long_text
    assert envelope["evidenceBundle"]["items"][1]["contentText"].endswith("不可丢失的末尾")


def test_generation_revision_requires_exact_previous_candidate_identity() -> None:
    registry = _enabled_registry()
    executor = _executor(RecordingModel())
    valid = _request("revise_lore", revision=True)
    executor.resolve(valid, registry)

    for field, value in (("artifactId", "artifact-other"), ("artifactRevision", 3)):
        changed = dict(valid.input)
        previous = dict(changed["previousCandidate"])
        previous[field] = value
        changed["previousCandidate"] = previous
        request = rehash_request(valid.model_copy(update={"input": changed}))
        with pytest.raises(ExecutionCapabilityError, match="候选"):
            executor.resolve(request, registry)

    initial = _request("revise_lore")
    bound = rehash_request(
        initial.model_copy(update={"artifactId": "artifact-updates-1", "artifactRevision": 1})
    )
    with pytest.raises(ExecutionCapabilityError, match="结构化资料"):
        executor.resolve(bound, registry)


@pytest.mark.parametrize(
    "items",
    [
        [],
        [_json_item(resource_id="another-novel")],
        [_json_item(content={"items": {}})],
        [_json_item(range_value={"startCodePoint": 0, "endCodePoint": 1})],
        [
            _json_item(),
            _json_item(item_id="evidence-index-2", ordinal=2),
        ],
    ],
    ids=("missing", "wrong-novel", "items-not-list", "range", "duplicate"),
)
def test_generation_requires_one_complete_same_novel_index(
    items: list[EvidenceItem],
) -> None:
    request = _request("create_lore")
    if not items:
        items = [_text_item("不是 index", ordinal=1)]
    request = _with_evidence(request, items)
    model = RecordingModel()

    with pytest.raises(ExecutionCapabilityError, match="agent_updates_index"):
        _executor(model).resolve(request, _enabled_registry())

    assert model.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("operation_name", _OPERATIONS)
async def test_five_review_steps_use_dedicated_profile_and_exact_candidate(
    operation_name: str,
) -> None:
    request = _request(operation_name, reviewer=True)
    model = RecordingModel(
        result=ModelTurnResult(
            content="",
            toolCalls=[],
            structuredOutput={"contentVerdict": "pass", "findings": []},
            usage=ModelUsage(
                promptTokens=100,
                cachedTokens=0,
                completionTokens=20,
                totalTokens=120,
            ),
            finishReason="stop",
            rawFinishReason="stop",
        )
    )
    executor = _executor(model)
    resolved = executor.resolve(request, _enabled_registry())
    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_one_attempt,
        cancel_event=asyncio.Event(),
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)

    assert resolved.profile.key == _REVIEWER_PROFILES[operation_name]
    assert resolved.rubric_version == "rubric.agent_updates.review.v1"
    assert terminal.resultKind == "evaluation"
    assert terminal.evaluation.artifactId == request.artifactId
    assert terminal.evaluation.artifactRevision == request.artifactRevision
    assert terminal.evaluation.findings == []
    assert model.requests[0].tools == []
    assert model.requests[0].policy.thinkingMode == "disabled"
    assert len(model.requests) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"extra": True},
        {"task": {"operation": "create_outline"}},
        {"task": {"rubricVersion": "rubric.other.v1"}},
        {"task": {"targetWordCount": 4_000}},
        {"task": {"userInstruction": "\u0085\u3000\ufeff"}},
        {"candidate": {"updatesSha256": "0" * 64}},
    ],
    ids=(
        "outer-extra",
        "wrong-operation",
        "wrong-rubric",
        "unexpected-task-key",
        "blank-instruction",
        "hash",
    ),
)
def test_reviewer_rejects_invalid_task_or_candidate_before_provider(
    change: dict[str, Any],
) -> None:
    request = _request("revise_lore", reviewer=True)
    input_value = dict(request.input)
    if "extra" in change:
        input_value["extra"] = change["extra"]
    if "task" in change:
        input_value["task"] = dict(input_value["task"]) | change["task"]
    if "candidate" in change:
        input_value["candidate"] = dict(input_value["candidate"]) | change["candidate"]
    request = rehash_request(request.model_copy(update={"input": input_value}))
    model = RecordingModel()

    with pytest.raises(ExecutionCapabilityError, match="结构化资料|rubricVersion"):
        _executor(model).resolve(request, _enabled_registry())

    assert model.requests == []


@pytest.mark.parametrize("invalid_kind", ["candidate-range", "candidate-patch"])
def test_reviewer_rejects_text_location_or_patch_and_keeps_actual_usage(
    invalid_kind: str,
) -> None:
    request = _request("create_lore", reviewer=True)
    finding = _finding(request)
    if invalid_kind == "candidate-range":
        finding["candidateRange"] = {"startCodePoint": 0, "endCodePoint": 1}
    else:
        finding["candidatePatch"] = {
            "kind": "text_replace",
            "find": "旧值",
            "replace": "新值",
        }
    output = {"contentVerdict": "issues_found", "findings": [finding]}
    executor = _executor(RecordingModel())
    resolved = executor.resolve(request, _enabled_registry())

    terminal = executor.terminal_from_outcome(
        request,
        resolved,
        _outcome(output, reasoning_tokens=0),
    )

    assert terminal.errorCode in {
        "MODEL_OUTPUT_SCHEMA_INVALID",
        "MODEL_EVALUATION_INVALID",
    }
    assert terminal.usage.providerAttempts == 1
    assert terminal.usage.inputTokens == 123
    assert terminal.usage.cachedTokens == 23
    assert terminal.usage.promptCacheMissTokens == 100
    assert terminal.usage.completionTokens == 40


def test_generation_custom_semantic_failure_keeps_actual_usage() -> None:
    request = _request("create_outline")
    executor = _executor(RecordingModel())
    resolved = executor.resolve(request, _enabled_registry())

    terminal = executor.terminal_from_outcome(
        request,
        resolved,
        _outcome({"summary": "说明", "updates": {}}),
    )

    assert terminal.errorCode == "MODEL_OUTPUT_PROTOCOL_INVALID"
    assert terminal.usage.providerAttempts == 1
    assert terminal.usage.inputTokens == 123
    assert terminal.usage.promptCacheMissTokens == 100
    assert terminal.usage.completionTokens == 40


def test_retained_request_rejects_cross_operation_profile_tuple() -> None:
    registry = _enabled_registry()
    request = _request("create_lore", dispatch_mode="running_recovery")
    wrong = registry.profiles["lore.reviser.v2"]
    request = rehash_request(
        request.model_copy(
            update={
                "modelProfile": ModelProfileRef(
                    profile=wrong.key,
                    version=wrong.version,
                    reasoningMode=wrong.reasoning_mode,
                    deploymentProfileKey=wrong.deployment_profile_key,
                    promptProfile=PromptProfileRef(
                        name=wrong.prompt_profile.key,
                        version=wrong.prompt_profile.version,
                        sha256=wrong.prompt_profile.sha256,
                    ),
                )
            }
        )
    )

    with pytest.raises(ExecutionCapabilityError, match="handler 身份"):
        _executor(RecordingModel()).resolve(request, registry)
