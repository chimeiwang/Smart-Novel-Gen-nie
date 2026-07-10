from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, generate_id, utc_now

faction_territories = Table(
    "_FactionTerritories",
    Base.metadata,
    Column(
        "A",
        Text,
        ForeignKey(
            "public.Faction.id",
            name="_FactionTerritories_A_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    ),
    Column(
        "B",
        Text,
        ForeignKey(
            "public.Location.id",
            name="_FactionTerritories_B_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    ),
    PrimaryKeyConstraint("A", "B", name="_FactionTerritories_AB_pkey"),
    Index("_FactionTerritories_B_index", "B"),
    schema="public",
)


class Chapter(Base):
    __tablename__ = "Chapter"
    completedAt: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id", name="Chapter_novelId_fkey", ondelete="CASCADE", onupdate="CASCADE"
        ),
        nullable=False,
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        PG_ENUM("drafting", "review", "completed", name="ChapterStatus", create_type=False),
        nullable=False,
        server_default=text("'drafting'::\"ChapterStatus\""),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    novel: Mapped[Novel] = relationship(
        back_populates="chapters",
        foreign_keys=lambda: [Chapter.novelId],
    )
    beatPlans: Mapped[list[ChapterBeatPlan]] = relationship(
        back_populates="chapter",
        foreign_keys=lambda: [ChapterBeatPlan.chapterId],
    )
    chapterProgress: Mapped[ChapterProgress | None] = relationship(
        back_populates="chapter",
        foreign_keys=lambda: [ChapterProgress.chapterId],
    )
    qualityChecks: Mapped[list[ChapterQualityCheck]] = relationship(
        back_populates="chapter",
        foreign_keys=lambda: [ChapterQualityCheck.chapterId],
    )
    writingGoals: Mapped[list[ChapterWritingGoal]] = relationship(
        back_populates="chapter",
        foreign_keys=lambda: [ChapterWritingGoal.chapterId],
    )
    reviewArtifacts: Mapped[list[ReviewArtifact]] = relationship(
        back_populates="chapter",
        foreign_keys=lambda: [ReviewArtifact.chapterId],
    )
    writingSessions: Mapped[list[WritingSession]] = relationship(
        back_populates="chapter",
        foreign_keys=lambda: [WritingSession.chapterId],
    )
    writingTasks: Mapped[list[WritingTask]] = relationship(
        back_populates="chapter",
        foreign_keys=lambda: [WritingTask.chapterId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="Chapter_pkey",
        ),
        Index("Chapter_novelId_order_idx", "novelId", "order"),
        Index("Chapter_status_idx", "status"),
        {"schema": "public"},
    )


class ChapterBeatPlan(Base):
    __tablename__ = "ChapterBeatPlan"
    chapterAcceptanceCriteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    chapterGoal: Mapped[str] = mapped_column(Text, nullable=False)
    chapterId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Chapter.id",
            name="ChapterBeatPlan_chapterId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    generatedBy: Mapped[str | None] = mapped_column(Text, nullable=True)
    goalId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.ChapterWritingGoal.id",
            name="ChapterBeatPlan_goalId_fkey",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    mainPlotConnection: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        PG_ENUM(
            "draft",
            "reviewing",
            "approved",
            "rejected",
            "superseded",
            name="BeatPlanStatus",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'draft'::\"BeatPlanStatus\""),
    )
    totalEstimatedWords: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    chapter: Mapped[Chapter] = relationship(
        back_populates="beatPlans",
        foreign_keys=lambda: [ChapterBeatPlan.chapterId],
    )
    goal: Mapped[ChapterWritingGoal | None] = relationship(
        back_populates="beatPlans",
        foreign_keys=lambda: [ChapterBeatPlan.goalId],
    )
    sceneBeats: Mapped[list[SceneBeat]] = relationship(
        back_populates="beatPlan",
        foreign_keys=lambda: [SceneBeat.beatPlanId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="ChapterBeatPlan_pkey",
        ),
        Index("ChapterBeatPlan_chapterId_idx", "chapterId"),
        Index("ChapterBeatPlan_status_idx", "status"),
        {"schema": "public"},
    )


class ChapterProgress(Base):
    __tablename__ = "ChapterProgress"
    chapterId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Chapter.id",
            name="ChapterProgress_chapterId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    chapter: Mapped[Chapter] = relationship(
        back_populates="chapterProgress",
        foreign_keys=lambda: [ChapterProgress.chapterId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="ChapterProgress_pkey",
        ),
        Index("ChapterProgress_chapterId_key", "chapterId", unique=True),
        {"schema": "public"},
    )


class ChapterQualityCheck(Base):
    __tablename__ = "ChapterQualityCheck"
    chapterId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Chapter.id",
            name="ChapterQualityCheck_chapterId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    qualityGate: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    rewriteBrief: Mapped[str | None] = mapped_column(Text, nullable=True)
    scoreEndingHook: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scoreHook: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scoreOverall: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scorePacing: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scorePayoff: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scoreReaderPromise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scoreTension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        PG_ENUM(
            "pending",
            "running",
            "completed",
            "skipped",
            "failed",
            name="QualityCheckStatus",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'pending'::\"QualityCheckStatus\""),
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(
        PG_ENUM(
            "consistency",
            "lore_sync",
            "editorial",
            "craft",
            name="QualityCheckType",
            create_type=False,
        ),
        nullable=False,
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    chapter: Mapped[Chapter] = relationship(
        back_populates="qualityChecks",
        foreign_keys=lambda: [ChapterQualityCheck.chapterId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="ChapterQualityCheck_pkey",
        ),
        Index("ChapterQualityCheck_chapterId_idx", "chapterId"),
        Index("ChapterQualityCheck_chapterId_type_key", "chapterId", "type", unique=True),
        Index("ChapterQualityCheck_status_idx", "status"),
        {"schema": "public"},
    )


class ChapterWritingGoal(Base):
    __tablename__ = "ChapterWritingGoal"
    chapterId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Chapter.id",
            name="ChapterWritingGoal_chapterId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    desiredEmotion: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    narrativeGoal: Mapped[str] = mapped_column(Text, nullable=False)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="ChapterWritingGoal_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    requiredCharacters: Mapped[str | None] = mapped_column(Text, nullable=True)
    requiredForeshadowing: Mapped[str | None] = mapped_column(Text, nullable=True)
    specialNotes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )
    wordCountMax: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wordCountMin: Mapped[int | None] = mapped_column(Integer, nullable=True)

    beatPlans: Mapped[list[ChapterBeatPlan]] = relationship(
        back_populates="goal",
        foreign_keys=lambda: [ChapterBeatPlan.goalId],
    )
    chapter: Mapped[Chapter] = relationship(
        back_populates="writingGoals",
        foreign_keys=lambda: [ChapterWritingGoal.chapterId],
    )
    novel: Mapped[Novel] = relationship(
        back_populates="chapterWritingGoals",
        foreign_keys=lambda: [ChapterWritingGoal.novelId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="ChapterWritingGoal_pkey",
        ),
        Index("ChapterWritingGoal_chapterId_idx", "chapterId"),
        Index("ChapterWritingGoal_novelId_chapterId_idx", "novelId", "chapterId"),
        {"schema": "public"},
    )


class Character(Base):
    __tablename__ = "Character"
    age: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    appearance: Mapped[str | None] = mapped_column(Text, nullable=True)
    background: Mapped[str | None] = mapped_column(Text, nullable=True)
    behaviorBoundaries: Mapped[str | None] = mapped_column(Text, nullable=True)
    combatAbility: Mapped[str | None] = mapped_column(Text, nullable=True)
    coreDesire: Mapped[str | None] = mapped_column(Text, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    currentStatus: Mapped[str] = mapped_column(
        PG_ENUM(
            "active",
            "missing",
            "dead",
            "imprisoned",
            "unknown",
            name="CharacterStatus",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'active'::\"CharacterStatus\""),
    )
    factionId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.Faction.id",
            name="Character_factionId_fkey",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    gender: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    identity: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id", name="Character_novelId_fkey", ondelete="CASCADE", onupdate="CASCADE"
        ),
        nullable=False,
    )
    personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    powerLevel: Mapped[str | None] = mapped_column(Text, nullable=True)
    relationshipPrinciples: Mapped[str | None] = mapped_column(Text, nullable=True)
    shortTermGoal: Mapped[str | None] = mapped_column(Text, nullable=True)
    specialSkills: Mapped[str | None] = mapped_column(Text, nullable=True)
    speechStyle: Mapped[str | None] = mapped_column(Text, nullable=True)
    statusNote: Mapped[str | None] = mapped_column(Text, nullable=True)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    faction: Mapped[Faction | None] = relationship(
        back_populates="characters",
        foreign_keys=lambda: [Character.factionId],
    )
    novel: Mapped[Novel] = relationship(
        back_populates="characters",
        foreign_keys=lambda: [Character.novelId],
    )
    experiences: Mapped[list[CharacterExperience]] = relationship(
        back_populates="character",
        foreign_keys=lambda: [CharacterExperience.characterId],
    )
    outgoingRelations: Mapped[list[CharacterRelation]] = relationship(
        back_populates="character",
        foreign_keys=lambda: [CharacterRelation.characterId],
    )
    incomingRelations: Mapped[list[CharacterRelation]] = relationship(
        back_populates="target",
        foreign_keys=lambda: [CharacterRelation.targetId],
    )
    stateChanges: Mapped[list[CharacterStateChange]] = relationship(
        back_populates="character",
        foreign_keys=lambda: [CharacterStateChange.characterId],
    )
    ownedItems: Mapped[list[Item]] = relationship(
        back_populates="owner",
        foreign_keys=lambda: [Item.ownerId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="Character_pkey",
        ),
        Index("Character_currentStatus_idx", "currentStatus"),
        Index("Character_factionId_idx", "factionId"),
        Index("Character_novelId_idx", "novelId"),
        {"schema": "public"},
    )


