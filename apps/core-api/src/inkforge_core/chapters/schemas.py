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


class ChapterStatusRequest(StrictModel):
    status: ChapterStatus


class ChapterProgressRequest(StrictModel):
    content: str


class ChapterMutationResponse(StrictModel):
    updatedAt: datetime


class ChapterStatusResponse(StrictModel):
    id: str
    status: ChapterStatus
    completedAt: datetime | None


class CreateChapterResponse(StrictModel):
    chapter: WorkspaceChapter


class ChapterListResponse(StrictModel):
    chapters: list[WorkspaceChapter]
