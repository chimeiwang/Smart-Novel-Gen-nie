from __future__ import annotations

import hashlib
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

from .identity import Identifier
from .operations import (
    ExecutableCreativeOperationKind,
    PublicOperationDefinition,
)

ContentSha256 = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$"),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChapterTarget(StrictModel):
    type: Literal["chapter"]
    id: Identifier


class SelectionTarget(StrictModel):
    """客户端提交的不可变选区身份；正文由 Core 从权威源派生。"""

    resourceType: Literal[
        "chapter_content", "outline_content", "outline_node_content"
    ]
    resourceId: Identifier
    baseUpdatedAt: AwareDatetime
    baseContentHash: ContentSha256
    selectionStart: NonNegativeInt
    selectionEnd: NonNegativeInt
    selectedTextHash: ContentSha256

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.selectionStart >= self.selectionEnd:
            raise ValueError("选区结束位置必须大于开始位置")
        return self


class SelectionAttachmentMetadata(StrictModel):
    """选区来源快照的 UI 元数据；不包含也不承载权威正文。"""

    resourceType: Literal[
        "chapter_content", "outline_content", "outline_node_content"
    ]
    resourceId: Identifier
    sourceLabel: str = Field(min_length=1, max_length=256)
    baseUpdatedAt: AwareDatetime
    baseContentHash: ContentSha256
    selectionStart: NonNegativeInt
    selectionEnd: NonNegativeInt
    selectedTextHash: ContentSha256
    selectionPreview: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.selectionStart >= self.selectionEnd:
            raise ValueError("选区结束位置必须大于开始位置")
        return self


class SelectionSourceSnapshot(StrictModel):
    resourceType: Literal[
        "chapter_content", "outline_content", "outline_node_content"
    ]
    resourceId: Identifier
    content: str
    updatedAt: AwareDatetime
    contentSha256: ContentSha256


class SelectionSnapshot(StrictModel):
    resourceType: Literal[
        "chapter_content", "outline_content", "outline_node_content"
    ]
    resourceId: Identifier
    baseUpdatedAt: AwareDatetime
    baseContentHash: ContentSha256
    selectionStart: NonNegativeInt
    selectionEnd: NonNegativeInt
    selectedTextHash: ContentSha256
    selectedText: str
    contextBefore: str
    contextAfter: str
    sourceSnapshot: SelectionSourceSnapshot

    @model_validator(mode="after")
    def validate_snapshot_integrity(self) -> Self:
        if self.selectionStart >= self.selectionEnd:
            raise ValueError("选区快照范围必须为非空开区间")
        source = self.sourceSnapshot
        if (
            source.resourceType != self.resourceType
            or source.resourceId != self.resourceId
            or source.updatedAt != self.baseUpdatedAt
            or source.contentSha256 != self.baseContentHash
        ):
            raise ValueError("选区快照与来源快照身份或版本不一致")
        if hashlib.sha256(source.content.encode("utf-8")).hexdigest() != self.baseContentHash:
            raise ValueError("来源快照全文 hash 不一致")
        if hashlib.sha256(self.selectedText.encode("utf-8")).hexdigest() != self.selectedTextHash:
            raise ValueError("选区快照 selectedText hash 不一致")
        if self.selectionEnd > len(source.content):
            raise ValueError("选区快照范围超出来源正文")
        if source.content[self.selectionStart : self.selectionEnd] != self.selectedText:
            raise ValueError("选区快照正文与来源正文不一致")
        expected_before = source.content[
            max(0, self.selectionStart - 1000) : self.selectionStart
        ]
        if self.contextBefore != expected_before:
            raise ValueError("选区快照前文上下文不一致")
        expected_after = source.content[
            self.selectionEnd : min(len(source.content), self.selectionEnd + 1000)
        ]
        if self.contextAfter != expected_after:
            raise ValueError("选区快照后文上下文不一致")
        return self


class ChapterScope(StrictModel):
    kind: Literal["chapter"]
    chapterId: Identifier