class CharacterExperience(Base):
    __tablename__ = "CharacterExperience"
    chapterId: Mapped[str | None] = mapped_column(Text, nullable=True)
    characterId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Character.id",
            name="CharacterExperience_characterId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    character: Mapped[Character] = relationship(
        back_populates="experiences",
        foreign_keys=lambda: [CharacterExperience.characterId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="CharacterExperience_pkey",
        ),
        Index("CharacterExperience_chapterId_idx", "chapterId"),
        Index("CharacterExperience_characterId_idx", "characterId"),
        {"schema": "public"},
    )


class CharacterRelation(Base):
    __tablename__ = "CharacterRelation"
    characterId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Character.id",
            name="CharacterRelation_characterId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    endDate: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    intimacy: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    relationType: Mapped[str] = mapped_column(
        PG_ENUM(
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
            name="RelationType",
            create_type=False,
        ),
        nullable=False,
    )
    startDate: Mapped[str | None] = mapped_column(Text, nullable=True)
    targetId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Character.id",
            name="CharacterRelation_targetId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    character: Mapped[Character] = relationship(
        back_populates="outgoingRelations",
        foreign_keys=lambda: [CharacterRelation.characterId],
    )
    target: Mapped[Character] = relationship(
        back_populates="incomingRelations",
        foreign_keys=lambda: [CharacterRelation.targetId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="CharacterRelation_pkey",
        ),
        Index("CharacterRelation_characterId_idx", "characterId"),
        Index("CharacterRelation_relationType_idx", "relationType"),
        Index("CharacterRelation_targetId_idx", "targetId"),
        {"schema": "public"},
    )


