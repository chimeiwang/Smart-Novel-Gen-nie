"""章节规划自己的跨进程验收；只由隔离 Compose runner 调用。"""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .run_e2e import Acceptance, Scenario


def assert_completed_plan(
    facts: dict[str, object],
    *,
    model_steps: int,
    revisions: int,
    formal_plans: int,
    applied: bool,
    original_chapter_sha256: str,
    automatic_revision: bool = False,
) -> None:
    expected: dict[str, object] = {
        "engineVersion": 2,
        "operation": "plan_chapter",
        "status": "completed",
        "legacyTaskCount": 0,
        "legacyCommandCount": 0,
        "artifactCount": 1,
        "artifactKind": "beat_plan",
        "artifactStatus": "applied" if applied else "draft",
        "revisionCount": revisions,
        "evaluationCount": model_steps // 2,
        "reviewVerdicts": ["issues_found", "pass"]
        if automatic_revision
        else ["pass"] * (model_steps // 2),
        "modelStepCount": model_steps,
        "badModelStepCount": 0,
        "matchedBillingCount": model_steps,
        "reservationCount": model_steps,
        "tokenUsageCount": model_steps,
        "creditLedgerCount": 0,
        "balanceDeltaMicros": 0,
        "completedEventCount": 1,
        "approvedPlanCount": int(formal_plans > 0),
        "totalPlanCount": formal_plans,
        "supersededPlanCount": max(0, formal_plans - 1),
        "sceneBeatCount": formal_plans * 2,
        "chapterSha256": original_chapter_sha256,
    }
    mismatched = [key for key, value in expected.items() if facts.get(key) != value]
    if mismatched:
        raise AssertionError("章节规划持久结果不符合预期：" + ",".join(mismatched))


def _facts(acceptance: Acceptance, run_id: str) -> dict[str, object]:
    # 各计数都绑定本次隔离用户/小说/Run，不读取部署数据库。
    sql = """
    SELECT json_build_object(
      'engineVersion', r."engineVersion", 'operation', r.operation, 'status', r.status::text,
      'legacyTaskCount', (SELECT count(*) FROM public."WritingTask" WHERE "novelId" = r."novelId"),
      'legacyCommandCount', (SELECT count(*) FROM public."WritingRunCommand" c
        JOIN public."WritingTask" t ON t.id=c."taskId" WHERE t."novelId"=r."novelId"),
      'artifactCount', (SELECT count(*) FROM public."ReviewArtifact" WHERE "workflowRunId"=r.id),
      'artifactKind', (SELECT kind::text FROM public."ReviewArtifact" WHERE "workflowRunId"=r.id),
      'artifactStatus', (SELECT status::text FROM public."ReviewArtifact"
        WHERE "workflowRunId"=r.id),
      'revisionCount', (SELECT count(*) FROM public."ReviewArtifactRevision" v
        JOIN public."ReviewArtifact" a ON a.id=v."artifactId" WHERE a."workflowRunId"=r.id),
      'evaluationCount', (SELECT count(*) FROM public."WorkflowEvaluation" WHERE "runId"=r.id),
      'reviewVerdicts', (SELECT json_agg(e."contentVerdict" ORDER BY s.ordinal)
        FROM public."WorkflowEvaluation" e JOIN public."WorkflowStep" s ON s.id=e."stepId"
        WHERE e."runId"=r.id),
      'modelStepCount', (SELECT count(*) FROM public."WorkflowStep"
        WHERE "runId"=r.id AND purpose IN ('generation','review')),
      'badModelStepCount', (SELECT count(*) FROM public."WorkflowStep"
        WHERE "runId"=r.id AND purpose IN ('generation','review') AND
        (status::text <> 'completed' OR "attemptCount" <> 1 OR "fencingToken" <> 1
          OR "resultHash" IS NULL
          OR coalesce(("usageJson"::jsonb->>'providerAttempts')::int,0) <> 1)),
      'modelStepDiagnostics', (SELECT json_agg(json_build_object(
        'modelProfile', s."modelProfile", 'status', s.status::text, 'errorCode', s."errorCode",
        'inputTokens', s."usageJson"::jsonb->'inputTokens',
        'promptCacheMissTokens', s."usageJson"::jsonb->'promptCacheMissTokens',
        'completionTokens', s."usageJson"::jsonb->'completionTokens',
        'reasoningTokens', s."usageJson"::jsonb->'reasoningTokens',
        'visibleOutputTokens', s."usageJson"::jsonb->'visibleOutputTokens',
        'providerAttempts', s."usageJson"::jsonb->'providerAttempts') ORDER BY s.ordinal)
        FROM public."WorkflowStep" s WHERE s."runId"=r.id AND s.purpose IN ('generation','review')),
      'matchedBillingCount', (SELECT count(*) FROM public."WorkflowStep" s
        JOIN public."WorkflowBillingReservation" b ON b."stepId"=s.id AND b."runId"=r.id
        JOIN public."TokenUsage" u ON u."requestId"=b."requestId"
          AND u."taskId"=s.id AND u."runId"=r.id
        WHERE s."runId"=r.id AND s.purpose IN ('generation','review') AND
          b."userId"=r."userId" AND u."userId"=r."userId" AND u.model='fake'
          AND b.status='settled' AND b."reservedMicros"=0 AND b."chargedMicros"=0
          AND b."settledAt" IS NOT NULL AND b."usageJson"::jsonb=s."usageJson"::jsonb
          AND u."promptTokens"=(s."usageJson"::jsonb->>'inputTokens')::int
          AND u."completionTokens"=(s."usageJson"::jsonb->>'completionTokens')::int
          AND u."cachedTokens"=(s."usageJson"::jsonb->>'cachedTokens')::int
          AND u."totalTokens"=u."promptTokens"+u."completionTokens"),
      'reservationCount', (SELECT count(*) FROM public."WorkflowBillingReservation"
        WHERE "runId"=r.id),
      'tokenUsageCount', (SELECT count(*) FROM public."TokenUsage" WHERE "runId"=r.id),
      'creditLedgerCount', (SELECT count(*) FROM public."CreditLedger" WHERE "requestId" IN
        (SELECT "requestId" FROM public."WorkflowBillingReservation" WHERE "runId"=r.id)),
      'userBalanceMicros', (SELECT "creditBalanceMicros" FROM public."User" WHERE id=r."userId"),
      'completedEventCount', (SELECT count(*) FROM public."WorkflowEvent"
        WHERE "runId"=r.id AND "eventType"='completed'),
      'approvedPlanCount', (SELECT count(*) FROM public."ChapterBeatPlan"
        WHERE "chapterId"=r."chapterId" AND status::text='approved'),
      'totalPlanCount', (SELECT count(*) FROM public."ChapterBeatPlan"
        WHERE "chapterId"=r."chapterId"),
      'supersededPlanCount', (SELECT count(*) FROM public."ChapterBeatPlan"
        WHERE "chapterId"=r."chapterId" AND status::text='superseded'),
      'sceneBeatCount', (SELECT count(*) FROM public."SceneBeat" s JOIN public."ChapterBeatPlan" p
        ON p.id=s."beatPlanId" WHERE p."chapterId"=r."chapterId"),
      'chapterContent', (SELECT content FROM public."Chapter" WHERE id=r."chapterId")
    )::text FROM public."WorkflowRun" r WHERE r.id=:'e2e_run_id';
    """
    facts = json.loads(acceptance.stack.psql(sql, variables={"e2e_run_id": run_id}))
    if not isinstance(facts, dict) or not isinstance(facts.get("chapterContent"), str):
        raise AssertionError("章节规划数据库证据缺失")
    facts["chapterSha256"] = hashlib.sha256(facts.pop("chapterContent").encode()).hexdigest()
    balance = facts.pop("userBalanceMicros", None)
    initial_balance = acceptance.initial_credit_balance_micros
    facts["balanceDeltaMicros"] = (
        balance - initial_balance
        if isinstance(balance, int) and isinstance(initial_balance, int)
        else None
    )
    acceptance.safe_diagnostics["chapterPlanning"] = {"runId": run_id, **facts}
    return facts


def _waiting(acceptance: Acceptance, run_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        snapshot = acceptance.request("GET", f"/api/v1/writing/runs/{run_id}", expected=200).json()
        if snapshot.get("engineVersion") != 2 or snapshot.get("operation") != "plan_chapter":
            raise AssertionError("章节规划没有创建正确的 V2 Run")
        if snapshot.get("status") == "waiting_user":
            return snapshot
        if snapshot.get("status") in {"completed", "failed", "cancelled"}:
            _facts(acceptance, run_id)
            raise AssertionError("章节规划未产生待确认候选便结束")
        time.sleep(0.2)
    raise AssertionError("章节规划没有在门限内进入等待确认")


def _artifact(acceptance: Acceptance, snapshot: dict[str, object]) -> dict[str, object]:
    candidate = snapshot.get("artifact")
    if not isinstance(candidate, dict) or not isinstance(candidate.get("artifactId"), str):
        raise AssertionError("章节规划缺少权威 Artifact 身份")
    artifact_id = candidate["artifactId"]
    revision = candidate.get("artifactRevision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise AssertionError("章节规划缺少精确 Artifact revision")
    detail = acceptance.request(
        "GET", f"/api/v1/review-artifacts/{artifact_id}?revision={revision}", expected=200
    ).json()
    if (
        detail.get("engineVersion") != 2
        or detail.get("kind") != "beat_plan"
        or detail.get("workflowRunId") != snapshot.get("runId")
        or detail.get("taskId") is not None
        or detail.get("sourceBindingStatus") != "verified"
        or detail.get("revision") != revision
    ):
        raise AssertionError("章节规划详情没有恢复精确 V2 来源身份")
    payload = detail.get("payload")
    plan = payload.get("beatPlan") if isinstance(payload, dict) else None
    if not isinstance(plan, dict) or plan.get("title") != "隔离章节规划":
        raise AssertionError("章节规划详情没有重建完整计划")
    beats = plan.get("sceneBeats")
    if not isinstance(beats, list) or [beat.get("order") for beat in beats] != [1, 2]:
        raise AssertionError("章节规划没有确定性派生连续节拍顺序")
    return detail


def _decide(
    acceptance: Acceptance, detail: dict[str, object], decision: str, request_id: str
) -> dict[str, object]:
    body: dict[str, object] = {
        "engineVersion": 2,
        "clientRequestId": request_id,
        "expectedRevision": detail["revision"],
        "decision": decision,
    }
    if decision == "revise":
        body["userMessage"] = "保持现有证据和章节目标，重新组织节拍后交作者确认。"
    return acceptance.request(
        "POST",
        f"/api/v1/review-artifacts/{detail['id']}/decision",
        expected=202,
        json_body=body,
    ).json()


def scenarios(acceptance: Acceptance) -> Iterator[Scenario]:
    from .run_e2e import Scenario

    acceptance.control_request("PUT", "/control/provider-mode", {"mode": "pass"})
    chapter = acceptance.request(
        "GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200
    ).json()
    original_hash = hashlib.sha256(chapter["content"].encode()).hexdigest()
    formal_plans = 0
    for name, decision, revise, restart, automatic in (
        ("plan_discard_after_core_restart", "discard", False, True, False),
        ("plan_approve_idempotent", "approve", False, False, False),
        ("plan_revise_then_discard", "discard", True, False, False),
        ("plan_automatic_revision_then_approve", "approve", False, False, True),
    ):
        acceptance.control_request(
            "PUT",
            "/control/chapter-plan-review-mode",
            {"mode": "revise_once" if automatic else "pass"},
        )
        session_id = acceptance.create_session(name)
        request_id = "e2e-" + name + "-start"
        body = acceptance.run_body(
            session_id=session_id,
            client_request_id=request_id,
            instruction="只依据已有事实规划本章，不改正式正文。",
            operation="plan_chapter",
        )
        providers_before = acceptance.provider_keys()
        started = acceptance.start_run(body).json()
        run_id = str(started["runId"])
        snapshot = _waiting(acceptance, run_id)
        detail = _artifact(acceptance, snapshot)
        if detail.get("revision") != (2 if automatic else 1):
            raise AssertionError("自动复审没有产生预期的候选修订次数")
        before = _facts(acceptance, run_id)
        if before["badModelStepCount"] != 0:
            raise AssertionError("章节规划生成或复审未完整成功，已保留 Step 脱敏诊断")
        if before["totalPlanCount"] != formal_plans or before["chapterSha256"] != original_hash:
            raise AssertionError("确认前章节规划已写入正式计划或正文")
        runtime: dict[str, object] | None = None
        if restart:
            runtime = acceptance.stack.restart_and_wait("core-api")
            restored = _artifact(acceptance, _waiting(acceptance, run_id))
            if restored != detail:
                raise AssertionError("Core 重启改变了不可变章节规划详情")
        if revise:
            response = _decide(acceptance, detail, "revise", "e2e-plan-user-revise-0001")
            if response.get("runId") != run_id:
                raise AssertionError("返工错误创建了另一个 Run")
            if _decide(acceptance, detail, "revise", "e2e-plan-user-revise-0001") != response:
                raise AssertionError("返工请求的幂等重放改变了权威受理结果")
            detail = _artifact(acceptance, _waiting(acceptance, run_id))
            if detail.get("revision") != 2:
                raise AssertionError("用户返工没有创建候选 revision 2")
        decision_id = "e2e-" + name + "-decision"
        completed = _decide(acceptance, detail, decision, decision_id)
        if (
            completed.get("engineVersion") != 2
            or completed.get("runId") != run_id
            or completed.get("status") != "completed"
        ):
            raise AssertionError("作者决定没有直接完成同一 V2 Run")
        model_steps = 4 if revise or automatic else 2
        formal_plans += int(decision == "approve")
        facts = _facts(acceptance, run_id)
        assert_completed_plan(
            facts,
            model_steps=model_steps,
            revisions=2 if revise or automatic else 1,
            formal_plans=formal_plans,
            applied=decision == "approve",
            original_chapter_sha256=original_hash,
            automatic_revision=automatic,
        )
        if _decide(acceptance, detail, decision, decision_id) != completed:
            raise AssertionError("决定幂等重放没有返回同一权威结果")
        if (
            acceptance.start_run(body).json().get("runId") != run_id
            or _facts(acceptance, run_id) != facts
        ):
            raise AssertionError("启动或决定重放产生了重复计划、计费或事件")
        providers = [
            item
            for item in acceptance.provider_facts()
            if item["idempotency_key"] not in providers_before
        ]
        if len(providers) != model_steps or any(
            item.get("physical_calls") != 1 or item.get("completed_calls") != 1
            for item in providers
        ):
            raise AssertionError("章节规划的模型物理调用不是每个耐久 Step 恰好一次")
        yield Scenario(
            name=name,
            run_id=run_id,
            session_id=session_id,
            client_request_id=request_id,
            provider_identity={"steps": providers},
            database_facts={**facts, "serviceRestart": runtime},
        )
