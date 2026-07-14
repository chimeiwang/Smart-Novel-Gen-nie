from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from .identity import Identifier

AgentJobKind = Literal["writing", "portrait", "rag", "quality"]
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
