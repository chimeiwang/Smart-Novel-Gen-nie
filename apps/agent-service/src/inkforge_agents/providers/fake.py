from __future__ import annotations

import json
import re

from pydantic import JsonValue

from .base import (
    ModelStructuredOutputRoute,
    ModelToolCall,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
    ModelUsageDiagnostics,
)

FAKE_CHAPTER_REVIEW_REPORT = "本章人物行动清楚，线索核对形成推进；结尾选择可进一步强化后果。"
FAKE_OUTLINE_SELECTION_REPLACEMENT = "人物核对新行动线索后，作出不可逆的选择。"


class FakeModelProvider:
    billable = False
    provider_name = "fake"
    model_name = "fake"
    transport_profile = "transport.fake.v1"
    endpoint_profile = "endpoint.local-fake.v1"
    capability_version = "capability.fake.structured-output.v1"
    supports_request_idempotency = True

    def supports_structured_output(self, route: ModelStructuredOutputRoute) -> bool:
        return route in {
            "responses_json_schema_v1",
            "chat_json_output_v1",
            "quality_strict_tool_v1",
        }

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        if request.structuredOutput is not None:
            output = _structured_output(request)
            prompt_tokens = sum(len(message.content) for message in request.messages)
            completion_tokens = len(json.dumps(output, ensure_ascii=False))
            return ModelTurnResult(
                content="",
                toolCalls=[],
                structuredOutput=output,
                finishReason="stop",
                rawFinishReason="stop",
                usage=ModelUsage(
                    promptTokens=prompt_tokens,
                    cachedTokens=0,
                    completionTokens=completion_tokens,
                    totalTokens=prompt_tokens + completion_tokens,
                ),
                diagnostics=ModelUsageDiagnostics(
                    promptCacheMissTokens=prompt_tokens,
                    reasoningTokens=(0 if request.policy.thinkingMode == "disabled" else None),
                ),
                effectiveMaxOutputTokens=request.maxOutputTokens,
            )
        content, tool_calls = _build_response(request)
        prompt_tokens = sum(len(message.content) for message in request.messages)
        completion_tokens = len(content)
        return ModelTurnResult(
            content=content,
            toolCalls=tool_calls,
            finishReason="tool_calls" if tool_calls else "stop",
            rawFinishReason="tool_calls" if tool_calls else "stop",
            usage=ModelUsage(
                promptTokens=prompt_tokens,
                cachedTokens=0,
                completionTokens=completion_tokens,
                totalTokens=prompt_tokens + completion_tokens,
            ),
            diagnostics=ModelUsageDiagnostics(),
        )


def _structured_output(request: ModelTurnRequest) -> dict[str, JsonValue]:
    structured = request.structuredOutput
    if structured is None:
        raise ValueError("模拟结构化输出缺少 Schema")
    properties = structured.jsonSchema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("模拟结构化输出 Schema 缺少 properties")
    if {"workflow", "operation", "confidence", "clarification"} <= set(properties):
        # 隔离 Fake 只识别明确测试标记；真实意图判断仍由严格模型 Step 执行。
        envelope = json.loads(request.messages[-1].content)
        input_value = envelope.get("input", {})
        text = input_value.get("userInstruction", "")
        answers = input_value.get("clarifications", [])
        if answers:
            text = answers[-1].get("userMessage", "")
        available = _intent_available_operations(envelope)
        marker = re.fullmatch(r"【隔离意图:([a-z][a-z0-9_]*)】", text)
        if marker is not None and marker.group(1) in {item[0] for item in available}:
            return {
                "workflow": "long_serial",
                "operation": marker.group(1),
                "confidence": 0.99,
                "targetType": None,
                "targetId": None,
                "scopeKind": None,
                "arguments": {},
                "clarification": None,
            }
        descriptions = "；".join(item[1] for item in available)
        return {
            "workflow": None,
            "operation": None,
            "confidence": 0.2,
            "targetType": None,
            "targetId": None,
            "scopeKind": None,
            "arguments": {},
            "clarification": {
                "code": "intent.unclear",
                "prompt": f"请根据当前可用操作说明明确请求：{descriptions}",
            },
        }
    if "replacement" in properties:
        replacement = (
            FAKE_OUTLINE_SELECTION_REPLACEMENT
            if structured.name == "output_outline_selection_replacement_v1"
            else "模拟选区替换文本"
        )
        return {"replacement": replacement}
    if "report" in properties:
        return {"report": FAKE_CHAPTER_REVIEW_REPORT}
    if "answer" in properties:
        return {"answer": "模拟模型已依据冻结章节证据回答问题。"}
    if {"summary", "content"} <= set(properties):
        return {
            "summary": "人物核对已有线索并作出行动选择。",
            "content": "林舟把旧行动线索放在桌上，逐一核对。\n\n窗外雨声渐紧，他终于作出选择。",
        }
    if {"title", "summary", "chapterGoal", "sceneBeats"} <= set(properties):
        return {
            "title": "隔离章节规划",
            "summary": "人物核对现有事实后，为下一步行动作出选择。",
            "chapterGoal": "让人物通过可观察的行动确认当前处境。",
            "totalEstimatedWords": 1000,
            "sceneBeats": [
                {
                    "goal": "人物核对已经发现的线索。",
                    "conflict": "线索不足以直接支持结论。",
                    "characters": [],
                    "foreshadowingRefs": [],
                    "estimatedWords": 500,
                    "acceptanceCriteria": "人物确认一条已有证据。",
                },
                {
                    "goal": "人物依据已确认的证据选择下一步行动。",
                    "characters": [],
                    "estimatedWords": 500,
                    "acceptanceCriteria": "人物作出明确决定。",
                },
            ],
        }
    if {"contentVerdict", "findings"} <= set(properties):
        return {"contentVerdict": "pass", "findings": []}
    raise ValueError("模拟 Provider 不支持该结构化输出 Schema")


