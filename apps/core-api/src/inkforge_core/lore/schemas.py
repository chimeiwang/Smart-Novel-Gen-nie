from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class CreateCharacterRequest(StrictModel):
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


class UpdateCharacterRequest(StrictModel):
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


class CreateItemRequest(StrictModel):
    name: str
    aliases: str | None = None
    type: str | None = None
    rarity: str | None = None
    effect: str | None = None
    origin: str | None = None
    description: str | None = None
    ownerId: str | None = None


class UpdateItemRequest(StrictModel):
    name: str | None = None
    aliases: str | None = None
    type: str | None = None
    rarity: str | None = None
    effect: str | None = None
    origin: str | None = None
    description: str | None = None
    ownerId: str | None = None


class CreateLocationRequest(StrictModel):
    name: str
    aliases: str | None = None
    type: str | None = None
    parentId: str | None = None
    climate: str | None = None
    culture: str | None = None
    description: str | None = None


class UpdateLocationRequest(StrictModel):
    name: str | None = None
    aliases: str | None = None
    type: str | None = None
    parentId: str | None = None
    climate: str | None = None
    culture: str | None = None
    description: str | None = None


class CreateFactionRequest(StrictModel):
    name: str
    aliases: str | None = None
    type: str | None = None
    baseId: str | None = None
    description: str | None = None


class UpdateFactionRequest(StrictModel):
    name: str | None = None
    aliases: str | None = None
    type: str | None = None
    baseId: str | None = None
    description: str | None = None


class CreateGlossaryRequest(StrictModel):
    term: str
    definition: str
    category: str | None = None


class UpdateGlossaryRequest(StrictModel):
    term: str | None = None
    definition: str | None = None
    category: str | None = None


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


class WritingBibleRequest(StrictModel):
    targetTotalWordCount: int | None = Field(default=None, gt=0)
    genre: str | None = None
    targetReaders: str | None = None
    coreSellingPoint: str | None = None
    readerPromise: str | None = None
    appealModel: str | None = None
    taboo: str | None = None
    comparableTitles: str | None = None
    notes: str | None = None


class CharacterResponse(CreateCharacterRequest):
    id: str
    createdAt: datetime
    updatedAt: datetime


class ItemResponse(CreateItemRequest):
    id: str
    createdAt: datetime
    updatedAt: datetime


class LocationResponse(CreateLocationRequest):
    id: str
    createdAt: datetime
    updatedAt: datetime


class FactionResponse(CreateFactionRequest):
    id: str
    createdAt: datetime
    updatedAt: datetime


class GlossaryResponse(CreateGlossaryRequest):
    id: str
    createdAt: datetime
    updatedAt: datetime


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


class WritingBibleResponse(WritingBibleRequest):
    id: str
    storyLengthProfile: StoryLengthProfile
    createdAt: datetime
    updatedAt: datetime
