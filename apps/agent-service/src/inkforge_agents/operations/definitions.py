# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..definitions.agents import AgentId
from .contracts import CreativeOperationKind, OutputKind, TargetType

ContextStrategy = Literal[
    "brief",
    "lore",
    "outline",
    "chapter",
    "review",
    "short_outline",
    "short_story",
]
ArtifactPolicy = Literal["none", "agent_updates", "text"]
ArtifactKeyPolicy = Literal[
    "none", "generated_stable", "builder_or_generated", "preserve"
]

NOVEL_READ = frozenset({"get_novel_info", "list_available_data"})
CHARACTER_READ = frozenset(
    {"list_characters_summary", "get_character_detail", "get_character_list"}
)
LORE_READ = frozenset(
    {
        "list_factions_summary",
        "get_faction_detail",
        "list_locations_summary",
        "get_location_detail",
        "list_items_summary",
        "get_item_detail",
        "list_glossaries_summary",
        "get_glossary_detail",
        "search_lore",
        "find_similar_lore",
        "semantic_search_references",
    }
)
PLOT_READ = frozenset(
    {
        "list_outline_summary",
        "get_outline_node",
        "get_plot_progress",
        "list_foreshadowings_summary",
        "get_foreshadowing_detail",
        "get_recent_chapters",
    }
)
STYLE_READ = frozenset({"get_style_profile"})
LORE_PROPOSALS = frozenset(
    {"propose_update_character", "propose_update_character_status"}
)
OUTLINE_PROPOSALS = frozenset({"propose_update_outline"})
FORESHADOW_PROPOSALS = frozenset(
    {"propose_add_foreshadowing", "propose_resolve_foreshadowing"}
)
COMMON_BUILDER_TOOLS = frozenset(
    {
        "propose_updates",
        "start_update_builder",
        "append_update_batch",
        "put_update_text_block",
        "put_update_item_text_block",
        "put_update_item_text_blocks",
        "finish_update_builder",
    }
)
OUTLINE_BUILDER_TOOLS = COMMON_BUILDER_TOOLS | {"append_outline_tree"}

_BASE_READ = NOVEL_READ | CHARACTER_READ | LORE_READ | PLOT_READ
_EDITOR_READ = NOVEL_READ | CHARACTER_READ | PLOT_READ | STYLE_READ
_STRUCTURED_TERMINALS = frozenset({"propose_updates", "finish_update_builder"})


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
    allowedToolNames: frozenset[str] = frozenset()
    terminalControlTools: frozenset[str] = frozenset()
    artifactEventTypes: frozenset[str] = frozenset()
    artifactKeyPolicy: ArtifactKeyPolicy = "none"

    def __post_init__(self) -> None:
        for field_name in (
            "allowedToolNames",
            "terminalControlTools",
            "artifactEventTypes",
        ):
            object.__setattr__(self, field_name, frozenset(getattr(self, field_name)))
        if self.requiresArtifact != (self.artifactPolicy != "none"):
            raise ValueError("requiresArtifact 与 artifactPolicy 不一致")
        if (self.textArtifactKind is not None) != (self.artifactPolicy == "text"):
            raise ValueError("textArtifactKind 与文本产物策略不一致")
        if not self.terminalControlTools <= self.allowedToolNames:
            raise ValueError("Operation 终止工具必须属于允许工具")
        if self.requiresArtifact:
            if not self.artifactEventTypes:
                raise ValueError("产物 Operation 必须声明产物事件")
            if self.artifactKeyPolicy == "none":
                raise ValueError("产物 Operation 必须声明 artifactKey 策略")
        elif (
            self.artifactEventTypes
            or self.terminalControlTools
            or self.artifactKeyPolicy != "none"
        ):
            raise ValueError("无产物 Operation 不得声明产物执行契约")


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
    *,
    allowed_tools: frozenset[str],
    terminal_tools: frozenset[str] = frozenset(),
    artifact_events: frozenset[str] = frozenset(),
    artifact_key_policy: ArtifactKeyPolicy = "none",
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
        allowedToolNames=allowed_tools,
        terminalControlTools=terminal_tools,
        artifactEventTypes=artifact_events,
        artifactKeyPolicy=artifact_key_policy,
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
        allowed_tools=_EDITOR_READ,
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
        allowed_tools=_BASE_READ | LORE_PROPOSALS | COMMON_BUILDER_TOOLS,
        terminal_tools=_STRUCTURED_TERMINALS,
        artifact_events=_STRUCTURED_TERMINALS,
        artifact_key_policy="builder_or_generated",
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
        allowed_tools=_BASE_READ | LORE_PROPOSALS | COMMON_BUILDER_TOOLS,
        terminal_tools=_STRUCTURED_TERMINALS,
        artifact_events=_STRUCTURED_TERMINALS,
        artifact_key_policy="builder_or_generated",
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
        allowed_tools=_BASE_READ | OUTLINE_PROPOSALS | OUTLINE_BUILDER_TOOLS,
        terminal_tools=_STRUCTURED_TERMINALS,
        artifact_events=_STRUCTURED_TERMINALS,
        artifact_key_policy="builder_or_generated",
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
        allowed_tools=_BASE_READ | OUTLINE_PROPOSALS | OUTLINE_BUILDER_TOOLS,
        terminal_tools=_STRUCTURED_TERMINALS,
        artifact_events=_STRUCTURED_TERMINALS,
        artifact_key_policy="builder_or_generated",
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
        "beat_plan",
        allowed_tools=_BASE_READ | {"submit_beat_plan"},
        terminal_tools=frozenset({"submit_beat_plan"}),
        artifact_events=frozenset({"submit_beat_plan"}),
        artifact_key_policy="generated_stable",
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
        allowed_tools=_BASE_READ | STYLE_READ | {"begin_artifact_output"},
        terminal_tools=frozenset({"begin_artifact_output"}),
        artifact_events=frozenset({"begin_artifact_output"}),
        artifact_key_policy="generated_stable",
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
        allowed_tools=_BASE_READ | STYLE_READ | {"begin_artifact_output"},
        terminal_tools=frozenset({"begin_artifact_output"}),
        artifact_events=frozenset({"begin_artifact_output"}),
        artifact_key_policy="generated_stable",
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
        allowed_tools=_EDITOR_READ,
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
        allowed_tools=_BASE_READ | FORESHADOW_PROPOSALS | OUTLINE_BUILDER_TOOLS,
        terminal_tools=_STRUCTURED_TERMINALS,
        artifact_events=_STRUCTURED_TERMINALS,
        artifact_key_policy="builder_or_generated",
    ),
    "develop_short_outline": _definition(
        "develop_short_outline",
        "生成或修改中短篇大纲",
        "outline",
        "剧情",
        (),
        "outline_proposal",
        "short_outline",
        "none",
        "根据 Core 权威中短篇上下文生成或修改完整大纲；不得回退为长篇大纲。",
        allowed_tools=_BASE_READ,
    ),
    "write_short_story": _definition(
        "write_short_story",
        "生成或修改中短篇整稿",
        "chapter",
        "写作",
        (),
        "chapter_text",
        "short_story",
        "none",
        "中短篇整稿能力由专用串行审核工作流执行，不能复用长篇逐章写作。",
        allowed_tools=frozenset(),
    ),
}
