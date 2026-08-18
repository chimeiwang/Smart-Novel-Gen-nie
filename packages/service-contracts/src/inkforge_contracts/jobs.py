from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .identity import Identifier
from .long_serial import LONG_SERIAL_RUN_PAYLOAD_ADAPTER
from .short_medium import ShortMediumRunPayload

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

    @model_validator(mode="after")
    def validate_writing_payload(self) -> AgentJobRequest:
        if self.kind != "writing" or "workflow" not in self.payload:
            return self
        workflow = self.payload["workflow"]
        if workflow == "short_medium":
            ShortMediumRunPayload.model_validate(self.payload)
        elif workflow == "long_serial":
            LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(self.payload)
        else:
            raise ValueError("写作任务 workflow 不受支持")
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
