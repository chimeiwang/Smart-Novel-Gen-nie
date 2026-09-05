"""整章审阅、场景改写和大纲选区改写的隔离跨进程验收。"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from inkforge_agents.providers.fake import (
    FAKE_CHAPTER_REVIEW_REPORT,
    FAKE_OUTLINE_SELECTION_REPLACEMENT,
)
from inkforge_contracts import ChapterDraftResult, OutlineSelectionResult

from .chapter_writing import _facts as writing_facts
from .chapter_writing import _other_layers
from .natural_entry import (
    _facts as natural_facts,
)
from .natural_entry import (
    assert_natural_facts,
    assert_provider_steps,
    natural_body,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .run_e2e import Acceptance, Scenario

ResourceType = Literal["outline_content", "outline_node_content"]


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _canonical_sha(value: object) -> str:
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


@dataclass(frozen=True, slots=True)
class OutlineSource:
    resource_type: ResourceType
    resource_id: str
    content: str
    updated_at: str
    selection_start: int
    selection_end: int

    def __post_init__(self) -> None:
        if (
            not self.resource_id
            or self.selection_start < 0
            or self.selection_end <= self.selection_start
            or self.selection_end > len(self.content)
        ):
            raise ValueError("大纲 E2E 来源身份或码点范围无效")

    @property
    def selected_text(self) -> str:
        return self.content[self.selection_start : self.selection_end]

    @property
    def prefix(self) -> str:
        return self.content[: self.selection_start]

    @property
    def suffix(self) -> str:
        return self.content[self.selection_end :]

    @property
    def content_sha256(self) -> str:
        return _sha(self.content)

    @property
    def selected_text_sha256(self) -> str:
        return _sha(self.selected_text)

    @property
    def mode(self) -> str:
        return (
            "outline_content_selection"
            if self.resource_type == "outline_content"
            else "outline_node_content_selection"
        )


def _selection_body(
    acceptance: Acceptance,
    source: OutlineSource,
    *,
    session_id: str,
    client_request_id: str,
    instruction: str,
) -> dict[str, object]:
    scope: dict[str, object] = (
        {"kind": "novel"}
        if source.resource_type == "outline_content"
        else {"kind": "outline_node", "outlineNodeId": source.resource_id}
    )
    return {
        "clientRequestId": client_request_id,
        "workflow": "long_serial",
        "novelId": acceptance.novel_id,
        "chapterId": acceptance.chapter_id,
        "writingSessionId": session_id,
        "operation": "rewrite_outline_selection",
        "target": {"type": "chapter", "id": acceptance.chapter_id},
        "scope": scope,
        "selectionTarget": {
            "resourceType": source.resource_type,
            "resourceId": source.resource_id,
            "baseUpdatedAt": source.updated_at,
            "baseContentHash": source.content_sha256,
            "selectionStart": source.selection_start,
            "selectionEnd": source.selection_end,
            "selectedTextHash": source.selected_text_sha256,
        },
        "targetWordCount": 1000,
        "userInstruction": instruction,
    }


def assert_durable_facts(
    facts: dict[str, object],
    *,
    database_operation: str | None,
    model_steps: int,
    artifact_kind: str | None,
    artifact_status: str | None,
    revisions: int,
    verdicts: list[str],
    message_roles: list[str],
) -> None:
    expected: dict[str, object] = {
        "engineVersion": 2,
        "databaseOperation": database_operation,
        "status": "completed",
        "legacyTaskCount": 0,
        "legacyCommandCount": 0,
        "artifactCount": int(artifact_kind is not None),
        "artifactKind": artifact_kind,
        "artifactStatus": artifact_status,
        "revisionCount": revisions,
        "evaluationCount": len(verdicts),
        "reviewVerdicts": verdicts,
        "modelStepCount": model_steps,
        "badModelStepCount": 0,
        "matchedBillingCount": model_steps,
        "reservationCount": model_steps,
        "tokenUsageCount": model_steps,
        "creditLedgerCount": 0,
        "balanceDeltaMicros": 0,
        "completedEventCount": 1,
        "messageRoles": message_roles,
    }
    mismatch = [key for key, value in expected.items() if key not in facts or facts[key] != value]
    if mismatch:
        raise AssertionError("审阅/改写持久证据不符合预期：" + ",".join(mismatch))


def _durable_facts(acceptance: Acceptance, run_id: str) -> dict[str, object]:
    raw = json.loads(
        acceptance.stack.psql(
            """
        SELECT json_build_object(
          'engineVersion',r."engineVersion",'databaseOperation',r.operation,
          'status',r.status::text,
          'legacyTaskCount',(SELECT count(*) FROM public."WritingTask"
            WHERE "novelId"=r."novelId"),
          'legacyCommandCount',(SELECT count(*) FROM public."WritingRunCommand" c
            JOIN public."WritingTask" t ON t.id=c."taskId" WHERE t."novelId"=r."novelId"),
          'artifactCount',(SELECT count(*) FROM public."ReviewArtifact"
            WHERE "workflowRunId"=r.id),
          'artifactKind',(SELECT kind::text FROM public."ReviewArtifact"
            WHERE "workflowRunId"=r.id ORDER BY id LIMIT 1),
          'artifactStatus',(SELECT status::text FROM public."ReviewArtifact"
            WHERE "workflowRunId"=r.id ORDER BY id LIMIT 1),
          'revisionCount',(SELECT count(*) FROM public."ReviewArtifactRevision" v
            JOIN public."ReviewArtifact" a ON a.id=v."artifactId"
            WHERE a."workflowRunId"=r.id),
          'evaluationCount',(SELECT count(*) FROM public."WorkflowEvaluation"
            WHERE "runId"=r.id),
          'reviewVerdicts',(SELECT coalesce(json_agg(e."contentVerdict" ORDER BY s.ordinal),
              '[]'::json) FROM public."WorkflowEvaluation" e
            JOIN public."WorkflowStep" s ON s.id=e."stepId" WHERE e."runId"=r.id),
          'modelSteps',(SELECT coalesce(json_agg(json_build_object(
              'id',s.id,'purpose',s.purpose,'status',s.status::text,
              'attemptCount',s."attemptCount",'fencingToken',s."fencingToken",
              'inputHash',s."inputHash",'resultHash',s."resultHash",
              'modelProfile',s."modelProfile",'artifactId',s."artifactId",
              'artifactRevision',s."artifactRevision",'usage',s."usageJson"::jsonb)
              ORDER BY s.ordinal), '[]'::json)
            FROM public."WorkflowStep" s WHERE s."runId"=r.id
              AND s.purpose IN ('resolve_intent','generation','review')),
          'matchedBillingCount',(SELECT count(*) FROM public."WorkflowStep" s
            JOIN public."WorkflowBillingReservation" b ON b."stepId"=s.id AND b."runId"=r.id
            JOIN public."TokenUsage" u ON u."requestId"=b."requestId"
              AND u."taskId"=s.id AND u."runId"=r.id
            WHERE s."runId"=r.id AND s.purpose IN ('resolve_intent','generation','review')
              AND b."userId"=r."userId" AND u."userId"=r."userId" AND u.model='fake'
              AND b.status='settled' AND b."reservedMicros"=0 AND b."chargedMicros"=0
              AND b."settledAt" IS NOT NULL AND b."usageJson"::jsonb=s."usageJson"::jsonb
              AND u."promptTokens"=(s."usageJson"::jsonb->>'inputTokens')::int
              AND u."cachedTokens"=(s."usageJson"::jsonb->>'cachedTokens')::int
              AND u."promptCacheMissTokens" IS NOT DISTINCT FROM
                (s."usageJson"::jsonb->>'promptCacheMissTokens')::int
              AND u."completionTokens"=(s."usageJson"::jsonb->>'completionTokens')::int
              AND u."reasoningTokens" IS NOT DISTINCT FROM
                (s."usageJson"::jsonb->>'reasoningTokens')::int
              AND u."totalTokens"=u."promptTokens"+u."completionTokens"),
          'reservationCount',(SELECT count(*) FROM public."WorkflowBillingReservation"
            WHERE "runId"=r.id),
          'tokenUsageCount',(SELECT count(*) FROM public."TokenUsage" WHERE "runId"=r.id),
          'creditLedgerCount',(SELECT count(*) FROM public."CreditLedger" WHERE "requestId" IN
            (SELECT "requestId" FROM public."WorkflowBillingReservation" WHERE "runId"=r.id)),
          'userBalanceMicros',(SELECT "creditBalanceMicros" FROM public."User"
            WHERE id=r."userId"),
          'completedEventCount',(SELECT count(*) FROM public."WorkflowEvent"
            WHERE "runId"=r.id AND "eventType"='completed'),
          'completedPayload',(SELECT "payloadJson"::jsonb FROM public."WorkflowEvent"
            WHERE "runId"=r.id AND "eventType"='completed' ORDER BY sequence LIMIT 1),
          'generationStepId',(SELECT id FROM public."WorkflowStep"
            WHERE "runId"=r.id AND purpose='generation' ORDER BY ordinal LIMIT 1),
          'generationOutput',(SELECT output::jsonb FROM public."WorkflowStep"
            WHERE "runId"=r.id AND purpose='generation' ORDER BY ordinal LIMIT 1),
          'messages',(SELECT coalesce(json_agg(json_build_object('id',m.id,'role',m.role,
              'content',m.content,'metadata',m.metadata::jsonb) ORDER BY m."createdAt",m.id),
              '[]'::json) FROM public."WritingMessage" m
            WHERE m."sessionId"=r."writingSessionId")
        )::text FROM public."WorkflowRun" r WHERE r.id=:'e2e_run_id';
        """,
            variables={"e2e_run_id": run_id},
        )
    )
    model_steps = raw.pop("modelSteps")
    messages = raw.pop("messages")
    generation_output = raw.pop("generationOutput")
    if not isinstance(model_steps, list) or not isinstance(messages, list):
        raise AssertionError("审阅/改写缺少模型 Step 或会话消息事实")
    raw["modelStepCount"] = len(model_steps)
    raw["badModelStepCount"] = sum(
        not isinstance(step, dict)
        or step.get("status") != "completed"
        or step.get("attemptCount") != 1
        or step.get("fencingToken") != 1
        or not isinstance(step.get("inputHash"), str)
        or not isinstance(step.get("resultHash"), str)
        or not isinstance(step.get("modelProfile"), str)
        or not isinstance(step.get("usage"), dict)
        or cast(dict[str, object], step.get("usage")).get("providerAttempts") != 1
        for step in model_steps
    )
    raw["modelStepDiagnostics"] = [
        {
            key: step.get(key)
            for key in (
                "id",
                "purpose",
                "status",
                "modelProfile",
                "artifactId",
                "artifactRevision",
            )
        }
        for step in model_steps
        if isinstance(step, dict)
    ]
    raw["messageRoles"] = [message.get("role") for message in messages if isinstance(message, dict)]
    raw["messageIds"] = [message.get("id") for message in messages if isinstance(message, dict)]
    raw["messageContentSha256"] = [
        _sha(str(message.get("content"))) for message in messages if isinstance(message, dict)
    ]
    raw["messageSources"] = [
        metadata.get("source")
        for message in messages
        if isinstance(message, dict) and isinstance((metadata := message.get("metadata")), dict)
    ]
    raw["generationOutputSha256"] = (
        _canonical_sha(generation_output) if isinstance(generation_output, dict) else None
    )
    report = generation_output.get("report") if isinstance(generation_output, dict) else None
    raw["generationReportSha256"] = _sha(report) if isinstance(report, str) else None
    balance = raw.pop("userBalanceMicros", None)
    initial = acceptance.initial_credit_balance_micros
    raw["balanceDeltaMicros"] = (
        balance - initial if type(balance) is int and type(initial) is int else None
    )
    acceptance.safe_diagnostics["reviewRewrites"] = {"runId": run_id, **raw}
    return cast(dict[str, object], raw)


def _wait_artifact(
    acceptance: Acceptance, run_id: str, operation: str, *, timeout: float = 120
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        value = acceptance.request("GET", f"/api/v1/writing/runs/{run_id}", expected=200).json()
        if not isinstance(value, dict):
            raise AssertionError("改写 Run 快照不是对象")
        last = value
        projected_operation = value.get("operation")
        if value.get("engineVersion") != 2 or projected_operation not in {
            None,
            operation,
        }:
            raise AssertionError("改写 Run 没有保持 V2 与真实操作")
        if value.get("status") == "waiting_user":
            if projected_operation != operation or not isinstance(
                value.get("artifact"), dict
            ):
                raise AssertionError("改写 Run 等待作者时缺少 Artifact")
            return cast(dict[str, object], value)
        if value.get("status") in {"completed", "failed", "cancelled"}:
            _durable_facts(acceptance, run_id)
            raise AssertionError("改写 Run 未产生候选便结束")
        time.sleep(0.2)
    _durable_facts(acceptance, run_id)
    raise AssertionError(f"改写 Run 未进入等待作者：{last.get('status')}")


def _chapter_artifact(acceptance: Acceptance, snapshot: dict[str, object]) -> dict[str, object]:
    candidate = snapshot.get("artifact")
    if not isinstance(candidate, dict) or not isinstance(candidate.get("artifactId"), str):
        raise AssertionError("场景改写缺少草案身份")
    revision = candidate.get("artifactRevision")
    if type(revision) is not int or revision < 1:
        raise AssertionError("场景改写缺少精确草案 revision")
    detail = acceptance.request(
        "GET",
        f"/api/v1/review-artifacts/{candidate['artifactId']}?revision={revision}",
        expected=200,
    ).json()
    if (
        detail.get("engineVersion") != 2
        or detail.get("kind") != "chapter_draft"
        or detail.get("taskId") is not None
        or detail.get("workflowRunId") != snapshot.get("runId")
        or detail.get("revision") != revision
        or detail.get("sourceBindingStatus") != "verified"
    ):
        raise AssertionError("场景改写详情没有绑定精确 V2 草案来源")
    payload = detail.get("payload")
    if not isinstance(payload, dict) or payload.get("operation") != "rewrite_scene":
        raise AssertionError("场景改写详情丢失真实 operation")
    if payload.get("target") != {
        "mode": "existing_chapter",
        "chapterId": acceptance.chapter_id,
    }:
        raise AssertionError("场景改写详情目标不是完整当前章节")
    ChapterDraftResult.model_validate(
        {key: payload.get(key) for key in ("summary", "content", "contentSha256", "wordCount")}
    )
    diff = detail.get("diff")
    if (
        not isinstance(diff, dict)
        or diff.get("type") != "chapter_content"
        or diff.get("after") != payload.get("content")
    ):
        raise AssertionError("场景改写详情没有完整章节 before/after")
    return cast(dict[str, object], detail)


def _outline_artifact(
    acceptance: Acceptance,
    snapshot: dict[str, object],
    source: OutlineSource,
) -> dict[str, object]:
    candidate = snapshot.get("artifact")
    if not isinstance(candidate, dict) or not isinstance(candidate.get("artifactId"), str):
        raise AssertionError("大纲选区改写缺少候选身份")
    revision = candidate.get("artifactRevision")
    if type(revision) is not int or revision < 1:
        raise AssertionError("大纲选区改写缺少精确候选 revision")
    detail = acceptance.request(
        "GET",
        f"/api/v1/review-artifacts/{candidate['artifactId']}?revision={revision}",
        expected=200,
    ).json()
    if (
        detail.get("engineVersion") != 2
        or detail.get("id") != candidate["artifactId"]
        or detail.get("kind") != "outline_draft"
        or detail.get("taskId") is not None
        or detail.get("workflowRunId") != snapshot.get("runId")
        or detail.get("revision") != revision
        or detail.get("sourceBindingStatus") != "verified"
    ):
        raise AssertionError("大纲选区详情没有绑定精确 V2 来源")
    payload = detail.get("payload")
    diff = detail.get("diff")
    if not isinstance(payload, dict) or not isinstance(diff, dict):
        raise AssertionError("大纲选区详情缺少完整 payload/diff")
    if (
        payload.get("candidatePrefix") != source.prefix
        or payload.get("candidateSuffix") != source.suffix
    ):
        raise AssertionError("大纲选区候选修改了选区外文本")
    replacement = payload.get("replacement")
    candidate_text = (
        source.prefix + replacement + source.suffix if isinstance(replacement, str) else None
    )
    expected_target = {
        "mode": source.mode,
        "resourceType": source.resource_type,
        "resourceId": source.resource_id,
        "baseUpdatedAt": source.updated_at,
        "baseContentHash": source.content_sha256,
        "selectionStart": source.selection_start,
        "selectionEnd": source.selection_end,
        "selectedTextHash": source.selected_text_sha256,
    }
    expected_selection = {
        "start": source.selection_start,
        "end": source.selection_end,
        "selectedText": source.selected_text,
        "selectedTextHash": source.selected_text_sha256,
    }
    output = {
        "replacement": replacement,
        "contentSha256": payload.get("contentSha256"),
    }
    try:
        OutlineSelectionResult.model_validate(output)
    except ValueError:
        raise AssertionError("大纲选区详情的替换文本或派生哈希无效") from None
    valid = (
        payload.get("kind") == "outline_draft"
        and payload.get("operation") == "rewrite_outline_selection"
        and payload.get("target") == expected_target
        and payload.get("resourceType") == source.resource_type
        and payload.get("resourceId") == source.resource_id
        and payload.get("baseUpdatedAt") == source.updated_at
        and payload.get("baseContentHash") == source.content_sha256
        and payload.get("selectionStart") == source.selection_start
        and payload.get("selectionEnd") == source.selection_end
        and payload.get("selectedTextHash") == source.selected_text_sha256
        and payload.get("selectedText") == source.selected_text
        and payload.get("selection") == expected_selection
        and payload.get("contentSha256") == _sha(cast(str, replacement))
        and payload.get("candidate") == candidate_text
        and diff.get("type") == "selection"
        and diff.get("mode") == source.mode
        and diff.get("resourceType") == source.resource_type
        and diff.get("resourceId") == source.resource_id
        and diff.get("selectionStart") == source.selection_start
        and diff.get("selectionEnd") == source.selection_end
        and diff.get("selectedText") == source.selected_text
        and diff.get("replacement") == replacement
        and diff.get("before") == source.content
        and diff.get("after") == candidate_text
        and diff.get("candidate") == candidate_text
        and diff.get("prefix") == source.prefix
        and diff.get("suffix") == source.suffix
    )
    if not valid:
        raise AssertionError("大纲选区详情没有重建完整 Unicode 来源与候选")
    return cast(dict[str, object], detail)


def _decide(
    acceptance: Acceptance,
    detail: dict[str, object],
    *,
    decision: Literal["approve", "discard", "revise"],
    client_request_id: str,
    edited_content: str | None = None,
    edited_replacement: str | None = None,
    user_message: str | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "engineVersion": 2,
        "clientRequestId": client_request_id,
        "expectedRevision": detail["revision"],
        "decision": decision,
    }
    if edited_content is not None:
        body["editedContent"] = edited_content
    if edited_replacement is not None:
        body["editedReplacement"] = edited_replacement
    if user_message is not None:
        body["userMessage"] = user_message
    return cast(
        dict[str, object],
        acceptance.request(
            "POST",
            f"/api/v1/review-artifacts/{detail['id']}/decision",
            expected=202,
            json_body=body,
        ).json(),
    )


def _assert_decision_snapshot_matches_get(
    receipt: dict[str, object], terminal: dict[str, object], run_id: str
) -> None:
    if (
        receipt.get("engineVersion") != 2
        or receipt.get("runId") != run_id
        or receipt.get("status") != "completed"
        or ("taskId" in receipt and receipt["taskId"] is not None)
        or terminal.get("engineVersion") != 2
        or terminal.get("runId") != run_id
        or terminal.get("taskId") != run_id
        or terminal.get("status") != "completed"
    ):
        raise AssertionError("改写决定回执或权威终态兼容身份无效")
    normalized_receipt = dict(receipt)
    normalized_terminal = dict(terminal)
    normalized_receipt.pop("taskId", None)
    normalized_terminal.pop("taskId", None)
    if normalized_receipt != normalized_terminal:
        raise AssertionError("改写决定回执与 GET 权威快照除兼容 taskId 外不一致")


def _assert_provider_bindings(
    acceptance: Acceptance,
    run_id: str,
    before: set[str],
    facts: dict[str, object],
    expected: int,
) -> list[dict[str, object]]:
    providers = [
        item for item in acceptance.provider_facts() if item["idempotency_key"] not in before
    ]
    assert_provider_steps(providers, expected)
    diagnostics = facts.get("modelStepDiagnostics")
    if not isinstance(diagnostics, list):
        raise AssertionError("缺少模型 Step 诊断身份")
    expected_keys = {
        f"{run_id}.{step['id']}"
        for step in diagnostics
        if isinstance(step, dict) and isinstance(step.get("id"), str)
    }
    if {provider["idempotency_key"] for provider in providers} != expected_keys:
        raise AssertionError("Provider 幂等身份没有逐 Step 绑定当前 Run")
    return providers


def _resource_content(acceptance: Acceptance, source: OutlineSource) -> str:
    if source.resource_type == "outline_content":
        value = acceptance.stack.psql(
            "SELECT to_json(content)::text FROM public.\"Outline\" "
            "WHERE id=:'e2e_resource_id';",
            variables={"e2e_resource_id": source.resource_id},
        )
    else:
        value = acceptance.stack.psql(
            "SELECT to_json(content)::text FROM public.\"OutlineNode\" "
            "WHERE id=:'e2e_resource_id';",
            variables={"e2e_resource_id": source.resource_id},
        )
    content = json.loads(value)
    if not isinstance(content, str):
        raise AssertionError("大纲 E2E 来源正文缺失")
    return content


def _protected_layers_hash(acceptance: Acceptance, source: OutlineSource) -> str:
    value = acceptance.stack.psql(
        """
      SELECT jsonb_build_object(
        'novel',to_jsonb(n),
        'chapters',(SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id)
          FROM public."Chapter" c WHERE c."novelId"=n.id),
        'worldSetting',(SELECT jsonb_agg(to_jsonb(w) ORDER BY w.id)
          FROM public."WorldSetting" w WHERE w."novelId"=n.id),
        'storyBackground',(SELECT jsonb_agg(to_jsonb(b) ORDER BY b.id)
          FROM public."StoryBackground" b WHERE b."novelId"=n.id),
        'writingBible',(SELECT jsonb_agg(to_jsonb(b) ORDER BY b.id)
          FROM public."WritingBible" b WHERE b."novelId"=n.id),
        'outline',(SELECT jsonb_agg(CASE
            WHEN :'e2e_resource_type'='outline_content' AND o.id=:'e2e_resource_id'
              THEN to_jsonb(o)-'content'-'updatedAt' ELSE to_jsonb(o) END ORDER BY o.id)
          FROM public."Outline" o WHERE o."novelId"=n.id),
        'outlineNodes',(SELECT jsonb_agg(CASE
            WHEN :'e2e_resource_type'='outline_node_content' AND o.id=:'e2e_resource_id'
              THEN to_jsonb(o)-'content'-'updatedAt' ELSE to_jsonb(o) END ORDER BY o.id)
          FROM public."OutlineNode" o WHERE o."novelId"=n.id),
        'progress',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.id)
          FROM public."ChapterProgress" p JOIN public."Chapter" c ON c.id=p."chapterId"
          WHERE c."novelId"=n.id),
        'plot',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.id)
          FROM public."PlotProgress" p WHERE p."novelId"=n.id),
        'plans',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.id)
          FROM public."ChapterBeatPlan" p JOIN public."Chapter" c ON c.id=p."chapterId"
          WHERE c."novelId"=n.id),
        'beats',(SELECT jsonb_agg(to_jsonb(s) ORDER BY s.id)
          FROM public."SceneBeat" s JOIN public."ChapterBeatPlan" p ON p.id=s."beatPlanId"
          JOIN public."Chapter" c ON c.id=p."chapterId" WHERE c."novelId"=n.id),
        'characters',(SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id)
          FROM public."Character" c WHERE c."novelId"=n.id),
        'factions',(SELECT jsonb_agg(to_jsonb(f) ORDER BY f.id)
          FROM public."Faction" f WHERE f."novelId"=n.id),
        'locations',(SELECT jsonb_agg(to_jsonb(l) ORDER BY l.id)
          FROM public."Location" l WHERE l."novelId"=n.id),
        'items',(SELECT jsonb_agg(to_jsonb(i) ORDER BY i.id)
          FROM public."Item" i WHERE i."novelId"=n.id),
        'glossary',(SELECT jsonb_agg(to_jsonb(g) ORDER BY g.id)
          FROM public."Glossary" g WHERE g."novelId"=n.id),
        'foreshadowing',(SELECT jsonb_agg(to_jsonb(f) ORDER BY f.id)
          FROM public."Foreshadowing" f WHERE f."novelId"=n.id)
      )::text FROM public."Novel" n WHERE n.id=:'e2e_novel_id';
    """,
        variables={
            "e2e_novel_id": acceptance.novel_id,
            "e2e_resource_type": source.resource_type,
            "e2e_resource_id": source.resource_id,
        },
    )
    return _canonical_sha(json.loads(value))


def _prepare_outline_source(
    acceptance: Acceptance,
    *,
    resource_type: ResourceType,
    label: str,
    content: str,
    updated_at: str,
    selection_start: int,
    selection_end: int,
) -> OutlineSource:
    database_timestamp = updated_at.removesuffix("Z").replace("T", " ")
    if resource_type == "outline_content":
        resource_id = acceptance.stack.psql(
            """
          INSERT INTO public."Outline" (id,"novelId",content,"createdAt","updatedAt")
          VALUES (:'e2e_resource_id',:'e2e_novel_id',:'e2e_content',CURRENT_TIMESTAMP,
            :'e2e_updated_at'::timestamp)
          ON CONFLICT ("novelId") DO UPDATE SET content=excluded.content,
            "updatedAt"=excluded."updatedAt"
          RETURNING id;
        """,
            variables={
                "e2e_resource_id": f"e2e-{label}-outline",
                "e2e_novel_id": acceptance.novel_id,
                "e2e_content": content,
                "e2e_updated_at": database_timestamp,
            },
        )
    else:
        resource_id = f"e2e-{label}-node"
        acceptance.stack.psql(
            """
          INSERT INTO public."OutlineNode" (
            id,"novelId",kind,title,"order",content,"createdAt","updatedAt"
          ) VALUES (:'e2e_resource_id',:'e2e_novel_id','plot_unit','隔离节点',1,
            :'e2e_content',CURRENT_TIMESTAMP,:'e2e_updated_at'::timestamp)
          ON CONFLICT (id) DO UPDATE SET content=excluded.content,
            "updatedAt"=excluded."updatedAt";
        """,
            variables={
                "e2e_resource_id": resource_id,
                "e2e_novel_id": acceptance.novel_id,
                "e2e_content": content,
                "e2e_updated_at": database_timestamp,
            },
        )
    return OutlineSource(
        resource_type=resource_type,
        resource_id=resource_id,
        content=content,
        updated_at=updated_at,
        selection_start=selection_start,
        selection_end=selection_end,
    )


def _outline_generation_inputs(acceptance: Acceptance, run_id: str) -> list[dict[str, object]]:
    value = json.loads(
        acceptance.stack.psql(
            """
          SELECT coalesce(json_agg(input::jsonb ORDER BY ordinal),'[]'::json)::text
          FROM public."WorkflowStep" WHERE "runId"=:'e2e_run_id' AND purpose='generation';
        """,
            variables={"e2e_run_id": run_id},
        )
    )
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise AssertionError("大纲选区缺少严格 generation 输入")
    return cast(list[dict[str, object]], value)


def _session_review_message(
    acceptance: Acceptance, session_id: str, run_id: str, report: str
) -> str:
    detail = acceptance.request(
        "GET", f"/api/v1/writing/sessions/{session_id}", expected=200
    ).json()
    messages = detail.get("messages") if isinstance(detail, dict) else None
    if not isinstance(messages, list) or len(messages) != 2:
        raise AssertionError("整章审阅会话不是唯一一问一报告")
    user, agent = messages
    if (
        not isinstance(user, dict)
        or not isinstance(agent, dict)
        or user.get("role") != "user"
        or agent.get("role") != "agent"
        or agent.get("agentId") != "编辑"
        or agent.get("content") != report
    ):
        raise AssertionError("整章审阅会话消息角色或完整报告无效")
    metadata = agent.get("metadata")
    source = metadata.get("source") if isinstance(metadata, dict) else None
    if (
        not isinstance(source, dict)
        or source.get("engineVersion") != 2
        or source.get("runId") != run_id
        or source.get("operation") != "review_chapter"
        or source.get("outcomeType") != "chapter_review_report"
    ):
        raise AssertionError("整章审阅报告消息没有绑定 V2 Run 来源")
    message_id = agent.get("id")
    if not isinstance(message_id, str):
        raise AssertionError("整章审阅报告消息缺少身份")
    return message_id


def _review_scenarios(acceptance: Acceptance) -> Iterator[Scenario]:
    from .run_e2e import Scenario

    for name, with_session, restart in (
        ("review_chapter_without_session", False, False),
        ("review_chapter_session_core_restart", True, True),
    ):
        session_id = acceptance.create_session(name) if with_session else ""
        request_id = f"e2e-{name}-start"
        body = acceptance.run_body(
            session_id=session_id,
            client_request_id=request_id,
            instruction="完整审阅当前章节，只返回报告，不修改正式资料。",
            operation="review_chapter",
        )
        if not with_session:
            body.pop("writingSessionId")
        chapter_before = acceptance.request(
            "GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200
        ).json()
        other_before = _other_layers(acceptance)
        providers_before = acceptance.provider_keys()
        started = acceptance.start_run(body).json()
        run_id = str(started["runId"])
        terminal = acceptance.wait_terminal(run_id, timeout=120)
        if (
            terminal.get("engineVersion") != 2
            or terminal.get("operation") != "review_chapter"
            or terminal.get("status") != "completed"
            or terminal.get("reviewReport") != FAKE_CHAPTER_REVIEW_REPORT
            or terminal.get("artifact") is not None
        ):
            raise AssertionError("整章审阅没有返回完整只读 V2 报告")
        runtime: dict[str, object] | None = None
        if restart:
            runtime = acceptance.stack.restart_and_wait("core-api")
            restored = acceptance.request(
                "GET", f"/api/v1/writing/runs/{run_id}", expected=200
            ).json()
            if restored != terminal:
                raise AssertionError("Core 重启后整章审阅报告或 Run 快照漂移")
        facts = _durable_facts(acceptance, run_id)
        roles = ["user", "agent"] if with_session else []
        assert_durable_facts(
            facts,
            database_operation="review_chapter",
            model_steps=1,
            artifact_kind=None,
            artifact_status=None,
            revisions=0,
            verdicts=[],
            message_roles=roles,
        )
        if facts.get("generationReportSha256") != _sha(FAKE_CHAPTER_REVIEW_REPORT):
            raise AssertionError("Step.output 没有持久化完整审阅报告")
        completed = facts.get("completedPayload")
        if (
            not isinstance(completed, dict)
            or completed.get("outcomeType") != "chapter_review_report"
        ):
            raise AssertionError("整章审阅 completed 事件 outcome 无效")
        if with_session:
            message_id = _session_review_message(
                acceptance, session_id, run_id, FAKE_CHAPTER_REVIEW_REPORT
            )
            if completed.get("resultId") != message_id:
                raise AssertionError("审阅 completed.resultId 未绑定唯一报告消息")
        elif completed.get("resultId") != facts.get("generationStepId"):
            raise AssertionError("无会话审阅 resultId 未绑定唯一 generation Step")
        chapter_after = acceptance.request(
            "GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200
        ).json()
        if chapter_after != chapter_before or _other_layers(acceptance) != other_before:
            raise AssertionError("只读整章审阅修改了正式创作数据")
        if acceptance.start_run(body).json() != terminal:
            raise AssertionError("整章审阅启动幂等重放没有返回原终态")
        if _durable_facts(acceptance, run_id) != facts:
            raise AssertionError("整章审阅重放新增了消息、Step、事件或计费")
        providers = _assert_provider_bindings(acceptance, run_id, providers_before, facts, 1)
        yield Scenario(
            name=name,
            run_id=run_id,
            session_id=session_id,
            client_request_id=request_id,
            provider_identity={"steps": providers},
            database_facts={**facts, "serviceRestart": runtime},
        )


def _natural_review_scenario(acceptance: Acceptance) -> Scenario:
    from .run_e2e import Scenario

    name = "natural_review_chapter"
    session_id = acceptance.create_session(name)
    request_id = f"e2e-{name}-start"
    instruction = "【隔离意图:review_chapter】"
    body = natural_body(
        acceptance.novel_id,
        acceptance.chapter_id,
        session_id,
        request_id,
        instruction,
    )
    chapter_before = acceptance.request(
        "GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200
    ).json()
    other_before = _other_layers(acceptance)
    providers_before = acceptance.provider_keys()
    started = acceptance.start_run(body).json()
    run_id = str(started["runId"])
    terminal = acceptance.wait_terminal(run_id, timeout=120)
    if (
        terminal.get("operation") != "review_chapter"
        or terminal.get("reviewReport") != FAKE_CHAPTER_REVIEW_REPORT
    ):
        raise AssertionError("自然审阅没有投影完整报告")
    facts = _durable_facts(acceptance, run_id)
    assert_durable_facts(
        facts,
        database_operation=None,
        model_steps=2,
        artifact_kind=None,
        artifact_status=None,
        revisions=0,
        verdicts=[],
        message_roles=["user", "agent"],
    )
    natural = natural_facts(acceptance, run_id, terminal, instruction, [])
    assert_natural_facts(natural, operation="review_chapter", answers=0, business_steps=1)
    message_id = _session_review_message(acceptance, session_id, run_id, FAKE_CHAPTER_REVIEW_REPORT)
    completed = facts.get("completedPayload")
    if not isinstance(completed, dict) or completed.get("resultId") != message_id:
        raise AssertionError("自然审阅终态未绑定唯一报告消息")
    if (
        acceptance.request("GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200).json()
        != chapter_before
        or _other_layers(acceptance) != other_before
    ):
        raise AssertionError("自然审阅修改了正式创作数据")
    if acceptance.start_run(body).json() != terminal:
        raise AssertionError("自然审阅启动重放没有返回原终态")
    if _durable_facts(acceptance, run_id) != facts:
        raise AssertionError("自然审阅重放新增了事实")
    providers = _assert_provider_bindings(acceptance, run_id, providers_before, facts, 2)
    return Scenario(
        name=name,
        run_id=run_id,
        session_id=session_id,
        client_request_id=request_id,
        provider_identity={"steps": providers},
        database_facts={**facts, "natural": natural},
    )


def _set_completed_quality(acceptance: Acceptance) -> None:
    acceptance.stack.psql(
        """
      UPDATE public."ChapterQualityCheck" SET status='completed',result='隔离旧终检',
        "qualityGate"='pass',"scoreOverall"=90
      WHERE "chapterId"=:'chapter_id' AND type::text='consistency';
    """,
        variables={"chapter_id": acceptance.chapter_id},
    )


def _assert_scene_business(
    facts: dict[str, object],
    *,
    database_operation: str | None,
    artifact_status: str,
    revisions: int,
    message_roles: list[str],
    expected_chapter_sha256: str,
    expected_other_layers_sha256: str,
    applied: bool,
) -> None:
    assert_durable_facts(
        facts,
        database_operation=database_operation,
        model_steps=3 + int(database_operation is None),
        artifact_kind="chapter_draft",
        artifact_status=artifact_status,
        revisions=revisions,
        verdicts=["pass", "pass"],
        message_roles=message_roles,
    )
    expected: dict[str, object] = {
        "chapterSha256": expected_chapter_sha256,
        "otherLayersSha256": expected_other_layers_sha256,
    }
    if applied:
        expected.update(
            chapterStatus="drafting",
            chapterCompletedAt=None,
            qualityCheckCount=1,
            qualityStatus="pending",
            qualityResult=None,
            qualityGate=None,
            qualityScoreOverall=None,
        )
    mismatch = [key for key, value in expected.items() if facts.get(key) != value]
    if mismatch:
        raise AssertionError("场景改写正式应用或隔离层证据无效：" + ",".join(mismatch))


def _explicit_scene_scenario(acceptance: Acceptance) -> Scenario:
    from .run_e2e import Scenario

    name = "rewrite_scene_edited_approve"
    _set_completed_quality(acceptance)
    session_id = acceptance.create_session(name)
    request_id = f"e2e-{name}-start"
    body = acceptance.run_body(
        session_id=session_id,
        client_request_id=request_id,
        instruction="依据完整章节来源改写冲突场景，仍返回完整整章。",
        operation="rewrite_scene",
    )
    before = acceptance.request(
        "GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200
    ).json()
    original_hash = _sha(before["content"])
    other_hash = _other_layers(acceptance)
    providers_before = acceptance.provider_keys()
    started = acceptance.start_run(body).json()
    run_id = str(started["runId"])
    detail = _chapter_artifact(acceptance, _wait_artifact(acceptance, run_id, "rewrite_scene"))
    if writing_facts(acceptance, run_id)["chapterSha256"] != original_hash:
        raise AssertionError("场景候选在作者确认前修改了正式正文")
    edited = "  作者完整编辑后的场景正文😀\r\n" * 120 + "尾段保留  \n"
    decision_id = f"e2e-{name}-decision"
    completed = _decide(
        acceptance,
        detail,
        decision="approve",
        client_request_id=decision_id,
        edited_content=edited,
    )
    if completed.get("runId") != run_id or completed.get("status") != "completed":
        raise AssertionError("场景编辑批准没有完成同一 Run")
    facts = writing_facts(acceptance, run_id)
    generic = _durable_facts(acceptance, run_id)
    facts["databaseOperation"] = facts.pop("operation")
    for field in (
        "modelStepCount",
        "badModelStepCount",
        "matchedBillingCount",
        "reservationCount",
        "tokenUsageCount",
        "creditLedgerCount",
        "balanceDeltaMicros",
        "messageRoles",
    ):
        facts[field] = generic[field]
    _assert_scene_business(
        facts,
        database_operation="rewrite_scene",
        artifact_status="applied",
        revisions=2,
        message_roles=["user"],
        expected_chapter_sha256=_sha(edited),
        expected_other_layers_sha256=other_hash,
        applied=True,
    )
    if (
        _decide(
            acceptance,
            detail,
            decision="approve",
            client_request_id=decision_id,
            edited_content=edited,
        )
        != completed
        or acceptance.start_run(body).json().get("runId") != run_id
    ):
        raise AssertionError("场景改写启动或决定没有幂等重放")
    if writing_facts(acceptance, run_id)["chapterSha256"] != _sha(edited):
        raise AssertionError("场景改写幂等重放改变了正式正文")
    providers = _assert_provider_bindings(acceptance, run_id, providers_before, generic, 3)
    return Scenario(
        name=name,
        run_id=run_id,
        session_id=session_id,
        client_request_id=request_id,
        provider_identity={"steps": providers},
        database_facts=facts,
    )


def _natural_scene_scenario(
    acceptance: Acceptance, *, decision: Literal["approve", "discard"]
) -> Scenario:
    from .run_e2e import Scenario

    name = f"natural_rewrite_scene_{decision}"
    _set_completed_quality(acceptance)
    session_id = acceptance.create_session(name)
    request_id = f"e2e-{name}-start"
    instruction = "【隔离意图:rewrite_scene】"
    body = natural_body(
        acceptance.novel_id,
        acceptance.chapter_id,
        session_id,
        request_id,
        instruction,
    )
    before = acceptance.request(
        "GET", f"/api/v1/chapters/{acceptance.chapter_id}", expected=200
    ).json()
    original_hash = _sha(before["content"])
    other_hash = _other_layers(acceptance)
    providers_before = acceptance.provider_keys()
    started = acceptance.start_run(body).json()
    run_id = str(started["runId"])
    detail = _chapter_artifact(acceptance, _wait_artifact(acceptance, run_id, "rewrite_scene"))
    payload = cast(dict[str, object], detail["payload"])
    candidate_content = cast(str, payload["content"])
    decision_id = f"e2e-{name}-decision"
    completed = _decide(
        acceptance,
        detail,
        decision=decision,
        client_request_id=decision_id,
    )
    terminal = acceptance.wait_terminal(run_id, timeout=120)
    _assert_decision_snapshot_matches_get(completed, terminal, run_id)
    if terminal.get("operation") != "rewrite_scene":
        raise AssertionError("自然场景改写 GET 终态丢失真实 operation")
    natural = natural_facts(acceptance, run_id, terminal, instruction, [])
    assert_natural_facts(natural, operation="rewrite_scene", answers=0, business_steps=3)
    facts = writing_facts(acceptance, run_id)
    generic = _durable_facts(acceptance, run_id)
    facts.pop("operation")
    for field in (
        "databaseOperation",
        "modelStepCount",
        "badModelStepCount",
        "matchedBillingCount",
        "reservationCount",
        "tokenUsageCount",
        "creditLedgerCount",
        "balanceDeltaMicros",
        "messageRoles",
    ):
        facts[field] = generic[field]
    _assert_scene_business(
        facts,
        database_operation=None,
        artifact_status="applied" if decision == "approve" else "draft",
        revisions=1,
        message_roles=["user"],
        expected_chapter_sha256=(
            _sha(candidate_content) if decision == "approve" else original_hash
        ),
        expected_other_layers_sha256=other_hash,
        applied=decision == "approve",
    )
    if (
        _decide(
            acceptance,
            detail,
            decision=decision,
            client_request_id=decision_id,
        )
        != completed
        or acceptance.start_run(body).json() != terminal
    ):
        raise AssertionError("自然场景改写启动或决定没有幂等重放")
    providers = _assert_provider_bindings(acceptance, run_id, providers_before, generic, 4)
    return Scenario(
        name=name,
        run_id=run_id,
        session_id=session_id,
        client_request_id=request_id,
        provider_identity={"steps": providers},
        database_facts={**facts, "natural": natural},
    )


def _outline_approve_scenario(
    acceptance: Acceptance, *, resource_type: ResourceType, index: int
) -> Scenario:
    from .run_e2e import Scenario

    suffix = "outline" if resource_type == "outline_content" else "node"
    name = f"rewrite_outline_{suffix}_edited_approve"
    content = (
        "总纲前😀旧线索\r\n总纲后　"
        if resource_type == "outline_content"
        else "节点前😀旧节点\r\n节点后　"
    )
    source = _prepare_outline_source(
        acceptance,
        resource_type=resource_type,
        label=f"{suffix}-{index}",
        content=content,
        updated_at=f"2026-09-05T04:05:{index:02d}.789Z",
        selection_start=3,
        selection_end=7,
    )
    protected_hash = _protected_layers_hash(acceptance, source)
    session_id = acceptance.create_session(name)
    request_id = f"e2e-{name}-start"
    instruction = "完整改写所选大纲片段，选区外必须保持原样。"
    body = _selection_body(
        acceptance,
        source,
        session_id=session_id,
        client_request_id=request_id,
        instruction=instruction,
    )
    providers_before = acceptance.provider_keys()
    started = acceptance.start_run(body).json()
    run_id = str(started["runId"])
    detail = _outline_artifact(
        acceptance,
        _wait_artifact(acceptance, run_id, "rewrite_outline_selection"),
        source,
    )
    initial_payload = cast(dict[str, object], detail["payload"])
    if (
        detail["revision"] != 1
        or initial_payload.get("replacement") != FAKE_OUTLINE_SELECTION_REPLACEMENT
        or _resource_content(acceptance, source) != source.content
    ):
        raise AssertionError("大纲候选在作者确认前修改了正式来源")
    edited = f"  编辑后的{suffix}替换😀\r\n保留尾空格  "
    decision_id = f"e2e-{name}-decision"
    completed = _decide(
        acceptance,
        detail,
        decision="approve",
        client_request_id=decision_id,
        edited_replacement=edited,
    )
    if completed.get("runId") != run_id or completed.get("status") != "completed":
        raise AssertionError("大纲选区编辑批准没有完成同一 Run")
    expected_content = source.prefix + edited + source.suffix
    if _resource_content(acceptance, source) != expected_content:
        raise AssertionError("大纲选区编辑批准没有精确替换 Unicode 码点范围")
    if _protected_layers_hash(acceptance, source) != protected_hash:
        raise AssertionError("大纲选区批准修改了选区外文本或其他正式资料层")
    facts = _durable_facts(acceptance, run_id)
    assert_durable_facts(
        facts,
        database_operation="rewrite_outline_selection",
        model_steps=2,
        artifact_kind="outline_draft",
        artifact_status="applied",
        revisions=2,
        verdicts=["pass"],
        message_roles=["user"],
    )
    inputs = _outline_generation_inputs(acceptance, run_id)
    if len(inputs) != 1 or set(inputs[0]) != {"userInstruction", "selectionTarget"}:
        raise AssertionError("大纲首轮 generation 输入不是严格冻结形状")
    if (
        _decide(
            acceptance,
            detail,
            decision="approve",
            client_request_id=decision_id,
            edited_replacement=edited,
        )
        != completed
        or acceptance.start_run(body).json().get("runId") != run_id
        or _resource_content(acceptance, source) != expected_content
    ):
        raise AssertionError("大纲选区启动或决定重放产生重复应用")
    providers = _assert_provider_bindings(acceptance, run_id, providers_before, facts, 2)
    return Scenario(
        name=name,
        run_id=run_id,
        session_id=session_id,
        client_request_id=request_id,
        provider_identity={"steps": providers},
        database_facts={
            **facts,
            "resourceType": source.resource_type,
            "resourceId": source.resource_id,
            "sourceSha256": source.content_sha256,
            "resultSha256": _sha(expected_content),
            "outsideSelectionUnchanged": True,
            "otherLayersUnchanged": True,
        },
    )


def _outline_revise_scenario(acceptance: Acceptance) -> Scenario:
    from .run_e2e import Scenario

    name = "rewrite_outline_same_run_revise_discard"
    source = _prepare_outline_source(
        acceptance,
        resource_type="outline_content",
        label="revise",
        content="总纲前😀旧线索\r\n返工后仍不应用　",
        updated_at="2026-09-05T04:05:30.789Z",
        selection_start=3,
        selection_end=7,
    )
    protected_hash = _protected_layers_hash(acceptance, source)
    session_id = acceptance.create_session(name)
    request_id = f"e2e-{name}-start"
    instruction = "先改写这个总纲选区，再交作者决定。"
    body = _selection_body(
        acceptance,
        source,
        session_id=session_id,
        client_request_id=request_id,
        instruction=instruction,
    )
    providers_before = acceptance.provider_keys()
    started = acceptance.start_run(body).json()
    run_id = str(started["runId"])
    first = _outline_artifact(
        acceptance,
        _wait_artifact(acceptance, run_id, "rewrite_outline_selection"),
        source,
    )
    first_payload = cast(dict[str, object], first["payload"])
    if first_payload.get("replacement") != FAKE_OUTLINE_SELECTION_REPLACEMENT:
        raise AssertionError("大纲选区 Fake 输出不是本轮独立严格输出")
    revise_id = f"e2e-{name}-revise"
    revise_message = "保持同一来源与选区，完整重写 replacement 后再次复审。"
    accepted = _decide(
        acceptance,
        first,
        decision="revise",
        client_request_id=revise_id,
        user_message=revise_message,
    )
    if accepted.get("runId") != run_id:
        raise AssertionError("大纲返工错误创建了新 Run")
    if (
        _decide(
            acceptance,
            first,
            decision="revise",
            client_request_id=revise_id,
            user_message=revise_message,
        )
        != accepted
    ):
        raise AssertionError("大纲返工受理没有幂等重放")
    second = _outline_artifact(
        acceptance,
        _wait_artifact(acceptance, run_id, "rewrite_outline_selection"),
        source,
    )
    if second["revision"] != 2:
        raise AssertionError("大纲手动返工没有产生 revision 2")
    inputs = _outline_generation_inputs(acceptance, run_id)
    expected_previous = {
        "artifactId": first["id"],
        "artifactRevision": 1,
        "replacement": first_payload["replacement"],
    }
    if (
        len(inputs) != 2
        or set(inputs[0]) != {"userInstruction", "selectionTarget"}
        or set(inputs[1])
        != {
            "userInstruction",
            "selectionTarget",
            "originalUserInstruction",
            "previousCandidate",
        }
        or inputs[1].get("userInstruction") != revise_message
        or inputs[1].get("originalUserInstruction") != instruction
        or inputs[1].get("selectionTarget") != inputs[0].get("selectionTarget")
        or inputs[1].get("previousCandidate") != expected_previous
    ):
        raise AssertionError("大纲返工没有绑定原指令、同源与精确上一候选")
    decision_id = f"e2e-{name}-discard"
    completed = _decide(
        acceptance,
        second,
        decision="discard",
        client_request_id=decision_id,
    )
    if completed.get("runId") != run_id or completed.get("status") != "completed":
        raise AssertionError("大纲返工后丢弃没有完成原 Run")
    if (
        _resource_content(acceptance, source) != source.content
        or _protected_layers_hash(acceptance, source) != protected_hash
    ):
        raise AssertionError("大纲返工或丢弃修改了正式来源或其他资料层")
    facts = _durable_facts(acceptance, run_id)
    assert_durable_facts(
        facts,
        database_operation="rewrite_outline_selection",
        model_steps=4,
        artifact_kind="outline_draft",
        artifact_status="draft",
        revisions=2,
        verdicts=["pass", "pass"],
        message_roles=["user"],
    )
    if (
        _decide(
            acceptance,
            second,
            decision="discard",
            client_request_id=decision_id,
        )
        != completed
        or acceptance.start_run(body).json().get("runId") != run_id
        or _durable_facts(acceptance, run_id) != facts
    ):
        raise AssertionError("大纲返工/丢弃重放新增了候选、计费或事件")
    providers = _assert_provider_bindings(acceptance, run_id, providers_before, facts, 4)
    return Scenario(
        name=name,
        run_id=run_id,
        session_id=session_id,
        client_request_id=request_id,
        provider_identity={"steps": providers},
        database_facts={
            **facts,
            "resourceType": source.resource_type,
            "resourceId": source.resource_id,
            "sourceSha256": source.content_sha256,
            "sourceUnchanged": True,
            "revisionInputBindingsVerified": True,
        },
    )


def scenarios(acceptance: Acceptance) -> Iterator[Scenario]:
    acceptance.control_request("PUT", "/control/provider-mode", {"mode": "pass"})
    acceptance.control_request("PUT", "/control/chapter-writing-review-mode", {"mode": "pass"})
    yield from _review_scenarios(acceptance)
    yield _natural_review_scenario(acceptance)
    yield _explicit_scene_scenario(acceptance)
    yield _natural_scene_scenario(acceptance, decision="approve")
    yield _natural_scene_scenario(acceptance, decision="discard")
    yield _outline_approve_scenario(acceptance, resource_type="outline_content", index=10)
    yield _outline_approve_scenario(acceptance, resource_type="outline_node_content", index=20)
    yield _outline_revise_scenario(acceptance)
