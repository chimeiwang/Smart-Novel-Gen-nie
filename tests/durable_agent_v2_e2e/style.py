"""复用原框架验证用户级画像五节原子完成、首节重启恢复与单节重做。"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from inkforge_contracts.style_execution import StylePortraitContextV2

from .style_fixture import (
    ORIGINAL_CHAR_COUNT,
    REFERENCES,
    SECTIONS,
    SOURCE_TEXT,
    portrait_markdown,
    raw_section,
    sha,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .run_e2e import Acceptance, Scenario


def _style(acceptance: Acceptance, style_id: str) -> dict[str, object]:
    styles = acceptance.request("GET", "/api/v1/styles", expected=200).json()
    found = [style for style in styles if style["id"] == style_id]
    if len(found) != 1:
        raise AssertionError("画像公开列表没有唯一当前文风")
    return found[0]


def _upload(acceptance: Acceptance, style_id: str) -> list[dict[str, object]]:
    references = []
    for filename, content in REFERENCES:
        response = acceptance.core.post(
            f"/api/v1/styles/{style_id}/references",
            files={"file": (filename, content.encode("utf-8"), "text/plain")},
        )
        if response.status_code != 201:
            raise AssertionError("画像 UTF-8 参考上传返回 HTTP " + str(response.status_code))
        reference = response.json()
        if (
            reference["styleId"] != style_id
            or reference["filename"] != filename
            or reference["status"] != "ready"
            or reference["charCount"] != sum(not char.isspace() for char in content)
        ):
            raise AssertionError("画像上传未保留 UTF-8/BOM 或原非空白 Unicode 字数")
        references.append(reference)
    if references != sorted(references, key=lambda value: (value["createdAt"], value["id"])):
        raise AssertionError("画像参考上传顺序与冻结排序不一致")
    return references


def _wait_task(acceptance: Acceptance, style_id: str, run_id: str, section: str | None) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        task = acceptance.request("GET", f"/api/v1/portrait-tasks/{run_id}", expected=200).json()
        if task["id"] != run_id or task["styleId"] != style_id or task["section"] != section:
            raise AssertionError("画像原任务查询身份不匹配")
        if task["status"] == "success":
            return
        if task["status"] not in {"pending", "processing"}:
            raise AssertionError("画像运行未成功：" + str(task["status"]))
        time.sleep(0.2)
    raise AssertionError("画像任务未在门限内完成")


def assert_style_facts(facts: dict[str, object], *, count: int) -> None:
    expected = {
        "engineVersion": 2,
        "workflow": "style",
        "operation": "portrait",
        "status": "completed",
        "novelId": None,
        "chapterId": None,
        "writingSessionId": None,
        "sourceType": "style_portrait_v2",
        "targetType": "style_profile",
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
        "creditLedgerCount": 0,
        "legacyPortraitTaskCount": 0,
        "legacyWritingTaskCount": 0,
        "legacyCommandCount": 0,
        "artifactCount": 0,
        "evaluationCount": 0,
    }
    failures = [key for key, value in expected.items() if key not in facts or facts[key] != value]
    if failures:
        raise AssertionError("画像耐久事实不一致：" + ",".join(failures))


def _facts(
    acceptance: Acceptance,
    run_id: str,
    style_id: str,
    *,
    section: str | None,
    references: list[dict[str, object]],
    expected_sections: dict[str, str],
) -> dict[str, object]:
    raw = json.loads(
        acceptance.stack.psql(
            """
      SELECT json_build_object(
        'engineVersion',r."engineVersion",'workflow',r.workflow,'operation',r.operation,
        'status',r.status::text,'novelId',r."novelId",'chapterId',r."chapterId",
        'writingSessionId',r."writingSessionId",'sourceType',r."sourceType",'sourceId',r."sourceId",
        'targetType',r."targetType",'targetId',r."targetId",'output',r.output::jsonb,
        'stepCount',(SELECT count(*) FROM public."WorkflowStep" WHERE "runId"=r.id),
        'completedStepCount',(SELECT count(*) FROM public."WorkflowStep"
          WHERE "runId"=r.id AND status='completed'),
        'generationCount',(SELECT count(*) FROM public."WorkflowStep"
          WHERE "runId"=r.id AND purpose='generation'),
        'terminalEventCount',(SELECT count(*) FROM public."WorkflowEvent"
          WHERE "runId"=r.id AND "eventType" IN ('completed','failed','cancelled')),
        'completedEventCount',(SELECT count(*) FROM public."WorkflowEvent"
          WHERE "runId"=r.id AND "eventType"='completed'),
        'completedPayload',(SELECT "payloadJson"::jsonb FROM public."WorkflowEvent"
          WHERE "runId"=r.id AND "eventType"='completed'),
        'bundleCount',(SELECT count(*) FROM public."WorkflowEvidenceBundle" WHERE "runId"=r.id),
        'evidenceCount',(SELECT count(*) FROM public."WorkflowEvidenceItem" i
          JOIN public."WorkflowEvidenceBundle" b ON b.id=i."bundleId" WHERE b."runId"=r.id),
        'context',(SELECT i."contentJson"::jsonb FROM public."WorkflowEvidenceItem" i
          WHERE i."bundleId"=r."currentEvidenceBundleId"),
        'reservationCount',(SELECT count(*) FROM public."WorkflowBillingReservation"
          WHERE "runId"=r.id),
        'tokenUsageCount',(SELECT count(*) FROM public."TokenUsage" WHERE "runId"=r.id),
        'userBalanceMicros',(SELECT "creditBalanceMicros" FROM public."User"
          WHERE id=r."userId"),
        'creditLedgerCount',(SELECT count(*) FROM public."CreditLedger"
          WHERE "requestId" IN (SELECT "requestId" FROM public."WorkflowBillingReservation"
            WHERE "runId"=r.id)),
        'matchedBillingCount',(SELECT count(*) FROM public."WorkflowStep" s
          JOIN public."WorkflowBillingReservation" b ON b."stepId"=s.id AND b."runId"=r.id
          JOIN public."TokenUsage" u ON u."requestId"=b."requestId"
            AND u."taskId"=s.id AND u."runId"=r.id
          WHERE s."runId"=r.id AND u."novelId" IS NULL AND u."userId"=r."userId"
            AND b."userId"=r."userId" AND b.status='settled'
            AND b."reservedMicros"=0 AND b."chargedMicros"=0 AND b."settledAt" IS NOT NULL
            AND b."usageJson"::jsonb=s."usageJson"::jsonb AND u.model='fake'
            AND u."promptTokens"=(s."usageJson"::jsonb->>'inputTokens')::int
            AND u."cachedTokens"=(s."usageJson"::jsonb->>'cachedTokens')::int
            AND u."promptCacheMissTokens"=(s."usageJson"::jsonb->>'promptCacheMissTokens')::int
            AND u."completionTokens"=(s."usageJson"::jsonb->>'completionTokens')::int
            AND u."reasoningTokens"=(s."usageJson"::jsonb->>'reasoningTokens')::int
            AND u."completionTokens"-u."reasoningTokens"
              =(s."usageJson"::jsonb->>'visibleOutputTokens')::int
            AND u."totalTokens"=u."promptTokens"+u."completionTokens"),
        'legacyPortraitTaskCount',(SELECT count(*) FROM public."StylePortraitTask"
          WHERE "styleId"=r."targetId"),
        'legacyWritingTaskCount',(SELECT count(*) FROM public."WritingTask" t
          JOIN public."Novel" n ON n.id=t."novelId" WHERE n."userId"=r."userId"),
        'legacyCommandCount',(SELECT count(*) FROM public."WritingRunCommand" x
          JOIN public."WritingTask" t ON t.id=x."taskId"
          JOIN public."Novel" n ON n.id=t."novelId" WHERE n."userId"=r."userId"),
        'artifactCount',(SELECT count(*) FROM public."ReviewArtifact" WHERE "workflowRunId"=r.id),
        'evaluationCount',(SELECT count(*) FROM public."WorkflowEvaluation" WHERE "runId"=r.id),
        'steps',(SELECT json_agg(json_build_object(
          'id',s.id,'input',s.input::jsonb,'output',s.output::jsonb,'bundleId',s."evidenceBundleId",
          'profile',s."modelProfile",'lane',s.lane,'idempotencyKey',s."idempotencyKey",
          'route',s."resolvedModelJson"::jsonb->>'structuredOutputRoute',
          'resultHash',s."resultHash",'requestHash',s."requestHash",'fencingToken',s."fencingToken",
          'usage',s."usageJson"::jsonb) ORDER BY s.ordinal)
          FROM public."WorkflowStep" s WHERE s."runId"=r.id)
      )::text FROM public."WorkflowRun" r WHERE r.id=:'e2e_run_id';
    """,
            variables={"e2e_run_id": run_id},
        )
    )
    sections = (section,) if section else SECTIONS
    assert_style_facts(raw, count=len(sections))
    balance = raw.pop("userBalanceMicros")
    initial_balance = acceptance.initial_credit_balance_micros
    if type(balance) is not int or type(initial_balance) is not int or balance != initial_balance:
        raise AssertionError("画像 Fake 调用缺少真实余额或导致用户余额变化")
    if raw["targetId"] != style_id or raw["sourceId"] != style_id:
        raise AssertionError("画像 Run 没有绑定真实用户级文风")
    context = StylePortraitContextV2.model_validate(raw.pop("context"))
    expected_refs = [
        {
            "referenceId": reference["id"],
            "filename": filename,
            "charCount": reference["charCount"],
            "content": content,
            "contentSha256": sha(content),
        }
        for reference, (filename, content) in zip(references, REFERENCES, strict=True)
    ]
    if context.model_dump(mode="json") != {
        "styleId": style_id,
        "mode": "section" if section else "full",
        "section": section,
        "references": expected_refs,
        "originalCharCount": ORIGINAL_CHAR_COUNT,
        "sourceTextSha256": sha(SOURCE_TEXT),
    }:
        raise AssertionError("画像冻结来源、排序、BOM 或元数据字数不完整")
    expected_output = {
        "mode": "section" if section else "full",
        "originalCharCount": ORIGINAL_CHAR_COUNT,
        "usedCharCount": ORIGINAL_CHAR_COUNT,
        "truncated": False,
    }
    if section:
        expected_output.update(section=section, content=raw_section(section).strip())
    else:
        expected_output.update({name: raw_section(name).strip() for name in SECTIONS})
    if raw.pop("output") != expected_output:
        raise AssertionError("画像最终 Run 结果未按原 Python strip 处理完整文本")
    if raw.pop("completedPayload") != {"outcomeType": "style_portrait", "resultId": style_id}:
        raise AssertionError("画像唯一终态事件未指向当前文风")
    style = _style(acceptance, style_id)
    if (
        any(style[name] != expected_sections[name] for name in SECTIONS)
        or style["portraitMarkdown"] != portrait_markdown(expected_sections)
        or style["originalCharCount"] != ORIGINAL_CHAR_COUNT
        or style["usedCharCount"] != ORIGINAL_CHAR_COUNT
        or style["truncated"] is not False
        or style["errorMessage"] is not None
    ):
        raise AssertionError("公开完整文风、五节拼接或单节不改其他字段规则不一致")
    tasks = [task for task in style["tasks"] if task["id"] == run_id]
    if len(tasks) != 1 or tasks[0]["status"] != "success" or tasks[0]["section"] != section:
        raise AssertionError("Style 列表没有双读同一成功画像任务")
    steps = raw.pop("steps")
    if len(steps) != len(sections) or len({step["bundleId"] for step in steps}) != 1:
        raise AssertionError("画像五节未复用同一完整 Evidence")
    journals = []
    for index, (name, step) in enumerate(zip(sections, steps, strict=True)):
        if (
            step["input"] != {"section": name}
            or step["output"] != {"content": raw_section(name)}
            or step["route"] != "plain_text_v1"
            or step["profile"] != "style.portrait.v2"
            or step["lane"] != "batch_media"
            or step["usage"]["providerAttempts"] != 1
            or step["usage"]["protocolCorrections"] != 0
            or step["usage"]["reasoningTokens"] != 0
            or step["idempotencyKey"] != run_id + "." + step["id"]
        ):
            raise AssertionError("画像原始 Step、纯文本路由或逐节独立调用不一致")
        journal = acceptance.wait_delivered_journal(step["id"])
        attempts = [
            item
            for item in acceptance.control_state()["callbackAttempts"]
            if item["run_id"] == run_id
            and item["step_id"] == step["id"]
            and item.get("callback_kind") == "result"
        ]
        if not any(item.get("receipt_status") == "accepted" for item in attempts):
            raise AssertionError("画像终态缺少合法 Core 回执")
        acceptance.assert_callback_attempt_bindings(
            run_id=run_id,
            step=step,
            journal=journal,
            attempts=attempts,
            allow_one_unauthenticated_inflight_request=section is None and index == 0,
        )
        if (
            section is None
            and index == 0
            and len([item for item in attempts if item["action"] == "held_before_forward"]) < 2
        ):
            raise AssertionError("画像首节没有形成 Agent 重启前后的两次相同终态投递")
        journals.append(journal)
    return raw | {
        "stepIds": [step["id"] for step in steps],
        "providerKeys": [step["idempotencyKey"] for step in steps],
        "journals": journals,
        "rawSectionHashes": [sha(raw_section(name)) for name in sections],
        "finalSectionHashes": {name: sha(expected_sections[name]) for name in SECTIONS},
        "sourceTextSha256": sha(SOURCE_TEXT),
        "originalCharCount": ORIGINAL_CHAR_COUNT,
        "rawAndPythonStripVerified": True,
        "fullStyleVerified": True,
        "balanceDeltaMicros": balance - initial_balance,
        "balanceUnchanged": True,
    }


def scenarios(acceptance: Acceptance) -> Iterator[Scenario]:
    from .run_e2e import Scenario

    style_id = acceptance.request(
        "POST", "/api/v1/styles", expected=201, json_body={"name": "画像 V2 隔离验收"}
    ).json()["id"]
    references = _upload(acceptance, style_id)
    expected_sections = {name: raw_section(name).strip() for name in SECTIONS}
    for section in (None, "uniqueMarkers"):
        if section:
            acceptance.request(
                "PATCH",
                f"/api/v1/styles/{style_id}/sections/creativeMethodology",
                expected=200,
                json_body={"content": "作者在单节重做前保留的新方法。"},
            )
            expected_sections["creativeMethodology"] = "作者在单节重做前保留的新方法。"
            acceptance.request(
                "PATCH",
                f"/api/v1/styles/{style_id}/sections/{section}",
                expected=200,
                json_body={"content": "待重做的旧标记。"},
            )
        before = acceptance.provider_keys()
        if section is None:
            acceptance.control_request(
                "PUT", "/control/callback-mode", {"mode": "hold_before_forward"}
            )
        suffix = "/portrait" if section is None else f"/sections/{section}/portrait"
        started = acceptance.request(
            "POST", f"/api/v1/styles/{style_id}{suffix}", expected=202
        ).json()
        run_id = started["taskId"]
        restart = None
        if section is None:
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
                raise AssertionError("画像首节尚未持久化完整 terminal journal")
            restart = acceptance.stack.restart_and_wait("agent-service")
            acceptance.wait_callback_gate(run_id, minimum_reached=2, timeout=60)
            acceptance.control_request("PUT", "/control/provider-mode", {"mode": "hold"})
            acceptance.control_request("POST", "/control/callback-release", {"abort": False})
            acceptance.wait_provider_gate()
            completed = acceptance.stack.psql(
                'SELECT count(*) FROM public."WorkflowStep" '
                "WHERE \"runId\"=:'run' AND status='completed';",
                variables={"run": run_id},
            )
            partial = _style(acceptance, style_id)
            if (
                completed != "1"
                or any(partial[name] is not None for name in SECTIONS)
                or partial["portraitMarkdown"] is not None
            ):
                raise AssertionError("画像全套尚未完成就写入了部分节，或首节被重复执行")
            acceptance.control_request("POST", "/control/provider-release", {"abort": False})
        _wait_task(acceptance, style_id, run_id, section)
        facts = _facts(
            acceptance,
            run_id,
            style_id,
            section=section,
            references=references,
            expected_sections=expected_sections,
        )
        providers = [
            item for item in acceptance.provider_facts() if item["idempotency_key"] not in before
        ]
        if (
            len(providers) != (5 if section is None else 1)
            or any(
                item["physical_calls"] != 1 or item["completed_calls"] != 1 for item in providers
            )
            or {item["idempotency_key"] for item in providers} != set(facts["providerKeys"])
        ):
            raise AssertionError("画像完整五节或单节没有逐 Step 恰好一次模型调用")
        if restart:
            facts.update(serviceRestart=restart, heldFirstJournal=held, noPartialStyleWrite=True)
        yield Scenario(
            name="style_full_agent_restart" if section is None else "style_single_section",
            run_id=run_id,
            session_id="",
            client_request_id="",
            provider_identity={"calls": providers},
            database_facts=facts,
        )
