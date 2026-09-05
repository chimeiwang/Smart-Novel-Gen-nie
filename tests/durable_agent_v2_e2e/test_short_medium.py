"""中短篇隔离场景与确定性 Provider 的离线自检。"""

from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from inkforge_agents.providers.base import (
    ModelExecutionPolicy,
    ModelMessage,
    ModelStructuredOutputRequest,
    ModelTurnRequest,
)
from inkforge_contracts.short_medium_execution import ShortMediumContextV2

from . import controlled_provider
from .short_medium import _adopt, _facts, _submit_initial_manuscript, assert_short_facts
from .short_medium_fixture import (
    OPENING,
    OUTLINE,
    REPLACEMENT,
    REPORT,
    SHORT_PROFILES,
    manuscript_segment,
    sha,
    short_medium_output,
)


def test_controlled_provider_imports_from_same_flat_directory_as_compose(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    module = importlib.import_module("controlled_provider")
    assert module.ControlledFakeModelProvider.provider_name == "fake"
    assert callable(module.short_medium_output)


def _request(operation, *, index=0, count=2):
    context = dict.fromkeys(ShortMediumContextV2.model_fields)
    context.update(
        workflow="short_medium",
        operation=operation,
        documentType="outline" if operation == "generate_outline" else "manuscript",
        chapterId=None if operation == "generate_outline" else "chapter-1",
        userInstruction="完整指令",
        targetTotalWordCount=15001,
        sourceKind="opening",
        sourceText=OPENING,
    )
    if operation != "generate_outline":
        context.update(
            sourceOutlineVersionId="outline-1",
            sourceOutlineContent=OUTLINE,
            sourceOutlineContentHash=sha(OUTLINE),
        )
    if operation in {"replace_selection", "full_check"}:
        context.update(baseVersionId="base-1", baseContent="前😀后", baseContentHash=sha("前😀后"))
    if operation == "replace_selection":
        context.update(
            selectionStart=1,
            selectionEnd=2,
            selectedText="😀",
            selectedTextHash=sha("😀"),
            contextBefore="前",
            contextAfter="后",
        )
    if operation != "generate_manuscript":
        count = 1
    items = [{"resourceType": "short_medium_context", "contentJson": context}]
    for prior in range(index):
        content = manuscript_segment(prior, count, source_kind="opening", source_text=OPENING)
        items.append(
            {
                "resourceType": "short_medium_segment",
                "resourceId": f"producer-{prior}",
                "contentJson": {"index": prior, "content": content, "contentSha256": sha(content)},
            }
        )
    profile, (_, schema) = next(
        (key, value) for key, value in SHORT_PROFILES.items() if value[0] == operation
    )
    field = (
        "replacement"
        if operation == "replace_selection"
        else "text"
        if operation == "full_check"
        else "content"
    )
    return ModelTurnRequest(
        messages=[
            ModelMessage(
                role="user",
                content=json.dumps(
                    {
                        "workflow": "short_medium",
                        "operation": operation,
                        "purpose": "generation",
                        "input": {"segmentIndex": index, "segmentCount": count},
                        "evidenceBundle": {"items": items},
                    },
                    ensure_ascii=False,
                ),
            )
        ],
        tools=[],
        maxOutputTokens=40000,
        policy=ModelExecutionPolicy(
            policyId=profile,
            thinkingMode="disabled" if operation == "full_check" else "enabled",
            reasoningEffort=None if operation == "full_check" else "high",
        ),
        structuredOutput=ModelStructuredOutputRequest(
            route="responses_json_schema_v1",
            name=schema,
            jsonSchema={
                "type": "object",
                "required": [field],
                "properties": {field: {"type": "string", "minLength": 1}},
            },
        ),
        requestIdempotencyKey="provider-short-1",
    )


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("generate_outline", {"content": OUTLINE}),
        ("replace_selection", {"replacement": REPLACEMENT}),
        ("full_check", {"text": REPORT}),
    ],
)
def test_fixture_only_returns_exact_semantic_text(operation, expected):
    assert short_medium_output(_request(operation)) == expected