class ChapterRangeScope(StrictModel):
    kind: Literal["chapter_range"]
    chapterStartOrder: NonNegativeInt
    chapterEndOrder: NonNegativeInt

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.chapterStartOrder > self.chapterEndOrder:
            raise ValueError("章节范围起点不能晚于终点")
        return self


class OutlineNodeScope(StrictModel):
    kind: Literal["outline_node"]
    outlineNodeId: Identifier


class NovelScope(StrictModel):
    kind: Literal["novel"]


LongSerialScope = Annotated[
    ChapterScope | ChapterRangeScope | OutlineNodeScope | NovelScope,
    Field(discriminator="kind"),
]


class AbsenceSentinel(StrictModel):
    resourceType: Identifier
    resourceId: Identifier


class SourceBinding(StrictModel):
    resourceType: Identifier
    resourceId: Identifier
    exists: bool
    updatedAt: AwareDatetime | None
    contentSha256: ContentSha256 | None
    revision: NonNegativeInt | None
    absenceSentinel: AbsenceSentinel | None

    @model_validator(mode="after")
    def validate_version_shape(self) -> Self:
        if self.exists:
            if self.updatedAt is None or self.contentSha256 is None:
                raise ValueError("存在的来源必须包含 updatedAt 和 contentSha256")
            if self.absenceSentinel is not None:
                raise ValueError("存在的来源不能包含 absenceSentinel")
        else:
            if any(
                value is not None
                for value in (self.updatedAt, self.contentSha256, self.revision)
            ):
                raise ValueError("不存在的来源不能包含版本或内容摘要")
            if self.absenceSentinel is None:
                raise ValueError("不存在的来源必须包含 absenceSentinel")
        return self


class LongSerialResumeInput(StrictModel):
    userMessage: str | None = None
    artifactId: Identifier | None = None
    decision: Literal["approve", "discard", "revise"] | None = None

    @model_validator(mode="after")
    def validate_artifact_decision(self) -> Self:
        if (self.artifactId is None) != (self.decision is None):
            raise ValueError("草案决定恢复输入必须同时包含 artifactId 和 decision")
        return self


