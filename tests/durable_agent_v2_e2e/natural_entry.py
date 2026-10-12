"""普通自然消息、同 Run 澄清与现有三项业务的真实隔离跨进程验收。"""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, cast

from .chapter_planning import _artifact as plan_artifact
from .chapter_planning import _facts as plan_facts
from .chapter_writing import _artifact as writing_artifact
from .chapter_writing import _facts as writing_facts
from .chapter_writing import _other_layers

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .run_e2e import Acceptance, Scenario

_MODEL_PURPOSES = {"resolve_intent", "generation", "review"}


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def natural_body(
    novel_id: str, chapter_id: str, session_id: str, request_id: str, instruction: str
) -> dict[str, object]:
    return {
        "inputMode": "natural",
        "workflow": "long_serial",
        "novelId": novel_id,
        "chapterId": chapter_id,
        "writingSessionId": session_id,
        "clientRequestId": request_id,
        "userInstruction": instruction,
        "targetWordCount": 1000,
    }


def assert_natural_facts(
    facts: dict[str, object],
    *,
    operation: str | None,
    answers: int,
    business_steps: int,
    session_runs: int = 1,
) -> None:
    resolved = operation is not None
    models = answers + 1 + business_steps
    expected = {
        "engineVersion": 2,
        "databaseOperation": None,
        "publicOperation": operation,
        "status": "completed" if resolved else "failed",
        "errorCode": None if resolved else "INTENT_UNRESOLVED",
        "sessionRunCount": session_runs,
        "legacyTaskCount": 0,
        "legacyCommandCount": 0,
        "resolverCount": answers + 1,
        "badResolverProfileCount": 0,
        "businessStepCount": business_steps,
        "modelStepCount": models,
        "badModelStepCount": 0,
        "matchedBillingCount": models,
        "reservationCount": models,
        "tokenUsageCount": models,
        "creditLedgerCount": 0,
        "balanceDeltaMicros": 0,
        "questionCount": answers,
        "answerCount": answers,
        "selectionCount": int(resolved),
        "badControlStepCount": 0,
        "evidenceBundleCount": 1 + int(resolved),
        "resolverEvidenceCount": 1,
        "badResolverEvidenceCount": 0,
        "businessEvidenceCount": int(resolved),
        "businessOnIntentEvidenceCount": 0,
        "completedEventCount": int(resolved),
        "failedEventCount": int(not resolved),
        "messageHistoryVerified": True,
        "inputHistoryVerified": True,
        "controlHashesVerified": True,
    }
    mismatches = [key for key, value in expected.items() if key not in facts or facts[key] != value]
    if mismatches:
        raise AssertionError("自然入口持久证据不符合预期：" + ",".join(mismatches))


def assert_provider_steps(providers: list[dict[str, object]], model_steps: int) -> None:
    keys = [provider.get("idempotency_key") for provider in providers]
    if (
        len(providers) != model_steps
        or len(set(keys)) != model_steps
        or any(not isinstance(key, str) or not key for key in keys)
        or any(
            provider.get("physical_calls") != 1 or provider.get("completed_calls") != 1
            for provider in providers
        )
    ):
        raise AssertionError("自然入口每个模型 Step 必须恰好一次真实 Fake Provider 调用")


def _wait(acceptance: Acceptance, run_id: str, *, clarification: bool) -> dict[str, object]:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        snapshot = acceptance.request("GET", f"/api/v1/writing/runs/{run_id}", expected=200).json()
        if snapshot.get("engineVersion") != 2 or snapshot.get("runId") != run_id:
            raise AssertionError("自然入口切换了引擎或 Run 身份")
        acceptance.safe_diagnostics["naturalEntryLastSnapshot"] = snapshot
        if snapshot.get("status") == "waiting_user":
            if clarification != isinstance(snapshot.get("clarification"), dict):
                raise AssertionError("自然入口等待原因不是预期的澄清或作者确认")
            return cast(dict[str, object], snapshot)
        if snapshot.get("status") in {"completed", "failed", "cancelled"}:
            raise AssertionError("自然入口尚未进入预期等待便结束")
        time.sleep(0.2)
    raise AssertionError("自然入口未在门限内进入预期等待")


