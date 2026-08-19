from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
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
        cascade="all, delete",
        passive_deletes=True,
        back_populates="chapter",
        foreign_keys=lambda: [ChapterBeatPlan.chapterId],
    )
    chapterProgress: Mapped[ChapterProgress | None] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="chapter",
        foreign_keys=lambda: [ChapterProgress.chapterId],
    )
    qualityChecks: Mapped[list[ChapterQualityCheck]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="chapter",
        foreign_keys=lambda: [ChapterQualityCheck.chapterId],
    )
    writingGoals: Mapped[list[ChapterWritingGoal]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="chapter",
        foreign_keys=lambda: [ChapterWritingGoal.chapterId],
    )
    reviewArtifacts: Mapped[list[ReviewArtifact]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="chapter",
        foreign_keys=lambda: [ReviewArtifact.chapterId],
    )
    writingSessions: Mapped[list[WritingSession]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="chapter",
        foreign_keys=lambda: [WritingSession.chapterId],
    )
    writingTasks: Mapped[list[WritingTask]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="chapter",
        foreign_keys=lambda: [WritingTask.chapterId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="Chapter_pkey",
        ),
        Index("Chapter_id_novelId_key", "id", "novelId", unique=True),
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
        cascade="all, delete",
        passive_deletes=True,
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
        passive_deletes=True,
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
        cascade="all, delete",
        passive_deletes=True,
        back_populates="character",
        foreign_keys=lambda: [CharacterExperience.characterId],
    )
    outgoingRelations: Mapped[list[CharacterRelation]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="character",
        foreign_keys=lambda: [CharacterRelation.characterId],
    )
    incomingRelations: Mapped[list[CharacterRelation]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="target",
        foreign_keys=lambda: [CharacterRelation.targetId],
    )
    stateChanges: Mapped[list[CharacterStateChange]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="character",
        foreign_keys=lambda: [CharacterStateChange.characterId],
    )
    ownedItems: Mapped[list[Item]] = relationship(
        passive_deletes=True,
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
        passive_deletes=True,
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
        passive_deletes=True,
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
        passive_deletes=True,
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
        passive_deletes=True,
        back_populates="parent",
        foreign_keys=lambda: [Location.parentId],
    )
    factions: Mapped[list[Faction]] = relationship(
        passive_deletes=True,
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
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [Chapter.novelId],
    )
    chapterWritingGoals: Mapped[list[ChapterWritingGoal]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [ChapterWritingGoal.novelId],
    )
    characters: Mapped[list[Character]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [Character.novelId],
    )
    factions: Mapped[list[Faction]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [Faction.novelId],
    )
    foreshadowings: Mapped[list[Foreshadowing]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [Foreshadowing.novelId],
    )
    glossaryEntries: Mapped[list[Glossary]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [Glossary.novelId],
    )
    items: Mapped[list[Item]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [Item.novelId],
    )
    locations: Mapped[list[Location]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
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
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [Outline.novelId],
    )
    outlineNodes: Mapped[list[OutlineNode]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [OutlineNode.novelId],
    )
    plotProgress: Mapped[PlotProgress | None] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [PlotProgress.novelId],
    )
    ragChunks: Mapped[list[RagChunk]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [RagChunk.novelId],
    )
    ragDocuments: Mapped[list[RagDocument]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [RagDocument.novelId],
    )
    referenceMaterials: Mapped[list[ReferenceMaterial]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [ReferenceMaterial.novelId],
    )
    reviewArtifacts: Mapped[list[ReviewArtifact]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [ReviewArtifact.novelId],
    )
    storyBackground: Mapped[StoryBackground | None] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [StoryBackground.novelId],
    )
    workflowRuns: Mapped[list[WorkflowRun]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [WorkflowRun.novelId],
    )
    worldSetting: Mapped[WorldSetting | None] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [WorldSetting.novelId],
    )
    writingBible: Mapped[WritingBible | None] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [WritingBible.novelId],
    )
    writingConfig: Mapped[WritingConfig | None] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [WritingConfig.novelId],
    )
    writingSessions: Mapped[list[WritingSession]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [WritingSession.novelId],
    )
    writingTasks: Mapped[list[WritingTask]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="novel",
        foreign_keys=lambda: [WritingTask.novelId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="Novel_pkey",
        ),
        Index("Novel_userId_idx", "userId"),
        Index("Novel_id_userId_key", "id", "userId", unique=True),
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
        passive_deletes=True,
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
        cascade="all, delete",
        passive_deletes=True,
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
            "video_scene_plan",
            "video_adaptation_plan",
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
    # 旧视频方案草案绑定 VideoScene；章节影视化 v2 使用独立 Adaptation/Task 目标。
    videoAdaptationId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.VideoChapterAdaptation.id",
            name="ReviewArtifact_videoAdaptationId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    videoAdaptationTaskId: Mapped[str | None] = mapped_column(Text, nullable=True)
    videoSceneId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.VideoScene.id",
            name="ReviewArtifact_videoSceneId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
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
        cascade="all, delete",
        passive_deletes=True,
        back_populates="artifact",
        foreign_keys=lambda: [ReviewArtifactEvaluation.artifactId],
    )
    revisions: Mapped[list[ReviewArtifactRevision]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="artifact",
        foreign_keys=lambda: [ReviewArtifactRevision.artifactId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="ReviewArtifact_pkey",
        ),
        ForeignKeyConstraint(
            ("videoAdaptationId", "novelId"),
            ("public.VideoChapterAdaptation.id", "public.VideoChapterAdaptation.novelId"),
            name="ReviewArtifact_video_adaptation_novel_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("videoAdaptationTaskId", "videoAdaptationId"),
            ("public.VideoAdaptationTask.id", "public.VideoAdaptationTask.adaptationId"),
            name="ReviewArtifact_video_adaptation_task_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("videoSceneId", "novelId"),
            ("public.VideoScene.id", "public.VideoScene.novelId"),
            name="ReviewArtifact_video_scene_novel_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        Index("ReviewArtifact_artifactKey_idx", "artifactKey"),
        Index("ReviewArtifact_chapterId_status_idx", "chapterId", "status"),
        Index("ReviewArtifact_novelId_status_idx", "novelId", "status"),
        Index("ReviewArtifact_taskId_idx", "taskId"),
        Index(
            "ReviewArtifact_id_videoAdaptationId_key",
            "id",
            "videoAdaptationId",
            unique=True,
        ),
        Index(
            "ReviewArtifact_videoAdaptationId_status_idx",
            "videoAdaptationId",
            "status",
        ),
        Index("ReviewArtifact_videoSceneId_status_idx", "videoSceneId", "status"),
        Index(
            "ReviewArtifact_id_videoSceneId_key",
            "id",
            "videoSceneId",
            unique=True,
        ),
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
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        cascade="all, delete",
        passive_deletes=True,
        back_populates="user",
        foreign_keys=lambda: [CreditLedger.userId],
    )
    novels: Mapped[list[Novel]] = relationship(
        passive_deletes=True,
        back_populates="user",
        foreign_keys=lambda: [Novel.userId],
    )
    tokenUsages: Mapped[list[TokenUsage]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="user",
        foreign_keys=lambda: [TokenUsage.userId],
    )
    writingStyles: Mapped[list[WritingStyle]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="user",
        foreign_keys=lambda: [WritingStyle.userId],
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
        passive_deletes=True,
        back_populates="workflowRun",
        foreign_keys=lambda: [ReviewArtifact.workflowRunId],
    )
    novel: Mapped[Novel] = relationship(
        back_populates="workflowRuns",
        foreign_keys=lambda: [WorkflowRun.novelId],
    )
    steps: Mapped[list[WorkflowStep]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
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
        cascade="all, delete",
        passive_deletes=True,
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
        passive_deletes=True,
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
    userId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.User.id",
            name="WritingStyle_userId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )

    novels: Mapped[list[Novel]] = relationship(
        passive_deletes=True,
        back_populates="appliedStyle",
        foreign_keys=lambda: [Novel.appliedStyleId],
    )
    tasks: Mapped[list[StylePortraitTask]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="style",
        foreign_keys=lambda: [StylePortraitTask.styleId],
    )
    references: Mapped[list[StyleReference]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="style",
        foreign_keys=lambda: [StyleReference.styleId],
    )
    user: Mapped[User] = relationship(
        back_populates="writingStyles",
        foreign_keys=lambda: [WritingStyle.userId],
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="WritingStyle_pkey",
        ),
        Index("WritingStyle_userId_createdAt_idx", "userId", "createdAt"),
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
        passive_deletes=True,
        back_populates="task",
        foreign_keys=lambda: [ReviewArtifact.taskId],
    )
    commands: Mapped[list[WritingRunCommand]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="task",
        foreign_keys=lambda: [WritingRunCommand.taskId],
    )
    outboxEvents: Mapped[list[WritingEventOutbox]] = relationship(
        cascade="all, delete",
        passive_deletes=True,
        back_populates="task",
        foreign_keys=lambda: [WritingEventOutbox.taskId],
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


class WritingRunCommand(Base):
    __tablename__ = "WritingRunCommand"
    artifactId: Mapped[str | None] = mapped_column(Text, nullable=True)
    attemptCount: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completedAt: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=True
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    idempotencyKey: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    lastError: Mapped[str | None] = mapped_column(Text, nullable=True)
    nextAttemptAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    payloadJson: Mapped[str] = mapped_column(Text, nullable=False)
    resultJson: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'::text")
    )
    submittedAt: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=True
    )
    taskId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.WritingTask.id",
            name="WritingRunCommand_taskId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    task: Mapped[WritingTask] = relationship(
        back_populates="commands",
        foreign_keys=lambda: [WritingRunCommand.taskId],
    )
    outboxEvents: Mapped[list[WritingEventOutbox]] = relationship(
        passive_deletes=True,
        back_populates="command",
        foreign_keys=lambda: [WritingEventOutbox.commandId],
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="WritingRunCommand_pkey"),
        Index("WritingRunCommand_idempotencyKey_key", "idempotencyKey", unique=True),
        Index("WritingRunCommand_due_idx", "status", "nextAttemptAt"),
        Index(
            "WritingRunCommand_active_task_key",
            "taskId",
            unique=True,
            postgresql_where=text("\"status\" IN ('pending', 'submitted', 'processing')"),
        ),
        {"schema": "public"},
    )


