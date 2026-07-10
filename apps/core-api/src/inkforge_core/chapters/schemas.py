from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..novels.schemas import WorkspaceChapter


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateChapterRequest(StrictModel):
    pass


class UpdateChapterRequest(StrictModel):
    title: str
    content: str


class ChapterStatusRequest(StrictModel):
    status: Literal["drafting", "review", "completed"]


class ChapterProgressRequest(StrictModel):
    content: str


class ChapterMutationResponse(StrictModel):
    updatedAt: datetime


class ChapterStatusResponse(StrictModel):
    id: str
    status: str
    completedAt: datetime | None


class CreateChapterResponse(StrictModel):
    chapter: WorkspaceChapter


class ChapterListResponse(StrictModel):
    chapters: list[WorkspaceChapter]