def test_second_segment_requires_complete_prior_prefix_not_tail_summary():
    request = _request("generate_manuscript", index=1)
    assert short_medium_output(request) == {
        "content": manuscript_segment(1, 2, source_kind="opening", source_text=OPENING)
    }
    envelope = json.loads(request.messages[0].content)
    previous = envelope["evidenceBundle"]["items"][1]["contentJson"]
    previous["content"] = previous["content"][-100:]
    previous["contentSha256"] = sha(previous["content"])
    request.messages[0].content = json.dumps(envelope, ensure_ascii=False)
    with pytest.raises(ValueError, match="完整已完成前缀"):
        short_medium_output(request)


class _ControlClient:
    calls = []

    def __init__(self, **_kwargs):
        self.calls.clear()

    async def post(self, path, *, json):
        self.calls.append((path, json))
        return httpx.Response(200, json={}, request=httpx.Request("POST", "http://control" + path))

    async def aclose(self):
        pass


@pytest.mark.parametrize("operation", [value[0] for value in SHORT_PROFILES.values()])
@pytest.mark.asyncio
async def test_controlled_provider_uses_existing_gate_and_never_sends_text_to_controller(
    monkeypatch, operation
):
    monkeypatch.setattr(controlled_provider.httpx, "AsyncClient", _ControlClient)
    provider = controlled_provider.ControlledFakeModelProvider(
        control_url="http://control", control_token="t" * 40
    )
    request = _request(operation)
    result = await provider.complete_turn(request)
    assert result.structuredOutput == short_medium_output(request)
    assert result.finishReason == "stop"
    assert result.diagnostics.reasoningTokens == 0
    assert [path for path, _ in _ControlClient.calls] == [
        "/control/provider/reached",
        "/control/provider/completed",
    ]
    assert all(set(body) == {"idempotencyKey", "requestSha256"} for _, body in _ControlClient.calls)
    assert result.usage.completionTokens <= request.maxOutputTokens
    await provider.aclose()


def good_facts():
    return {
        "engineVersion": 2,
        "workflow": "short_medium",
        "operation": "generate_manuscript",
        "status": "completed",
        "legacyTaskCount": 0,
        "legacyCommandCount": 0,
        "artifactCount": 1,
        "candidateVersionId": "candidate-1",
        "modelCount": 2,
        "manifestCount": 1,
        "completedEventCount": 1,
        "evaluationCount": 0,
        "reservationCount": 2,
        "matchedBillingCount": 2,
        "tokenUsageCount": 2,
    }


@pytest.mark.parametrize("field", list(good_facts()))
def test_short_fact_assertion_rejects_every_missing_authoritative_field(field):
    facts = good_facts()
    assert_short_facts(
        facts, operation="generate_manuscript", model_count=2, candidate_id="candidate-1"
    )
    facts.pop(field)
    with pytest.raises(AssertionError):
        assert_short_facts(
            facts, operation="generate_manuscript", model_count=2, candidate_id="candidate-1"
        )


def test_fact_collector_verifies_real_producer_ids_and_does_not_return_body():
    contents = ["第一完整段😀\n", "第二完整段🚀\n"]
    steps = [
        {
            "id": f"step-{i}",
            "status": "completed",
            "input": {"segmentIndex": i, "segmentCount": 2},
            "output": {"content": content, "contentSha256": sha(content)},
            "resultHash": f"result-{i}",
            "requestHash": f"request-{i}",
            "bundleId": f"bundle-{i}",
            "fencingToken": 1,
            "idempotencyKey": f"provider-{i}",
        }
        for i, content in enumerate(contents)
    ]
    raw = good_facts() | {
        "steps": steps,
        "manifest": {
            "segmentCount": 2,
            "contentSha256": sha("".join(contents)),
            "segments": [
                {
                    "index": i,
                    "stepId": step["id"],
                    "contentSha256": sha(contents[i]),
                    "resultHash": step["resultHash"],
                }
                for i, step in enumerate(steps)
            ],
        },
        "manifestOutput": {"candidateVersionId": "candidate-1"},
        "evidence": [
            {"bundleId": f"bundle-{i}", "ordinal": 1, "resourceType": "short_medium_context"}
            for i in range(2)
        ]
        + [
            {
                "bundleId": "bundle-1",
                "ordinal": 2,
                "resourceType": "short_medium_segment",
                "resourceId": "step-0",
                "content": {"index": 0, "content": contents[0], "contentSha256": sha(contents[0])},
            }
        ],
    }
    acceptance = SimpleNamespace(
        stack=SimpleNamespace(psql=lambda *_args, **_kwargs: json.dumps(raw)),
        wait_delivered_journal=lambda identity: {
            "requestHash": "request-" + identity[-1],
            "resultHash": "result-" + identity[-1],
            "fencingToken": 1,
        },
    )
    facts = _facts(
        acceptance,
        "run-1",
        operation="generate_manuscript",
        expected_text="".join(contents),
        model_count=2,
        candidate_id="candidate-1",
    )
    assert facts["fullPrefixVerified"] is True
    assert all(content not in json.dumps(facts, ensure_ascii=False) for content in contents)
    raw["evidence"][-1]["resourceId"] = "unrelated-step"
    with pytest.raises(AssertionError, match="真实已完成段"):
        _facts(
            acceptance,
            "run-1",
            operation="generate_manuscript",
            expected_text="".join(contents),
            model_count=2,
            candidate_id="candidate-1",
        )


