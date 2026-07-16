from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from ..definitions.agents import AgentId
from .contracts import (
    CreativeOperation,
    create_default_operation_for_agent,
    create_fallback_operation,
)
from .definitions import OPERATION_DEFINITIONS

ALIASES: dict[str, AgentId] = {
    "设定": "设定",
    "设定顾问": "设定",
    "剧情": "剧情",
    "剧情顾问": "剧情",
    "写作": "写作",
    "作家": "写作",
    "校验": "校验",
    "校验员": "校验",
    "编辑": "编辑",
    "网文编辑": "编辑",
    "编辑顾问": "编辑",
}


class OperationClassifier(Protocol):
    async def classify(self, user_message: str) -> CreativeOperation: ...


@dataclass(frozen=True, slots=True)
class OperationRouteResult:
    operation: CreativeOperation
    usedCommand: bool
    reasoning: str


def parse_agent_command(message: str) -> AgentId | None:
    match = re.search(r"@([\u4e00-\u9fa5A-Za-z0-9_-]+)", message)
    return ALIASES.get(match.group(1)) if match else None


async def route_creative_operation(
    user_message: str,
    classifier: OperationClassifier | None = None,
) -> OperationRouteResult:
    if re.search(r"同步.{0,6}设定|维护设定库|提取.{0,12}事实变化", user_message):
        fallback = create_fallback_operation(user_message)
        return OperationRouteResult(fallback, False, "同步设定流程已移除，回退为普通问答。")
    command = parse_agent_command(user_message)
    if command is not None:
        explicit_operation = classify_by_explicit_keywords(user_message)
        if (
            explicit_operation.kind != "answer_question"
            and explicit_operation.primaryAgent == command
        ):
            operation = normalize_operation(explicit_operation)
        else:
            operation = normalize_operation(
                create_default_operation_for_agent(command, user_message),
                preserve_primary=True,
            )
        return OperationRouteResult(operation, True, operation.reasoning)
    if not user_message.strip():
        fallback = create_fallback_operation(user_message)
        return OperationRouteResult(fallback, False, fallback.reasoning)
    try:
        operation = (
            await classifier.classify(user_message)
            if classifier is not None
            else classify_by_explicit_keywords(user_message)
        )
        if operation.kind == "sync_lore":
            fallback = create_fallback_operation(user_message)
            return OperationRouteResult(
                fallback,
                False,
                "同步设定流程已移除，回退为普通问答。",
            )
        if operation.confidence < 0.5:
            operation = create_fallback_operation(user_message)
        else:
            operation = normalize_operation(operation)
        return OperationRouteResult(operation, False, operation.reasoning)
    except Exception:
        fallback = create_fallback_operation(user_message)
        return OperationRouteResult(fallback, False, "识别失败，回退为回答问题。")


def normalize_operation(
    operation: CreativeOperation,
    *,
    preserve_primary: bool = False,
) -> CreativeOperation:
    if operation.kind == "sync_lore":
        return create_fallback_operation(operation.userGoal)
    definition = OPERATION_DEFINITIONS[operation.kind]
    return operation.model_copy(
        update={
            "targetType": definition.targetType
            if operation.targetType == "unknown"
            else operation.targetType,
            "primaryAgent": (
                operation.primaryAgent if preserve_primary else definition.primaryAgent
            ),
            "reviewers": list(definition.reviewers),
            "outputKind": definition.outputKind,
            "requiresArtifact": definition.requiresArtifact,
            "requiresUserApproval": definition.requiresUserApproval,
            "reasoning": operation.reasoning or definition.executionBrief,
        }
    )


def classify_by_explicit_keywords(message: str) -> CreativeOperation:
    rules = [
        (r"改写|重写|润色", "rewrite_scene"),
        (r"续写|写正文|生成.{0,4}正文|写一章", "write_chapter"),
        (r"章节计划|规划.{0,6}章节|Beat Plan", "plan_chapter"),
        (r"伏笔", "manage_foreshadowing"),
        (r"一致性|OOC|角色.{0,4}一致|逻辑断裂|检查.{0,12}冲突", "review_chapter"),
        (r"审核|评审|商业性|追读", "review_chapter"),
        (r"创建.{0,6}大纲|生成.{0,6}大纲", "create_outline"),
        (r"修改.{0,6}大纲|调整.{0,6}大纲", "revise_outline"),
        (r"创建.{0,6}设定|新建.{0,6}设定", "create_lore"),
        (r"修改.{0,6}设定|调整.{0,6}设定", "revise_lore"),
    ]
    for pattern, kind in rules:
        if re.search(pattern, message, re.IGNORECASE):
            definition = OPERATION_DEFINITIONS[kind]  # type: ignore[index]
            return CreativeOperation(
                kind=definition.kind,
                targetType=definition.targetType,
                userGoal=message,
                primaryAgent=definition.primaryAgent,
                reviewers=list(definition.reviewers),
                outputKind=definition.outputKind,
                requiresArtifact=definition.requiresArtifact,
                requiresUserApproval=definition.requiresUserApproval,
                confidence=0.78,
                reasoning="用户消息包含明确创作动作。",
            )
    return create_fallback_operation(message)
