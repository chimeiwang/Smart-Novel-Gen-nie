from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import (
    Chapter,
    Character,
    CharacterExperience,
    CharacterRelation,
    Faction,
    Glossary,
    Item,
    Location,
    Novel,
    StoryBackground,
    WorldSetting,
    WritingBible,
)
from ..errors import ApiError

_ENTITY_MODELS: dict[str, type[Any]] = {
    "characters": Character,
    "items": Item,
    "locations": Location,
    "factions": Faction,
    "glossary": Glossary,
}
_CONTENT_MODELS: dict[str, type[Any]] = {
    "story-background": StoryBackground,
    "world-setting": WorldSetting,
    "writing-bible": WritingBible,
}


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _model_dict(value: Any) -> dict[str, Any]:
    return {
        column.key: _utc(item) if isinstance(item := getattr(value, column.key), datetime) else item
        for column in value.__table__.columns
        if column.key != "novelId"
    }


class LoreRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_writing_bible_profile(self, novel_id: str, user_id: str) -> str:
        async with self._session_factory() as session:
            await self._require_owner(session, novel_id, user_id)
            profile = await session.scalar(
                select(WritingBible.storyLengthProfile).where(
                    WritingBible.novelId == novel_id
                )
            )
        if profile is None:
            raise ApiError(
                status_code=404,
                code="WRITING_BIBLE_NOT_FOUND",
                message="作品圣经不存在",
            )
        return profile

    async def list_entities(self, novel_id: str, user_id: str, kind: str) -> list[dict[str, Any]]:
        model = self._entity_model(kind)
        async with self._session_factory() as session:
            await self._require_owner(session, novel_id, user_id)
            values = (
                await session.scalars(
                    select(model)
                    .where(model.novelId == novel_id)
                    .order_by(model.createdAt.asc(), model.id.asc())
                )
            ).all()
        return [_model_dict(value) for value in values]

    async def create_entity(
        self, novel_id: str, user_id: str, kind: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        model = self._entity_model(kind)
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                if kind == "locations":
                    await self._lock_novel(session, novel_id)
                await self._validate_entity_links(session, novel_id, kind, None, fields)
                value = model(novelId=novel_id, **fields)
                session.add(value)
                await session.flush()
                result = _model_dict(value)
        return result

    async def update_entity(
        self,
        novel_id: str,
        user_id: str,
        kind: str,
        entity_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        model = self._entity_model(kind)
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                if kind == "locations":
                    await self._lock_novel(session, novel_id)
                await self._validate_entity_links(session, novel_id, kind, entity_id, fields)
                statement = (
                    update(model)
                    .where(model.id == entity_id, model.novelId == novel_id)
                    .values(**fields)
                )
                outcome = cast(CursorResult[Any], await session.execute(statement))
                if outcome.rowcount != 1:
                    raise self._not_found(kind)
                value = await session.scalar(
                    select(model).where(model.id == entity_id, model.novelId == novel_id)
                )
                if value is None:
                    raise self._not_found(kind)
                result = _model_dict(value)
        return result

    async def delete_entity(self, novel_id: str, user_id: str, kind: str, entity_id: str) -> None:
        model = self._entity_model(kind)
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                if kind == "locations":
                    await self._lock_novel(session, novel_id)
                    child = await session.scalar(
                        select(Location.id).where(Location.parentId == entity_id).limit(1)
                    )
                    if child is not None:
                        raise ApiError(
                            status_code=409,
                            code="LOCATION_HAS_CHILDREN",
                            message="地点仍有子地点，不能删除",
                        )
                outcome = cast(
                    CursorResult[Any],
                    await session.execute(
                        delete(model).where(model.id == entity_id, model.novelId == novel_id)
                    ),
                )
                if outcome.rowcount != 1:
                    raise self._not_found(kind)

    async def create_experience(
        self, novel_id: str, user_id: str, character_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._require_related(session, Character, character_id, novel_id, "角色")
                chapter_id = fields.get("chapterId")
                if chapter_id is not None:
                    await self._require_related(session, Chapter, chapter_id, novel_id, "章节")
                if fields.get("order") is None:
                    maximum = await session.scalar(
                        select(func.max(CharacterExperience.order)).where(
                            CharacterExperience.characterId == character_id
                        )
                    )
                    fields["order"] = (maximum if maximum is not None else -1) + 1
                value = CharacterExperience(characterId=character_id, **fields)
                session.add(value)
                await session.flush()
                result = _model_dict(value)
        return result

    async def list_experiences(
        self, novel_id: str, user_id: str, character_id: str
    ) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            await self._require_owner(session, novel_id, user_id)
            await self._require_related(session, Character, character_id, novel_id, "角色")
            values = (
                await session.scalars(
                    select(CharacterExperience)
                    .where(CharacterExperience.characterId == character_id)
                    .order_by(
                        CharacterExperience.order.asc(),
                        CharacterExperience.createdAt.asc(),
                        CharacterExperience.id.asc(),
                    )
                )
            ).all()
        return [_model_dict(value) for value in values]

    async def update_experience(
        self, novel_id: str, user_id: str, experience_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                chapter_id = fields.get("chapterId")
                if chapter_id is not None:
                    await self._require_related(session, Chapter, chapter_id, novel_id, "章节")
                subquery = select(Character.id).where(Character.novelId == novel_id)
                outcome = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(CharacterExperience)
                        .where(
                            CharacterExperience.id == experience_id,
                            CharacterExperience.characterId.in_(subquery),
                        )
                        .values(**fields)
                    ),
                )
                if outcome.rowcount != 1:
                    raise ApiError(
                        status_code=404, code="EXPERIENCE_NOT_FOUND", message="角色经历不存在"
                    )
                value = await session.scalar(
                    select(CharacterExperience).where(CharacterExperience.id == experience_id)
                )
                result = _model_dict(value)
        return result

    async def delete_experience(self, novel_id: str, user_id: str, experience_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                subquery = select(Character.id).where(Character.novelId == novel_id)
                outcome = cast(
                    CursorResult[Any],
                    await session.execute(
                        delete(CharacterExperience).where(
                            CharacterExperience.id == experience_id,
                            CharacterExperience.characterId.in_(subquery),
                        )
                    ),
                )
                if outcome.rowcount != 1:
                    raise ApiError(
                        status_code=404, code="EXPERIENCE_NOT_FOUND", message="角色经历不存在"
                    )

    async def create_relation(
        self, novel_id: str, user_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                for field in ("characterId", "targetId"):
                    await self._require_related(session, Character, fields[field], novel_id, "角色")
                value = CharacterRelation(**fields)
                session.add(value)
                await session.flush()
                result = _model_dict(value)
        return result

    async def list_relations(self, novel_id: str, user_id: str) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            await self._require_owner(session, novel_id, user_id)
            characters = select(Character.id).where(Character.novelId == novel_id)
            values = (
                await session.scalars(
                    select(CharacterRelation)
                    .where(
                        CharacterRelation.characterId.in_(characters),
                        CharacterRelation.targetId.in_(characters),
                    )
                    .order_by(CharacterRelation.createdAt.asc(), CharacterRelation.id.asc())
                )
            ).all()
        return [_model_dict(value) for value in values]

    async def update_relation(
        self, novel_id: str, user_id: str, relation_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                characters = select(Character.id).where(Character.novelId == novel_id)
                outcome = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(CharacterRelation)
                        .where(
                            CharacterRelation.id == relation_id,
                            CharacterRelation.characterId.in_(characters),
                            CharacterRelation.targetId.in_(characters),
                        )
                        .values(**fields)
                    ),
                )
                if outcome.rowcount != 1:
                    raise ApiError(
                        status_code=404, code="RELATION_NOT_FOUND", message="人物关系不存在"
                    )
                value = await session.scalar(
                    select(CharacterRelation).where(CharacterRelation.id == relation_id)
                )
                result = _model_dict(value)
        return result

    async def delete_relation(self, novel_id: str, user_id: str, relation_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                characters = select(Character.id).where(Character.novelId == novel_id)
                outcome = cast(
                    CursorResult[Any],
                    await session.execute(
                        delete(CharacterRelation).where(
                            CharacterRelation.id == relation_id,
                            CharacterRelation.characterId.in_(characters),
                        )
                    ),
                )
                if outcome.rowcount != 1:
                    raise ApiError(
                        status_code=404, code="RELATION_NOT_FOUND", message="人物关系不存在"
                    )

    async def upsert_content(
        self, novel_id: str, user_id: str, kind: str, content: Any
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                if kind == "story-progress":
                    await session.execute(
                        update(Novel)
                        .where(Novel.id == novel_id, Novel.userId == user_id)
                        .values(storyProgress=content)
                    )
                    return {"id": novel_id, "content": content}
                model = _CONTENT_MODELS.get(kind)
                if model is None:
                    raise ApiError(
                        status_code=404, code="LORE_KIND_NOT_FOUND", message="设定类型不存在"
                    )
                fields = content if kind == "writing-bible" else {"content": content}
                if kind == "writing-bible" and "targetTotalWordCount" in fields:
                    profile = await session.scalar(
                        select(WritingBible.storyLengthProfile).where(
                            WritingBible.novelId == novel_id
                        )
                    )
                    self._require_target_for_profile(
                        profile,
                        fields["targetTotalWordCount"],
                    )
                if kind != "writing-bible" and content is None:
                    raise ApiError(
                        status_code=422, code="LORE_CONTENT_REQUIRED", message="内容不能为 null"
                    )
                statement = (
                    pg_insert(model)
                    .values(novelId=novel_id, **fields)
                    .on_conflict_do_update(index_elements=[model.novelId], set_=fields)
                    .returning(model)
                )
                value = (await session.scalars(statement)).one()
                return _model_dict(value)

    @staticmethod
    def _require_target_for_profile(profile: str | None, target: object) -> None:
        if profile is None:
            raise ApiError(
                status_code=404,
                code="WRITING_BIBLE_NOT_FOUND",
                message="作品圣经不存在",
            )
        if profile == "short_medium" and (
            not isinstance(target, int)
            or isinstance(target, bool)
            or not 6_000 <= target <= 80_000
        ):
            raise ApiError(
                status_code=422,
                code="SHORT_STORY_TARGET_WORD_COUNT_INVALID",
                message="中短篇目标总字数必须在 6000 到 80000 之间",
            )

    async def _validate_entity_links(
        self,
        session: AsyncSession,
        novel_id: str,
        kind: str,
        entity_id: str | None,
        fields: dict[str, Any],
    ) -> None:
        relation = {
            "characters": ("factionId", Faction, "势力"),
            "items": ("ownerId", Character, "角色"),
            "locations": ("parentId", Location, "地点"),
            "factions": ("baseId", Location, "地点"),
        }.get(kind)
        if relation is None or relation[0] not in fields or fields[relation[0]] is None:
            return
        related_id = cast(str, fields[relation[0]])
        await self._require_related(session, relation[1], related_id, novel_id, relation[2])
        if kind == "locations":
            if related_id == entity_id:
                raise ApiError(
                    status_code=422, code="LOCATION_CYCLE", message="地点不能以自身为父地点"
                )
            current: str | None = related_id
            visited: set[str] = set()
            while current and current not in visited:
                if current == entity_id:
                    raise ApiError(
                        status_code=422, code="LOCATION_CYCLE", message="地点层级不能形成循环"
                    )
                visited.add(current)
                current = cast(
                    str | None,
                    await session.scalar(select(Location.parentId).where(Location.id == current)),
                )

    @staticmethod
    async def _require_owner(session: AsyncSession, novel_id: str, user_id: str) -> None:
        owner = await session.scalar(select(Novel.userId).where(Novel.id == novel_id))
        if owner is None:
            raise ApiError(status_code=403, code="NOVEL_FORBIDDEN", message="无权访问该小说")
        if owner != user_id:
            raise ApiError(status_code=403, code="NOVEL_FORBIDDEN", message="无权访问该小说")

    @staticmethod
    async def _lock_novel(session: AsyncSession, novel_id: str) -> None:
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            key = int.from_bytes(hashlib.sha256(novel_id.encode()).digest()[:8], "big", signed=True)
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    @staticmethod
    async def _require_related(
        session: AsyncSession, model: type[Any], entity_id: str, novel_id: str, label: str
    ) -> None:
        related_novel = await session.scalar(select(model.novelId).where(model.id == entity_id))
        if related_novel is None:
            raise ApiError(
                status_code=422, code="RELATED_RESOURCE_NOT_FOUND", message=f"{label}不存在"
            )
        if related_novel != novel_id:
            raise ApiError(
                status_code=422,
                code="RELATED_RESOURCE_CROSS_NOVEL",
                message=f"{label}不属于当前小说",
            )

    @staticmethod
    def _entity_model(kind: str) -> type[Any]:
        model = _ENTITY_MODELS.get(kind)
        if model is None:
            raise ApiError(status_code=404, code="LORE_KIND_NOT_FOUND", message="设定类型不存在")
        return model

    @staticmethod
    def _not_found(kind: str) -> ApiError:
        return ApiError(status_code=404, code="LORE_NOT_FOUND", message=f"{kind}资源不存在")
