from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from inkforge_core.db.models import (
    Novel,
    StoryBackground,
    User,
    WorldSetting,
    WritingBible,
    WritingStyle,
)
from inkforge_core.errors import ApiError
from inkforge_core.lore.repository import LoreRepository
from sqlalchemy import DefaultClause, MetaData, select, text
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
            StoryBackground.__table__,
            WorldSetting.__table__,
            WritingBible.__table__,
        ):
            table.to_metadata(metadata)
        metadata.tables["public.StoryBackground"].c.content.server_default = DefaultClause(
            text("''")
        )
        metadata.tables["public.WorldSetting"].c.content.server_default = DefaultClause(text("''"))
        metadata.tables[
            "public.WritingBible"
        ].c.storyLengthProfile.server_default = DefaultClause(text("'long_serial'"))
        metadata.tables["public.WritingStyle"].c.sourceType.server_default = DefaultClause(
            text("'manual'")
        )
        await connection.run_sync(metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed_novel(factory: async_sessionmaker) -> datetime:
    initial = datetime(2026, 8, 6, 1, 2, 3)
    async with factory() as session, session.begin():
        session.add(
            User(
                id="user-1",
                username="user",
                passwordHash="固定哈希",
            )
        )
        session.add(
            Novel(
                id="novel-1",
                userId="user-1",
                name="作品",
                updatedAt=initial,
            )
        )
    return initial.replace(tzinfo=UTC)


def test_expected_updated_at_normalizes_utc_and_reports_current_version() -> None:
    from inkforge_core.concurrency import require_expected_updated_at

    current = datetime(2026, 8, 6, 9, 0)
    require_expected_updated_at(
        current,
        datetime(2026, 8, 6, 17, 0, tzinfo=timezone(timedelta(hours=8))),
        code="LORE_CONTENT_VERSION_CONFLICT",
    )

    with pytest.raises(ApiError) as caught:
        require_expected_updated_at(
            current,
            datetime(2026, 8, 6, 8, 59, tzinfo=UTC),
            code="LORE_CONTENT_VERSION_CONFLICT",
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "LORE_CONTENT_VERSION_CONFLICT"
    assert caught.value.message == "资源版本已变化，请重新读取"
    assert caught.value.details == {"currentUpdatedAt": "2026-08-06T09:00:00+00:00"}


def test_expected_updated_at_reports_null_for_missing_resource() -> None:
    from inkforge_core.concurrency import require_expected_updated_at

    with pytest.raises(ApiError) as caught:
        require_expected_updated_at(
            None,
            datetime(2026, 8, 6, tzinfo=UTC),
            code="LORE_CONTENT_VERSION_CONFLICT",
        )

    assert caught.value.details == {"currentUpdatedAt": None}


def test_next_utc_timestamp_is_strictly_newer_than_future_current() -> None:
    from inkforge_core.concurrency import next_utc_timestamp

    current = datetime.now(UTC) + timedelta(days=1)
    result = next_utc_timestamp(current)

    assert result.tzinfo is UTC
    assert result >= current + timedelta(microseconds=1)


def test_command_resource_id_is_stable_and_domain_separated() -> None:
    from inkforge_core.concurrency import command_resource_id

    parts = ("lore", "用户", "novel-1", "request-1")
    expected = "ifc_" + hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    assert command_resource_id(*parts) == expected
    assert command_resource_id("outline", *parts[1:]) != expected


@pytest.mark.asyncio
async def test_world_setting_create_idempotency_monotonic_update_and_stale_rejection(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "世界设定.db")
    try:
        await _seed_novel(factory)
        repository = LoreRepository(factory)

        created = await repository.upsert_content(
            "novel-1", "user-1", "world-setting", "初始设定", None
        )
        created_version = created["updatedAt"]
        assert created_version.microsecond % 1000 == 0

        unchanged = await repository.upsert_content(
            "novel-1", "user-1", "world-setting", "初始设定", created_version
        )
        assert unchanged["updatedAt"] == created_version

        changed = await repository.upsert_content(
            "novel-1", "user-1", "world-setting", "权威新设定", created_version
        )
        assert changed["updatedAt"] > created_version

        with pytest.raises(ApiError) as caught:
            await repository.upsert_content(
                "novel-1", "user-1", "world-setting", "陈旧覆盖", created_version
            )
        assert caught.value.code == "LORE_CONTENT_VERSION_CONFLICT"

        async with factory() as session:
            current = await session.scalar(
                select(WorldSetting).where(WorldSetting.novelId == "novel-1")
            )
        assert current is not None
        assert current.content == "权威新设定"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_story_progress_uses_locked_novel_updated_at_as_version(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "故事进展.db")
    try:
        initial_version = await _seed_novel(factory)
        repository = LoreRepository(factory)

        changed = await repository.upsert_content(
            "novel-1", "user-1", "story-progress", "推进到第一章", initial_version
        )

        assert changed["updatedAt"] > initial_version
        async with factory() as session:
            novel = await session.get(Novel, "novel-1")
        assert novel is not None
        assert changed["updatedAt"] == novel.updatedAt.replace(tzinfo=UTC)
    finally:
        await engine.dispose()
