from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from inkforge_core.app import create_app
from inkforge_core.auth.dependencies import get_current_user
from inkforge_core.auth.repository import AuthUser
from inkforge_core.concurrency import command_resource_id
from inkforge_core.db.models import (
    Chapter,
    Character,
    CharacterExperience,
    CharacterRelation,
    Faction,
    Location,
    Novel,
    User,
    WritingStyle,
)
from inkforge_core.errors import ApiError
from inkforge_core.lore.repository import LoreRepository
from inkforge_core.lore.schemas import (
    CreateExperienceRequest,
    CreateExperienceResponse,
    CreateRelationRequest,
    CreateRelationResponse,
    ExperienceResponse,
    RelationResponse,
    UpdateExperienceRequest,
    UpdateRelationRequest,
)
from pydantic import ValidationError
from sqlalchemy import DefaultClause, MetaData, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


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
            Chapter.__table__,
            Location.__table__,
            Faction.__table__,
            Character.__table__,
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
        metadata.tables["public.Chapter"].c.status.server_default = DefaultClause(
            text("'drafting'")
        )
        metadata.tables["public.Chapter"].c.content.server_default = DefaultClause(text("''"))
        await connection.run_sync(metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed(factory: async_sessionmaker) -> None:
    async with factory() as session, session.begin():
        session.add(User(id="user-1", username="user-1", passwordHash="固定哈希"))
        session.add_all(
            [
                Novel(id="novel-1", userId="user-1", name="作品一"),
                Novel(id="novel-2", userId="user-1", name="作品二"),
            ]
        )
        session.add_all(
            [
                Chapter(id="chapter-1", novelId="novel-1", title="第一章", order=1),
                Chapter(id="chapter-2", novelId="novel-2", title="异界章", order=1),
                Character(id="character-a", novelId="novel-1", name="甲"),
                Character(id="character-b", novelId="novel-1", name="乙"),
                Character(id="character-other", novelId="novel-2", name="异界角色"),
            ]
        )


@pytest.mark.parametrize("schema", [CreateExperienceRequest, CreateRelationRequest])
def test_create_requests_require_bounded_client_request_id(schema: type[Any]) -> None:
    business = (
        {"content": "经历"}
        if schema is CreateExperienceRequest
        else {"characterId": "character-a", "targetId": "character-b", "relationType": "friend"}
    )
    with pytest.raises(ValidationError):
        schema.model_validate(business)
    with pytest.raises(ValidationError):
        schema.model_validate({**business, "clientRequestId": "too-short"})
    with pytest.raises(ValidationError):
        schema.model_validate({**business, "clientRequestId": "x" * 257})


@pytest.mark.parametrize(
    ("schema", "business"),
    [
        (UpdateExperienceRequest, {"content": "新经历"}),
        (UpdateRelationRequest, {"description": "新描述"}),
    ],
)
def test_update_requests_require_non_null_version_and_business_patch(
    schema: type[Any], business: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate(business)
    with pytest.raises(ValidationError):
        schema.model_validate({"expectedUpdatedAt": "2026-08-06T00:00:00Z"})
    with pytest.raises(ValidationError):
        schema.model_validate({"expectedUpdatedAt": None, **business})


def test_relationship_responses_do_not_expose_operation_fields() -> None:
    now = datetime(2026, 8, 6, tzinfo=UTC)
    experience = CreateExperienceResponse(
        id="experience-1",
        characterId="character-a",
        chapterId=None,
        content="经历",
        order=0,
        createdAt=now,
        updatedAt=now,
        effective=False,
    )
    relation = CreateRelationResponse(
        id="relation-1",
        characterId="character-a",
        targetId="character-b",
        relationType="friend",
        intimacy=0,
        createdAt=now,
        updatedAt=now,
        effective=False,
    )
    assert experience.effective is False
    assert relation.effective is False
    for response_type in (ExperienceResponse, RelationResponse):
        assert "clientRequestId" not in response_type.model_fields
        assert "expectedUpdatedAt" not in response_type.model_fields
        assert "effective" not in response_type.model_fields


@pytest.mark.asyncio
async def test_experience_has_stable_create_identity_cas_and_safe_delete(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "经历安全写入.db")
    try:
        await _seed(factory)
        repository = LoreRepository(factory)
        request_id = "experience-request-0001"
        fields = {"chapterId": "chapter-1", "content": "初始经历", "order": 3}

        created = await repository.create_experience(
            "novel-1", "user-1", "character-a", request_id, fields
        )
        assert created["id"] == command_resource_id(
            "experiences", "user-1", "novel-1", request_id
        )
        assert created["effective"] is True
        assert created["createdAt"] == created["updatedAt"]
        assert created["updatedAt"].microsecond % 1000 == 0

        replayed = await repository.create_experience(
            "novel-1", "user-1", "character-a", request_id, fields
        )
        assert replayed["id"] == created["id"]
        assert replayed["effective"] is False

        with pytest.raises(ApiError) as changed_replay:
            await repository.create_experience(
                "novel-1", "user-1", "character-a", request_id, {**fields, "content": "篡改"}
            )
        assert changed_replay.value.code == "RESOURCE_CREATE_CONFLICT"
        with pytest.raises(ApiError) as changed_character:
            await repository.create_experience(
                "novel-1", "user-1", "character-other", request_id, fields
            )
        assert changed_character.value.code == "RESOURCE_CREATE_CONFLICT"

        unchanged = await repository.update_experience(
            "novel-1", "user-1", created["id"], {"content": "初始经历"}, created["updatedAt"]
        )
        assert unchanged["updatedAt"] == created["updatedAt"]

        changed = await repository.update_experience(
            "novel-1", "user-1", created["id"], {"content": "变化"}, created["updatedAt"]
        )
        assert changed["updatedAt"] > created["updatedAt"]
        restored = await repository.update_experience(
            "novel-1", "user-1", created["id"], {"content": "初始经历"}, changed["updatedAt"]
        )
        assert restored["updatedAt"] > changed["updatedAt"]

        with pytest.raises(ApiError) as history_conflict:
            await repository.create_experience(
                "novel-1", "user-1", "character-a", request_id, fields
            )
        assert history_conflict.value.code == "RESOURCE_CREATE_CONFLICT"

        with pytest.raises(ApiError) as stale_update:
            await repository.update_experience(
                "novel-1", "user-1", created["id"], {"content": "陈旧覆盖"}, created["updatedAt"]
            )
        assert stale_update.value.code == "LORE_EXPERIENCE_VERSION_CONFLICT"

        with pytest.raises(ApiError) as stale_delete:
            await repository.delete_experience(
                "novel-1", "user-1", created["id"], created["updatedAt"]
            )
        assert stale_delete.value.code == "LORE_EXPERIENCE_VERSION_CONFLICT"

        deleted = await repository.delete_experience(
            "novel-1", "user-1", created["id"], restored["updatedAt"]
        )
        assert deleted == {
            "deletedType": "experience",
            "deletedId": created["id"],
            "affected": {},
        }
        recreated = await repository.create_experience(
            "novel-1", "user-1", "character-a", request_id, fields
        )
        assert recreated["id"] == created["id"]
        assert recreated["effective"] is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_relation_has_stable_create_identity_cas_and_only_deletes_target(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "关系安全写入.db")
    try:
        await _seed(factory)
        repository = LoreRepository(factory)
        fields = {
            "characterId": "character-a",
            "targetId": "character-b",
            "relationType": "friend",
            "intimacy": 20,
            "description": "旧识",
        }
        request_id = "relation-request-00001"
        created = await repository.create_relation(
            "novel-1", "user-1", request_id, fields
        )
        survivor = await repository.create_relation(
            "novel-1", "user-1", "relation-survivor-01", {**fields, "relationType": "ally"}
        )
        assert created["id"] == command_resource_id(
            "relations", "user-1", "novel-1", request_id
        )
        assert created["effective"] is True
        assert created["createdAt"] == created["updatedAt"]

        replayed = await repository.create_relation(
            "novel-1", "user-1", request_id, fields
        )
        assert replayed["effective"] is False
        with pytest.raises(ApiError) as content_conflict:
            await repository.create_relation(
                "novel-1", "user-1", request_id, {**fields, "intimacy": 21}
            )
        assert content_conflict.value.code == "RESOURCE_CREATE_CONFLICT"
        with pytest.raises(ApiError) as reference_conflict:
            await repository.create_relation(
                "novel-1",
                "user-1",
                request_id,
                {**fields, "targetId": "character-other"},
            )
        assert reference_conflict.value.code == "RESOURCE_CREATE_CONFLICT"

        unchanged = await repository.update_relation(
            "novel-1", "user-1", created["id"], {"description": "旧识"}, created["updatedAt"]
        )
        assert unchanged["updatedAt"] == created["updatedAt"]
        changed = await repository.update_relation(
            "novel-1", "user-1", created["id"], {"description": "反目"}, created["updatedAt"]
        )
        restored = await repository.update_relation(
            "novel-1", "user-1", created["id"], {"description": "旧识"}, changed["updatedAt"]
        )
        with pytest.raises(ApiError) as history_conflict:
            await repository.create_relation("novel-1", "user-1", request_id, fields)
        assert history_conflict.value.code == "RESOURCE_CREATE_CONFLICT"

        with pytest.raises(ApiError) as stale_update:
            await repository.update_relation(
                "novel-1",
                "user-1",
                created["id"],
                {"description": "陈旧覆盖"},
                created["updatedAt"],
            )
        assert stale_update.value.code == "LORE_RELATION_VERSION_CONFLICT"
        with pytest.raises(ApiError) as stale_delete:
            await repository.delete_relation(
                "novel-1", "user-1", created["id"], created["updatedAt"]
            )
        assert stale_delete.value.code == "LORE_RELATION_VERSION_CONFLICT"

        deleted = await repository.delete_relation(
            "novel-1", "user-1", created["id"], restored["updatedAt"]
        )
        assert deleted == {"deletedType": "relation", "deletedId": created["id"], "affected": {}}
        async with factory() as session:
            assert await session.get(CharacterRelation, survivor["id"]) is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_experience_and_relation_reject_cross_novel_references(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "跨小说隔离.db")
    try:
        await _seed(factory)
        repository = LoreRepository(factory)
        with pytest.raises(ApiError) as experience_character:
            await repository.create_experience(
                "novel-1", "user-1", "character-other", "experience-cross-001", {"content": "非法"}
            )
        assert experience_character.value.code == "RELATED_RESOURCE_CROSS_NOVEL"

        with pytest.raises(ApiError) as experience_chapter:
            await repository.create_experience(
                "novel-1",
                "user-1",
                "character-a",
                "experience-cross-002",
                {"chapterId": "chapter-2", "content": "非法"},
            )
        assert experience_chapter.value.code == "RELATED_RESOURCE_CROSS_NOVEL"

        created = await repository.create_experience(
            "novel-1", "user-1", "character-a", "experience-owned-01", {"content": "合法"}
        )
        with pytest.raises(ApiError) as update_chapter:
            await repository.update_experience(
                "novel-1",
                "user-1",
                created["id"],
                {"chapterId": "chapter-2"},
                created["updatedAt"],
            )
        assert update_chapter.value.code == "RELATED_RESOURCE_CROSS_NOVEL"

        for field in ("characterId", "targetId"):
            invalid = {
                "characterId": "character-a",
                "targetId": "character-b",
                "relationType": "friend",
                field: "character-other",
            }
            with pytest.raises(ApiError) as relation:
                await repository.create_relation(
                    "novel-1", "user-1", f"relation-cross-{field}", invalid
                )
            assert relation.value.code == "RELATED_RESOURCE_CROSS_NOVEL"

        same_request_id = "shared-request-00001"
        first_experience = await repository.create_experience(
            "novel-1", "user-1", "character-a", same_request_id, {"content": "本界经历"}
        )
        other_experience = await repository.create_experience(
            "novel-2",
            "user-1",
            "character-other",
            same_request_id,
            {"content": "异界经历"},
        )
        assert first_experience["id"] != other_experience["id"]
        with pytest.raises(ApiError) as isolated_update:
            await repository.update_experience(
                "novel-1",
                "user-1",
                other_experience["id"],
                {"content": "越界修改"},
                other_experience["updatedAt"],
            )
        assert isolated_update.value.code == "EXPERIENCE_NOT_FOUND"
        with pytest.raises(ApiError) as isolated_delete:
            await repository.delete_experience(
                "novel-1",
                "user-1",
                other_experience["id"],
                other_experience["updatedAt"],
            )
        assert isolated_delete.value.code == "EXPERIENCE_NOT_FOUND"

        other_relation = await repository.create_relation(
            "novel-2",
            "user-1",
            same_request_id,
            {
                "characterId": "character-other",
                "targetId": "character-other",
                "relationType": "friend",
            },
        )
        with pytest.raises(ApiError) as relation_update:
            await repository.update_relation(
                "novel-1",
                "user-1",
                other_relation["id"],
                {"description": "越界修改"},
                other_relation["updatedAt"],
            )
        assert relation_update.value.code == "RELATION_NOT_FOUND"
        with pytest.raises(ApiError) as relation_delete:
            await repository.delete_relation(
                "novel-1",
                "user-1",
                other_relation["id"],
                other_relation["updatedAt"],
            )
        assert relation_delete.value.code == "RELATION_NOT_FOUND"

        async with factory() as session:
            assert await session.get(CharacterExperience, other_experience["id"]) is not None
            assert await session.get(CharacterRelation, other_relation["id"]) is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_experience_batch_rolls_back_when_later_version_is_stale(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "经历批量回滚.db")
    try:
        await _seed(factory)
        repository = LoreRepository(factory)
        target = await repository.create_experience(
            "novel-1", "user-1", "character-a", "experience-target-01", {"content": "旧经历"}
        )
        created_id = command_resource_id(
            "experiences", "user-1", "novel-1", "experience-batch-new"
        )
        with pytest.raises(ApiError) as caught:
            await repository.apply_experience_mutations(
                "novel-1",
                "user-1",
                [
                    SimpleNamespace(
                        action="create",
                        character_id="character-a",
                        fields={"content": "不会落库"},
                        client_request_id="experience-batch-new",
                    ),
                    SimpleNamespace(
                        action="update",
                        entity_id=target["id"],
                        fields={"content": "陈旧覆盖"},
                        expected_updated_at=target["updatedAt"] - timedelta(seconds=1),
                    ),
                ],
            )
        assert caught.value.code == "LORE_EXPERIENCE_VERSION_CONFLICT"
        async with factory() as session:
            assert await session.get(CharacterExperience, created_id) is None
            current = await session.get(CharacterExperience, target["id"])
        assert current is not None
        assert current.content == "旧经历"
    finally:
        await engine.dispose()


def test_delete_routes_require_version_and_return_impact_without_control_leak() -> None:
    class Service:
        async def delete_experience(self, user_id, novel_id, entity_id, body):
            del user_id, novel_id
            assert body.expectedUpdatedAt == datetime(2026, 8, 6, tzinfo=UTC)
            return {"deletedType": "experience", "deletedId": entity_id, "affected": {}}

        async def delete_relation(self, user_id, novel_id, entity_id, body):
            del user_id, novel_id
            assert body.expectedUpdatedAt == datetime(2026, 8, 6, tzinfo=UTC)
            return {"deletedType": "relation", "deletedId": entity_id, "affected": {}}

    app = create_app(testing=True)
    app.state.lore_service = Service()
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="user-1",
        username="user",
        password_hash="固定哈希",  # noqa: S106
        credit_balance_micros=0,
    )
    client = TestClient(app)
    for path, kind in (
        ("/api/v1/novels/novel-1/experiences/experience-1", "experience"),
        ("/api/v1/novels/novel-1/relations/relation-1", "relation"),
    ):
        missing = client.request("DELETE", path)
        assert missing.status_code == 422
        response = client.request(
            "DELETE", path, json={"expectedUpdatedAt": "2026-08-06T00:00:00Z"}
        )
        assert response.status_code == 200
        assert response.json() == {
            "deletedType": kind,
            "deletedId": f"{kind}-1",
            "affected": {},
        }


def test_create_routes_use_dedicated_effective_responses() -> None:
    paths = create_app(testing=True).openapi()["paths"]
    experience_schema = paths[
        "/api/v1/novels/{novel_id}/characters/{character_id}/experiences"
    ]["post"]["responses"]["201"]["content"]["application/json"]["schema"]
    relation_schema = paths["/api/v1/novels/{novel_id}/relations"]["post"]["responses"]["201"][
        "content"
    ]["application/json"]["schema"]
    assert experience_schema["$ref"].endswith("/CreateExperienceResponse")
    assert relation_schema["$ref"].endswith("/CreateRelationResponse")
