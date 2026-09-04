"""只在受双门禁的 E2E Agent 进程中注入的可控 Fake Provider。"""

from __future__ import annotations

import hashlib
import json

import httpx
from inkforge_agents.providers.base import (
    ModelStructuredOutputRoute,
    ModelTurnRequest,
    ModelTurnResult,
)
from inkforge_agents.providers.fake import FakeModelProvider
from inkforge_contracts import ChapterDraftResult, EvaluationFinding

_WRITING_REVIEW_ROLES = {
    "reviewer.chapter_draft_consistency.v1": "consistency",
    "reviewer.chapter_draft_editorial.v1": "editorial",
}


class ControlledFakeModelProvider:
    """通过外部测试控制器提供确定性等待点，并且不暴露任何业务路由。"""

    billable = False
    provider_name = FakeModelProvider.provider_name
    model_name = FakeModelProvider.model_name
    transport_profile = FakeModelProvider.transport_profile
    endpoint_profile = FakeModelProvider.endpoint_profile
    capability_version = FakeModelProvider.capability_version
    supports_request_idempotency = FakeModelProvider.supports_request_idempotency

    def __init__(self, *, control_url: str, control_token: str) -> None:
        if not control_url or len(control_token.encode("utf-8")) < 32:
            raise ValueError("E2E Fake Provider 控制参数无效")
        self._delegate = FakeModelProvider()
        self._token = control_token
        self._http = httpx.AsyncClient(
            base_url=control_url,
            headers={"X-InkForge-E2E-Token": control_token},
            timeout=httpx.Timeout(None, connect=2.0),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
            trust_env=False,
        )

    def supports_structured_output(self, route: ModelStructuredOutputRoute) -> bool:
        return self._delegate.supports_structured_output(route)

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        idempotency_key = request.requestIdempotencyKey
        if idempotency_key is None:
            # E2E 只控制 V2；闲置的 V1 消费器仍可保持与普通 Fake Provider 同形。
            return await self._delegate.complete_turn(request)
        request_sha256 = hashlib.sha256(
            json.dumps(
                request.model_dump(mode="json", by_alias=True, exclude_none=True),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        response = await self._http.post(
            "/control/provider/reached",
            json={
                "idempotencyKey": idempotency_key,
                "requestSha256": request_sha256,
            },
        )
        response.raise_for_status()
        result = await self._delegate.complete_turn(request)
        if request.policy.policyId == "reviewer.chapter_plan_editorial.v1":
            decision = await self._http.post(
                "/control/provider/chapter-plan-review-decision",
                json={
                    "idempotencyKey": idempotency_key,
                    "requestSha256": request_sha256,
                },
            )
            decision.raise_for_status()
            verdict = decision.json().get("contentVerdict")
            if verdict == "issues_found":
                result = _chapter_plan_revision(request, result)
            elif verdict != "pass":
                raise ValueError("E2E 章节规划复审控制结论无效")
        elif request.policy.policyId in _WRITING_REVIEW_ROLES:
            role = _WRITING_REVIEW_ROLES[request.policy.policyId]
            decision = await self._http.post(
                "/control/provider/chapter-writing-review-decision",
                json={
                    "idempotencyKey": idempotency_key,
                    "requestSha256": request_sha256,
                    "role": role,
                },
            )
            decision.raise_for_status()
            body = decision.json()
            mode, revision, verdict = (
                body.get("mode"),
                body.get("artifactRevision"),
                body.get("contentVerdict"),
            )
            if (
                mode not in {"pass", "revise_once", "patch_once", "patch_conflict"}
                or type(revision) is not int
                or revision < 1
                or verdict != ("issues_found" if revision == 1 and mode != "pass" else "pass")
            ):
                raise ValueError("E2E 正文复审控制结论或候选修订无效")
            if verdict == "issues_found":
                result = _chapter_writing_revision(request, result, mode=mode, role=role)
        completed = await self._http.post(
            "/control/provider/completed",
            json={
                "idempotencyKey": idempotency_key,
                "requestSha256": request_sha256,
            },
        )
        completed.raise_for_status()
        return result

    async def aclose(self) -> None:
        await self._http.aclose()


def _chapter_writing_revision(
    request: ModelTurnRequest,
    result: ModelTurnResult,
    *,
    mode: str,
    role: str,
) -> ModelTurnResult:
    """候选仅留当前测试 Agent 内存；控制器只取得角色和不可变调用身份。"""
    envelopes = [
        json.loads(message.content) for message in request.messages if message.role == "user"
    ]
    if len(envelopes) != 1 or not isinstance(envelopes[0], dict):
        raise ValueError("E2E 正文复审缺少唯一执行信封")
    envelope = envelopes[0]
    if (envelope.get("workflow"), envelope.get("operation"), envelope.get("purpose")) != (
        "long_serial",
        "write_chapter",
        "review",
    ):
        raise ValueError("E2E 正文复审执行身份不匹配")
    try:
        candidate = ChapterDraftResult.model_validate(envelope["input"]["candidate"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("E2E 正文复审候选不符合完整结果契约") from None
    bundle = envelope.get("evidenceBundle")
    items = bundle.get("items") if isinstance(bundle, dict) else None
    if not isinstance(items, list):
        raise ValueError("E2E 正文复审缺少冻结 Evidence")
    item = next(
        (value for value in items if isinstance(value, dict) and value.get("exists") is True), None
    )
    if item is None:
        raise ValueError("E2E 正文复审没有可引用证据")
    finding = {
        "dimension": "chapter_draft.local",
        "severity": "warning",
        "claim": "隔离验收要求明确人物核对行动线索的措辞。",
        "evidence": [
            {"evidenceItemId": item.get("id"), "contentSha256": item.get("contentSha256")}
        ],
        "suggestion": "依据同一冻结事实修改候选措辞，保留完整正文。",
        "confidence": 1.0,
    }
    if mode in {"patch_once", "patch_conflict"}:
        find = "旧行动线索"
        if candidate.content.count(find) != 1:
            raise ValueError("E2E 正文 patch 需要候选内唯一已知原文")
        start = candidate.content.index(find)
        replacement = (
            "另一行动线索" if mode == "patch_conflict" and role == "editorial" else "新行动线索"
        )
        finding["candidatePatch"] = {"kind": "text_replace", "find": find, "replace": replacement}
        finding["candidateRange"] = {"startCodePoint": start, "endCodePoint": start + len(find)}
    output = {
        "contentVerdict": "issues_found",
        "findings": [EvaluationFinding.model_validate(finding).model_dump(mode="json")],
    }
    completion_tokens = len(json.dumps(output, ensure_ascii=False))
    return result.model_copy(
        update={
            "structuredOutput": output,
            "usage": result.usage.model_copy(
                update={
                    "completionTokens": completion_tokens,
                    "totalTokens": result.usage.promptTokens + completion_tokens,
                }
            ),
        }
    )


def _chapter_plan_revision(request: ModelTurnRequest, result: ModelTurnResult) -> ModelTurnResult:
    """仅在内存读取真实冻结证据身份；控制器与诊断不接收候选正文。"""

    envelopes = [
        json.loads(message.content) for message in request.messages if message.role == "user"
    ]
    if len(envelopes) != 1 or not isinstance(envelopes[0], dict):
        raise ValueError("E2E 章节规划复审缺少唯一执行信封")
    envelope = envelopes[0]
    if (envelope.get("workflow"), envelope.get("operation"), envelope.get("purpose")) != (
        "long_serial",
        "plan_chapter",
        "review",
    ):
        raise ValueError("E2E 章节规划复审执行身份不匹配")
    bundle = envelope.get("evidenceBundle")
    items = bundle.get("items") if isinstance(bundle, dict) else None
    if not isinstance(items, list):
        raise ValueError("E2E 章节规划复审缺少冻结 Evidence")
    item = next(
        (value for value in items if isinstance(value, dict) and value.get("exists") is True), None
    )
    if item is None:
        raise ValueError("E2E 章节规划复审没有可引用证据")
    finding = EvaluationFinding.model_validate(
        {
            "dimension": "chapter_plan.local",
            "severity": "warning",
            "claim": "隔离验收要求候选经过一次完整返工以突出人物主动选择。",
            "evidence": [
                {"evidenceItemId": item.get("id"), "contentSha256": item.get("contentSha256")}
            ],
            "suggestion": "保持冻结事实不变，完整重写规划并突出人物的主动选择。",
            "confidence": 1.0,
        }
    )
    output = {
        "contentVerdict": "issues_found",
        "findings": [finding.model_dump(mode="json")],
    }
    completion_tokens = len(json.dumps(output, ensure_ascii=False))
    return result.model_copy(
        update={
            "structuredOutput": output,
            "usage": result.usage.model_copy(
                update={
                    "completionTokens": completion_tokens,
                    "totalTokens": result.usage.promptTokens + completion_tokens,
                }
            ),
        }
    )
