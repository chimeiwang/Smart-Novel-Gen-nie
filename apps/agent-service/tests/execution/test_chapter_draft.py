from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import pytest
from inkforge_agents.execution.executor import (
    ExecutionCapabilityError,
    StatelessExecutionStepExecutor,
)
from inkforge_agents.execution.registry import load_execution_registry
from inkforge_agents.providers.base import ModelTurnResult, ModelUsage, ModelUsageDiagnostics
from inkforge_contracts.execution import (
    ChapterDraftResult,
    ModelProfileRef,
    OutputSchemaRef,
    PromptProfileRef,
    StepBudget,
    materialize_chapter_draft_output,
)

from .support import rehash_request
from .test_chapter_plan import _context_item, _with_evidence
from .test_chapter_plan import _request as plan_request
from .test_executor import RecordingModel, _one_attempt


def _draft():
    return {"summary": "完整写章说明", "content": "\ufeff 夜里，林舟推开门。\n😀\u0085"}


def _request(
    *, reviewer: str | None = None, revision: bool = False, operation_name: str = "write_chapter"
):
    operation = load_execution_registry(environment="test").resolve("long_serial", operation_name)
    profile = (
        next(p for p in operation.reviewer_profiles if p.key == reviewer)
        if reviewer
        else operation.generator_profile
    )
    schema = operation.reviewer_output_schema if reviewer else operation.output_schema
    budget = (
        operation.reviewer_step_budgets[profile.key]
        if reviewer
        else operation.generator_step_budget
    )
    payload = {"userInstruction": "  写完整正文\n", "targetWordCount": 4000}
    if revision:
        payload |= {
            "originalUserInstruction": "最初要求A",
            "previousArtifact": {
                "artifactId": "artifact-plan-1",
                "artifactRevision": 1,
                "payload": materialize_chapter_draft_output(_draft()),
            },
        }
    if reviewer:
        payload = {
            "task": {
                "workflow": "long_serial",
                "operation": operation_name,
                "userInstruction": "本轮修改要求B",
                "originalUserInstruction": "最初要求A",
                "targetWordCount": 4000,
                "rubricVersion": operation.operation.review_policy.rubric_version,
            },
            "candidate": materialize_chapter_draft_output(_draft()),
        }
    base = plan_request(revision=revision, reviewer=bool(reviewer))
    candidate = base.model_copy(
        update={
            "operation": operation_name,
            "input": payload,
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
            "budget": StepBudget.model_validate(
                {
                    "maxModelCalls": budget.max_model_calls,
                    "maxInputTokens": budget.max_input_tokens,
                    "maxPromptCacheMissTokens": budget.max_prompt_cache_miss_tokens,
                    "maxCompletionTokens": budget.max_completion_tokens,
                    "maxReasoningTokens": budget.max_reasoning_tokens,
                    "maxVisibleOutputTokens": budget.max_visible_output_tokens,
                    "maxCostMicros": budget.max_cost_micros,
                    "maxWallClockSeconds": budget.max_wall_clock_seconds,
                    "maxProviderRetries": budget.max_provider_retries,
                    "maxProtocolCorrections": budget.max_protocol_corrections,
                }
            ),
            "evidenceBundle": base.evidenceBundle.model_copy(
                update={
                    "policyVersion": operation.operation.review_policy.evidence_policy
                    if reviewer
                    else operation.operation.evidence_policy,
                }
            ),
        }
    )
    return _with_evidence(
        candidate,
        [
            _context_item(
                resourceType="chapter_writing_context",
                metadata={"role": "chapter_writing_context"},
                contentJson={
                    "schemaVersion": 1,
                    "novelId": "novel-1",
                    "currentChapter": {"id": "chapter-1", "content": "原文"},
                },
            )
        ],
    )


def _executor(model):
    return StatelessExecutionStepExecutor(model, max_output_tokens=20_000, retry_base_seconds=0)


def _result(output, *, finish="stop", input_tokens=12_000):
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


def test_draft_catalog_has_six_cold_calls_and_dedicated_review_profiles():
    operation = load_execution_registry(environment="test").resolve("long_serial", "write_chapter")
    assert [p.key for p in operation.reviewer_profiles] == [
        "reviewer.chapter_draft_consistency.v1",
        "reviewer.chapter_draft_editorial.v1",
    ]
    assert (
        operation.operation.review_policy.merge_policy == "review.chapter_draft.patch_or_author.v1"
    )
    assert operation.operation.run_budget.max_model_calls == 6
    assert operation.operation.run_budget.max_prompt_cache_miss_tokens == 180_000
    assert all("选区外" not in p.prompt_profile.system_prompt for p in operation.reviewer_profiles)


