from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from inkforge_core.db.models import Novel, OutlineNode, User, WritingStyle
from inkforge_core.errors import ApiError
from inkforge_core.outlines.repository import OutlineRepository
from inkforge_core.outlines.schemas import (
    CreateOutlineNodeRequest,
    DeleteOutlineNodeRequest,
    UpdateOutlineNodeRequest,
)
from inkforge_core.outlines.service import OutlineService
from pydantic import ValidationError
from sqlalchemy import DefaultClause, MetaData, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

NODE_FIELDS = {
    "title": "第一卷",
    "content": "卷目标",
    "kind": "stage",
    "status": "planned",
    "order": 0,
    "parentId": None,
    "linkedChapterId": None,
    "estimatedWordCount": 100_000,
    "actualWordCount": None,
    "chapterStartOrder": 1,
    "chapterEndOrder": 30,
}


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
            OutlineNode.__table__,
        ):
            table.to_metadata(metadata)
        metadata.tables["public.WritingStyle"].c.sourceType.server_default = DefaultClause(
            text("'manual'")
        )
        outline_node_table = metadata.tables["public.OutlineNode"]
        outline_node_table.c.kind.server_default = DefaultClause(text("'stage'"))
        outline_node_table.c.status.server_default = DefaultClause(text("'planned'"))
        await connection.run_sync(metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed_novel(factory: async_sessionmaker) -> None:
    async with factory() as session, session.begin():
        session.add(User(id="user-1", username="user-1", passwordHash="固定哈希"))
        session.add(Novel(id="novel-1", userId="user-1", name="作品一"))


def test_outline_node_create_requires_stable_client_request_id() -> None:
    with pytest.raises(ValidationError):
        CreateOutlineNodeRequest(title="第一卷", kind="stage")

    request = CreateOutlineNodeRequest(
        title="第一卷",
        kind="stage",
        clientRequestId="outline-node-create-0001",
    )

    assert request.clientRequestId == "outline-node-create-0001"


def test_outline_node_update_requires_non_null_expected_version() -> None:
    with pytest.raises(ValidationError):
        UpdateOutlineNodeRequest(title="第一卷·新")
    with pytest.raises(ValidationError):
        UpdateOutlineNodeRequest(title="第一卷·新", expectedUpdatedAt=None)

    expected = datetime(2026, 8, 10, tzinfo=UTC)
    request = UpdateOutlineNodeRequest(
        title="第一卷·新",
        expectedUpdatedAt=expected,
    )

    assert request.expectedUpdatedAt == expected


class RecordingNodeRepository:
    def __init__(self) -> None:
        self.call: tuple[object, ...] | None = None

    async def create_node(self, *args: object) -> dict[str, object]:
        self.call = args
        return {"id": "node-1", "effective": True}

    async def update_node(self, *args: object) -> dict[str, object]:
        self.call = args
        return {"id": "node-1", "effective": True}

    async def delete_node(self, *args: object) -> dict[str, object]:
        self.call = args
        return {"deletedId": "node-1", "effective": True}


@pytest.mark.asyncio
async def test_outline_node_service_separates_create_request_identity() -> None:
    repository = RecordingNodeRepository()
    service = OutlineService(repository)  # type: ignore[arg-type]

    await service.create_node(
        "user-1",
        "novel-1",
        CreateOutlineNodeRequest(
            title="第一卷",
            kind="stage",
            clientRequestId="outline-node-create-0001",
        ),
    )

    assert repository.call == (
        "novel-1",
        "user-1",
        "outline-node-create-0001",
        {
            "title": "第一卷",
            "content": None,
            "kind": "stage",
            "status": "planned",
            "order": 0,
            "parentId": None,
            "linkedChapterId": None,
            "estimatedWordCount": None,
            "actualWordCount": None,
            "chapterStartOrder": None,
            "chapterEndOrder": None,
        },
    )


@pytest.mark.asyncio
async def test_outline_node_service_separates_update_and_delete_versions() -> None:
    repository = RecordingNodeRepository()
    service = OutlineService(repository)  # type: ignore[arg-type]
    expected = datetime(2026, 8, 10, tzinfo=UTC)

    await service.update_node(
        "user-1",
        "novel-1",
        "node-1",
        UpdateOutlineNodeRequest(title="新标题", expectedUpdatedAt=expected),
    )
    assert repository.call == (
        "novel-1",
        "user-1",
        "node-1",
        {"title": "新标题"},
        expected,
    )
    await service.delete_node(
        "user-1",
        "novel-1",
        "node-1",
        DeleteOutlineNodeRequest(expectedUpdatedAt=expected),
    )
    assert repository.call == (
        "novel-1",
        "user-1",
        "node-1",
        expected,
    )


@pytest.mark.asyncio
async def test_outline_node_create_replay_update_cas_and_delete_cas(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "大纲节点.db")
    try:
        await _seed_novel(factory)
        repository = OutlineRepository(factory)

        created = await repository.create_node(
            "novel-1",
            "user-1",
            "outline-node-create-0001",
            NODE_FIELDS,
        )
        assert created["effective"] is True
        created_version = created["updatedAt"]

        replayed = await repository.create_node(
            "novel-1",
            "user-1",
            "outline-node-create-0001",
            NODE_FIELDS,
        )
        assert replayed == {**created, "effective": False}

        with pytest.raises(ApiError) as create_conflict:
            await repository.create_node(
                "novel-1",
                "user-1",
                "outline-node-create-0001",
                {**NODE_FIELDS, "title": "不同内容"},
            )
        assert create_conflict.value.code == "RESOURCE_CREATE_CONFLICT"

        unchanged = await repository.update_node(
            "novel-1",
            "user-1",
            created["id"],
            {"title": "第一卷"},
            created_version,
        )
        assert unchanged["effective"] is False
        assert unchanged["updatedAt"] == created_version

        changed = await repository.update_node(
            "novel-1",
            "user-1",
            created["id"],
            {"title": "第一卷·宗门立足"},
            created_version,
        )
        assert changed["effective"] is True
        assert changed["updatedAt"] > created_version

        with pytest.raises(ApiError) as update_conflict:
            await repository.update_node(
                "novel-1",
                "user-1",
                created["id"],
                {"title": "陈旧覆盖"},
                created_version,
            )
        assert update_conflict.value.code == "OUTLINE_NODE_VERSION_CONFLICT"

        with pytest.raises(ApiError) as delete_conflict:
            await repository.delete_node(
                "novel-1",
                "user-1",
                created["id"],
                created_version,
            )
        assert delete_conflict.value.code == "OUTLINE_NODE_VERSION_CONFLICT"

        deleted = await repository.delete_node(
            "novel-1",
            "user-1",
            created["id"],
            changed["updatedAt"],
        )
        assert deleted == {"deletedId": created["id"], "effective": True}
        async with factory() as session:
            assert await session.scalar(
                select(OutlineNode).where(OutlineNode.id == created["id"])
            ) is None
    finally:
        await engine.dispose()