class WritingEventOutbox(Base):
    __tablename__ = "WritingEventOutbox"
    attemptCount: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    commandId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.WritingRunCommand.id",
            name="WritingEventOutbox_commandId_fkey",
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
    dedupeKey: Mapped[str] = mapped_column(Text, nullable=False)
    deliveryState: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'::text")
    )
    durableBaseline: Mapped[int] = mapped_column(Integer, nullable=False)
    eventType: Mapped[str] = mapped_column(Text, nullable=False)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    lastErrorCode: Mapped[str | None] = mapped_column(Text, nullable=True)
    leaseExpiresAt: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=True
    )
    leaseToken: Mapped[str | None] = mapped_column(Text, nullable=True)
    nextAttemptAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    payloadJson: Mapped[str] = mapped_column(Text, nullable=False)
    publishedAt: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=True
    )
    redisEventId: Mapped[str | None] = mapped_column(Text, nullable=True)
    sourceEventId: Mapped[str] = mapped_column(Text, nullable=False)
    sourceSequence: Mapped[int] = mapped_column(Integer, nullable=False)
    taskId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.WritingTask.id",
            name="WritingEventOutbox_taskId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    task: Mapped[WritingTask] = relationship(
        back_populates="outboxEvents",
        foreign_keys=lambda: [WritingEventOutbox.taskId],
    )
    command: Mapped[WritingRunCommand | None] = relationship(
        back_populates="outboxEvents",
        foreign_keys=lambda: [WritingEventOutbox.commandId],
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="WritingEventOutbox_pkey"),
        Index(
            "WritingEventOutbox_sourceEventId_key",
            "sourceEventId",
            unique=True,
        ),
        Index("WritingEventOutbox_dedupeKey_key", "dedupeKey", unique=True),
        Index(
            "WritingEventOutbox_taskId_sourceSequence_key",
            "taskId",
            "sourceSequence",
            unique=True,
        ),
        Index(
            "WritingEventOutbox_due_idx",
            "deliveryState",
            "nextAttemptAt",
            "createdAt",
            postgresql_where=text("\"deliveryState\" IN ('pending', 'delivering')"),
        ),
        Index(
            "WritingEventOutbox_task_sequence_idx",
            "taskId",
            "sourceSequence",
        ),
        Index(
            "WritingEventOutbox_publishedAt_idx",
            "publishedAt",
            postgresql_where=text('"publishedAt" IS NOT NULL'),
        ),
        {"schema": "public"},
    )