class CharacterStateChange(Base):
    __tablename__ = "CharacterStateChange"
    afterState: Mapped[str] = mapped_column(Text, nullable=False)
    beforeState: Mapped[str | None] = mapped_column(Text, nullable=True)
    changeType: Mapped[str] = mapped_column(Text, nullable=False)
    chapterId: Mapped[str | None] = mapped_column(Text, nullable=True)
    characterId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Character.id",
            name="CharacterStateChange_characterId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)

    character: Mapped[Character] = relationship(
        back_populates="stateChanges",
        foreign_keys=lambda: [CharacterStateChange.characterId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="CharacterStateChange_pkey",
        ),
        Index("CharacterStateChange_chapterId_idx", "chapterId"),
        Index("CharacterStateChange_characterId_idx", "characterId"),
        {"schema": "public"},
    )


class CreditLedger(Base):
    __tablename__ = "CreditLedger"
    agentId: Mapped[str | None] = mapped_column(Text, nullable=True)
    amountMicros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balanceAfterMicros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cachedTokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completionTokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    novelId: Mapped[str | None] = mapped_column(Text, nullable=True)
    promptTokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    requestId: Mapped[str | None] = mapped_column(Text, nullable=True)
    totalTokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    type: Mapped[str] = mapped_column(Text, nullable=False)
    userId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.User.id",
            name="CreditLedger_userId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )

    user: Mapped[User] = relationship(
        back_populates="creditLedgerEntries",
        foreign_keys=lambda: [CreditLedger.userId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="CreditLedger_pkey",
        ),
        Index("CreditLedger_requestId_idx", "requestId"),
        Index("CreditLedger_type_idx", "type"),
        Index("CreditLedger_userId_createdAt_idx", "userId", "createdAt"),
        Index("CreditLedger_userId_idx", "userId"),
        {"schema": "public"},
    )


class Faction(Base):
    __tablename__ = "Faction"
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    baseId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.Location.id",
            name="Faction_baseId_fkey",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id", name="Faction_novelId_fkey", ondelete="CASCADE", onupdate="CASCADE"
        ),
        nullable=False,
    )
    type: Mapped[str | None] = mapped_column(Text, nullable=True)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    characters: Mapped[list[Character]] = relationship(
        back_populates="faction",
        foreign_keys=lambda: [Character.factionId],
    )
    base: Mapped[Location | None] = relationship(
        back_populates="basedFactions",
        foreign_keys=lambda: [Faction.baseId],
    )
    novel: Mapped[Novel] = relationship(
        back_populates="factions",
        foreign_keys=lambda: [Faction.novelId],
    )
    territories: Mapped[list[Location]] = relationship(
        secondary=faction_territories,
        primaryjoin=lambda: Faction.id == faction_territories.c.A,
        secondaryjoin=lambda: Location.id == faction_territories.c.B,
        back_populates="factions",
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="Faction_pkey",
        ),
        Index("Faction_baseId_idx", "baseId"),
        Index("Faction_novelId_idx", "novelId"),
        {"schema": "public"},
    )


class Foreshadowing(Base):
    __tablename__ = "Foreshadowing"
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    expectedPayoff: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="Foreshadowing_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    payoffAt: Mapped[str | None] = mapped_column(Text, nullable=True)
    plantedAt: Mapped[str | None] = mapped_column(Text, nullable=True)
    plantedContent: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        PG_ENUM("active", "paid_off", "abandoned", name="ForeshadowingStatus", create_type=False),
        nullable=False,
        server_default=text("'active'::\"ForeshadowingStatus\""),
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    novel: Mapped[Novel] = relationship(
        back_populates="foreshadowings",
        foreign_keys=lambda: [Foreshadowing.novelId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="Foreshadowing_pkey",
        ),
        Index("Foreshadowing_novelId_idx", "novelId"),
        Index("Foreshadowing_status_idx", "status"),
        {"schema": "public"},
    )


class Glossary(Base):
    __tablename__ = "Glossary"
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id", name="Glossary_novelId_fkey", ondelete="CASCADE", onupdate="CASCADE"
        ),
        nullable=False,
    )
    term: Mapped[str] = mapped_column(Text, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    novel: Mapped[Novel] = relationship(
        back_populates="glossaryEntries",
        foreign_keys=lambda: [Glossary.novelId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="Glossary_pkey",
        ),
        Index("Glossary_novelId_idx", "novelId"),
        {"schema": "public"},
    )


class Item(Base):
    __tablename__ = "Item"
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id", name="Item_novelId_fkey", ondelete="CASCADE", onupdate="CASCADE"
        ),
        nullable=False,
    )
    origin: Mapped[str | None] = mapped_column(Text, nullable=True)
    ownerId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.Character.id", name="Item_ownerId_fkey", ondelete="SET NULL", onupdate="CASCADE"
        ),
        nullable=True,
    )
    rarity: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str | None] = mapped_column(Text, nullable=True)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    novel: Mapped[Novel] = relationship(
        back_populates="items",
        foreign_keys=lambda: [Item.novelId],
    )
    owner: Mapped[Character | None] = relationship(
        back_populates="ownedItems",
        foreign_keys=lambda: [Item.ownerId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="Item_pkey",
        ),
        Index("Item_novelId_idx", "novelId"),
        Index("Item_ownerId_idx", "ownerId"),
        {"schema": "public"},
    )


