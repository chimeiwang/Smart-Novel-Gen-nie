from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from pydantic import JsonValue
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..concurrency import command_resource_id, next_utc_timestamp, require_expected_updated_at
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
_ENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "characters": (
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
    ),
    "items": (
        "name",
        "aliases",
        "type",
        "rarity",
        "effect",
        "origin",
        "description",
        "ownerId",
    ),
    "locations": (
        "name",
        "aliases",
        "type",
        "parentId",
        "climate",
        "culture",
        "description",
    ),
    "factions": ("name", "aliases", "type", "baseId", "description"),
    "glossary": ("term", "definition", "category"),
}


@dataclass(frozen=True, slots=True)
class EntityMutation:
    action: Literal["create", "update", "delete"]
    kind: str
    fields: dict[str, Any]
    entity_id: str | None = None
    client_request_id: str | None = None
    expected_updated_at: datetime | None = None
    lookup_field: str | None = None
    lookup_value: str | None = None
    error_label: str = "设定实体"


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _database_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def _model_dict(value: Any) -> dict[str, Any]:
    return {
        column.key: _utc(item) if isinstance(item := getattr(value, column.key), datetime) else item
        for column in value.__table__.columns
        if column.key != "novelId"
    }


class LoreRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

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
        self,
        novel_id: str,
        user_id: str,
        kind: str,
        client_request_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._lock_novel(session, novel_id)
                return await self._create_entity_in_session(
                    session,
                    novel_id,
                    user_id,
                    kind,
                    client_request_id,
                    fields,
                )

    async def update_entity(
        self,
        novel_id: str,
        user_id: str,
        kind: str,
        entity_id: str,
        fields: dict[str, Any],
        expected_updated_at: datetime,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._lock_novel(session, novel_id)
                return await self._update_entity_in_session(
                    session,
                    novel_id,
                    kind,
                    entity_id,
                    fields,
                    expected_updated_at,
                )

    async def delete_entity(
        self,
        novel_id: str,
        user_id: str,
        kind: str,
        entity_id: str,
        expected_updated_at: datetime,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._lock_novel(session, novel_id)
                return await self._delete_entity_in_session(
                    session,
                    novel_id,
                    kind,
                    entity_id,
                    expected_updated_at,
                )

    async def apply_entity_mutations(
        self,
        novel_id: str,
        user_id: str,
        mutations: list[EntityMutation],
    ) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._lock_novel(session, novel_id)
                results: list[dict[str, Any]] = []
                for mutation in mutations:
                    if mutation.action == "create":
                        if mutation.client_request_id is None:
                            raise ValueError(
                                f"{mutation.error_label} create 缺少 clientRequestId"
                            )
                        result = await self._create_entity_in_session(
                            session,
                            novel_id,
                            user_id,
                            mutation.kind,
                            mutation.client_request_id,
                            mutation.fields,
                        )
                    else:
                        entity_id = mutation.entity_id
                        if entity_id is None:
                            entity_id = await self._resolve_entity_id_in_session(
                                session,
                                novel_id,
                                mutation.kind,
                                mutation.lookup_field,
                                mutation.lookup_value,
                                mutation.error_label,
                            )
                        if mutation.expected_updated_at is None:
                            raise ValueError(
                                f"{mutation.error_label} {mutation.action} 缺少 expectedUpdatedAt"
                            )
                        if mutation.action == "update":
                            result = await self._update_entity_in_session(
                                session,
                                novel_id,
                                mutation.kind,
                                entity_id,
                                mutation.fields,
                                mutation.expected_updated_at,
                            )
                        else:
                            result = await self._delete_entity_in_session(
                                session,
                                novel_id,
                                mutation.kind,
                                entity_id,
                                mutation.expected_updated_at,
                            )
                    results.append(result)
                return results

    async def _create_entity_in_session(
        self,
        session: AsyncSession,
        novel_id: str,
        user_id: str,
        kind: str,
        client_request_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        model = self._entity_model(kind)
        entity_id = command_resource_id(kind, user_id, novel_id, client_request_id)
        create_fields = self._entity_create_fields(kind, fields)
        value = await session.scalar(
            select(model).where(model.id == entity_id).with_for_update()
        )
        if value is not None:
            current_fields = {name: getattr(value, name) for name in _ENTITY_FIELDS[kind]}
            is_initial_version = _utc(value.createdAt) == _utc(value.updatedAt)
            if (
                value.novelId == novel_id
                and is_initial_version
                and current_fields == create_fields
            ):
                return {**_model_dict(value), "effective": False}
            raise ApiError(
                status_code=409,
                code="RESOURCE_CREATE_CONFLICT",
                message="创建请求已绑定其他内容",
            )
        await self._validate_entity_links(session, novel_id, kind, entity_id, create_fields)
        created_at = _database_utc(next_utc_timestamp(None))
        value = model(
            id=entity_id,
            novelId=novel_id,
            **create_fields,
            createdAt=created_at,
            updatedAt=created_at,
        )
        session.add(value)
        await session.flush()
        return {**_model_dict(value), "effective": True}

    async def _update_entity_in_session(
        self,
        session: AsyncSession,
        novel_id: str,
        kind: str,
        entity_id: str,
        fields: dict[str, Any],
        expected_updated_at: datetime,
    ) -> dict[str, Any]:
        model = self._entity_model(kind)
        value = await session.scalar(
            select(model)
            .where(model.id == entity_id, model.novelId == novel_id)
            .with_for_update()
        )
        if value is None:
            raise self._not_found(kind)
        current_updated_at = _utc(value.updatedAt)
        require_expected_updated_at(
            current_updated_at,
            expected_updated_at,
            code="LORE_ENTITY_VERSION_CONFLICT",
        )
        if any(getattr(value, name) != requested for name, requested in fields.items()):
            await self._validate_entity_links(session, novel_id, kind, entity_id, fields)
            for name, requested in fields.items():
                setattr(value, name, requested)
            value.updatedAt = _database_utc(next_utc_timestamp(current_updated_at))
            await session.flush()
        return _model_dict(value)

    async def _delete_entity_in_session(
        self,
        session: AsyncSession,
        novel_id: str,
        kind: str,
        entity_id: str,
        expected_updated_at: datetime,
    ) -> dict[str, Any]:
        model = self._entity_model(kind)
        value = await session.scalar(
            select(model)
            .where(model.id == entity_id, model.novelId == novel_id)
            .with_for_update()
        )
        if value is None:
            raise self._not_found(kind)
        require_expected_updated_at(
            _utc(value.updatedAt),
            expected_updated_at,
            code="LORE_ENTITY_VERSION_CONFLICT",
        )
        references = await self._entity_delete_references(session, kind, entity_id)
        if references:
            raise ApiError(
                status_code=409,
                code="LORE_ENTITY_REFERENCED",
                message="设定实体仍被引用，不能删除",
                details=references,
            )
        outcome = cast(
            CursorResult[Any],
            await session.execute(
                delete(model).where(model.id == entity_id, model.novelId == novel_id)
            ),
        )
        if outcome.rowcount != 1:
            raise self._not_found(kind)
        return {"deletedType": kind, "deletedId": entity_id, "affected": {}}

    async def _resolve_entity_id_in_session(
        self,
        session: AsyncSession,
        novel_id: str,
        kind: str,
        lookup_field: str | None,
        lookup_value: str | None,
        error_label: str,
    ) -> str:
        model = self._entity_model(kind)
        if lookup_field not in _ENTITY_FIELDS[kind] or lookup_value is None:
            raise ValueError(f"{error_label} 无法唯一解析已有实体")
        entity_ids = (
            await session.scalars(
                select(model.id)
                .where(
                    model.novelId == novel_id,
                    getattr(model, lookup_field) == lookup_value,
                )
                .limit(2)
                .with_for_update()
            )
        ).all()
        if len(entity_ids) != 1:
            raise ValueError(f"{error_label} 无法唯一解析已有实体")
        return cast(str, entity_ids[0])

    @staticmethod
    def _entity_create_fields(kind: str, fields: dict[str, Any]) -> dict[str, Any]:
        defaults: dict[str, Any] = {"currentStatus": "active"}
        return {
            name: fields[name] if name in fields else defaults.get(name)
            for name in _ENTITY_FIELDS[kind]
        }

    @staticmethod
    async def _entity_delete_references(
        session: AsyncSession, kind: str, entity_id: str
    ) -> dict[str, JsonValue]:
        statements: dict[str, Any]
        if kind == "characters":
            statements = {
                "relations": select(func.count(CharacterRelation.id)).where(
                    or_(
                        CharacterRelation.characterId == entity_id,
                        CharacterRelation.targetId == entity_id,
                    )
                ),
                "experiences": select(func.count(CharacterExperience.id)).where(
                    CharacterExperience.characterId == entity_id
                ),
                "ownedItems": select(func.count(Item.id)).where(Item.ownerId == entity_id),
            }
        elif kind == "locations":
            statements = {
                "childLocations": select(func.count(Location.id)).where(
                    Location.parentId == entity_id
                ),
                "basedFactions": select(func.count(Faction.id)).where(
                    Faction.baseId == entity_id
                ),
            }
        elif kind == "factions":
            statements = {
                "characters": select(func.count(Character.id)).where(
                    Character.factionId == entity_id
                )
            }
        else:
            return {}
        counts = {
            name: int(await session.scalar(statement) or 0)
            for name, statement in statements.items()
        }
        return {name: count for name, count in counts.items() if count > 0}

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
        self,
        novel_id: str,
        user_id: str,
        kind: str,
        content: Any,
        expected_updated_at: datetime | None,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._lock_novel(session, novel_id)
                if kind == "story-progress":
                    novel = await session.scalar(
                        select(Novel)
                        .where(Novel.id == novel_id, Novel.userId == user_id)
                        .with_for_update()
                    )
                    if novel is None:
                        raise ApiError(
                            status_code=403,
                            code="NOVEL_FORBIDDEN",
                            message="无权访问该小说",
                        )
                    current_updated_at = _utc(novel.updatedAt)
                    require_expected_updated_at(
                        current_updated_at,
                        expected_updated_at,
                        code="LORE_CONTENT_VERSION_CONFLICT",
                    )
                    if novel.storyProgress != content:
                        novel.storyProgress = content
                        novel.updatedAt = _database_utc(
                            next_utc_timestamp(current_updated_at)
                        )
                        await session.flush()
                    return {
                        "id": novel.id,
                        "content": novel.storyProgress,
                        "createdAt": _utc(novel.createdAt),
                        "updatedAt": _utc(novel.updatedAt),
                    }
                model = _CONTENT_MODELS.get(kind)
                if model is None:
                    raise ApiError(
                        status_code=404, code="LORE_KIND_NOT_FOUND", message="设定类型不存在"
                    )
                fields = content if kind == "writing-bible" else {"content": content}
                if kind != "writing-bible" and content is None:
                    raise ApiError(
                        status_code=422, code="LORE_CONTENT_REQUIRED", message="内容不能为 null"
                    )
                value = await session.scalar(
                    select(model)
                    .where(model.novelId == novel_id)
                    .with_for_update()
                )
                current_updated_at = _utc(value.updatedAt) if value is not None else None
                require_expected_updated_at(
                    current_updated_at,
                    expected_updated_at,
                    code="LORE_CONTENT_VERSION_CONFLICT",
                )
                if value is None:
                    created_at = _database_utc(next_utc_timestamp(None))
                    value = model(
                        novelId=novel_id,
                        **fields,
                        createdAt=created_at,
                        updatedAt=created_at,
                    )
                    session.add(value)
                    await session.flush()
                elif any(getattr(value, name) != requested for name, requested in fields.items()):
                    for name, requested in fields.items():
                        setattr(value, name, requested)
                    value.updatedAt = _database_utc(
                        next_utc_timestamp(current_updated_at)
                    )
                    await session.flush()
                return _model_dict(value)

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
        await session.scalar(
            select(Novel.id).where(Novel.id == novel_id).with_for_update()
        )
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