def _intent_available_operations(envelope: object) -> list[tuple[str, str]]:
    if not isinstance(envelope, dict):
        return []
    evidence = envelope.get("evidenceBundle")
    if not isinstance(evidence, dict):
        return []
    items = evidence.get("items")
    if not isinstance(items, list):
        return []
    result: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict) or item.get("resourceType") != "intent_context":
            continue
        content = item.get("contentJson")
        if not isinstance(content, dict):
            continue
        available = content.get("availableOperations")
        if not isinstance(available, list):
            continue
        for operation in available:
            if not isinstance(operation, dict):
                continue
            code = operation.get("operation")
            description = operation.get("description")
            if isinstance(code, str) and isinstance(description, str):
                result.append((code, description))
    return result


def _build_response(request: ModelTurnRequest) -> tuple[str, list[ModelToolCall]]:
    content = "模拟模型已完成本轮处理。"
    if not request.tools or any(message.role == "tool" for message in request.messages):
        return content, []

    tool_names = {tool.name for tool in request.tools}
    message_text = "\n".join(message.content for message in request.messages)
    name, arguments = _select_tool(tool_names, message_text)
    if name is None:
        name = request.tools[0].name
        arguments = {}
    if name == "begin_artifact_output":
        if arguments.get("operation") in {
            "rewrite_chapter_selection",
            "rewrite_outline_selection",
        }:
            content = "模拟选区替换文本"
        else:
            content = (
                "ARTIFACT_OUTPUT_START\n"
                "这是模拟模型生成的完整章节正文，用于验证待审核草案流程。\n"
                "ARTIFACT_OUTPUT_END"
            )
    return content, [
        ModelToolCall(
            id="fake-tool-call-1",
            name=name,
            arguments=arguments,
        )
    ]


def _select_tool(
    tool_names: set[str],
    message_text: str,
) -> tuple[str | None, dict[str, JsonValue]]:
    if "submit_quality_report" in tool_names:
        return (
            "submit_quality_report",
            {
                "scores": {
                    "characterConsistency": 90.0,
                    "worldRuleConsistency": 90.0,
                    "timelineConsistency": 90.0,
                    "causalityConsistency": 90.0,
                    "foreshadowingConsistency": 90.0,
                },
                "qualityGate": "pass",
                "issues": [],
                "report": "一致性终检未发现冲突。",
                "rewriteBrief": None,
            },
        )
    if "submit_evaluation" in tool_names:
        return (
            "submit_evaluation",
            {
                "artifactKey": "fake-artifact",
                "verdict": "pass",
                "summary": "模拟复审通过。",
            },
        )
    if "begin_artifact_output" in tool_names and any(
        keyword in message_text
        for keyword in (
            "正文",
            "写一章",
            "续写",
            "改写",
            "重写",
            "rewrite_chapter_selection",
            "rewrite_outline_selection",
        )
    ):
        selection = _selection_context(message_text)
        if selection is not None:
            operation = selection.get("operation")
            if operation in {
                "rewrite_chapter_selection",
                "rewrite_outline_selection",
            }:
                args: dict[str, JsonValue] = {
                    **selection,
                    "kind": "chapter_draft"
                    if operation == "rewrite_chapter_selection"
                    else "outline_draft",
                    "summary": "模拟选区改写草案",
                    "artifactKey": "fake-selection-draft",
                    "submitForReview": True,
                    "replacement": "模拟选区替换文本",
                }
                return "begin_artifact_output", args
        return (
            "begin_artifact_output",
            {
                "kind": "chapter_draft",
                "summary": "模拟章节正文草案。",
                "content": "这是模拟模型生成的完整章节正文，用于验证待审核草案流程。",
                "artifactKey": "fake-chapter-draft",
                "submitForReview": True,
            },
        )
    if "propose_updates" in tool_names:
        return (
            "propose_updates",
            {
                "summary": "模拟结构化更新草案。",
                "updates": {"worldSetting": "模拟世界设定更新。"},
                "artifactKey": "fake-agent-updates",
                "submitForReview": True,
            },
        )
    if "submit_beat_plan" in tool_names:
        return (
            "submit_beat_plan",
            {
                "title": "模拟章节计划",
                "beatCount": 1,
                "summary": "模拟章节计划草案。",
                "chapterGoal": "推进当前章节。",
                "totalEstimatedWords": 1000,
                "sceneBeats": [
                    {
                        "order": 1,
                        "goal": "推进当前章节。",
                        "estimatedWords": 1000,
                    }
                ],
            },
        )
    if "submit_validation_report" in tool_names:
        return (
            "submit_validation_report",
            {"hasConflicts": False, "conflicts": []},
        )
    return None, {}


def _selection_context(message_text: str) -> dict[str, JsonValue] | None:
    operation_match = re.search(r"rewrite_(?:chapter|outline)_selection", message_text)
    if operation_match is None:
        return None
    operation = operation_match.group(0)
    context: dict[str, JsonValue] = {"operation": operation}
    for field in (
        "resourceType",
        "resourceId",
        "baseUpdatedAt",
        "baseContentHash",
        "selectionStart",
        "selectionEnd",
        "selectedTextHash",
    ):
        match = re.search(rf'"{field}"\s*:\s*("[^"]*"|-?\d+)', message_text)
        if match is None:
            return None
        raw = match.group(1)
        context[field] = json.loads(raw) if raw.startswith('"') else int(raw)
    return context
