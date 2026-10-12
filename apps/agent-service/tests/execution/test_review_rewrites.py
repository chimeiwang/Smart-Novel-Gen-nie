from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from inkforge_agents.execution.executor import (
    ExecutionCapabilityError,
    ProviderCallOutcome,
    StatelessExecutionStepExecutor,
)
from inkforge_agents.execution.registry import load_execution_registry
from inkforge_agents.providers.fake import (
    FAKE_CHAPTER_REVIEW_REPORT,
    FAKE_OUTLINE_SELECTION_REPLACEMENT,
)
from inkforge_contracts import ChapterReviewOutput, OutlineSelectionResult
from inkforge_contracts.execution import (
    EvidenceRange,
    ModelProfileRef,
    OutputSchemaRef,
    PromptProfileRef,
    StepBudget,
    canonical_execution_json_bytes,
    canonical_execution_sha256,
)

from .support import rehash_request
from .test_chapter_draft import _request as draft_request
from .test_chapter_plan import _with_evidence
from .test_executor import RecordingModel


def _request(operation_name: str, input_value: dict, *, outline: bool = False):
    registry = load_execution_registry(environment="test")
    operation = registry.resolve("long_serial", operation_name)
    profile, schema, budget = (
        operation.generator_profile,
        operation.output_schema,
        operation.generator_step_budget,
    )
    base = draft_request(operation_name="rewrite_scene")
    candidate = base.model_copy(
        update={
            "operation": operation_name,
            "input": input_value,
            "lane": operation.operation.lane,
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
                update={"policyVersion": operation.operation.evidence_policy}
            ),
        }
    )
    if not outline:
        return rehash_request(candidate)
    source = "旧剧情单元"
    target = input_value["selectionTarget"]
    item = base.evidenceBundle.items[0].model_copy(
        update={
            "resourceType": "outline_content",
            "resourceId": "outline-1",
            "contentType": "text",
            "contentText": source,
            "contentJson": None,
            "contentSha256": hashlib.sha256(source.encode()).hexdigest(),
            "byteCount": len(source.encode()),
            "resourceUpdatedAt": datetime(2026, 9, 5, tzinfo=UTC),
            "range": EvidenceRange(startCodePoint=0, endCodePoint=len(source)),
            "metadata": {
                "role": "selection_source",
                "selectedTextHash": target["selectedTextHash"],
            },
        }
    )
    return _with_evidence(candidate, [item])


def _terminal(request):
    executor = StatelessExecutionStepExecutor(RecordingModel(), max_output_tokens=20_000)
    registry = load_execution_registry(environment="test")
    resolved = executor.resolve(request, registry)
    output = (
        {"report": FAKE_CHAPTER_REVIEW_REPORT}
        if request.operation == "review_chapter"
        else {"replacement": FAKE_OUTLINE_SELECTION_REPLACEMENT}
    )
    from .test_chapter_draft import _result

    return executor.terminal_from_outcome(
        request, resolved, ProviderCallOutcome(_result(output), 1, 20)
    )


def test_chapter_review_returns_plain_complete_report_without_evaluation_or_artifact():
    terminal = _terminal(_request("review_chapter", {"userInstruction": "完整审阅"}))
    assert ChapterReviewOutput.model_validate(terminal.output).report == FAKE_CHAPTER_REVIEW_REPORT
    assert terminal.evaluation is None


@pytest.mark.parametrize("mutation", ["extra_evidence", "boolean_schema_version"])
def test_chapter_review_rejects_non_unique_or_boolean_context_before_provider(
    mutation: str,
) -> None:
    request = _request("review_chapter", {"userInstruction": "完整审阅"})
    items = list(request.evidenceBundle.items)
    if mutation == "extra_evidence":
        extra = items[0].model_copy(
            update={
                "id": "evidence-extra",
                "ordinal": 2,
                "resourceType": "chapter_content",
            }
        )
        request = _with_evidence(request, [*items, extra])
    else:
        context = dict(items[0].contentJson or {})
        context["schemaVersion"] = True
        encoded = canonical_execution_json_bytes(context)
        item = items[0].model_copy(
            update={
                "contentJson": context,
                "contentSha256": canonical_execution_sha256(context),
                "byteCount": len(encoded),
            }
        )
        request = _with_evidence(request, [item])
    model = RecordingModel()
    executor = StatelessExecutionStepExecutor(model, max_output_tokens=20_000)

    with pytest.raises(ExecutionCapabilityError, match="完整上下文身份"):
        executor.resolve(request, load_execution_registry(environment="test"))

    assert model.requests == []


def test_outline_selection_returns_hash_bound_replacement():
    source = "旧剧情单元"
    request = _request(
        "rewrite_outline_selection",
        {
            "userInstruction": "改写选区",
            "selectionTarget": {
                "resourceType": "outline_content",
                "resourceId": "outline-1",
                "baseUpdatedAt": "2026-09-05T00:00:00Z",
                "baseContentHash": hashlib.sha256(source.encode()).hexdigest(),
                "selectionStart": 0,
                "selectionEnd": len(source),
                "selectedTextHash": hashlib.sha256(source.encode()).hexdigest(),
            },
        },
        outline=True,
    )
    terminal = _terminal(request)
    assert OutlineSelectionResult.model_validate(terminal.output).replacement == (
        FAKE_OUTLINE_SELECTION_REPLACEMENT
    )


def test_outline_selection_rejects_range_past_full_source_before_provider() -> None:
    source = "旧剧情单元"
    selected = source[1:]
    original = _request(
        "rewrite_outline_selection",
        {
            "userInstruction": "改写选区",
            "selectionTarget": {
                "resourceType": "outline_content",
                "resourceId": "outline-1",
                "baseUpdatedAt": "2026-09-05T00:00:00Z",
                "baseContentHash": hashlib.sha256(source.encode()).hexdigest(),
                "selectionStart": 0,
                "selectionEnd": len(source),
                "selectedTextHash": hashlib.sha256(source.encode()).hexdigest(),
            },
        },
        outline=True,
    )
    target = dict(original.input["selectionTarget"])
    target.update(
        selectionStart=1,
        selectionEnd=99,
        selectedTextHash=hashlib.sha256(selected.encode()).hexdigest(),
    )
    item = original.evidenceBundle.items[0].model_copy(
        update={
            "range": EvidenceRange(startCodePoint=1, endCodePoint=99),
            "metadata": {
                "role": "selection_source",
                "selectedTextHash": target["selectedTextHash"],
            },
        }
    )
    request = _with_evidence(
        original.model_copy(
            update={
                "input": {"userInstruction": "改写选区", "selectionTarget": target}
            }
        ),
        [item],
    )
    model = RecordingModel()
    executor = StatelessExecutionStepExecutor(model, max_output_tokens=20_000)

    with pytest.raises(ExecutionCapabilityError, match="Evidence"):
        executor.resolve(request, load_execution_registry(environment="test"))

    assert model.requests == []
