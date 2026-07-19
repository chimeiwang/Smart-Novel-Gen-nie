from __future__ import annotations

import re

from inkforge_contracts import count_short_story_text_length
from pydantic import JsonValue

from .base import (
    ModelToolCall,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
)


class FakeModelProvider:
    billable = False
    provider_name = "fake"
    model_name = "fake"

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
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
        )


def _build_response(request: ModelTurnRequest) -> tuple[str, list[ModelToolCall]]:
    content = "模拟模型已完成本轮处理。"
    message_text = "\n".join(message.content for message in request.messages)
    if not request.tools and "operation=write_short_story" in message_text:
        target_match = re.search(
            r'"targetTotalWordCount"\s*:\s*(\d+)', message_text
        )
        target = int(target_match.group(1)) if target_match is not None else 6000
        target = min(max(target, 6000), 80000)
        tail = "尾声：选择已经兑现，故事在这里完整结束。【模拟整稿尾部】"
        filler_length = target - count_short_story_text_length(tail)
        body = "文" * filler_length
        return (
            "ARTIFACT_OUTPUT_START\n"
            f"{body}\n\n"
            f"{tail}\n"
            "ARTIFACT_OUTPUT_END",
            [],
        )
    if not request.tools or any(message.role == "tool" for message in request.messages):
        return content, []

    tool_names = {tool.name for tool in request.tools}
    name, arguments = _select_tool(tool_names, message_text)
    if name is None:
        name = request.tools[0].name
        arguments = {}
    if name == "begin_artifact_output":
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
    if "submit_short_story_outline" in tool_names:
        if "mode=reviser" in message_text:
            revision_match = re.search(r'"revision"\s*:\s*(\d+)', message_text)
            source_revision = (
                int(revision_match.group(1)) if revision_match is not None else 1
            )
            section_ids = re.findall(
                r'"id"\s*:\s*"(short-section-[^"]+)"', message_text
            )
            requested_section_match = re.search(
                r"(?:修改|强化|调整|重写)第\s*(\d+)\s*节", message_text
            )
            requested_section_index = (
                int(requested_section_match.group(1)) - 1
                if requested_section_match is not None
                else 0
            )
            section_operations: list[JsonValue] = []
            if 0 <= requested_section_index < len(section_ids):
                section_operations.append(
                    {
                        "operation": "update",
                        "sectionId": section_ids[requested_section_index],
                        "events": f"模拟模型根据第 {source_revision} 版和用户意见更新了本节事件。",
                    }
                )
            return (
                "submit_short_story_outline",
                {
                    "mode": "patch",
                    "sourceRevision": source_revision,
                    "sectionOperations": section_operations,
                    "changeSummary": "模拟模型完成了本轮大纲修改。",
                },
            )
        return (
            "submit_short_story_outline",
            {
                "mode": "full",
                "corePremise": "主角试图保住一名被城市集体遗忘的人。",
                "anchors": {
                    "mustKeep": ["结局兑现原始灵感"],
                    "confirmed": ["保持单一主线"],
                    "avoid": [],
                },
                "sections": [
                    {"title": "异常", "events": "主角发现熟人从所有人的记忆中消失。"},
                    {"title": "追索", "events": "主角追查遗忘规则并付出代价。"},
                    {"title": "选择", "events": "主角理解真相并完成最终选择。"},
                ],
                "changeSummary": "模拟模型根据原始灵感形成首版完整大纲。",
            },
        )
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
        if (
            "[E2E_AUTO_REWRITE_ONCE]" in message_text
            and "operation=write_short_story" in message_text
            and "mode=reviewer" in message_text
            and re.search(r'"automaticRewriteCount"\s*:\s*0', message_text)
            and "结构、节奏、高潮和结局兑现" in message_text
        ):
            return (
                "submit_evaluation",
                {
                    "artifactKey": "fake-artifact",
                    "verdict": "revise",
                    "summary": "模拟编辑要求执行一次自动完整返工。",
                    "requiredChanges": "强化开场危机，并保持结局兑现不变。",
                },
            )
        return (
            "submit_evaluation",
            {
                "artifactKey": "fake-artifact",
                "verdict": "pass",
                "summary": "模拟复审通过。",
            },
        )
    if "begin_artifact_output" in tool_names and any(
        keyword in message_text for keyword in ("正文", "写一章", "续写", "改写", "重写")
    ):
        return (
            "begin_artifact_output",
            {
                "kind": "chapter_draft",
                "summary": "模拟章节正文草案。",
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
            },
        )
    if "submit_validation_report" in tool_names:
        return (
            "submit_validation_report",
            {"hasConflicts": False, "conflicts": []},
        )
    return None, {}
