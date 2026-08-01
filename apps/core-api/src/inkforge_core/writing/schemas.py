from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

CoreAgentId = Literal["设定", "剧情", "写作", "校验", "编辑"]
WritingCommandStatus = Literal[
    "pending", "submitted", "processing", "succeeded", "failed"
]


def _default_agents() -> list[CoreAgentId]:
    return ["设定", "剧情", "写作", "校验", "编辑"]


class WritingSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CreateWritingSessionRequest(WritingSchema):
    novelId: str = Field(min_length=1, max_length=256)
    chapterId: str = Field(min_length=1, max_length=256)
    title: str | None = Field(default=None, min_length=1, max_length=500)


class UpdateWritingSessionRequest(WritingSchema):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    phase: Literal["idle", "discussing", "generating", "recording", "completed"] | None = None


class CreateMessageRequest(WritingSchema):
    role: Literal["user", "agent", "system"]
    agentId: str | None = Field(default=None, min_length=1, max_length=64)
    content: str = Field(min_length=1)
    intent: str | None = Field(default=None, min_length=1, max_length=256)
    metadata: JsonValue | None = None
    parentId: str | None = Field(default=None, min_length=1, max_length=256)


class MessageResponse(WritingSchema):
    id: str
    sessionId: str
    role: str
    agentId: str | None
    content: str
    intent: str | None
    metadata: JsonValue | None
    parentId: str | None
    createdAt: datetime


class LastMessageResponse(WritingSchema):
    content: str
    role: str
    agentId: str | None


class WritingSessionResponse(WritingSchema):
    id: str
    novelId: str
    chapterId: str
    title: str | None
    phase: str
    createdAt: datetime
    updatedAt: datetime


class WritingSessionListItem(WritingSessionResponse):
    messageCount: int
    lastMessage: LastMessageResponse | None


class WritingTaskSummary(WritingSchema):
    id: str
    phase: str
    updatedAt: datetime
    hasAwaitingReviewArtifact: bool
    currentOperation: dict[str, JsonValue] | None
    operationStage: str | None
    activeArtifactId: str | None


class SessionRecoveryState(WritingSchema):
    currentTask: WritingTaskSummary | None
    lastTask: WritingTaskSummary | None


class WritingSessionDetail(WritingSessionResponse, SessionRecoveryState):
    messages: list[MessageResponse]


class DeleteWritingSessionResponse(WritingSchema):
    success: Literal[True]


class StartWritingRunRequest(WritingSchema):
    clientRequestId: str = Field(min_length=16, max_length=128)
    novelId: str = Field(min_length=1, max_length=256)
    chapterId: str = Field(min_length=1, max_length=256)
    writingSessionId: str | None = Field(default=None, min_length=1, max_length=256)
    targetWordCount: int = Field(default=4000, ge=1, le=10_000_000)
    selectedAgents: list[CoreAgentId] = Field(default_factory=_default_agents)
    userMessage: str = Field(min_length=1)


class ShortMediumStartWritingRunRequest(WritingSchema):
    clientRequestId: str = Field(min_length=16, max_length=128)
    workflow: Literal["short_medium"]
    novelId: str = Field(min_length=1, max_length=256)
    operation: Literal[
        "generate_outline",
        "generate_manuscript",
        "replace_selection",
        "full_check",
    ]
    documentType: Literal["outline", "manuscript"]
    chapterId: str | None = Field(default=None, min_length=1, max_length=256)
    baseVersionId: str | None = Field(default=None, min_length=1, max_length=256)
    sourceOutlineVersionId: str | None = Field(
        default=None, min_length=1, max_length=256
    )
    selectionStart: int | None = Field(default=None, ge=0)
    selectionEnd: int | None = Field(default=None, ge=0)
    selectedTextHash: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    userInstruction: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_operation_identity(self) -> Self:
        selection_values = (
            self.selectionStart,
            self.selectionEnd,
            self.selectedTextHash,
        )
        if self.documentType == "manuscript" and self.chapterId is None:
            raise ValueError("正文操作必须绑定全文章节")
        if self.documentType == "outline" and self.chapterId is not None:
            raise ValueError("大纲操作不能绑定章节")
        if self.operation == "generate_outline":
            if (
                self.documentType != "outline"
                or self.sourceOutlineVersionId is not None
                or any(value is not None for value in selection_values)
            ):
                raise ValueError("生成大纲的文档身份无效")
            return self
        if self.operation == "generate_manuscript":
            if (
                self.documentType != "manuscript"
                or self.sourceOutlineVersionId is None
                or any(value is not None for value in selection_values)
            ):
                raise ValueError("生成正文必须绑定当前来源大纲版本")
            return self
        if self.operation == "replace_selection":
            if (
                self.baseVersionId is None
                or self.userInstruction is None
                or any(value is None for value in selection_values)
            ):
                raise ValueError("选区修改必须携带基础版本、码点范围、选区 hash 和要求")
            if (
                self.selectionStart is not None
                and self.selectionEnd is not None
                and self.selectionStart >= self.selectionEnd
            ):
                raise ValueError("选区结束位置必须大于开始位置")
            return self
        if (
            self.documentType != "manuscript"
            or self.baseVersionId is None
            or any(value is not None for value in selection_values)
        ):
            raise ValueError("全文检查必须绑定正文版本且不能携带选区")
        return self


type WritingRunStartRequest = StartWritingRunRequest | ShortMediumStartWritingRunRequest


class ResumeWritingRunRequest(WritingSchema):
    clientRequestId: str = Field(min_length=16, max_length=128)
    writingSessionId: str | None = Field(default=None, min_length=1, max_length=256)
    userMessage: str | None = None
    artifactId: str | None = Field(default=None, min_length=1, max_length=256)
    decision: Literal["approve", "discard", "revise"] | None = None


class WritingRunResponse(WritingSchema):
    id: str
    novelId: str
    chapterId: str
    writingSessionId: str | None
    phase: str
    targetWordCount: int
    selectedAgents: list[str]
    createdAt: datetime
    updatedAt: datetime
    commandId: str
    commandStatus: WritingCommandStatus


class ResumeWritingRunResponse(WritingSchema):
    accepted: Literal[True]
    taskId: str
    commandId: str
    commandStatus: WritingCommandStatus


class WritingRunOutcomeCommand(WritingSchema):
    id: str
    kind: str
    status: WritingCommandStatus
    updatedAt: datetime


class WritingRunOutcomeResult(WritingSchema):
    kind: Literal[
        "none",
        "review_artifact",
        "short_candidate",
        "check_report",
        "final_message",
    ]
    ready: bool
    id: str | None = None


class WritingRunOutcome(WritingSchema):
    state: Literal[
        "queued",
        "running",
        "waiting_user",
        "succeeded",
        "failed",
        "inconsistent",
    ]
    code: str
    taskTerminal: bool
    streamShouldClose: bool
    reconciliationRequired: bool
    currentCommand: WritingRunOutcomeCommand | None
    result: WritingRunOutcomeResult
    observedAt: datetime


class WritingRunStatusResponse(WritingSchema):
    taskId: str
    novelId: str
    chapterId: str
    phase: str
    updatedAt: datetime
    commandId: str | None
    commandStatus: WritingCommandStatus | None
    operation: Literal[
        "generate_outline",
        "generate_manuscript",
        "replace_selection",
        "full_check",
    ] | None
    candidateVersionId: str | None
    checkReport: dict[str, JsonValue] | None
    error: dict[str, JsonValue] | None
    outcome: WritingRunOutcome