class VideoProject(Base):
    """小说级视频制作项目，保存正式控制面的项目级状态。"""

    __tablename__ = "VideoProject"
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deletedAt: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=True
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    mode: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'highlight'::text")
    )
    novelId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.Novel.id",
            name="VideoProject_novelId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'seedance_2_5'::text")
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'::text"))
    targetAspectRatio: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'16:9'::text")
    )
    targetLanguage: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'zh-CN'::text")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoProject_pkey"),
        Index("VideoProject_id_novelId_key", "id", "novelId", unique=True),
        Index(
            "VideoProject_novelId_updatedAt_idx",
            "novelId",
            "updatedAt",
            postgresql_where=text('"deletedAt" IS NULL'),
        ),
        {"schema": "public"},
    )


class VideoScene(Base):
    """绑定不可变原文快照、正式方案和提示词的单个视频场景。"""

    __tablename__ = "VideoScene"
    chapterId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.Chapter.id",
            name="VideoScene_chapterId_fkey",
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
    durationSeconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("15"))
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    lastErrorCode: Mapped[str | None] = mapped_column(Text, nullable=True)
    lastErrorMessage: Mapped[str | None] = mapped_column(Text, nullable=True)
    novelId: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    planJson: Mapped[str | None] = mapped_column(Text, nullable=True)
    projectId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.VideoProject.id",
            name="VideoScene_projectId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    promptCharacterCount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    promptText: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    sourceHash: Mapped[str] = mapped_column(Text, nullable=False)
    sourceText: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'::text"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoScene_pkey"),
        ForeignKeyConstraint(
            ("projectId", "novelId"),
            ("public.VideoProject.id", "public.VideoProject.novelId"),
            name="VideoScene_project_novel_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("chapterId", "novelId"),
            ("public.Chapter.id", "public.Chapter.novelId"),
            name="VideoScene_chapter_novel_fkey",
            ondelete="NO ACTION",
            onupdate="CASCADE",
        ),
        Index("VideoScene_id_novelId_key", "id", "novelId", unique=True),
        Index("VideoScene_id_projectId_key", "id", "projectId", unique=True),
        Index("VideoScene_chapterId_idx", "chapterId"),
        Index("VideoScene_projectId_status_idx", "projectId", "status", "ordinal"),
        Index("VideoScene_project_ordinal_key", "projectId", "ordinal", unique=True),
        {"schema": "public"},
    )


class VideoAsset(Base):
    """具有内容哈希、权利状态和锁定时间的真实多媒体素材。"""

    __tablename__ = "VideoAsset"
    byteSize: Mapped[int] = mapped_column(BigInteger, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    durationMs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duty: Mapped[str] = mapped_column(Text, nullable=False)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    lockedAt: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=True
    )
    mimeType: Mapped[str] = mapped_column(Text, nullable=False)
    modality: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    projectId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.VideoProject.id",
            name="VideoAsset_projectId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    rightsStatus: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'unconfirmed'::text")
    )
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    sourceKind: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'user_upload'::text")
    )
    storageKey: Mapped[str] = mapped_column(Text, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoAsset_pkey"),
        Index("VideoAsset_id_projectId_key", "id", "projectId", unique=True),
        Index("VideoAsset_projectId_modality_idx", "projectId", "modality", "createdAt"),
        Index("VideoAsset_project_storage_key", "projectId", "storageKey", unique=True),
        {"schema": "public"},
    )


