from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from inkforge_core.billing.repository import (
    BillingRepository,
    ChargeUsage,
    InsufficientCreditsError,
    UsageConflictError,
)
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
        metadata.tables["public.TokenUsage"].c.model.server_default = DefaultClause(text("''"))
        await connection.run_sync(metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _usage(*, completion_tokens: int = 20) -> ChargeUsage:
    return ChargeUsage(
        request_id="request-1",
        user_id="user-1",
        novel_id="novel-1",
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
        model="deepseek-v4-flash",
        agent_id="写作",
        prompt_tokens=0,
        cached_tokens=0,
        completion_tokens=0,
        total_tokens=0,
    )


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
async def test_same_request_with_different_usage_conflicts(tmp_path: Path) -> None:
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
        await repository.charge_usage(_usage())

        with pytest.raises(UsageConflictError):
            await repository.charge_usage(_usage(completion_tokens=21))
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
async def test_zero_usage_does_not_write_ledger_or_token_usage(tmp_path: Path) -> None:
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
        result = await BillingRepository(factory).charge_usage(_empty_usage())

        async with factory() as session:
            ledger_count = (
                await session.execute(select(func.count()).select_from(CreditLedger))
            ).scalar_one()
            usage_count = (
                await session.execute(select(func.count()).select_from(TokenUsage))
            ).scalar_one()
        assert result.charged_micros == 0
        assert result.balance_after_micros == 1_000_000
        assert ledger_count == 0
        assert usage_count == 0
    finally:
        await engine.dispose()
