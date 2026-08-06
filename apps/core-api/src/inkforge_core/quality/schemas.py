from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from inkforge_contracts import ConsistencyQualityReport
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from ..novels.schemas import QualityCheckDto


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _parse_json_datetime(value: object) -> object:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


JsonDatetime = Annotated[datetime, BeforeValidator(_parse_json_datetime)]


class UpdateQualityCheckRequest(StrictModel):
    status: Literal["pending", "skipped"]
    resetResult: bool = False
    expectedUpdatedAt: JsonDatetime


class RunQualityCheckRequest(StrictModel):
    clientRequestId: str = Field(min_length=16, max_length=128)
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


class QualityRunSuccessRequest(ConsistencyQualityReport):
    model_config = ConfigDict(extra="forbid", strict=True)

    userId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    runId: str = Field(min_length=1, max_length=256)


class QualityRunFailureRequest(StrictModel):
    userId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    runId: str = Field(min_length=1, max_length=256)
    message: str = Field(min_length=1, max_length=1000)
