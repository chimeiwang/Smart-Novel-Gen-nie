from __future__ import annotations

import re

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


def _fake_short_story() -> str:
    phases = ("异常", "追索", "试探", "失去", "反击", "真相", "抉择", "余波")
    locations = ("旧钟楼", "雨巷", "档案馆", "渡口", "废站", "市集", "天台", "晨雾中的广场")
    clues = (
        "褪色车票",
        "停摆怀表",
        "缺页名册",
        "未寄出的信",
        "反写门牌",
        "录音残片",
        "旧报剪影",
        "带裂纹的铜铃",
    )
    costs = (
        "失去一段记忆",
        "暴露藏身处",
        "误伤唯一盟友",
        "放弃安全退路",
        "承认旧日过错",
        "承担陌生人的怀疑",
        "交出关键证据",
        "错过最后一班船",
    )
    paragraphs = [
        "开端：城里每天黎明都会忘记一个人，只有守夜人林岚仍记得那些消失的名字。她在钟楼底层发现好友沈砚的照片正在褪色，于是决定在下一次钟响前查清遗忘的来源。"
    ]
    for index in range(72):
        phase = phases[index % len(phases)]
        location = locations[(index * 3) % len(locations)]
        clue = clues[(index * 5) % len(clues)]
        cost = costs[(index * 7) % len(costs)]
        paragraphs.append(
            f"{phase}·第{index + 1}次钟响。林岚抵达{location}，"
            f"从{clue}留下的细节中确认遗忘并非自然发生。"
            f"她先用自己的记录核对目击者的话，再逼迫幕后守门人回答前一夜的去向；对方试图用一段温柔的假记忆换走她的追问，她却选择{cost}。"
            "这个选择让线索向前推进，也让她与沈砚的约定变得更难兑现。她没有绕开代价，而是把新发现写进随身册页，准备在下一处矛盾中验证。"
        )
    paragraphs.append(
        "高潮：最后一次钟响前，林岚确认整座城市用集体遗忘维持虚假的安稳。她公开册页，让每个被遗忘者重新拥有名字，也接受自己会被所有人忘记的代价。沈砚在钟声落下时读出了她留下的第一句话，完成了两人的约定。"
    )
    paragraphs.append(
        "尾声：清晨的人群仍不知道守夜人的面孔，却开始为无名者保留空椅。沈砚把册页放回钟楼，选择已经兑现，故事在这里完整结束。【模拟整稿尾部】"
    )
    return "\n\n".join(paragraphs)


_FAKE_SHORT_STORY = _fake_short_story()


def _build_response(request: ModelTurnRequest) -> tuple[str, list[ModelToolCall]]:
    content = "模拟模型已完成本轮处理。"
    message_text = "\n".join(message.content for message in request.messages)
    if not request.tools and "operation=write_short_story" in message_text:
        return (
            "ARTIFACT_OUTPUT_START\n"
            f"{_FAKE_SHORT_STORY}\n"
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
