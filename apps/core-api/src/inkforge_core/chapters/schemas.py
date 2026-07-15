from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..novels.schemas import ChapterStatus, WorkspaceChapter


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CreateChapterRequest(StrictModel):
    pass


class UpdateChapterRequest(StrictModel):
    title: str
    content: str
    expectedUpdatedAt: datetime


class ChapterStatusRequest(StrictModel):
    status: ChapterStatus
    expectedUpdatedAt: datetime


class ChapterProgressRequest(StrictModel):
    content: str


class ChapterMutationResponse(StrictModel):
    updatedAt: datetime


class ChapterStatusResponse(StrictModel):
    id: str
    status: ChapterStatus
    completedAt: datetime | None
    updatedAt: datetime


class CreateChapterResponse(StrictModel):
    chapter: WorkspaceChapter


class ChapterListResponse(StrictModel):
    chapters: list[WorkspaceChapter]