class LongSerialRunBase(StrictModel):
    version: Literal[1]
    workflow: Literal["long_serial"]
    chapterId: Identifier
    writingSessionId: Identifier | None
    operation: ExecutableCreativeOperationKind
    target: ChapterTarget
    scope: LongSerialScope
    selectionTarget: SelectionTarget | None = None
    selectionSnapshot: SelectionSnapshot | None = None
    sourceBindings: tuple[SourceBinding, ...] = Field(min_length=1)
    targetWordCount: int = Field(ge=1, le=10_000_000)
    userInstruction: str = Field(min_length=1)

    @field_validator("userInstruction")
    @classmethod
    def validate_user_instruction(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("用户要求不能为空白")
        return value

    @model_validator(mode="after")
    def validate_selection_target(self) -> Self:
        selection_operations = {
            "rewrite_chapter_selection",
            "rewrite_outline_selection",
        }
        if self.operation in selection_operations and self.selectionTarget is None:
            raise ValueError("选区操作必须携带 selectionTarget")
        if self.operation in selection_operations and self.selectionSnapshot is not None:
            if self.selectionTarget is None or (
                self.selectionSnapshot.resourceType != self.selectionTarget.resourceType
                or self.selectionSnapshot.resourceId != self.selectionTarget.resourceId
                or self.selectionSnapshot.baseUpdatedAt != self.selectionTarget.baseUpdatedAt
                or self.selectionSnapshot.baseContentHash != self.selectionTarget.baseContentHash
                or self.selectionSnapshot.selectionStart != self.selectionTarget.selectionStart
                or self.selectionSnapshot.selectionEnd != self.selectionTarget.selectionEnd
                or self.selectionSnapshot.selectedTextHash != self.selectionTarget.selectedTextHash
            ):
                raise ValueError("选区快照必须继承 selectionTarget 身份")
        if self.operation in selection_operations and self.selectionSnapshot is None:
            # 启动请求在 Core 校验前可以暂不携带快照；Core 生成 job 时会补齐。
            pass
        if self.operation not in selection_operations and self.selectionSnapshot is not None:
            raise ValueError("普通长篇操作不能携带 selectionSnapshot")
        if self.operation not in selection_operations and self.selectionTarget is not None:
            raise ValueError("普通长篇操作不能携带 selectionTarget")
        if self.operation == "rewrite_chapter_selection" and (
            self.selectionTarget is not None
            and self.selectionTarget.resourceType != "chapter_content"
        ):
            raise ValueError("章节选区操作只能指向章节正文")
        if self.operation == "rewrite_outline_selection" and (
            self.selectionTarget is not None
            and self.selectionTarget.resourceType
            not in {"outline_content", "outline_node_content"}
        ):
            raise ValueError("大纲选区操作只能指向总纲或大纲节点正文")
        return self


class StartLongSerialRunPayload(LongSerialRunBase):
    resume: Literal[False]
    resumeInput: None


class ResumeLongSerialRunPayload(LongSerialRunBase):
    resume: Literal[True]
    resumeInput: LongSerialResumeInput


LongSerialRunPayload = Annotated[
    StartLongSerialRunPayload | ResumeLongSerialRunPayload,
    Field(discriminator="resume"),
]

LONG_SERIAL_RUN_PAYLOAD_ADAPTER: TypeAdapter[LongSerialRunPayload] = TypeAdapter(
    LongSerialRunPayload
)

PUBLIC_LONG_SERIAL_OPERATIONS: dict[str, PublicOperationDefinition] = {
    "answer_question": PublicOperationDefinition(
        operation="answer_question",
        workflow="long_serial",
        targetKind="chapter",
        allowedScopeKinds=("chapter",),
        mutating=False,
        principalAgent="编辑",
        reviewers=(),
        artifactKind=None,
    ),
    "plan_chapter": PublicOperationDefinition(
        operation="plan_chapter",
        workflow="long_serial",
        targetKind="chapter",
        allowedScopeKinds=("chapter",),
        mutating=True,
        principalAgent="剧情",
        reviewers=("编辑",),
        artifactKind="beat_plan",
    ),
    "rewrite_scene": PublicOperationDefinition(
        operation="rewrite_scene",
        workflow="long_serial",
        targetKind="chapter",
        allowedScopeKinds=("chapter",),
        mutating=True,
        principalAgent="写作",
        reviewers=("校验", "编辑"),
        artifactKind="chapter_draft",
    ),
    "rewrite_chapter_selection": PublicOperationDefinition(
        operation="rewrite_chapter_selection",
        workflow="long_serial",
        targetKind="chapter",
        allowedScopeKinds=("chapter",),
        mutating=True,
        principalAgent="写作",
        reviewers=("校验", "编辑"),
        artifactKind="chapter_draft",
    ),
    "rewrite_outline_selection": PublicOperationDefinition(
        operation="rewrite_outline_selection",
        workflow="long_serial",
        targetKind="chapter",
        allowedScopeKinds=("novel", "outline_node"),
        mutating=True,
        principalAgent="剧情",
        reviewers=("编辑",),
        artifactKind="outline_draft",
    ),
    "write_chapter": PublicOperationDefinition(
        operation="write_chapter",
        workflow="long_serial",
        targetKind="chapter",
        allowedScopeKinds=("chapter",),
        mutating=True,
        principalAgent="写作",
        reviewers=("校验", "编辑"),
        artifactKind="chapter_draft",
    ),
    "review_chapter": PublicOperationDefinition(
        operation="review_chapter",
        workflow="long_serial",
        targetKind="chapter",
        allowedScopeKinds=("chapter",),
        mutating=False,
        principalAgent="编辑",
        reviewers=(),
        artifactKind=None,
    ),
}