class Location(Base):
    __tablename__ = "Location"
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    climate: Mapped[str | None] = mapped_column(Text, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    culture: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id", name="Location_novelId_fkey", ondelete="CASCADE", onupdate="CASCADE"
        ),
        nullable=False,
    )
    parentId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.Location.id",
            name="Location_parentId_fkey",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    type: Mapped[str | None] = mapped_column(Text, nullable=True)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    basedFactions: Mapped[list[Faction]] = relationship(
        back_populates="base",
        foreign_keys=lambda: [Faction.baseId],
    )
    novel: Mapped[Novel] = relationship(
        back_populates="locations",
        foreign_keys=lambda: [Location.novelId],
    )
    parent: Mapped[Location | None] = relationship(
        back_populates="children",
        foreign_keys=lambda: [Location.parentId],
        remote_side=lambda: [Location.id],
    )
    children: Mapped[list[Location]] = relationship(
        back_populates="parent",
        foreign_keys=lambda: [Location.parentId],
    )
    factions: Mapped[list[Faction]] = relationship(
        secondary=faction_territories,
        primaryjoin=lambda: Location.id == faction_territories.c.B,
        secondaryjoin=lambda: Faction.id == faction_territories.c.A,
        back_populates="territories",
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="Location_pkey",
        ),
        Index("Location_novelId_idx", "novelId"),
        Index("Location_parentId_idx", "parentId"),
        {"schema": "public"},
    )


class Novel(Base):
    __tablename__ = "Novel"
    appliedStyleId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.WritingStyle.id",
            name="Novel_appliedStyleId_fkey",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    storyProgress: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )
    userId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.User.id", name="Novel_userId_fkey", ondelete="SET NULL", onupdate="CASCADE"
        ),
        nullable=True,
    )

    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [Chapter.novelId],
    )
    chapterWritingGoals: Mapped[list[ChapterWritingGoal]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [ChapterWritingGoal.novelId],
    )
    characters: Mapped[list[Character]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [Character.novelId],
    )
    factions: Mapped[list[Faction]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [Faction.novelId],
    )
    foreshadowings: Mapped[list[Foreshadowing]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [Foreshadowing.novelId],
    )
    glossaryEntries: Mapped[list[Glossary]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [Glossary.novelId],
    )
    items: Mapped[list[Item]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [Item.novelId],
    )
    locations: Mapped[list[Location]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [Location.novelId],
    )
    appliedStyle: Mapped[WritingStyle | None] = relationship(
        back_populates="novels",
        foreign_keys=lambda: [Novel.appliedStyleId],
    )
    user: Mapped[User | None] = relationship(
        back_populates="novels",
        foreign_keys=lambda: [Novel.userId],
    )
    outline: Mapped[Outline | None] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [Outline.novelId],
    )
    outlineNodes: Mapped[list[OutlineNode]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [OutlineNode.novelId],
    )
    plotProgress: Mapped[PlotProgress | None] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [PlotProgress.novelId],
    )
    ragChunks: Mapped[list[RagChunk]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [RagChunk.novelId],
    )
    ragDocuments: Mapped[list[RagDocument]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [RagDocument.novelId],
    )
    referenceMaterials: Mapped[list[ReferenceMaterial]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [ReferenceMaterial.novelId],
    )
    reviewArtifacts: Mapped[list[ReviewArtifact]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [ReviewArtifact.novelId],
    )
    storyBackground: Mapped[StoryBackground | None] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [StoryBackground.novelId],
    )
    workflowRuns: Mapped[list[WorkflowRun]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [WorkflowRun.novelId],
    )
    worldSetting: Mapped[WorldSetting | None] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [WorldSetting.novelId],
    )
    writingBible: Mapped[WritingBible | None] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [WritingBible.novelId],
    )
    writingConfig: Mapped[WritingConfig | None] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [WritingConfig.novelId],
    )
    writingSessions: Mapped[list[WritingSession]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [WritingSession.novelId],
    )
    writingTasks: Mapped[list[WritingTask]] = relationship(
        back_populates="novel",
        foreign_keys=lambda: [WritingTask.novelId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="Novel_pkey",
        ),
        Index("Novel_userId_idx", "userId"),
        {"schema": "public"},
    )


class Outline(Base):
    __tablename__ = "Outline"
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id", name="Outline_novelId_fkey", ondelete="CASCADE", onupdate="CASCADE"
        ),
        nullable=False,
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    novel: Mapped[Novel] = relationship(
        back_populates="outline",
        foreign_keys=lambda: [Outline.novelId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="Outline_pkey",
        ),
        Index("Outline_novelId_key", "novelId", unique=True),
        {"schema": "public"},
    )


class OutlineNode(Base):
    __tablename__ = "OutlineNode"
    actualWordCount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chapterEndOrder: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chapterStartOrder: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    estimatedWordCount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    kind: Mapped[str] = mapped_column(
        PG_ENUM("stage", "plot_unit", "chapter_group", name="OutlineNodeKind", create_type=False),
        nullable=False,
        server_default=text("'stage'::\"OutlineNodeKind\""),
    )
    linkedChapterId: Mapped[str | None] = mapped_column(Text, nullable=True)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="OutlineNode_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    parentId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.OutlineNode.id",
            name="OutlineNode_parentId_fkey",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        PG_ENUM(
            "planned",
            "in_progress",
            "completed",
            "skipped",
            name="OutlineNodeStatus",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'planned'::\"OutlineNodeStatus\""),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    novel: Mapped[Novel] = relationship(
        back_populates="outlineNodes",
        foreign_keys=lambda: [OutlineNode.novelId],
    )
    parent: Mapped[OutlineNode | None] = relationship(
        back_populates="children",
        foreign_keys=lambda: [OutlineNode.parentId],
        remote_side=lambda: [OutlineNode.id],
    )
    children: Mapped[list[OutlineNode]] = relationship(
        back_populates="parent",
        foreign_keys=lambda: [OutlineNode.parentId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="OutlineNode_pkey",
        ),
        Index("OutlineNode_novelId_idx", "novelId"),
        Index(
            "OutlineNode_novelId_kind_chapterStartOrder_chapterEndOrder_idx",
            "novelId",
            "kind",
            "chapterStartOrder",
            "chapterEndOrder",
        ),
        Index("OutlineNode_novelId_kind_idx", "novelId", "kind"),
        Index("OutlineNode_parentId_idx", "parentId"),
        Index("OutlineNode_status_idx", "status"),
        {"schema": "public"},
    )


