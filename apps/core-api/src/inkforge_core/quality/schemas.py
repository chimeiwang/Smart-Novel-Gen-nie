from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..novels.schemas import QualityCheckDto


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class UpdateQualityCheckRequest(StrictModel):
    status: Literal["pending", "skipped"]
    resetResult: bool = False


class RunQualityCheckRequest(StrictModel):
    taskId: str | None = None
    message: str | None = None


class RunQualityCheckResponse(StrictModel):
    accepted: bool
    checkId: str
    taskId: str


class QualityCheckResponse(StrictModel):
    check: QualityCheckDto


class QualityRunContextRequest(StrictModel):
    userId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    runId: str = Field(min_length=1, max_length=256)
    sourceTaskId: str | None = Field(default=None, min_length=1, max_length=256)
    message: str | None = None


class QualityRunContextResponse(StrictModel):
    checkId: str
    novelId: str
    chapterId: str
    chapterContent: str
    message: str


class QualityRunSuccessRequest(StrictModel):
    userId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    runId: str = Field(min_length=1, max_length=256)
    result: str
    scores: dict[str, float]
    qualityGate: Literal["pass", "revise", "rewrite"]
    rewriteBrief: str | None = None


class QualityRunFailureRequest(StrictModel):
    userId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    runId: str = Field(min_length=1, max_length=256)
    message: str = Field(min_length=1, max_length=1000)
