"""质量隔离验收的受控响应、持久事实断言和观察恢复离线自检。"""

from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from inkforge_agents.execution.quality import quality_response
from inkforge_agents.providers.base import (
    ModelExecutionPolicy,
    ModelMessage,
    ModelTool,
    ModelTurnRequest,
)
from inkforge_contracts.quality import ConsistencyQualityReport

from . import controlled_provider
from .quality import _facts, assert_quality_facts
from .quality_fixture import (
    CORRECTION_CODE,
    CORRECTION_MARKER,
    REPORT,
    quality_report,
    quality_turn_result,
    sha,
)
from .run_e2e import Acceptance


def _request(*, correction=False, purpose="generation"):
    instruction = "检查本章一致性" + ("：" + CORRECTION_MARKER if correction else "")
    context = {
        "checkId": "check-1",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "chapterContent": "完整原文😀\r\n",
        "chapterContentSha256": sha("完整原文😀\r\n"),
        "sourceUpdatedAt": "2026-09-05T01:00:00Z",
        "message": instruction,
        "sourceTaskId": None,
    }
    input_value = {"userInstruction": instruction}
    if purpose == "protocol_correction":
        input_value.update(
            failedStepId="step-1", failedResultHash="a" * 64, failureCode=CORRECTION_CODE
        )
    profile = (
        "system.quality_protocol_corrector.v2"
        if purpose == "protocol_correction"
        else "quality.consistency.v2"
    )
    return ModelTurnRequest(
        messages=[
            ModelMessage(
                role="user",
                content=json.dumps(
                    {
                        "workflow": "quality",
                        "operation": "consistency",
                        "purpose": purpose,
                        "input": input_value,
                        "evidenceBundle": {
                            "items": [
                                {
                                    "resourceType": "quality_context",
                                    "resourceId": "check-1",
                                    "contentJson": context,
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                ),
            )
        ],
        tools=[
            ModelTool(
                name="submit_quality_report",
                description="返回完整一致性报告",
                strict=True,
                parameters=ConsistencyQualityReport.model_json_schema(),
            )
        ],
        requiredToolName="submit_quality_report",
        maxOutputTokens=8000,
        policy=ModelExecutionPolicy(policyId=profile, thinkingMode="disabled"),
        requestIdempotencyKey="run-1.step-1",
    )


@pytest.mark.parametrize("purpose", ["generation", "protocol_correction"])
def test_fixture_only_first_generation_has_safe_invalid_tool_diagnostic(purpose):
    result = quality_turn_result(_request(correction=True, purpose=purpose))
    assert result.finishReason == "tool_calls"
    assert result.structuredOutput is None
    assert result.diagnostics.promptCacheMissTokens == result.usage.promptTokens
    assert result.diagnostics.reasoningTokens == 0
    assert result.usage.completionTokens <= 8000
    report, correctable = quality_response(result)
    if purpose == "generation":
        assert report is None and correctable is True
        assert result.toolCalls == []
        assert result.invalidToolCallCount == 1
        assert result.invalidToolCallNames == ["submit_quality_report"]
        assert result.invalidToolCallCodes == ["json_decode_error"]
        assert result.invalidToolCallArgumentCharacterCounts == [99]
        assert REPORT not in result.model_dump_json()
    else:
        assert correctable is False
        assert report == quality_report(correction=True)
        assert result.invalidToolCallCount == 0
        assert report["qualityGate"] == "revise"


def test_normal_fixture_returns_full_pass_report():
    result = quality_turn_result(_request())
    assert quality_response(result) == (quality_report(correction=False), False)
    assert result.toolCalls[0].arguments["report"].endswith("完整一致性报告尾部🚀")


@pytest.mark.parametrize("mutation", ["source_hash", "source_id", "purpose", "partial_correction"])
def test_fixture_rejects_mismatched_frozen_input(mutation):
    request = _request(correction=True, purpose="protocol_correction")
    envelope = json.loads(request.messages[0].content)
    if mutation == "source_hash":
        envelope["evidenceBundle"]["items"][0]["contentJson"]["chapterContent"] = "被替换正文"
    elif mutation == "source_id":
        envelope["evidenceBundle"]["items"][0]["resourceId"] = "another-check"
    elif mutation == "purpose":
        envelope["purpose"] = "generation"
    else:
        envelope["input"].pop("failedResultHash")
    request.messages[0].content = json.dumps(envelope, ensure_ascii=False)
    with pytest.raises(ValueError):
        quality_turn_result(request)


def test_fixture_can_be_imported_by_flat_compose_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    assert callable(importlib.import_module("controlled_provider").quality_turn_result)


class _ControlClient:
    calls = []

    def __init__(self, **_kwargs):
        self.calls.clear()

    async def post(self, path, *, json):
        self.calls.append((path, json))
        return httpx.Response(200, json={}, request=httpx.Request("POST", "http://control" + path))

    async def aclose(self):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("correction", [False, True])
async def test_controlled_quality_provider_keeps_same_gates_and_only_logs_hashes(
    monkeypatch, correction
):
    monkeypatch.setattr(controlled_provider.httpx, "AsyncClient", _ControlClient)
    provider = controlled_provider.ControlledFakeModelProvider(
        control_url="http://control", control_token="t" * 40
    )
    assert provider.supports_structured_output("quality_strict_tool_v1")
    result = await provider.complete_turn(_request(correction=correction))
    assert result.invalidToolCallCount == int(correction)
    assert [path for path, _ in _ControlClient.calls] == [
        "/control/provider/reached",
        "/control/provider/completed",
    ]
    assert all(set(body) == {"idempotencyKey", "requestSha256"} for _, body in _ControlClient.calls)
    await provider.aclose()


def good_facts(*, correction=True):
    count = 2 if correction else 1
    instruction = "检查本章一致性" + ("：" + CORRECTION_MARKER if correction else "")
    report = quality_report(correction=correction)
    steps = [
        {
            "id": "step-1",
            "purpose": "generation",
            "status": "failed" if correction else "completed",
            "input": {"userInstruction": instruction},
            "output": None if correction else report,
            "errorCode": CORRECTION_CODE if correction else None,
            "profile": "quality.consistency.v2",
            "route": "quality_strict_tool_v1",
            "resultHash": "a" * 64,
            "requestHash": "b" * 64,
            "fencingToken": 1,
            "bundleId": "bundle-1",
            "idempotencyKey": "run-1.step-1",
            "usage": {"providerAttempts": 1, "protocolCorrections": 0},
        }
    ]
    if correction:
        steps.append(
            {
                **steps[0],
                "id": "step-2",
                "purpose": "protocol_correction",
                "status": "completed",
                "profile": "system.quality_protocol_corrector.v2",
                "output": report,
                "errorCode": None,
                "input": {
                    "userInstruction": instruction,
                    "failedStepId": "step-1",
                    "failedResultHash": "a" * 64,
                    "failureCode": CORRECTION_CODE,
                },
                "idempotencyKey": "run-1.step-2",
            }
        )
    return {
        "engineVersion": 2,
        "workflow": "quality",
        "operation": "consistency",
        "kind": "quality_check",
        "sourceType": "quality_check_v2",
        "targetType": "chapter",
        "sourceId": "check-1",
        "targetId": "chapter-1",
        "status": "completed",
        "checkStatus": "completed",
        "chapterStatus": "review",
        "qualityGate": report["qualityGate"],
        "scoreOverall": 82,
        "legacyScores": [None] * 6,
        "publicReport": report["report"],
        "report": report,
        "rewriteBrief": report["rewriteBrief"],
        "chapterContent": "完整原文😀\r\n",
        "plan": {
            "plan": {
                "reviewers": [],
                "systemSteps": [{"purpose": "protocol_correction"}],
                "runBudget": {"maxProtocolCorrectionSteps": 1, "maxModelCalls": 2},
            }
        },
        "stepCount": count,
        "generationCount": 1,
        "correctionCount": int(correction),
        "completedStepCount": 1,
        "failedStepCount": int(correction),
        "artifactStepCount": 0,
        "terminalEventCount": 1,
        "completedEventCount": 1,
        "evidenceCount": 1,
        "completedPayload": {
            "outcomeType": "consistency_quality_report",
            "resultId": steps[-1]["id"],
        },
        "reservationCount": count,
        "tokenUsageCount": count,
        "matchedBillingCount": count,
        "creditLedgerCount": 0,
        "artifactCount": 0,
        "evaluationCount": 0,
        "legacyTaskCount": 0,
        "legacyCommandCount": 0,
        "steps": steps,
        "context": json.loads(_request(correction=correction).messages[0].content)[
            "evidenceBundle"
        ]["items"][0]["contentJson"],
    }


def _acceptance(facts):
    calls = []
    journals = {
        step["id"]: {
            "jobId": step["id"],
            "requestHash": step["requestHash"],
            "resultHash": step["resultHash"],
            "fencingToken": 1,
        }
        for step in facts["steps"]
    }
    attempts = []
    for step in facts["steps"]:
        identity = {
            "run_id": "run-1",
            "step_id": step["id"],
            "job_id": step["id"],
            "fencing_token": 1,
            "request_hash": step["requestHash"],
            "result_hash": step["resultHash"],
            "callback_kind": "failure" if step["status"] == "failed" else "result",
        }
        attempts.append(
            {
                **identity,
                "action": "forwarded",
                "core_status": 200,
                "receipt_status": "accepted",
                "receipt_identity_matches": True,
            }
        )
        attempts.append(
            {
                **identity,
                "callback_kind": "progress",
                "result_hash": None,
                "action": "forwarded",
                "core_status": 200,
                "receipt_status": "accepted",
                "receipt_identity_matches": True,
            }
        )
        if step["status"] == "failed":
            attempts.extend([{**identity, "action": "held_before_forward"}] * 2)

    def journal(step_id, *, expected_state):
        calls.append((step_id, expected_state))
        return journals[step_id]

    def psql(sql, *, variables):
        assert variables == {"e2e_run_id": "run-1"}
        assert 'b."usageJson"::jsonb=s."usageJson"::jsonb' in sql
        assert 'u."taskId"=s.id AND u."runId"=r.id' in sql
        return json.dumps(facts, ensure_ascii=False)

    return SimpleNamespace(
        novel_id="novel-1",
        chapter_id="chapter-1",
        stack=SimpleNamespace(psql=psql),
        wait_delivered_journal=journal,
        control_state=lambda: {"callbackAttempts": attempts},
        assert_callback_attempt_bindings=Acceptance.assert_callback_attempt_bindings,
    ), calls


@pytest.mark.parametrize("correction", [False, True])
def test_quality_facts_verify_independent_billing_and_strip_full_text_from_evidence(correction):
    raw = good_facts(correction=correction)
    acceptance, calls = _acceptance(raw)
    facts = _facts(
        acceptance,
        "run-1",
        "check-1",
        correction=correction,
        instruction=raw["context"]["message"],
        source_content=raw["chapterContent"],
    )
    assert calls == (
        [("step-1", "failure"), ("step-2", "result")] if correction else [("step-1", "result")]
    )
    assert facts["completeReportVerified"] is True
    assert REPORT not in json.dumps(facts, ensure_ascii=False)
    assert "完整原文" not in json.dumps(facts, ensure_ascii=False)
    assert facts["reportSha256"] == sha(REPORT)


@pytest.mark.parametrize(
    "field",
    [
        "stepCount",
        "correctionCount",
        "terminalEventCount",
        "matchedBillingCount",
        "tokenUsageCount",
        "artifactCount",
        "evaluationCount",
        "legacyTaskCount",
        "legacyCommandCount",
        "scoreOverall",
    ],
)
def test_quality_facts_reject_missing_or_changed_authoritative_counts(field):
    facts = good_facts()
    facts[field] += 1
    with pytest.raises(AssertionError, match="持久事实"):
        assert_quality_facts(facts, correction=True)
    facts.pop(field)
    with pytest.raises(AssertionError, match="持久事实"):
        assert_quality_facts(facts, correction=True)


@pytest.mark.parametrize(
    "mutation",
    [
        "truncated_report",
        "wrong_failed_step",
        "new_evidence",
        "wrong_route",
        "duplicate_call",
        "changed_body",
    ],
)
def test_quality_facts_reject_result_binding_drift(mutation):
    raw = deepcopy(good_facts())
    if mutation == "truncated_report":
        raw["publicReport"] = REPORT[:100]
    elif mutation == "wrong_failed_step":
        raw["steps"][1]["input"]["failedStepId"] = "another-step"
    elif mutation == "new_evidence":
        raw["steps"][1]["bundleId"] = "another-bundle"
    elif mutation == "wrong_route":
        raw["steps"][1]["route"] = "chat_json_output_v1"
    elif mutation == "duplicate_call":
        raw["steps"][1]["usage"]["providerAttempts"] = 2
    else:
        raw["chapterContent"] = "改变后的正文"
    acceptance, _ = _acceptance(raw)
    with pytest.raises(AssertionError):
        _facts(
            acceptance,
            "run-1",
            "check-1",
            correction=True,
            instruction=raw["context"]["message"],
            source_content="完整原文😀\r\n",
        )


def test_delivered_journal_observer_accepts_failure_only_when_explicitly_requested():
    failure = {
        "present": True,
        "state": "failure",
        "callbackDelivery": "delivered",
        "terminalPayloadPresent": False,
    }
    observer = SimpleNamespace(journal_facts=lambda _step_id: failure, safe_diagnostics={})
    assert (
        Acceptance.wait_delivered_journal(observer, "step-1", expected_state="failure") == failure
    )
