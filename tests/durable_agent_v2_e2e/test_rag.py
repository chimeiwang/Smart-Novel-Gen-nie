"""RAG 隔离供应商与数据库证据核验自身的确定性门禁，不启动 Compose。"""

from __future__ import annotations

import importlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient

from . import control_app
from .rag import _database, assert_completed_facts, assert_pending_facts
from .rag_fixture import (
    BASE_URL,
    BATCHES,
    CHUNKS,
    CONTENT,
    ENDPOINT_KEY,
    MODEL,
    batch_body,
    embedding,
    embedding_response,
    request_hash,
    sha,
)
from .run_e2e import ComposeStack


def test_fixture_uses_two_complete_unicode_batches_without_chat_or_fake():
    assert 10 < len(CHUNKS) <= 64
    assert len(BATCHES) == 2 and len(BATCHES[0]) == 10 and len(BATCHES[1]) == 1
    assert "".join(CHUNKS) == CONTENT
    assert CONTENT.startswith("\ufeff") and CONTENT.endswith("\t\n") and "😀\r\n" in CONTENT
    assert all(len(chunk) == 1800 for chunk in CHUNKS[:-1])
    assert len(set(CHUNKS)) == len(CHUNKS)
    for batch in BATCHES:
        body = batch_body(batch)
        identity, result = embedding_response(body)
        assert set(body) == {"model", "input"}
        assert identity["requestSha256"] == request_hash(body)
        assert identity["idempotencyKey"] == "embedding." + request_hash(body)
        assert result["model"] == MODEL
        assert result["usage"] == {
            "prompt_tokens": sum(map(len, batch)),
            "total_tokens": sum(map(len, batch)),
        }
        assert [value["index"] for value in result["data"]] == list(reversed(range(len(batch))))
        assert [
            value["embedding"] for value in sorted(result["data"], key=lambda value: value["index"])
        ] == [embedding(text) for text in batch]


@pytest.mark.parametrize("mutation", ["truncate", "order", "model", "chat", "identity", "empty"])
def test_embedding_http_fixture_rejects_noncanonical_inputs(mutation):
    body = batch_body(BATCHES[0])
    if mutation == "truncate":
        body["input"][0] = body["input"][0][:-1]
    elif mutation == "order":
        body["input"].reverse()
    elif mutation == "model":
        body["model"] = "fake"
    elif mutation == "chat":
        body["messages"] = []
    elif mutation == "identity":
        body["runId"] = "不应发送的业务身份"
    else:
        body["input"] = []
    with pytest.raises(ValueError):
        embedding_response(body)


