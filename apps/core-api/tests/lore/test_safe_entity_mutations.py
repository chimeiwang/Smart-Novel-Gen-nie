from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from inkforge_core.app import create_app
from inkforge_core.auth.dependencies import get_current_user
from inkforge_core.auth.repository import AuthUser
from inkforge_core.concurrency import command_resource_id
from inkforge_core.db.models import (
    Character,
    CharacterExperience,
    CharacterRelation,
    Faction,
    Glossary,
    Item,
    Location,
    Novel,
    User,
    WritingStyle,
)
from inkforge_core.errors import ApiError
from inkforge_core.lore.repository import EntityMutation, LoreRepository
from inkforge_core.lore.schemas import (
    CreateCharacterRequest,
    CreateCharacterResponse,
    CreateFactionRequest,
    CreateGlossaryRequest,
    CreateItemRequest,
    CreateLocationRequest,
    DeleteEntityRequest,
    UpdateCharacterRequest,
    UpdateFactionRequest,
    UpdateGlossaryRequest,
    UpdateItemRequest,
    UpdateLocationRequest,
)
from pydantic import ValidationError
from sqlalchemy import DefaultClause, MetaData, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

ENTITY_CASES = [
    ("characters", {"name": "角色", "currentStatus": "active"}, {"name": "新角色"}),
    ("items", {"name": "物品"}, {"name": "新物品"}),
    ("locations", {"name": "地点"}, {"name": "新地点"}),
    ("factions", {"name": "势力"}, {"name": "新势力"}),
    ("glossary", {"term": "术语", "definition": "释义"}, {"term": "新术语"}),
]