def _answer(
    acceptance: Acceptance, snapshot: dict[str, object], request_id: str, message: str
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    question = snapshot.get("clarification")
    if not isinstance(question, dict) or not isinstance(question.get("decisionStepId"), str):
        raise AssertionError("自然入口快照缺少当前决定身份")
    body: dict[str, object] = {
        "clientRequestId": request_id,
        "expectedRevision": snapshot["revision"],
        "decisionStepId": question["decisionStepId"],
        "userMessage": message,
    }
    path = f"/api/v1/writing/runs/{snapshot['runId']}/clarification"
    receipt = acceptance.request("POST", path, expected=202, json_body=body).json()
    if (
        receipt.get("runId") != snapshot["runId"]
        or receipt.get("status") != "pending"
        or receipt.get("operation") is not None
        or receipt.get("clarification") is not None
        or receipt.get("revision") != cast(int, snapshot["revision"]) + 1
    ):
        raise AssertionError("澄清回答没有受理到原 Run 的下一解析器")
    if acceptance.request("POST", path, expected=202, json_body=body).json() != receipt:
        raise AssertionError("澄清即时幂等重放没有返回原始受理回执")
    return (
        body,
        receipt,
        {
            "decisionStepId": question["decisionStepId"],
            "prompt": question["prompt"],
            "userMessage": message,
        },
    )


def _facts(
    acceptance: Acceptance,
    run_id: str,
    snapshot: dict[str, object],
    instruction: str,
    answers: list[dict[str, object]],
    *,
    session_messages: list[str] | None = None,
) -> dict[str, object]:
    raw = json.loads(
        acceptance.stack.psql(
            """
        SELECT json_build_object(
          'engineVersion',r."engineVersion",'databaseOperation',r.operation,
          'status',r.status::text,'errorCode',r."errorCode",'runInput',r.input::jsonb,
          'sessionRunCount',(SELECT count(*) FROM public."WorkflowRun"
            WHERE "writingSessionId"=r."writingSessionId"),
          'legacyTaskCount',(SELECT count(*) FROM public."WritingTask" WHERE "novelId"=r."novelId"),
          'legacyCommandCount',(SELECT count(*) FROM public."WritingRunCommand" c
            JOIN public."WritingTask" t ON t.id=c."taskId" WHERE t."novelId"=r."novelId"),
          'steps',(SELECT json_agg(json_build_object('id',s.id,'purpose',s.purpose,
            'status',s.status::text,'lane',s.lane,'stepType',s."stepType"::text,
            'attemptCount',s."attemptCount",'fencingToken',s."fencingToken",
            'input',s.input::jsonb,'output',s.output::jsonb,'inputHash',s."inputHash",
            'resultHash',s."resultHash",'evidenceBundleId',s."evidenceBundleId",
            'modelProfile',s."modelProfile",'budget',s."budgetJson"::jsonb,
            'usage',s."usageJson"::jsonb,'errorCode',s."errorCode",
            'hasBilling',EXISTS(SELECT 1 FROM public."WorkflowBillingReservation" b
              WHERE b."stepId"=s.id)) ORDER BY s.ordinal)
            FROM public."WorkflowStep" s WHERE s."runId"=r.id),
          'bundles',(SELECT json_agg(json_build_object('id',b.id,'version',b.version,
            'policyVersion',b."policyVersion")) FROM public."WorkflowEvidenceBundle" b
            WHERE b."runId"=r.id),
          'userMessages',(SELECT json_agg(m.content ORDER BY m."createdAt",m.id)
            FROM public."WritingMessage" m
            WHERE m."sessionId"=r."writingSessionId" AND m.role='user'),
          'matchedBillingCount',(SELECT count(*) FROM public."WorkflowStep" s
            JOIN public."WorkflowBillingReservation" b ON b."stepId"=s.id AND b."runId"=r.id
            JOIN public."TokenUsage" u ON u."requestId"=b."requestId"
              AND u."runId"=r.id AND u."taskId"=s.id
            WHERE s."runId"=r.id AND s.purpose IN ('resolve_intent','generation','review')
              AND b."userId"=r."userId" AND u."userId"=r."userId" AND u.model='fake'
              AND b.status='settled' AND b."reservedMicros"=0 AND b."chargedMicros"=0
              AND b."settledAt" IS NOT NULL AND b."usageJson"::jsonb=s."usageJson"::jsonb
              AND u."promptTokens"=(s."usageJson"::jsonb->>'inputTokens')::int
              AND u."cachedTokens"=(s."usageJson"::jsonb->>'cachedTokens')::int
              AND u."promptCacheMissTokens" IS NOT DISTINCT FROM
                (s."usageJson"::jsonb->>'promptCacheMissTokens')::int
              AND u."reasoningTokens" IS NOT DISTINCT FROM
                (s."usageJson"::jsonb->>'reasoningTokens')::int
              AND u."completionTokens"=(s."usageJson"::jsonb->>'completionTokens')::int
              AND u."totalTokens"=u."promptTokens"+u."completionTokens"),
          'reservationCount',(SELECT count(*) FROM public."WorkflowBillingReservation"
            WHERE "runId"=r.id),
          'tokenUsageCount',(SELECT count(*) FROM public."TokenUsage" WHERE "runId"=r.id),
          'creditLedgerCount',(SELECT count(*) FROM public."CreditLedger" WHERE "requestId" IN
            (SELECT "requestId" FROM public."WorkflowBillingReservation" WHERE "runId"=r.id)),
          'userBalance',(SELECT "creditBalanceMicros" FROM public."User" WHERE id=r."userId"),
          'completedEventCount',(SELECT count(*) FROM public."WorkflowEvent"
            WHERE "runId"=r.id AND "eventType"='completed'),
          'failedEventCount',(SELECT count(*) FROM public."WorkflowEvent"
            WHERE "runId"=r.id AND "eventType"='failed')
        )::text FROM public."WorkflowRun" r WHERE r.id=:'e2e_run_id';
        """,
            variables={"e2e_run_id": run_id},
        )
    )
    steps = raw.pop("steps")
    bundles = raw.pop("bundles")
    original = raw.pop("runInput")
    messages = raw.pop("userMessages")
    if not isinstance(steps, list) or not isinstance(bundles, list):
        raise AssertionError("自然入口缺少持久 Step 或 Evidence")
    models = [step for step in steps if step["purpose"] in _MODEL_PURPOSES]
    resolvers = [step for step in models if step["purpose"] == "resolve_intent"]
    business = [step for step in models if step["purpose"] != "resolve_intent"]
    controls = [step for step in steps if step["purpose"].startswith("intent_")]
    resolver_bundle_ids = {step["evidenceBundleId"] for step in resolvers}
    business_bundle_ids = {step["evidenceBundleId"] for step in business}
    balance = raw.pop("userBalance")
    expected_business_instruction = (
        instruction
        if not answers
        else _canonical(
            {
                "initialInstruction": instruction,
                "clarifications": [
                    {"prompt": answer["prompt"], "userMessage": answer["userMessage"]}
                    for answer in answers
                ],
            }
        )
    )
    input_verified = (
        original.get("userInstruction") == instruction
        and all(
            step["input"] == {"userInstruction": instruction, "clarifications": answers[:index]}
            for index, step in enumerate(resolvers)
        )
        and all(
            step["input"].get("userInstruction") == expected_business_instruction
            for step in business
            if step["purpose"] == "generation"
        )
    )
    hashes_verified = all(
        _sha(_canonical(step["input"])) == step["inputHash"]
        and (
            step["purpose"] != "intent_clarification_answer"
            or _sha(_canonical(step["output"])) == step["resultHash"]
        )
        for step in controls
    )
    raw.update(
        {
            "publicOperation": snapshot.get("operation"),
            "modelStepCount": len(models),
            "resolverCount": len(resolvers),
            "badResolverProfileCount": sum(
                step["modelProfile"] != "system.intent_resolver.v2" for step in resolvers
            ),
            "businessStepCount": len(business),
            "badModelStepCount": sum(
                step["status"] != "completed"
                or step["attemptCount"] != 1
                or step["fencingToken"] != 1
                or step["resultHash"] is None
                or not isinstance(step["usage"], dict)
                or step["usage"].get("providerAttempts") != 1
                for step in models
            ),
            "questionCount": sum(step["purpose"] == "intent_clarification" for step in controls),
            "answerCount": sum(
                step["purpose"] == "intent_clarification_answer" for step in controls
            ),
            "selectionCount": sum(step["purpose"] == "intent_selection" for step in controls),
            "badControlStepCount": sum(
                step["status"] != "completed"
                or step["lane"] != "control"
                or step["fencingToken"] != 1
                or step["attemptCount"] != 0
                or step["modelProfile"] is not None
                or step["budget"] is not None
                or step["usage"] is not None
                or step["hasBilling"]
                or step["stepType"]
                != ("persistence" if step["purpose"] == "intent_selection" else "user_confirmation")
                for step in controls
            ),
            "evidenceBundleCount": len(bundles),
            "resolverEvidenceCount": len(resolver_bundle_ids),
            "badResolverEvidenceCount": sum(
                bundle["version"] != 1 or bundle["policyVersion"] != "evidence.system.intent.v1"
                for bundle in bundles
                if bundle["id"] in resolver_bundle_ids
            ),
            "businessEvidenceCount": len(business_bundle_ids),
            "businessOnIntentEvidenceCount": len(resolver_bundle_ids & business_bundle_ids),
            "balanceDeltaMicros": balance - acceptance.initial_credit_balance_micros
            if type(balance) is int and type(acceptance.initial_credit_balance_micros) is int
            else None,
            "messageHistoryVerified": messages
            == (
                session_messages
                if session_messages is not None
                else [instruction, *[a["userMessage"] for a in answers]]
            ),
            "inputHistoryVerified": input_verified,
            "controlHashesVerified": hashes_verified,
            "initialInstructionSha256": _sha(instruction),
            "modelStepDiagnostics": [
                {
                    key: step[key]
                    for key in ("id", "purpose", "status", "errorCode", "modelProfile", "usage")
                }
                for step in models
            ],
        }
    )
    acceptance.safe_diagnostics["naturalEntry"] = {"runId": run_id, **raw}
    return cast(dict[str, object], raw)


def _next_message(
    acceptance: Acceptance,
    first_body: dict[str, object],
    first_snapshot: dict[str, object],
    first_facts: dict[str, object],
    first_providers: list[dict[str, object]],
) -> Scenario:
    from .run_e2e import Scenario

    name = "natural_same_session_next_message"
    session_id = cast(str, first_body["writingSessionId"])
    instruction = cast(str, first_body["userInstruction"])
    first_run_id = cast(str, first_snapshot["runId"])
    request_id = f"e2e-{name}-start"
    # 相同完整原文、不同命令身份仍是普通新消息；不调用 clarification 或旧 resume。
    body = {**first_body, "clientRequestId": request_id}
    before = acceptance.provider_keys()
    started = acceptance.start_run(body).json()
    run_id = str(started["runId"])
    if run_id == first_run_id or started.get("operation") is not None:
        raise AssertionError("同会话普通下一条消息没有创建独立的待解析 Run")
    snapshot = acceptance.wait_terminal(run_id, timeout=120)
    messages = [instruction, instruction]
    facts = _facts(acceptance, run_id, snapshot, instruction, [], session_messages=messages)
    assert_natural_facts(
        facts, operation="answer_question", answers=0, business_steps=1, session_runs=2
    )
    old_snapshot = acceptance.start_run(first_body).json()
    if old_snapshot != first_snapshot or old_snapshot.get("runId") == run_id:
        raise AssertionError("旧启动请求重放错误指向了同会话最新 Run")
    if acceptance.start_run(body).json() != snapshot:
        raise AssertionError("同会话第二个启动请求没有重放自己的 Run")
    old_facts = _facts(
        acceptance, first_run_id, first_snapshot, instruction, [], session_messages=messages
    )
    if old_facts != {**first_facts, "sessionRunCount": 2}:
        raise AssertionError("普通第二条消息或旧启动重放改写了第一个 Run 的事实")
    if _facts(acceptance, run_id, snapshot, instruction, [], session_messages=messages) != facts:
        raise AssertionError("普通消息重放新增了用户消息、Step 或计费")
    all_providers = acceptance.provider_facts()
    providers = [p for p in all_providers if p["idempotency_key"] not in before]
    assert_provider_steps(providers, 2)
    models = cast(list[dict[str, object]], facts["modelStepDiagnostics"])
    if {p["idempotency_key"] for p in providers} != {f"{run_id}.{step['id']}" for step in models}:
        raise AssertionError("同会话第二个 Run 的 Provider 身份没有绑定自己的 Step")
    first_keys = {p["idempotency_key"] for p in first_providers}
    previous_providers = [p for p in all_providers if p["idempotency_key"] in first_keys]
    if previous_providers != first_providers:
        raise AssertionError("普通下一条消息或旧启动重放重复执行了第一个 Run")
    assert_provider_steps([*first_providers, *providers], 4)
    return Scenario(
        name=name,
        run_id=run_id,
        session_id=session_id,
        client_request_id=request_id,
        provider_identity={"steps": providers, "previousRunSteps": previous_providers},
        database_facts={
            **facts,
            "previousRunId": first_run_id,
            "previousStartReplayVerified": True,
            "previousRunUnchanged": True,
            "sessionMessageCount": len(messages),
        },
    )


def scenarios(acceptance: Acceptance) -> Iterator[Scenario]:
    from .run_e2e import Scenario

    acceptance.control_request("PUT", "/control/provider-mode", {"mode": "pass"})
    acceptance.control_request("PUT", "/control/chapter-plan-review-mode", {"mode": "pass"})
    acceptance.control_request("PUT", "/control/chapter-writing-review-mode", {"mode": "pass"})
    run_ids: set[str] = set()
    for name, operation, clarify, restart in (
        ("natural_answer_same_run", "answer_question", False, False),
        ("natural_clarification_restart_plan_approve", "plan_chapter", True, True),
        ("natural_two_answers_unresolved", None, True, False),
        ("natural_write_dual_review_approve", "write_chapter", False, False),
    ):
        session_id = acceptance.create_session(name)
        request_id = "e2e-" + name + "-start"
        instruction = (
            "  保留完整原始说明😀\r\n" * 30 + "尾段　" if clarify else f"【隔离意图:{operation}】"
        )
        body = natural_body(
            acceptance.novel_id, acceptance.chapter_id, session_id, request_id, instruction
        )
        provider_before = acceptance.provider_keys()
        started = acceptance.start_run(body).json()
        run_id = str(started["runId"])
        if run_id in run_ids or started.get("operation") is not None:
            raise AssertionError("普通新消息没有新建独立的待解析 Run")
        run_ids.add(run_id)
        if acceptance.start_run(body).json().get("runId") != run_id:
            raise AssertionError("自然启动幂等重放创建了第二个 Run")
        answers: list[dict[str, object]] = []
        accepted: list[tuple[dict[str, object], dict[str, object]]] = []
        runtime: dict[str, object] | None = None
        if clarify:
            waiting = _wait(acceptance, run_id, clarification=True)
            if restart:
                runtime = acceptance.stack.restart_and_wait("core-api")
                restored = _wait(acceptance, run_id, clarification=True)
                if restored != waiting:
                    raise AssertionError("Core 重启没有恢复同一待回答问题和 revision")
            for index in range(2 if operation is None else 1):
                message = (
                    f"  尚未明确第{index + 1}次😀\r\n　"
                    if operation is None
                    else f"【隔离意图:{operation}】"
                )
                answer_body, receipt, history = _answer(
                    acceptance,
                    waiting,
                    f"e2e-{name}-answer-{index + 1}",
                    message,
                )
                accepted.append((answer_body, receipt))
                answers.append(history)
                if operation is None and index == 0:
                    waiting = _wait(acceptance, run_id, clarification=True)
        business_steps = 0
        business_facts: dict[str, object] = {}
        if operation in {"plan_chapter", "write_chapter"}:
            before = acceptance.request(
                "GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200
            ).json()
            other_layers = _other_layers(acceptance) if operation == "write_chapter" else None
            waiting = _wait(acceptance, run_id, clarification=False)
            if waiting.get("operation") != operation:
                raise AssertionError("自然选择没有投影成预期业务操作")
            detail = (
                plan_artifact(acceptance, waiting)
                if operation == "plan_chapter"
                else writing_artifact(acceptance, waiting)
            )
            before_decision = acceptance.request(
                "GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200
            ).json()
            if before_decision["content"] != before["content"]:
                raise AssertionError("自然业务候选在作者确认前改变了正式正文")
            decision_body: dict[str, object] = {
                "engineVersion": 2,
                "clientRequestId": f"e2e-{name}-approve",
                "expectedRevision": detail["revision"],
                "decision": "approve",
            }
            decision_path = f"/api/v1/review-artifacts/{detail['id']}/decision"
            decided = acceptance.request(
                "POST", decision_path, expected=202, json_body=decision_body
            ).json()
            if decided.get("runId") != run_id or decided.get("status") != "completed":
                raise AssertionError("作者批准没有完成原自然 Run")
            if (
                acceptance.request(
                    "POST", decision_path, expected=202, json_body=decision_body
                ).json()
                != decided
            ):
                raise AssertionError("自然业务作者决定没有幂等返回原回执")
            final_chapter = acceptance.request(
                "GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200
            ).json()
            if operation == "write_chapter":
                payload = cast(dict[str, object], detail["payload"])
                if (
                    final_chapter["content"] != payload["content"]
                    or _other_layers(acceptance) != other_layers
                ):
                    raise AssertionError("自然写章未完整应用正文或混写其他数据层")
                business_steps = 3
            else:
                if final_chapter["content"] != before["content"]:
                    raise AssertionError("自然规划错误修改了正式正文")
                business_steps = 2
            adopted = (
                plan_facts(acceptance, run_id)
                if operation == "plan_chapter"
                else writing_facts(acceptance, run_id)
            )
            expected_adoption: dict[str, object] = {
                "artifactCount": 1,
                "artifactStatus": "applied",
                "revisionCount": 1,
                "evaluationCount": business_steps - 1,
                "reviewVerdicts": ["pass"] * (business_steps - 1),
                "modelStepCount": business_steps,
                "matchedBillingCount": business_steps,
            }
            if operation == "plan_chapter":
                expected_adoption.update(
                    approvedPlanCount=1, totalPlanCount=1, supersededPlanCount=0, sceneBeatCount=2
                )
            else:
                expected_adoption.update(
                    chapterStatus="drafting",
                    chapterCompletedAt=None,
                    qualityCheckCount=1,
                    qualityStatus="pending",
                    qualityResult=None,
                    qualityGate=None,
                    qualityScoreOverall=None,
                )
            if any(
                key not in adopted or adopted[key] != value
                for key, value in expected_adoption.items()
            ):
                raise AssertionError("自然业务没有完成正式持久应用与所需复审")
            business_facts = {
                "artifactId": detail["id"],
                "artifactKind": detail["kind"],
                "sourceBindingStatus": detail["sourceBindingStatus"],
                "chapterSha256": _sha(final_chapter["content"]),
            }
        elif operation == "answer_question":
            business_steps = 1
        snapshot = acceptance.wait_terminal(run_id, timeout=120)
        facts = _facts(acceptance, run_id, snapshot, instruction, answers)
        assert_natural_facts(
            facts, operation=operation, answers=len(answers), business_steps=business_steps
        )
        for answer_body, receipt in accepted:
            if (
                acceptance.request(
                    "POST",
                    f"/api/v1/writing/runs/{run_id}/clarification",
                    expected=202,
                    json_body=answer_body,
                ).json()
                != receipt
            ):
                raise AssertionError("终态后澄清重放没有返回最初受理回执")
        if (
            acceptance.start_run(body).json() != snapshot
            or _facts(acceptance, run_id, snapshot, instruction, answers) != facts
        ):
            raise AssertionError("自然启动或澄清重放改变了权威终态、内容或计费")
        providers = [
            p for p in acceptance.provider_facts() if p["idempotency_key"] not in provider_before
        ]
        assert_provider_steps(providers, len(answers) + 1 + business_steps)
        model_diagnostics = cast(list[dict[str, object]], facts["modelStepDiagnostics"])
        if {p["idempotency_key"] for p in providers} != {
            f"{run_id}.{step['id']}" for step in model_diagnostics
        }:
            raise AssertionError("Provider 调用身份未逐个绑定 Core 的模型 Step")
        yield Scenario(
            name=name,
            run_id=run_id,
            session_id=session_id,
            client_request_id=request_id,
            provider_identity={"steps": providers},
            database_facts={**facts, **business_facts, "serviceRestart": runtime},
        )
        if name == "natural_answer_same_run":
            following = _next_message(acceptance, body, snapshot, facts, providers)
            if following.run_id in run_ids:
                raise AssertionError("同会话下一条普通消息复用了已记录的 Run 身份")
            run_ids.add(following.run_id)
            yield following