@pytest.mark.asyncio
async def test_scene_rewrite_reuses_complete_chapter_result_with_distinct_profile():
    request = _request(operation_name="rewrite_scene")
    operation = load_execution_registry(environment="test").resolve("long_serial", "rewrite_scene")
    assert operation.generator_profile.key == "writer.scene_rewrite.v1"
    assert [profile.key for profile in operation.reviewer_profiles] == [
        "reviewer.chapter_draft_consistency.v1",
        "reviewer.chapter_draft_editorial.v1",
    ]
    model = RecordingModel(result=_result(_draft()))
    executor = _executor(model)
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_one_attempt,
        cancel_event=asyncio.Event(),
    )
    assert (
        ChapterDraftResult.model_validate(
            executor.terminal_from_outcome(request, resolved, outcome).output
        ).content
        == _draft()["content"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", [False, True])
async def test_draft_generates_complete_result_once_and_preserves_revision_input(revision):
    request = _request(revision=revision)
    output = _draft() | {"content": "完整正文😀\n" * 1500}
    model = RecordingModel(result=_result(output))
    executor = _executor(model)
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=_one_attempt,
        cancel_event=asyncio.Event(),
    )
    terminal = executor.terminal_from_outcome(request, resolved, outcome)
    assert terminal.resultKind == "output"
    assert ChapterDraftResult.model_validate(terminal.output).content == output["content"]
    assert terminal.usage.promptCacheMissTokens == 12_000
    assert len(model.requests) == terminal.usage.providerAttempts == 1
    assert json.loads(model.requests[0].messages[1].content)["input"] == request.input
    assert model.requests[0].tools == []


@pytest.mark.parametrize(
    "reviewer", ["reviewer.chapter_draft_consistency.v1", "reviewer.chapter_draft_editorial.v1"]
)
@pytest.mark.parametrize("patch", [None, {"kind": "text_replace", "find": "推开", "replace": ""}])
def test_draft_reviews_keep_current_and_original_instruction_and_optional_structured_patch(
    reviewer, patch
):
    from inkforge_agents.execution.executor import ProviderCallOutcome

    request = _request(reviewer=reviewer)
    item = request.evidenceBundle.items[0]
    finding = {
        "dimension": "chapter_draft.local",
        "severity": "warning",
        "claim": "重复描写",
        "candidateRange": None,
        "evidence": [
            {"evidenceItemId": item.id, "contentSha256": item.contentSha256, "range": None}
        ],
        "suggestion": "删除重复",
        "confidence": 0.9,
    }
    if patch is not None:
        finding["candidatePatch"] = patch
    executor = _executor(RecordingModel())
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    model_request = executor.build_model_request(request, resolved)
    assert json.loads(model_request.messages[1].content)["input"] == request.input
    terminal = executor.terminal_from_outcome(
        request,
        resolved,
        ProviderCallOutcome(
            _result({"contentVerdict": "issues_found", "findings": [finding]}), 1, 20
        ),
    )
    assert terminal.resultKind == "evaluation"
    dumped = terminal.evaluation.model_dump(mode="json")["findings"][0]
    assert dumped.get("candidatePatch") == patch
    assert ("candidatePatch" in dumped) == (patch is not None)


@pytest.mark.parametrize(
    "change",
    [
        {"summary": "\ufeff\u0085"},
        {"content": " "},
        {"wordCount": 1},
        {"contentSha256": "a" * 64},
    ],
)
def test_draft_invalid_provider_output_fails_without_partial_candidate(change):
    from inkforge_agents.execution.executor import ProviderCallOutcome

    request = _request()
    executor = _executor(RecordingModel())
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    terminal = executor.terminal_from_outcome(
        request, resolved, ProviderCallOutcome(_result(_draft() | change), 1, 20)
    )
    assert terminal.errorCode in {"MODEL_OUTPUT_SCHEMA_INVALID", "MODEL_OUTPUT_PROTOCOL_INVALID"}
    assert terminal.usage.providerAttempts == 1


@pytest.mark.parametrize("finish", ["length", "content_filter", "unknown"])
def test_draft_incomplete_finish_is_not_success(finish):
    from inkforge_agents.execution.executor import ProviderCallOutcome

    request = _request()
    executor = _executor(RecordingModel())
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    terminal = executor.terminal_from_outcome(
        request, resolved, ProviderCallOutcome(_result(_draft(), finish=finish), 1, 20)
    )
    assert terminal.errorCode in {
        "MODEL_OUTPUT_TRUNCATED",
        "MODEL_OUTPUT_FILTERED",
        "MODEL_FINISH_REASON_INVALID",
    }


@pytest.mark.parametrize(
    "context",
    [
        None,
        {},
        {"schemaVersion": True},
        {"schemaVersion": 1, "novelId": "other", "currentChapter": {"id": "chapter-1"}},
        {"schemaVersion": 1, "novelId": "novel-1", "currentChapter": {"id": "other"}},
    ],
)
def test_draft_requires_exact_context_identity_before_provider(context):
    request = _request()
    items = (
        plan_request().evidenceBundle.items
        if context is None
        else [_context_item(resourceType="chapter_writing_context", contentJson=context)]
    )
    request = _with_evidence(request, items)
    with pytest.raises(ExecutionCapabilityError, match="Evidence"):
        _executor(RecordingModel()).resolve(request, load_execution_registry(environment="test"))


def test_draft_revision_cannot_swap_previous_artifact():
    request = _request(revision=True)
    payload = deepcopy(request.input)
    payload["previousArtifact"]["artifactRevision"] = 2
    with pytest.raises(ExecutionCapabilityError):
        _executor(RecordingModel()).resolve(
            rehash_request(request.model_copy(update={"input": payload})),
            load_execution_registry(environment="test"),
        )


@pytest.mark.asyncio
async def test_draft_real_fake_cold_context_generates_then_both_reviewers_consume_full_candidate():
    context = {
        "schemaVersion": 1,
        "novelId": "novel-1",
        "currentChapter": {"id": "chapter-1", "content": "冻结正文。" * 2200},
    }
    items = [_context_item(resourceType="chapter_writing_context", contentJson=context)]
    model = RecordingModel()  # 未预设响应，真实调用 FakeModelProvider 及其计量。
    executor = _executor(model)
    registry = load_execution_registry(environment="test")
    request = _with_evidence(_request(), items)
    resolved = executor.resolve(request, registry)
    generated = executor.terminal_from_outcome(
        request,
        resolved,
        await executor.call_provider(
            request,
            executor.build_model_request(request, resolved),
            begin_attempt=_one_attempt,
            cancel_event=asyncio.Event(),
        ),
    )
    assert generated.resultKind == "output"
    assert 10_000 < generated.usage.promptCacheMissTokens < 30_000
    for role in ("consistency", "editorial"):
        review = _with_evidence(_request(reviewer=f"reviewer.chapter_draft_{role}.v1"), items)
        review = rehash_request(
            review.model_copy(update={"input": review.input | {"candidate": generated.output}})
        )
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
        assert reviewed.resultKind == "evaluation"
        assert reviewed.evaluation.contentVerdict == "pass"
        assert reviewed.evaluation.evidenceBundleId == request.evidenceBundle.id
        assert 10_000 < reviewed.usage.promptCacheMissTokens < 30_000
        assert reviewed.usage.cachedTokens == 0
        assert reviewed.usage.providerAttempts == 1
        assert (
            json.loads(model.requests[-1].messages[1].content)["input"]["candidate"]
            == generated.output
        )
    assert len(model.requests) == 3


@pytest.mark.parametrize("reviewer", [None, "reviewer.chapter_draft_consistency.v1"])
def test_draft_large_complete_input_over_budget_is_rejected_without_call_or_truncation(reviewer):
    content = "原" * 30_001
    request = _with_evidence(
        _request(reviewer=reviewer),
        [
            _context_item(
                resourceType="chapter_writing_context",
                contentJson={
                    "schemaVersion": 1,
                    "novelId": "novel-1",
                    "currentChapter": {"id": "chapter-1", "content": content},
                },
            )
        ],
    )
    model = RecordingModel()
    executor = _executor(model)
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    with pytest.raises(ExecutionCapabilityError, match="完整模型输入超过"):
        executor.build_model_request(request, resolved)
    assert model.requests == []
    assert request.evidenceBundle.items[0].contentJson["currentChapter"]["content"] == content


@pytest.mark.asyncio
async def test_draft_inflight_cancellation_keeps_one_attempt_and_unknown_usage():
    request = _request()
    executor = _executor(RecordingModel(block=True))
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
    started, cancelled = asyncio.Event(), asyncio.Event()

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
    terminal = executor.terminal_from_outcome(
        request,
        resolved,
        await asyncio.wait_for(running, timeout=1),
        cancel_request_id="cancel-writing-1",
    )
    assert terminal.errorCode == "RUN_CANCELLED"
    assert terminal.usage.providerAttempts == 1
    assert terminal.usage.usageStatus == "unknown"
    assert terminal.usage.completionTokens is None
