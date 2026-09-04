"""完整正文、双复审及作者采用的独立跨进程隔离验收。"""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, cast

from inkforge_contracts import ChapterDraftResult

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .run_e2e import Acceptance, Scenario


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def assert_completed_writing(
    facts: dict[str, object],
    *,
    model_steps: int,
    revisions: int,
    patch_steps: int,
    applied: bool,
    chapter_sha256: str,
    other_layers_sha256: str,
    verdicts: list[str],
) -> None:
    expected: dict[str, object] = {
        "engineVersion": 2,
        "operation": "write_chapter",
        "status": "completed",
        "legacyTaskCount": 0,
        "legacyCommandCount": 0,
        "artifactCount": 1,
        "artifactKind": "chapter_draft",
        "artifactStatus": "applied" if applied else "draft",
        "revisionCount": revisions,
        "evaluationCount": len(verdicts),
        "reviewVerdicts": verdicts,
        "modelStepCount": model_steps,
        "badModelStepCount": 0,
        "patchStepCount": patch_steps,
        "badPatchStepCount": 0,
        "matchedBillingCount": model_steps,
        "reservationCount": model_steps,
        "tokenUsageCount": model_steps,
        "creditLedgerCount": 0,
        "balanceDeltaMicros": 0,
        "completedEventCount": 1,
        "chapterSha256": chapter_sha256,
        "otherLayersSha256": other_layers_sha256,
    }
    if applied:
        expected.update(
            {
                "chapterStatus": "drafting",
                "chapterCompletedAt": None,
                "qualityCheckCount": 1,
                "qualityStatus": "pending",
                "qualityResult": None,
                "qualityGate": None,
                "qualityScoreOverall": None,
            }
        )
    mismatch = [key for key, value in expected.items() if key not in facts or facts[key] != value]
    if mismatch:
        raise AssertionError("正文写作持久结果不符合预期：" + ",".join(mismatch))


def _other_layers(acceptance: Acceptance) -> str:
    result = acceptance.stack.psql(
        """
      SELECT jsonb_build_object(
        'novel', jsonb_build_object('storyProgress', n."storyProgress"),
        'worldSetting', (SELECT jsonb_agg(to_jsonb(w) ORDER BY w.id)
          FROM public."WorldSetting" w WHERE w."novelId"=n.id),
        'storyBackground', (SELECT jsonb_agg(to_jsonb(b) ORDER BY b.id)
          FROM public."StoryBackground" b WHERE b."novelId"=n.id),
        'writingBible', (SELECT jsonb_agg(to_jsonb(b) ORDER BY b.id)
          FROM public."WritingBible" b WHERE b."novelId"=n.id),
        'outline', (SELECT jsonb_agg(to_jsonb(o) ORDER BY o.id)
          FROM public."Outline" o WHERE o."novelId"=n.id),
        'chapterCount', (SELECT count(*) FROM public."Chapter" WHERE "novelId"=n.id),
        'progress', (SELECT jsonb_agg(to_jsonb(p) ORDER BY p.id)
          FROM public."ChapterProgress" p JOIN public."Chapter" c ON c.id=p."chapterId"
          WHERE c."novelId"=n.id),
        'plot', (SELECT jsonb_agg(to_jsonb(p) ORDER BY p.id)
          FROM public."PlotProgress" p WHERE p."novelId"=n.id),
        'plans', (SELECT jsonb_agg(to_jsonb(p) ORDER BY p.id)
          FROM public."ChapterBeatPlan" p JOIN public."Chapter" c ON c.id=p."chapterId"
          WHERE c."novelId"=n.id),
        'beats', (SELECT jsonb_agg(to_jsonb(s) ORDER BY s.id)
          FROM public."SceneBeat" s JOIN public."ChapterBeatPlan" p ON p.id=s."beatPlanId"
          JOIN public."Chapter" c ON c.id=p."chapterId" WHERE c."novelId"=n.id),
        'characters', (SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id)
          FROM public."Character" c WHERE c."novelId"=n.id),
        'factions', (SELECT jsonb_agg(to_jsonb(f) ORDER BY f.id)
          FROM public."Faction" f WHERE f."novelId"=n.id),
        'locations', (SELECT jsonb_agg(to_jsonb(l) ORDER BY l.id)
          FROM public."Location" l WHERE l."novelId"=n.id),
        'items', (SELECT jsonb_agg(to_jsonb(i) ORDER BY i.id)
          FROM public."Item" i WHERE i."novelId"=n.id),
        'glossary', (SELECT jsonb_agg(to_jsonb(g) ORDER BY g.id)
          FROM public."Glossary" g WHERE g."novelId"=n.id),
        'foreshadowing', (SELECT jsonb_agg(to_jsonb(f) ORDER BY f.id)
          FROM public."Foreshadowing" f WHERE f."novelId"=n.id),
        'outlines', (SELECT jsonb_agg(to_jsonb(o) ORDER BY o.id)
          FROM public."OutlineNode" o WHERE o."novelId"=n.id)
      )::text FROM public."Novel" n WHERE n.id=:'e2e_novel_id';
    """,
        variables={"e2e_novel_id": acceptance.novel_id},
    )
    return _sha(json.dumps(json.loads(result), ensure_ascii=False, sort_keys=True))