class VideoAssetBinding(Base):
    """记录一个场景如何使用某个已上传素材，避免仅靠自然语言猜测职责。"""

    __tablename__ = "VideoAssetBinding"
    assetId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.VideoAsset.id",
            name="VideoAssetBinding_assetId_fkey",
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
    excludeFeaturesJson: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'[]'::text")
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    includeFeaturesJson: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("50"))
    projectId: Mapped[str] = mapped_column(Text, nullable=False)
    sceneId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.VideoScene.id",
            name="VideoAssetBinding_sceneId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    targetEntity: Mapped[str] = mapped_column(Text, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoAssetBinding_pkey"),
        ForeignKeyConstraint(
            ("sceneId", "projectId"),
            ("public.VideoScene.id", "public.VideoScene.projectId"),
            name="VideoAssetBinding_scene_project_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("assetId", "projectId"),
            ("public.VideoAsset.id", "public.VideoAsset.projectId"),
            name="VideoAssetBinding_asset_project_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        Index("VideoAssetBinding_sceneId_priority_idx", "sceneId", "priority", "createdAt"),
        Index("VideoAssetBinding_scene_asset_key", "sceneId", "assetId", unique=True),
        {"schema": "public"},
    )


class VideoGenerationTask(Base):
    """持久化视频规划和供应商任务，Redis 只保存可重建的执行索引。"""

    __tablename__ = "VideoGenerationTask"
    attemptCount: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completedAt: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=True
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    idempotencyKey: Mapped[str] = mapped_column(Text, nullable=False)
    jobId: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    lastErrorCode: Mapped[str | None] = mapped_column(Text, nullable=True)
    lastErrorMessage: Mapped[str | None] = mapped_column(Text, nullable=True)
    nextAttemptAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    projectId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.VideoProject.id",
            name="VideoGenerationTask_projectId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    providerTaskId: Mapped[str | None] = mapped_column(Text, nullable=True)
    requestJson: Mapped[str] = mapped_column(Text, nullable=False)
    resultJson: Mapped[str | None] = mapped_column(Text, nullable=True)
    sceneId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.VideoScene.id",
            name="VideoGenerationTask_sceneId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'::text")
    )
    submittedAt: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=True
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoGenerationTask_pkey"),
        ForeignKeyConstraint(
            ("sceneId", "projectId"),
            ("public.VideoScene.id", "public.VideoScene.projectId"),
            name="VideoGenerationTask_scene_project_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        Index(
            "VideoGenerationTask_due_idx",
            "status",
            "nextAttemptAt",
            "createdAt",
            postgresql_where=text("\"status\" IN ('pending', 'submitted', 'processing')"),
        ),
        Index("VideoGenerationTask_idempotencyKey_key", "idempotencyKey", unique=True),
        Index("VideoGenerationTask_jobId_key", "jobId", unique=True),
        Index(
            "VideoGenerationTask_id_sceneId_projectId_key",
            "id",
            "sceneId",
            "projectId",
            unique=True,
        ),
        Index("VideoGenerationTask_sceneId_createdAt_idx", "sceneId", "createdAt"),
        {"schema": "public"},
    )


class VideoReviewDecisionCommand(Base):
    """服务器 dev 库中同步批准视频候选的开发预览耐久幂等记录。"""

    __tablename__ = "VideoReviewDecisionCommand"
    artifactId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.ReviewArtifact.id",
            name="VideoReviewDecisionCommand_artifactId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    clientRequestId: Mapped[str] = mapped_column(Text, nullable=False)
    completedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    decision: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'approve'::text")
    )
    expectedArtifactRevision: Mapped[int] = mapped_column(Integer, nullable=False)
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    novelId: Mapped[str] = mapped_column(Text, nullable=False)
    projectId: Mapped[str] = mapped_column(Text, nullable=False)
    requestHash: Mapped[str] = mapped_column(Text, nullable=False)
    requestedByUserId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.User.id",
            name="VideoReviewDecisionCommand_requestedByUserId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    resultJson: Mapped[str] = mapped_column(Text, nullable=False)
    sceneId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.VideoScene.id",
            name="VideoReviewDecisionCommand_sceneId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    sourceTaskId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.VideoGenerationTask.id",
            name="VideoReviewDecisionCommand_sourceTaskId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'succeeded'::text")
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoReviewDecisionCommand_pkey"),
        ForeignKeyConstraint(
            ("novelId", "requestedByUserId"),
            ("public.Novel.id", "public.Novel.userId"),
            name="VideoReviewDecisionCommand_novel_owner_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("projectId", "novelId"),
            ("public.VideoProject.id", "public.VideoProject.novelId"),
            name="VideoReviewDecisionCommand_project_novel_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("sceneId", "projectId"),
            ("public.VideoScene.id", "public.VideoScene.projectId"),
            name="VideoReviewDecisionCommand_scene_project_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("artifactId", "sceneId"),
            ("public.ReviewArtifact.id", "public.ReviewArtifact.videoSceneId"),
            name="VideoReviewDecisionCommand_artifact_scene_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("sourceTaskId", "sceneId", "projectId"),
            (
                "public.VideoGenerationTask.id",
                "public.VideoGenerationTask.sceneId",
                "public.VideoGenerationTask.projectId",
            ),
            name="VideoReviewDecisionCommand_task_scene_project_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        Index(
            "VideoReviewDecisionCommand_user_request_key",
            "requestedByUserId",
            "clientRequestId",
            unique=True,
        ),
        Index(
            "VideoReviewDecisionCommand_artifact_revision_idx",
            "artifactId",
            "expectedArtifactRevision",
            "decision",
        ),
        Index(
            "VideoReviewDecisionCommand_scene_created_idx",
            "sceneId",
            "createdAt",
        ),
        {"schema": "public"},
    )