class PlotProgress(Base):
    __tablename__ = "PlotProgress"
    currentConflict: Mapped[str | None] = mapped_column(Text, nullable=True)
    currentGoal: Mapped[str | None] = mapped_column(Text, nullable=True)
    currentStage: Mapped[str] = mapped_column(Text, nullable=False)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    nextMilestone: Mapped[str | None] = mapped_column(Text, nullable=True)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="PlotProgress_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    novel: Mapped[Novel] = relationship(
        back_populates="plotProgress",
        foreign_keys=lambda: [PlotProgress.novelId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="PlotProgress_pkey",
        ),
        Index("PlotProgress_novelId_key", "novelId", unique=True),
        {"schema": "public"},
    )


class RagChunk(Base):
    __tablename__ = "RagChunk"
    charCount: Mapped[int] = mapped_column(Integer, nullable=False)
    chunkIndex: Mapped[int] = mapped_column(Integer, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    documentId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.RagDocument.id",
            name="RagChunk_documentId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    embeddingDimension: Mapped[int] = mapped_column(Integer, nullable=False)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id", name="RagChunk_novelId_fkey", ondelete="CASCADE", onupdate="CASCADE"
        ),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)

    document: Mapped[RagDocument] = relationship(
        back_populates="chunks",
        foreign_keys=lambda: [RagChunk.documentId],
    )
    novel: Mapped[Novel] = relationship(
        back_populates="ragChunks",
        foreign_keys=lambda: [RagChunk.novelId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="RagChunk_pkey",
        ),
        Index("RagChunk_documentId_chunkIndex_key", "documentId", "chunkIndex", unique=True),
        Index("RagChunk_novelId_idx", "novelId"),
        {"schema": "public"},
    )


class RagDocument(Base):
    __tablename__ = "RagDocument"
    contentHash: Mapped[str] = mapped_column(Text, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    errorMessage: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="RagDocument_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    sourceId: Mapped[str] = mapped_column(Text, nullable=False)
    sourceType: Mapped[str] = mapped_column(
        PG_ENUM("reference_material", name="RagSourceType", create_type=False), nullable=False
    )
    status: Mapped[str] = mapped_column(
        PG_ENUM("disabled", "ready", "failed", name="RagDocumentStatus", create_type=False),
        nullable=False,
        server_default=text("'disabled'::\"RagDocumentStatus\""),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    chunks: Mapped[list[RagChunk]] = relationship(
        back_populates="document",
        foreign_keys=lambda: [RagChunk.documentId],
    )
    novel: Mapped[Novel] = relationship(
        back_populates="ragDocuments",
        foreign_keys=lambda: [RagDocument.novelId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="RagDocument_pkey",
        ),
        Index("RagDocument_novelId_sourceType_idx", "novelId", "sourceType"),
        Index("RagDocument_sourceType_sourceId_key", "sourceType", "sourceId", unique=True),
        {"schema": "public"},
    )


class ReferenceMaterial(Base):
    __tablename__ = "ReferenceMaterial"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="ReferenceMaterial_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    sourceUrl: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(
        PG_ENUM(
            "note",
            "web",
            "book",
            "image",
            "custom",
            name="ReferenceMaterialType",
            create_type=False,
        ),
        nullable=False,
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    novel: Mapped[Novel] = relationship(
        back_populates="referenceMaterials",
        foreign_keys=lambda: [ReferenceMaterial.novelId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="ReferenceMaterial_pkey",
        ),
        Index("ReferenceMaterial_novelId_type_idx", "novelId", "type"),
        {"schema": "public"},
    )


class ReviewArtifact(Base):
    __tablename__ = "ReviewArtifact"
    appliedAt: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=True
    )
    artifactKey: Mapped[str | None] = mapped_column(Text, nullable=True)
    chapterId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.Chapter.id",
            name="ReviewArtifact_chapterId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    createdByAgent: Mapped[str | None] = mapped_column(Text, nullable=True)
    diffJson: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    kind: Mapped[str] = mapped_column(
        PG_ENUM(
            "agent_updates",
            "outline_draft",
            "chapter_draft",
            "lore_draft",
            "revision_brief",
            "beat_plan_draft",
            "chapter_content",
            "beat_plan",
            "freeform_markdown",
            name="ReviewArtifactKind",
            create_type=False,
        ),
        nullable=False,
    )
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="ReviewArtifact_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    payloadJson: Mapped[str] = mapped_column(Text, nullable=False)
    reviewerAgent: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(
        PG_ENUM(
            "draft",
            "under_review",
            "awaiting_user",
            "applying",
            "applied",
            name="ReviewArtifactStatus",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'draft'::\"ReviewArtifactStatus\""),
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    taskId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.WritingTask.id",
            name="ReviewArtifact_taskId_fkey",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )
    updatedByAgent: Mapped[str | None] = mapped_column(Text, nullable=True)
    workflowRunId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.WorkflowRun.id",
            name="ReviewArtifact_workflowRunId_fkey",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )

    chapter: Mapped[Chapter | None] = relationship(
        back_populates="reviewArtifacts",
        foreign_keys=lambda: [ReviewArtifact.chapterId],
    )
    novel: Mapped[Novel] = relationship(
        back_populates="reviewArtifacts",
        foreign_keys=lambda: [ReviewArtifact.novelId],
    )
    task: Mapped[WritingTask | None] = relationship(
        back_populates="reviewArtifacts",
        foreign_keys=lambda: [ReviewArtifact.taskId],
    )
    workflowRun: Mapped[WorkflowRun | None] = relationship(
        back_populates="reviewArtifacts",
        foreign_keys=lambda: [ReviewArtifact.workflowRunId],
    )
    evaluations: Mapped[list[ReviewArtifactEvaluation]] = relationship(
        back_populates="artifact",
        foreign_keys=lambda: [ReviewArtifactEvaluation.artifactId],
    )
    revisions: Mapped[list[ReviewArtifactRevision]] = relationship(
        back_populates="artifact",
        foreign_keys=lambda: [ReviewArtifactRevision.artifactId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="ReviewArtifact_pkey",
        ),
        Index("ReviewArtifact_artifactKey_idx", "artifactKey"),
        Index("ReviewArtifact_chapterId_status_idx", "chapterId", "status"),
        Index("ReviewArtifact_novelId_status_idx", "novelId", "status"),
        Index("ReviewArtifact_taskId_idx", "taskId"),
        Index("ReviewArtifact_workflowRunId_idx", "workflowRunId"),
        {"schema": "public"},
    )