def _facts(acceptance: Acceptance, run_id: str) -> dict[str, object]:
    result = acceptance.stack.psql(
        """
    SELECT json_build_object(
      'engineVersion', r."engineVersion", 'operation', r.operation, 'status', r.status::text,
      'legacyTaskCount', (SELECT count(*) FROM public."WritingTask" WHERE "novelId"=r."novelId"),
      'legacyCommandCount', (SELECT count(*) FROM public."WritingRunCommand" x
        JOIN public."WritingTask" t ON t.id=x."taskId" WHERE t."novelId"=r."novelId"),
      'artifactCount', (SELECT count(*) FROM public."ReviewArtifact" WHERE "workflowRunId"=r.id),
      'artifactKind', a.kind::text, 'artifactStatus', a.status::text,
      'revisionCount', (SELECT count(*) FROM public."ReviewArtifactRevision"
        WHERE "artifactId"=a.id),
      'evaluationCount', (SELECT count(*) FROM public."WorkflowEvaluation" WHERE "runId"=r.id),
      'reviewVerdicts', (SELECT json_agg(e."contentVerdict" ORDER BY s.ordinal)
        FROM public."WorkflowEvaluation" e JOIN public."WorkflowStep" s ON s.id=e."stepId"
        WHERE e."runId"=r.id),
      'modelStepCount', (SELECT count(*) FROM public."WorkflowStep" WHERE "runId"=r.id
        AND purpose IN ('generation','review')),
      'badModelStepCount', (SELECT count(*) FROM public."WorkflowStep" WHERE "runId"=r.id
        AND purpose IN ('generation','review') AND (status::text <> 'completed'
          OR "attemptCount" <> 1 OR "fencingToken" <> 1 OR "resultHash" IS NULL
          OR coalesce(("usageJson"::jsonb->>'providerAttempts')::int,0) <> 1)),
      'modelStepDiagnostics', (SELECT json_agg(json_build_object('purpose',s.purpose,
        'modelProfile',s."modelProfile", 'status',s.status::text, 'errorCode',s."errorCode",
        'usage',s."usageJson"::jsonb) ORDER BY s.ordinal)
        FROM public."WorkflowStep" s WHERE s."runId"=r.id AND s.purpose IN ('generation','review')),
      'patchStepCount', (SELECT count(*) FROM public."WorkflowStep" WHERE "runId"=r.id
        AND purpose='candidate_patch'),
      'badPatchStepCount', (SELECT count(*) FROM public."WorkflowStep" s WHERE s."runId"=r.id
        AND purpose='candidate_patch' AND (status::text <> 'completed'
          OR "stepType" <> 'persistence'
          OR lane <> 'control' OR "modelProfile" IS NOT NULL OR "usageJson" IS NOT NULL
          OR "resultHash" IS NULL OR EXISTS (SELECT 1 FROM public."WorkflowBillingReservation" b
            WHERE b."stepId"=s.id))),
      'matchedBillingCount', (SELECT count(*) FROM public."WorkflowStep" s
        JOIN public."WorkflowBillingReservation" b ON b."stepId"=s.id AND b."runId"=r.id
        JOIN public."TokenUsage" u ON u."requestId"=b."requestId"
          AND u."taskId"=s.id AND u."runId"=r.id
        WHERE s."runId"=r.id AND s.purpose IN ('generation','review')
          AND b."userId"=r."userId" AND u."userId"=r."userId" AND u.model='fake'
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
      'completedEventCount', (SELECT count(*) FROM public."WorkflowEvent" WHERE "runId"=r.id
        AND "eventType"='completed'),
      'chapterContent', c.content, 'chapterStatus', c.status::text,
      'chapterCompletedAt', c."completedAt",
      'qualityCheckCount', (SELECT count(*) FROM public."ChapterQualityCheck" WHERE "chapterId"=c.id
        AND type::text='consistency'),
      'qualityStatus', q.status::text, 'qualityResult', q.result,
      'qualityGate', q."qualityGate", 'qualityScoreOverall', q."scoreOverall"
    )::text FROM public."WorkflowRun" r
      LEFT JOIN public."ReviewArtifact" a ON a."workflowRunId"=r.id
      JOIN public."Chapter" c ON c.id=r."chapterId"
      LEFT JOIN public."ChapterQualityCheck" q ON q."chapterId"=c.id AND q.type::text='consistency'
    WHERE r.id=:'e2e_run_id';
    """,
        variables={"e2e_run_id": run_id},
    )
    facts = json.loads(result)
    if not isinstance(facts, dict) or not isinstance(facts.get("chapterContent"), str):
        raise AssertionError("正文写作数据库证据缺失")
    facts["chapterSha256"] = _sha(facts.pop("chapterContent"))
    facts["otherLayersSha256"] = _other_layers(acceptance)
    balance = facts.pop("userBalanceMicros", None)
    initial = acceptance.initial_credit_balance_micros
    facts["balanceDeltaMicros"] = (
        balance - initial if isinstance(balance, int) and isinstance(initial, int) else None
    )
    acceptance.safe_diagnostics["chapterWriting"] = {"runId": run_id, **facts}
    return facts


