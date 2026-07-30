from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    JsonValue,
    PositiveInt,
    model_validator,
)

from .identity import Identifier, NonBlankString
from .short_medium import validate_short_medium_result


class AgentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocolVersion: Literal["1.1"]
    eventId: Identifier
    jobId: Identifier
    runId: Identifier
    taskId: Identifier
    sequence: PositiveInt
    event: NonBlankString
    data: dict[str, JsonValue]
    occurredAt: AwareDatetime


class CheckpointCallback(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocolVersion: Literal["1.1"]
    eventId: Identifier
    jobId: Identifier
    runId: Identifier
    taskId: Identifier
    sequence: PositiveInt
    checkpoint: dict[str, JsonValue]
    occurredAt: AwareDatetime


class RunCompletionCallback(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocolVersion: Literal["1.1"]
    eventId: Identifier
    jobId: Identifier
    runId: Identifier
    taskId: Identifier
    sequence: PositiveInt
    result: dict[str, JsonValue]
    occurredAt: AwareDatetime

    @model_validator(mode="after")
    def validate_short_medium_completion(self) -> "RunCompletionCallback":
        validate_short_medium_result(self.result)
        return self


class RunFailureCallback(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocolVersion: Literal["1.1"]
    eventId: Identifier
    jobId: Identifier
    runId: Identifier
    taskId: Identifier
    sequence: PositiveInt
    code: NonBlankString
    message: NonBlankString
    recoverable: bool
    occurredAt: AwareDatetime
