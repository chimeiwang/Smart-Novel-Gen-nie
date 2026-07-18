from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from inkforge_contracts.runs import CreativeOperationKind, WritingWorkflowKind
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
    workflowKind: WritingWorkflowKind
    operation: CreativeOperationKind | None
    targetWordCount: int = Field(default=4000, ge=1, le=10_000_000)
    selectedAgents: list[CoreAgentId] = Field(default_factory=_default_agents)
    userMessage: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_workflow_operation(self) -> Self:
        short_operations = {"develop_short_outline", "write_short_story"}
        if self.workflowKind == "short_medium":
            if self.operation not in short_operations:
                raise ValueError("中短篇必须指定专用 Operation")
            if not 6_000 <= self.targetWordCount <= 80_000:
                raise ValueError("中短篇目标总字数必须为 6000～80000")
        elif self.operation in short_operations:
            raise ValueError("长篇不能使用中短篇 Operation")
        elif self.operation == "sync_lore":
            raise ValueError("同步设定 Operation 已移除")
        return self


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
