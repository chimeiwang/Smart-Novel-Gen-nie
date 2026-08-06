from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

OutlineKind = Literal["stage", "plot_unit", "chapter_group"]
OutlineStatus = Literal["planned", "in_progress", "completed", "skipped"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _parse_json_datetime(value: object) -> object:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


JsonDatetime = Annotated[datetime, BeforeValidator(_parse_json_datetime)]


class OutlineContentRequest(StrictModel):
    content: str
    expectedUpdatedAt: JsonDatetime


class CreateOutlineNodeRequest(StrictModel):
    title: str
    content: str | None = None
    kind: OutlineKind
    status: OutlineStatus = "planned"
    order: int = 0
    parentId: str | None = None
    linkedChapterId: str | None = None
    estimatedWordCount: int | None = Field(default=None, ge=0)
    actualWordCount: int | None = Field(default=None, ge=0)
    chapterStartOrder: int | None = None
    chapterEndOrder: int | None = None


class UpdateOutlineNodeRequest(StrictModel):
    title: str | None = None
    content: str | None = None
    kind: OutlineKind | None = None
    status: OutlineStatus | None = None
    order: int | None = None
    parentId: str | None = None
    linkedChapterId: str | None = None
    estimatedWordCount: int | None = Field(default=None, ge=0)
    actualWordCount: int | None = Field(default=None, ge=0)
    chapterStartOrder: int | None = None
    chapterEndOrder: int | None = None


class PlotProgressFields(StrictModel):
    currentStage: str
    currentGoal: str | None = None
    currentConflict: str | None = None
    nextMilestone: str | None = None


class PlotProgressRequest(PlotProgressFields):
    expectedUpdatedAt: JsonDatetime | None


class CreateForeshadowingRequest(StrictModel):
    name: str
    plantedAt: str | None = None
    plantedContent: str | None = None
    expectedPayoff: str | None = None
    payoffAt: str | None = None
    status: Literal["active", "paid_off", "abandoned"] = "active"


class UpdateForeshadowingRequest(StrictModel):
    name: str | None = None
    plantedAt: str | None = None
    plantedContent: str | None = None
    expectedPayoff: str | None = None
    payoffAt: str | None = None
    status: Literal["active", "paid_off", "abandoned"] | None = None


class OutlineContentResponse(StrictModel):
    id: str
    content: str
    contentHash: str
    createdAt: datetime
    updatedAt: datetime


class OutlineNodeResponse(CreateOutlineNodeRequest):
    id: str
    createdAt: datetime
    updatedAt: datetime


class PlotProgressResponse(PlotProgressFields):
    id: str
    updatedAt: datetime


class ForeshadowingResponse(CreateForeshadowingRequest):
    id: str
    createdAt: datetime
    updatedAt: datetime
