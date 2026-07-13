# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..definitions.agents import AgentId
from .contracts import CreativeOperationKind, OutputKind, TargetType

ContextStrategy = Literal["brief", "lore", "outline", "chapter", "review"]
ArtifactPolicy = Literal["none", "agent_updates", "text"]


@dataclass(frozen=True, slots=True)
class OperationDefinition:
    kind: CreativeOperationKind
    label: str
    targetType: TargetType
    primaryAgent: AgentId
    reviewers: tuple[AgentId, ...]
    outputKind: OutputKind
    contextStrategy: ContextStrategy
    artifactPolicy: ArtifactPolicy
    requiresArtifact: bool
    requiresUserApproval: bool
    executionBrief: str
    textArtifactKind: str | None = None


def _definition(
    kind: CreativeOperationKind,
    label: str,
    target: TargetType,
    agent: AgentId,
    reviewers: tuple[AgentId, ...],
    output: OutputKind,
    context: ContextStrategy,
    policy: ArtifactPolicy,
    brief: str,
    text_kind: str | None = None,
) -> OperationDefinition:
    requires_artifact = policy != "none"
    return OperationDefinition(
        kind=kind,
        label=label,
        targetType=target,
        primaryAgent=agent,
        reviewers=reviewers,
        outputKind=output,
        contextStrategy=context,
        artifactPolicy=policy,
        requiresArtifact=requires_artifact,
        requiresUserApproval=requires_artifact,
        executionBrief=brief,
        textArtifactKind=text_kind,
    )


OPERATION_DEFINITIONS: dict[CreativeOperationKind, OperationDefinition] = {
    "answer_question": _definition(
        "answer_question",
        "回答问题",
        "unknown",
        "编辑",
        (),
        "chat_answer",
        "brief",
        "none",
        "直接回答用户问题，不生成待审核草案。",
    ),
    "create_lore": _definition(
        "create_lore",
        "新建设定",
        "lore",
        "设定",
        ("校验",),
        "lore_proposal",
        "lore",
        "agent_updates",
        "生成可审核的设定新增草案。",
    ),
    "revise_lore": _definition(
        "revise_lore",
        "修改设定",
        "lore",
        "设定",
        ("校验",),
        "lore_proposal",
        "lore",
        "agent_updates",
        "生成可审核的设定修改草案。",
    ),
    "create_outline": _definition(
        "create_outline",
        "创建大纲",
        "outline",
        "剧情",
        ("编辑",),
        "outline_proposal",
        "outline",
        "agent_updates",
        "生成可审核的结构化大纲草案。",
    ),
    "revise_outline": _definition(
        "revise_outline",
        "修改大纲",
        "outline",
        "剧情",
        ("编辑",),
        "outline_proposal",
        "outline",
        "agent_updates",
        "生成可审核的大纲修改草案。",
    ),
    "plan_chapter": _definition(
        "plan_chapter",
        "规划章节",
        "chapter",
        "剧情",
        ("编辑",),
        "beat_plan",
        "outline",
        "text",
        "生成可审核的章节规划草案。",
        "beat_plan_draft",
    ),
    "write_chapter": _definition(
        "write_chapter",
        "生成正文草案",
        "chapter",
        "写作",
        ("校验", "编辑"),
        "chapter_text",
        "chapter",
        "text",
        "生成正文草案，不直接写入章节。",
        "chapter_draft",
    ),
    "rewrite_scene": _definition(
        "rewrite_scene",
        "改写场景草案",
        "scene",
        "写作",
        ("校验", "编辑"),
        "chapter_text",
        "chapter",
        "text",
        "生成场景改写草案。",
        "chapter_draft",
    ),
    "review_chapter": _definition(
        "review_chapter",
        "审核章节",
        "chapter",
        "编辑",
        (),
        "review_report",
        "review",
        "none",
        "生成章节审核报告。",
    ),
    "manage_foreshadowing": _definition(
        "manage_foreshadowing",
        "管理伏笔",
        "foreshadowing",
        "剧情",
        ("校验",),
        "outline_proposal",
        "outline",
        "agent_updates",
        "生成伏笔新增、推进、回收或废弃草案。",
    ),
}