class ReviewArtifactEvaluation(Base):
    __tablename__ = "ReviewArtifactEvaluation"
    artifactId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.ReviewArtifact.id",
            name="ReviewArtifactEvaluation_artifactId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    evaluatorAgent: Mapped[str] = mapped_column(Text, nullable=False)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    requiredChanges: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(
        PG_ENUM(
            "pass", "revise", "block", name="ReviewArtifactEvaluationVerdict", create_type=False
        ),
        nullable=False,
    )

    artifact: Mapped[ReviewArtifact] = relationship(
        back_populates="evaluations",
        foreign_keys=lambda: [ReviewArtifactEvaluation.artifactId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="ReviewArtifactEvaluation_pkey",
        ),
        Index("ReviewArtifactEvaluation_artifactId_revision_idx", "artifactId", "revision"),
        Index("ReviewArtifactEvaluation_evaluatorAgent_idx", "evaluatorAgent"),
        {"schema": "public"},
    )


class ReviewArtifactRevision(Base):
    __tablename__ = "ReviewArtifactRevision"
    artifactId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.ReviewArtifact.id",
            name="ReviewArtifactRevision_artifactId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    createdByAgent: Mapped[str | None] = mapped_column(Text, nullable=True)
    diffJson: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    payloadJson: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    artifact: Mapped[ReviewArtifact] = relationship(
        back_populates="revisions",
        foreign_keys=lambda: [ReviewArtifactRevision.artifactId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="ReviewArtifactRevision_pkey",
        ),
        Index("ReviewArtifactRevision_artifactId_idx", "artifactId"),
        Index(
            "ReviewArtifactRevision_artifactId_revision_key", "artifactId", "revision", unique=True
        ),
        {"schema": "public"},
    )


class SceneBeat(Base):
    __tablename__ = "SceneBeat"
    acceptanceCriteria: Mapped[str] = mapped_column(Text, nullable=False)
    beatPlanId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.ChapterBeatPlan.id",
            name="SceneBeat_beatPlanId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    characters: Mapped[str] = mapped_column(Text, nullable=False)
    conflict: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimatedWords: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    foreshadowingRefs: Mapped[str | None] = mapped_column(Text, nullable=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    order: Mapped[int] = mapped_column(Integer, nullable=False)

    beatPlan: Mapped[ChapterBeatPlan] = relationship(
        back_populates="sceneBeats",
        foreign_keys=lambda: [SceneBeat.beatPlanId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="SceneBeat_pkey",
        ),
        Index("SceneBeat_beatPlanId_idx", "beatPlanId"),
        {"schema": "public"},
    )


class StoryBackground(Base):
    __tablename__ = "StoryBackground"
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="StoryBackground_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    novel: Mapped[Novel] = relationship(
        back_populates="storyBackground",
        foreign_keys=lambda: [StoryBackground.novelId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="StoryBackground_pkey",
        ),
        Index("StoryBackground_novelId_key", "novelId", unique=True),
        {"schema": "public"},
    )


class StylePortraitTask(Base):
    __tablename__ = "StylePortraitTask"
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    errorMessage: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'::text")
    )
    styleId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.WritingStyle.id",
            name="StylePortraitTask_styleId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    style: Mapped[WritingStyle] = relationship(
        back_populates="tasks",
        foreign_keys=lambda: [StylePortraitTask.styleId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="StylePortraitTask_pkey",
        ),
        Index("StylePortraitTask_styleId_idx", "styleId"),
        {"schema": "public"},
    )


class StyleReference(Base):
    __tablename__ = "StyleReference"
    charCount: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    errorMessage: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    filepath: Mapped[str] = mapped_column(Text, nullable=False)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ready'::text"))
    styleId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.WritingStyle.id",
            name="StyleReference_styleId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )

    style: Mapped[WritingStyle] = relationship(
        back_populates="references",
        foreign_keys=lambda: [StyleReference.styleId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="StyleReference_pkey",
        ),
        Index("StyleReference_styleId_idx", "styleId"),
        {"schema": "public"},
    )


