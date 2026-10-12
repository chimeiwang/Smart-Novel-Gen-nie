"""既有 Compose harness 的中短篇四操作与双段重启验收。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .short_medium_fixture import OPENING, OUTLINE, REPLACEMENT, REPORT, manuscript_segment, sha

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .run_e2e import Acceptance, Scenario


def assert_short_facts(
    facts: dict[str, object], *, operation: str, model_count: int, candidate_id: str | None
) -> None:
    expected = {
        "engineVersion": 2,
        "workflow": "short_medium",
        "operation": operation,
        "status": "completed",
        "legacyTaskCount": 0,
        "legacyCommandCount": 0,
        "artifactCount": int(candidate_id is not None),
        "candidateVersionId": candidate_id,
        "modelCount": model_count,
        "manifestCount": 1,
        "completedEventCount": 1,
        "evaluationCount": 0,
        "reservationCount": model_count,
        "matchedBillingCount": model_count,
        "tokenUsageCount": model_count,
    }
    failures = [key for key, value in expected.items() if key not in facts or facts[key] != value]
    if failures:
        raise AssertionError("中短篇持久事实不一致：" + ",".join(failures))


def _facts(
    acceptance: Acceptance,
    run_id: str,
    *,
    operation: str,
    expected_text: str,
    model_count: int,
    candidate_id: str | None,
) -> dict[str, object]:
    raw = json.loads(
        acceptance.stack.psql(
            """
      SELECT json_build_object(
        'engineVersion',r."engineVersion",'workflow',r.workflow,'operation',r.operation,'status',r.status::text,
        'legacyTaskCount',(SELECT count(*) FROM public."WritingTask" WHERE "novelId"=r."novelId"),
        'legacyCommandCount',(SELECT count(*) FROM public."WritingRunCommand" c
          JOIN public."WritingTask" t
          ON t.id=c."taskId" WHERE t."novelId"=r."novelId"),
        'artifactCount',(SELECT count(*) FROM public."ReviewArtifact" WHERE "workflowRunId"=r.id),
        'candidateVersionId',(SELECT id FROM public."ReviewArtifact"
          WHERE "workflowRunId"=r.id LIMIT 1),
        'modelCount',(SELECT count(*) FROM public."WorkflowStep"
          WHERE "runId"=r.id AND purpose='generation'),
        'manifestCount',(SELECT count(*) FROM public."WorkflowStep"
          WHERE "runId"=r.id AND purpose='short_medium_manifest'),
        'completedEventCount',(SELECT count(*) FROM public."WorkflowEvent"
          WHERE "runId"=r.id AND "eventType"='completed'),
        'evaluationCount',(SELECT count(*) FROM public."WorkflowEvaluation" WHERE "runId"=r.id),
        'reservationCount',(SELECT count(*) FROM public."WorkflowBillingReservation"
          WHERE "runId"=r.id),
        'tokenUsageCount',(SELECT count(*) FROM public."TokenUsage" WHERE "runId"=r.id),
        'matchedBillingCount',(SELECT count(*) FROM public."WorkflowStep" s
          JOIN public."WorkflowBillingReservation" b ON b."stepId"=s.id AND b."runId"=r.id
          JOIN public."TokenUsage" u ON u."requestId"=b."requestId"
            AND u."taskId"=s.id AND u."runId"=r.id
          WHERE s."runId"=r.id AND s.purpose='generation' AND b.status='settled'
            AND b."reservedMicros"=0 AND b."chargedMicros"=0 AND b."settledAt" IS NOT NULL
            AND b."usageJson"::jsonb=s."usageJson"::jsonb
            AND b."userId"=r."userId" AND u."userId"=r."userId"
            AND u.model='fake' AND u."promptTokens"=(s."usageJson"::jsonb->>'inputTokens')::int
            AND u."completionTokens"=(s."usageJson"::jsonb->>'completionTokens')::int),
        'steps',(SELECT json_agg(json_build_object('id',s.id,'status',s.status::text,
          'input',s.input::jsonb,'inputHash',s."inputHash",'output',s.output::jsonb,
          'resultHash',s."resultHash",'requestHash',s."requestHash",'fencingToken',s."fencingToken",
          'idempotencyKey',s."idempotencyKey",'bundleId',s."evidenceBundleId") ORDER BY s.ordinal)
          FROM public."WorkflowStep" s WHERE s."runId"=r.id AND s.purpose='generation'),
        'manifest',(SELECT input::jsonb FROM public."WorkflowStep"
          WHERE "runId"=r.id AND purpose='short_medium_manifest'),
        'manifestOutput',(SELECT output::jsonb FROM public."WorkflowStep"
          WHERE "runId"=r.id AND purpose='short_medium_manifest'),
        'evidence',(SELECT json_agg(json_build_object('bundleId',i."bundleId",'ordinal',i.ordinal,
          'resourceId',i."resourceId",'resourceType',i."resourceType",'content',i."contentJson"::jsonb))
          FROM public."WorkflowEvidenceItem" i
          JOIN public."WorkflowEvidenceBundle" b ON b.id=i."bundleId"
          WHERE b."runId"=r.id)
      )::text FROM public."WorkflowRun" r WHERE r.id=:'e2e_run_id';
    """,
            variables={"e2e_run_id": run_id},
        )
    )
    steps, manifest, output, evidence = (
        raw.pop("steps"),
        raw.pop("manifest"),
        raw.pop("manifestOutput"),
        raw.pop("evidence"),
    )
    assert_short_facts(raw, operation=operation, model_count=model_count, candidate_id=candidate_id)
    if manifest["segmentCount"] != model_count or manifest["contentSha256"] != sha(expected_text):
        raise AssertionError("中短篇零模型汇总未绑定完整最终文本")
    refs = manifest["segments"]
    if len(refs) != model_count or len(steps) != model_count:
        raise AssertionError("中短篇模型段数或汇总清单不完整")
    field = (
        "replacement"
        if operation == "replace_selection"
        else "text"
        if operation == "full_check"
        else "content"
    )
    texts: list[str] = []
    journals = []
    for index, step in enumerate(steps):
        if step["status"] != "completed" or step["input"] != {
            "segmentIndex": index,
            "segmentCount": model_count,
        }:
            raise AssertionError("中短篇模型 Step 未按连续序号持久化")
        text = step["output"][field]
        if step["output"][field + "Sha256"] != sha(text):
            raise AssertionError("中短篇模型输出原文哈希不符")
        ref = refs[index]
        if (
            ref["stepId"] != step["id"]
            or ref["index"] != index
            or ref["contentSha256"] != sha(text)
            or ref["resultHash"] != step["resultHash"]
        ):
            raise AssertionError("中短篇清单未绑定真实生产 Step")
        current = sorted(
            (item for item in evidence if item["bundleId"] == step["bundleId"]),
            key=lambda item: item["ordinal"],
        )
        if len(current) != index + 1 or current[0]["resourceType"] != "short_medium_context":
            raise AssertionError("中短篇下一段缺少完整证据来源")
        for prior_index, item in enumerate(current[1:]):
            if (
                item["resourceType"] != "short_medium_segment"
                or item["resourceId"] != steps[prior_index]["id"]
                or item["content"]
                != {
                    "index": prior_index,
                    "content": texts[prior_index],
                    "contentSha256": sha(texts[prior_index]),
                }
            ):
                raise AssertionError("中短篇前缀来源不是真实已完成段的完整原文")
        texts.append(text)
        journal = acceptance.wait_delivered_journal(step["id"])
        if (
            journal["requestHash"] != step["requestHash"]
            or journal["resultHash"] != step["resultHash"]
            or journal["fencingToken"] != step["fencingToken"]
        ):
            raise AssertionError("中短篇 Core 与 execution journal 身份不一致")
        journals.append(journal)
    if "".join(texts) != expected_text:
        raise AssertionError("中短篇最终正文被截断或额外拼入分隔符")
    expected_reference = (
        {"candidateVersionId": candidate_id}
        if candidate_id
        else {"checkReportStepId": steps[-1]["id"]}
    )
    if output != expected_reference:
        raise AssertionError("中短篇汇总结果引用不精确")
    return raw | {
        "contentSha256": sha(expected_text),
        "segmentHashes": [sha(text) for text in texts],
        "stepIds": [step["id"] for step in steps],
        "providerKeys": [step["idempotencyKey"] for step in steps],
        "journals": journals,
        "fullPrefixVerified": True,
    }


def _adopt(
    acceptance: Acceptance,
    *,
    run_id: str,
    candidate: str,
    document: str,
    base: str | None,
    expected_content: str,
    key: str,
) -> None:
    root = f"/api/v1/novels/{acceptance.novel_id}"
    detail = acceptance.request("GET", f"{root}/versions/{candidate}", expected=200).json()
    if (
        detail["id"] != candidate
        or detail["status"] != "awaiting_user"
        or detail["content"] != expected_content
        or detail["contentHash"] != sha(expected_content)
        or detail["payload"]["sourceTaskId"] != run_id
        or detail["taskId"] is not None
    ):
        raise AssertionError("中短篇候选不是当前 Run 的完整版本")
    body = {
        "clientRequestId": key,
        "documentType": document,
        "baseVersionId": base,
        "chapterId": acceptance.chapter_id if document == "manuscript" else None,
        "confirmationHash": detail["diff"]["confirmationHash"],
    }
    first = acceptance.request(
        "POST", f"{root}/versions/{candidate}/adopt", expected=200, json_body=body
    ).json()
    replay = acceptance.request(
        "POST", f"{root}/versions/{candidate}/adopt", expected=200, json_body=body
    ).json()
    if first != replay or first["status"] != "applied" or first["content"] != expected_content:
        raise AssertionError("中短篇原确认请求未幂等采用同一完整候选")
    if document == "manuscript":
        chapter = acceptance.request(
            "GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200
        ).json()
        if chapter["content"] != expected_content:
            raise AssertionError("中短篇采用后正文未逐字回读")


def _submit_initial_manuscript(acceptance: Acceptance, outline_id: str) -> str:
    """创建时填入的固定开头先走原人工版本流程，不绕过干净工作稿规则。"""
    root = f"/api/v1/novels/{acceptance.novel_id}"
    chapter = acceptance.request(
        "GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200
    ).json()
    if chapter.get("id") != acceptance.chapter_id or chapter.get("content") != OPENING:
        raise AssertionError("初始正文工作稿没有保留创建时的完整固定开头")
    binding = {
        "documentType": "manuscript",
        "chapterId": acceptance.chapter_id,
        "baseVersionId": None,
    }
    preview = acceptance.request(
        "POST", f"{root}/versions/preview", expected=200, json_body=binding
    ).json()
    if (
        preview.get("dirty") is not True
        or preview.get("baseVersionId") is not None
        or preview.get("contentHash") != sha(OPENING)
    ):
        raise AssertionError("初始正文预览没有绑定未版本化的完整固定开头")
    submitted = acceptance.request(
        "POST",
        f"{root}/versions",
        expected=200,
        json_body={
            **binding,
            "clientRequestId": "e2e-short-initial-manuscript-0001",
            "expectedUpdatedAt": preview["expectedUpdatedAt"],
            "contentHash": preview["contentHash"],
            "confirmationHash": preview["confirmationHash"],
            "summary": "隔离验收：保存创建时已有的固定开头工作稿",
        },
    ).json()
    version_id = submitted.get("id")
    payload = submitted.get("payload")
    if (
        not isinstance(version_id, str)
        or not version_id
        or submitted.get("status") != "applied"
        or submitted.get("source") != "manual"
        or submitted.get("content") != OPENING
        or submitted.get("contentHash") != sha(OPENING)
        or submitted.get("sourceOutlineVersionId") != outline_id
        or not isinstance(payload, dict)
        or payload.get("sourceOutlineVersionId") != outline_id
    ):
        raise AssertionError("初始正文人工版本未保留完整开头或未绑定当前已采用蓝图")
    clean = acceptance.request(
        "POST",
        f"{root}/versions/preview",
        expected=200,
        json_body={**binding, "baseVersionId": version_id},
    ).json()
    if (
        clean.get("dirty") is not False
        or clean.get("baseVersionId") != version_id
        or clean.get("contentHash") != sha(OPENING)
    ):
        raise AssertionError("初始正文人工提交后工作稿仍未与基础版本一致")
    acceptance.safe_diagnostics["shortInitialManuscript"] = {
        "versionId": version_id,
        "sourceOutlineVersionId": outline_id,
        "contentSha256": sha(OPENING),
        "dirty": False,
    }
    return version_id


def scenarios(acceptance: Acceptance) -> Iterator[Scenario]:
    from .run_e2e import Scenario

    created = acceptance.request(
        "POST",
        "/api/v1/novels",
        expected=201,
        json_body={
            "name": "中短篇 V2 隔离验收",
            "storyLengthProfile": "short_medium",
            "targetTotalWordCount": 15001,
            "sourceKind": "opening",
            "sourceText": OPENING,
            "clientRequestId": "e2e-short-create-0001",
        },
    ).json()
    acceptance.novel_id, acceptance.chapter_id = created["novelId"], created["chapterId"]
    acceptance.stack.activate_durable_scope(
        user_id=acceptance.user_id, novel_id=acceptance.novel_id
    )
    outline_id: str | None = None
    manuscript_id: str | None = None
    manuscript = "".join(
        manuscript_segment(index, 2, source_kind="opening", source_text=OPENING)
        for index in range(2)
    )
    replacement_start = len(OPENING)
    replacement_end = replacement_start + len("第1连续单元😀。")
    replaced = manuscript[:replacement_start] + REPLACEMENT + manuscript[replacement_end:]
    for operation in ("generate_outline", "generate_manuscript", "replace_selection", "full_check"):
        if operation == "generate_manuscript" and manuscript_id is None:
            if outline_id is None:
                raise AssertionError("提交初始正文版本前缺少已采用蓝图")
            manuscript_id = _submit_initial_manuscript(acceptance, outline_id)
        document = "outline" if operation == "generate_outline" else "manuscript"
        base = outline_id if document == "outline" else manuscript_id
        key = "e2e-short-" + operation + "-0001"
        body: dict[str, object] = {
            "clientRequestId": key,
            "workflow": "short_medium",
            "novelId": acceptance.novel_id,
            "documentType": document,
            "operation": operation,
            "chapterId": acceptance.chapter_id if document == "manuscript" else None,
            "baseVersionId": base,
            "userInstruction": "保留完整素材，只执行当前操作。",
        }
        if operation == "generate_manuscript":
            body["sourceOutlineVersionId"] = outline_id
            acceptance.control_request(
                "PUT", "/control/callback-mode", {"mode": "hold_before_forward"}
            )
        if operation == "replace_selection":
            body.update(
                selectionStart=replacement_start,
                selectionEnd=replacement_end,
                selectedTextHash=sha(manuscript[replacement_start:replacement_end]),
            )
        before = acceptance.provider_keys()
        started = acceptance.start_run(body).json()
        run_id = started["runId"]
        if started.get("engineVersion") != 2:
            raise AssertionError("中短篇隔离任务未走 V2")
        restart = None
        if operation == "generate_manuscript":
            acceptance.wait_callback_gate(run_id, minimum_reached=1)
            restart = acceptance.stack.restart_and_wait("agent-service")
            acceptance.wait_callback_gate(run_id, minimum_reached=2, timeout=60)
            acceptance.control_request("POST", "/control/callback-release", {"abort": False})
        terminal = acceptance.wait_terminal(run_id, timeout=90)
        if terminal.get("engineVersion") != 2 or terminal.get("status") != "completed":
            raise AssertionError("中短篇跨进程任务未完成：" + str(terminal.get("error")))
        model_count = 2 if operation == "generate_manuscript" else 1
        expected_model_text = {
            "generate_outline": OUTLINE,
            "generate_manuscript": manuscript,
            "replace_selection": REPLACEMENT,
            "full_check": REPORT,
        }[operation]
        candidate = terminal.get("candidateVersionId")
        if operation == "full_check":
            if candidate is not None or terminal.get("checkReport") != {"text": REPORT}:
                raise AssertionError("中短篇检查未回读完整报告或错误生成候选")
        else:
            if not isinstance(candidate, str) or not candidate:
                raise AssertionError("中短篇完成缺少精确候选")
            expected_content = replaced if operation == "replace_selection" else expected_model_text
            _adopt(
                acceptance,
                run_id=run_id,
                candidate=candidate,
                document=document,
                base=base,
                expected_content=expected_content,
                key=key + "-adopt",
            )
            if document == "outline":
                outline_id = candidate
            else:
                manuscript_id = candidate
        facts = _facts(
            acceptance,
            run_id,
            operation=operation,
            expected_text=expected_model_text,
            model_count=model_count,
            candidate_id=candidate,
        )
        providers = [
            item for item in acceptance.provider_facts() if item["idempotency_key"] not in before
        ]
        if len(providers) != model_count or any(
            item["physical_calls"] != 1 or item["completed_calls"] != 1 for item in providers
        ):
            raise AssertionError("已完成中短篇段被重复调用或缺少真实模型调用")
        if {item["idempotency_key"] for item in providers} != set(facts["providerKeys"]):
            raise AssertionError("中短篇 Provider 调用身份不属于当前 Run 的真实 Step")
        if restart is not None:
            facts["serviceRestart"] = restart
        yield Scenario(
            name="short_medium_" + operation,
            run_id=run_id,
            session_id="",
            client_request_id=key,
            provider_identity={"calls": providers},
            database_facts=facts,
        )
