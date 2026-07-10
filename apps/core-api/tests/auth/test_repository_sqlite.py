from __future__ import annotations

from pathlib import Path

import pytest
from inkforge_core.auth.repository import AuthRepository
from inkforge_core.db.models import CreditLedger, User
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


async def create_isolated_database(
    path: Path,
) -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path.as_posix()}",
        execution_options={"schema_translate_map": {"public": None}},
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: User.metadata.create_all(
                sync_connection,
                tables=[User.__table__, CreditLedger.__table__],
            )
        )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_real_async_session_commits_user_and_ledger_together(tmp_path: Path) -> None:
    engine, session_factory = await create_isolated_database(tmp_path / "成功.db")
    try:
        repository = AuthRepository(session_factory)
        created = await repository.register_user("alice", "固定哈希")

        async with session_factory() as session:
            users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
            ledger = (await session.execute(select(CreditLedger))).scalar_one()
        assert users == 1
        assert created.credit_balance_micros == 1_000_000_000
        assert ledger.userId == created.id
        assert ledger.type == "signup_bonus"
        assert ledger.amountMicros == 1_000_000_000
        assert ledger.balanceAfterMicros == 1_000_000_000
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_async_session_rolls_back_user_when_ledger_insert_fails(
    tmp_path: Path,
) -> None:
    engine, session_factory = await create_isolated_database(tmp_path / "回滚.db")

    def fail_ledger_insert(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        if statement.lstrip().startswith("INSERT") and '"CreditLedger"' in statement:
            raise RuntimeError("流水写入失败")

    event.listen(engine.sync_engine, "before_cursor_execute", fail_ledger_insert)
    try:
        repository = AuthRepository(session_factory)
        with pytest.raises(RuntimeError, match="流水写入失败"):
            await repository.register_user("alice", "固定哈希")

        async with session_factory() as session:
            users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
            ledgers = (
                await session.execute(select(func.count()).select_from(CreditLedger))
            ).scalar_one()
        assert users == 0
        assert ledgers == 0
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", fail_ledger_insert)
        await engine.dispose()
