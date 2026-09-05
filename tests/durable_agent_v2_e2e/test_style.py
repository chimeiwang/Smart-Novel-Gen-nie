"""文风画像独立进程验收的纯文本夹具、上传与权威事实离线自检。"""

from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from inkforge_agents.providers.base import ModelExecutionPolicy, ModelMessage, ModelTurnRequest
from inkforge_agents.runtime.portrait_prompts import (
    PORTRAIT_SECTION_INSTRUCTIONS,
    PORTRAIT_SYSTEM_PROMPT,
)

from . import controlled_provider
from .run_e2e import Acceptance
from .style import _facts, _upload, assert_style_facts
from .style_fixture import (
    ORIGINAL_CHAR_COUNT,
    REFERENCES,
    SECTIONS,
    SOURCE_TEXT,
    portrait_markdown,
    raw_section,
    sha,
    style_turn_result,
)


def _request(section):
    return ModelTurnRequest(
        messages=[
            ModelMessage(role="system", content=PORTRAIT_SYSTEM_PROMPT),
            ModelMessage(
                role="user",
                content=f"任务：{PORTRAIT_SECTION_INSTRUCTIONS[section]}\n\n完整参考资料：\n{SOURCE_TEXT}",
            ),
        ],
        tools=[],
        maxOutputTokens=6000,
        thinkingMode="disabled",
        parallelToolCalls=False,
        policy=ModelExecutionPolicy(policyId="style.portrait.v2", thinkingMode="disabled"),
        requestIdempotencyKey="run-1.step-1",
    )


@pytest.mark.parametrize("section", SECTIONS)
def test_plain_text_fixture_preserves_raw_bom_and_python_whitespace(section):
    request = _request(section)
    result = style_turn_result(request)
    assert result.content == raw_section(section)
    assert result.content != result.content.strip()
    assert result.content.strip().startswith("\ufeff")
    assert "内部\u00a0空白" in result.content.strip()
    assert result.finishReason == "stop" and not result.toolCalls
    assert result.structuredOutput is None
    assert result.usage.promptTokens == result.diagnostics.promptCacheMissTokens
    assert result.diagnostics.reasoningTokens == 0
    assert result.usage.completionTokens <= 6000


@pytest.mark.parametrize("mutation", ["truncate", "append_prior", "change_system", "parallel"])
def test_fixture_rejects_changed_sources_or_nonplain_request(mutation):
    request = _request(SECTIONS[0])
    if mutation == "truncate":
        request.messages[1].content = request.messages[1].content[:-3]
    elif mutation == "append_prior":
        request.messages[1].content += "\n前节结果：" + raw_section(SECTIONS[0])
    elif mutation == "change_system":
        request.messages[0].content += "请输出 JSON。"
    else:
        request.parallelToolCalls = True
    with pytest.raises(ValueError):
        style_turn_result(request)


