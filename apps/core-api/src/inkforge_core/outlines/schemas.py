from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OutlineKind = Literal["stage", "plot_unit", "chapter_group"]
OutlineStatus = Literal["planned", "in_progress", "completed", "skipped"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OutlineContentRequest(StrictModel):
    content: str


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


class PlotProgressRequest(StrictModel):
    currentStage: str
    currentGoal: str | None = None
    currentConflict: str | None = None
    nextMilestone: str | None = None


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
