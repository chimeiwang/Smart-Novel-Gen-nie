from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from inkforge_core.db.models import Novel, PlotProgress, User, WritingStyle
from inkforge_core.errors import ApiError
from inkforge_core.outlines.repository import OutlineRepository
from inkforge_core.outlines.schemas import PlotProgressRequest, PlotProgressResponse
from inkforge_core.outlines.service import OutlineService
from pydantic import ValidationError
from sqlalchemy import DefaultClause, MetaData, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

PLOT_FIELDS = {
    "currentStage": "第一幕",
    "currentGoal": "找到线索",
    "currentConflict": "时间不足",
    "nextMilestone": "进入遗迹",
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
            PlotProgress.__table__,
        ):
            table.to_metadata(metadata)
        metadata.tables["public.WritingStyle"].c.sourceType.server_default = DefaultClause(
            text("'manual'")
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


def test_plot_progress_request_requires_explicit_nullable_version() -> None:
    with pytest.raises(ValidationError):
        PlotProgressRequest.model_validate(PLOT_FIELDS)

    request = PlotProgressRequest.model_validate(
        {**PLOT_FIELDS, "expectedUpdatedAt": None}
    )

    assert request.expectedUpdatedAt is None


def test_plot_progress_response_does_not_expose_expected_version() -> None:
    now = datetime(2026, 8, 7, tzinfo=UTC)
    response = PlotProgressResponse(
        id="plot-1",
        updatedAt=now,
        **PLOT_FIELDS,
    )

    assert "expectedUpdatedAt" not in type(response).model_fields
    assert "expectedUpdatedAt" not in response.model_dump()


class RecordingPlotRepository:
    def __init__(self) -> None:
        self.saved: tuple[str, str, dict[str, Any], datetime | None] | None = None

    async def upsert_plot(
        self,
        novel_id: str,
        user_id: str,
        fields: dict[str, Any],
        expected_updated_at: datetime | None,
    ) -> dict[str, Any]:
        self.saved = (novel_id, user_id, fields, expected_updated_at)
        return {"id": "plot-1", "updatedAt": datetime.now(UTC), **fields}


@pytest.mark.asyncio
async def test_plot_service_separates_business_fields_from_expected_version() -> None:
    repository = RecordingPlotRepository()
    service = OutlineService(repository)  # type: ignore[arg-type]
    expected = datetime(2026, 8, 7, 1, 2, 3, tzinfo=UTC)

    await service.save_plot(
        "user-1",
        "novel-1",
        PlotProgressRequest(**PLOT_FIELDS, expectedUpdatedAt=expected),
    )

    assert repository.saved == ("novel-1", "user-1", PLOT_FIELDS, expected)


@pytest.mark.asyncio
async def test_plot_progress_create_idempotent_update_and_stale_rejection(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "剧情进度.db")
    try:
        await _seed_novels(factory)
        repository = OutlineRepository(factory)

        created = await repository.upsert_plot(
            "novel-1", "user-1", PLOT_FIELDS, None
        )
        created_version = created["updatedAt"]
        assert created["id"]
        assert created_version.microsecond % 1000 == 0

        unchanged = await repository.upsert_plot(
            "novel-1", "user-1", PLOT_FIELDS, created_version
        )
        assert unchanged == created

        changed_fields = {**PLOT_FIELDS, "currentStage": "第二幕"}
        changed = await repository.upsert_plot(
            "novel-1", "user-1", changed_fields, created_version
        )
        changed_version = changed["updatedAt"]
        assert changed_version > created_version
        assert changed_version.microsecond % 1000 == 0

        for stale_fields in (
            {**PLOT_FIELDS, "currentStage": "陈旧覆盖"},
            changed_fields,
        ):
            with pytest.raises(ApiError) as caught:
                await repository.upsert_plot(
                    "novel-1", "user-1", stale_fields, created_version
                )
            assert caught.value.status_code == 409
            assert caught.value.code == "PLOT_PROGRESS_VERSION_CONFLICT"
            assert caught.value.details == {
                "currentUpdatedAt": changed_version.isoformat()
            }

        async with factory() as session:
            current = await session.scalar(
                select(PlotProgress).where(PlotProgress.novelId == "novel-1")
            )
        assert current is not None
        assert current.currentStage == "第二幕"
        assert current.updatedAt.replace(tzinfo=UTC) == changed_version
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plot_progress_missing_resource_only_accepts_null_version(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "剧情进度-首次创建.db")
    try:
        await _seed_novels(factory)
        repository = OutlineRepository(factory)
        stale = datetime(2026, 8, 7, tzinfo=UTC) - timedelta(days=1)

        with pytest.raises(ApiError) as caught:
            await repository.upsert_plot("novel-2", "user-1", PLOT_FIELDS, stale)

        assert caught.value.code == "PLOT_PROGRESS_VERSION_CONFLICT"
        assert caught.value.details == {"currentUpdatedAt": None}
        async with factory() as session:
            assert (
                await session.scalar(
                    select(PlotProgress).where(PlotProgress.novelId == "novel-2")
                )
                is None
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plot_progress_keeps_novel_ownership_boundary(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "剧情进度-归属.db")
    try:
        await _seed_novels(factory)
        repository = OutlineRepository(factory)

        with pytest.raises(ApiError) as caught:
            await repository.upsert_plot("novel-other", "user-1", PLOT_FIELDS, None)

        assert caught.value.status_code == 403
        assert caught.value.code == "NOVEL_FORBIDDEN"
    finally:
        await engine.dispose()
