from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, NonNegativeInt, model_validator

from .identity import Identifier, NonBlankString

CreativeOperationKind = Literal[
    "answer_question",
    "create_lore",
    "revise_lore",
    "create_outline",
    "revise_outline",
    "plan_chapter",
    "write_chapter",
    "rewrite_scene",
    "review_chapter",
    "sync_lore",
    "manage_foreshadowing",
]


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocolVersion: Literal["1.0"]
    runId: Identifier
    taskId: Identifier
    novelId: Identifier
    userId: Identifier
    operation: CreativeOperationKind
    resume: bool = False


class RunAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocolVersion: Literal["1.0"]
    runId: Identifier
    taskId: Identifier
    status: Literal["accepted", "queued"]


class RunStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocolVersion: Literal["1.0"]
    runId: Identifier
    taskId: Identifier
    status: Literal[
        "queued",
        "running",
        "awaiting_user",
        "completed",
        "failed",
        "cancelled",
    ]
    lastSequence: NonNegativeInt
    error: NonBlankString | None

    @model_validator(mode="after")
    def validate_error(self) -> Self:
        if self.status == "failed" and self.error is None:
            raise ValueError("失败状态必须包含非空错误")
        if self.status != "failed" and self.error is not None:
            raise ValueError("非失败状态不能包含错误")
        return self
