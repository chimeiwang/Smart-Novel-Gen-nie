from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ReferenceType = Literal["note", "web", "book", "image", "custom"]
RagStatus = Literal["disabled", "ready", "failed"]
EmbeddingVector = Annotated[list[float], Field(min_length=1, max_length=4096)]


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
    contentHash: str
    errorMessage: str | None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class RagSearchRequest(StrictModel):
    embedding: list[float]
    topK: int = Field(default=5, gt=0, le=20)


class CompleteReferenceIndexRequest(StrictModel):
    taskId: str = Field(min_length=1, max_length=256)
    runId: str = Field(min_length=1, max_length=256)
    expectedContentHash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    embeddings: list[EmbeddingVector] = Field(max_length=64)


class FailReferenceIndexRequest(StrictModel):
    taskId: str = Field(min_length=1, max_length=256)
    runId: str = Field(min_length=1, max_length=256)
    expectedContentHash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    message: str = Field(min_length=1, max_length=1000)


class RagSearchResult(StrictModel):
    title: str
    sourceId: str
    chunkIndex: int
    score: float
    text: str


class ReindexAcceptedResponse(StrictModel):
    accepted: Literal[True]
