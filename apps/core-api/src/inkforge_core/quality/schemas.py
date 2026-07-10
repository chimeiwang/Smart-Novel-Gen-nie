from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..novels.schemas import QualityCheckDto


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