class TokenUsage(Base):
    __tablename__ = "TokenUsage"
    agentId: Mapped[str | None] = mapped_column(Text, nullable=True)
    cachedTokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completionTokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    model: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    novelId: Mapped[str | None] = mapped_column(Text, nullable=True)
    promptTokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    totalTokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    userId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.User.id", name="TokenUsage_userId_fkey", ondelete="CASCADE", onupdate="CASCADE"
        ),
        nullable=False,
    )

    user: Mapped[User] = relationship(
        back_populates="tokenUsages",
        foreign_keys=lambda: [TokenUsage.userId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="TokenUsage_pkey",
        ),
        Index("TokenUsage_agentId_idx", "agentId"),
        Index("TokenUsage_novelId_idx", "novelId"),
        Index("TokenUsage_userId_createdAt_idx", "userId", "createdAt"),
        Index("TokenUsage_userId_idx", "userId"),
        {"schema": "public"},
    )


class User(Base):
    __tablename__ = "User"
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    creditBalanceMicros: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    passwordHash: Mapped[str] = mapped_column(Text, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )
    username: Mapped[str] = mapped_column(Text, nullable=False)

    creditLedgerEntries: Mapped[list[CreditLedger]] = relationship(
        back_populates="user",
        foreign_keys=lambda: [CreditLedger.userId],
    )
    novels: Mapped[list[Novel]] = relationship(
        back_populates="user",
        foreign_keys=lambda: [Novel.userId],
    )
    tokenUsages: Mapped[list[TokenUsage]] = relationship(
        back_populates="user",
        foreign_keys=lambda: [TokenUsage.userId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="User_pkey",
        ),
        Index("User_username_key", "username", unique=True),
        {"schema": "public"},
    )


class WorkflowRun(Base):
    __tablename__ = "WorkflowRun"
    chapterId: Mapped[str] = mapped_column(Text, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    currentAgentId: Mapped[str | None] = mapped_column(Text, nullable=True)
    errorMessage: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    input: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(
        PG_ENUM(
            "chat",
            "chapter_generation",
            "quality_check",
            "lore_sync",
            "beat_plan",
            name="WorkflowRunKind",
            create_type=False,
        ),
        nullable=False,
    )
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="WorkflowRun_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    sourceId: Mapped[str | None] = mapped_column(Text, nullable=True)
    sourceType: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        PG_ENUM(
            "pending",
            "running",
            "waiting_user",
            "completed",
            "failed",
            "cancelled",
            name="WorkflowRunStatus",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'pending'::\"WorkflowRunStatus\""),
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )
    userId: Mapped[str | None] = mapped_column(Text, nullable=True)

    reviewArtifacts: Mapped[list[ReviewArtifact]] = relationship(
        back_populates="workflowRun",
        foreign_keys=lambda: [ReviewArtifact.workflowRunId],
    )
    novel: Mapped[Novel] = relationship(
        back_populates="workflowRuns",
        foreign_keys=lambda: [WorkflowRun.novelId],
    )
    steps: Mapped[list[WorkflowStep]] = relationship(
        back_populates="run",
        foreign_keys=lambda: [WorkflowStep.runId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="WorkflowRun_pkey",
        ),
        Index("WorkflowRun_chapterId_idx", "chapterId"),
        Index("WorkflowRun_kind_idx", "kind"),
        Index("WorkflowRun_novelId_idx", "novelId"),
        Index("WorkflowRun_status_idx", "status"),
        Index("WorkflowRun_userId_idx", "userId"),
        {"schema": "public"},
    )


class WorkflowStep(Base):
    __tablename__ = "WorkflowStep"
    agentId: Mapped[str | None] = mapped_column(Text, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    durationMs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    input: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    runId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.WorkflowRun.id",
            name="WorkflowStep_runId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        PG_ENUM(
            "pending",
            "running",
            "completed",
            "failed",
            "skipped",
            name="WorkflowStepStatus",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'pending'::\"WorkflowStepStatus\""),
    )
    stepType: Mapped[str] = mapped_column(
        PG_ENUM(
            "agent",
            "tool",
            "user_confirmation",
            "persistence",
            name="WorkflowStepType",
            create_type=False,
        ),
        nullable=False,
    )

    run: Mapped[WorkflowRun] = relationship(
        back_populates="steps",
        foreign_keys=lambda: [WorkflowStep.runId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="WorkflowStep_pkey",
        ),
        Index("WorkflowStep_runId_idx", "runId"),
        {"schema": "public"},
    )


class WorldSetting(Base):
    __tablename__ = "WorldSetting"
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="WorldSetting_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    novel: Mapped[Novel] = relationship(
        back_populates="worldSetting",
        foreign_keys=lambda: [WorldSetting.novelId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="WorldSetting_pkey",
        ),
        Index("WorldSetting_novelId_key", "novelId", unique=True),
        {"schema": "public"},
    )


class WritingBible(Base):
    __tablename__ = "WritingBible"
    appealModel: Mapped[str | None] = mapped_column(Text, nullable=True)
    comparableTitles: Mapped[str | None] = mapped_column(Text, nullable=True)
    coreSellingPoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    genre: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="WritingBible_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    readerPromise: Mapped[str | None] = mapped_column(Text, nullable=True)
    storyLengthProfile: Mapped[str] = mapped_column(
        PG_ENUM("short_medium", "long_serial", name="StoryLengthProfile", create_type=False),
        nullable=False,
        server_default=text("'long_serial'::\"StoryLengthProfile\""),
    )
    taboo: Mapped[str | None] = mapped_column(Text, nullable=True)
    targetReaders: Mapped[str | None] = mapped_column(Text, nullable=True)
    targetTotalWordCount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    novel: Mapped[Novel] = relationship(
        back_populates="writingBible",
        foreign_keys=lambda: [WritingBible.novelId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="WritingBible_pkey",
        ),
        Index("WritingBible_novelId_key", "novelId", unique=True),
        {"schema": "public"},
    )


