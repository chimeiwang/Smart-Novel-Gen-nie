from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from inkforge_core.db.models import Novel, User, WritingStyle
from inkforge_core.errors import ApiError
from inkforge_core.styles.repository import StyleRepository
from inkforge_core.styles.schemas import ApplyStyleRequest
from pydantic import ValidationError
from sqlalchemy import DefaultClause, MetaData, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


async def _create_database(path: Path) -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path.as_posix()}",
        execution_options={"schema_translate_map": {"public": None}},
    )
    async with engine.begin() as connection:
        metadata = MetaData()
        for table in (User.__table__, WritingStyle.__table__, Novel.__table__):
            table.to_metadata(metadata)
        metadata.tables["public.WritingStyle"].c.sourceType.server_default = DefaultClause(
            text("'manual'")
        )
        await connection.run_sync(metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed(factory: async_sessionmaker) -> None:
    async with factory() as session, session.begin():
        session.add_all(
            [
                User(id="user-1", username="user-1", passwordHash="固定哈希"),
                User(id="user-2", username="user-2", passwordHash="固定哈希"),
                WritingStyle(
                    id="style-old",
                    userId="user-1",
                    name="旧文风",
                    portraitMarkdown="完整画像",
                ),
                WritingStyle(
                    id="style-new",
                    userId="user-1",
                    name="新文风",
                    portraitMarkdown="完整画像",
                ),
                WritingStyle(
                    id="style-incomplete",
                    userId="user-1",
                    name="未完成文风",
                    portraitMarkdown=None,
                ),
                WritingStyle(
                    id="style-foreign",
                    userId="user-2",
                    name="他人文风",
                    portraitMarkdown="完整画像",
                ),
                Novel(
                    id="novel-current",
                    userId="user-1",
                    name="已有文风作品",
                    appliedStyleId="style-old",
                ),
                Novel(id="novel-empty", userId="user-1", name="未应用文风作品"),
                Novel(id="novel-foreign", userId="user-2", name="他人作品"),
            ]
        )


async def _current_style(factory: async_sessionmaker, novel_id: str) -> str | None:
    async with factory() as session:
        return await session.scalar(
            select(Novel.appliedStyleId).where(Novel.id == novel_id)
        )


def test_apply_style_request_requires_both_explicit_nullable_values() -> None:
    for body in ({}, {"styleId": None}, {"expectedStyleId": None}):
        with pytest.raises(ValidationError):
            ApplyStyleRequest.model_validate(body)

    request = ApplyStyleRequest.model_validate(
        {"styleId": None, "expectedStyleId": None}
    )
    assert request.styleId is None
    assert request.expectedStyleId is None


@pytest.mark.asyncio
async def test_apply_style_rejects_stale_version_before_validating_target(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "文风冲突.db")
    try:
        await _seed(factory)
        repository = StyleRepository(factory)

        with pytest.raises(ApiError) as caught:
            await repository.apply_style(
                "novel-current",
                "user-1",
                "style-foreign",
                expected_style_id=None,
            )

        assert caught.value.status_code == 409
        assert caught.value.code == "APPLIED_STYLE_VERSION_CONFLICT"
        assert caught.value.details == {"currentStyleId": "style-old"}
        assert await _current_style(factory, "novel-current") == "style-old"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_apply_style_supports_apply_clear_and_idempotency(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "文风应用.db")
    try:
        await _seed(factory)
        repository = StyleRepository(factory)

        unchanged = await repository.apply_style(
            "novel-current",
            "user-1",
            "style-old",
            expected_style_id="style-old",
        )
        assert unchanged == {"styleId": "style-old", "effective": False}

        applied = await repository.apply_style(
            "novel-empty",
            "user-1",
            "style-new",
            expected_style_id=None,
        )
        assert applied == {"styleId": "style-new", "effective": True}
        assert await _current_style(factory, "novel-empty") == "style-new"

        cleared = await repository.apply_style(
            "novel-current",
            "user-1",
            None,
            expected_style_id="style-old",
        )
        assert cleared == {"styleId": None, "effective": True}
        assert await _current_style(factory, "novel-current") is None

        clear_again = await repository.apply_style(
            "novel-current",
            "user-1",
            None,
            expected_style_id=None,
        )
        assert clear_again == {"styleId": None, "effective": False}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("style_id", "code"),
    [
        ("style-foreign", "STYLE_NOT_FOUND"),
        ("style-incomplete", "STYLE_PORTRAIT_INCOMPLETE"),
    ],
)
async def test_apply_style_preserves_style_ownership_and_portrait_requirements(
    tmp_path: Path,
    style_id: str,
    code: str,
) -> None:
    engine, factory = await _create_database(tmp_path / f"{style_id}.db")
    try:
        await _seed(factory)
        repository = StyleRepository(factory)

        with pytest.raises(ApiError) as caught:
            await repository.apply_style(
                "novel-current",
                "user-1",
                style_id,
                expected_style_id="style-old",
            )

        assert caught.value.code == code
        assert await _current_style(factory, "novel-current") == "style-old"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_apply_style_preserves_novel_ownership(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "小说归属.db")
    try:
        await _seed(factory)
        repository = StyleRepository(factory)

        with pytest.raises(ApiError) as caught:
            await repository.apply_style(
                "novel-foreign",
                "user-1",
                None,
                expected_style_id=None,
            )

        assert caught.value.code == "NOVEL_NOT_FOUND"
        assert await _current_style(factory, "novel-foreign") is None
    finally:
        await engine.dispose()


class RecordingTransaction:
    def __init__(self) -> None:
        self.rolled_back = False

    @asynccontextmanager
    async def begin(self):
        try:
            yield
        except Exception:
            self.rolled_back = True
            raise


class RecordingSession(RecordingTransaction):
    def __init__(self) -> None:
        super().__init__()
        self.novel = Novel(
            id="novel-current",
            userId="user-1",
            name="作品",
            appliedStyleId="style-old",
        )
        self.queries: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    async def scalar(self, statement):
        rendered = str(statement)
        self.queries.append(rendered)
        return self.novel


@pytest.mark.asyncio
async def test_apply_style_locks_novel_and_rolls_back_conflict() -> None:
    session = RecordingSession()
    repository = StyleRepository(lambda: session)  # type: ignore[arg-type]

    with pytest.raises(ApiError) as caught:
        await repository.apply_style(
            "novel-current",
            "user-1",
            None,
            expected_style_id=None,
        )

    assert caught.value.code == "APPLIED_STYLE_VERSION_CONFLICT"
    assert len(session.queries) == 1
    assert '"Novel"' in session.queries[0]
    assert "FOR UPDATE" in session.queries[0]
    assert session.rolled_back is True
    assert session.novel.appliedStyleId == "style-old"
