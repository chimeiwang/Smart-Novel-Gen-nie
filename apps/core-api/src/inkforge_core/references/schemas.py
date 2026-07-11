from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReferenceType = Literal["note", "web", "book", "image", "custom"]
RagStatus = Literal["disabled", "ready", "failed"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CreateReferenceRequest(StrictModel):
    title: str
    type: ReferenceType
    content: str
    sourceUrl: str | None = None


class UpdateReferenceRequest(StrictModel):
    title: str | None = None
    type: ReferenceType | None = None
    content: str | None = None
    sourceUrl: str | None = None


class ReferenceMaterialResponse(StrictModel):
    id: str
    title: str
    type: ReferenceType
    content: str
    sourceUrl: str | None
    ragStatus: RagStatus
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class RagSearchRequest(StrictModel):
    embedding: list[float]
    topK: int = Field(default=5, gt=0, le=20)


class CompleteReferenceIndexRequest(StrictModel):
    embeddings: list[list[float]]


class RagSearchResult(StrictModel):
    title: str
    sourceId: str
    chunkIndex: int
    score: float
    text: str
