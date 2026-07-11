from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import (
    Chapter,
    ChapterQualityCheck,
    CreditLedger,
    Novel,
    StylePortraitTask,
    TokenUsage,
    User,
    WritingTask,
)
from .pricing import calculate_usage_cost_micros


class InsufficientCreditsError(Exception):
    """表示余额不足以结算本次真实模型用量。"""


class UsageConflictError(Exception):
    """表示相同请求标识被用于不同的用量载荷。"""


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    balance_micros: int


@dataclass(frozen=True, slots=True)
class ChargeUsage:
    request_id: str
    user_id: str
    novel_id: str
    model: str
    agent_id: str
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class ChargeResult:
    request_id: str
    charged_micros: int
    balance_after_micros: int
    idempotent: bool


@dataclass(frozen=True, slots=True)
class LedgerSnapshot:
    id: str
    type: str
    amount_micros: int
    balance_after_micros: int
    note: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SummarySnapshot:
    username: str
    balance_micros: int
    entries: tuple[LedgerSnapshot, ...]


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int
    total_tokens: int


class BillingRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._sqlite_charge_lock = asyncio.Lock()

    async def get_authorization_context(
        self, user_id: str, task_id: str, novel_id: str
    ) -> AuthorizationContext | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(User.creditBalanceMicros)
                .join(Novel, Novel.userId == User.id)
                .join(WritingTask, WritingTask.novelId == Novel.id)
                .where(User.id == user_id, Novel.id == novel_id, WritingTask.id == task_id)
            )
            balance = result.scalar_one_or_none()
            if balance is None and novel_id.startswith("style:"):
                style_id = novel_id.removeprefix("style:")
                balance = (
                    await session.execute(
                        select(User.creditBalanceMicros)
                        .join(StylePortraitTask, StylePortraitTask.id == task_id)
                        .where(
                            User.id == user_id,
                            StylePortraitTask.styleId == style_id,
                        )
                    )
                ).scalar_one_or_none()
            elif balance is None:
                balance = (
                    await session.execute(
                        select(User.creditBalanceMicros)
                        .join(Novel, Novel.userId == User.id)
                        .join(Chapter, Chapter.novelId == Novel.id)
                        .join(
                            ChapterQualityCheck,
                            ChapterQualityCheck.chapterId == Chapter.id,
                        )
                        .where(
                            User.id == user_id,
                            Novel.id == novel_id,
                            ChapterQualityCheck.id == task_id,
                        )
                    )
                ).scalar_one_or_none()
        return None if balance is None else AuthorizationContext(int(balance))

    async def get_balance(self, user_id: str) -> int | None:
        async with self._session_factory() as session:
            balance = await session.scalar(
                select(User.creditBalanceMicros).where(User.id == user_id)
            )
        return None if balance is None else int(balance)

    async def charge_usage(self, usage: ChargeUsage) -> ChargeResult:
        amount = calculate_usage_cost_micros(
            prompt_tokens=usage.prompt_tokens,
            cached_tokens=usage.cached_tokens,
            completion_tokens=usage.completion_tokens,
        )
        if amount == 0:
            balance = await self.get_balance(usage.user_id)
            if balance is None:
                raise InsufficientCreditsError
            return ChargeResult(
                request_id=usage.request_id,
                charged_micros=0,
                balance_after_micros=balance,
                idempotent=False,
            )
        async with self._session_factory() as probe:
            is_postgresql = probe.bind is not None and probe.bind.dialect.name == "postgresql"
        if is_postgresql:
            return await self._charge_in_transaction(usage, use_advisory_lock=True)
        async with self._sqlite_charge_lock:
            return await self._charge_in_transaction(usage, use_advisory_lock=False)

    async def _charge_in_transaction(
        self, usage: ChargeUsage, *, use_advisory_lock: bool
    ) -> ChargeResult:
        amount = calculate_usage_cost_micros(
            prompt_tokens=usage.prompt_tokens,
            cached_tokens=usage.cached_tokens,
            completion_tokens=usage.completion_tokens,
        )
        async with self._session_factory() as session:
            async with session.begin():
                if use_advisory_lock:
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(:lock_key)"),
                        {"lock_key": _advisory_lock_key(usage.request_id)},
                    )
                existing = (
                    await session.execute(
                        select(CreditLedger)
                        .where(
                            CreditLedger.requestId == usage.request_id,
                            CreditLedger.type == "ai_charge",
                        )
                        .order_by(CreditLedger.createdAt, CreditLedger.id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    if not _same_usage(existing, usage, amount):
                        raise UsageConflictError
                    return ChargeResult(
                        request_id=usage.request_id,
                        charged_micros=amount,
                        balance_after_micros=existing.balanceAfterMicros,
                        idempotent=True,
                    )

                balance_after = await session.scalar(
                    update(User)
                    .where(
                        User.id == usage.user_id,
                        User.creditBalanceMicros >= amount,
                    )
                    .values(creditBalanceMicros=User.creditBalanceMicros - amount)
                    .returning(User.creditBalanceMicros)
                )
                if balance_after is None:
                    raise InsufficientCreditsError
                session.add(
                    CreditLedger(
                        userId=usage.user_id,
                        type="ai_charge",
                        amountMicros=-amount,
                        balanceAfterMicros=balance_after,
                        model=usage.model,
                        promptTokens=usage.prompt_tokens,
                        cachedTokens=usage.cached_tokens,
                        completionTokens=usage.completion_tokens,
                        totalTokens=usage.total_tokens,
                        agentId=usage.agent_id,
                        novelId=usage.novel_id,
                        requestId=usage.request_id,
                        note="人工智能模型调用",
                    )
                )
                session.add(
                    TokenUsage(
                        userId=usage.user_id,
                        model=usage.model,
                        promptTokens=usage.prompt_tokens,
                        cachedTokens=usage.cached_tokens,
                        completionTokens=usage.completion_tokens,
                        totalTokens=usage.total_tokens,
                        agentId=usage.agent_id,
                        novelId=usage.novel_id,
                    )
                )
            return ChargeResult(
                request_id=usage.request_id,
                charged_micros=amount,
                balance_after_micros=int(balance_after),
                idempotent=False,
            )

    async def get_summary(self, user_id: str) -> SummarySnapshot | None:
        async with self._session_factory() as session:
            user_row = (
                await session.execute(
                    select(User.username, User.creditBalanceMicros).where(User.id == user_id)
                )
            ).one_or_none()
            if user_row is None:
                return None
            ledgers = (
                await session.execute(
                    select(CreditLedger)
                    .where(CreditLedger.userId == user_id)
                    .order_by(CreditLedger.createdAt.desc(), CreditLedger.id.desc())
                    .limit(20)
                )
            ).scalars()
            entries = tuple(
                LedgerSnapshot(
                    id=item.id,
                    type=item.type,
                    amount_micros=item.amountMicros,
                    balance_after_micros=item.balanceAfterMicros,
                    note=item.note,
                    created_at=item.createdAt,
                )
                for item in ledgers
            )
        return SummarySnapshot(user_row.username, int(user_row.creditBalanceMicros), entries)

    async def get_usage(
        self, user_id: str, month_start: datetime
    ) -> tuple[UsageSnapshot, UsageSnapshot]:
        columns = (
            func.coalesce(func.sum(TokenUsage.promptTokens), 0),
            func.coalesce(func.sum(TokenUsage.cachedTokens), 0),
            func.coalesce(func.sum(TokenUsage.completionTokens), 0),
            func.coalesce(func.sum(TokenUsage.totalTokens), 0),
        )
        async with self._session_factory() as session:
            total = (
                await session.execute(select(*columns).where(TokenUsage.userId == user_id))
            ).one()
            monthly = (
                await session.execute(
                    select(*columns).where(
                        TokenUsage.userId == user_id,
                        TokenUsage.createdAt >= month_start,
                    )
                )
            ).one()
        return UsageSnapshot(*map(int, total)), UsageSnapshot(*map(int, monthly))


def _advisory_lock_key(request_id: str) -> int:
    raw = int.from_bytes(hashlib.sha256(request_id.encode()).digest()[:8], "big")
    return raw if raw < 2**63 else raw - 2**64


def _same_usage(ledger: CreditLedger, usage: ChargeUsage, amount: int) -> bool:
    return (
        ledger.userId == usage.user_id
        and ledger.novelId == usage.novel_id
        and ledger.model == usage.model
        and ledger.agentId == usage.agent_id
        and ledger.promptTokens == usage.prompt_tokens
        and ledger.cachedTokens == usage.cached_tokens
        and ledger.completionTokens == usage.completion_tokens
        and ledger.totalTokens == usage.total_tokens
        and ledger.amountMicros == -amount
    )