class VideoChapterAdaptation(Base):
    """一个项目对一个不可变章节版本的影视化改编根，不冒充真实场景。"""

    __tablename__ = "VideoChapterAdaptation"
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    projectId: Mapped[str] = mapped_column(Text, nullable=False)
    novelId: Mapped[str] = mapped_column(Text, nullable=False)
    chapterId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.Chapter.id",
            name="VideoChapterAdaptation_chapterId_fkey",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    chapterTitle: Mapped[str] = mapped_column(Text, nullable=False)
    chapterUpdatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False
    )
    sourceText: Mapped[str] = mapped_column(Text, nullable=False)
    sourceHash: Mapped[str] = mapped_column(Text, nullable=False)
    lifecycleStatus: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'active'::text")
    )
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoChapterAdaptation_pkey"),
        ForeignKeyConstraint(
            ("projectId", "novelId"),
            ("public.VideoProject.id", "public.VideoProject.novelId"),
            name="VideoChapterAdaptation_project_novel_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("chapterId", "novelId"),
            ("public.Chapter.id", "public.Chapter.novelId"),
            name="VideoChapterAdaptation_chapter_novel_fkey",
            ondelete="NO ACTION",
            onupdate="CASCADE",
        ),
        Index("VideoChapterAdaptation_id_projectId_key", "id", "projectId", unique=True),
        Index("VideoChapterAdaptation_id_novelId_key", "id", "novelId", unique=True),
        Index(
            "VideoChapterAdaptation_project_chapter_source_key",
            "projectId",
            "chapterId",
            "sourceHash",
            unique=True,
            postgresql_where=text(
                '"chapterId" IS NOT NULL AND "lifecycleStatus" = \'active\''
            ),
        ),
        Index("VideoChapterAdaptation_project_created_idx", "projectId", "createdAt"),
        {"schema": "public"},
    )


class VideoAdaptationTask(Base):
    """章节拆镜与逐镜提示词的耐久任务；Redis 只保存可重建队列索引。"""

    __tablename__ = "VideoAdaptationTask"
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    adaptationId: Mapped[str] = mapped_column(Text, nullable=False)
    projectId: Mapped[str] = mapped_column(Text, nullable=False)
    novelId: Mapped[str] = mapped_column(Text, nullable=False)
    baseShotPlanVersionId: Mapped[str | None] = mapped_column(Text, nullable=True)
    jobId: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    workflow: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'deepseek'::text")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'::text")
    )
    idempotencyKey: Mapped[str] = mapped_column(Text, nullable=False)
    requestJson: Mapped[str] = mapped_column(Text, nullable=False)
    resultJson: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpointStage: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'none'::text")
    )
    checkpointJson: Mapped[str | None] = mapped_column(Text, nullable=True)
    attemptCount: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    nextAttemptAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    lastErrorCode: Mapped[str | None] = mapped_column(Text, nullable=True)
    lastErrorMessage: Mapped[str | None] = mapped_column(Text, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    submittedAt: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=True
    )
    completedAt: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=True
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoAdaptationTask_pkey"),
        ForeignKeyConstraint(
            ("adaptationId", "projectId"),
            ("public.VideoChapterAdaptation.id", "public.VideoChapterAdaptation.projectId"),
            name="VideoAdaptationTask_adaptation_project_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("adaptationId", "novelId"),
            ("public.VideoChapterAdaptation.id", "public.VideoChapterAdaptation.novelId"),
            name="VideoAdaptationTask_adaptation_novel_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("projectId", "novelId"),
            ("public.VideoProject.id", "public.VideoProject.novelId"),
            name="VideoAdaptationTask_project_novel_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("baseShotPlanVersionId", "adaptationId"),
            ("public.VideoShotPlanVersion.id", "public.VideoShotPlanVersion.adaptationId"),
            name="VideoAdaptationTask_base_plan_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        Index("VideoAdaptationTask_id_adaptationId_key", "id", "adaptationId", unique=True),
        Index(
            "VideoAdaptationTask_id_baseShotPlanVersionId_key",
            "id",
            "baseShotPlanVersionId",
            unique=True,
        ),
        Index("VideoAdaptationTask_jobId_key", "jobId", unique=True),
        Index("VideoAdaptationTask_idempotencyKey_key", "idempotencyKey", unique=True),
        Index(
            "VideoAdaptationTask_due_idx",
            "status",
            "nextAttemptAt",
            "createdAt",
            postgresql_where=text("\"status\" IN ('pending', 'submitted', 'processing')"),
        ),
        Index("VideoAdaptationTask_adaptation_created_idx", "adaptationId", "createdAt"),
        {"schema": "public"},
    )


class VideoShotPlanVersion(Base):
    """用户批准后创建的不可变电影化镜头方案版本。"""

    __tablename__ = "VideoShotPlanVersion"
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    adaptationId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.VideoChapterAdaptation.id",
            name="VideoShotPlanVersion_adaptationId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    versionNo: Mapped[int] = mapped_column(Integer, nullable=False)
    basedOnVersionId: Mapped[str | None] = mapped_column(Text, nullable=True)
    sourceTaskId: Mapped[str] = mapped_column(Text, nullable=False)
    reviewArtifactId: Mapped[str] = mapped_column(Text, nullable=False)
    createdByUserId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.User.id",
            name="VideoShotPlanVersion_createdByUserId_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    contentHash: Mapped[str] = mapped_column(Text, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoShotPlanVersion_pkey"),
        ForeignKeyConstraint(
            ("sourceTaskId", "adaptationId"),
            ("public.VideoAdaptationTask.id", "public.VideoAdaptationTask.adaptationId"),
            name="VideoShotPlanVersion_source_task_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("reviewArtifactId", "adaptationId"),
            ("public.ReviewArtifact.id", "public.ReviewArtifact.videoAdaptationId"),
            name="VideoShotPlanVersion_review_artifact_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("basedOnVersionId", "adaptationId"),
            ("public.VideoShotPlanVersion.id", "public.VideoShotPlanVersion.adaptationId"),
            name="VideoShotPlanVersion_based_on_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        Index(
            "VideoShotPlanVersion_adaptation_version_key",
            "adaptationId",
            "versionNo",
            unique=True,
        ),
        Index("VideoShotPlanVersion_sourceTaskId_key", "sourceTaskId", unique=True),
        Index("VideoShotPlanVersion_reviewArtifactId_key", "reviewArtifactId", unique=True),
        Index(
            "VideoShotPlanVersion_id_adaptationId_key",
            "id",
            "adaptationId",
            unique=True,
        ),
        {"schema": "public"},
    )


