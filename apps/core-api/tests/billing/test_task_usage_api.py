from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from inkforge_core.app import create_app
from inkforge_core.auth.dependencies import get_current_user
from inkforge_core.auth.repository import AuthUser
from inkforge_core.billing.repository import BillingRepository, UsageDataIntegrityError
from inkforge_core.billing.service import BillingService
from inkforge_core.db.models import TokenUsage
from inkforge_core.errors import ApiError
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


async def _create_database(path: Path) -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path.as_posix()}",
        execution_options={"schema_translate_map": {"public": None}},
    )
    async with engine.begin() as connection:
        await connection.execute(
            text(
                'CREATE TABLE "User" ('
                '"id" TEXT PRIMARY KEY, "username" TEXT NOT NULL, '
                '"passwordHash" TEXT NOT NULL, "creditBalanceMicros" BIGINT NOT NULL)'
            )
        )
        await connection.execute(
            text(
                'CREATE TABLE "Novel" ('
                '"id" TEXT PRIMARY KEY, "name" TEXT NOT NULL, "userId" TEXT)'
            )
        )
        await connection.execute(
            text(
                'CREATE TABLE "WritingTask" ('
                '"id" TEXT PRIMARY KEY, "novelId" TEXT NOT NULL)'
            )
        )
        await connection.execute(
            text(
                'CREATE TABLE "TokenUsage" ('
                '"id" TEXT PRIMARY KEY, "userId" TEXT NOT NULL, "model" TEXT NOT NULL, '
                '"promptTokens" INTEGER NOT NULL, "cachedTokens" INTEGER NOT NULL, '
                '"completionTokens" INTEGER NOT NULL, "totalTokens" INTEGER NOT NULL, '
                '"agentId" TEXT, "novelId" TEXT, "requestId" TEXT, "taskId" TEXT, '
                '"runId" TEXT, "createdAt" TIMESTAMP NOT NULL)'
            )
        )
        await connection.execute(
            text(
                'INSERT INTO "User" '
                '("id", "username", "passwordHash", "creditBalanceMicros") VALUES '
                "('user-owner', 'alice', 'hash', 0), "
                "('user-other', 'bob', 'hash', 0)"
            )
        )
        await connection.execute(
            text(
                'INSERT INTO "Novel" ("id", "name", "userId") VALUES '
                "('novel-owned', '自己的小说', 'user-owner'), "
                "('novel-other', '别人的小说', 'user-other')"
            )
        )
        await connection.execute(
            text(
                'INSERT INTO "WritingTask" ("id", "novelId") VALUES '
                "('task-owned', 'novel-owned'), "
                "('task-empty', 'novel-owned'), "
                "('task-other', 'novel-other')"
            )
        )
        await connection.execute(
            text(
                'INSERT INTO "TokenUsage" ('
                '"id", "userId", "model", "promptTokens", "cachedTokens", '
                '"completionTokens", "totalTokens", "agentId", "novelId", '
                '"requestId", "taskId", "runId", "createdAt") VALUES '
                "('usage-b', 'user-owner', 'deepseek-v4-flash', 100, 40, 20, 120, "
                "'写作', 'novel-owned', 'request-b', 'task-owned', 'run-2', "
                "'2026-08-21 01:00:00'), "
                "('usage-a', 'user-owner', 'deepseek-v4-flash', 50, 10, 30, 80, "
                "'规划', 'novel-owned', 'request-a', 'task-owned', 'run-1', "
                "'2026-08-21 01:00:00'), "
                "('usage-later', 'user-owner', 'deepseek-v4-flash', 25, 5, 5, 30, "
                "'复审', 'novel-owned', 'request-later', 'task-owned', 'run-2', "
                "'2026-08-21 02:00:00'), "
                "('usage-foreign', 'user-other', 'deepseek-v4-flash', 999, 0, 1, 1000, "
                "'写作', 'novel-other', 'request-foreign', 'task-other', 'run-other', "
                "'2026-08-21 03:00:00'), "
                "('usage-legacy', 'user-owner', 'legacy', 777, 0, 0, 777, NULL, "
                "'novel-owned', NULL, NULL, NULL, '2026-08-20 00:00:00')"
            )
        )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def _owned_client(factory: async_sessionmaker) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(testing=True)
    app.state.billing_service = BillingService(BillingRepository(factory), None)
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="user-owner",
        username="alice",
        password_hash="",
        credit_balance_micros=0,
    )
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
async def test_owned_task_returns_exact_usage_summary_and_stable_calls(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "任务用量.db")
    try:
        async with _owned_client(factory) as client:
            response = await client.get("/api/v1/billing/usage/tasks/task-owned")
    finally:
        await engine.dispose()

    assert response.status_code == 200
    assert response.json() == {
        "taskId": "task-owned",
        "requestCount": 3,
        "promptTokens": 175,
        "cachedTokens": 55,
        "completionTokens": 55,
        "totalTokens": 230,
        "calls": [
            {
                "requestId": "request-a",
                "runId": "run-1",
                "agentId": "规划",
                "model": "deepseek-v4-flash",
                "promptTokens": 50,
                "cachedTokens": 10,
                "completionTokens": 30,
                "totalTokens": 80,
                "createdAt": "2026-08-21T01:00:00Z",
            },
            {
                "requestId": "request-b",
                "runId": "run-2",
                "agentId": "写作",
                "model": "deepseek-v4-flash",
                "promptTokens": 100,
                "cachedTokens": 40,
                "completionTokens": 20,
                "totalTokens": 120,
                "createdAt": "2026-08-21T01:00:00Z",
            },
            {
                "requestId": "request-later",
                "runId": "run-2",
                "agentId": "复审",
                "model": "deepseek-v4-flash",
                "promptTokens": 25,
                "cachedTokens": 5,
                "completionTokens": 5,
                "totalTokens": 30,
                "createdAt": "2026-08-21T02:00:00Z",
            },
        ],
    }


