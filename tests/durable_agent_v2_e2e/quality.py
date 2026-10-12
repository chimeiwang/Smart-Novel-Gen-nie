"""原质量公共接口上的正常终检与独立纠正、失败 journal 重启验收。"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from inkforge_contracts.quality_execution import QualityContextV2

from .quality_fixture import CORRECTION_CODE, CORRECTION_MARKER, quality_report, sha

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .run_e2e import Acceptance, Scenario


def assert_quality_facts(facts: dict[str, object], *, correction: bool) -> None:
    count = 2 if correction else 1
    expected = {
        "engineVersion": 2,
        "workflow": "quality",
        "operation": "consistency",
        "kind": "quality_check",
        "sourceType": "quality_check_v2",
        "targetType": "chapter",
        "status": "completed",
        "checkStatus": "completed",
        "chapterStatus": "review",
        "qualityGate": "revise" if correction else "pass",
        "scoreOverall": 82,
        "stepCount": count,
        "generationCount": 1,
        "correctionCount": int(correction),
        "completedStepCount": 1,
        "failedStepCount": int(correction),
        "terminalEventCount": 1,
        "completedEventCount": 1,
        "evidenceCount": 1,
        "reservationCount": count,
        "matchedBillingCount": count,
        "tokenUsageCount": count,
        "artifactCount": 0,
        "evaluationCount": 0,
        "legacyTaskCount": 0,
        "legacyCommandCount": 0,
        "creditLedgerCount": 0,
        "artifactStepCount": 0,
    }
    failures = [key for key, value in expected.items() if key not in facts or facts[key] != value]
    if failures:
        raise AssertionError("一致性终检持久事实不一致：" + ",".join(failures))


def _facts(
    acceptance: Acceptance,
    run_id: str,
    check_id: str,
    *,
    correction: bool,
    instruction: str,
    source_content: str,
) -> dict[str, object]:
    raw = json.loads(
        acceptance.stack.psql(
            """
      SELECT json_build_object(
        'engineVersion',r."engineVersion",'workflow',r.workflow,'operation',r.operation,
        'kind',r.kind::text,'sourceType',r."sourceType",'sourceId',r."sourceId",
        'targetType',r."targetType",'targetId',r."targetId",'status',r.status::text,
        'checkStatus',q.status::text,'chapterStatus',c.status::text,
        'qualityGate',q."qualityGate",'scoreOverall',q."scoreOverall",
        'legacyScores',json_build_array(q."scoreHook",q."scoreTension",q."scorePayoff",
          q."scorePacing",q."scoreEndingHook",q."scoreReaderPromise"),
        'publicReport',q.result,'rewriteBrief',q."rewriteBrief",'chapterContent',c.content,
        'report',r.output::jsonb,'plan',r."modelPolicyJson"::jsonb,
        'stepCount',(SELECT count(*) FROM public."WorkflowStep" WHERE "runId"=r.id),
        'generationCount',(SELECT count(*) FROM public."WorkflowStep"
          WHERE "runId"=r.id AND purpose='generation'),
        'correctionCount',(SELECT count(*) FROM public."WorkflowStep"
          WHERE "runId"=r.id AND purpose='protocol_correction'),
        'completedStepCount',(SELECT count(*) FROM public."WorkflowStep"
          WHERE "runId"=r.id AND status='completed'),
        'failedStepCount',(SELECT count(*) FROM public."WorkflowStep"
          WHERE "runId"=r.id AND status='failed'),
        'artifactStepCount',(SELECT count(*) FROM public."WorkflowStep"
          WHERE "runId"=r.id AND "artifactId" IS NOT NULL),
        'terminalEventCount',(SELECT count(*) FROM public."WorkflowEvent"
          WHERE "runId"=r.id AND "eventType" IN ('completed','failed','cancelled')),
        'completedEventCount',(SELECT count(*) FROM public."WorkflowEvent"
          WHERE "runId"=r.id AND "eventType"='completed'),
        'completedPayload',(SELECT "payloadJson"::jsonb FROM public."WorkflowEvent"
          WHERE "runId"=r.id AND "eventType"='completed'),
        'evidenceCount',(SELECT count(*) FROM public."WorkflowEvidenceItem" i
          JOIN public."WorkflowEvidenceBundle" b ON b.id=i."bundleId" WHERE b."runId"=r.id),
        'context',(SELECT i."contentJson"::jsonb FROM public."WorkflowEvidenceItem" i
          WHERE i."bundleId"=r."currentEvidenceBundleId"),
        'reservationCount',(SELECT count(*) FROM public."WorkflowBillingReservation"
          WHERE "runId"=r.id),
        'tokenUsageCount',(SELECT count(*) FROM public."TokenUsage" WHERE "runId"=r.id),
        'creditLedgerCount',(SELECT count(*) FROM public."CreditLedger"
          WHERE "requestId" IN (SELECT "requestId" FROM public."WorkflowBillingReservation"
            WHERE "runId"=r.id)),
        'matchedBillingCount',(SELECT count(*) FROM public."WorkflowStep" s
          JOIN public."WorkflowBillingReservation" b ON b."stepId"=s.id AND b."runId"=r.id
          JOIN public."TokenUsage" u ON u."requestId"=b."requestId"
            AND u."taskId"=s.id AND u."runId"=r.id
          WHERE s."runId"=r.id AND b.status='settled'
            AND b."reservedMicros"=0 AND b."chargedMicros"=0
            AND b."settledAt" IS NOT NULL AND b."usageJson"::jsonb=s."usageJson"::jsonb
            AND b."userId"=r."userId" AND u."userId"=r."userId" AND u.model='fake'
            AND u."promptTokens"=(s."usageJson"::jsonb->>'inputTokens')::int
            AND u."completionTokens"=(s."usageJson"::jsonb->>'completionTokens')::int),
        'artifactCount',(SELECT count(*) FROM public."ReviewArtifact" WHERE "workflowRunId"=r.id),
        'evaluationCount',(SELECT count(*) FROM public."WorkflowEvaluation" WHERE "runId"=r.id),
        'legacyTaskCount',(SELECT count(*) FROM public."WritingTask" WHERE "novelId"=r."novelId"),
        'legacyCommandCount',(SELECT count(*) FROM public."WritingRunCommand" x
          JOIN public."WritingTask" t ON t.id=x."taskId" WHERE t."novelId"=r."novelId"),
        'steps',(SELECT json_agg(json_build_object(
          'id',s.id,'purpose',s.purpose,'status',s.status::text,
          'input',s.input::jsonb,'output',s.output::jsonb,'errorCode',s."errorCode",'profile',s."modelProfile",
          'route',s."resolvedModelJson"::jsonb->>'structuredOutputRoute','resultHash',s."resultHash",
          'requestHash',s."requestHash",'fencingToken',s."fencingToken",'bundleId',s."evidenceBundleId",
          'idempotencyKey',s."idempotencyKey",'usage',s."usageJson"::jsonb) ORDER BY s.ordinal)
          FROM public."WorkflowStep" s WHERE s."runId"=r.id)
      )::text FROM public."WorkflowRun" r
        JOIN public."Chapter" c ON c.id=r."chapterId"
        JOIN public."ChapterQualityCheck" q ON q.id=r."sourceId"
      WHERE r.id=:'e2e_run_id';
    """,
            variables={"e2e_run_id": run_id},
        )
    )
    assert_quality_facts(raw, correction=correction)
    expected = quality_report(correction=correction)
    report, public_report, brief = (
        raw.pop("report"),
        raw.pop("publicReport"),
        raw.pop("rewriteBrief"),
    )
    if (
        report != expected
        or public_report != expected["report"]
        or brief != expected["rewriteBrief"]
    ):
        raise AssertionError("质量公开报告或 Run 完整报告被截断或改变")
    if raw.pop("legacyScores") != [None] * 6 or raw.pop("chapterContent") != source_content:
        raise AssertionError("质量终检改变了正文或保留了旧商业分数")
    context = QualityContextV2.model_validate(raw.pop("context"))
    if (
        context.checkId != check_id
        or context.novelId != acceptance.novel_id
        or context.chapterId != acceptance.chapter_id
        or context.chapterContent != source_content
        or context.message != instruction
        or context.sourceTaskId is not None
        or raw["sourceId"] != check_id
        or raw["targetId"] != acceptance.chapter_id
    ):
        raise AssertionError("质量终检没有冻结当前完整正文及精确检查项身份")
    plan = raw.pop("plan")["plan"]
    if (
        plan["reviewers"] != []
        or len(plan["systemSteps"]) != 1
        or plan["systemSteps"][0]["purpose"] != "protocol_correction"
        or plan["runBudget"]["maxProtocolCorrectionSteps"] != 1
        or plan["runBudget"]["maxModelCalls"] != 2
    ):
        raise AssertionError("质量冻结计划没有精确授权一次独立纠正")
    steps = raw.pop("steps")
    if steps[0]["input"] != {"userInstruction": instruction}:
        raise AssertionError("质量首个 Step 夹带非原指令字段")
    if correction:
        if (
            steps[0]["status"] != "failed"
            or steps[0]["errorCode"] != CORRECTION_CODE
            or steps[0]["output"] is not None
            or steps[1]["input"]
            != {
                "userInstruction": instruction,
                "failedStepId": steps[0]["id"],
                "failedResultHash": steps[0]["resultHash"],
                "failureCode": CORRECTION_CODE,
            }
            or steps[1]["bundleId"] != steps[0]["bundleId"]
        ):
            raise AssertionError("独立纠正没有绑定唯一已结算失败 Step 和原 Evidence")
    if steps[-1]["status"] != "completed" or steps[-1]["output"] != expected:
        raise AssertionError("质量最终 Step 没有持久化完整合法报告")
    if raw.pop("completedPayload") != {
        "outcomeType": "consistency_quality_report",
        "resultId": steps[-1]["id"],
    }:
        raise AssertionError("质量唯一完成事件没有绑定最终报告 Step")
    journals = []
    for index, step in enumerate(steps):
        expected_purpose = "generation" if index == 0 else "protocol_correction"
        expected_profile = (
            "quality.consistency.v2" if index == 0 else "system.quality_protocol_corrector.v2"
        )
        if (
            step["purpose"] != expected_purpose
            or step["profile"] != expected_profile
            or step["route"] != "quality_strict_tool_v1"
            or step["idempotencyKey"] != run_id + "." + step["id"]
            or step["usage"]["providerAttempts"] != 1
            or step["usage"]["protocolCorrections"] != 0
        ):
            raise AssertionError("质量模型 Step 用途、部署路由或单次用量身份不一致")
        failed = correction and index == 0
        journal = acceptance.wait_delivered_journal(
            step["id"], expected_state="failure" if failed else "result"
        )
        attempts = acceptance.control_state()["callbackAttempts"]
        matching = [
            item
            for item in attempts
            if item["run_id"] == run_id
            and item["step_id"] == step["id"]
            and item.get("callback_kind") == ("failure" if failed else "result")
        ]
        if not any(item.get("receipt_status") == "accepted" for item in matching):
            raise AssertionError("质量模型终态没有已接受的真实 Core 回执")
        acceptance.assert_callback_attempt_bindings(
            run_id=run_id,
            step=step,
            journal=journal,
            attempts=matching,
            allow_one_unauthenticated_inflight_request=failed,
        )
        if (
            failed
            and len([item for item in matching if item["action"] == "held_before_forward"]) < 2
        ):
            raise AssertionError("质量首次失败没有形成重启前后的两次相同终态投递")
        journals.append(journal)
    return raw | {
        "reportSha256": sha(str(expected["report"])),
        "sourceSha256": sha(source_content),
        "stepIds": [step["id"] for step in steps],
        "providerKeys": [step["idempotencyKey"] for step in steps],
        "journals": journals,
        "completeReportVerified": True,
        "correctionBindingVerified": correction,
    }


def _wait_check(acceptance: Acceptance, check_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        check = acceptance.request("GET", f"/api/v1/quality-checks/{check_id}", expected=200).json()
        if check.get("id") != check_id:
            raise AssertionError("质量查询返回了其他检查项")
        if check.get("status") == "completed":
            return check
        if check.get("status") not in {"pending", "running"}:
            raise AssertionError("质量运行未完成，检查项状态：" + str(check.get("status")))
        time.sleep(0.2)
    raise AssertionError("质量检查没有在门限内完成")


def scenarios(acceptance: Acceptance) -> Iterator[Scenario]:
    from .run_e2e import Scenario

    chapter_path = f"/api/v1/chapters/{acceptance.chapter_id}"
    chapter = acceptance.request("GET", chapter_path, expected=200).json()
    source_content = chapter["content"]
    acceptance.request(
        "PATCH",
        chapter_path + "/status",
        expected=200,
        json_body={
            "status": "review",
            "expectedUpdatedAt": chapter["updatedAt"],
        },
    )
    chapter = acceptance.request("GET", chapter_path, expected=200).json()
    checks = [check for check in chapter["qualityChecks"] if check["type"] == "consistency"]
    if len(checks) != 1:
        raise AssertionError("章节送审没有创建唯一一致性终检项")
    check_id = checks[0]["id"]
    run_path = f"/api/v1/quality-checks/{check_id}/run"
    for correction in (False, True):
        instruction = "检查本章一致性" + ("：" + CORRECTION_MARKER if correction else "")
        request_id = "e2e-quality-correction-0001" if correction else "e2e-quality-report-0001"
        body = {"clientRequestId": request_id, "message": instruction, "taskId": None}
        before = acceptance.provider_keys()
        if correction:
            acceptance.control_request(
                "PUT", "/control/callback-mode", {"mode": "hold_before_forward"}
            )
        started = acceptance.request("POST", run_path, expected=202, json_body=body).json()
        run_id = started.get("taskId")
        if (
            started.get("accepted") is not True
            or started.get("checkId") != check_id
            or not isinstance(run_id, str)
        ):
            raise AssertionError("原质量运行接口没有返回明确的运行身份")
        replay = acceptance.request("POST", run_path, expected=202, json_body=body).json()
        if replay != started:
            raise AssertionError("质量创建请求重放没有复用同一 Run")
        restart = None
        if correction:
            acceptance.wait_callback_gate(run_id, minimum_reached=1)
            restart = acceptance.stack.restart_and_wait("agent-service")
            acceptance.wait_callback_gate(run_id, minimum_reached=2, timeout=60)
            acceptance.control_request("POST", "/control/callback-release", {"abort": False})
        public = _wait_check(acceptance, check_id)
        expected = quality_report(correction=correction)
        if (
            public["result"] != expected["report"]
            or public["qualityGate"] != expected["qualityGate"]
            or public["scoreOverall"] != 82
        ):
            raise AssertionError("原质量查询接口没有回读完整报告和 HALF_EVEN 分数")
        facts = _facts(
            acceptance,
            run_id,
            check_id,
            correction=correction,
            instruction=instruction,
            source_content=source_content,
        )
        providers = [
            item for item in acceptance.provider_facts() if item["idempotency_key"] not in before
        ]
        if (
            len(providers) != (2 if correction else 1)
            or any(
                item["physical_calls"] != 1 or item["completed_calls"] != 1 for item in providers
            )
            or {item["idempotency_key"] for item in providers} != set(facts["providerKeys"])
        ):
            raise AssertionError("质量正常或纠正 Step 缺少唯一物理模型调用，或重启后重复调用")
        if restart is not None:
            facts["serviceRestart"] = restart
        yield Scenario(
            name="quality_correction_failure_journal_restart" if correction else "quality_report",
            run_id=run_id,
            session_id="",
            client_request_id=request_id,
            provider_identity={"calls": providers},
            database_facts=facts,
        )
