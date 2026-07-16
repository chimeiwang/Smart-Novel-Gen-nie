from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict

from ..novels.schemas import ChapterStatus, WorkspaceChapter


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _parse_json_datetime(value: object) -> object:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


JsonDatetime = Annotated[datetime, BeforeValidator(_parse_json_datetime)]


class CreateChapterRequest(StrictModel):
    pass


class UpdateChapterRequest(StrictModel):
    title: str
    content: str
    expectedUpdatedAt: JsonDatetime


class ChapterStatusRequest(StrictModel):
    status: ChapterStatus
    expectedUpdatedAt: JsonDatetime


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
