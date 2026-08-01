from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol, cast

from pydantic import JsonValue
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from ..db.base import generate_id, utc_now
from ..db.models import WritingEventOutbox, WritingRunCommand, WritingTask
from .sse import EventSequenceGap, EventSourceConflict, WritingEvent

OUTBOX_RETENTION = timedelta(days=7)
OUTBOX_STALE_AFTER = timedelta(minutes=5)
OUTBOX_EVENT_TYPES = frozenset(
    {"completed", "error", "artifact_awaiting_user_approval"}
)


@dataclass(frozen=True, slots=True)
class BoundaryEvent:
    source_event_id: str
    source_sequence: int
    dedupe_key: str
    event_type: str
    payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class OutboxRegistration:
    outbox_id: str | None
    conflict: bool = False


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    id: str
    task_id: str
    command_id: str | None
    source_event_id: str
    source_sequence: int
    durable_baseline: int
    dedupe_key: str
    event_type: str
    payload: Any
    delivery_state: str
    attempt_count: int
    next_attempt_at: datetime
    lease_token: str | None
    lease_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class OutboxHealthStatus:
    blocked_count: int
    stale_unpublished_count: int


class OutboxRepositoryPort(Protocol):
    async def claim_due(
        self, *, now: datetime, limit: int, lease_seconds: int
    ) -> list[OutboxRecord]: ...

    async def mark_published(
        self, outbox_id: str, lease_token: str, redis_event_id: str
    ) -> bool: ...

    async def schedule_retry(
        self,
        outbox_id: str,
        lease_token: str,
        *,
        next_attempt_at: datetime,
        error_code: str,
    ) -> bool: ...

    async def mark_blocked(
        self, outbox_id: str, lease_token: str, *, error_code: str
    ) -> bool: ...

    async def supersede_waiting_if_stale(
        self,
        outbox_id: str,
        lease_token: str,
        *,
        now: datetime,
    ) -> bool: ...

    async def cleanup_terminal(self, *, older_than: datetime) -> int: ...


class OutboxHealthRepositoryPort(Protocol):
    async def health_status(
        self,
        *,
        now: datetime,
        stale_after: timedelta,
    ) -> OutboxHealthStatus: ...


class OutboxEventStorePort(Protocol):
    async def append_agent_event(
        self,
        task_id: str,
        *,
        source_event_id: str,
        sequence: int,
        event: str,
        data: dict[str, JsonValue],
        durable_baseline: int,
        allow_rebase: bool,
    ) -> WritingEvent: ...


class WritingOutboxRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def claim_due(
        self, *, now: datetime, limit: int, lease_seconds: int
    ) -> list[OutboxRecord]:
        candidate = aliased(WritingEventOutbox)
        earlier = aliased(WritingEventOutbox)
        earlier_unpublished = exists(
            select(earlier.id).where(
                earlier.taskId == candidate.taskId,
                earlier.sourceSequence < candidate.sourceSequence,
                earlier.deliveryState.in_(("pending", "delivering", "blocked")),
            )
        )
        claimable = or_(
            (
                (candidate.deliveryState == "pending")
                & (candidate.nextAttemptAt <= now)
            ),
            (
                (candidate.deliveryState == "delivering")
                & (candidate.leaseExpiresAt.is_not(None))
                & (candidate.leaseExpiresAt <= now)
            ),
        )
        async with self._session_factory() as session:
            async with session.begin():
                rows = (
                    await session.scalars(
                        select(candidate)
                        .where(claimable, ~earlier_unpublished)
                        .order_by(
                            candidate.nextAttemptAt,
                            candidate.createdAt,
                            candidate.id,
                        )
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
                lease_expires_at = now + timedelta(seconds=lease_seconds)
                claimed: list[OutboxRecord] = []
                for row in rows:
                    row.deliveryState = "delivering"
                    row.attemptCount += 1
                    row.leaseToken = generate_id()
                    row.leaseExpiresAt = lease_expires_at
                    row.updatedAt = now
                    claimed.append(_record(row))
                await session.flush()
                return claimed

    async def mark_published(
        self, outbox_id: str, lease_token: str, redis_event_id: str
    ) -> bool:
        now = utc_now()
        return await self._finish_lease(
            outbox_id,
            lease_token,
            {
                "deliveryState": "published",
                "redisEventId": redis_event_id,
                "publishedAt": now,
                "lastErrorCode": None,
                "leaseToken": None,
                "leaseExpiresAt": None,
                "updatedAt": now,
            },
        )

    async def schedule_retry(
        self,
        outbox_id: str,
        lease_token: str,
        *,
        next_attempt_at: datetime,
        error_code: str,
    ) -> bool:
        return await self._finish_lease(
            outbox_id,
            lease_token,
            {
                "deliveryState": "pending",
                "nextAttemptAt": next_attempt_at,
                "lastErrorCode": error_code,
                "leaseToken": None,
                "leaseExpiresAt": None,
                "updatedAt": utc_now(),
            },
        )

    async def mark_blocked(
        self, outbox_id: str, lease_token: str, *, error_code: str
    ) -> bool:
        return await self._finish_lease(
            outbox_id,
            lease_token,
            {
                "deliveryState": "blocked",
                "lastErrorCode": error_code,
                "leaseToken": None,
                "leaseExpiresAt": None,
                "updatedAt": utc_now(),
            },
        )

    async def supersede_waiting_if_stale(
        self,
        outbox_id: str,
        lease_token: str,
        *,
        now: datetime,
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    select(WritingEventOutbox)
                    .where(
                        WritingEventOutbox.id == outbox_id,
                        WritingEventOutbox.deliveryState == "delivering",
                        WritingEventOutbox.leaseToken == lease_token,
                    )
                    .with_for_update()
                )
                if (
                    row is None
                    or row.eventType != "artifact_awaiting_user_approval"
                ):
                    return False
                if not await _supersede_waiting_row_if_stale(
                    session,
                    row,
                    now=now,
                ):
                    return False
                await session.flush()
                return True

    async def cleanup_terminal(self, *, older_than: datetime) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    delete(WritingEventOutbox).where(
                        or_(
                            (
                                (WritingEventOutbox.deliveryState == "published")
                                & (WritingEventOutbox.publishedAt.is_not(None))
                                & (WritingEventOutbox.publishedAt < older_than)
                            ),
                            (
                                (WritingEventOutbox.deliveryState == "superseded")
                                & (WritingEventOutbox.updatedAt < older_than)
                            ),
                        )
                    )
                )
                return int(cast(CursorResult[Any], result).rowcount or 0)

    async def health_status(
        self,
        *,
        now: datetime,
        stale_after: timedelta,
    ) -> OutboxHealthStatus:
        stale_before = now - stale_after
        async with self._session_factory() as session:
            blocked_count = await session.scalar(
                select(func.count())
                .select_from(WritingEventOutbox)
                .where(WritingEventOutbox.deliveryState == "blocked")
            )
            stale_unpublished_count = await session.scalar(
                select(func.count())
                .select_from(WritingEventOutbox)
                .where(
                    WritingEventOutbox.deliveryState.in_(("pending", "delivering")),
                    WritingEventOutbox.createdAt < stale_before,
                )
            )
        return OutboxHealthStatus(
            blocked_count=int(blocked_count or 0),
            stale_unpublished_count=int(stale_unpublished_count or 0),
        )

    async def replay_dispositions(
        self,
        events: list[WritingEvent],
    ) -> dict[str, Literal["emit", "skip", "wait"]]:
        boundary_events = [
            event
            for event in events
            if event.event in OUTBOX_EVENT_TYPES and event.source_event_id
        ]
        if not boundary_events:
            return {event.id: "emit" for event in events}
        source_ids = [
            cast(str, event.source_event_id) for event in boundary_events
        ]
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        WritingEventOutbox.sourceEventId,
                        WritingEventOutbox.deliveryState,
                    ).where(WritingEventOutbox.sourceEventId.in_(source_ids))
                )
            ).all()
        states = {source_event_id: state for source_event_id, state in rows}
        dispositions: dict[str, Literal["emit", "skip", "wait"]] = {}
        for event in events:
            if event.event not in OUTBOX_EVENT_TYPES or not event.source_event_id:
                dispositions[event.id] = "emit"
                continue
            state = states.get(event.source_event_id)
            if state is None or state == "published":
                dispositions[event.id] = "emit"
            elif state == "superseded":
                dispositions[event.id] = "skip"
            else:
                dispositions[event.id] = "wait"
        return dispositions

    async def _finish_lease(
        self,
        outbox_id: str,
        lease_token: str,
        values: dict[str, Any],
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(WritingEventOutbox)
                    .where(
                        WritingEventOutbox.id == outbox_id,
                        WritingEventOutbox.deliveryState == "delivering",
                        WritingEventOutbox.leaseToken == lease_token,
                    )
                    .values(**values)
                )
                return bool(cast(CursorResult[Any], result).rowcount)


