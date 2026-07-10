from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, JsonValue, PositiveInt

from .identity import Identifier, NonBlankString


class AgentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocolVersion: Literal["1.0"]
    eventId: Identifier
    runId: Identifier
    taskId: Identifier
    sequence: PositiveInt
    event: NonBlankString
    data: dict[str, JsonValue]
    occurredAt: AwareDatetime


class CheckpointCallback(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocolVersion: Literal["1.0"]
    eventId: Identifier
    runId: Identifier
    taskId: Identifier
    sequence: PositiveInt
    checkpoint: dict[str, JsonValue]
    occurredAt: AwareDatetime


class RunCompletionCallback(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocolVersion: Literal["1.0"]
    eventId: Identifier
    runId: Identifier
    taskId: Identifier
    sequence: PositiveInt
    result: dict[str, JsonValue]
    occurredAt: AwareDatetime


class RunFailureCallback(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocolVersion: Literal["1.0"]
    eventId: Identifier
    runId: Identifier
    taskId: Identifier
    sequence: PositiveInt
    code: NonBlankString
    message: NonBlankString
    recoverable: bool
    occurredAt: AwareDatetime
