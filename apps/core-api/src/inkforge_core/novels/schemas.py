from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True)


type ChapterStatus = Literal["drafting", "review", "completed"]
type StoryLengthProfile = Literal["short_medium", "long_serial"]
type ShortMediumSourceKind = Literal["idea", "opening", "ending", "outline", "mixed"]
type StyleSourceType = Literal["manual", "agent"]
type ReferenceType = Literal["note", "web", "book", "image", "custom"]
type RagDocumentStatus = Literal["disabled", "ready", "failed"]
type QualityCheckType = Literal["consistency", "lore_sync", "editorial", "craft"]
type QualityCheckStatus = Literal["pending", "running", "completed", "skipped", "failed"]
type QualityGate = Literal["pass", "revise", "rewrite"]
type BeatPlanStatus = Literal["draft", "reviewing", "approved", "rejected", "superseded"]
type CharacterStatus = Literal["active", "missing", "dead", "imprisoned", "unknown"]
type RelationType = Literal[
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
type OutlineNodeKind = Literal["stage", "plot_unit", "chapter_group"]
type OutlineNodeStatus = Literal["planned", "in_progress", "completed", "skipped"]


def _parse_json_datetime(value: object) -> object:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


JsonDatetime = Annotated[AwareDatetime, BeforeValidator(_parse_json_datetime)]


class CreateNovelRequest(StrictModel):
    name: str = Field(min_length=1)
    summary: str | None = None
    storyLengthProfile: StoryLengthProfile
    targetTotalWordCount: int | None = Field(default=None, gt=0)
    clientRequestId: str | None = Field(default=None, min_length=16, max_length=128)
    sourceKind: ShortMediumSourceKind | None = None
    sourceText: str | None = None
    genre: str | None = None
    protagonist: str | None = None
    coreSellingPoint: str | None = None
    readerPromise: str | None = None
    firstChapterGoal: str | None = None

    @model_validator(mode="after")
    def validate_short_medium_source(self) -> CreateNovelRequest:
        if self.storyLengthProfile == "short_medium":
            if self.clientRequestId is None or self.sourceKind is None:
                raise ValueError("中短篇创建必须提供请求标识和素材类型")
            if self.sourceText is None or not self.sourceText.strip():
                raise ValueError("中短篇创建必须提供起始素材")
            if self.targetTotalWordCount is None:
                raise ValueError("中短篇创建必须提供目标字数")
            if not 6_000 <= self.targetTotalWordCount <= 80_000:
                raise ValueError("中短篇目标字数必须在 6000 到 80000 之间")
        elif any(
            value is not None
            for value in (self.clientRequestId, self.sourceKind, self.sourceText)
        ):
            raise ValueError("长篇创建不能携带中短篇起始素材字段")
        return self


class CreateNovelResponse(StrictModel):
    novelId: str
    chapterId: str


class UpdateNovelSummaryRequest(StrictModel):
    summary: str | None
    expectedUpdatedAt: JsonDatetime


class StyleSummary(StrictModel):
    id: str
    name: str
    portraitMarkdown: str | None = None
    sourceType: StyleSourceType


class AppliedStyleSummary(StrictModel):
    id: str
    name: str


class ChapterIdSummary(StrictModel):
    id: str


class DashboardNovel(StrictModel):
    id: str
    name: str
    summary: str | None
    updatedAt: datetime
    chapters: list[ChapterIdSummary]
    appliedStyle: AppliedStyleSummary | None


class DashboardResponse(StrictModel):
    novels: list[DashboardNovel]


class NovelResponse(StrictModel):
    id: str
    name: str
    summary: str | None
    storyProgress: str | None
    appliedStyleId: str | None
    storyLengthProfile: StoryLengthProfile | None = None
    targetTotalWordCount: int | None = None
    createdAt: datetime
    updatedAt: datetime


class ChapterProgressDto(StrictModel):
    id: str
    chapterId: str
    content: str
    createdAt: datetime
    updatedAt: datetime


class QualityCheckDto(StrictModel):
    id: str
    chapterId: str
    type: QualityCheckType
    status: QualityCheckStatus
    title: str
    summary: str | None
    result: str | None
    scoreHook: int | None
    scoreTension: int | None
    scorePayoff: int | None
    scorePacing: int | None
    scoreEndingHook: int | None
    scoreReaderPromise: int | None
    scoreOverall: int | None
    qualityGate: QualityGate | None
    rewriteBrief: str | None
    createdAt: datetime
    updatedAt: datetime


class SceneBeatDto(StrictModel):
    id: str
    order: int
    goal: str
    conflict: str | None
    characters: str
    foreshadowingRefs: str | None
    estimatedWords: int
    acceptanceCriteria: str


class BeatPlanDto(StrictModel):
    id: str
    chapterId: str
    goalId: str | None
    status: BeatPlanStatus
    chapterGoal: str
    mainPlotConnection: str | None
    chapterAcceptanceCriteria: str | None
    totalEstimatedWords: int
    generatedBy: str | None
    createdAt: datetime
    updatedAt: datetime
    sceneBeats: list[SceneBeatDto]


class WorkspaceChapter(StrictModel):
    id: str
    title: str
    content: str
    order: int
    status: ChapterStatus
    completedAt: datetime | None
    createdAt: datetime
    updatedAt: datetime
    wordCount: int
    progress: ChapterProgressDto | None
    qualityChecks: list[QualityCheckDto]
    approvedBeatPlan: BeatPlanDto | None


class FactionSummary(StrictModel):
    id: str
    name: str


class CharacterExperienceDto(StrictModel):
    id: str
    chapterId: str | None
    content: str
    order: int
    createdAt: datetime
    updatedAt: datetime


class RelationPeer(StrictModel):
    id: str
    name: str


class CharacterRelationDto(StrictModel):
    id: str
    characterId: str
    targetId: str
    relationType: RelationType
    intimacy: int
    description: str | None
    startDate: str | None
    endDate: str | None
    character: RelationPeer | None = None
    target: RelationPeer | None = None
    createdAt: datetime
    updatedAt: datetime


class CharacterDto(StrictModel):
    id: str
    name: str
    aliases: str | None
    gender: str | None
    age: str | None
    appearance: str | None
    personality: str | None
    identity: str | None
    background: str | None
    coreDesire: str | None
    behaviorBoundaries: str | None
    speechStyle: str | None
    relationshipPrinciples: str | None
    shortTermGoal: str | None
    factionId: str | None
    faction: FactionSummary | None
    powerLevel: str | None
    combatAbility: str | None
    specialSkills: str | None
    currentStatus: CharacterStatus
    statusNote: str | None
    experiences: list[CharacterExperienceDto]
    outgoingRelations: list[CharacterRelationDto]
    incomingRelations: list[CharacterRelationDto]
    createdAt: datetime
    updatedAt: datetime


class OwnerSummary(StrictModel):
    id: str
    name: str


class ItemDto(StrictModel):
    id: str
    name: str
    aliases: str | None
    type: str | None
    rarity: str | None
    effect: str | None
    origin: str | None
    description: str | None
    ownerId: str | None
    owner: OwnerSummary | None
    createdAt: datetime
    updatedAt: datetime


class LocationDto(StrictModel):
    id: str
    name: str
    aliases: str | None
    type: str | None
    parentId: str | None
    climate: str | None
    culture: str | None
    description: str | None
    createdAt: datetime
    updatedAt: datetime


class FactionDto(StrictModel):
    id: str
    name: str
    aliases: str | None
    type: str | None
    baseId: str | None
    description: str | None
    createdAt: datetime
    updatedAt: datetime


class GlossaryDto(StrictModel):
    id: str
    term: str
    definition: str
    category: str | None
    createdAt: datetime
    updatedAt: datetime


class ContentDto(StrictModel):
    id: str
    content: str
    createdAt: datetime
    updatedAt: datetime


class WritingBibleDto(StrictModel):
    id: str
    storyLengthProfile: StoryLengthProfile
    targetTotalWordCount: int | None
    genre: str | None
    targetReaders: str | None
    coreSellingPoint: str | None
    readerPromise: str | None
    appealModel: str | None
    taboo: str | None
    comparableTitles: str | None
    notes: str | None
    createdAt: datetime
    updatedAt: datetime


class OutlineNodeDto(StrictModel):
    id: str
    title: str
    content: str | None
    kind: OutlineNodeKind
    status: OutlineNodeStatus
    order: int
    parentId: str | None
    linkedChapterId: str | None
    estimatedWordCount: int | None
    actualWordCount: int | None
    chapterStartOrder: int | None
    chapterEndOrder: int | None
    createdAt: datetime
    updatedAt: datetime


class PlotProgressDto(StrictModel):
    id: str
    currentStage: str
    currentGoal: str | None
    currentConflict: str | None
    nextMilestone: str | None
    updatedAt: datetime


class ReferenceDto(StrictModel):
    id: str
    title: str
    type: ReferenceType
    content: str
    sourceUrl: str | None
    ragStatus: RagDocumentStatus
    contentHash: str
    errorMessage: str | None
    createdAt: datetime
    updatedAt: datetime


class WorkspaceNovel(NovelResponse):
    appliedStyle: AppliedStyleSummary | None


class ApprovedBeatPlanSummary(StrictModel):
    sceneCount: int
    totalEstimatedWords: int


class WorkspaceChapterSummary(StrictModel):
    id: str
    title: str
    order: int
    status: ChapterStatus
    updatedAt: datetime
    wordCount: int
    approvedBeatPlan: ApprovedBeatPlanSummary | None


class WorkspaceBootstrapResponse(StrictModel):
    novel: WorkspaceNovel
    chapters: list[WorkspaceChapterSummary]
    currentChapter: WorkspaceChapter | None
    currentChapterId: str | None


class WorkspaceLoreResponse(StrictModel):
    characters: list[CharacterDto]
    items: list[ItemDto]
    locations: list[LocationDto]
    factions: list[FactionDto]
    glossaries: list[GlossaryDto]


class WorkspacePlanningResponse(StrictModel):
    storyProgress: str | None
    storyProgressUpdatedAt: datetime
    storyBackground: ContentDto | None
    worldSetting: ContentDto | None
    writingBible: WritingBibleDto | None
    outline: ContentDto | None
    outlineNodes: list[OutlineNodeDto]
    plotProgress: PlotProgressDto | None


class WorkspaceResourcesResponse(StrictModel):
    references: list[ReferenceDto]
    styles: list[StyleSummary]
    appliedStyle: AppliedStyleSummary | None


class WorkspaceResponse(StrictModel):
    novel: WorkspaceNovel
    chapters: list[WorkspaceChapter]
    currentChapterId: str | None
    characters: list[CharacterDto]
    items: list[ItemDto]
    locations: list[LocationDto]
    factions: list[FactionDto]
    glossaries: list[GlossaryDto]
    storyBackground: ContentDto | None
    worldSetting: ContentDto | None
    writingBible: WritingBibleDto | None
    outline: ContentDto | None
    outlineNodes: list[OutlineNodeDto]
    plotProgress: PlotProgressDto | None
    references: list[ReferenceDto]
    styles: list[StyleSummary]