async def enqueue_boundary_event(
    session: AsyncSession,
    *,
    task_id: str,
    command_id: str | None,
    boundary: BoundaryEvent,
    durable_baseline: int | None,
) -> OutboxRegistration:
    """在调用方已有事务中登记一个持久化业务边界事件。"""
    payload_json = json.dumps(
        boundary.payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    existing = await session.scalar(
        select(WritingEventOutbox)
        .where(
            or_(
                WritingEventOutbox.sourceEventId == boundary.source_event_id,
                WritingEventOutbox.dedupeKey == boundary.dedupe_key,
                (
                    (WritingEventOutbox.taskId == task_id)
                    & (
                        WritingEventOutbox.sourceSequence
                        == boundary.source_sequence
                    )
                ),
            )
        )
        .with_for_update()
    )
    if existing is not None:
        if not _same_boundary_event(
            existing,
            task_id=task_id,
            command_id=command_id,
            boundary=boundary,
            durable_baseline=durable_baseline,
            payload_json=payload_json,
        ):
            return OutboxRegistration(outbox_id=None, conflict=True)
        return OutboxRegistration(outbox_id=existing.id)

    if (
        durable_baseline is None
        or durable_baseline < 0
        or durable_baseline >= boundary.source_sequence
    ):
        return OutboxRegistration(outbox_id=None, conflict=True)

    outbox_id = generate_id()
    session.add(
        WritingEventOutbox(
            id=outbox_id,
            taskId=task_id,
            commandId=command_id,
            sourceEventId=boundary.source_event_id,
            sourceSequence=boundary.source_sequence,
            durableBaseline=durable_baseline,
            dedupeKey=boundary.dedupe_key,
            eventType=boundary.event_type,
            payloadJson=payload_json,
            nextAttemptAt=utc_now(),
        )
    )
    await session.flush()
    return OutboxRegistration(outbox_id=outbox_id)


async def supersede_waiting_for_new_command(
    session: AsyncSession,
    *,
    task_id: str,
    now: datetime | None = None,
) -> int:
    """在新命令事务中关闭尚未发布的旧等待通知。"""
    changed_at = now or utc_now()
    result = await session.execute(
        update(WritingEventOutbox)
        .where(
            WritingEventOutbox.taskId == task_id,
            WritingEventOutbox.eventType
            == "artifact_awaiting_user_approval",
            WritingEventOutbox.deliveryState.in_(
                ("pending", "delivering", "blocked")
            ),
        )
        .values(
            deliveryState="superseded",
            lastErrorCode="OUTBOX_WAITING_SUPERSEDED",
            leaseToken=None,
            leaseExpiresAt=None,
            updatedAt=changed_at,
        )
    )
    return int(cast(CursorResult[Any], result).rowcount or 0)


class WritingOutboxPublisher:
    def __init__(
        self,
        repository: OutboxRepositoryPort,
        event_store: OutboxEventStorePort,
        *,
        clock: Any = utc_now,
        batch_size: int = 20,
        lease_seconds: int = 30,
        interval_seconds: float = 1.0,
        cleanup_interval_seconds: float = 3_600,
    ) -> None:
        if (
            batch_size < 1
            or lease_seconds < 1
            or interval_seconds <= 0
            or cleanup_interval_seconds <= 0
        ):
            raise ValueError("Outbox publisher 配置无效")
        self._repository = repository
        self._event_store = event_store
        self._clock = clock
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._interval_seconds = interval_seconds
        self._cleanup_interval_seconds = cleanup_interval_seconds
        self._next_cleanup_at: datetime | None = None
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        while not self._stop.is_set():
            await self.run_once()
            await self._run_cleanup_if_due()
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                pass

    async def run_once(self) -> int:
        now = cast(datetime, self._clock())
        records = await self._repository.claim_due(
            now=now,
            limit=self._batch_size,
            lease_seconds=self._lease_seconds,
        )
        published = 0
        for record in records:
            lease_token = record.lease_token
            if lease_token is None:
                continue
            error_code = _record_contract_error(record)
            if error_code is not None:
                await self._repository.mark_blocked(
                    record.id,
                    lease_token,
                    error_code=error_code,
                )
                continue
            if (
                record.event_type == "artifact_awaiting_user_approval"
                and await self._repository.supersede_waiting_if_stale(
                    record.id,
                    lease_token,
                    now=now,
                )
            ):
                continue
            try:
                event = await self._event_store.append_agent_event(
                    record.task_id,
                    source_event_id=record.source_event_id,
                    sequence=record.source_sequence,
                    event=record.event_type,
                    data=cast(dict[str, JsonValue], record.payload),
                    durable_baseline=record.durable_baseline,
                    allow_rebase=True,
                )
            except EventSequenceGap:
                if (
                    record.event_type == "artifact_awaiting_user_approval"
                    and await self._repository.supersede_waiting_if_stale(
                        record.id,
                        lease_token,
                        now=now,
                    )
                ):
                    continue
                await self._repository.mark_blocked(
                    record.id,
                    lease_token,
                    error_code="OUTBOX_EVENT_SEQUENCE_GAP",
                )
                continue
            except EventSourceConflict:
                await self._repository.mark_blocked(
                    record.id,
                    lease_token,
                    error_code="OUTBOX_EVENT_SOURCE_CONFLICT",
                )
                continue
            except (
                ConnectionError,
                TimeoutError,
                OSError,
                RedisConnectionError,
                RedisTimeoutError,
            ):
                delay = _retry_delay_seconds(record.attempt_count)
                await self._repository.schedule_retry(
                    record.id,
                    lease_token,
                    next_attempt_at=now + timedelta(seconds=delay),
                    error_code="OUTBOX_REDIS_UNAVAILABLE",
                )
                continue
            if await self._repository.mark_published(
                record.id,
                lease_token,
                event.id,
            ):
                published += 1
        return published

    async def _run_cleanup_if_due(self) -> None:
        now = cast(datetime, self._clock())
        if self._next_cleanup_at is not None and now < self._next_cleanup_at:
            return
        await self._repository.cleanup_terminal(older_than=now - OUTBOX_RETENTION)
        self._next_cleanup_at = now + timedelta(
            seconds=self._cleanup_interval_seconds
        )


class WritingOutboxReadiness:
    def __init__(
        self,
        repository: OutboxHealthRepositoryPort,
        *,
        stale_after: timedelta = OUTBOX_STALE_AFTER,
        clock: Any = utc_now,
    ) -> None:
        if stale_after <= timedelta(0):
            raise ValueError("Outbox 健康检查积压阈值无效")
        self._repository = repository
        self._stale_after = stale_after
        self._clock = clock
        self._error_code: str | None = None

    async def check(self) -> bool:
        self._error_code = "OUTBOX_HEALTH_UNAVAILABLE"
        status = await self._repository.health_status(
            now=cast(datetime, self._clock()),
            stale_after=self._stale_after,
        )
        if status.blocked_count and status.stale_unpublished_count:
            self._error_code = "OUTBOX_BLOCKED_AND_STALE_BACKLOG"
        elif status.blocked_count:
            self._error_code = "OUTBOX_BLOCKED"
        elif status.stale_unpublished_count:
            self._error_code = "OUTBOX_STALE_BACKLOG"
        else:
            self._error_code = None
        return self._error_code is None

    def error_codes(self) -> dict[str, str]:
        if self._error_code is None:
            return {}
        return {"writing_outbox": self._error_code}


def _record(row: WritingEventOutbox) -> OutboxRecord:
    try:
        payload = json.loads(row.payloadJson)
    except (json.JSONDecodeError, TypeError):
        payload = object()
    return OutboxRecord(
        id=row.id,
        task_id=row.taskId,
        command_id=row.commandId,
        source_event_id=row.sourceEventId,
        source_sequence=row.sourceSequence,
        durable_baseline=row.durableBaseline,
        dedupe_key=row.dedupeKey,
        event_type=row.eventType,
        payload=payload,
        delivery_state=row.deliveryState,
        attempt_count=row.attemptCount,
        next_attempt_at=row.nextAttemptAt,
        lease_token=row.leaseToken,
        lease_expires_at=row.leaseExpiresAt,
    )


async def _supersede_waiting_row_if_stale(
    session: AsyncSession,
    row: WritingEventOutbox,
    *,
    now: datetime,
) -> bool:
    if row.eventType != "artifact_awaiting_user_approval":
        return False
    task_phase = await session.scalar(
        select(WritingTask.phase).where(WritingTask.id == row.taskId)
    )
    later_command_id = await session.scalar(
        select(WritingRunCommand.id)
        .where(
            WritingRunCommand.taskId == row.taskId,
            WritingRunCommand.id != row.commandId,
            WritingRunCommand.createdAt >= row.createdAt,
        )
        .order_by(
            WritingRunCommand.createdAt.desc(),
            WritingRunCommand.id.desc(),
        )
        .limit(1)
    )
    if task_phase not in {"completed", "error"} and later_command_id is None:
        return False
    row.deliveryState = "superseded"
    row.lastErrorCode = "OUTBOX_WAITING_SUPERSEDED"
    row.leaseToken = None
    row.leaseExpiresAt = None
    row.updatedAt = now
    return True


def _is_json_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    try:
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return False
    return True


def _record_contract_error(record: OutboxRecord) -> str | None:
    if not _is_json_payload(record.payload):
        return "OUTBOX_PAYLOAD_INVALID"
    if (
        not record.task_id.strip()
        or not record.source_event_id.strip()
        or not record.dedupe_key.strip()
        or record.source_sequence <= 0
        or record.durable_baseline < 0
        or record.durable_baseline >= record.source_sequence
        or record.event_type not in OUTBOX_EVENT_TYPES
    ):
        return "OUTBOX_CONTRACT_INVALID"
    return None


def _retry_delay_seconds(attempt_count: int) -> int:
    return int(min(60, max(1, 2 ** max(0, attempt_count - 1))))


def _same_boundary_event(
    existing: WritingEventOutbox,
    *,
    task_id: str,
    command_id: str | None,
    boundary: BoundaryEvent,
    durable_baseline: int | None,
    payload_json: str,
) -> bool:
    return (
        existing.taskId == task_id
        and existing.commandId == command_id
        and existing.sourceEventId == boundary.source_event_id
        and existing.sourceSequence == boundary.source_sequence
        and (
            durable_baseline is None
            or existing.durableBaseline == durable_baseline
        )
        and existing.dedupeKey == boundary.dedupe_key
        and existing.eventType == boundary.event_type
        and existing.payloadJson == payload_json
    )
