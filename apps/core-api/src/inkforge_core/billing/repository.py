from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
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


class UsageDataIntegrityError(RuntimeError):
    """表示已归集的模型用量缺少查询所需的权威身份。"""


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    balance_micros: int


@dataclass(frozen=True, slots=True)
class ChargeUsage:
    request_id: str
    user_id: str
    novel_id: str
    task_id: str
    run_id: str
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


@dataclass(frozen=True, slots=True)
class TaskUsageCallSnapshot:
    request_id: str
    run_id: str
    agent_id: str | None
    model: str
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int
    total_tokens: int
    created_at: datetime


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
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    if use_advisory_lock:
                        await session.execute(
                            text("SELECT pg_advisory_xact_lock(:lock_key)"),
                            {"lock_key": _advisory_lock_key(usage.request_id)},
                        )
                    existing = await session.scalar(
                        select(TokenUsage).where(TokenUsage.requestId == usage.request_id)
                    )
                    if existing is not None:
                        return await _idempotent_result(session, existing, usage, amount)

                    if amount > 0:
                        legacy_result = await _legacy_idempotent_result(
                            session, usage, amount
                        )
                        if legacy_result is not None:
                            return legacy_result

                    if amount == 0:
                        balance_after = await session.scalar(
                            select(User.creditBalanceMicros).where(User.id == usage.user_id)
                        )
                    else:
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
                    if amount > 0:
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
                            requestId=usage.request_id,
                            taskId=usage.task_id,
                            runId=usage.run_id,
                        )
                    )
                    await session.flush()
                return ChargeResult(
                    request_id=usage.request_id,
                    charged_micros=amount,
                    balance_after_micros=int(balance_after),
                    idempotent=False,
                )
        except IntegrityError:
            result = await self._resolve_integrity_race(usage, amount)
            if result is None:
                raise
            return result

    async def _resolve_integrity_race(
        self, usage: ChargeUsage, amount: int
    ) -> ChargeResult | None:
        async with self._session_factory() as session:
            existing = await session.scalar(
                select(TokenUsage).where(TokenUsage.requestId == usage.request_id)
            )
            if existing is None:
                return None
            return await _idempotent_result(session, existing, usage, amount)

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

    async def get_task_usage(
        self, user_id: str, task_id: str
    ) -> tuple[TaskUsageCallSnapshot, ...] | None:
        async with self._session_factory() as session:
            owned_task_id = await session.scalar(
                select(WritingTask.id)
                .join(Novel, Novel.id == WritingTask.novelId)
                .where(WritingTask.id == task_id, Novel.userId == user_id)
            )
            if owned_task_id is None:
                return None
            usages = (
                await session.execute(
                    select(TokenUsage)
                    .where(TokenUsage.userId == user_id, TokenUsage.taskId == task_id)
                    .order_by(TokenUsage.createdAt.asc(), TokenUsage.id.asc())
                )
            ).scalars()
            return tuple(_task_usage_call_snapshot(item) for item in usages)


def _advisory_lock_key(request_id: str) -> int:
    raw = int.from_bytes(hashlib.sha256(request_id.encode()).digest()[:8], "big")
    return raw if raw < 2**63 else raw - 2**64


def _task_usage_call_snapshot(item: TokenUsage) -> TaskUsageCallSnapshot:
    if (
        item.requestId is None
        or not item.requestId.strip()
        or item.runId is None
        or not item.runId.strip()
    ):
        raise UsageDataIntegrityError(
            f"模型用量记录缺少请求或运行标识：{item.id}"
        )
    created_at = (
        item.createdAt.replace(tzinfo=UTC)
        if item.createdAt.tzinfo is None
        else item.createdAt.astimezone(UTC)
    )
    return TaskUsageCallSnapshot(
        request_id=item.requestId,
        run_id=item.runId,
        agent_id=item.agentId,
        model=item.model,
        prompt_tokens=item.promptTokens,
        cached_tokens=item.cachedTokens,
        completion_tokens=item.completionTokens,
        total_tokens=item.totalTokens,
        created_at=created_at,
    )


async def _idempotent_result(
    session: AsyncSession,
    existing: TokenUsage,
    usage: ChargeUsage,
    amount: int,
) -> ChargeResult:
    if not _same_usage(existing, usage):
        raise UsageConflictError
    if amount == 0:
        balance_after = await session.scalar(
            select(User.creditBalanceMicros).where(User.id == usage.user_id)
        )
    else:
        balance_after = await session.scalar(
            select(CreditLedger.balanceAfterMicros)
            .where(
                CreditLedger.requestId == usage.request_id,
                CreditLedger.type == "ai_charge",
                CreditLedger.amountMicros == -amount,
            )
            .order_by(CreditLedger.createdAt, CreditLedger.id)
            .limit(1)
        )
    if balance_after is None:
        raise UsageConflictError
    return ChargeResult(
        request_id=usage.request_id,
        charged_micros=amount,
        balance_after_micros=int(balance_after),
        idempotent=True,
    )


def _same_usage(existing: TokenUsage, usage: ChargeUsage) -> bool:
    return (
        existing.userId == usage.user_id
        and existing.novelId == usage.novel_id
        and existing.taskId == usage.task_id
        and existing.runId == usage.run_id
        and existing.model == usage.model
        and existing.agentId == usage.agent_id
        and existing.promptTokens == usage.prompt_tokens
        and existing.cachedTokens == usage.cached_tokens
        and existing.completionTokens == usage.completion_tokens
        and existing.totalTokens == usage.total_tokens
    )


async def _legacy_idempotent_result(
    session: AsyncSession,
    usage: ChargeUsage,
    amount: int,
) -> ChargeResult | None:
    ledgers = (
        await session.execute(
            select(CreditLedger)
            .where(
                CreditLedger.requestId == usage.request_id,
                CreditLedger.type == "ai_charge",
            )
            .order_by(CreditLedger.createdAt, CreditLedger.id)
            .limit(2)
        )
    ).scalars().all()
    if not ledgers:
        return None
    if len(ledgers) != 1 or not _same_legacy_charge(ledgers[0], usage, amount):
        raise UsageConflictError
    return ChargeResult(
        request_id=usage.request_id,
        charged_micros=amount,
        balance_after_micros=int(ledgers[0].balanceAfterMicros),
        idempotent=True,
    )


def _same_legacy_charge(
    existing: CreditLedger,
    usage: ChargeUsage,
    amount: int,
) -> bool:
    return (
        existing.userId == usage.user_id
        and existing.novelId == usage.novel_id
        and existing.model == usage.model
        and existing.agentId == usage.agent_id
        and existing.promptTokens == usage.prompt_tokens
        and existing.cachedTokens == usage.cached_tokens
        and existing.completionTokens == usage.completion_tokens
        and existing.totalTokens == usage.total_tokens
        and existing.amountMicros == -amount
    )