class VideoChapterAdaptationHead(Base):
    """章节改编根唯一允许原子切换的正式版本指针。"""

    __tablename__ = "VideoChapterAdaptationHead"
    adaptationId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.VideoChapterAdaptation.id",
            name="VideoChapterAdaptationHead_adaptationId_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    currentShotPlanVersionId: Mapped[str | None] = mapped_column(Text, nullable=True)
    currentEpisodePlanVersionId: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    __table_args__ = (
        PrimaryKeyConstraint("adaptationId", name="VideoChapterAdaptationHead_pkey"),
        ForeignKeyConstraint(
            ("currentShotPlanVersionId", "adaptationId"),
            ("public.VideoShotPlanVersion.id", "public.VideoShotPlanVersion.adaptationId"),
            name="VideoChapterAdaptationHead_current_plan_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("currentEpisodePlanVersionId", "adaptationId"),
            ("public.VideoEpisodePlanVersion.id", "public.VideoEpisodePlanVersion.adaptationId"),
            name="VideoChapterAdaptationHead_current_episode_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            (
                "currentEpisodePlanVersionId",
                "currentShotPlanVersionId",
                "adaptationId",
            ),
            (
                "public.VideoEpisodePlanVersion.id",
                "public.VideoEpisodePlanVersion.shotPlanVersionId",
                "public.VideoEpisodePlanVersion.adaptationId",
            ),
            name="VideoChapterAdaptationHead_current_episode_plan_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        {"schema": "public"},
    )


class VideoCinematicScene(Base):
    """正式镜头方案中的真实时间、地点和连续行动场景。"""

    __tablename__ = "VideoCinematicScene"
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    planVersionId: Mapped[str] = mapped_column(Text, nullable=False)
    adaptationId: Mapped[str] = mapped_column(Text, nullable=False)
    sceneKey: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    locationLabel: Mapped[str] = mapped_column(Text, nullable=False)
    timeLabel: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    changeSummary: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoCinematicScene_pkey"),
        ForeignKeyConstraint(
            ("planVersionId", "adaptationId"),
            ("public.VideoShotPlanVersion.id", "public.VideoShotPlanVersion.adaptationId"),
            name="VideoCinematicScene_plan_adaptation_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        Index("VideoCinematicScene_plan_key_key", "planVersionId", "sceneKey", unique=True),
        Index("VideoCinematicScene_plan_ordinal_key", "planVersionId", "ordinal", unique=True),
        Index(
            "VideoCinematicScene_id_planVersionId_key",
            "id",
            "planVersionId",
            unique=True,
        ),
        {"schema": "public"},
    )


class VideoDramaticBeat(Base):
    """场景中由目标、信息、情绪、权力或行动结果变化定义的戏剧节拍。"""

    __tablename__ = "VideoDramaticBeat"
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    planVersionId: Mapped[str] = mapped_column(Text, nullable=False)
    sceneId: Mapped[str] = mapped_column(Text, nullable=False)
    beatKey: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    dramaticTurn: Mapped[str] = mapped_column(Text, nullable=False)
    visualStrategy: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoDramaticBeat_pkey"),
        ForeignKeyConstraint(
            ("sceneId", "planVersionId"),
            ("public.VideoCinematicScene.id", "public.VideoCinematicScene.planVersionId"),
            name="VideoDramaticBeat_scene_plan_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        Index("VideoDramaticBeat_plan_key_key", "planVersionId", "beatKey", unique=True),
        Index("VideoDramaticBeat_plan_ordinal_key", "planVersionId", "ordinal", unique=True),
        Index(
            "VideoDramaticBeat_id_planVersionId_key",
            "id",
            "planVersionId",
            unique=True,
        ),
        Index(
            "VideoDramaticBeat_id_sceneId_planVersionId_key",
            "id",
            "sceneId",
            "planVersionId",
            unique=True,
        ),
        {"schema": "public"},
    )


class VideoDramaticBeatSourceAnchor(Base):
    """戏剧节拍相对于章节不可变全文的有序 code point 来源范围。"""

    __tablename__ = "VideoDramaticBeatSourceAnchor"
    beatId: Mapped[str] = mapped_column(Text, nullable=False)
    planVersionId: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    startCodePoint: Mapped[int] = mapped_column(Integer, nullable=False)
    endCodePoint: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint(
            "beatId", "ordinal", name="VideoDramaticBeatSourceAnchor_pkey"
        ),
        ForeignKeyConstraint(
            ("beatId", "planVersionId"),
            ("public.VideoDramaticBeat.id", "public.VideoDramaticBeat.planVersionId"),
            name="VideoDramaticBeatSourceAnchor_beat_plan_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        {"schema": "public"},
    )


