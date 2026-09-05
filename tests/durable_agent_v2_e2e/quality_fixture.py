"""隔离 E2E 的质量工具响应；测试标记只在此受控 Provider 中解释。"""

from __future__ import annotations

import hashlib
import json

from inkforge_agents.providers.base import (
    ModelToolCall,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
    ModelUsageDiagnostics,
)
from inkforge_contracts.quality import ConsistencyQualityReport
from inkforge_contracts.quality_execution import QualityContextV2, QualityStepInput
from pydantic import JsonValue

CORRECTION_MARKER = "QUALITY_E2E_CORRECTION_ONCE"
CORRECTION_CODE = "MODEL_TOOL_PROTOCOL_CORRECTION_REQUIRED"
QUALITY_PROFILES = {
    "quality.consistency.v2": "generation",
    "system.quality_protocol_corrector.v2": "protocol_correction",
}
REPORT = (
    "核查位置：旧城开门场景。人物依据已有线索作出选择，建议明确行动先后。\r\n" * 40
    + "完整一致性报告尾部🚀"
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def quality_report(*, correction: bool) -> dict[str, JsonValue]:
    return ConsistencyQualityReport.model_validate(
        {
            "scores": {
                name: 82.5
                for name in (
                    "characterConsistency",
                    "worldRuleConsistency",
                    "timelineConsistency",
                    "causalityConsistency",
                    "foreshadowingConsistency",
                )
            },
            "qualityGate": "revise" if correction else "pass",
            "issues": [
                {
                    "dimension": "timeline",
                    "severity": "warning",
                    "message": "建议明确行动先后。",
                    "evidence": "人物核对不可变的章节事实。",
                    "location": None,
                    "suggestion": "由作者决定是否补充时间衔接。",
                }
            ]
            if correction
            else [],
            "report": REPORT,
            "rewriteBrief": "保留全文，由作者选择是否补充衔接。" if correction else None,
        }
    ).model_dump(mode="json")


def quality_turn_result(request: ModelTurnRequest) -> ModelTurnResult | None:
    purpose = QUALITY_PROFILES.get(request.policy.policyId)
    if purpose is None:
        return None
    if (
        request.structuredOutput is not None
        or request.requiredToolName != "submit_quality_report"
        or [(tool.name, tool.strict) for tool in request.tools] != [("submit_quality_report", True)]
        or request.policy.thinkingMode != "disabled"
    ):
        raise ValueError("质量 E2E 必须使用关闭思考的唯一 strict 工具请求")
    envelopes = [
        json.loads(message.content) for message in request.messages if message.role == "user"
    ]
    if len(envelopes) != 1 or not isinstance(envelopes[0], dict):
        raise ValueError("质量 E2E 缺少唯一完整执行信封")
    envelope = envelopes[0]
    if (envelope.get("workflow"), envelope.get("operation"), envelope.get("purpose")) != (
        "quality",
        "consistency",
        purpose,
    ):
        raise ValueError("质量 E2E 执行身份不一致")
    step = QualityStepInput.model_validate(envelope["input"])
    items = envelope["evidenceBundle"]["items"]
    if len(items) != 1 or items[0]["resourceType"] != "quality_context":
        raise ValueError("质量 E2E 没有唯一完整正文上下文")
    context = QualityContextV2.model_validate(items[0]["contentJson"])
    if (
        items[0]["resourceId"] != context.checkId
        or step.userInstruction != (context.message or "检查本章一致性")
        or (purpose == "protocol_correction") != (step.failedStepId is not None)
    ):
        raise ValueError("质量 E2E 来源、原指令或纠正身份不一致")
    correction = CORRECTION_MARKER in step.userInstruction
    invalid = correction and purpose == "generation"
    report = quality_report(correction=correction)
    prompt_tokens = sum(len(message.content) for message in request.messages)
    completion_tokens = 20 if invalid else len(json.dumps(report, ensure_ascii=False))
    return ModelTurnResult(
        content="",
        toolCalls=[]
        if invalid
        else [
            ModelToolCall(id="e2e-quality-report", name="submit_quality_report", arguments=report)
        ],
        finishReason="tool_calls",
        rawFinishReason="tool_calls",
        invalidToolCallCount=int(invalid),
        invalidToolCallNames=["submit_quality_report"] if invalid else [],
        invalidToolCallCodes=["json_decode_error"] if invalid else [],
        invalidToolCallArgumentCharacterCounts=[99] if invalid else [],
        usage=ModelUsage(
            promptTokens=prompt_tokens,
            cachedTokens=0,
            completionTokens=completion_tokens,
            totalTokens=prompt_tokens + completion_tokens,
        ),
        diagnostics=ModelUsageDiagnostics(promptCacheMissTokens=prompt_tokens, reasoningTokens=0),
        effectiveMaxOutputTokens=request.maxOutputTokens,
    )
