from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

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
    createdAt: datetime
    updatedAt: datetime


class ArtifactSelectionRef(ReviewSchema):
    section: str = Field(min_length=1, max_length=100)
    index: int | None = Field(default=None, ge=0)


class ReviewArtifactDecisionRequest(ReviewSchema):
    clientRequestId: str = Field(min_length=16, max_length=128)
    decision: Literal["approve", "discard", "revise"]
    editedContent: str | None = None
    selectedUpdateRefs: list[ArtifactSelectionRef] | None = None
    userMessage: str | None = None


class ArtifactDecisionResponse(ReviewSchema):
    artifactId: str
    decision: Literal["approve", "discard", "revise"]
    savedCount: int = 0
    deleted: bool = False


class ArtifactDecisionAcceptedResponse(ReviewSchema):
    artifactId: str
    taskId: str
    commandId: str
    decision: Literal["approve", "discard", "revise"]
    status: Literal["pending", "submitted", "processing", "succeeded", "failed"]
    savedCount: int = 0
    deleted: bool = False


class CreateArtifactRequest(ReviewSchema):
    runId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
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

    @model_validator(mode="after")
    def validate_payload_kind(self) -> CreateArtifactRequest:
        if self.payload.get("kind") != self.kind:
            raise ValueError("草案 kind 必须与 payload.kind 一致")
        return self


class SubmitArtifactEvaluationRequest(ReviewSchema):
    runId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
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
