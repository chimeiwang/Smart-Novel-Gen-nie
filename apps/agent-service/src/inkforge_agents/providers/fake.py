from __future__ import annotations

import json
import re
from typing import cast

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
            "plain_text_v1",
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
    if structured.name == "episode_script":
        return _fake_episode_script(_frozen_video_context(request))
    if structured.name == "episode_script_review":
        return {
            "decision": "pass",
            "summary": "模拟审阅未发现阻断作者采用的问题。",
            "requiredChanges": [],
            "findings": [],
        }
    if structured.name == "episode_storyboard":
        return _fake_episode_storyboard(_frozen_video_context(request))
    if structured.name == "episode_storyboard_review":
        return {
            "decision": "pass",
            "summary": "模拟审片未发现阻断作者采用的问题。",
            "requiredChanges": [],
            "findings": [],
        }
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


def _frozen_video_context(request: ModelTurnRequest) -> dict[str, JsonValue]:
    """只解析本地适配器写入的显式 JSON 边界，不读取或猜测作品身份。"""

    content = request.messages[-1].content
    marker = "冻结上下文："
    stage_marker = "\n本次阶段："
    if marker not in content or stage_marker not in content:
        raise ValueError("模拟视频输出缺少冻结上下文边界")
    raw = content.split(marker, 1)[1].split(stage_marker, 1)[0]
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("模拟视频冻结上下文必须是对象")
    return value


def _fake_episode_script(context: dict[str, JsonValue]) -> dict[str, JsonValue]:
    draft = context.get("draft")
    if not isinstance(draft, dict):
        raise ValueError("模拟剧本输出缺少冻结工作稿")
    raw_scenes = draft.get("scenes")
    scenes = list(raw_scenes) if isinstance(raw_scenes, list) else []
    selected = context.get("selectedSceneIds")
    selected_ids = set(selected) if isinstance(selected, list) else set()
    if selected_ids:
        chosen = [
            scene
            for scene in scenes
            if isinstance(scene, dict) and scene.get("id") in selected_ids
        ]
        if len(chosen) != len(selected_ids):
            raise ValueError("模拟剧本修订范围不属于冻结工作稿")
        return cast(
            dict[str, JsonValue],
            {
                "overview": None,
                "scenes": chosen,
                "endingStates": None,
                "dependencies": None,
            },
        )
    if not scenes:
        sources = context.get("sources")
        if not isinstance(sources, list) or not sources or not isinstance(sources[0], dict):
            raise ValueError("模拟剧本起草缺少真实冻结来源")
        source = sources[0]
        ranges = source.get("selectedRanges")
        if not isinstance(ranges, list) or not ranges or not isinstance(ranges[0], dict):
            raise ValueError("模拟剧本起草缺少真实选区")
        selected_range = ranges[0]
        text = selected_range.get("text")
        if not isinstance(text, str) or not text:
            raise ValueError("模拟剧本起草选区正文无效")
        snapshot_id = source.get("sourceSnapshotId")
        scenes = [
            {
                "id": None,
                "tempKey": "fake-scene-1",
                "title": "隔离试制场次",
                "locationLabel": "来源场景",
                "timeLabel": "当前时段",
                "narrativeTime": "本集",
                "characterIds": [],
                "lines": [
                    {
                        "id": None,
                        "tempKey": "fake-line-1",
                        "kind": "action",
                        "speakerId": None,
                        "text": f"人物依据来源行动：{text[:120]}",
                        "sourceRefs": [
                            {
                                "sourceSnapshotId": snapshot_id,
                                "start": selected_range.get("start"),
                                "end": selected_range.get("end"),
                            }
                        ],
                    }
                ],
            }
        ]
    overview = draft.get("overview")
    ending_states = draft.get("endingStates")
    dependencies = draft.get("dependencies")
    return {
        "overview": overview if isinstance(overview, dict) else {},
        "scenes": scenes,
        "endingStates": ending_states if isinstance(ending_states, list) else [],
        "dependencies": dependencies if isinstance(dependencies, list) else [],
    }


def _fake_episode_storyboard(context: dict[str, JsonValue]) -> dict[str, JsonValue]:
    draft = context.get("draft")
    if not isinstance(draft, dict):
        raise ValueError("模拟分镜输出缺少冻结工作稿")
    raw_shots = draft.get("shots")
    shots = list(raw_shots) if isinstance(raw_shots, list) else []
    selected = context.get("selectedShotIds")
    selected_ids = set(selected) if isinstance(selected, list) else set()
    if selected_ids:
        shots = [
            shot
            for shot in shots
            if isinstance(shot, dict) and shot.get("id") in selected_ids
        ]
        if len(shots) != len(selected_ids):
            raise ValueError("模拟分镜修订范围不属于冻结工作稿")
    elif not shots:
        script = context.get("script")
        script_scenes = script.get("scenes") if isinstance(script, dict) else None
        if (
            not isinstance(script_scenes, list)
            or not script_scenes
            or not isinstance(script_scenes[0], dict)
        ):
            raise ValueError("模拟分镜起草缺少正式剧本场次")
        scene = script_scenes[0]
        lines = scene.get("lines")
        first_line = lines[0] if isinstance(lines, list) and lines else None
        references = context.get("availableReferences")
        defaults = context.get("productionDefaults")
        if (
            not isinstance(references, list)
            or not references
            or not isinstance(references[0], dict)
            or not isinstance(defaults, dict)
        ):
            raise ValueError("模拟分镜起草缺少已批准参考或制作默认值")
        scene_id = scene.get("id")
        line_id = first_line.get("id") if isinstance(first_line, dict) else None
        action = first_line.get("text") if isinstance(first_line, dict) else scene.get("title")
        shots = [
            {
                "id": None,
                "tempKey": "fake-shot-1",
                "lineage": [],
                "scriptSceneId": scene_id,
                "scriptLineIds": [line_id] if isinstance(line_id, str) else [],
                "title": "隔离试制镜头",
                "action": action if isinstance(action, str) and action else "人物完成本场行动。",
                "framing": "medium",
                "cameraMovement": "static",
                "durationMs": 6000,
                "productionIntent": {
                    **defaults,
                    "prompt": "人物在冻结场景中完成剧本明确动作，保持定妆和道具一致。",
                    "durationSeconds": 6,
                    "references": [
                        {
                            "canonVersionId": references[0].get("canonVersionId"),
                            "strength": references[0].get("defaultStrength"),
                        }
                    ],
                },
            }
        ]
    return {"shots": [_storyboard_proposal_shot(shot) for shot in shots]}


def _storyboard_proposal_shot(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ValueError("模拟分镜镜头必须是对象")
    shot = dict(value)
    intent = shot.get("productionIntent")
    if not isinstance(intent, dict):
        raise ValueError("模拟分镜镜头缺少制作意图")
    choices: list[dict[str, JsonValue]] = []
    references = intent.get("references")
    if not isinstance(references, list):
        raise ValueError("模拟分镜镜头缺少参考版本")
    for reference in references:
        if not isinstance(reference, dict):
            raise ValueError("模拟分镜参考必须是对象")
        choices.append(
            {
                "canonVersionId": reference.get("canonVersionId"),
                "strength": reference.get("strength"),
            }
        )
    shot["productionIntent"] = {
        key: item
        for key, item in intent.items()
        if key not in {"references"}
    } | {"references": choices}
    return shot


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