@pytest.mark.asyncio
async def test_owned_task_without_usage_returns_zero_summary(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "空任务用量.db")
    try:
        async with _owned_client(factory) as client:
            response = await client.get("/api/v1/billing/usage/tasks/task-empty")
    finally:
        await engine.dispose()

    assert response.status_code == 200
    assert response.json() == {
        "taskId": "task-empty",
        "requestCount": 0,
        "promptTokens": 0,
        "cachedTokens": 0,
        "completionTokens": 0,
        "totalTokens": 0,
        "calls": [],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("task_id", ["task-missing", "task-other"])
async def test_missing_and_foreign_tasks_return_same_404(
    tmp_path: Path, task_id: str
) -> None:
    engine, factory = await _create_database(tmp_path / f"{task_id}.db")
    try:
        async with _owned_client(factory) as client:
            response = await client.get(f"/api/v1/billing/usage/tasks/{task_id}")
    finally:
        await engine.dispose()

    assert response.status_code == 404
    assert response.json()["code"] == "WRITING_TASK_NOT_FOUND"
    assert response.json()["message"] == "写作任务不存在或无权访问"


@pytest.mark.asyncio
async def test_repository_checks_writing_task_ownership_before_reading_usage(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "归属校验.db")
    try:
        repository = BillingRepository(factory)

        assert await repository.get_task_usage("user-owner", "task-other") is None
        owned = await repository.get_task_usage("user-owner", "task-owned")
    finally:
        await engine.dispose()

    assert owned is not None
    assert [call.request_id for call in owned] == [
        "request-a",
        "request-b",
        "request-later",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_field", ["requestId", "runId"])
async def test_repository_rejects_attributed_usage_missing_required_identity(
    tmp_path: Path, missing_field: str
) -> None:
    engine, factory = await _create_database(tmp_path / f"缺少{missing_field}.db")
    try:
        async with factory() as session, session.begin():
            await session.execute(
                update(TokenUsage)
                .where(TokenUsage.id == "usage-a")
                .values({missing_field: None})
            )
        repository = BillingRepository(factory)

        with pytest.raises(
            UsageDataIntegrityError, match="模型用量记录缺少请求或运行标识"
        ):
            await repository.get_task_usage("user-owner", "task-owned")
    finally:
        await engine.dispose()


class _RejectingAuthService:
    async def get_current_user(self, token: str | None) -> AuthUser:
        raise ApiError(status_code=401, code="UNAUTHENTICATED", message="请先登录")


@pytest.mark.asyncio
async def test_task_usage_requires_login() -> None:
    app = create_app(testing=True)
    app.state.auth_service = _RejectingAuthService()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/billing/usage/tasks/task-owned")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