class VideoShot(Base):
    """正式戏剧节拍中的最终剪辑镜头，不等同于供应商生成片段。"""

    __tablename__ = "VideoShot"
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    planVersionId: Mapped[str] = mapped_column(Text, nullable=False)
    sceneId: Mapped[str] = mapped_column(Text, nullable=False)
    beatId: Mapped[str] = mapped_column(Text, nullable=False)
    shotKey: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    narrativePurpose: Mapped[str] = mapped_column(Text, nullable=False)
    adaptationType: Mapped[str] = mapped_column(Text, nullable=False)
    shotScale: Mapped[str] = mapped_column(Text, nullable=False)
    cameraAngle: Mapped[str] = mapped_column(Text, nullable=False)
    cameraMovement: Mapped[str] = mapped_column(Text, nullable=False)
    visualIntent: Mapped[str] = mapped_column(Text, nullable=False)
    audioMode: Mapped[str] = mapped_column(Text, nullable=False)
    audioIntent: Mapped[str] = mapped_column(Text, nullable=False)
    cutReason: Mapped[str] = mapped_column(Text, nullable=False)
    timelineDurationMs: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoShot_pkey"),
        ForeignKeyConstraint(
            ("sceneId", "planVersionId"),
            ("public.VideoCinematicScene.id", "public.VideoCinematicScene.planVersionId"),
            name="VideoShot_scene_plan_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("beatId", "planVersionId"),
            ("public.VideoDramaticBeat.id", "public.VideoDramaticBeat.planVersionId"),
            name="VideoShot_beat_plan_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("beatId", "sceneId", "planVersionId"),
            (
                "public.VideoDramaticBeat.id",
                "public.VideoDramaticBeat.sceneId",
                "public.VideoDramaticBeat.planVersionId",
            ),
            name="VideoShot_beat_scene_plan_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        Index("VideoShot_plan_key_key", "planVersionId", "shotKey", unique=True),
        Index("VideoShot_plan_ordinal_key", "planVersionId", "ordinal", unique=True),
        Index("VideoShot_id_planVersionId_key", "id", "planVersionId", unique=True),
        {"schema": "public"},
    )


class VideoShotSourceAnchor(Base):
    """正式镜头相对于章节不可变全文的有序 code point 来源范围。"""

    __tablename__ = "VideoShotSourceAnchor"
    shotId: Mapped[str] = mapped_column(Text, nullable=False)
    planVersionId: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    startCodePoint: Mapped[int] = mapped_column(Integer, nullable=False)
    endCodePoint: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("shotId", "ordinal", name="VideoShotSourceAnchor_pkey"),
        ForeignKeyConstraint(
            ("shotId", "planVersionId"),
            ("public.VideoShot.id", "public.VideoShot.planVersionId"),
            name="VideoShotSourceAnchor_shot_plan_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        {"schema": "public"},
    )


class VideoEpisodePlanVersion(Base):
    """固定引用一个镜头方案版本的不可变分集边界版本。"""

    __tablename__ = "VideoEpisodePlanVersion"
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    adaptationId: Mapped[str] = mapped_column(Text, nullable=False)
    shotPlanVersionId: Mapped[str] = mapped_column(Text, nullable=False)
    versionNo: Mapped[int] = mapped_column(Integer, nullable=False)
    basedOnVersionId: Mapped[str | None] = mapped_column(Text, nullable=True)
    createdByUserId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.User.id",
            name="VideoEpisodePlanVersion_createdByUserId_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    contentHash: Mapped[str] = mapped_column(Text, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoEpisodePlanVersion_pkey"),
        ForeignKeyConstraint(
            ("shotPlanVersionId", "adaptationId"),
            ("public.VideoShotPlanVersion.id", "public.VideoShotPlanVersion.adaptationId"),
            name="VideoEpisodePlanVersion_shot_plan_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("basedOnVersionId", "adaptationId"),
            ("public.VideoEpisodePlanVersion.id", "public.VideoEpisodePlanVersion.adaptationId"),
            name="VideoEpisodePlanVersion_based_on_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        Index(
            "VideoEpisodePlanVersion_adaptation_version_key",
            "adaptationId",
            "versionNo",
            unique=True,
        ),
        Index(
            "VideoEpisodePlanVersion_id_adaptationId_key",
            "id",
            "adaptationId",
            unique=True,
        ),
        Index(
            "VideoEpisodePlanVersion_id_shotPlanVersionId_key",
            "id",
            "shotPlanVersionId",
            unique=True,
        ),
        Index(
            "VideoEpisodePlanVersion_id_shotPlanVersionId_adaptationId_key",
            "id",
            "shotPlanVersionId",
            "adaptationId",
            unique=True,
        ),
        {"schema": "public"},
    )


class VideoEpisodeBoundary(Base):
    """一个分集版本中按正式镜头顺序排列的换集边界。"""

    __tablename__ = "VideoEpisodeBoundary"
    episodePlanVersionId: Mapped[str] = mapped_column(Text, nullable=False)
    shotPlanVersionId: Mapped[str] = mapped_column(Text, nullable=False)
    afterShotId: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint(
            "episodePlanVersionId", "ordinal", name="VideoEpisodeBoundary_pkey"
        ),
        ForeignKeyConstraint(
            ("episodePlanVersionId", "shotPlanVersionId"),
            (
                "public.VideoEpisodePlanVersion.id",
                "public.VideoEpisodePlanVersion.shotPlanVersionId",
            ),
            name="VideoEpisodeBoundary_episode_shot_plan_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("afterShotId", "shotPlanVersionId"),
            ("public.VideoShot.id", "public.VideoShot.planVersionId"),
            name="VideoEpisodeBoundary_shot_plan_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        Index(
            "VideoEpisodeBoundary_version_shot_key",
            "episodePlanVersionId",
            "afterShotId",
            unique=True,
        ),
        {"schema": "public"},
    )


