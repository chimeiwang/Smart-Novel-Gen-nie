from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .identity import Identifier, NonBlankString
from .runs import CreativeOperationKind, WritingWorkflowKind

AgentJobKind = Literal["writing", "portrait", "rag", "quality"]
AgentJobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]

SHORT_STORY_OPERATIONS = frozenset({"develop_short_outline", "write_short_story"})


class ShortOutlineInspirationSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["short_outline_inspiration"]
    originalInspiration: NonBlankString


class ApprovedShortOutlineSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["approved_short_outline"]
    outlineArtifactId: Identifier
    outlineRevision: int = Field(ge=1)
    outlineHash: str = Field(pattern=r"^[0-9a-f]{64}$")


WritingSource = ShortOutlineInspirationSource | ApprovedShortOutlineSource


class WritingJobPayload(BaseModel):
    """Core 持久命令与 Agent 队列之间的稳定写作身份。"""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    resume: bool
    chapterId: Identifier
    writingSessionId: Identifier | None
    resumeInput: dict[str, JsonValue] | None
    workflowKind: WritingWorkflowKind
    operation: CreativeOperationKind | None
    targetTotalWordCount: int | None
    source: WritingSource | None
    startRequest: dict[str, JsonValue] | None = None
    decisionRequest: dict[str, JsonValue] | None = None
    force: bool = False

    @model_validator(mode="after")
    def validate_workflow_identity(self) -> Self:
        if self.workflowKind == "short_medium":
            if self.operation not in SHORT_STORY_OPERATIONS:
                raise ValueError("中短篇写作命令必须指定专用 Operation")
            if (
                self.targetTotalWordCount is None
                or not 6_000 <= self.targetTotalWordCount <= 80_000
            ):
                raise ValueError("中短篇目标总字数必须为 6000～80000")
            if self.operation == "develop_short_outline" and not isinstance(
                self.source, ShortOutlineInspirationSource
            ):
                raise ValueError("中短篇大纲命令缺少原始灵感来源")
            if self.operation == "write_short_story" and not isinstance(
                self.source, ApprovedShortOutlineSource
            ):
                raise ValueError("中短篇整稿命令缺少已批准大纲来源")
            return self
        if self.operation in SHORT_STORY_OPERATIONS:
            raise ValueError("长篇命令不能使用中短篇 Operation")
        if self.operation == "sync_lore":
            raise ValueError("已移除的同步设定 Operation 不能进入新写作命令")
        if self.source is not None:
            raise ValueError("长篇命令不能携带中短篇来源")
        return self


class AgentJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocolVersion: Literal["1.0"]
    jobId: Identifier
    kind: AgentJobKind
    runId: Identifier
    taskId: Identifier
    novelId: Identifier
    userId: Identifier
    priority: int = Field(ge=0, le=99)
    payload: dict[str, JsonValue]
    force: bool = False


class AgentJobAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocolVersion: Literal["1.0"] = "1.0"
    jobId: Identifier
    runId: Identifier
    taskId: Identifier
    status: AgentJobStatus


class AgentJobCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocolVersion: Literal["1.0"]
    runId: Identifier
    taskId: Identifier
    novelId: Identifier
