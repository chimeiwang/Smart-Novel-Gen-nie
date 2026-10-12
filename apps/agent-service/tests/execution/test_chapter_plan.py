from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import pytest
from inkforge_agents.execution.executor import ExecutionCapabilityError
from inkforge_agents.execution.registry import load_execution_registry
from inkforge_agents.providers.base import ModelTurnResult, ModelUsage, ModelUsageDiagnostics
from inkforge_contracts.execution import (
    ChapterPlanResult,
    EvidenceItem,
    EvidenceManifest,
    EvidenceManifestItem,
    ModelProfileRef,
    OutputSchemaRef,
    PromptProfileRef,
    StepBudget,
    canonical_execution_json_bytes,
    canonical_execution_sha256,
    materialize_chapter_plan_output,
)

from .support import execution_request, rehash_request
from .test_executor import RecordingModel, _executor, _one_attempt


def _semantic_plan():
    return {
        "title": "夜访旧桥",
        "summary": "主角决定追查失踪同伴的去向。",
        "chapterGoal": "确认同伴最后的行动路线",
        "sceneBeats": [{"goal": "从守桥人处取得线索", "estimatedWords": 1200}],
    }


def _context_item(**overrides):
    context = overrides.pop(
        "contentJson",
        {
            "schemaVersion": 1,
            "novelId": "novel-1",
            "chapter": {"id": "chapter-1", "title": "旧桥", "order": 1},
            "chapterGoal": None,
            "outlinePath": [],
            "sourceBindings": [],
        },
    )
    item = {
        "id": "evidence-plan-1",
        "bundleId": "bundle-1",
        "ordinal": 1,
        "resourceType": "chapter_plan_context",
        "resourceId": "chapter-1",
        "exists": True,
        "contentType": "json",
        "contentJson": context,
        "contentSha256": canonical_execution_sha256(context),
        "byteCount": len(canonical_execution_json_bytes(context)),
        "metadata": {"role": "chapter_plan_context"},
    }
    return EvidenceItem.model_validate(item | overrides)


def _with_evidence(request, items):
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