def _waiting(acceptance: Acceptance, run_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        snapshot = acceptance.request("GET", f"/api/v1/writing/runs/{run_id}", expected=200).json()
        if snapshot.get("engineVersion") != 2 or snapshot.get("operation") != "write_chapter":
            raise AssertionError("正文写作没有创建正确的 V2 Run")
        if snapshot.get("status") == "waiting_user":
            return cast(dict[str, object], snapshot)
        if snapshot.get("status") in {"completed", "failed", "cancelled"}:
            _facts(acceptance, run_id)
            raise AssertionError("正文写作未产生待确认候选便结束")
        time.sleep(0.2)
    _facts(acceptance, run_id)
    raise AssertionError("正文写作没有在门限内进入等待确认")


def _artifact(acceptance: Acceptance, snapshot: dict[str, object]) -> dict[str, object]:
    candidate = snapshot.get("artifact")
    if not isinstance(candidate, dict) or not isinstance(candidate.get("artifactId"), str):
        raise AssertionError("正文写作缺少权威草案身份")
    revision = candidate.get("artifactRevision")
    if type(revision) is not int or revision < 1:
        raise AssertionError("正文写作缺少精确候选版本")
    detail = acceptance.request(
        "GET",
        f"/api/v1/review-artifacts/{candidate['artifactId']}?revision={revision}",
        expected=200,
    ).json()
    if (
        detail.get("engineVersion") != 2
        or detail.get("kind") != "chapter_draft"
        or detail.get("id") != candidate["artifactId"]
        or detail.get("revision") != revision
        or detail.get("taskId") is not None
        or detail.get("workflowRunId") != snapshot.get("runId")
        or detail.get("sourceBindingStatus") != "verified"
    ):
        raise AssertionError("正文写作详情没有恢复精确 V2 来源身份")
    data = detail.get("payload")
    if not isinstance(data, dict) or data.get("operation") != "write_chapter":
        raise AssertionError("正文写作详情没有重建完整 payload")
    if data.get("target") != {"mode": "existing_chapter", "chapterId": acceptance.chapter_id}:
        raise AssertionError("正文写作详情目标不是当前章节")
    ChapterDraftResult.model_validate(
        {key: data.get(key) for key in ("summary", "content", "contentSha256", "wordCount")}
    )
    diff = detail.get("diff")
    if (
        not isinstance(diff, dict)
        or diff.get("type") != "chapter_content"
        or diff.get("after") != data["content"]
    ):
        raise AssertionError("正文写作详情没有恢复完整全文差异")
    return cast(dict[str, object], detail)


def _decide(
    acceptance: Acceptance,
    detail: dict[str, object],
    decision: str,
    request_id: str,
    *,
    edited_content: str | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "engineVersion": 2,
        "clientRequestId": request_id,
        "expectedRevision": detail["revision"],
        "decision": decision,
    }
    if decision == "revise":
        body["userMessage"] = "保持已有事实，完整重写并突出人物的主动选择。"
    if edited_content is not None:
        body["editedContent"] = edited_content
    return cast(
        dict[str, object],
        acceptance.request(
            "POST",
            f"/api/v1/review-artifacts/{detail['id']}/decision",
            expected=202,
            json_body=body,
        ).json(),
    )


def scenarios(acceptance: Acceptance) -> Iterator[Scenario]:
    from .run_e2e import Scenario

    acceptance.control_request("PUT", "/control/provider-mode", {"mode": "pass"})
    # 仅对本 runner 新建的隔离数据库植入非空事实，证明采用正文不覆盖其他数据层。
    acceptance.stack.psql(
        """
      INSERT INTO public."ChapterProgress" (id,"chapterId",content,"updatedAt")
        VALUES ('e2e-writing-progress',:'chapter_id','进展只由独立流程更新。',CURRENT_TIMESTAMP);
      INSERT INTO public."PlotProgress" (id,"novelId","currentStage","updatedAt")
        VALUES ('e2e-writing-plot',:'novel_id','核对线索',CURRENT_TIMESTAMP);
      INSERT INTO public."ChapterBeatPlan" (id,"chapterId",status,"chapterGoal","updatedAt")
        VALUES ('e2e-writing-plan',:'chapter_id','approved','依据线索作出选择。',CURRENT_TIMESTAMP);
    """,
        variables={"chapter_id": acceptance.chapter_id, "novel_id": acceptance.novel_id},
    )
    for name, decision, manual, restart, mode, edited in (
        ("writing_discard_after_core_restart", "discard", False, True, "pass", False),
        ("writing_approve_idempotent", "approve", False, False, "pass", False),
        ("writing_user_revise_then_discard", "discard", True, False, "pass", False),
        ("writing_automatic_rewrite_then_approve", "approve", False, False, "revise_once", False),
        ("writing_patch_then_dual_review_approve", "approve", False, False, "patch_once", False),
        ("writing_patch_conflict_then_discard", "discard", False, False, "patch_conflict", False),
        # 共用章的大篇幅编辑最后验证，正文保持完整；不污染后续正常预算的生成/复审场景。
        ("writing_edit_approve_exact_full_text", "approve", False, False, "pass", True),
    ):
        acceptance.control_request("PUT", "/control/chapter-writing-review-mode", {"mode": mode})
        # 在生成前把既有终检标记为完成；批准后必须失效。正式服务不执行此测试 SQL。
        acceptance.stack.psql(
            """
          UPDATE public."ChapterQualityCheck" SET status='completed',result='隔离旧终检',
            "qualityGate"='pass',"scoreOverall"=90
          WHERE "chapterId"=:'chapter_id' AND type::text='consistency';
        """,
            variables={"chapter_id": acceptance.chapter_id},
        )
        chapter = acceptance.request(
            "GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200
        ).json()
        original_hash = _sha(chapter["content"])
        other_layers_hash = _other_layers(acceptance)
        session_id = acceptance.create_session(name)
        request_id = "e2e-" + name + "-start"
        body = acceptance.run_body(
            session_id=session_id,
            client_request_id=request_id,
            instruction="依据冻结资料写完整章节，只产生待采用正文，不更新其他资料。",
            operation="write_chapter",
        )
        providers_before = acceptance.provider_keys()
        started = acceptance.start_run(body).json()
        run_id = str(started["runId"])
        detail = _artifact(acceptance, _waiting(acceptance, run_id))
        automatic = mode in {"revise_once", "patch_once"}
        if detail["revision"] != (2 if automatic else 1):
            raise AssertionError("自动修改没有产生预期次数的候选版本")
        if _facts(acceptance, run_id)["chapterSha256"] != original_hash:
            raise AssertionError("作者确认前生成候选已改写正式正文")
        service_restart: dict[str, object] | None = None
        if restart:
            service_restart = acceptance.stack.restart_and_wait("core-api")
            if _artifact(acceptance, _waiting(acceptance, run_id)) != detail:
                raise AssertionError("Core 重启改变了不可变正文详情")
        if manual:
            reply = _decide(acceptance, detail, "revise", "e2e-writing-manual-revise-0001")
            if (
                reply.get("runId") != run_id
                or _decide(acceptance, detail, "revise", "e2e-writing-manual-revise-0001") != reply
            ):
                raise AssertionError("用户返工没有幂等继续同一 Run")
            detail = _artifact(acceptance, _waiting(acceptance, run_id))
            if detail["revision"] != 2:
                raise AssertionError("用户返工没有生成 revision 2")
        data = detail["payload"]
        if not isinstance(data, dict) or not isinstance(data.get("content"), str):
            raise AssertionError("正文草案没有完整文本")
        content = data["content"]
        if mode == "patch_once" and ("新行动线索" not in content or "旧行动线索" in content):
            raise AssertionError("确定性 patch 没有完整应用唯一替换")
        if mode == "patch_conflict" and "旧行动线索" not in content:
            raise AssertionError("冲突 patch 没有原子放弃")
        edit_text = "  作者编辑保留完整正文😀\r\n" * 1000 + "尾段\r\n" if edited else None
        applied_content = edit_text if edit_text is not None else content
        decision_id = "e2e-" + name + "-decision"
        completed = _decide(acceptance, detail, decision, decision_id, edited_content=edit_text)
        if (
            completed.get("engineVersion") != 2
            or completed.get("runId") != run_id
            or completed.get("status") != "completed"
        ):
            raise AssertionError("作者决定没有完成同一 V2 Run")
        model_steps = 5 if mode == "patch_once" else 6 if manual or mode == "revise_once" else 3
        verdicts = ["issues_found"] * 2 if mode != "pass" else ["pass"] * 2
        if automatic or manual:
            verdicts += ["pass"] * 2
        facts = _facts(acceptance, run_id)
        assert_completed_writing(
            facts,
            model_steps=model_steps,
            revisions=1 + int(automatic or manual) + int(edited),
            patch_steps=int(mode == "patch_once"),
            applied=decision == "approve",
            chapter_sha256=_sha(applied_content) if decision == "approve" else original_hash,
            other_layers_sha256=other_layers_hash,
            verdicts=verdicts,
        )
        if (
            _decide(acceptance, detail, decision, decision_id, edited_content=edit_text)
            != completed
        ):
            raise AssertionError("作者决定幂等重放改变了结果")
        if (
            acceptance.start_run(body).json().get("runId") != run_id
            or _facts(acceptance, run_id) != facts
        ):
            raise AssertionError("重复启动或决定产生重复正文、版本、计费或事件")
        providers = [
            item
            for item in acceptance.provider_facts()
            if item["idempotency_key"] not in providers_before
        ]
        if len(providers) != model_steps or any(
            item.get("physical_calls") != 1 or item.get("completed_calls") != 1
            for item in providers
        ):
            raise AssertionError("每个模型 Step 的物理调用不恰好一次")
        yield Scenario(
            name=name,
            run_id=run_id,
            session_id=session_id,
            client_request_id=request_id,
            provider_identity={"steps": providers},
            database_facts={**facts, "serviceRestart": service_restart},
        )
