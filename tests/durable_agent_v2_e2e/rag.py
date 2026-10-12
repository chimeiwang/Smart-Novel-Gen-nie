"""资料原公共 API 与真实隔离 embeddings HTTP 的跨进程耐久验收。"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from .rag_fixture import (
    BATCHES,
    CHUNKS,
    CONTENT,
    ENDPOINT_KEY,
    MODEL,
    batch_body,
    embedding,
    request_hash,
    sha,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .run_e2e import Acceptance, Scenario


def _reference(acceptance: Acceptance, reference_id: str) -> dict[str, object]:
    items = acceptance.request(
        "GET", f"/api/v1/novels/{acceptance.novel_id}/references", expected=200
    ).json()
    found = [item for item in items if item["id"] == reference_id]
    if len(found) != 1:
        raise AssertionError("资料公开列表未返回唯一当前资料")
    return found[0]


def _database(acceptance: Acceptance, run_id: str) -> dict[str, object]:
    return json.loads(
        acceptance.stack.psql(
            """
      SELECT json_build_object(
        'engineVersion',r."engineVersion",'workflow',r.workflow,'operation',r.operation,
        'status',r.status::text,'novelId',r."novelId",'chapterId',r."chapterId",
        'writingSessionId',r."writingSessionId",'sourceType',r."sourceType",'sourceId',r."sourceId",
        'targetType',r."targetType",'targetId',r."targetId",'input',r.input::jsonb,
        'output',r.output::jsonb,'content',m.content,'documentStatus',d.status::text,
        'contentHash',d."contentHash",'indexGeneration',
          to_char(d."updatedAt",'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
        'stepCount',(SELECT count(*) FROM public."WorkflowStep" WHERE "runId"=r.id),
        'completedStepCount',(SELECT count(*) FROM public."WorkflowStep"
          WHERE "runId"=r.id AND status='completed'),
        'terminalEventCount',(SELECT count(*) FROM public."WorkflowEvent"
          WHERE "runId"=r.id AND "eventType" IN ('completed','failed','cancelled')),
        'completedPayload',(SELECT "payloadJson"::jsonb FROM public."WorkflowEvent"
          WHERE "runId"=r.id AND "eventType"='completed'),
        'bundleCount',(SELECT count(*) FROM public."WorkflowEvidenceBundle" WHERE "runId"=r.id),
        'evidence',(SELECT json_agg(json_build_object(
          'content',i."contentJson"::jsonb,'kind',i."resourceType",'resourceId',i."resourceId"))
          FROM public."WorkflowEvidenceItem" i WHERE i."bundleId"=r."currentEvidenceBundleId"),
        'reservationCount',(SELECT count(*) FROM public."WorkflowBillingReservation"
          WHERE "runId"=r.id),
        'matchedBillingCount',(SELECT count(*) FROM public."WorkflowStep" s
          JOIN public."WorkflowBillingReservation" b ON b."stepId"=s.id AND b."runId"=r.id
          WHERE s."runId"=r.id AND b."userId"=r."userId"
            AND b.status='reconciliation_required' AND b."settledAt" IS NULL
            AND b."reservedMicros"=0 AND b."chargedMicros"=0
            AND b."usageJson"::jsonb=s."usageJson"::jsonb
            AND (b."pricingJson"::jsonb->>'billable')::boolean=false),
        'tokenUsageCount',(SELECT count(*) FROM public."TokenUsage" WHERE "runId"=r.id),
        'creditLedgerCount',(SELECT count(*) FROM public."CreditLedger"
          WHERE "requestId" IN (SELECT "requestId" FROM public."WorkflowBillingReservation"
            WHERE "runId"=r.id)),
        'userBalanceMicros',(SELECT "creditBalanceMicros" FROM public."User" WHERE id=r."userId"),
        'legacyWritingTaskCount',(SELECT count(*) FROM public."WritingTask"
          WHERE "novelId"=r."novelId"),
        'legacyRunCount',(SELECT count(*) FROM public."WorkflowRun"
          WHERE "novelId"=r."novelId" AND "engineVersion"=1),
        'artifactCount',(SELECT count(*) FROM public."ReviewArtifact" WHERE "workflowRunId"=r.id),
        'evaluationCount',(SELECT count(*) FROM public."WorkflowEvaluation" WHERE "runId"=r.id),
        'chunks',COALESCE((SELECT json_agg(json_build_object(
          'index',c."chunkIndex",'text',c.text,'charCount',c."charCount",
          'dimension',c."embeddingDimension",'embedding',c.embedding::text::jsonb)
          ORDER BY c."chunkIndex") FROM public."RagChunk" c WHERE c."documentId"=d.id),'[]'::json),
        'steps',(SELECT json_agg(json_build_object(
          'id',s.id,'status',s.status::text,'purpose',s.purpose,'input',s.input::jsonb,
          'output',s.output::jsonb,'bundleId',s."evidenceBundleId",'profile',s."modelProfile",
          'model',s."resolvedModelJson"::jsonb,'usage',s."usageJson"::jsonb,
          'requestHash',s."requestHash",'resultHash',s."resultHash",'fencingToken',s."fencingToken")
          ORDER BY s.ordinal) FROM public."WorkflowStep" s WHERE s."runId"=r.id)
      )::text FROM public."WorkflowRun" r
        JOIN public."ReferenceMaterial" m ON m.id=r."sourceId" AND m."novelId"=r."novelId"
        JOIN public."RagDocument" d ON d."sourceId"=m.id AND d."novelId"=m."novelId"
          AND d."sourceType"='reference_material'
        WHERE r.id=:'e2e_run_id';
    """,
            variables={"e2e_run_id": run_id},
        )
    )


def assert_pending_facts(facts: dict[str, object]) -> None:
    if (
        facts["stepCount"] != 2
        or facts["completedStepCount"] != 1
        or facts["terminalEventCount"] != 0
        or facts["documentStatus"] != "disabled"
        or facts["chunks"] != []
        or facts["content"] != CONTENT
        or facts["contentHash"] != sha(CONTENT)
    ):
        raise AssertionError("第二批完成前不得部分发布索引或截断原文")


def assert_completed_facts(
    raw: dict[str, object], *, reference_id: str, novel_id: str, initial_balance: int
) -> dict[str, object]:
    expected = {
        "engineVersion": 2,
        "workflow": "rag",
        "operation": "embedding",
        "status": "completed",
        "novelId": novel_id,
        "chapterId": None,
        "writingSessionId": None,
        "sourceType": "rag_index_v2",
        "sourceId": reference_id,
        "targetType": "reference",
        "targetId": reference_id,
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
        "completedPayload": {"outcomeType": "rag_index", "resultId": reference_id},
    }
    if any(key not in raw or raw[key] != value for key, value in expected.items()):
        raise AssertionError("RAG 终态、逐 Step 零金额待对账或无 V1 影子事实不一致")
    identity = {
        "referenceId": reference_id,
        "contentHash": sha(CONTENT),
        "indexGeneration": raw["indexGeneration"],
    }
    if raw["input"] != identity or raw["output"] != identity | {"chunkCount": len(CHUNKS)}:
        raise AssertionError("RAG 原文、索引代次与最终摘要没有绑定同一来源")
    if raw["evidence"] != [
        {
            "kind": "rag_embedding_context",
            "resourceId": reference_id,
            "content": identity | {"content": CONTENT, "chunkCount": len(CHUNKS)},
        }
    ]:
        raise AssertionError("RAG 唯一冻结 Evidence 未保存完整原文和索引代次")
    chunks = [
        {
            "index": index,
            "text": chunk,
            "charCount": len(chunk),
            "dimension": 3,
            "embedding": embedding(chunk),
        }
        for index, chunk in enumerate(CHUNKS)
    ]
    if raw["chunks"] != chunks:
        raise AssertionError("RAG 全部块、Unicode 码点字数或有序向量未完整原子应用")
    steps = raw["steps"]
    if len(steps) != len(BATCHES) or len({step["bundleId"] for step in steps}) != 1:
        raise AssertionError("RAG 两批没有复用同一完整 Evidence")
    for index, (step, batch) in enumerate(zip(steps, BATCHES, strict=True)):
        if (
            step["status"] != "completed"
            or step["purpose"] != "generation"
            or step["profile"] != "rag.embedding.v2"
            or step["input"] != {"batchIndex": index}
            or step["output"] != {"embeddings": [embedding(text) for text in batch]}
        ):
            raise AssertionError("RAG Step 未按独立批次保存完整有序向量")
        model = step["model"]
        expected_model = {
            "provider": "openai_embeddings",
            "model": MODEL,
            "deploymentProfileKey": "deployment.rag.embedding.v2",
            "structuredOutputRoute": "embeddings_v1",
            "endpointProfile": ENDPOINT_KEY,
            "transportProfile": "transport.openai-embeddings.v1",
            "capabilityVersion": "capability.openai-embeddings.batch.v1",
            "reasoningMode": "disabled",
            "supportsRequestIdempotency": False,
        }
        if any(key not in model or model[key] != value for key, value in expected_model.items()):
            raise AssertionError("RAG 冻结供应商配置不是真实隔离 embeddings HTTP 身份")
        usage = step["usage"]
        expected_usage = {
            "usageStatus": "partial",
            "providerAttempts": 1,
            "protocolCorrections": 0,
            "inputTokens": sum(len(text) for text in batch),
            "completionTokens": 0,
            "reasoningTokens": 0,
            "visibleOutputTokens": 0,
        }
        if (
            any(key not in usage or usage[key] != value for key, value in expected_usage.items())
            or any(
                usage.get(key) is not None
                for key in ("cachedTokens", "promptCacheMissTokens", "costMicros")
            )
            or type(usage.get("wallTimeMillis")) is not int
            or usage["wallTimeMillis"] < 0
        ):
            raise AssertionError("RAG 真实 prompt 用量丢失或未知缓存/成本被伪造为零")
    balance = raw["userBalanceMicros"]
    if type(balance) is not int or type(initial_balance) is not int or balance != initial_balance:
        raise AssertionError("RAG 不收费路径缺少真实余额或发生扣款")
    return {
        **{key: raw[key] for key in expected if key not in {"content", "completedPayload"}},
        "indexGeneration": raw["indexGeneration"],
        "chunkCount": len(CHUNKS),
        "chunkHashes": [sha(chunk) for chunk in CHUNKS],
        "embeddingDimension": 3,
        "stepIds": [step["id"] for step in steps],
        "partialUsage": [step["usage"] for step in steps],
        "balanceDeltaMicros": 0,
        "balanceUnchanged": True,
        "completeIndexVerified": True,
    }


def _no_v1_queue(acceptance: Acceptance) -> dict[str, int]:
    counts = {}
    for field in ("payloads", "statuses"):
        result = acceptance.stack.run(
            ["exec", "-T", "redis", "redis-cli", "--raw", "HLEN", "inkforge:runs:" + field],
            timeout=30,
        ).stdout.strip()
        if result != "0":
            raise AssertionError("资料 V2 隔离 phase 出现 V1 Redis 任务影子")
        counts[field] = 0
    return counts


def scenarios(acceptance: Acceptance) -> Iterator[Scenario]:
    from .run_e2e import Scenario

    before = acceptance.provider_keys()
    acceptance.control_request("PUT", "/control/callback-mode", {"mode": "hold_before_forward"})
    client_request_id = "rag-e2e-full-content-" + sha(CONTENT)
    reference = acceptance.request(
        "POST",
        f"/api/v1/novels/{acceptance.novel_id}/references",
        expected=201,
        json_body={
            "clientRequestId": client_request_id,
            "title": "两批完整资料",
            "type": "note",
            "content": CONTENT,
        },
    ).json()
    reference_id = reference["id"]
    if reference["content"] != CONTENT or reference["contentHash"] != sha(CONTENT):
        raise AssertionError("原资料创建没有完整保存正文")
    run_id = acceptance.stack.psql(
        'SELECT id FROM public."WorkflowRun" WHERE "sourceType"=\'rag_index_v2\' '
        "AND \"sourceId\"=:'reference';",
        variables={"reference": reference_id},
    )
    if not run_id or "\n" in run_id:
        raise AssertionError("资料创建事务没有唯一原子绑定 V2 Run")
    acceptance.wait_callback_gate(run_id, minimum_reached=1)
    first_id = acceptance.stack.psql(
        'SELECT id FROM public."WorkflowStep" WHERE "runId"=:\'run\';',
        variables={"run": run_id},
    )
    held = acceptance.journal_facts(first_id)
    if (
        held["state"] != "result"
        or held["terminalPayloadPresent"] is not True
        or held["callbackDelivery"] != "pending"
    ):
        raise AssertionError("RAG 首批完整向量尚未持久化 terminal journal")
    restart = acceptance.stack.restart_and_wait("agent-service")
    acceptance.wait_callback_gate(run_id, minimum_reached=2, timeout=60)
    acceptance.control_request("PUT", "/control/provider-mode", {"mode": "hold"})
    acceptance.control_request("POST", "/control/callback-release", {"abort": False})
    acceptance.wait_provider_gate()
    pending = _database(acceptance, run_id)
    assert_pending_facts(pending)
    if _reference(acceptance, reference_id)["ragStatus"] != "disabled":
        raise AssertionError("第二批完成前公开资料索引已部分 ready")
    acceptance.control_request("POST", "/control/provider-release", {"abort": False})
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        current = _reference(acceptance, reference_id)
        if current["ragStatus"] == "ready":
            break
        if current["ragStatus"] == "failed":
            raise AssertionError("资料 V2 索引失败")
        time.sleep(0.2)
    else:
        raise AssertionError("资料索引未在门限内原子完成")
    raw = _database(acceptance, run_id)
    if raw["indexGeneration"] != pending["indexGeneration"]:
        raise AssertionError("RAG 完成错误推进了当前索引代次")
    facts = assert_completed_facts(
        raw,
        reference_id=reference_id,
        novel_id=acceptance.novel_id,
        initial_balance=acceptance.initial_credit_balance_micros,
    )
    if current["content"] != CONTENT or current["contentHash"] != sha(CONTENT):
        raise AssertionError("资料索引完成覆盖了完整原文")
    journals = []
    for index, step in enumerate(raw["steps"]):
        journal = acceptance.wait_delivered_journal(step["id"])
        attempts = [
            item
            for item in acceptance.control_state()["callbackAttempts"]
            if item["run_id"] == run_id
            and item["step_id"] == step["id"]
            and item.get("callback_kind") == "result"
        ]
        acceptance.assert_callback_attempt_bindings(
            run_id=run_id,
            step=step,
            journal=journal,
            attempts=attempts,
            allow_one_unauthenticated_inflight_request=index == 0,
        )
        if not any(item.get("receipt_status") == "accepted" for item in attempts):
            raise AssertionError("RAG 完整 Step 结果缺少真实 Core 接受回执")
        if index == 0 and sum(item["action"] == "held_before_forward" for item in attempts) < 2:
            raise AssertionError("RAG 首批未形成重启前后相同终态重放")
        journals.append(journal)
    providers = [
        item for item in acceptance.provider_facts() if item["idempotency_key"] not in before
    ]
    expected_hashes = {request_hash(batch_body(batch)) for batch in BATCHES}
    if (
        len(providers) != 2
        or {item["request_sha256"] for item in providers} != expected_hashes
        or any(item["physical_calls"] != 1 or item["completed_calls"] != 1 for item in providers)
    ):
        raise AssertionError("RAG 重启后首批发生重调或两批 HTTP 输入不完整")
    facts.update(
        serviceRestart=restart,
        heldFirstJournal=held,
        journals=journals,
        noPartialIndexWrite=True,
        legacyQueueCounts=_no_v1_queue(acceptance),
    )
    yield Scenario(
        name="rag_two_batches_agent_restart",
        run_id=run_id,
        session_id="",
        client_request_id=client_request_id,
        provider_identity={"calls": providers},
        database_facts=facts,
    )
