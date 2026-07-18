from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar, cast

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.base import utc_now
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
from .schemas import (
    DashboardNovel,
    DashboardResponse,
    NovelResponse,
    UpdateNovelTitleResponse,
    WorkspaceBootstrapResponse,
    WorkspaceLoreResponse,
    WorkspacePlanningResponse,
    WorkspaceResourcesResponse,
    WorkspaceResponse,
)
from .service import NovelCreation, require_valid_creation_target

T = TypeVar("T")
IGNORED_TEXT_CHARACTERS = (
    "\u0009\u000a\u000b\u000c\u000d\u0020\u0085\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000\ufeff"
)
_TEXT_LENGTH_TRANSLATION = str.maketrans("", "", IGNORED_TEXT_CHARACTERS)


def utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def count_text_length(value: str) -> int:
    return len(value.translate(_TEXT_LENGTH_TRANSLATION))


def beat_plan_chapter_ids(
    *,
    include_all_details: bool,
    chapter_ids: list[str],
    detail_ids: list[str],
) -> list[str]:
    return chapter_ids if include_all_details else detail_ids


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
                require_valid_creation_target(
                    creation.story_length_profile,
                    creation.target_total_word_count,
                )
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
            bibles = await self._for_ids(
                session, WritingBible, WritingBible.novelId, novel_ids
            )
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
        bible_by_novel = {bible.novelId: bible for bible in bibles}
        return DashboardResponse(
            novels=[
                DashboardNovel.model_validate(
                    {
                        "id": novel.id,
                        "name": novel.name,
                        "summary": novel.summary,
                        **self._profile_fields(bible_by_novel.get(novel.id)),
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
            bibles = await self._for_ids(
                session,
                WritingBible,
                WritingBible.novelId,
                [novel.id for novel in novels],
            )
        bible_by_novel = {bible.novelId: bible for bible in bibles}
        return [
            NovelResponse.model_validate(
                self._novel_dict(novel, bible_by_novel.get(novel.id))
            )
            for novel in novels
        ]

    async def get_novel(self, novel_id: str, user_id: str) -> NovelResponse:
        async with self._session_factory() as session:
            novel = await self._require_owner(session, novel_id, user_id)
            bible = await self._one_for_novel(session, WritingBible, novel_id)
        return NovelResponse.model_validate(self._novel_dict(novel, bible))

    async def update_title(
        self,
        novel_id: str,
        user_id: str,
        name: str,
        expected_updated_at: datetime,
    ) -> UpdateNovelTitleResponse:
        async with self._session_factory() as session:
            async with session.begin():
                novel = await session.scalar(
                    select(Novel).where(Novel.id == novel_id).with_for_update()
                )
                if novel is None:
                    raise ApiError(
                        status_code=404,
                        code="NOVEL_NOT_FOUND",
                        message="小说不存在",
                    )
                if novel.userId is None or novel.userId != user_id:
                    raise ApiError(
                        status_code=403,
                        code="NOVEL_FORBIDDEN",
                        message="无权访问该小说",
                    )
                current_updated_at = self._required_novel_updated_at(novel.updatedAt)
                normalized_expected = (
                    expected_updated_at.replace(tzinfo=UTC)
                    if expected_updated_at.tzinfo is None
                    else expected_updated_at.astimezone(UTC)
                )
                if normalized_expected != current_updated_at:
                    raise ApiError(
                        status_code=409,
                        code="NOVEL_VERSION_CONFLICT",
                        message="小说已在其他位置更新，请重新加载后再修改标题",
                        details={"currentUpdatedAt": current_updated_at.isoformat()},
                    )
                if novel.name == name:
                    return UpdateNovelTitleResponse(
                        name=novel.name,
                        updatedAt=current_updated_at,
                    )
                novel.name = name
                novel.updatedAt = max(
                    utc_now(),
                    current_updated_at.replace(tzinfo=None) + timedelta(milliseconds=1),
                )
                await session.flush()
                updated_at = self._required_novel_updated_at(novel.updatedAt)
        return UpdateNovelTitleResponse(name=novel.name, updatedAt=updated_at)

    async def get_workspace(
        self, novel_id: str, user_id: str, chapter_id: str | None
    ) -> WorkspaceResponse:
        async with self._session_factory() as session:
            async with session.begin():
                await self._set_repeatable_read(session)
                novel = await self._require_owner(session, novel_id, user_id)
                workspace = await self._load_workspace(
                    session,
                    novel,
                    chapter_id,
                    user_id=user_id,
                )
        return WorkspaceResponse.model_validate(workspace)

    async def get_workspace_bootstrap(
        self, novel_id: str, user_id: str, chapter_id: str | None
    ) -> WorkspaceBootstrapResponse:
        async with self._session_factory() as session:
            async with session.begin():
                await self._set_repeatable_read(session)
                novel = await self._require_owner(
                    session, novel_id, user_id, hide_forbidden=True
                )
                workspace = await self._load_workspace_bootstrap(
                    session, novel, chapter_id, user_id=user_id
                )
        return WorkspaceBootstrapResponse.model_validate(workspace)

    async def get_workspace_lore(
        self, novel_id: str, user_id: str
    ) -> WorkspaceLoreResponse:
        async with self._session_factory() as session:
            async with session.begin():
                await self._set_repeatable_read(session)
                novel = await self._require_owner(
                    session, novel_id, user_id, hide_forbidden=True
                )
                workspace = await self._load_lore(session, novel)
        return WorkspaceLoreResponse.model_validate(workspace)

    async def get_workspace_planning(
        self, novel_id: str, user_id: str
    ) -> WorkspacePlanningResponse:
        async with self._session_factory() as session:
            async with session.begin():
                await self._set_repeatable_read(session)
                novel = await self._require_owner(
                    session, novel_id, user_id, hide_forbidden=True
                )
                workspace = await self._load_planning(session, novel)
        return WorkspacePlanningResponse.model_validate(workspace)

    async def get_workspace_resources(
        self, novel_id: str, user_id: str
    ) -> WorkspaceResourcesResponse:
        async with self._session_factory() as session:
            async with session.begin():
                await self._set_repeatable_read(session)
                novel = await self._require_owner(
                    session, novel_id, user_id, hide_forbidden=True
                )
                workspace = await self._load_resources(session, novel, user_id=user_id)
        return WorkspaceResourcesResponse.model_validate(workspace)

    async def _load_workspace(
        self,
        session: AsyncSession,
        novel: Novel,
        requested_chapter_id: str | None,
        *,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        owner_id = cast(str, user_id or novel.userId)
        chapter_data = await self._load_chapter_workspace(
            session, novel.id, requested_chapter_id, include_all_details=True
        )
        lore = await self._load_lore(session, novel)
        planning = await self._load_planning(session, novel)
        resources = await self._load_resources(session, novel, user_id=owner_id)
        return {
            "novel": {
                **self._novel_dict(novel, planning["writingBible"]),
                "appliedStyle": resources["appliedStyle"],
            },
            "chapters": chapter_data["allChapters"],
            "currentChapterId": chapter_data["currentChapterId"],
            **lore,
            "storyBackground": planning["storyBackground"],
            "worldSetting": planning["worldSetting"],
            "writingBible": planning["writingBible"],
            "outline": planning["outline"],
            "outlineNodes": planning["outlineNodes"],
            "plotProgress": planning["plotProgress"],
            "references": resources["references"],
            "styles": resources["styles"],
        }

    async def _load_workspace_bootstrap(
        self,
        session: AsyncSession,
        novel: Novel,
        requested_chapter_id: str | None,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        chapter_data = await self._load_chapter_workspace(
            session, novel.id, requested_chapter_id, include_all_details=False
        )
        applied_style = await self._load_applied_style(session, novel, user_id)
        bible = await self._one_for_novel(session, WritingBible, novel.id)
        profile_fields = self._profile_fields(bible)
        return {
            "novel": {
                **self._novel_dict(novel, bible),
                "appliedStyle": (
                    {"id": applied_style.id, "name": applied_style.name}
                    if applied_style
                    else None
                ),
            },
            **profile_fields,
            "chapters": chapter_data["chapters"],
            "currentChapter": chapter_data["currentChapter"],
            "currentChapterId": chapter_data["currentChapterId"],
        }

    async def _load_chapter_workspace(
        self,
        session: AsyncSession,
        novel_id: str,
        requested_chapter_id: str | None,
        *,
        include_all_details: bool,
    ) -> dict[str, Any]:
        full_chapters: list[Chapter] = []
        chapter_meta: list[dict[str, Any]]
        if include_all_details:
            full_chapters = list(
                (
                    await session.scalars(
                        select(Chapter)
                        .where(Chapter.novelId == novel_id)
                        .order_by(Chapter.order.asc(), Chapter.id.asc())
                    )
                ).all()
            )
            chapter_meta = [
                {
                    "id": chapter.id,
                    "title": chapter.title,
                    "order": chapter.order,
                    "status": chapter.status,
                    "updatedAt": utc_datetime(chapter.updatedAt),
                    "wordCount": count_text_length(chapter.content),
                }
                for chapter in full_chapters
            ]
        else:
            word_count = func.length(
                func.translate(Chapter.content, IGNORED_TEXT_CHARACTERS, "")
            ).label("wordCount")
            rows = (
                await session.execute(
                    select(
                        Chapter.id.label("id"),
                        Chapter.title.label("title"),
                        Chapter.order.label("order"),
                        Chapter.status.label("status"),
                        Chapter.updatedAt.label("updatedAt"),
                        word_count,
                    )
                    .where(Chapter.novelId == novel_id)
                    .order_by(Chapter.order.asc(), Chapter.id.asc())
                )
            ).all()
            chapter_meta = [
                {
                    "id": row.id,
                    "title": row.title,
                    "order": row.order,
                    "status": row.status,
                    "updatedAt": utc_datetime(row.updatedAt),
                    "wordCount": row.wordCount or 0,
                }
                for row in rows
            ]

        valid_ids = {value["id"] for value in chapter_meta}
        current_id = requested_chapter_id if requested_chapter_id in valid_ids else None
        if current_id is None:
            drafting = [value for value in chapter_meta if value["status"] == "drafting"]
            selected = drafting[-1] if drafting else (chapter_meta[-1] if chapter_meta else None)
            current_id = selected["id"] if selected else None

        if include_all_details:
            detail_chapters = full_chapters
        elif current_id is not None:
            current = await session.scalar(
                select(Chapter).where(
                    Chapter.id == current_id,
                    Chapter.novelId == novel_id,
                )
            )
            detail_chapters = [current] if current is not None else []
        else:
            detail_chapters = []

        chapter_ids = [value["id"] for value in chapter_meta]
        detail_ids = [chapter.id for chapter in detail_chapters]
        plan_chapter_ids = beat_plan_chapter_ids(
            include_all_details=include_all_details,
            chapter_ids=chapter_ids,
            detail_ids=detail_ids,
        )
        progresses = await self._for_ids(
            session, ChapterProgress, ChapterProgress.chapterId, detail_ids
        )
        checks = await self._for_ids(
            session,
            ChapterQualityCheck,
            ChapterQualityCheck.chapterId,
            detail_ids,
            ChapterQualityCheck.createdAt.asc(),
            ChapterQualityCheck.id.asc(),
        )
        plans = (
            list(
                (
                    await session.scalars(
                        select(ChapterBeatPlan)
                        .where(
                            ChapterBeatPlan.chapterId.in_(plan_chapter_ids),
                            ChapterBeatPlan.status == "approved",
                        )
                        .order_by(ChapterBeatPlan.updatedAt.desc(), ChapterBeatPlan.id.asc())
                    )
                ).all()
            )
            if plan_chapter_ids
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
            for chapter in detail_chapters
        ]
        chapter_by_id = {value["id"]: value for value in chapter_values}
        summaries = []
        for value in chapter_meta:
            summary_plan = latest_plans.get(cast(str, value["id"]))
            summaries.append(
                {
                    **value,
                    "approvedBeatPlan": (
                        {
                            "sceneCount": len(beats_by_plan[summary_plan.id]),
                            "totalEstimatedWords": summary_plan.totalEstimatedWords,
                        }
                        if summary_plan
                        else None
                    ),
                }
            )
        return {
            "chapters": summaries,
            "currentChapter": chapter_by_id.get(current_id),
            "currentChapterId": current_id,
            "allChapters": chapter_values,
        }

    async def _load_lore(self, session: AsyncSession, novel: Novel) -> dict[str, Any]:
        novel_id = novel.id
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
        }

    async def _load_planning(self, session: AsyncSession, novel: Novel) -> dict[str, Any]:
        novel_id = novel.id
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
        return {
            "storyProgress": novel.storyProgress,
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
        }

    async def _load_resources(
        self,
        session: AsyncSession,
        novel: Novel,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        references = list(
            (
                await session.execute(
                    select(ReferenceMaterial, RagDocument)
                    .outerjoin(
                        RagDocument,
                        (RagDocument.sourceType == "reference_material")
                        & (RagDocument.sourceId == ReferenceMaterial.id),
                    )
                    .where(ReferenceMaterial.novelId == novel.id)
                    .order_by(ReferenceMaterial.updatedAt.desc(), ReferenceMaterial.id.asc())
                )
            ).all()
        )
        applied_style = await self._load_applied_style(session, novel, user_id)
        styles = list(
            (
                await session.scalars(
                    select(WritingStyle)
                    .where(WritingStyle.userId == user_id)
                    .order_by(WritingStyle.updatedAt.desc(), WritingStyle.id.asc())
                )
            ).all()
        )
        return {
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
            "appliedStyle": (
                {"id": applied_style.id, "name": applied_style.name}
                if applied_style
                else None
            ),
        }

    @staticmethod
    async def _load_applied_style(
        session: AsyncSession,
        novel: Novel,
        user_id: str,
    ) -> WritingStyle | None:
        if novel.appliedStyleId is None:
            return None
        return cast(
            WritingStyle | None,
            await session.scalar(
                select(WritingStyle).where(
                    WritingStyle.id == novel.appliedStyleId,
                    WritingStyle.userId == user_id,
                )
            ),
        )

    @staticmethod
    async def _set_repeatable_read(session: AsyncSession) -> None:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            )

    async def _require_owner(
        self,
        session: AsyncSession,
        novel_id: str,
        user_id: str,
        *,
        hide_forbidden: bool = False,
    ) -> Novel:
        novel = await session.scalar(select(Novel).where(Novel.id == novel_id))
        if novel is None or (hide_forbidden and novel.userId != user_id):
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
    def _novel_dict(
        novel: Novel,
        bible: WritingBible | dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            **model_fields(
            novel,
            "id",
            "name",
            "summary",
            "storyProgress",
            "appliedStyleId",
            "createdAt",
            "updatedAt",
            ),
            **NovelRepository._profile_fields(bible),
        }

    @staticmethod
    def _profile_fields(
        bible: WritingBible | dict[str, Any] | None,
    ) -> dict[str, Any]:
        if bible is None:
            raise RuntimeError("小说缺少 WritingBible，无法确定篇幅模式")
        if isinstance(bible, dict):
            return {
                "storyLengthProfile": bible["storyLengthProfile"],
                "targetTotalWordCount": bible.get("targetTotalWordCount"),
            }
        return {
            "storyLengthProfile": bible.storyLengthProfile,
            "targetTotalWordCount": bible.targetTotalWordCount,
        }

    @staticmethod
    def _required_novel_updated_at(value: datetime | None) -> datetime:
        updated_at = utc_datetime(value)
        if updated_at is None:
            raise RuntimeError("小说更新时间缺失")
        return updated_at

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
