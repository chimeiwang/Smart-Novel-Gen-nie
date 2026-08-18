from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .identity import Identifier
from .short_medium import ShortMediumRunPayload
from .video import VideoPlanJobPayload

AgentJobKind = Literal["writing", "portrait", "rag", "quality", "video"]
AgentJobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


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

    @model_validator(mode="after")
    def validate_short_medium_payload(self) -> AgentJobRequest:
        """按任务类型校验队列载荷，避免处理器收到无结构 JSON。"""

        if (
            self.kind == "writing"
            and self.payload.get("workflow") == "short_medium"
        ):
            ShortMediumRunPayload.model_validate(self.payload)
        elif self.kind == "video":
            VideoPlanJobPayload.model_validate(self.payload)
        return self


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
