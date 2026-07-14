from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

StyleSourceType = Literal["manual", "agent"]
StyleReferenceStatus = Literal["ready", "error"]
PortraitTaskStatus = Literal["pending", "processing", "success", "error"]
PortraitSection = Literal[
    "creativeMethodology",
    "uniqueMarkers",
    "generationStyle",
    "expressionFeatures",
    "styleTraits",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CreateStyleRequest(StrictModel):
    name: str = Field(min_length=1, max_length=200)


class UpdatePortraitSectionRequest(StrictModel):
    content: str = Field(min_length=1)


class ApplyStyleRequest(StrictModel):
    styleId: str | None


class StyleReferenceResponse(StrictModel):
    id: str
    styleId: str
    filename: str
    charCount: int = Field(ge=0)
    status: StyleReferenceStatus
    errorMessage: str | None
    createdAt: datetime


class PortraitTaskResponse(StrictModel):
    id: str
    styleId: str
    section: PortraitSection | None
    status: PortraitTaskStatus
    errorMessage: str | None
    createdAt: datetime
    updatedAt: datetime


class StyleResponse(StrictModel):
    id: str
    name: str
    sourceType: StyleSourceType
    creativeMethodology: str | None
    uniqueMarkers: str | None
    generationStyle: str | None
    expressionFeatures: str | None
    styleTraits: str | None
    portraitMarkdown: str | None
    originalCharCount: int = Field(ge=0)
    usedCharCount: int = Field(ge=0)
    truncated: bool
    errorMessage: str | None
    createdAt: datetime
    updatedAt: datetime
    references: list[StyleReferenceResponse]
    tasks: list[PortraitTaskResponse]


class PortraitAcceptedResponse(StrictModel):
    taskId: str
    status: Literal["pending"]


class PortraitProcessingRequest(StrictModel):
    runId: str = Field(min_length=1, max_length=256)


class FullPortraitSuccessRequest(StrictModel):
    mode: Literal["full"]
    runId: str = Field(min_length=1, max_length=256)
    creativeMethodology: str = Field(min_length=1)
    uniqueMarkers: str = Field(min_length=1)
    generationStyle: str = Field(min_length=1)
    expressionFeatures: str = Field(min_length=1)
    styleTraits: str = Field(min_length=1)
    originalCharCount: int = Field(ge=0)
    usedCharCount: int = Field(ge=0)
    truncated: Literal[False]


class SectionPortraitSuccessRequest(StrictModel):
    mode: Literal["section"]
    runId: str = Field(min_length=1, max_length=256)
    section: PortraitSection
    content: str = Field(min_length=1)
    originalCharCount: int = Field(ge=0)
    usedCharCount: int = Field(ge=0)
    truncated: Literal[False]


PortraitSuccessRequest = Annotated[
    FullPortraitSuccessRequest | SectionPortraitSuccessRequest,
    Field(discriminator="mode"),
]


class PortraitFailureRequest(StrictModel):
    runId: str = Field(min_length=1, max_length=256)
    message: str = Field(min_length=1, max_length=1000)


class PortraitContextRequest(StrictModel):
    runId: str = Field(min_length=1, max_length=256)


class PortraitContextResponse(StrictModel):
    sourceText: str = Field(min_length=1)
    originalCharCount: int = Field(ge=0)