def _request(*, revision=False, reviewer=False):
    registry = load_execution_registry(environment="test")
    operation = registry.resolve("long_serial", "plan_chapter")
    profile = operation.reviewer_profiles[0] if reviewer else operation.generator_profile
    schema = operation.reviewer_output_schema if reviewer else operation.output_schema
    budget = (
        operation.reviewer_step_budgets[profile.key]
        if reviewer
        else operation.generator_step_budget
    )
    payload = {"userInstruction": "  规划冲突推进\n", "targetWordCount": 4000}
    artifact = {"artifactId": "artifact-plan-1", "artifactRevision": 1}
    if revision:
        payload |= {
            "originalUserInstruction": "最初的完整指令",
            "previousArtifact": artifact
            | {"payload": materialize_chapter_plan_output(_semantic_plan())},
        }
    if reviewer:
        payload = {
            "task": {
                "workflow": "long_serial",
                "operation": "plan_chapter",
                "userInstruction": "规划冲突推进",
                "targetWordCount": 4000,
                "rubricVersion": operation.operation.review_policy.rubric_version,
            },
            "candidate": materialize_chapter_plan_output(_semantic_plan()),
        }
    base = execution_request()
    return _with_evidence(
        base.model_copy(
            update={
                "operation": "plan_chapter",
                "purpose": "review" if reviewer else "generation",
                "lane": operation.operation.review_policy.lane
                if reviewer
                else operation.operation.lane,
                "input": payload,
                "artifactId": artifact["artifactId"] if revision or reviewer else None,
                "artifactRevision": artifact["artifactRevision"] if revision or reviewer else None,
                "evidenceBundle": base.evidenceBundle.model_copy(
                    update={
                        "policyVersion": operation.operation.review_policy.evidence_policy
                        if reviewer
                        else operation.operation.evidence_policy,
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
        ),
        [_context_item()],
    )


def test_catalog_planning_uses_dedicated_generator_reviewer_and_four_call_budget():
    operation = load_execution_registry(environment="test").resolve("long_serial", "plan_chapter")
    assert operation.generator_profile.key == "plot.chapter_plan.v1"
    assert [profile.key for profile in operation.reviewer_profiles] == [
        "reviewer.chapter_plan_editorial.v1"
    ]
    reviewer = operation.reviewer_profiles[0]
    assert "章节规划" in reviewer.prompt_profile.system_prompt
    assert "选区外" not in reviewer.prompt_profile.system_prompt
    assert operation.operation.review_policy.max_automatic_revisions == 1
    assert operation.operation.run_budget.max_model_calls == 4
    assert operation.operation.run_budget.max_prompt_cache_miss_tokens == 120_000
    assert operation.generator_step_budget.max_prompt_cache_miss_tokens == 30_000
    assert operation.reviewer_step_budgets[reviewer.key].max_prompt_cache_miss_tokens == 30_000
    assert (
        2
        * (
            operation.generator_step_budget.max_completion_tokens
            + operation.reviewer_step_budgets[reviewer.key].max_completion_tokens
        )
        <= operation.operation.run_budget.max_completion_tokens
    )


@pytest.mark.asyncio
async def test_planning_cold_context_uses_real_fake_generation_then_review():
    context = dict(_context_item().contentJson)
    context["writingBible"] = {"id": "bible-1", "content": "已有世界设定事实。" * 1_200}
    items = [_context_item(contentJson=context)]
    registry = load_execution_registry(environment="test")
    # 不预设 result；适配器实际委托 FakeModelProvider 产生输出和字符计量。
    model = RecordingModel()
    executor = _executor(model)
    request = _with_evidence(_request(), items)
    resolved = executor.resolve(request, registry)
    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_one_attempt,
        cancel_event=asyncio.Event(),
    )
    generated = executor.terminal_from_outcome(request, resolved, outcome)
    assert 10_000 < generated.usage.promptCacheMissTokens < 30_000
    assert generated.usage.cachedTokens == 0
    assert getattr(generated, "errorCode", None) is None
    assert generated.resultKind == "output"

    review = _with_evidence(_request(reviewer=True), items)
    review = rehash_request(review.model_copy(
        update={"input": review.input | {"candidate": generated.output}}
    ))
    resolved_review = executor.resolve(review, registry)
    reviewed = executor.terminal_from_outcome(
        review,
        resolved_review,
        await executor.call_provider(
            review,
            executor.build_model_request(review, resolved_review),
            begin_attempt=_one_attempt,
            cancel_event=asyncio.Event(),
        ),
    )
    assert 10_000 < reviewed.usage.promptCacheMissTokens < 30_000
    assert reviewed.usage.cachedTokens == 0
    assert getattr(reviewed, "errorCode", None) is None
    assert reviewed.resultKind == "evaluation"
    assert reviewed.evaluation.contentVerdict == "pass"
    assert reviewed.evaluation.evidenceBundleId == request.evidenceBundle.id
    assert generated.usage.providerAttempts == reviewed.usage.providerAttempts == 1
    assert len(model.requests) == 2


@pytest.mark.parametrize("reviewer", [False, True])
def test_planning_complete_context_over_30000_is_rejected_before_provider(reviewer):
    context = dict(_context_item().contentJson)
    context["writingBible"] = {"id": "bible-1", "content": "已" * 30_001}
    request = _with_evidence(_request(reviewer=reviewer), [_context_item(contentJson=context)])
    model = RecordingModel()
    executor = _executor(model)
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    with pytest.raises(ExecutionCapabilityError, match="完整模型输入超过"):
        executor.build_model_request(request, resolved)
    assert model.requests == []


def test_planning_rejects_missing_context_evidence_before_provider():
    request = _with_evidence(_request(), execution_request().evidenceBundle.items)
    with pytest.raises(ExecutionCapabilityError, match="规划.*Evidence"):
        _executor(RecordingModel()).resolve(
            request, load_execution_registry(environment="test")
        )


def test_planning_rejects_context_for_another_novel_before_provider():
    request = _with_evidence(
        _request(),
        [_context_item(contentJson={
            "schemaVersion": 1,
            "novelId": "another-novel",
            "chapter": {"id": "chapter-1"},
        })],
    )
    with pytest.raises(ExecutionCapabilityError, match="规划.*Evidence"):
        _executor(RecordingModel()).resolve(request, load_execution_registry(environment="test"))


@pytest.mark.parametrize("reviewer", [False, True])
@pytest.mark.parametrize(
    "invalid_context",
    [
        [],
        {},
        {"schemaVersion": True, "novelId": "novel-1", "chapter": {"id": "chapter-1"}},
        {"schemaVersion": 2, "novelId": "novel-1", "chapter": {"id": "chapter-1"}},
        {"schemaVersion": "1", "novelId": "novel-1", "chapter": {"id": "chapter-1"}},
        {"schemaVersion": 1, "novelId": "novel-1", "chapter": None},
        {"schemaVersion": 1, "novelId": "novel-1", "chapter": {}},
        {"schemaVersion": 1, "novelId": "novel-1", "chapter": {"id": "another-chapter"}},
    ],
)
def test_planning_rejects_invalid_context_shape_or_binding(invalid_context, reviewer):
    request = _with_evidence(
        _request(reviewer=reviewer), [_context_item(contentJson=invalid_context)]
    )
    with pytest.raises(ExecutionCapabilityError, match="规划.*Evidence"):
        _executor(RecordingModel()).resolve(request, load_execution_registry(environment="test"))


@pytest.mark.parametrize("reviewer", [False, True])
@pytest.mark.parametrize("invalid_kind", ["duplicate", "absent", "text", "range"])
def test_planning_requires_one_existing_complete_json_context(invalid_kind, reviewer):
    items = [_context_item()]
    if invalid_kind == "duplicate":
        items.append(_context_item(id="evidence-plan-2", ordinal=2))
    elif invalid_kind == "absent":
        items = [_context_item(
            exists=False, contentType=None, contentJson=None, contentSha256=None, byteCount=0
        )]
    elif invalid_kind == "text":
        items = [execution_request().evidenceBundle.items[0].model_copy(
            update={"resourceType": "chapter_plan_context"}
        )]
    else:
        items = [_context_item(range={"startCodePoint": 0, "endCodePoint": 1})]
    request = _with_evidence(_request(reviewer=reviewer), items)
    with pytest.raises(ExecutionCapabilityError, match="规划.*Evidence"):
        _executor(RecordingModel()).resolve(request, load_execution_registry(environment="test"))


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", [False, True])
async def test_planning_initial_and_revision_use_one_call_and_derive_system_fields(revision):
    request = _request(revision=revision)
    model = RecordingModel(
        result=ModelTurnResult(
            content="",
            toolCalls=[],
            structuredOutput=_semantic_plan(),
            usage=ModelUsage(promptTokens=10, cachedTokens=0, completionTokens=20, totalTokens=30),
            diagnostics=ModelUsageDiagnostics(reasoningTokens=6, promptCacheMissTokens=10),
            finishReason="stop",
            rawFinishReason="stop",
        )
    )
    executor = _executor(model)
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    model_request = executor.build_model_request(request, resolved)
    outcome = await executor.call_provider(
        request, model_request, begin_attempt=_one_attempt, cancel_event=asyncio.Event()
    )
    result = executor.terminal_from_outcome(request, resolved, outcome)
    assert result.resultKind == "output"
    assert ChapterPlanResult.model_validate(result.output).beatCount == 1
    assert len(model.requests) == 1
    assert model_request.tools == []
    assert result.usage.providerAttempts == 1
    assert result.usage.completionTokens == 20
    assert result.usage.reasoningTokens == 6
    assert result.usage.visibleOutputTokens == 14
    assert result.usage.promptCacheMissTokens == 10
    assert result.usage.costMicros is None
    assert result.usage.usageStatus == "partial"
    assert json.loads(model_request.messages[1].content)["input"] == request.input


@pytest.mark.parametrize(
    "invalid",
    [
        {"title": " \u3000"},
        {"title": "\ufeff"},
        {"artifactKey": "模型伪造"},
        {"beatCount": 1},
        {"sceneBeats": [{"goal": "目标", "order": 1}]},
        {"totalEstimatedWords": 2147483648},
    ],
)
def test_planning_invalid_provider_output_closes_as_protocol_failure(invalid):
    request = _request()
    model = RecordingModel()
    executor = _executor(model)
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    from inkforge_agents.execution.executor import ProviderCallOutcome

    outcome = ProviderCallOutcome(
        ModelTurnResult(
            content="",
            toolCalls=[],
            structuredOutput=_semantic_plan() | invalid,
            usage=ModelUsage(promptTokens=10, cachedTokens=0, completionTokens=20, totalTokens=30),
            finishReason="stop",
            rawFinishReason="stop",
        ),
        1,
        10,
    )
    result = executor.terminal_from_outcome(request, resolved, outcome)
    assert result.errorCode in {"MODEL_OUTPUT_SCHEMA_INVALID", "MODEL_OUTPUT_PROTOCOL_INVALID"}
    assert result.usage.providerAttempts == 1


def test_planning_missing_required_provider_field_is_rejected():
    request = _request()
    executor = _executor(RecordingModel())
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    incomplete = _semantic_plan()
    del incomplete["summary"]
    from inkforge_agents.execution.executor import ProviderCallOutcome

    result = executor.terminal_from_outcome(
        request,
        resolved,
        ProviderCallOutcome(
            ModelTurnResult(
                content="",
                toolCalls=[],
                structuredOutput=incomplete,
                usage=ModelUsage(
                    promptTokens=10, cachedTokens=0, completionTokens=20, totalTokens=30
                ),
                finishReason="stop",
            ),
            1,
            10,
        ),
    )
    assert result.errorCode == "MODEL_OUTPUT_SCHEMA_INVALID"


def test_planning_revision_rejects_mismatched_artifact_before_provider():
    request = _request(revision=True)
    payload = deepcopy(request.input)
    payload["previousArtifact"]["artifactRevision"] = 2
    request = rehash_request(request.model_copy(update={"input": payload}))
    with pytest.raises(ExecutionCapabilityError, match="候选"):
        _executor(RecordingModel()).resolve(request, load_execution_registry(environment="test"))


@pytest.mark.asyncio
async def test_planning_reviewer_uses_semantic_candidate_and_same_evidence():
    request = _request(reviewer=True)
    model = RecordingModel(
        result=ModelTurnResult(
            content="",
            toolCalls=[],
            structuredOutput={"contentVerdict": "pass", "findings": []},
            usage=ModelUsage(promptTokens=10, cachedTokens=0, completionTokens=20, totalTokens=30),
            finishReason="stop",
            rawFinishReason="stop",
        )
    )
    executor = _executor(model)
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_one_attempt,
        cancel_event=asyncio.Event(),
    )
    result = executor.terminal_from_outcome(request, resolved, outcome)
    assert result.resultKind == "evaluation"
    assert result.evaluation.artifactId == request.artifactId
    assert result.evaluation.evidenceBundleId == request.evidenceBundle.id
    assert result.evaluation.rubricVersion == "rubric.chapter_plan.review.v1"
    assert model.requests[0].policy.thinkingMode == "disabled"
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_planning_cancel_during_provider_keeps_unknown_usage_without_fake_zero():
    request = _request()
    model = RecordingModel(block=True)
    executor = _executor(model)
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    cancelled = asyncio.Event()
    started = asyncio.Event()

    async def begin_attempt():
        started.set()
        return 1

    running = asyncio.create_task(
        executor.call_provider(
            request,
            executor.build_model_request(request, resolved),
            begin_attempt=begin_attempt,
            cancel_event=cancelled,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    cancelled.set()
    outcome = await asyncio.wait_for(running, timeout=1)
    result = executor.terminal_from_outcome(
        request,
        resolved,
        outcome,
        cancel_request_id="cancel-plan-1",
    )
    assert result.errorCode == "RUN_CANCELLED"
    assert result.cancelRequestId == "cancel-plan-1"
    assert result.usage.usageStatus == "unknown"
    assert result.usage.providerAttempts == 1
    assert result.usage.completionTokens is None
    assert len(model.requests) == 1
