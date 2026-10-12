"""开发视频保持原 Task、作者确认与保存入口，V2 只承担当次执行权威。"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from inkforge_contracts.video_adaptation import (
    ChapterAdaptationPlanCandidate,
    SeedanceShotPromptSpec,
)
from inkforge_contracts.video_execution import VideoTaskContextV2

from .video_fixture import SOURCE, TITLE, compiled_prompt, prompt

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .run_e2e import Acceptance, Scenario


def _read(acceptance: Acceptance, adaptation_id: str) -> dict[str, object]:
    return acceptance.request(
        "GET", f"/api/v1/video/chapter-adaptations/{adaptation_id}", expected=200
    ).json()


def _run_id(acceptance: Acceptance, task_id: str) -> str:
    run_id = acceptance.stack.psql(
        'SELECT id FROM public."WorkflowRun" '
        "WHERE \"sourceType\"='video_adaptation_task_v2' AND \"sourceId\"=:'task';",
        variables={"task": task_id},
    )
    if not run_id or "\n" in run_id:
        raise AssertionError("原视频 Task 未原子绑定唯一 V2 Run")
    return run_id


def _wait(acceptance: Acceptance, adaptation_id: str, task_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        value = _read(acceptance, adaptation_id)
        task = value["latestTask"]
        if task is None or task["id"] != task_id:
            raise AssertionError("原改编聚合未指向本次视频 Task")
        if task["status"] == "completed":
            return value
        if task["status"] not in {"pending", "submitted", "processing"}:
            raise AssertionError("原视频 Task 未成功：" + str(task["status"]))
        time.sleep(0.2)
    raise AssertionError("视频 Task 未在门限内完成")


def _database(acceptance: Acceptance, run_id: str) -> dict[str, object]:
    return json.loads(
        acceptance.stack.psql(
            """
      SELECT json_build_object(
        'engineVersion',r."engineVersion",'workflow',r.workflow,'operation',r.operation,
        'status',r.status::text,'novelId',r."novelId",'chapterId',r."chapterId",
        'writingSessionId',r."writingSessionId",'sourceType',r."sourceType",'sourceId',r."sourceId",
        'targetType',r."targetType",'targetId',r."targetId",'input',r.input::jsonb,'output',r.output::jsonb,
        'taskId',t.id,'taskStatus',t.status,'taskJobId',t."jobId",'taskAttemptCount',t."attemptCount",
        'taskRequest',t."requestJson"::jsonb,'taskResult',t."resultJson"::jsonb,
        'checkpointStage',t."checkpointStage",'checkpoint',t."checkpointJson"::jsonb,
        'stepCount',(SELECT count(*) FROM public."WorkflowStep" WHERE "runId"=r.id),
        'completedStepCount',(SELECT count(*) FROM public."WorkflowStep"
          WHERE "runId"=r.id AND status='completed'),
        'terminalEventCount',(SELECT count(*) FROM public."WorkflowEvent" WHERE "runId"=r.id
          AND "eventType" IN ('completed','failed','cancelled')),
        'completedPayload',(SELECT "payloadJson"::jsonb FROM public."WorkflowEvent"
          WHERE "runId"=r.id AND "eventType"='completed'),
        'bundleCount',(SELECT count(*) FROM public."WorkflowEvidenceBundle" WHERE "runId"=r.id),
        'evidence',(SELECT json_agg(json_build_object(
          'kind',i."resourceType",'resourceId',i."resourceId",
          'content',i."contentJson"::jsonb)) FROM public."WorkflowEvidenceItem" i
          WHERE i."bundleId"=r."currentEvidenceBundleId"),
        'reservationCount',(SELECT count(*) FROM public."WorkflowBillingReservation"
          WHERE "runId"=r.id),
        'matchedBillingCount',(SELECT count(*) FROM public."WorkflowStep" s
          JOIN public."WorkflowBillingReservation" b ON b."stepId"=s.id AND b."runId"=r.id
          JOIN public."TokenUsage" u ON u."requestId"=b."requestId"
            AND u."taskId"=s.id AND u."runId"=r.id
          WHERE s."runId"=r.id AND b."userId"=r."userId" AND u."userId"=r."userId"
            AND u."novelId"=r."novelId" AND b.status='settled' AND b."reservedMicros"=0
            AND b."chargedMicros"=0 AND b."settledAt" IS NOT NULL
            AND (b."pricingJson"::jsonb->>'billable')::boolean=false AND u.model='fake'
            AND b."usageJson"::jsonb=s."usageJson"::jsonb
            AND u."promptTokens"=(s."usageJson"::jsonb->>'inputTokens')::int
            AND u."cachedTokens"=(s."usageJson"::jsonb->>'cachedTokens')::int
            AND u."promptCacheMissTokens"=(s."usageJson"::jsonb->>'promptCacheMissTokens')::int
            AND u."completionTokens"=(s."usageJson"::jsonb->>'completionTokens')::int
            AND u."reasoningTokens"=(s."usageJson"::jsonb->>'reasoningTokens')::int
            AND u."completionTokens"-u."reasoningTokens"=
              (s."usageJson"::jsonb->>'visibleOutputTokens')::int
            AND u."totalTokens"=u."promptTokens"+u."completionTokens"),
        'tokenUsageCount',(SELECT count(*) FROM public."TokenUsage" WHERE "runId"=r.id),
        'creditLedgerCount',(SELECT count(*) FROM public."CreditLedger" WHERE "requestId" IN
          (SELECT "requestId" FROM public."WorkflowBillingReservation" WHERE "runId"=r.id)),
        'userBalanceMicros',(SELECT "creditBalanceMicros" FROM public."User" WHERE id=r."userId"),
        'legacyRunCount',(SELECT count(*) FROM public."WorkflowRun"
          WHERE "novelId"=r."novelId" AND "engineVersion"=1),
        'legacyVideoTaskCount',(SELECT count(*) FROM public."VideoGenerationTask"),
        'evaluationCount',(SELECT count(*) FROM public."WorkflowEvaluation" WHERE "runId"=r.id),
        'artifacts',(SELECT COALESCE(json_agg(json_build_object(
          'id',id,'status',status::text,'kind',kind::text,
          'taskId',"videoAdaptationTaskId",'payload',"payloadJson"::jsonb)),'[]'::json)
          FROM public."ReviewArtifact" WHERE "videoAdaptationTaskId"=t.id),
        'planVersionCount',(SELECT count(*) FROM public."VideoShotPlanVersion"
          WHERE "adaptationId"=t."adaptationId"),
        'promptVersionCount',(SELECT count(*) FROM public."VideoShotPromptVersion" p
          JOIN public."VideoShotPlanVersion" v
          ON v.id=p."shotPlanVersionId" WHERE v."adaptationId"=t."adaptationId"),
        'steps',(SELECT json_agg(json_build_object(
          'id',s.id,'status',s.status::text,'purpose',s.purpose,
          'input',s.input::jsonb,'output',s.output::jsonb,
          'bundleId',s."evidenceBundleId",'profile',s."modelProfile",
          'model',s."resolvedModelJson"::jsonb,'usage',s."usageJson"::jsonb,'requestHash',s."requestHash",
          'resultHash',s."resultHash",'fencingToken',s."fencingToken") ORDER BY s.ordinal)
          FROM public."WorkflowStep" s WHERE s."runId"=r.id)
      )::text FROM public."WorkflowRun" r JOIN public."VideoAdaptationTask" t ON t.id=r."sourceId"
      WHERE r.id=:'e2e_run_id';
    """,
            variables={"e2e_run_id": run_id},
        )
    )


def assert_video_facts(
    raw: dict[str, object], *, novel_id: str, prompt_run: bool, initial_balance: int
) -> dict[str, object]:
    stages = (
        ["shot_prompt", "shot_prompt"]
        if prompt_run
        else ["dramatic_structure", "shot_design", "cinematic_review"]
    )
    count = len(stages)
    expected = {
        "engineVersion": 2,
        "workflow": "video",
        "status": "completed",
        "novelId": novel_id,
        "chapterId": None,
        "writingSessionId": None,
        "sourceType": "video_adaptation_task_v2",
        "operation": "chapter_shot_prompt_v2" if prompt_run else "chapter_cinematic_adaptation_v2",
        "targetType": "video_shot_prompt" if prompt_run else "video_adaptation",
        "taskStatus": "completed",
        "taskAttemptCount": 0,
        "stepCount": count,
        "completedStepCount": count,
        "terminalEventCount": 1,
        "bundleCount": 1,
        "reservationCount": count,
        "matchedBillingCount": count,
        "tokenUsageCount": count,
        "creditLedgerCount": 0,
        "legacyRunCount": 0,
        "legacyVideoTaskCount": 0,
        "evaluationCount": 0,
        "planVersionCount": 1 if prompt_run else 0,
        "promptVersionCount": 0,
    }
    if any(key not in raw or raw[key] != value for key, value in expected.items()):
        raise AssertionError("视频 V2 执行、原 Task、零费审计或正式写入时机不一致")
    task_id = raw["taskId"]
    if raw["sourceId"] != task_id or raw["input"] != {"taskId": task_id}:
        raise AssertionError("视频 Run 必须保留原业务 Task 身份")
    evidence = raw["evidence"]
    if (
        len(evidence) != 1
        or evidence[0]["kind"] != "video_task_context"
        or evidence[0]["resourceId"] != task_id
    ):
        raise AssertionError("视频必须使用唯一完整任务 Evidence")
    context = VideoTaskContextV2.model_validate(evidence[0]["content"])
    if (
        context.taskId != task_id
        or context.inheritedCheckpoint is not None
        or context.payload.model_dump(mode="json") != raw["taskRequest"]
        or context.payload.sourceText != SOURCE
        or context.payload.adaptationId != raw["targetId"]
    ):
        raise AssertionError("视频冻结完整 payload、来源或业务目标不一致")
    steps = raw["steps"]
    if len(steps) != count or len({step["bundleId"] for step in steps}) != 1:
        raise AssertionError("视频阶段必须共用同一完整来源")
    for index, (step, stage) in enumerate(zip(steps, stages, strict=True)):
        dependencies = [
            {"stepId": previous["id"], "resultHash": previous["resultHash"]}
            for previous in steps[:index]
        ]
        if (
            step["status"] != "completed"
            or step["purpose"] != "generation"
            or step["profile"] != f"video.{stage}.v2"
            or step["input"]["stageKey"] != stage
            or step["input"]["cycle"] != 0
            or step["input"]["correction"] != (prompt_run and index == 1)
            or step["input"]["dependencies"] != dependencies
            or step["output"]["stageKey"] != stage
            or step["id"] == raw["taskJobId"]
        ):
            raise AssertionError("视频阶段、前驱哈希或 Task/Step 身份被混淆")
        model = step["model"]
        expected_model = {
            "provider": "fake",
            "model": "fake",
            "transportProfile": "transport.fake.v1",
            "endpointProfile": "endpoint.local-fake.v1",
            "structuredOutputRoute": "responses_json_schema_v1",
            "capabilityVersion": "capability.fake.structured-output.v1",
            "reasoningMode": "disabled",
            "supportsRequestIdempotency": False,
        }
        if any(key not in model or model[key] != value for key, value in expected_model.items()):
            raise AssertionError("视频测试替身冒充官方 Responses 或声明了不存在的幂等保证")
        usage = step["usage"]
        if (
            usage["usageStatus"] != "complete"
            or usage["providerAttempts"] != 1
            or usage["protocolCorrections"] != 0
            or usage["reasoningTokens"] != 0
            or usage["cachedTokens"] != 0
            or usage["costMicros"] != 0
            or usage["inputTokens"] != usage["promptCacheMissTokens"]
            or usage["inputTokens"] <= 0
            or usage["completionTokens"] != usage["visibleOutputTokens"]
            or usage["completionTokens"] <= 0
        ):
            raise AssertionError("视频逐阶段调用用量不完整或被重复计算")
    artifacts = raw["artifacts"]
    artifact_id = None if prompt_run else artifacts[0]["id"] if len(artifacts) == 1 else None
    if raw["output"] != {"taskId": task_id, "artifactId": artifact_id} or raw[
        "completedPayload"
    ] != {"outcomeType": "video_task", "resultId": task_id}:
        raise AssertionError("视频唯一完成事件没有绑定原 Task 结果")
    if prompt_run:
        finding = {
            "code": "prompt_budget",
            "shotKey": "S01",
            "blocking": True,
            "parameters": {"actual": len(compiled_prompt(correction=False)), "maximum": 480},
        }
        if (
            artifacts
            or steps[0]["output"]["outcome"] != "needs_correction"
            or steps[0]["output"]["validationFindings"] != [finding]
            or steps[1]["input"]["correctionFindings"] != [finding]
            or steps[1]["output"]["outcome"] != "ready"
            or raw["taskResult"]["promptBatch"] != steps[1]["output"]["promptBatch"]
        ):
            raise AssertionError("提示词必须按具体超预算原因创建唯一纠正阶段并保存完整候选")
    else:
        if (
            len(artifacts) != 1
            or artifacts[0]["kind"] != "video_adaptation_plan"
            or artifacts[0]["status"] != "awaiting_user"
            or artifacts[0]["taskId"] != task_id
            or raw["checkpointStage"] != "dramatic_structure"
            or raw["checkpoint"] != steps[0]["output"]["checkpoint"]
            or steps[1]["input"]["checkpoint"] != raw["checkpoint"]
            or steps[2]["input"]["candidate"] != steps[1]["output"]["candidate"]
            or raw["taskResult"]["candidate"] != artifacts[0]["payload"]["candidate"]
        ):
            raise AssertionError("拆镜阶段没有按原检查点、完整候选和 Task 外键进入作者审核")
        ChapterAdaptationPlanCandidate.model_validate(raw["taskResult"]["candidate"])
    balance = raw["userBalanceMicros"]
    if type(balance) is not int or type(initial_balance) is not int or balance != initial_balance:
        raise AssertionError("隔离视频 Fake 不应改变用户真实余额")
    return {
        **expected,
        "taskId": task_id,
        "stepIds": [step["id"] for step in steps],
        "stages": stages,
        "artifactId": artifact_id,
        "balanceDeltaMicros": 0,
        "balanceUnchanged": True,
    }


def _finish_evidence(
    acceptance: Acceptance, run_id: str, *, before: set[str], prompt_run: bool
) -> dict[str, object]:
    raw = _database(acceptance, run_id)
    facts = assert_video_facts(
        raw,
        novel_id=acceptance.novel_id,
        prompt_run=prompt_run,
        initial_balance=acceptance.initial_credit_balance_micros,
    )
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
            allow_one_unauthenticated_inflight_request=not prompt_run and index == 0,
        )
        if not any(item.get("receipt_status") == "accepted" for item in attempts):
            raise AssertionError("视频阶段缺少 Core 合法接受回执")
        if (
            not prompt_run
            and index == 0
            and sum(item["action"] == "held_before_forward" for item in attempts) < 2
        ):
            raise AssertionError("视频首阶段未在 Agent 重启后重放同一终态")
        journals.append(journal)
    providers = [
        item for item in acceptance.provider_facts() if item["idempotency_key"] not in before
    ]
    if len(providers) != len(raw["steps"]) or any(
        item["physical_calls"] != 1 or item["completed_calls"] != 1 for item in providers
    ):
        raise AssertionError("视频重启或阶段纠正重复调用了已完成的模型阶段")
    facts.update(journals=journals, providerCalls=providers)
    return facts


def _without_ids(value):
    if isinstance(value, list):
        return [_without_ids(item) for item in value]
    if isinstance(value, dict):
        return {key: _without_ids(item) for key, item in value.items() if key != "id"}
    return value


def scenarios(acceptance: Acceptance) -> Iterator[Scenario]:
    from .run_e2e import Scenario

    chapter = acceptance.request(
        "GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200
    ).json()
    acceptance.request(
        "PATCH",
        f"/api/v1/chapters/{acceptance.chapter_id}",
        expected=200,
        json_body={"title": TITLE, "content": SOURCE, "expectedUpdatedAt": chapter["updatedAt"]},
    )
    chapter = acceptance.request(
        "GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200
    ).json()
    project = acceptance.request(
        "POST",
        f"/api/v1/video/novels/{acceptance.novel_id}/projects",
        expected=201,
        json_body={
            "title": "视频 V2 隔离验收",
            "mode": "series",
            "targetAspectRatio": "16:9",
            "targetLanguage": "zh-CN",
        },
    ).json()
    adaptation = acceptance.request(
        "POST",
        f"/api/v1/video/projects/{project['id']}/chapter-adaptations",
        expected=201,
        json_body={
            "clientRequestId": "video-create-adaptation-0001",
            "chapterId": acceptance.chapter_id,
            "expectedChapterUpdatedAt": chapter["updatedAt"],
        },
    ).json()
    adaptation_id = adaptation["id"]
    before = acceptance.provider_keys()
    acceptance.control_request("PUT", "/control/callback-mode", {"mode": "hold_before_forward"})
    started = acceptance.request(
        "POST",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/shot-plan-runs",
        expected=202,
        json_body={
            "clientRequestId": "video-three-stage-plan-0001",
            "pacingPreset": "short_drama",
            "targetEpisodeSeconds": 90,
        },
    ).json()
    task_id = started["task"]["id"]
    run_id = _run_id(acceptance, task_id)
    acceptance.wait_callback_gate(run_id, minimum_reached=1)
    first = _database(acceptance, run_id)
    if first["stepCount"] != 1:
        raise AssertionError("首视频终报提交前不应已接续其他阶段")
    held = acceptance.journal_facts(first["steps"][0]["id"])
    if (
        held["state"] != "result"
        or held["terminalPayloadPresent"] is not True
        or held["callbackDelivery"] != "pending"
    ):
        raise AssertionError("视频首阶段尚未形成完整持久终报")
    restart = acceptance.stack.restart_and_wait("agent-service")
    acceptance.wait_callback_gate(run_id, minimum_reached=2, timeout=60)
    acceptance.control_request("PUT", "/control/provider-mode", {"mode": "hold"})
    acceptance.control_request("POST", "/control/callback-release", {"abort": False})
    acceptance.wait_provider_gate()
    intermediate = _database(acceptance, run_id)
    if (
        intermediate["stepCount"] != 2
        or intermediate["completedStepCount"] != 1
        or intermediate["checkpoint"] != intermediate["steps"][0]["output"]["checkpoint"]
        or intermediate["artifacts"]
        or intermediate["planVersionCount"] != 0
    ):
        raise AssertionError("视频首阶段重放没有保存原 dramatic checkpoint 或提前发布候选/正式版本")
    acceptance.control_request("POST", "/control/provider-release", {"abort": False})
    completed = _wait(acceptance, adaptation_id, task_id)
    facts = _finish_evidence(acceptance, run_id, before=before, prompt_run=False)
    if (
        completed["currentPlan"] is not None
        or completed["candidatePlan"] is None
        or completed["state"] != "awaiting_review"
    ):
        raise AssertionError("拆镜完成只能进入原作者审核，不得自动批准")
    candidate = completed["candidatePlan"]
    approved = acceptance.request(
        "POST",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/shot-plan/confirm",
        expected=200,
        json_body={
            "clientRequestId": "video-author-confirm-plan-0001",
            "expectedArtifactRevision": completed["reviewArtifact"]["revision"],
            "expectedAdaptationRevision": completed["headRevision"],
            "plan": candidate,
        },
    ).json()
    formal = approved["currentPlan"]
    if (
        formal is None
        or _without_ids(formal["scenes"]) != candidate["scenes"]
        or approved["state"] != "approved"
    ):
        raise AssertionError("原作者确认未完整物化同一镜头方案")
    if _database(acceptance, run_id)["planVersionCount"] != 1:
        raise AssertionError("作者确认未创建唯一正式镜头方案")
    formal_binding = json.loads(
        acceptance.stack.psql(
            """
            SELECT json_build_object('taskId',v."sourceTaskId",'artifactId',v."reviewArtifactId",
              'artifactStatus',a.status::text)::text FROM public."VideoShotPlanVersion" v
              JOIN public."ReviewArtifact" a ON a.id=v."reviewArtifactId" WHERE v.id=:'version';
            """,
            variables={"version": formal["planVersionId"]},
        )
    )
    if formal_binding != {
        "taskId": task_id,
        "artifactId": facts["artifactId"],
        "artifactStatus": "applied",
    }:
        raise AssertionError("正式方案未绑定同一原 Task 与已批准审核物")
    facts.update(
        serviceRestart=restart,
        heldFirstJournal=held,
        authorConfirmed=True,
        planVersionId=formal["planVersionId"],
    )
    yield Scenario(
        name="video_plan_three_stages_restart_confirm",
        run_id=run_id,
        session_id="",
        client_request_id="video-three-stage-plan-0001",
        provider_identity={"calls": facts.pop("providerCalls")},
        database_facts=facts,
    )

    before = acceptance.provider_keys()
    shot = formal["scenes"][0]["beats"][0]["shots"][0]
    started = acceptance.request(
        "POST",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/prompt-runs",
        expected=202,
        json_body={
            "clientRequestId": "video-concrete-prompt-correction-0001",
            "expectedAdaptationRevision": approved["headRevision"],
            "shotPlanVersionId": formal["planVersionId"],
            "shotIds": [shot["id"]],
        },
    ).json()
    prompt_task = started["task"]["id"]
    prompt_run = _run_id(acceptance, prompt_task)
    completed = _wait(acceptance, adaptation_id, prompt_task)
    facts = _finish_evidence(acceptance, prompt_run, before=before, prompt_run=True)
    candidates = completed["promptCandidates"]
    expected_spec = SeedanceShotPromptSpec.model_validate(
        prompt(correction=True)["prompts"][0]["spec"]
    ).model_dump(mode="json")
    if (
        len(candidates) != 1
        or candidates[0]["taskId"] != prompt_task
        or candidates[0]["shotId"] != shot["id"]
        or candidates[0]["compiledPrompt"] != compiled_prompt(correction=True)
        or candidates[0]["spec"] != expected_spec
        or candidates[0]["visualReferences"] != []
        or completed["promptVersions"] != []
    ):
        raise AssertionError("逐镜候选未完整保留原具体纠正结果，或已越过作者保存")
    saved = acceptance.request(
        "PUT",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/shots/{shot['id']}/prompt",
        expected=200,
        json_body={
            "expectedPromptRevision": 1,
            "candidateTaskId": prompt_task,
            "currentPrompt": candidates[0]["compiledPrompt"],
        },
    ).json()
    versions = saved["promptVersions"]
    if (
        len(versions) != 1
        or versions[0]["currentText"] != compiled_prompt(correction=True)
        or versions[0]["generatedText"] != compiled_prompt(correction=True)
        or versions[0]["promptEdited"] is not False
        or versions[0]["visualReferences"] != []
    ):
        raise AssertionError("原 savePrompt 路径未完整保存作者选定的生成候选")
    persisted = acceptance.stack.psql(
        'SELECT "sourceTaskId" FROM public."VideoShotPromptVersion" WHERE id=:\'version\';',
        variables={"version": versions[0]["id"]},
    )
    if persisted != prompt_task:
        raise AssertionError("正式 PromptVersion 丢失原候选 Task 外键")
    for field in ("payloads", "statuses"):
        if (
            acceptance.stack.run(
                ["exec", "-T", "redis", "redis-cli", "--raw", "HLEN", "inkforge:runs:" + field],
                timeout=30,
            ).stdout.strip()
            != "0"
        ):
            raise AssertionError("视频 V2 阶段出现旧 V1 Redis 调度影子")
    task_count = acceptance.stack.psql(
        'SELECT count(*) FROM public."VideoAdaptationTask" WHERE "adaptationId"=:\'adaptation\';',
        variables={"adaptation": adaptation_id},
    )
    if task_count != "2":
        raise AssertionError("两个视频请求必须只保留两个必要业务 Task，不能重复建立 V1 影子 Task")
    facts.update(
        authorSavedPrompt=True,
        promptVersionId=versions[0]["id"],
        noLegacyQueue=True,
        originalBusinessTaskCount=2,
    )
    yield Scenario(
        name="video_prompt_specific_correction_save",
        run_id=prompt_run,
        session_id="",
        client_request_id="video-concrete-prompt-correction-0001",
        provider_identity={"calls": facts.pop("providerCalls")},
        database_facts=facts,
    )
