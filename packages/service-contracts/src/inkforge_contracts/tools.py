from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, JsonValue, model_validator

from .identity import CoreAgentId, Identifier, NonBlankString


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocolVersion: Literal["1.0"]
    callId: Identifier
    runId: Identifier
    taskId: Identifier
    novelId: Identifier
    agentId: CoreAgentId
    toolName: NonBlankString
    arguments: dict[str, JsonValue]


class ToolCallResult(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocolVersion: Literal["1.0"]
    callId: Identifier
    runId: Identifier
    taskId: Identifier
    success: bool
    result: JsonValue | None
    error: str | None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.success and self.error is not None:
            raise ValueError("成功结果不能包含错误")
        if not self.success and (self.error is None or not self.error.strip()):
            raise ValueError("失败结果必须包含非空错误")
        return self