def test_adoption_uses_get_confirmation_hash_and_replays_same_public_request():
    content = "完整候选😀\n"
    detail = {
        "id": "candidate-1",
        "status": "awaiting_user",
        "content": content,
        "contentHash": sha(content),
        "payload": {"sourceTaskId": "run-1"},
        "taskId": None,
        "diff": {"confirmationHash": "a" * 64},
    }
    applied = detail | {"status": "applied"}
    replies = [detail, applied, deepcopy(applied), {"content": content}]
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return SimpleNamespace(json=lambda: replies.pop(0))

    acceptance = SimpleNamespace(novel_id="novel-1", chapter_id="chapter-1", request=request)
    _adopt(
        acceptance,
        run_id="run-1",
        candidate="candidate-1",
        document="manuscript",
        base=None,
        expected_content=content,
        key="e2e-short-adopt-0001",
    )
    assert calls[1] == calls[2]
    assert calls[1][2]["json_body"]["confirmationHash"] == "a" * 64


def _initial_manuscript_acceptance(*, source_outline="outline-applied"):
    preview = {
        "documentType": "manuscript",
        "chapterId": "chapter-1",
        "baseVersionId": None,
        "expectedUpdatedAt": "2026-09-05T11:00:00Z",
        "contentHash": sha(OPENING),
        "confirmationHash": "a" * 64,
        "dirty": True,
    }
    submitted = {
        "id": "manual-base-1",
        "status": "applied",
        "source": "manual",
        "content": OPENING,
        "contentHash": sha(OPENING),
        "baseVersionId": None,
        "sourceOutlineVersionId": source_outline,
        "payload": {"sourceOutlineVersionId": source_outline},
    }
    replies = [
        {"id": "chapter-1", "content": OPENING},
        preview,
        submitted,
        preview | {"baseVersionId": "manual-base-1", "dirty": False},
    ]
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return SimpleNamespace(json=lambda: replies.pop(0))

    return SimpleNamespace(
        novel_id="novel-1", chapter_id="chapter-1", request=request, safe_diagnostics={}
    ), calls


def test_initial_opening_work_draft_is_manually_versioned_before_agent_start():
    acceptance, calls = _initial_manuscript_acceptance()
    assert _submit_initial_manuscript(acceptance, "outline-applied") == "manual-base-1"
    assert [(method, path) for method, path, _ in calls] == [
        ("GET", "/api/v1/chapters/chapter-1"),
        ("POST", "/api/v1/novels/novel-1/versions/preview"),
        ("POST", "/api/v1/novels/novel-1/versions"),
        ("POST", "/api/v1/novels/novel-1/versions/preview"),
    ]
    body = calls[2][2]["json_body"]
    assert body["baseVersionId"] is None
    assert body["expectedUpdatedAt"] == "2026-09-05T11:00:00Z"
    assert body["contentHash"] == sha(OPENING)
    assert body["confirmationHash"] == "a" * 64
    assert "sourceOutlineVersionId" not in body
    assert "content" not in body
    assert calls[3][2]["json_body"]["baseVersionId"] == "manual-base-1"
    assert OPENING not in json.dumps(acceptance.safe_diagnostics, ensure_ascii=False)


def test_initial_manual_version_must_bind_the_actual_applied_outline():
    acceptance, calls = _initial_manuscript_acceptance(source_outline="unrelated-outline")
    with pytest.raises(AssertionError, match="已采用蓝图"):
        _submit_initial_manuscript(acceptance, "outline-applied")
    assert len(calls) == 3
