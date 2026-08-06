from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

ReferenceType = Literal["note", "web", "book", "image", "custom"]
RagStatus = Literal["disabled", "ready", "failed"]
EmbeddingVector = Annotated[list[float], Field(min_length=1, max_length=4096)]


def _parse_json_datetime(value: object) -> object:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


JsonDatetime = Annotated[datetime, BeforeValidator(_parse_json_datetime)]
ContentHash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReferenceFields(StrictModel):
    title: str
    type: ReferenceType
    content: str
    sourceUrl: str | None = None


class ReferencePatch(StrictModel):
    title: str | None = None
    type: ReferenceType | None = None
    content: str | None = None
    sourceUrl: str | None = None


class CreateReferenceRequest(ReferenceFields):
    clientRequestId: str = Field(min_length=16, max_length=256)


class UpdateReferenceRequest(ReferencePatch):
    expectedUpdatedAt: JsonDatetime

    @model_validator(mode="after")
    def require_business_field(self) -> UpdateReferenceRequest:
        if not self.model_fields_set - {"expectedUpdatedAt"}:
            raise ValueError("至少需要提供一个更新字段")
        return self


class DeleteReferenceRequest(StrictModel):
    expectedUpdatedAt: JsonDatetime


class ReindexReferenceRequest(StrictModel):
    expectedContentHash: ContentHash


class ReferenceMaterialResponse(ReferenceFields):
    id: str
    ragStatus: RagStatus
    contentHash: ContentHash
    errorMessage: str | None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class CreateReferenceResponse(ReferenceMaterialResponse):
    effective: bool


class DeleteReferenceAffected(StrictModel):
    reference: Literal[1]
    ragDocuments: Literal[0, 1]
    ragChunks: int = Field(ge=0)


class DeleteReferenceImpactResponse(StrictModel):
    deletedType: Literal["reference"]
    deletedId: str
    affected: DeleteReferenceAffected


class RagSearchRequest(StrictModel):
    queryEmbedding: EmbeddingVector
    topK: int = Field(default=5, gt=0, le=20)


class CompleteReferenceIndexRequest(StrictModel):
    taskId: str = Field(min_length=1, max_length=256)
    runId: str = Field(min_length=1, max_length=256)
    expectedContentHash: ContentHash
    embeddings: list[EmbeddingVector] = Field(max_length=64)


class FailReferenceIndexRequest(StrictModel):
    taskId: str = Field(min_length=1, max_length=256)
    runId: str = Field(min_length=1, max_length=256)
    expectedContentHash: ContentHash
    message: str = Field(min_length=1, max_length=1000)


class ReferenceIndexContextRequest(StrictModel):
    userId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    runId: str = Field(min_length=1, max_length=256)
    expectedContentHash: ContentHash


class ReferenceIndexContextResponse(StrictModel):
    contentHash: ContentHash
    chunks: list[str] = Field(max_length=64)


class RagSearchResult(StrictModel):
    title: str
    sourceId: str
    chunkIndex: int
    score: float
    text: str


class ReindexAcceptedResponse(StrictModel):
    accepted: Literal[True]