@pytest.fixture
def control(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("E2E_EXECUTION_CONTROL_TOKEN", "t" * 40)
    monkeypatch.setenv("E2E_CORE_UPSTREAM", "http://core:8000")
    monkeypatch.setenv("E2E_AGENT_UPSTREAM", "http://agent:8001")
    monkeypatch.setenv("E2E_CONTROL_DATABASE", ":memory:")
    with TestClient(control_app.create_app()) as client:
        yield client


def test_control_serves_embeddings_http_with_partial_usage_and_no_plaintext_store(control):
    body = batch_body(BATCHES[0])
    assert control.post("/v1/embeddings", json=body).status_code == 403
    assert (
        control.post(
            "/v1/embeddings", json=body, headers={"X-InkForge-E2E-Token": "t" * 40}
        ).status_code
        == 403
    )
    headers = {"Authorization": "Bearer " + "t" * 40}
    response = control.post("/v1/embeddings", json=body, headers=headers)
    assert response.status_code == 200
    assert response.json() == embedding_response(body)[1]
    state = control.get("/control/state", headers={"X-InkForge-E2E-Token": "t" * 40}).json()
    assert len(state["providerCalls"]) == 1
    assert state["providerCalls"][0]["physical_calls"] == 1
    assert state["providerCalls"][0]["completed_calls"] == 1
    serialized = json.dumps(state, ensure_ascii=False)
    assert CHUNKS[0] not in serialized and "Bearer" not in serialized and "t" * 40 not in serialized
    # 同请求再次发生应计数为真实重复调用，不在受控服务端伪装请求幂等。
    assert control.post("/v1/embeddings", json=body, headers=headers).status_code == 200
    state = control.get("/control/state", headers={"X-InkForge-E2E-Token": "t" * 40}).json()
    assert state["providerCalls"][0]["physical_calls"] == 2


def test_embedding_http_reuses_hold_gate_and_records_completion_only_after_release(control):
    headers = {"X-InkForge-E2E-Token": "t" * 40}
    assert (
        control.put("/control/provider-mode", json={"mode": "hold"}, headers=headers).status_code
        == 200
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            control.post,
            "/v1/embeddings",
            json=batch_body(BATCHES[1]),
            headers={"Authorization": "Bearer " + "t" * 40},
        )
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                state = control.get("/control/state", headers=headers).json()
                if state["providerGate"]["reached"] == 1:
                    break
                time.sleep(0.01)
            else:
                raise AssertionError("隔离 embeddings HTTP 未到达真实 gate")
            assert not future.done()
            assert state["providerCalls"][0]["physical_calls"] == 1
            assert state["providerCalls"][0]["completed_calls"] == 0
        finally:
            control.post("/control/provider-release", json={"abort": False}, headers=headers)
        assert future.result(timeout=3).status_code == 200


def _good_facts():
    identity = {
        "referenceId": "reference-1",
        "contentHash": sha(CONTENT),
        "indexGeneration": "2026-09-05T01:02:03.004Z",
    }
    return {
        "engineVersion": 2,
        "workflow": "rag",
        "operation": "embedding",
        "status": "completed",
        "novelId": "novel-1",
        "chapterId": None,
        "writingSessionId": None,
        "sourceType": "rag_index_v2",
        "sourceId": "reference-1",
        "targetType": "reference",
        "targetId": "reference-1",
        "stepCount": 2,
        "completedStepCount": 2,
        "terminalEventCount": 1,
        "bundleCount": 1,
        "reservationCount": 2,
        "matchedBillingCount": 2,
        "tokenUsageCount": 0,
        "creditLedgerCount": 0,
        "legacyWritingTaskCount": 0,
        "legacyRunCount": 0,
        "artifactCount": 0,
        "evaluationCount": 0,
        "documentStatus": "ready",
        "contentHash": sha(CONTENT),
        "content": CONTENT,
        "completedPayload": {"outcomeType": "rag_index", "resultId": "reference-1"},
        "indexGeneration": identity["indexGeneration"],
        "input": identity,
        "output": identity | {"chunkCount": len(CHUNKS)},
        "evidence": [
            {
                "kind": "rag_embedding_context",
                "resourceId": "reference-1",
                "content": identity | {"content": CONTENT, "chunkCount": len(CHUNKS)},
            }
        ],
        "chunks": [
            {
                "index": index,
                "text": chunk,
                "charCount": len(chunk),
                "dimension": 3,
                "embedding": embedding(chunk),
            }
            for index, chunk in enumerate(CHUNKS)
        ],
        "userBalanceMicros": 987654321,
        "steps": [
            {
                "id": f"step-{index}",
                "status": "completed",
                "purpose": "generation",
                "profile": "rag.embedding.v2",
                "input": {"batchIndex": index},
                "bundleId": "bundle-1",
                "output": {"embeddings": [embedding(text) for text in batch]},
                "model": {
                    "provider": "openai_embeddings",
                    "model": MODEL,
                    "deploymentProfileKey": "deployment.rag.embedding.v2",
                    "structuredOutputRoute": "embeddings_v1",
                    "endpointProfile": ENDPOINT_KEY,
                    "transportProfile": "transport.openai-embeddings.v1",
                    "capabilityVersion": "capability.openai-embeddings.batch.v1",
                    "reasoningMode": "disabled",
                    "supportsRequestIdempotency": False,
                },
                "usage": {
                    "usageStatus": "partial",
                    "providerAttempts": 1,
                    "protocolCorrections": 0,
                    "inputTokens": sum(map(len, batch)),
                    "completionTokens": 0,
                    "reasoningTokens": 0,
                    "visibleOutputTokens": 0,
                    "wallTimeMillis": 1,
                    "cachedTokens": None,
                    "promptCacheMissTokens": None,
                    "costMicros": None,
                },
            }
            for index, batch in enumerate(BATCHES)
        ],
    }


def _completed(raw):
    return assert_completed_facts(
        raw,
        reference_id="reference-1",
        novel_id="novel-1",
        initial_balance=987654321,
    )


def test_complete_evidence_keeps_real_partial_usage_and_omits_raw_content():
    facts = _completed(_good_facts())
    assert facts["chunkCount"] == 11
    assert facts["balanceDeltaMicros"] == 0 and facts["balanceUnchanged"] is True
    assert facts["tokenUsageCount"] == 0 and facts["matchedBillingCount"] == 2
    assert "content" not in facts and "userBalanceMicros" not in facts
    assert CHUNKS[0] not in json.dumps(facts, ensure_ascii=False)


@pytest.mark.parametrize(
    "field",
    [
        "terminalEventCount",
        "matchedBillingCount",
        "tokenUsageCount",
        "creditLedgerCount",
        "legacyRunCount",
        "legacyWritingTaskCount",
        "artifactCount",
        "evaluationCount",
        "bundleCount",
    ],
)
def test_completed_counters_reject_false_closure_and_missing_fields(field):
    raw = _good_facts()
    raw[field] += 1
    with pytest.raises(AssertionError):
        _completed(raw)
    raw.pop(field)
    with pytest.raises(AssertionError):
        _completed(raw)


@pytest.mark.parametrize(
    "mutation",
    [
        "truncate_source",
        "wrong_generation",
        "partial_chunks",
        "reversed_vectors",
        "char_count",
        "zero_cached",
        "zero_cost",
        "duplicate_call",
        "unknown_input",
        "chat_route",
        "fake_model",
        "different_endpoint",
        "claims_idempotency",
        "charged_balance",
        "missing_balance",
    ],
)
def test_completed_rejects_content_protocol_usage_and_balance_drift(mutation):
    raw = deepcopy(_good_facts())
    step = raw["steps"][0]
    if mutation == "truncate_source":
        raw["evidence"][0]["content"]["content"] = CONTENT[:-1]
    elif mutation == "wrong_generation":
        raw["indexGeneration"] = "2026-09-05T01:02:03.005Z"
    elif mutation == "partial_chunks":
        raw["chunks"].pop()
    elif mutation == "reversed_vectors":
        step["output"]["embeddings"].reverse()
    elif mutation == "char_count":
        raw["chunks"][0]["charCount"] = len(CHUNKS[0].encode("utf-16-le")) // 2
    elif mutation == "zero_cached":
        step["usage"]["cachedTokens"] = 0
    elif mutation == "zero_cost":
        step["usage"]["costMicros"] = 0
    elif mutation == "duplicate_call":
        step["usage"]["providerAttempts"] = 2
    elif mutation == "unknown_input":
        step["usage"]["inputTokens"] = None
    elif mutation == "chat_route":
        step["model"]["structuredOutputRoute"] = "plain_text_v1"
    elif mutation == "fake_model":
        step["model"]["model"] = "fake"
    elif mutation == "different_endpoint":
        step["model"]["endpointProfile"] = "endpoint.wrong.v1"
    elif mutation == "claims_idempotency":
        step["model"]["supportsRequestIdempotency"] = True
    elif mutation == "charged_balance":
        raw["userBalanceMicros"] -= 1
    else:
        raw["userBalanceMicros"] = None
    with pytest.raises(AssertionError):
        _completed(raw)


def test_pending_index_remains_empty_and_not_ready_until_all_batches_finish():
    raw = _good_facts()
    raw.update(completedStepCount=1, terminalEventCount=0, documentStatus="disabled", chunks=[])
    assert_pending_facts(raw)
    for field, value in (("chunks", _good_facts()["chunks"][:10]), ("documentStatus", "ready")):
        changed = raw | {field: value}
        with pytest.raises(AssertionError, match="部分发布"):
            assert_pending_facts(changed)


def test_database_uses_actual_schema_columns_and_read_only_queries():
    def psql(sql, *, variables):
        assert variables == {"e2e_run_id": "run-1"}
        assert 'i."resourceType"' in sql and "i.kind" not in sql
        assert 'b."pricingJson"' in sql and '"pricingSnapshotJson"' not in sql
        assert "reconciliation_required" in sql and 'b."settledAt" IS NULL' in sql
        assert "c.embedding::text::jsonb" in sql
        for operation in ("INSERT INTO", "UPDATE public.", "DELETE FROM"):
            assert operation not in sql
        return json.dumps(_good_facts(), ensure_ascii=False)

    assert _database(SimpleNamespace(stack=SimpleNamespace(psql=psql)), "run-1") == _good_facts()


def test_rag_phase_uses_test_only_compose_override_and_original_public_api():
    folder = Path(__file__).parent
    override = yaml.safe_load((folder / "compose.rag.yaml").read_text())
    assert set(override) == {"services"}
    assert set(override["services"]) == {"core-api", "agent-service"}
    for service in ("core-api", "agent-service"):
        environment = override["services"][service]["environment"]
        assert environment["RAG_INDEX_ENABLED"] == "true"
        assert environment["RAG_EMBEDDING_MODEL"] == MODEL
        assert environment["RAG_EMBEDDING_BASE_URL"] == BASE_URL
    assert "RAG_EMBEDDING_API_KEY" not in override["services"]["core-api"]["environment"]
    stack = SimpleNamespace(docker="docker", project="test", rag_embeddings=False)
    original = ComposeStack.command.fget(stack)
    stack.rag_embeddings = True
    assert ComposeStack.command.fget(stack) == original + ["-f", str(folder / "compose.rag.yaml")]
    source = (folder / "rag.py").read_text()
    assert "/api/v1/novels/{acceptance.novel_id}/references" in source
    assert 'restart_and_wait("agent-service")' in source
    assert "minimum_reached=2" in source and "terminalPayloadPresent" in source
    assert "noPartialIndexWrite=True" in source and '"inkforge:runs:"' in source
    assert 'phase == "rag"' in (folder / "run_e2e.py").read_text()
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.syspath_prepend(str(folder))
        assert callable(importlib.import_module("rag_fixture").embedding_response)
    finally:
        monkeypatch.undo()