class WritingConfig(Base):
    __tablename__ = "WritingConfig"
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    defaultWordCount: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("4000")
    )
    enabledAgents: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'设定,剧情,写作,校验,编辑'::text")
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="WritingConfig_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    novel: Mapped[Novel] = relationship(
        back_populates="writingConfig",
        foreign_keys=lambda: [WritingConfig.novelId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="WritingConfig_pkey",
        ),
        Index("WritingConfig_novelId_key", "novelId", unique=True),
        {"schema": "public"},
    )


class WritingMessage(Base):
    __tablename__ = "WritingMessage"
    agentId: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)
    parentId: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    sessionId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.WritingSession.id",
            name="WritingMessage_sessionId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )

    session: Mapped[WritingSession] = relationship(
        back_populates="messages",
        foreign_keys=lambda: [WritingMessage.sessionId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="WritingMessage_pkey",
        ),
        Index("WritingMessage_sessionId_createdAt_idx", "sessionId", "createdAt"),
        {"schema": "public"},
    )


class WritingSession(Base):
    __tablename__ = "WritingSession"
    chapterId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Chapter.id",
            name="WritingSession_chapterId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="WritingSession_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    phase: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'idle'::text"))
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    messages: Mapped[list[WritingMessage]] = relationship(
        back_populates="session",
        foreign_keys=lambda: [WritingMessage.sessionId],
    )
    chapter: Mapped[Chapter] = relationship(
        back_populates="writingSessions",
        foreign_keys=lambda: [WritingSession.chapterId],
    )
    novel: Mapped[Novel] = relationship(
        back_populates="writingSessions",
        foreign_keys=lambda: [WritingSession.novelId],
    )
    tasks: Mapped[list[WritingTask]] = relationship(
        back_populates="writingSession",
        foreign_keys=lambda: [WritingTask.writingSessionId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="WritingSession_pkey",
        ),
        Index("WritingSession_chapterId_idx", "chapterId"),
        Index("WritingSession_novelId_idx", "novelId"),
        {"schema": "public"},
    )


class WritingStyle(Base):
    __tablename__ = "WritingStyle"
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    creativeMethodology: Mapped[str | None] = mapped_column(Text, nullable=True)
    errorMessage: Mapped[str | None] = mapped_column(Text, nullable=True)
    expressionFeatures: Mapped[str | None] = mapped_column(Text, nullable=True)
    generationStyle: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    originalCharCount: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    portraitMarkdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    sourceType: Mapped[str] = mapped_column(
        PG_ENUM("manual", "agent", name="StyleSourceType", create_type=False),
        nullable=False,
        server_default=text("'manual'::\"StyleSourceType\""),
    )
    styleTraits: Mapped[str | None] = mapped_column(Text, nullable=True)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    uniqueMarkers: Mapped[str | None] = mapped_column(Text, nullable=True)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )
    usedCharCount: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    novels: Mapped[list[Novel]] = relationship(
        back_populates="appliedStyle",
        foreign_keys=lambda: [Novel.appliedStyleId],
    )
    tasks: Mapped[list[StylePortraitTask]] = relationship(
        back_populates="style",
        foreign_keys=lambda: [StylePortraitTask.styleId],
    )
    references: Mapped[list[StyleReference]] = relationship(
        back_populates="style",
        foreign_keys=lambda: [StyleReference.styleId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="WritingStyle_pkey",
        ),
        {"schema": "public"},
    )


class WritingTask(Base):
    __tablename__ = "WritingTask"
    agentOutputs: Mapped[str | None] = mapped_column(Text, nullable=True)
    chapterId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Chapter.id",
            name="WritingTask_chapterId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    characterChanges: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversationHistory: Mapped[str | None] = mapped_column(Text, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    finalContent: Mapped[str | None] = mapped_column(Text, nullable=True)
    foreshadowingUpdates: Mapped[str | None] = mapped_column(Text, nullable=True)
    generatedContent: Mapped[str | None] = mapped_column(Text, nullable=True)
    graphStateJson: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="WritingTask_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    outlineUpdates: Mapped[str | None] = mapped_column(Text, nullable=True)
    phase: Mapped[str] = mapped_column(
        PG_ENUM(
            "idle",
            "active",
            "waiting_call",
            "awaiting_user_review",
            "completed",
            "error",
            name="WritingTaskPhase",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'idle'::\"WritingTaskPhase\""),
    )
    selectedAgents: Mapped[str] = mapped_column(Text, nullable=False)
    targetWordCount: Mapped[int] = mapped_column(Integer, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )
    writingSessionId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.WritingSession.id",
            name="WritingTask_writingSessionId_fkey",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )

    reviewArtifacts: Mapped[list[ReviewArtifact]] = relationship(
        back_populates="task",
        foreign_keys=lambda: [ReviewArtifact.taskId],
    )
    chapter: Mapped[Chapter] = relationship(
        back_populates="writingTasks",
        foreign_keys=lambda: [WritingTask.chapterId],
    )
    novel: Mapped[Novel] = relationship(
        back_populates="writingTasks",
        foreign_keys=lambda: [WritingTask.novelId],
    )
    writingSession: Mapped[WritingSession | None] = relationship(
        back_populates="tasks",
        foreign_keys=lambda: [WritingTask.writingSessionId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="WritingTask_pkey",
        ),
        Index("WritingTask_chapterId_idx", "chapterId"),
        Index("WritingTask_novelId_idx", "novelId"),
        Index("WritingTask_writingSessionId_idx", "writingSessionId"),
        {"schema": "public"},
    )
