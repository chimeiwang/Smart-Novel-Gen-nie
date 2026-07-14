from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, TypeVar, cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import (
    Chapter,
    ChapterBeatPlan,
    ChapterProgress,
    ChapterQualityCheck,
    Character,
    CharacterExperience,
    CharacterRelation,
    Faction,
    Glossary,
    Item,
    Location,
    Novel,
    Outline,
    OutlineNode,
    PlotProgress,
    RagDocument,
    ReferenceMaterial,
    SceneBeat,
    StoryBackground,
    WorldSetting,
    WritingBible,
    WritingStyle,
)
from ..errors import ApiError
from ..references.rag import public_rag_error
from .schemas import DashboardNovel, DashboardResponse, NovelResponse, WorkspaceResponse
from .service import NovelCreation

T = TypeVar("T")


def utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def count_text_length(value: str) -> int:
    return len(re.sub(r"\s", "", value))


def model_fields(value: Any, *names: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in names:
        item = getattr(value, name)
        result[name] = utc_datetime(item) if isinstance(item, datetime) else item
    return result


def quality_check_dict(check: ChapterQualityCheck) -> dict[str, Any]:
    return model_fields(
        check,
        "id",
        "chapterId",
        "type",
        "status",
        "title",
        "summary",
        "result",
        "scoreHook",
        "scoreTension",
        "scorePayoff",
        "scorePacing",
        "scoreEndingHook",
        "scoreReaderPromise",
        "scoreOverall",
        "qualityGate",
        "rewriteBrief",
        "createdAt",
        "updatedAt",
    )


def chapter_dict(
    chapter: Chapter,
    progress: ChapterProgress | None,
    checks: list[ChapterQualityCheck],
    beat_plan: ChapterBeatPlan | None,
    scene_beats: list[SceneBeat],
) -> dict[str, Any]:
    beat_plan_value: dict[str, Any] | None = None
    if beat_plan is not None:
        beat_plan_value = model_fields(
            beat_plan,
            "id",
            "chapterId",
            "goalId",
            "status",
            "chapterGoal",
            "mainPlotConnection",
            "chapterAcceptanceCriteria",
            "totalEstimatedWords",
            "generatedBy",
            "createdAt",
            "updatedAt",
        )
        beat_plan_value["sceneBeats"] = [
            model_fields(
                beat,
                "id",
                "order",
                "goal",
                "conflict",
                "characters",
                "foreshadowingRefs",
                "estimatedWords",
                "acceptanceCriteria",
            )
            for beat in scene_beats
        ]
    return {
        **model_fields(
            chapter,
            "id",
            "title",
            "content",
            "order",
            "status",
            "completedAt",
            "createdAt",
            "updatedAt",
        ),
        "wordCount": count_text_length(chapter.content),
        "progress": (
            model_fields(progress, "id", "chapterId", "content", "createdAt", "updatedAt")
            if progress is not None
            else None
        ),
        "qualityChecks": [quality_check_dict(check) for check in checks],
        "approvedBeatPlan": beat_plan_value,
    }


class NovelRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_novel(self, creation: NovelCreation) -> dict[str, str]:
        async with self._session_factory() as session:
            async with session.begin():
                novel = Novel(
                    userId=creation.user_id,
                    name=creation.name,
                    summary=creation.summary,
                    storyProgress=creation.story_progress,
                )
                session.add(novel)
                await session.flush()
                chapter = Chapter(
                    novelId=novel.id,
                    title=creation.first_chapter_title,
                    order=creation.first_chapter_order,
                    content="",
                    status="drafting",
                )
                session.add_all(
                    [
                        chapter,
                        Outline(novelId=novel.id, content=creation.outline_content),
                        PlotProgress(
                            novelId=novel.id,
                            currentStage=creation.current_stage,
                            currentGoal=creation.current_goal,
                        ),
                        WritingBible(
                            novelId=novel.id,
                            storyLengthProfile=creation.story_length_profile,
                            targetTotalWordCount=creation.target_total_word_count,
                            genre=creation.genre,
                            coreSellingPoint=creation.core_selling_point,
                            readerPromise=creation.reader_promise,
                            notes=creation.notes,
                        ),
                    ]
                )
                await session.flush()
                result = {"novelId": novel.id, "chapterId": chapter.id}
        return result

    async def list_dashboard(self, user_id: str) -> DashboardResponse:
        async with self._session_factory() as session:
            novels = list(
                (
                    await session.scalars(
                        select(Novel)
                        .where(Novel.userId == user_id)
                        .order_by(Novel.updatedAt.desc(), Novel.id.asc())
                    )
                ).all()
            )
            novel_ids = [novel.id for novel in novels]
            chapters = await self._for_ids(
                session, Chapter, Chapter.novelId, novel_ids, Chapter.order.asc(), Chapter.id.asc()
            )
            style_ids = [novel.appliedStyleId for novel in novels if novel.appliedStyleId]
            styles = (
                list(
                    (
                        await session.scalars(
                            select(WritingStyle).where(
                                WritingStyle.id.in_(style_ids),
                                WritingStyle.userId == user_id,
                            )
                        )
                    ).all()
                )
                if style_ids
                else []
            )
        chapter_ids: dict[str, list[str]] = defaultdict(list)
        for chapter in chapters:
            chapter_ids[chapter.novelId].append(chapter.id)
        style_by_id = {style.id: style for style in styles}
        return DashboardResponse(
            novels=[
                DashboardNovel.model_validate(
                    {
                        "id": novel.id,
                        "name": novel.name,
                        "summary": novel.summary,
                        "updatedAt": utc_datetime(novel.updatedAt),
                        "chapters": [{"id": value} for value in chapter_ids[novel.id]],
                        "appliedStyle": (
                            {
                                "id": style_by_id[novel.appliedStyleId].id,
                                "name": style_by_id[novel.appliedStyleId].name,
                            }
                            if novel.appliedStyleId in style_by_id
                            else None
                        ),
                    }
                )
                for novel in novels
            ]
        )

    async def list_novels(self, user_id: str) -> list[NovelResponse]:
        async with self._session_factory() as session:
            novels = (
                await session.scalars(
                    select(Novel)
                    .where(Novel.userId == user_id)
                    .order_by(Novel.updatedAt.desc(), Novel.id.asc())
                )
            ).all()
        return [NovelResponse.model_validate(self._novel_dict(novel)) for novel in novels]

    async def get_novel(self, novel_id: str, user_id: str) -> NovelResponse:
        async with self._session_factory() as session:
            novel = await self._require_owner(session, novel_id, user_id)
        return NovelResponse.model_validate(self._novel_dict(novel))

    async def get_workspace(
        self, novel_id: str, user_id: str, chapter_id: str | None
    ) -> WorkspaceResponse:
        async with self._session_factory() as session:
            async with session.begin():
                bind = session.get_bind()
                if bind.dialect.name == "postgresql":
                    await session.execute(
                        text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    )
                novel = await self._require_owner(session, novel_id, user_id)
                workspace = await self._load_workspace(
                    session,
                    novel,
                    chapter_id,
                    user_id=user_id,
                )
        return WorkspaceResponse.model_validate(workspace)

    async def _load_workspace(
        self,
        session: AsyncSession,
        novel: Novel,
        requested_chapter_id: str | None,
        *,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        novel_id = novel.id
        owner_id = user_id or novel.userId
        chapters = list(
            (
                await session.scalars(
                    select(Chapter)
                    .where(Chapter.novelId == novel_id)
                    .order_by(Chapter.order.asc(), Chapter.id.asc())
                )
            ).all()
        )
        chapter_ids = [chapter.id for chapter in chapters]
        progresses = await self._for_ids(
            session, ChapterProgress, ChapterProgress.chapterId, chapter_ids
        )
        checks = await self._for_ids(
            session,
            ChapterQualityCheck,
            ChapterQualityCheck.chapterId,
            chapter_ids,
            ChapterQualityCheck.createdAt.asc(),
            ChapterQualityCheck.id.asc(),
        )
        plans = (
            list(
                (
                    await session.scalars(
                        select(ChapterBeatPlan)
                        .where(
                            ChapterBeatPlan.chapterId.in_(chapter_ids),
                            ChapterBeatPlan.status == "approved",
                        )
                        .order_by(ChapterBeatPlan.updatedAt.desc(), ChapterBeatPlan.id.asc())
                    )
                ).all()
            )
            if chapter_ids
            else []
        )
        latest_plans: dict[str, ChapterBeatPlan] = {}
        for plan in plans:
            latest_plans.setdefault(plan.chapterId, plan)
        plan_ids = [plan.id for plan in latest_plans.values()]
        scene_beats = await self._for_ids(
            session,
            SceneBeat,
            SceneBeat.beatPlanId,
            plan_ids,
            SceneBeat.order.asc(),
            SceneBeat.id.asc(),
        )

        characters = list(
            (
                await session.scalars(
                    select(Character)
                    .where(Character.novelId == novel_id)
                    .order_by(Character.updatedAt.desc(), Character.id.asc())
                )
            ).all()
        )
        character_ids = [character.id for character in characters]
        experiences = await self._for_ids(
            session,
            CharacterExperience,
            CharacterExperience.characterId,
            character_ids,
            CharacterExperience.order.asc(),
            CharacterExperience.id.asc(),
        )
        relations = (
            list(
                (
                    await session.scalars(
                        select(CharacterRelation)
                        .where(
                            (CharacterRelation.characterId.in_(character_ids))
                            | (CharacterRelation.targetId.in_(character_ids))
                        )
                        .order_by(CharacterRelation.createdAt.asc(), CharacterRelation.id.asc())
                    )
                ).all()
            )
            if character_ids
            else []
        )
        factions = list(
            (
                await session.scalars(
                    select(Faction)
                    .where(Faction.novelId == novel_id)
                    .order_by(Faction.updatedAt.desc(), Faction.id.asc())
                )
            ).all()
        )
        items = list(
            (
                await session.scalars(
                    select(Item)
                    .where(Item.novelId == novel_id)
                    .order_by(Item.updatedAt.desc(), Item.id.asc())
                )
            ).all()
        )
        locations = list(
            (
                await session.scalars(
                    select(Location)
                    .where(Location.novelId == novel_id)
                    .order_by(Location.updatedAt.desc(), Location.id.asc())
                )
            ).all()
        )
        glossaries = list(
            (
                await session.scalars(
                    select(Glossary)
                    .where(Glossary.novelId == novel_id)
                    .order_by(Glossary.updatedAt.desc(), Glossary.id.asc())
                )
            ).all()
        )
        background = await self._one_for_novel(session, StoryBackground, novel_id)
        world = await self._one_for_novel(session, WorldSetting, novel_id)
        bible = await self._one_for_novel(session, WritingBible, novel_id)
        outline = await self._one_for_novel(session, Outline, novel_id)
        nodes = list(
            (
                await session.scalars(
                    select(OutlineNode)
                    .where(OutlineNode.novelId == novel_id)
                    .order_by(
                        OutlineNode.order.asc(), OutlineNode.title.asc(), OutlineNode.id.asc()
                    )
                )
            ).all()
        )
        plot = await self._one_for_novel(session, PlotProgress, novel_id)
        references = list(
            (
                await session.execute(
                    select(ReferenceMaterial, RagDocument)
                    .outerjoin(
                        RagDocument,
                        (RagDocument.sourceType == "reference_material")
                        & (RagDocument.sourceId == ReferenceMaterial.id),
                    )
                    .where(ReferenceMaterial.novelId == novel_id)
                    .order_by(ReferenceMaterial.updatedAt.desc(), ReferenceMaterial.id.asc())
                )
            ).all()
        )
        applied_style = (
            await session.scalar(
                select(WritingStyle).where(
                    WritingStyle.id == novel.appliedStyleId,
                    WritingStyle.userId == owner_id,
                )
            )
            if novel.appliedStyleId
            else None
        )
        styles = list(
            (
                await session.scalars(
                    select(WritingStyle)
                    .where(WritingStyle.userId == owner_id)
                    .order_by(WritingStyle.updatedAt.desc(), WritingStyle.id.asc())
                )
            ).all()
        )

        progresses_by_chapter = {value.chapterId: value for value in progresses}
        checks_by_chapter: dict[str, list[ChapterQualityCheck]] = defaultdict(list)
        for check in checks:
            checks_by_chapter[check.chapterId].append(check)
        beats_by_plan: dict[str, list[SceneBeat]] = defaultdict(list)
        for beat in scene_beats:
            beats_by_plan[beat.beatPlanId].append(beat)
        chapter_values = [
            chapter_dict(
                chapter,
                progresses_by_chapter.get(chapter.id),
                checks_by_chapter[chapter.id],
                latest_plans.get(chapter.id),
                beats_by_plan[latest_plans[chapter.id].id] if chapter.id in latest_plans else [],
            )
            for chapter in chapters
        ]
        valid_ids = {chapter.id for chapter in chapters}
        current_id = requested_chapter_id if requested_chapter_id in valid_ids else None
        if current_id is None:
            drafting = [chapter for chapter in chapters if chapter.status == "drafting"]
            selected = drafting[-1] if drafting else (chapters[-1] if chapters else None)
            current_id = selected.id if selected else None

        faction_by_id = {faction.id: faction for faction in factions}
        character_by_id = {character.id: character for character in characters}
        experiences_by_character: dict[str, list[CharacterExperience]] = defaultdict(list)
        outgoing: dict[str, list[CharacterRelation]] = defaultdict(list)
        incoming: dict[str, list[CharacterRelation]] = defaultdict(list)
        for experience in experiences:
            experiences_by_character[experience.characterId].append(experience)
        for relation in relations:
            outgoing[relation.characterId].append(relation)
            incoming[relation.targetId].append(relation)

        return {
            "novel": {
                **self._novel_dict(novel),
                "appliedStyle": (
                    {"id": applied_style.id, "name": applied_style.name} if applied_style else None
                ),
            },
            "chapters": chapter_values,
            "currentChapterId": current_id,
            "characters": [
                self._character_dict(
                    character,
                    faction_by_id,
                    character_by_id,
                    experiences_by_character[character.id],
                    outgoing[character.id],
                    incoming[character.id],
                )
                for character in characters
            ],
            "items": [
                {
                    **model_fields(
                        item,
                        "id",
                        "name",
                        "aliases",
                        "type",
                        "rarity",
                        "effect",
                        "origin",
                        "description",
                        "ownerId",
                        "createdAt",
                        "updatedAt",
                    ),
                    "owner": (
                        {
                            "id": character_by_id[item.ownerId].id,
                            "name": character_by_id[item.ownerId].name,
                        }
                        if item.ownerId in character_by_id
                        else None
                    ),
                }
                for item in items
            ],
            "locations": [
                model_fields(
                    value,
                    "id",
                    "name",
                    "aliases",
                    "type",
                    "parentId",
                    "climate",
                    "culture",
                    "description",
                    "createdAt",
                    "updatedAt",
                )
                for value in locations
            ],
            "factions": [
                model_fields(
                    value,
                    "id",
                    "name",
                    "aliases",
                    "type",
                    "baseId",
                    "description",
                    "createdAt",
                    "updatedAt",
                )
                for value in factions
            ],
            "glossaries": [
                model_fields(
                    value, "id", "term", "definition", "category", "createdAt", "updatedAt"
                )
                for value in glossaries
            ],
            "storyBackground": self._content_dict(background),
            "worldSetting": self._content_dict(world),
            "writingBible": self._bible_dict(bible),
            "outline": self._content_dict(outline),
            "outlineNodes": [
                model_fields(
                    value,
                    "id",
                    "title",
                    "content",
                    "kind",
                    "status",
                    "order",
                    "parentId",
                    "linkedChapterId",
                    "estimatedWordCount",
                    "actualWordCount",
                    "chapterStartOrder",
                    "chapterEndOrder",
                    "createdAt",
                    "updatedAt",
                )
                for value in nodes
            ],
            "plotProgress": (
                model_fields(
                    plot,
                    "id",
                    "currentStage",
                    "currentGoal",
                    "currentConflict",
                    "nextMilestone",
                    "updatedAt",
                )
                if plot
                else None
            ),
            "references": [
                {
                    **model_fields(
                        value,
                        "id",
                        "title",
                        "type",
                        "content",
                        "sourceUrl",
                        "createdAt",
                        "updatedAt",
                    ),
                    "ragStatus": document.status if document else "disabled",
                    "contentHash": (
                        document.contentHash
                        if document
                        else hashlib.sha256(value.content.encode("utf-8")).hexdigest()
                    ),
                    "errorMessage": (
                        public_rag_error(document.status, document.errorMessage)
                        if document
                        else None
                    ),
                }
                for value, document in references
            ],
            "styles": [
                model_fields(value, "id", "name", "portraitMarkdown", "sourceType")
                for value in styles
            ],
        }

    async def _require_owner(self, session: AsyncSession, novel_id: str, user_id: str) -> Novel:
        novel = await session.scalar(select(Novel).where(Novel.id == novel_id))
        if novel is None:
            raise ApiError(status_code=404, code="NOVEL_NOT_FOUND", message="小说不存在")
        if novel.userId is None or novel.userId != user_id:
            raise ApiError(status_code=403, code="NOVEL_FORBIDDEN", message="无权访问该小说")
        return novel

    @staticmethod
    async def _for_ids(
        session: AsyncSession,
        model: type[T],
        column: Any,
        ids: list[str],
        *order_by: Any,
    ) -> list[T]:
        if not ids:
            return []
        statement = select(model).where(column.in_(ids))
        if order_by:
            statement = statement.order_by(*order_by)
        return list((await session.scalars(statement)).all())

    @staticmethod
    async def _one_for_novel(session: AsyncSession, model: type[T], novel_id: str) -> T | None:
        model_value = cast(Any, model)
        return cast(
            T | None,
            await session.scalar(select(model).where(model_value.novelId == novel_id)),
        )

    @staticmethod
    def _novel_dict(novel: Novel) -> dict[str, Any]:
        return model_fields(
            novel,
            "id",
            "name",
            "summary",
            "storyProgress",
            "appliedStyleId",
            "createdAt",
            "updatedAt",
        )

    @staticmethod
    def _content_dict(value: Any | None) -> dict[str, Any] | None:
        return model_fields(value, "id", "content", "createdAt", "updatedAt") if value else None

    @staticmethod
    def _bible_dict(value: WritingBible | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return model_fields(
            value,
            "id",
            "storyLengthProfile",
            "targetTotalWordCount",
            "genre",
            "targetReaders",
            "coreSellingPoint",
            "readerPromise",
            "appealModel",
            "taboo",
            "comparableTitles",
            "notes",
            "createdAt",
            "updatedAt",
        )

    @staticmethod
    def _character_dict(
        character: Character,
        factions: dict[str, Faction],
        characters: dict[str, Character],
        experiences: list[CharacterExperience],
        outgoing: list[CharacterRelation],
        incoming: list[CharacterRelation],
    ) -> dict[str, Any]:
        def relation_dict(relation: CharacterRelation, incoming_value: bool) -> dict[str, Any]:
            value = model_fields(
                relation,
                "id",
                "characterId",
                "targetId",
                "relationType",
                "intimacy",
                "description",
                "startDate",
                "endDate",
                "createdAt",
                "updatedAt",
            )
            source = characters.get(relation.characterId)
            target = characters.get(relation.targetId)
            value["character"] = (
                {"id": source.id, "name": source.name} if incoming_value and source else None
            )
            value["target"] = (
                {"id": target.id, "name": target.name} if not incoming_value and target else None
            )
            return value

        value = model_fields(
            character,
            "id",
            "name",
            "aliases",
            "gender",
            "age",
            "appearance",
            "personality",
            "identity",
            "background",
            "coreDesire",
            "behaviorBoundaries",
            "speechStyle",
            "relationshipPrinciples",
            "shortTermGoal",
            "factionId",
            "powerLevel",
            "combatAbility",
            "specialSkills",
            "currentStatus",
            "statusNote",
            "createdAt",
            "updatedAt",
        )
        faction = factions.get(character.factionId) if character.factionId else None
        value["faction"] = {"id": faction.id, "name": faction.name} if faction else None
        value["experiences"] = [
            model_fields(item, "id", "chapterId", "content", "order", "createdAt", "updatedAt")
            for item in experiences
        ]
        value["outgoingRelations"] = [relation_dict(item, False) for item in outgoing]
        value["incomingRelations"] = [relation_dict(item, True) for item in incoming]
        return value
