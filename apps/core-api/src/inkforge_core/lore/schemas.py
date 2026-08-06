from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

CharacterStatus = Literal["active", "missing", "dead", "imprisoned", "unknown"]
RelationType = Literal[
    "family",
    "master_student",
    "friend",
    "enemy",
    "ally",
    "lover",
    "rival",
    "subordinate",
    "acquaintance",
    "other",
]
StoryLengthProfile = Literal["short_medium", "long_serial"]
LoreKind = Literal["characters", "items", "locations", "factions", "glossary"]
ContentKind = Literal["story-background", "world-setting", "writing-bible", "story-progress"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _parse_json_datetime(value: object) -> object:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


JsonDatetime = Annotated[datetime, BeforeValidator(_parse_json_datetime)]


class CharacterFields(StrictModel):
    name: str
    aliases: str | None = None
    gender: str | None = None
    age: str | None = None
    appearance: str | None = None
    personality: str | None = None
    identity: str | None = None
    background: str | None = None
    coreDesire: str | None = None
    behaviorBoundaries: str | None = None
    speechStyle: str | None = None
    relationshipPrinciples: str | None = None
    shortTermGoal: str | None = None
    factionId: str | None = None
    powerLevel: str | None = None
    combatAbility: str | None = None
    specialSkills: str | None = None
    currentStatus: CharacterStatus = "active"
    statusNote: str | None = None


class CharacterPatch(StrictModel):
    name: str | None = None
    aliases: str | None = None
    gender: str | None = None
    age: str | None = None
    appearance: str | None = None
    personality: str | None = None
    identity: str | None = None
    background: str | None = None
    coreDesire: str | None = None
    behaviorBoundaries: str | None = None
    speechStyle: str | None = None
    relationshipPrinciples: str | None = None
    shortTermGoal: str | None = None
    factionId: str | None = None
    powerLevel: str | None = None
    combatAbility: str | None = None
    specialSkills: str | None = None
    currentStatus: CharacterStatus | None = None
    statusNote: str | None = None


class ItemFields(StrictModel):
    name: str
    aliases: str | None = None
    type: str | None = None
    rarity: str | None = None
    effect: str | None = None
    origin: str | None = None
    description: str | None = None
    ownerId: str | None = None


class ItemPatch(StrictModel):
    name: str | None = None
    aliases: str | None = None
    type: str | None = None
    rarity: str | None = None
    effect: str | None = None
    origin: str | None = None
    description: str | None = None
    ownerId: str | None = None


class LocationFields(StrictModel):
    name: str
    aliases: str | None = None
    type: str | None = None
    parentId: str | None = None
    climate: str | None = None
    culture: str | None = None
    description: str | None = None


class LocationPatch(StrictModel):
    name: str | None = None
    aliases: str | None = None
    type: str | None = None
    parentId: str | None = None
    climate: str | None = None
    culture: str | None = None
    description: str | None = None


class FactionFields(StrictModel):
    name: str
    aliases: str | None = None
    type: str | None = None
    baseId: str | None = None
    description: str | None = None


class FactionPatch(StrictModel):
    name: str | None = None
    aliases: str | None = None
    type: str | None = None
    baseId: str | None = None
    description: str | None = None


class GlossaryFields(StrictModel):
    term: str
    definition: str
    category: str | None = None


class GlossaryPatch(StrictModel):
    term: str | None = None
    definition: str | None = None
    category: str | None = None


class CreateCharacterRequest(CharacterFields):
    clientRequestId: str = Field(min_length=16, max_length=256)


class UpdateCharacterRequest(CharacterPatch):
    expectedUpdatedAt: JsonDatetime

    @model_validator(mode="after")
    def require_business_field(self) -> UpdateCharacterRequest:
        _require_patch_field(self)
        return self


class CreateItemRequest(ItemFields):
    clientRequestId: str = Field(min_length=16, max_length=256)


class UpdateItemRequest(ItemPatch):
    expectedUpdatedAt: JsonDatetime

    @model_validator(mode="after")
    def require_business_field(self) -> UpdateItemRequest:
        _require_patch_field(self)
        return self


class CreateLocationRequest(LocationFields):
    clientRequestId: str = Field(min_length=16, max_length=256)


class UpdateLocationRequest(LocationPatch):
    expectedUpdatedAt: JsonDatetime

    @model_validator(mode="after")
    def require_business_field(self) -> UpdateLocationRequest:
        _require_patch_field(self)
        return self


class CreateFactionRequest(FactionFields):
    clientRequestId: str = Field(min_length=16, max_length=256)


class UpdateFactionRequest(FactionPatch):
    expectedUpdatedAt: JsonDatetime

    @model_validator(mode="after")
    def require_business_field(self) -> UpdateFactionRequest:
        _require_patch_field(self)
        return self


class CreateGlossaryRequest(GlossaryFields):
    clientRequestId: str = Field(min_length=16, max_length=256)


class UpdateGlossaryRequest(GlossaryPatch):
    expectedUpdatedAt: JsonDatetime

    @model_validator(mode="after")
    def require_business_field(self) -> UpdateGlossaryRequest:
        _require_patch_field(self)
        return self


def _require_patch_field(value: BaseModel) -> None:
    if not value.model_fields_set - {"expectedUpdatedAt"}:
        raise ValueError("至少需要提供一个更新字段")


class DeleteEntityRequest(StrictModel):
    expectedUpdatedAt: JsonDatetime


class DeleteImpactResponse(StrictModel):
    deletedType: LoreKind
    deletedId: str
    affected: dict[str, int]


class ExperienceRequest(StrictModel):
    chapterId: str | None = None
    content: str
    order: int | None = None


class RelationRequest(StrictModel):
    characterId: str
    targetId: str
    relationType: RelationType
    intimacy: int = Field(default=0, ge=0, le=100)
    description: str | None = None
    startDate: str | None = None
    endDate: str | None = None


class UpdateRelationRequest(StrictModel):
    relationType: RelationType | None = None
    intimacy: int | None = Field(default=None, ge=0, le=100)
    description: str | None = None
    startDate: str | None = None
    endDate: str | None = None


class ContentRequest(StrictModel):
    content: str | None
    expectedUpdatedAt: JsonDatetime | None


class WritingBibleFields(StrictModel):
    storyLengthProfile: StoryLengthProfile | None = None
    targetTotalWordCount: int | None = Field(default=None, gt=0)
    genre: str | None = None
    targetReaders: str | None = None
    coreSellingPoint: str | None = None
    readerPromise: str | None = None
    appealModel: str | None = None
    taboo: str | None = None
    comparableTitles: str | None = None
    notes: str | None = None


class WritingBibleRequest(WritingBibleFields):
    expectedUpdatedAt: JsonDatetime | None


class CharacterResponse(CharacterFields):
    id: str
    createdAt: datetime
    updatedAt: datetime


class CreateCharacterResponse(CharacterResponse):
    effective: bool


class ItemResponse(ItemFields):
    id: str
    createdAt: datetime
    updatedAt: datetime


class CreateItemResponse(ItemResponse):
    effective: bool


class LocationResponse(LocationFields):
    id: str
    createdAt: datetime
    updatedAt: datetime


class CreateLocationResponse(LocationResponse):
    effective: bool


class FactionResponse(FactionFields):
    id: str
    createdAt: datetime
    updatedAt: datetime


class CreateFactionResponse(FactionResponse):
    effective: bool


class GlossaryResponse(GlossaryFields):
    id: str
    createdAt: datetime
    updatedAt: datetime


class CreateGlossaryResponse(GlossaryResponse):
    effective: bool


class ExperienceResponse(StrictModel):
    id: str
    characterId: str
    chapterId: str | None
    content: str
    order: int
    createdAt: datetime
    updatedAt: datetime


class RelationResponse(RelationRequest):
    id: str
    createdAt: datetime
    updatedAt: datetime


class ContentResponse(StrictModel):
    id: str
    content: str | None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class WritingBibleResponse(WritingBibleFields):
    id: str
    storyLengthProfile: StoryLengthProfile
    createdAt: datetime
    updatedAt: datetime