class VideoShotPromptVersion(Base):
    """用户明确保存的逐镜即梦提示词不可变版本。"""

    __tablename__ = "VideoShotPromptVersion"
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    shotId: Mapped[str] = mapped_column(Text, nullable=False)
    shotPlanVersionId: Mapped[str] = mapped_column(Text, nullable=False)
    versionNo: Mapped[int] = mapped_column(Integer, nullable=False)
    basedOnVersionId: Mapped[str | None] = mapped_column(Text, nullable=True)
    generatedText: Mapped[str | None] = mapped_column(Text, nullable=True)
    currentText: Mapped[str] = mapped_column(Text, nullable=False)
    sourceTaskId: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "public.VideoAdaptationTask.id",
            name="VideoShotPromptVersion_sourceTaskId_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    createdByUserId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.User.id",
            name="VideoShotPromptVersion_createdByUserId_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    contentHash: Mapped[str] = mapped_column(Text, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoShotPromptVersion_pkey"),
        ForeignKeyConstraint(
            ("shotId", "shotPlanVersionId"),
            ("public.VideoShot.id", "public.VideoShot.planVersionId"),
            name="VideoShotPromptVersion_shot_plan_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("sourceTaskId", "shotPlanVersionId"),
            (
                "public.VideoAdaptationTask.id",
                "public.VideoAdaptationTask.baseShotPlanVersionId",
            ),
            name="VideoShotPromptVersion_source_task_plan_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("basedOnVersionId", "shotId"),
            ("public.VideoShotPromptVersion.id", "public.VideoShotPromptVersion.shotId"),
            name="VideoShotPromptVersion_based_on_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        Index(
            "VideoShotPromptVersion_shot_version_key",
            "shotId",
            "versionNo",
            unique=True,
        ),
        Index("VideoShotPromptVersion_id_shotId_key", "id", "shotId", unique=True),
        {"schema": "public"},
    )


class VideoShotPromptHead(Base):
    """一个正式镜头当前采用的提示词版本指针。"""

    __tablename__ = "VideoShotPromptHead"
    shotId: Mapped[str] = mapped_column(Text, nullable=False)
    shotPlanVersionId: Mapped[str] = mapped_column(Text, nullable=False)
    currentVersionId: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    __table_args__ = (
        PrimaryKeyConstraint("shotId", name="VideoShotPromptHead_pkey"),
        ForeignKeyConstraint(
            ("shotId", "shotPlanVersionId"),
            ("public.VideoShot.id", "public.VideoShot.planVersionId"),
            name="VideoShotPromptHead_shot_plan_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("currentVersionId", "shotId"),
            ("public.VideoShotPromptVersion.id", "public.VideoShotPromptVersion.shotId"),
            name="VideoShotPromptHead_current_version_fkey",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        {"schema": "public"},
    )


class VideoAdaptationDecisionCommand(Base):
    """章节镜头方案批准的耐久幂等结果，独立于旧 Scene 批准命令。"""

    __tablename__ = "VideoAdaptationDecisionCommand"
    id: Mapped[str] = mapped_column(Text, nullable=False, default=generate_id)
    requestedByUserId: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "public.User.id",
            name="VideoAdaptationDecisionCommand_user_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    novelId: Mapped[str] = mapped_column(Text, nullable=False)
    projectId: Mapped[str] = mapped_column(Text, nullable=False)
    adaptationId: Mapped[str] = mapped_column(Text, nullable=False)
    artifactId: Mapped[str] = mapped_column(Text, nullable=False)
    sourceTaskId: Mapped[str] = mapped_column(Text, nullable=False)
    clientRequestId: Mapped[str] = mapped_column(Text, nullable=False)
    expectedArtifactRevision: Mapped[int] = mapped_column(Integer, nullable=False)
    expectedAdaptationRevision: Mapped[int] = mapped_column(Integer, nullable=False)
    requestHash: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'approve'::text")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'succeeded'::text")
    )
    resultJson: Mapped[str] = mapped_column(Text, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updatedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    completedAt: Mapped[datetime] = mapped_column(
        TIMESTAMP(precision=3, timezone=False), nullable=False
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="VideoAdaptationDecisionCommand_pkey"),
        ForeignKeyConstraint(
            ("novelId", "requestedByUserId"),
            ("public.Novel.id", "public.Novel.userId"),
            name="VideoAdaptationDecisionCommand_novel_owner_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("projectId", "novelId"),
            ("public.VideoProject.id", "public.VideoProject.novelId"),
            name="VideoAdaptationDecisionCommand_project_novel_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("adaptationId", "projectId"),
            ("public.VideoChapterAdaptation.id", "public.VideoChapterAdaptation.projectId"),
            name="VideoAdaptationDecisionCommand_adaptation_project_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("artifactId", "adaptationId"),
            ("public.ReviewArtifact.id", "public.ReviewArtifact.videoAdaptationId"),
            name="VideoAdaptationDecisionCommand_artifact_adaptation_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        ForeignKeyConstraint(
            ("sourceTaskId", "adaptationId"),
            ("public.VideoAdaptationTask.id", "public.VideoAdaptationTask.adaptationId"),
            name="VideoAdaptationDecisionCommand_task_adaptation_fkey",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        Index(
            "VideoAdaptationDecisionCommand_user_request_key",
            "requestedByUserId",
            "clientRequestId",
            unique=True,
        ),
        Index(
            "VideoAdaptationDecisionCommand_adaptation_created_idx",
            "adaptationId",
            "createdAt",
        ),
        {"schema": "public"},
    )
