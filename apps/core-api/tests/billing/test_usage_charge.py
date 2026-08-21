from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from inkforge_core.billing.grants import ModelGrantCodec
from inkforge_core.billing.repository import (
    BillingRepository,
    ChargeUsage,
    InsufficientCreditsError,
    UsageConflictError,
)
from inkforge_core.billing.schemas import ModelGrantClaims, ReportModelUsageRequest
from inkforge_core.billing.service import BillingService
from inkforge_core.db.models import CreditLedger, TokenUsage, User
from sqlalchemy import DefaultClause, MetaData, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


async def _create_database(path: Path) -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path.as_posix()}",
        execution_options={"schema_translate_map": {"public": None}},
    )
    async with engine.begin() as connection:
        metadata = MetaData()
        for table in (User.__table__, CreditLedger.__table__, TokenUsage.__table__):
            table.to_metadata(metadata)
        token_usage_table = metadata.tables["public.TokenUsage"]
        token_usage_table.c.model.server_default = DefaultClause(text("''"))
        for constraint in tuple(token_usage_table.constraints):
            if constraint.name == "TokenUsage_requestId_check":
                token_usage_table.constraints.remove(constraint)
        await connection.run_sync(metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _usage(
    *,
    request_id: str = "request-1",
    task_id: str = "task-1",
    run_id: str = "run-1",
    completion_tokens: int = 20,
) -> ChargeUsage:
    return ChargeUsage(
        request_id=request_id,
        user_id="user-1",
        novel_id="novel-1",
        task_id=task_id,
        run_id=run_id,
        model="deepseek-v4-flash",
        agent_id="写作",
        prompt_tokens=100,
        cached_tokens=40,
        completion_tokens=completion_tokens,
        total_tokens=100 + completion_tokens,
    )


def _empty_usage() -> ChargeUsage:
    return ChargeUsage(
        request_id="request-empty",
        user_id="user-1",
        novel_id="novel-1",
        task_id="task-empty",
        run_id="run-empty",
        model="deepseek-v4-flash",
        agent_id="写作",
        prompt_tokens=0,
        cached_tokens=0,
        completion_tokens=0,
        total_tokens=0,
    )


@pytest.mark.asyncio
async def test_service_persists_identity_from_verified_grant(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "授权身份.db")
    try:
        async with factory() as session, session.begin():
            session.add(
                User(
                    id="user-1",
                    username="alice",
                    passwordHash="固定哈希",
                    creditBalanceMicros=1_000_000,
                )
            )
        now = datetime.now(UTC).replace(microsecond=0)
        claims = ModelGrantClaims(
            requestId="request-from-core",
            taskId="task-from-grant",
            runId="run-from-grant",
            novelId="novel-1",
            userId="user-1",
            provider="openai_compatible",
            model="deepseek-v4-flash",
            agentId="写作",
            maxOutputTokens=1024,
            billable=True,
            iat=int(now.timestamp()),
            exp=int((now + timedelta(minutes=10)).timestamp()),
        )
        codec = ModelGrantCodec(Ed25519PrivateKey.generate())
        service = BillingService(BillingRepository(factory), codec)

        await service.charge(
            ReportModelUsageRequest(
                requestId=claims.requestId,
                taskId=claims.taskId,
                runId=claims.runId,
                novelId=claims.novelId,
                grantToken=codec.issue(claims),
                promptTokens=100,
                cachedTokens=40,
                completionTokens=20,
                totalTokens=120,
            ),
            now=now,
        )

        async with factory() as session:
            usage = (await session.execute(select(TokenUsage))).scalar_one()
        assert usage.requestId == "request-from-core"
        assert usage.taskId == "task-from-grant"
        assert usage.runId == "run-from-grant"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_retry_charges_once(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "幂等.db")
    try:
        async with factory() as session, session.begin():
            session.add(
                User(
                    id="user-1",
                    username="alice",
                    passwordHash="固定哈希",
                    creditBalanceMicros=1_000_000,
                )
            )
        repository = BillingRepository(factory)

        first, second = await asyncio.gather(
            repository.charge_usage(_usage()),
            repository.charge_usage(_usage()),
        )

        assert {first.idempotent, second.idempotent} == {False, True}
        async with factory() as session:
            user = await session.get(User, "user-1")
            ledger_count = (
                await session.execute(select(func.count()).select_from(CreditLedger))
            ).scalar_one()
            usage_count = (
                await session.execute(select(func.count()).select_from(TokenUsage))
            ).scalar_one()
        assert user is not None
        assert user.creditBalanceMicros == 899_200
        assert ledger_count == 1
        assert usage_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "different_value"),
    [
        ("user_id", "user-2"),
        ("novel_id", "novel-2"),
        ("task_id", "task-2"),
        ("run_id", "run-2"),
        ("model", "other-model"),
        ("agent_id", "质检"),
        ("prompt_tokens", 101),
        ("cached_tokens", 41),
        ("completion_tokens", 21),
        ("total_tokens", 121),
    ],
)
async def test_same_request_with_different_identity_or_usage_conflicts(
    tmp_path: Path, field: str, different_value: str | int
) -> None:
    engine, factory = await _create_database(tmp_path / "冲突.db")
    try:
        async with factory() as session, session.begin():
            session.add(
                User(
                    id="user-1",
                    username="alice",
                    passwordHash="固定哈希",
                    creditBalanceMicros=1_000_000,
                )
            )
        repository = BillingRepository(factory)
        original = _usage()
        await repository.charge_usage(original)

        with pytest.raises(UsageConflictError):
            await repository.charge_usage(replace(original, **{field: different_value}))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_integrity_recovery_distinguishes_retry_and_conflict(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "唯一冲突恢复.db")
    try:
        async with factory() as session, session.begin():
            session.add(
                User(
                    id="user-1",
                    username="alice",
                    passwordHash="固定哈希",
                    creditBalanceMicros=1_000_000,
                )
            )
        repository = BillingRepository(factory)
        original = _usage()
        first = await repository.charge_usage(original)

        retry = await repository._resolve_integrity_race(original, first.charged_micros)
        with pytest.raises(UsageConflictError):
            await repository._resolve_integrity_race(
                replace(original, run_id="run-conflict"), first.charged_micros
            )

        async with factory() as session:
            ledger_count = (
                await session.execute(select(func.count()).select_from(CreditLedger))
            ).scalar_one()
            usage_count = (
                await session.execute(select(func.count()).select_from(TokenUsage))
            ).scalar_one()
        assert retry is not None
        assert retry.idempotent is True
        assert retry.balance_after_micros == first.balance_after_micros
        assert ledger_count == 1
        assert usage_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_insufficient_balance_rolls_back_all_writes(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "余额不足.db")
    try:
        async with factory() as session, session.begin():
            session.add(
                User(
                    id="user-1",
                    username="alice",
                    passwordHash="固定哈希",
                    creditBalanceMicros=1,
                )
            )
        repository = BillingRepository(factory)

        with pytest.raises(InsufficientCreditsError):
            await repository.charge_usage(_usage())

        async with factory() as session:
            ledger_count = (
                await session.execute(select(func.count()).select_from(CreditLedger))
            ).scalar_one()
            usage_count = (
                await session.execute(select(func.count()).select_from(TokenUsage))
            ).scalar_one()
        assert ledger_count == 0
        assert usage_count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_zero_usage_writes_one_token_usage_and_retries_idempotently(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "零用量.db")
    try:
        async with factory() as session, session.begin():
            session.add(
                User(
                    id="user-1",
                    username="alice",
                    passwordHash="固定哈希",
                    creditBalanceMicros=1_000_000,
                )
            )
        repository = BillingRepository(factory)
        first = await repository.charge_usage(_empty_usage())
        async with factory() as session, session.begin():
            user = await session.get(User, "user-1")
            assert user is not None
            user.creditBalanceMicros = 900_000
        second = await repository.charge_usage(_empty_usage())

        async with factory() as session:
            user = await session.get(User, "user-1")
            ledger_count = (
                await session.execute(select(func.count()).select_from(CreditLedger))
            ).scalar_one()
            usage_count = (
                await session.execute(select(func.count()).select_from(TokenUsage))
            ).scalar_one()
            usage = (await session.execute(select(TokenUsage))).scalar_one()
        assert first.charged_micros == 0
        assert first.balance_after_micros == 1_000_000
        assert first.idempotent is False
        assert second.charged_micros == 0
        assert second.balance_after_micros == 900_000
        assert second.idempotent is True
        assert user is not None
        assert user.creditBalanceMicros == 900_000
        assert ledger_count == 0
        assert usage_count == 1
        assert usage.requestId == "request-empty"
        assert usage.taskId == "task-empty"
        assert usage.runId == "run-empty"
    finally:
        await engine.dispose()
