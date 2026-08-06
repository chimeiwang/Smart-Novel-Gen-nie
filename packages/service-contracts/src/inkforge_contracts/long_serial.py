from __future__ import annotations

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
    sourceBindings: tuple[SourceBinding, ...] = Field(min_length=1)
    targetWordCount: int = Field(ge=1, le=10_000_000)
    userInstruction: str = Field(min_length=1)

    @field_validator("userInstruction")
    @classmethod
    def validate_user_instruction(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("用户要求不能为空白")
        return value


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
