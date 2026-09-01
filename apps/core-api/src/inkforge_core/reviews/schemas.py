from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from inkforge_contracts.long_serial import SourceBinding
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, model_validator

from ..writing.schemas import WritingRunV2Response

ArtifactStatus = Literal["draft", "under_review", "awaiting_user", "applying", "applied"]
ArtifactKind = Literal[
    "agent_updates",
    "outline_draft",
    "chapter_draft",
    "lore_draft",
    "revision_brief",
    "beat_plan_draft",
    "chapter_content",
    "beat_plan",
    "freeform_markdown",
]
EvaluationVerdict = Literal["pass", "revise", "block"]
SourceBindingStatus = Literal["verified", "legacy_missing", "not_yet_supported"]

STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"draft", "under_review", "awaiting_user"}),
    "under_review": frozenset({"under_review", "draft", "awaiting_user"}),
    "awaiting_user": frozenset({"awaiting_user", "draft", "under_review", "applying"}),
    "applying": frozenset({"applying", "awaiting_user", "applied"}),
    "applied": frozenset({"applied"}),
}


def assert_status_transition(current: str, target: str) -> None:
    if target not in STATUS_TRANSITIONS.get(current, frozenset()):
        raise ValueError(f"待审核草案不能从 {current} 流转到 {target}")


class ReviewSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ArtifactEvaluationResponse(ReviewSchema):
    id: str
    artifactId: str
    revision: int
    evaluatorAgent: str
    verdict: EvaluationVerdict
    summary: str
    requiredChanges: str | None
    createdAt: datetime


class ReviewArtifactResponse(ReviewSchema):
    engineVersion: Literal[1, 2]
    id: str
    novelId: str
    chapterId: str | None
    taskId: str | None
    workflowRunId: str | None
    artifactKey: str | None
    kind: ArtifactKind
    status: ArtifactStatus
    title: str | None
    summary: str | None
    payload: dict[str, JsonValue]
    diff: JsonValue | None
    createdByAgent: str | None
    updatedByAgent: str | None
    reviewerAgent: str | None
    revision: int
    evaluations: list[ArtifactEvaluationResponse] = Field(default_factory=list)
    sourceBindings: list[SourceBinding] | None
    sourceBindingStatus: SourceBindingStatus
    createdAt: datetime
    updatedAt: datetime


class ReviewArtifactSummaryResponse(ReviewSchema):
    """集合查询使用的有界索引；完整内容必须按精确 revision 单独读取。"""

    engineVersion: Literal[1, 2]
    id: str
    novelId: str
    chapterId: str | None
    taskId: str | None
    workflowRunId: str | None
    artifactKey: str | None
    kind: ArtifactKind
    status: ArtifactStatus
    title: str | None
    summary: str | None
    revision: int
    actionable: bool
    createdAt: datetime
    updatedAt: datetime


class ReviewArtifactListResponse(ReviewSchema):
    items: list[ReviewArtifactResponse]
    nextCursor: str | None


class ReviewArtifactSummaryListResponse(ReviewSchema):
    items: list[ReviewArtifactSummaryResponse]
    nextCursor: str | None


class ArtifactSelectionRef(ReviewSchema):
    section: str = Field(min_length=1, max_length=100)
    index: int | None = Field(default=None, ge=0)


class ReviewArtifactDecisionRequest(ReviewSchema):
    engineVersion: Literal[1, 2] = Field(
        default=1,
        description=(
            "审核决定引擎版本；省略只兼容解释为 V1，V2 必须显式提交 2"
        ),
    )
    clientRequestId: str = Field(min_length=16, max_length=128)
    expectedRevision: StrictInt = Field(
        ge=1,
        description=(
            "V1 为既有草案修订号；V2 为规范 expectedArtifactRevision wire 字段"
        ),
    )
    decision: Literal["approve", "discard", "revise"]
    editedContent: str | None = None
    editedReplacement: str | None = None
    selectedUpdateRefs: list[ArtifactSelectionRef] | None = None
    userMessage: str | None = None

    @model_validator(mode="after")
    def validate_v2_decision_shape(self) -> Self:
        if self.engineVersion != 2:
            return self
        if self.editedContent is not None or self.selectedUpdateRefs is not None:
            raise ValueError("V2 章节选区决定只允许提交 editedReplacement")
        if self.decision == "approve":
            if (
                self.editedReplacement is not None
                and not self.editedReplacement.strip()
            ):
                raise ValueError("V2 editedReplacement 不能为空白")
            return self
        if self.editedReplacement is not None:
            raise ValueError("只有 V2 approve 可以提交 editedReplacement")
        if self.decision == "revise" and (
            self.userMessage is None or not self.userMessage.strip()
        ):
            raise ValueError("V2 revise 必须携带非空白 userMessage")
        return self


class ArtifactDecisionResponse(ReviewSchema):
    artifactId: str
    decision: Literal["approve", "discard", "revise"]
    savedCount: int = 0
    deleted: bool = False


class ArtifactDecisionAcceptedResponse(ReviewSchema):
    engineVersion: Literal[1] = 1
    artifactId: str
    taskId: str
    commandId: str
    decision: Literal["approve", "discard", "revise"]
    status: Literal["pending", "submitted", "processing", "succeeded", "failed"]
    savedCount: int = 0
    deleted: bool = False


type ArtifactDecisionPublicResponse = Annotated[
    ArtifactDecisionAcceptedResponse | WritingRunV2Response,
    Field(discriminator="engineVersion"),
]


class ArtifactConflictQuarantineRequest(ReviewSchema):
    runId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
    jobId: str = Field(min_length=1, max_length=256)


class ArtifactConflictQuarantineResponse(ReviewSchema):
    artifactId: str
    status: Literal["awaiting_user"]
    revision: StrictInt = Field(ge=1)


class CreateArtifactRequest(ReviewSchema):
    runId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
    jobId: str = Field(min_length=1, max_length=256)
    chapterId: str | None = Field(default=None, min_length=1, max_length=256)
    workflowRunId: str | None = Field(default=None, min_length=1, max_length=256)
    artifactKey: str | None = Field(default=None, min_length=1, max_length=500)
    kind: ArtifactKind
    status: Literal["draft", "under_review", "awaiting_user"]
    title: str | None = None
    summary: str | None = None
    payload: dict[str, JsonValue]
    diff: JsonValue | None = None
    createdByAgent: Literal["设定", "剧情", "写作", "校验", "编辑"]
    reviewerAgent: Literal["设定", "剧情", "写作", "校验", "编辑"] | None = None
    expectedRevision: StrictInt | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_payload_kind(self) -> CreateArtifactRequest:
        if self.payload.get("kind") != self.kind:
            raise ValueError("草案 kind 必须与 payload.kind 一致")
        if "_inkforgeControl" in self.payload:
            raise ValueError("草案 payload 不得包含保留控制字段")
        return self


class SubmitArtifactEvaluationRequest(ReviewSchema):
    runId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
    jobId: str = Field(min_length=1, max_length=256)
    revision: int = Field(ge=1)
    evaluatorAgent: Literal["设定", "剧情", "写作", "校验", "编辑"]
    verdict: EvaluationVerdict
    summary: str = Field(min_length=1)
    requiredChanges: str | None = None

    @model_validator(mode="after")
    def validate_required_changes(self) -> SubmitArtifactEvaluationRequest:
        if self.verdict == "revise" and not self.requiredChanges:
            raise ValueError("要求修改时必须提供 requiredChanges")
        return self
