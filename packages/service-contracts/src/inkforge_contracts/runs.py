from typing import Literal

from pydantic import BaseModel, ConfigDict, NonNegativeInt

from .identity import Identifier

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
    error: str | None