async def _create_database(path: Path) -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path.as_posix()}",
        execution_options={"schema_translate_map": {"public": None}},
    )
    async with engine.begin() as connection:
        metadata = MetaData()
        for table in (
            User.__table__,
            WritingStyle.__table__,
            Novel.__table__,
            Location.__table__,
            Faction.__table__,
            Character.__table__,
            Item.__table__,
            Glossary.__table__,
            CharacterExperience.__table__,
            CharacterRelation.__table__,
        ):
            table.to_metadata(metadata)
        metadata.tables["public.WritingStyle"].c.sourceType.server_default = DefaultClause(
            text("'manual'")
        )
        metadata.tables["public.Character"].c.currentStatus.server_default = DefaultClause(
            text("'active'")
        )
        await connection.run_sync(metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed_novels(factory: async_sessionmaker) -> None:
    async with factory() as session, session.begin():
        session.add_all(
            [
                User(id="user-1", username="user-1", passwordHash="固定哈希"),
                User(id="user-2", username="user-2", passwordHash="固定哈希"),
                Novel(id="novel-1", userId="user-1", name="作品一"),
                Novel(id="novel-2", userId="user-1", name="作品二"),
                Novel(id="novel-other", userId="user-2", name="他人作品"),
            ]
        )


@pytest.mark.parametrize(
    "schema",
    [
        CreateCharacterRequest,
        CreateItemRequest,
        CreateLocationRequest,
        CreateFactionRequest,
        CreateGlossaryRequest,
    ],
)
def test_entity_create_requires_bounded_client_request_id(schema: type[Any]) -> None:
    business = {"name": "资源"} if schema is not CreateGlossaryRequest else {
        "term": "术语",
        "definition": "释义",
    }
    with pytest.raises(ValidationError):
        schema.model_validate(business)
    with pytest.raises(ValidationError):
        schema.model_validate({**business, "clientRequestId": "too-short"})
    with pytest.raises(ValidationError):
        schema.model_validate({**business, "clientRequestId": "x" * 257})


@pytest.mark.parametrize(
    ("schema", "business"),
    [
        (UpdateCharacterRequest, {"name": "新名称"}),
        (UpdateItemRequest, {"name": "新名称"}),
        (UpdateLocationRequest, {"name": "新名称"}),
        (UpdateFactionRequest, {"name": "新名称"}),
        (UpdateGlossaryRequest, {"term": "新术语"}),
    ],
)
def test_entity_update_requires_version_and_business_patch(
    schema: type[Any], business: dict[str, str]
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate(business)
    with pytest.raises(ValidationError):
        schema.model_validate({"expectedUpdatedAt": "2026-08-06T00:00:00Z"})
    with pytest.raises(ValidationError):
        schema.model_validate({"expectedUpdatedAt": None, **business})


def test_entity_delete_requires_non_null_version() -> None:
    with pytest.raises(ValidationError):
        DeleteEntityRequest.model_validate({})
    with pytest.raises(ValidationError):
        DeleteEntityRequest.model_validate({"expectedUpdatedAt": None})


def test_entity_response_does_not_expose_operation_fields() -> None:
    now = datetime(2026, 8, 6, tzinfo=UTC)
    response = CreateCharacterResponse(
        id="character-1",
        name="角色",
        currentStatus="active",
        createdAt=now,
        updatedAt=now,
        effective=False,
    )
    assert response.effective is False
    assert "clientRequestId" not in type(response).model_fields
    assert "expectedUpdatedAt" not in type(response).model_fields
    assert "clientRequestId" not in response.model_dump()
    assert "expectedUpdatedAt" not in response.model_dump()


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "created_fields", "changed_fields"), ENTITY_CASES)
async def test_each_entity_has_stable_create_identity_and_cas(
    tmp_path: Path,
    kind: str,
    created_fields: dict[str, Any],
    changed_fields: dict[str, Any],
) -> None:
    engine, factory = await _create_database(tmp_path / f"{kind}.db")
    try:
        await _seed_novels(factory)
        repository = LoreRepository(factory)
        request_id = f"request-{kind}-00000001"

        created = await repository.create_entity(
            "novel-1", "user-1", kind, request_id, created_fields
        )
        assert created["id"] == command_resource_id(kind, "user-1", "novel-1", request_id)
        assert created["effective"] is True
        assert created["createdAt"] == created["updatedAt"]
        assert created["updatedAt"].microsecond % 1000 == 0

        replayed = await repository.create_entity(
            "novel-1", "user-1", kind, request_id, created_fields
        )
        assert replayed["id"] == created["id"]
        assert replayed["effective"] is False
        assert replayed["updatedAt"] == created["updatedAt"]

        conflicting_fields = {**created_fields, **changed_fields}
        with pytest.raises(ApiError) as create_conflict:
            await repository.create_entity(
                "novel-1", "user-1", kind, request_id, conflicting_fields
            )
        assert create_conflict.value.status_code == 409
        assert create_conflict.value.code == "RESOURCE_CREATE_CONFLICT"
        assert create_conflict.value.message == "创建请求已绑定其他内容"

        unchanged = await repository.update_entity(
            "novel-1",
            "user-1",
            kind,
            created["id"],
            {name: created_fields[name] for name in changed_fields},
            created["updatedAt"],
        )
        assert unchanged["updatedAt"] == created["updatedAt"]
        replayed_after_noop = await repository.create_entity(
            "novel-1", "user-1", kind, request_id, created_fields
        )
        assert replayed_after_noop["effective"] is False

        changed = await repository.update_entity(
            "novel-1",
            "user-1",
            kind,
            created["id"],
            changed_fields,
            created["updatedAt"],
        )
        assert changed["updatedAt"] > created["updatedAt"]
        assert changed["updatedAt"].microsecond % 1000 == 0

        with pytest.raises(ApiError) as stale_update:
            await repository.update_entity(
                "novel-1",
                "user-1",
                kind,
                created["id"],
                created_fields,
                created["updatedAt"],
            )
        assert stale_update.value.code == "LORE_ENTITY_VERSION_CONFLICT"

        with pytest.raises(ApiError) as replay_after_update:
            await repository.create_entity(
                "novel-1", "user-1", kind, request_id, created_fields
            )
        assert replay_after_update.value.code == "RESOURCE_CREATE_CONFLICT"

        restored = await repository.update_entity(
            "novel-1",
            "user-1",
            kind,
            created["id"],
            {name: created_fields[name] for name in changed_fields},
            changed["updatedAt"],
        )
        assert restored["updatedAt"] > changed["updatedAt"]
        with pytest.raises(ApiError) as replay_after_restore:
            await repository.create_entity(
                "novel-1", "user-1", kind, request_id, created_fields
            )
        assert replay_after_restore.value.code == "RESOURCE_CREATE_CONFLICT"

        with pytest.raises(ApiError) as stale_delete:
            await repository.delete_entity(
                "novel-1", "user-1", kind, created["id"], created["updatedAt"]
            )
        assert stale_delete.value.code == "LORE_ENTITY_VERSION_CONFLICT"

        deleted = await repository.delete_entity(
            "novel-1", "user-1", kind, created["id"], restored["updatedAt"]
        )
        assert deleted == {
            "deletedType": kind,
            "deletedId": created["id"],
            "affected": {},
        }

        recreated = await repository.create_entity(
            "novel-1", "user-1", kind, request_id, created_fields
        )
        assert recreated["id"] == created["id"]
        assert recreated["effective"] is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_entity_batch_rolls_back_create_when_later_cas_fails(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "批量原子性.db")
    try:
        await _seed_novels(factory)
        repository = LoreRepository(factory)
        target = await repository.create_entity(
            "novel-1", "user-1", "items", "target-item-00001", {"name": "旧物品"}
        )
        create_request_id = "batch-glossary-1"
        created_id = command_resource_id(
            "glossary", "user-1", "novel-1", create_request_id
        )

        with pytest.raises(ApiError) as caught:
            await repository.apply_entity_mutations(
                "novel-1",
                "user-1",
                [
                    EntityMutation(
                        action="create",
                        kind="glossary",
                        fields={"term": "批量术语", "definition": "不会落库"},
                        client_request_id=create_request_id,
                    ),
                    EntityMutation(
                        action="update",
                        kind="items",
                        fields={"name": "陈旧覆盖"},
                        entity_id=target["id"],
                        expected_updated_at=target["updatedAt"] - timedelta(seconds=1),
                    ),
                ],
            )
        assert caught.value.code == "LORE_ENTITY_VERSION_CONFLICT"

        async with factory() as session:
            assert await session.get(Glossary, created_id) is None
            current = await session.get(Item, target["id"])
        assert current is not None
        assert current.name == "旧物品"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_entity_batch_rolls_back_on_resolution_value_error(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "批量解析回滚.db")
    try:
        await _seed_novels(factory)
        repository = LoreRepository(factory)
        create_request_id = "batch-item-00001"
        created_id = command_resource_id("items", "user-1", "novel-1", create_request_id)

        with pytest.raises(ValueError, match="无法唯一解析"):
            await repository.apply_entity_mutations(
                "novel-1",
                "user-1",
                [
                    EntityMutation(
                        action="create",
                        kind="items",
                        fields={"name": "不会落库"},
                        client_request_id=create_request_id,
                    ),
                    EntityMutation(
                        action="update",
                        kind="items",
                        fields={"name": "无法更新"},
                        expected_updated_at=datetime(2026, 8, 6, tzinfo=UTC),
                        lookup_field="name",
                        lookup_value="不存在",
                    ),
                ],
            )

        async with factory() as session:
            assert await session.get(Item, created_id) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_identity_is_separated_by_novel_and_kind(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "命名空间.db")
    try:
        await _seed_novels(factory)
        repository = LoreRepository(factory)
        request_id = "same-request-0001"
        character = await repository.create_entity(
            "novel-1",
            "user-1",
            "characters",
            request_id,
            {"name": "角色", "currentStatus": "active"},
        )
        item = await repository.create_entity(
            "novel-1", "user-1", "items", request_id, {"name": "物品"}
        )
        other_novel = await repository.create_entity(
            "novel-2",
            "user-1",
            "characters",
            request_id,
            {"name": "角色", "currentStatus": "active"},
        )
        assert len({character["id"], item["id"], other_novel["id"]}) == 3
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_novel_entity_links_remain_rejected(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "跨小说引用.db")
    try:
        await _seed_novels(factory)
        repository = LoreRepository(factory)
        faction = await repository.create_entity(
            "novel-2", "user-1", "factions", "faction-request-1", {"name": "异界势力"}
        )
        with pytest.raises(ApiError) as caught:
            await repository.create_entity(
                "novel-1",
                "user-1",
                "characters",
                "character-request",
                {"name": "角色", "currentStatus": "active", "factionId": faction["id"]},
            )
        assert caught.value.code == "RELATED_RESOURCE_CROSS_NOVEL"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_character_delete_reports_all_reference_counts(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "角色引用.db")
    try:
        await _seed_novels(factory)
        repository = LoreRepository(factory)
        character = await repository.create_entity(
            "novel-1",
            "user-1",
            "characters",
            "character-main-01",
            {"name": "甲", "currentStatus": "active"},
        )
        target = await repository.create_entity(
            "novel-1",
            "user-1",
            "characters",
            "character-target",
            {"name": "乙", "currentStatus": "active"},
        )
        await repository.create_entity(
            "novel-1",
            "user-1",
            "items",
            "owned-item-00001",
            {"name": "信物", "ownerId": character["id"]},
        )
        async with factory() as session, session.begin():
            session.add(
                CharacterExperience(
                    id="experience-1",
                    characterId=character["id"],
                    content="经历",
                    order=0,
                )
            )
            session.add(
                CharacterRelation(
                    id="relation-1",
                    characterId=character["id"],
                    targetId=target["id"],
                    relationType="friend",
                    intimacy=1,
                )
            )

        with pytest.raises(ApiError) as caught:
            await repository.delete_entity(
                "novel-1", "user-1", "characters", character["id"], character["updatedAt"]
            )
        assert caught.value.status_code == 409
        assert caught.value.code == "LORE_ENTITY_REFERENCED"
        assert caught.value.details == {"relations": 1, "experiences": 1, "ownedItems": 1}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_location_and_faction_delete_report_reference_counts(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "地点势力引用.db")
    try:
        await _seed_novels(factory)
        repository = LoreRepository(factory)
        location = await repository.create_entity(
            "novel-1", "user-1", "locations", "location-main-01", {"name": "都城"}
        )
        await repository.create_entity(
            "novel-1",
            "user-1",
            "locations",
            "location-child-1",
            {"name": "内城", "parentId": location["id"]},
        )
        faction = await repository.create_entity(
            "novel-1",
            "user-1",
            "factions",
            "faction-main-001",
            {"name": "王廷", "baseId": location["id"]},
        )
        character = await repository.create_entity(
            "novel-1",
            "user-1",
            "characters",
            "character-faction",
            {"name": "成员", "currentStatus": "active", "factionId": faction["id"]},
        )

        with pytest.raises(ApiError) as location_error:
            await repository.delete_entity(
                "novel-1", "user-1", "locations", location["id"], location["updatedAt"]
            )
        assert location_error.value.code == "LORE_ENTITY_REFERENCED"
        assert location_error.value.details == {"childLocations": 1, "basedFactions": 1}

        with pytest.raises(ApiError) as faction_error:
            await repository.delete_entity(
                "novel-1", "user-1", "factions", faction["id"], faction["updatedAt"]
            )
        assert faction_error.value.code == "LORE_ENTITY_REFERENCED"
        assert faction_error.value.details == {"characters": 1}

        async with factory() as session:
            assert await session.get(Character, character["id"]) is not None
    finally:
        await engine.dispose()


def test_delete_routes_accept_body_and_return_impact_response() -> None:
    class Service:
        async def delete_entity(self, user_id, novel_id, kind, entity_id, body):
            del user_id, novel_id
            assert body.expectedUpdatedAt == datetime(2026, 8, 6, tzinfo=UTC)
            return {"deletedType": kind, "deletedId": entity_id, "affected": {}}

    app = create_app(testing=True)
    app.state.lore_service = Service()
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="user-1",
        username="user",
        password_hash="固定哈希",  # noqa: S106
        credit_balance_micros=0,
    )
    response = TestClient(app).request(
        "DELETE",
        "/api/v1/novels/novel-1/items/item-1",
        json={"expectedUpdatedAt": "2026-08-06T00:00:00Z"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "deletedType": "items",
        "deletedId": "item-1",
        "affected": {},
    }