def test_fixture_imports_under_flat_compose_mount(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    assert callable(importlib.import_module("controlled_provider").style_turn_result)


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
async def test_controlled_provider_uses_plain_route_and_existing_hash_only_gates(monkeypatch):
    monkeypatch.setattr(controlled_provider.httpx, "AsyncClient", _ControlClient)
    provider = controlled_provider.ControlledFakeModelProvider(
        control_url="http://control", control_token="t" * 40
    )
    assert provider.supports_structured_output("plain_text_v1")
    result = await provider.complete_turn(_request(SECTIONS[0]))
    assert result.content == raw_section(SECTIONS[0])
    assert [path for path, _ in _ControlClient.calls] == [
        "/control/provider/reached",
        "/control/provider/completed",
    ]
    assert all(set(body) == {"idempotencyKey", "requestSha256"} for _, body in _ControlClient.calls)
    await provider.aclose()


def _references():
    return [
        {
            "id": f"reference-{index}",
            "styleId": "style-1",
            "filename": filename,
            "charCount": sum(not char.isspace() for char in content),
            "status": "ready",
            "createdAt": f"2026-09-05T00:00:0{index}Z",
        }
        for index, (filename, content) in enumerate(REFERENCES)
    ]


def test_public_upload_preserves_exact_utf8_bytes_and_original_character_count():
    calls = []
    refs = _references()

    def post(path, *, files):
        index = len(calls)
        filename, content = REFERENCES[index]
        assert path == "/api/v1/styles/style-1/references"
        assert files == {"file": (filename, content.encode("utf-8"), "text/plain")}
        calls.append(files)
        return SimpleNamespace(status_code=201, json=lambda: refs[index])

    uploaded = _upload(SimpleNamespace(core=SimpleNamespace(post=post)), "style-1")
    assert uploaded == refs
    assert sum(value["charCount"] for value in uploaded) == ORIGINAL_CHAR_COUNT
    assert ORIGINAL_CHAR_COUNT == sum(not char.isspace() for _, text in REFERENCES for char in text)
    assert REFERENCES[0][1].startswith("\ufeff")


def _good_facts(section=None):
    names = (section,) if section else SECTIONS
    count = len(names)
    refs = _references()
    style_sections = {name: raw_section(name).strip() for name in SECTIONS}
    if section:
        style_sections["creativeMethodology"] = "作者保留的新方法。"
    counters = {
        "originalCharCount": ORIGINAL_CHAR_COUNT,
        "usedCharCount": ORIGINAL_CHAR_COUNT,
        "truncated": False,
    }
    output = {"mode": "section" if section else "full", **counters}
    output.update(
        {"section": section, "content": raw_section(section).strip()} if section else style_sections
    )
    raw = {
        "engineVersion": 2,
        "workflow": "style",
        "operation": "portrait",
        "status": "completed",
        "novelId": None,
        "chapterId": None,
        "writingSessionId": None,
        "sourceType": "style_portrait_v2",
        "sourceId": "style-1",
        "targetType": "style_profile",
        "targetId": "style-1",
        "stepCount": count,
        "completedStepCount": count,
        "generationCount": count,
        "terminalEventCount": 1,
        "completedEventCount": 1,
        "bundleCount": 1,
        "evidenceCount": 1,
        "reservationCount": count,
        "matchedBillingCount": count,
        "tokenUsageCount": count,
        "userBalanceMicros": 123456789,
        "creditLedgerCount": 0,
        "legacyPortraitTaskCount": 0,
        "legacyWritingTaskCount": 0,
        "legacyCommandCount": 0,
        "artifactCount": 0,
        "evaluationCount": 0,
        "output": output,
        "completedPayload": {"outcomeType": "style_portrait", "resultId": "style-1"},
        "context": {
            "styleId": "style-1",
            "mode": "section" if section else "full",
            "section": section,
            "originalCharCount": ORIGINAL_CHAR_COUNT,
            "sourceTextSha256": sha(SOURCE_TEXT),
            "references": [
                {
                    "referenceId": ref["id"],
                    "filename": filename,
                    "charCount": ref["charCount"],
                    "content": content,
                    "contentSha256": sha(content),
                }
                for ref, (filename, content) in zip(refs, REFERENCES, strict=True)
            ],
        },
        "steps": [
            {
                "id": f"step-{index}",
                "input": {"section": name},
                "output": {"content": raw_section(name)},
                "bundleId": "bundle-1",
                "profile": "style.portrait.v2",
                "lane": "batch_media",
                "idempotencyKey": f"run-1.step-{index}",
                "route": "plain_text_v1",
                "resultHash": "a" * 64,
                "requestHash": "b" * 64,
                "fencingToken": 1,
                "usage": {"providerAttempts": 1, "protocolCorrections": 0, "reasoningTokens": 0},
            }
            for index, name in enumerate(names)
        ],
    }
    public = {
        "id": "style-1",
        **style_sections,
        **counters,
        "errorMessage": None,
        "portraitMarkdown": portrait_markdown(style_sections),
        "tasks": [{"id": "run-1", "status": "success", "section": section}],
    }
    return raw, public, refs, style_sections


def _acceptance(raw, public):
    attempts = []
    for index, step in enumerate(raw["steps"]):
        identity = {
            "run_id": "run-1",
            "step_id": step["id"],
            "job_id": step["id"],
            "fencing_token": 1,
            "request_hash": step["requestHash"],
            "result_hash": step["resultHash"],
            "callback_kind": "result",
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
        attempts.append({**identity, "callback_kind": "progress", "result_hash": None})
        if index == 0:
            attempts.extend([{**identity, "action": "held_before_forward"}] * 2)

    def psql(sql, *, variables):
        assert variables == {"e2e_run_id": "run-1"}
        assert 'u."novelId" IS NULL' in sql and 'u."taskId"=s.id AND u."runId"=r.id' in sql
        for column in ("cachedTokens", "promptCacheMissTokens", "reasoningTokens"):
            assert f'u."{column}"=(s."usageJson"::jsonb->>\'{column}\')::int' in sql
        assert 'u."completionTokens"-u."reasoningTokens"' in sql
        assert "=(s.\"usageJson\"::jsonb->>'visibleOutputTokens')::int" in sql
        assert 'u."totalTokens"=u."promptTokens"+u."completionTokens"' in sql
        assert 'u."visibleOutputTokens"' not in sql
        assert '\'userBalanceMicros\',(SELECT "creditBalanceMicros" FROM public."User"' in sql
        assert 't."userId"' not in sql
        return json.dumps(raw, ensure_ascii=False)

    def request(method, path, *, expected):
        assert (method, path, expected) == ("GET", "/api/v1/styles", 200)
        return SimpleNamespace(json=lambda: [public])

    return SimpleNamespace(
        initial_credit_balance_micros=123456789,
        stack=SimpleNamespace(psql=psql),
        request=request,
        wait_delivered_journal=lambda step_id: {
            "jobId": step_id,
            "requestHash": "b" * 64,
            "resultHash": "a" * 64,
            "fencingToken": 1,
        },
        control_state=lambda: {"callbackAttempts": attempts},
        assert_callback_attempt_bindings=Acceptance.assert_callback_attempt_bindings,
    )


@pytest.mark.parametrize("section", [None, "uniqueMarkers"])
def test_full_and_single_facts_keep_raw_output_but_publish_stripped_complete_style(section):
    raw, public, refs, expected = _good_facts(section)
    facts = _facts(
        _acceptance(raw, public),
        "run-1",
        "style-1",
        section=section,
        references=refs,
        expected_sections=expected,
    )
    assert facts["rawAndPythonStripVerified"] is True
    assert facts["fullStyleVerified"] is True
    assert facts["balanceUnchanged"] is True
    assert facts["balanceDeltaMicros"] == 0
    assert "userBalanceMicros" not in facts
    assert facts["stepCount"] == (5 if section is None else 1)
    assert SOURCE_TEXT not in json.dumps(facts, ensure_ascii=False)
    assert raw_section(SECTIONS[0]) not in json.dumps(facts, ensure_ascii=False)


@pytest.mark.parametrize(
    "field",
    [
        "novelId",
        "chapterId",
        "stepCount",
        "terminalEventCount",
        "matchedBillingCount",
        "legacyPortraitTaskCount",
        "legacyWritingTaskCount",
        "artifactCount",
        "evaluationCount",
    ],
)
def test_counter_validation_rejects_missing_null_and_extra_shadow_state(field):
    raw, _, _, _ = _good_facts()
    raw[field] = "伪小说" if raw[field] is None else raw[field] + 1
    with pytest.raises(AssertionError, match="耐久事实"):
        assert_style_facts(raw, count=5)
    raw.pop(field)
    with pytest.raises(AssertionError, match="耐久事实"):
        assert_style_facts(raw, count=5)


@pytest.mark.parametrize(
    "mutation",
    [
        "trim_raw",
        "remove_bom",
        "source_count",
        "second_bundle",
        "tools_route",
        "duplicate_call",
        "change_other_section",
    ],
)
def test_facts_reject_raw_or_materialization_drift(mutation):
    raw, public, refs, expected = deepcopy(_good_facts("uniqueMarkers"))
    if mutation == "trim_raw":
        raw["steps"][0]["output"]["content"] = raw["steps"][0]["output"]["content"].strip()
    elif mutation == "remove_bom":
        public["uniqueMarkers"] = public["uniqueMarkers"].removeprefix("\ufeff")
    elif mutation == "source_count":
        public["originalCharCount"] += 1
    elif mutation == "second_bundle":
        raw["bundleCount"] = 2
    elif mutation == "tools_route":
        raw["steps"][0]["route"] = "quality_strict_tool_v1"
    elif mutation == "duplicate_call":
        raw["steps"][0]["usage"]["providerAttempts"] = 2
    else:
        public["creativeMethodology"] = "被单节调用覆盖"
    with pytest.raises(AssertionError):
        _facts(
            _acceptance(raw, public),
            "run-1",
            "style-1",
            section="uniqueMarkers",
            references=refs,
            expected_sections=expected,
        )


@pytest.mark.parametrize("balance", [123456788, 123456790, None, "123456789", True])
def test_facts_require_real_unchanged_fake_balance(balance):
    raw, public, refs, expected = _good_facts("uniqueMarkers")
    raw["userBalanceMicros"] = balance
    with pytest.raises(AssertionError, match="余额"):
        _facts(
            _acceptance(raw, public),
            "run-1",
            "style-1",
            section="uniqueMarkers",
            references=refs,
            expected_sections=expected,
        )


def test_facts_require_initial_balance_instead_of_assuming_zero():
    raw, public, refs, expected = _good_facts("uniqueMarkers")
    acceptance = _acceptance(raw, public)
    acceptance.initial_credit_balance_micros = None
    with pytest.raises(AssertionError, match="余额"):
        _facts(
            acceptance,
            "run-1",
            "style-1",
            section="uniqueMarkers",
            references=refs,
            expected_sections=expected,
        )


def test_style_phase_uses_public_upload_and_same_deterministic_restart_gates():
    source = (Path(__file__).parent / "style.py").read_text(encoding="utf-8")
    runner = (Path(__file__).parent / "run_e2e.py").read_text(encoding="utf-8")
    assert 'phase == "style"' in runner
    assert 'files={"file":' in source
    assert "/api/v1/portrait-tasks/{run_id}" in source
    assert 'restart_and_wait("agent-service")' in source
    assert "minimum_reached=2" in source
    assert 'held["terminalPayloadPresent"] is not True' in source
    assert "noPartialStyleWrite=True" in source
    for forbidden in (
        "INSERT INTO",
        "UPDATE public.",
        "DELETE FROM",
        "api.deepseek.com",
        "inkforge.cn",
    ):
        assert forbidden not in source
