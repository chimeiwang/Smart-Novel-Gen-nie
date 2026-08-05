from typing import Literal

from pydantic import BaseModel, ConfigDict

from .identity import CoreAgentId

HistoricalCreativeOperationKind = Literal[
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

ExecutableCreativeOperationKind = Literal[
    "answer_question",
    "create_lore",
    "revise_lore",
    "create_outline",
    "revise_outline",
    "plan_chapter",
    "write_chapter",
    "rewrite_scene",
    "review_chapter",
    "manage_foreshadowing",
]

# 兼容既有公共导入；历史任务仍需解析 sync_lore。
CreativeOperationKind = HistoricalCreativeOperationKind

LongSerialScopeKind = Literal[
    "chapter",
    "chapter_range",
    "outline_node",
    "novel",
]


class PublicOperationDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: ExecutableCreativeOperationKind
    workflow: Literal["long_serial"]
    targetKind: Literal["chapter"]
    allowedScopeKinds: tuple[LongSerialScopeKind, ...]
    mutating: bool
    principalAgent: CoreAgentId
    reviewers: tuple[CoreAgentId, ...]
    artifactKind: Literal["beat_plan", "chapter_draft"] | None
