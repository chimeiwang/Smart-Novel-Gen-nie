from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DebugSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowRunSummary(DebugSchema):
    runId: str
    taskId: str
    runKind: str
    userId: str
    novelId: str
    chapterId: str | None
    startedAt: str
    endedAt: str
    status: str


class WorkflowRunListResponse(DebugSchema):
    runs: list[WorkflowRunSummary]


class WorkflowRunDetailResponse(DebugSchema):
    summary: WorkflowRunSummary
    content: str
