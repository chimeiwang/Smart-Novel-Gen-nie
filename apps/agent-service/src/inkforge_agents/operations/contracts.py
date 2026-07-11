from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..definitions.agents import AgentId

CreativeOperationKind = Literal[
    "answer_question",
    "create_lore",
    "revise_lore",
    "create_outline",
    "revise_outline",
    "plan_chapter",
    "write_chapter",
    "rewrite_scene",
    "review_chapter",
    "sync_lore",
    "manage_foreshadowing",
]
TargetType = Literal[
    "novel",
    "chapter",
    "character",
    "lore",
    "outline",
    "foreshadowing",
    "scene",
    "artifact",
    "unknown",
]
OutputKind = Literal[
    "chat_answer",
    "lore_proposal",
    "outline_proposal",
    "beat_plan",
    "chapter_text",
    "review_report",
    "revision_brief",
    "sync_proposal",
]


class CreativeOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CreativeOperationKind
    targetType: TargetType
    targetId: str | None = None
    userGoal: str = Field(min_length=1)
    primaryAgent: AgentId
    reviewers: list[AgentId] = Field(default_factory=list)
    outputKind: OutputKind
    requiresArtifact: bool
    requiresUserApproval: bool
    confidence: float = Field(ge=0, le=1)
    reasoning: str


def create_fallback_operation(user_goal: str) -> CreativeOperation:
    return CreativeOperation(
        kind="answer_question",
        targetType="unknown",
        userGoal=user_goal.strip() or "继续对话",
        primaryAgent="编辑",
        reviewers=[],
        outputKind="chat_answer",
        requiresArtifact=False,
        requiresUserApproval=False,
        confidence=0.35,
        reasoning="无法稳定识别具体创作操作，回退为普通创作问答。",
    )


def create_default_operation_for_agent(
    agent_id: AgentId,
    user_goal: str,
    confidence: float = 0.72,
) -> CreativeOperation:
    from .definitions import OPERATION_DEFINITIONS

    kind_by_agent: dict[AgentId, CreativeOperationKind] = {
        "设定": "revise_lore",
        "剧情": "revise_outline",
        "写作": "write_chapter",
        "校验": "review_chapter",
        "编辑": "review_chapter",
    }
    definition = OPERATION_DEFINITIONS[kind_by_agent[agent_id]]
    return CreativeOperation(
        kind=definition.kind,
        targetType=definition.targetType,
        userGoal=user_goal.strip() or "继续处理当前创作请求",
        primaryAgent=agent_id,
        reviewers=list(definition.reviewers) if agent_id == definition.primaryAgent else [],
        outputKind=definition.outputKind,
        requiresArtifact=definition.requiresArtifact,
        requiresUserApproval=definition.requiresUserApproval,
        confidence=confidence,
        reasoning="用户使用智能体前缀，按该智能体的默认创作操作处理。",
    )
