from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import DefaultClause, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

NOW = datetime(2026, 8, 1, 12, 0, 0)


async def _create_outbox_database(
    path: Path,
) -> tuple[AsyncEngine, async_sessionmaker]:
    from inkforge_core.db.base import Base
    from inkforge_core.db.models import WritingEventOutbox

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path.as_posix()}",
        execution_options={"schema_translate_map": {"public": None}},
    )
    delivery_default = WritingEventOutbox.__table__.c.deliveryState.server_default
    WritingEventOutbox.__table__.c.deliveryState.server_default = DefaultClause(
        text("'pending'")
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=[WritingEventOutbox.__table__],
                )
            )
    finally:
        WritingEventOutbox.__table__.c.deliveryState.server_default = delivery_default
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _create_writing_outbox_database(
    path: Path,
) -> tuple[AsyncEngine, async_sessionmaker]:
    from inkforge_core.db.base import Base
    from inkforge_core.db.models import (
        WritingEventOutbox,
        WritingRunCommand,
        WritingTask,
    )

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path.as_posix()}",
        execution_options={"schema_translate_map": {"public": None}},
    )
    defaults = (
        (WritingTask.__table__.c.phase, "'idle'"),
        (WritingRunCommand.__table__.c.status, "'pending'"),
        (WritingEventOutbox.__table__.c.deliveryState, "'pending'"),
    )
    original_defaults = [(column, column.server_default) for column, _ in defaults]
    for column, default in defaults:
        column.server_default = DefaultClause(text(default))
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=[
                        WritingTask.__table__,
                        WritingRunCommand.__table__,
                        WritingEventOutbox.__table__,
                    ],
                )
            )
            await connection.execute(
                text('DROP INDEX "WritingRunCommand_active_task_key"')
            )
    finally:
        for column, original in original_defaults:
            column.server_default = original
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_writing_event_outbox_metadata_has_delivery_and_ordering_guards() -> None:
    from inkforge_core.db import models

    assert hasattr(models, "WritingEventOutbox")
    table = models.WritingEventOutbox.__table__

    assert set(table.c.keys()) == {
        "id",
        "taskId",
        "commandId",
        "sourceEventId",
        "sourceSequence",
        "durableBaseline",
        "dedupeKey",
        "eventType",
        "payloadJson",
        "deliveryState",
        "attemptCount",
        "nextAttemptAt",
        "leaseToken",
        "leaseExpiresAt",
        "lastErrorCode",
        "redisEventId",
        "createdAt",
        "updatedAt",
        "publishedAt",
    }
    assert table.c.taskId.nullable is False
    assert table.c.commandId.nullable is True
    assert next(iter(table.c.taskId.foreign_keys)).target_fullname == "public.WritingTask.id"
    assert next(iter(table.c.commandId.foreign_keys)).target_fullname == (
        "public.WritingRunCommand.id"
    )
    assert {index.name for index in table.indexes if index.unique} == {
        "WritingEventOutbox_sourceEventId_key",
        "WritingEventOutbox_dedupeKey_key",
        "WritingEventOutbox_taskId_sourceSequence_key",
    }
    assert "WritingEventOutbox_due_idx" in {index.name for index in table.indexes}
    assert "WritingEventOutbox_task_sequence_idx" in {
        index.name for index in table.indexes
    }


def _outbox_record(module: Any, **overrides: Any) -> Any:
    values = {
        "id": "outbox-1",
        "task_id": "task-1",
        "command_id": "command-1",
        "source_event_id": "event-1",
        "source_sequence": 3,
        "durable_baseline": 2,
        "dedupe_key": "command-1:terminal",
        "event_type": "completed",
        "payload": {"taskId": "task-1"},
        "delivery_state": "pending",
        "attempt_count": 0,
        "next_attempt_at": NOW,
        "lease_token": None,
        "lease_expires_at": None,
    }
    if "source_sequence" in overrides and "durable_baseline" not in overrides:
        values["durable_baseline"] = max(0, int(overrides["source_sequence"]) - 1)
    values.update(overrides)
    return module.OutboxRecord(**values)


async def test_outbox_repository_claim_uses_leases_and_preserves_task_order(
    tmp_path: Path,
) -> None:
    from inkforge_core.db.models import WritingEventOutbox
    from inkforge_core.writing import outbox as module

    assert hasattr(module, "WritingOutboxRepository")
    engine, session_factory = await _create_outbox_database(tmp_path / "outbox.db")
    try:
        async with session_factory() as session:
            async with session.begin():
                session.add_all(
                    [
                        WritingEventOutbox(
                            id="a-1",
                            taskId="task-1",
                            commandId=None,
                            sourceEventId="event-a-1",
                            sourceSequence=1,
                            durableBaseline=0,
                            dedupeKey="a:1",
                            eventType="completed",
                            payloadJson='{"taskId":"task-1"}',
                            deliveryState="pending",
                            attemptCount=0,
                            nextAttemptAt=NOW,
                        ),
                        WritingEventOutbox(
                            id="a-2",
                            taskId="task-1",
                            commandId=None,
                            sourceEventId="event-a-2",
                            sourceSequence=2,
                            durableBaseline=1,
                            dedupeKey="a:2",
                            eventType="completed",
                            payloadJson='{"taskId":"task-1"}',
                            deliveryState="pending",
                            attemptCount=0,
                            nextAttemptAt=NOW,
                        ),
                        WritingEventOutbox(
                            id="b-1",
                            taskId="task-2",
                            commandId=None,
                            sourceEventId="event-b-1",
                            sourceSequence=1,
                            durableBaseline=0,
                            dedupeKey="b:1",
                            eventType="error",
                            payloadJson='{"taskId":"task-2"}',
                            deliveryState="pending",
                            attemptCount=0,
                            nextAttemptAt=NOW,
                        ),
                    ]
                )
        repository = module.WritingOutboxRepository(session_factory)

        claimed = await repository.claim_due(now=NOW, limit=20, lease_seconds=30)

        assert [(item.task_id, item.source_sequence) for item in claimed] == [
            ("task-1", 1),
            ("task-2", 1),
        ]
        assert all(item.delivery_state == "delivering" for item in claimed)
        assert all(item.attempt_count == 1 for item in claimed)
        assert all(item.lease_token for item in claimed)
        assert all(item.lease_expires_at == NOW + timedelta(seconds=30) for item in claimed)
    finally:
        await engine.dispose()


async def test_outbox_repository_rejects_stale_worker_completion(tmp_path: Path) -> None:
    from inkforge_core.db.models import WritingEventOutbox
    from inkforge_core.writing import outbox as module

    assert hasattr(module, "WritingOutboxRepository")
    engine, session_factory = await _create_outbox_database(tmp_path / "lease.db")
    try:
        async with session_factory() as session:
            async with session.begin():
                session.add(
                    WritingEventOutbox(
                        id="outbox-1",
                        taskId="task-1",
                        commandId=None,
                        sourceEventId="event-1",
                        sourceSequence=1,
                        durableBaseline=0,
                        dedupeKey="command-1:terminal",
                        eventType="completed",
                        payloadJson='{"taskId":"task-1"}',
                        deliveryState="pending",
                        attemptCount=0,
                        nextAttemptAt=NOW,
                    )
                )
        repository = module.WritingOutboxRepository(session_factory)
        claimed = await repository.claim_due(now=NOW, limit=1, lease_seconds=30)
        assert len(claimed) == 1
        current_lease = claimed[0].lease_token
        assert current_lease is not None

        assert await repository.mark_published(
            "outbox-1", "stale-lease", "redis-stale"
        ) is False
        assert await repository.mark_published(
            "outbox-1", current_lease, "redis-1"
        ) is True

        async with session_factory() as session:
            row = await session.get(WritingEventOutbox, "outbox-1")
            assert row is not None
            assert row.deliveryState == "published"
            assert row.redisEventId == "redis-1"
            assert row.publishedAt is not None
            assert row.leaseToken is None
    finally:
        await engine.dispose()


class _FakeOutboxRepository:
    def __init__(self, module: Any, records: list[Any]) -> None:
        self.module = module
        self.records = records
        self.published: list[tuple[str, str, str]] = []
        self.retried: list[tuple[str, str, datetime]] = []
        self.blocked: list[tuple[str, str, str]] = []
        self.superseded: set[str] = set()
        self.cleaned_before: list[datetime] = []

    async def claim_due(self, *, now: datetime, limit: int, lease_seconds: int) -> list[Any]:
        del limit
        claimed: list[Any] = []
        seen_tasks: set[str] = set()
        for record in sorted(self.records, key=lambda item: (item.task_id, item.source_sequence)):
            if record.task_id in seen_tasks or record.next_attempt_at > now:
                continue
            seen_tasks.add(record.task_id)
            claimed.append(
                replace(
                    record,
                    delivery_state="delivering",
                    attempt_count=record.attempt_count + 1,
                    lease_token=f"lease-{record.id}",
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                )
            )
        return claimed

    async def mark_published(
        self, outbox_id: str, lease_token: str, redis_event_id: str
    ) -> bool:
        self.published.append((outbox_id, lease_token, redis_event_id))
        return True

    async def schedule_retry(
        self,
        outbox_id: str,
        lease_token: str,
        *,
        next_attempt_at: datetime,
        error_code: str,
    ) -> bool:
        self.retried.append((outbox_id, error_code, next_attempt_at))
        return True

    async def mark_blocked(
        self, outbox_id: str, lease_token: str, *, error_code: str
    ) -> bool:
        self.blocked.append((outbox_id, lease_token, error_code))
        return True

    async def supersede_waiting_if_stale(
        self,
        outbox_id: str,
        lease_token: str,
        *,
        now: datetime,
    ) -> bool:
        del lease_token, now
        return outbox_id in self.superseded

    async def cleanup_terminal(self, *, older_than: datetime) -> int:
        self.cleaned_before.append(older_than)
        return 0


class _FakeEventStore:
    def __init__(
        self,
        *,
        error: Exception | None = None,
        errors_by_task: dict[str, Exception] | None = None,
    ) -> None:
        self.error = error
        self.errors_by_task = errors_by_task or {}
        self.appended: list[dict[str, Any]] = []

    async def append_agent_event(self, task_id: str, **kwargs: Any) -> Any:
        if task_id in self.errors_by_task:
            raise self.errors_by_task[task_id]
        if self.error is not None:
            raise self.error
        self.appended.append({"task_id": task_id, **kwargs})
        return type("Event", (), {"id": "redis-1"})()


async def test_publisher_claims_only_the_first_event_per_task_and_marks_delivery() -> None:
    from inkforge_core.writing import outbox as module

    repository = _FakeOutboxRepository(
        module,
        [
            _outbox_record(module, id="a-2", source_sequence=2),
            _outbox_record(module, id="a-1", source_sequence=1),
            _outbox_record(
                module,
                id="b-1",
                task_id="task-2",
                source_event_id="event-b",
                source_sequence=1,
                dedupe_key="command-2:terminal",
            ),
        ],
    )
    store = _FakeEventStore()
    publisher = module.WritingOutboxPublisher(repository, store, clock=lambda: NOW)

    published = await publisher.run_once()

    assert published == 2
    assert [(item["task_id"], item["sequence"]) for item in store.appended] == [
        ("task-1", 1),
        ("task-2", 1),
    ]
    assert [item[0] for item in repository.published] == ["a-1", "b-1"]


async def test_publisher_does_not_confirm_waiting_if_new_command_wins_after_xadd() -> None:
    from inkforge_core.writing import outbox as module

    class SupersedingRepository(_FakeOutboxRepository):
        def __init__(self) -> None:
            super().__init__(
                module,
                [
                    _outbox_record(
                        module,
                        event_type="artifact_awaiting_user_approval",
                    )
                ],
            )
            self.mark_attempts = 0

        async def mark_published(
            self, outbox_id: str, lease_token: str, redis_event_id: str
        ) -> bool:
            del lease_token, redis_event_id
            self.mark_attempts += 1
            self.superseded.add(outbox_id)
            return False

    repository = SupersedingRepository()
    store = _FakeEventStore()
    publisher = module.WritingOutboxPublisher(repository, store, clock=lambda: NOW)

    assert await publisher.run_once() == 0
    assert repository.mark_attempts == 1
    assert len(store.appended) == 1
    assert repository.published == []


async def test_repository_classifies_outbox_boundaries_before_sse_replay(
    tmp_path: Path,
) -> None:
    from inkforge_core.db.models import WritingEventOutbox
    from inkforge_core.writing import outbox as module
    from inkforge_core.writing.sse import WritingEvent

    engine, session_factory = await _create_outbox_database(
        tmp_path / "outbox-visibility.db"
    )
    try:
        rows = []
        for index, state in enumerate(
            ("published", "superseded", "delivering", "blocked"),
            start=1,
        ):
            row = WritingEventOutbox(
                id=f"outbox-{index}",
                taskId="task-1",
                commandId=None,
                sourceEventId=f"source-{state}",
                sourceSequence=index,
                durableBaseline=index - 1,
                dedupeKey=f"dedupe-{state}",
                eventType="artifact_awaiting_user_approval",
                payloadJson="{}",
                deliveryState=state,
                attemptCount=1,
                nextAttemptAt=NOW,
                createdAt=NOW,
                updatedAt=NOW,
            )
            if state == "published":
                row.redisEventId = "redis-published"
                row.publishedAt = NOW
            if state == "delivering":
                row.leaseToken = "lease-delivering"
                row.leaseExpiresAt = NOW + timedelta(seconds=30)
            rows.append(row)
        async with session_factory() as session:
            async with session.begin():
                session.add_all(rows)

        events = [
            WritingEvent(
                id=str(index),
                event="artifact_awaiting_user_approval",
                data={},
                occurred_at=NOW,
                source_event_id=source_id,
                sequence=index,
            )
            for index, source_id in enumerate(
                (
                    "source-published",
                    "source-superseded",
                    "source-delivering",
                    "source-blocked",
                    "legacy-source",
                ),
                start=1,
            )
        ]
        events.append(
            WritingEvent(
                id="6",
                event="agent_status",
                data={},
                occurred_at=NOW,
                source_event_id="ordinary-source",
                sequence=6,
            )
        )

        repository = module.WritingOutboxRepository(session_factory)

        assert await repository.replay_dispositions(events) == {
            "1": "emit",
            "2": "skip",
            "3": "wait",
            "4": "wait",
            "5": "emit",
            "6": "emit",
        }
    finally:
        await engine.dispose()


async def test_publisher_retries_redis_failure_without_changing_business_state() -> None:
    from inkforge_core.writing import outbox as module

    repository = _FakeOutboxRepository(module, [_outbox_record(module)])
    store = _FakeEventStore(error=ConnectionError("redis unavailable"))
    publisher = module.WritingOutboxPublisher(repository, store, clock=lambda: NOW)

    published = await publisher.run_once()

    assert published == 0
    assert repository.published == []
    assert repository.retried[0][0:2] == ("outbox-1", "OUTBOX_REDIS_UNAVAILABLE")
    assert NOW < repository.retried[0][2] <= NOW + timedelta(seconds=60)


@pytest.mark.parametrize(
    "error",
    [RedisConnectionError("redis unavailable"), RedisTimeoutError("redis timeout")],
)
async def test_publisher_retries_real_redis_client_transient_errors(
    error: Exception,
) -> None:
    from inkforge_core.writing import outbox as module

    repository = _FakeOutboxRepository(module, [_outbox_record(module)])
    publisher = module.WritingOutboxPublisher(
        repository,
        _FakeEventStore(error=error),
        clock=lambda: NOW,
    )

    assert await publisher.run_once() == 0
    assert repository.retried[0][0:2] == (
        "outbox-1",
        "OUTBOX_REDIS_UNAVAILABLE",
    )


async def test_publisher_blocks_invalid_payload_instead_of_looping() -> None:
    from inkforge_core.writing import outbox as module

    repository = _FakeOutboxRepository(
        module,
        [_outbox_record(module, payload={"invalid": object()})],
    )
    publisher = module.WritingOutboxPublisher(
        repository,
        _FakeEventStore(),
        clock=lambda: NOW,
    )

    published = await publisher.run_once()

    assert published == 0
    assert repository.blocked == [
        ("outbox-1", "lease-outbox-1", "OUTBOX_PAYLOAD_INVALID")
    ]


async def test_publisher_blocks_sequence_gap_and_continues_other_tasks() -> None:
    from inkforge_core.writing import outbox as module
    from inkforge_core.writing.sse import EventSequenceGap

    repository = _FakeOutboxRepository(
        module,
        [
            _outbox_record(module, id="a-1"),
            _outbox_record(
                module,
                id="b-1",
                task_id="task-2",
                source_event_id="event-2",
                dedupe_key="command-2:terminal",
            ),
        ],
    )
    store = _FakeEventStore(
        errors_by_task={"task-1": EventSequenceGap(2, 3)},
    )
    publisher = module.WritingOutboxPublisher(repository, store, clock=lambda: NOW)

    assert await publisher.run_once() == 1
    assert repository.blocked == [
        ("a-1", "lease-a-1", "OUTBOX_EVENT_SEQUENCE_GAP")
    ]
    assert [item[0] for item in repository.published] == ["b-1"]


async def test_waiting_sequence_gap_is_superseded_after_a_later_command_wins() -> None:
    from inkforge_core.writing import outbox as module
    from inkforge_core.writing.sse import EventSequenceGap

    repository = _FakeOutboxRepository(
        module,
        [
            _outbox_record(
                module,
                id="waiting-race",
                event_type="artifact_awaiting_user_approval",
            )
        ],
    )
    checks = 0

    async def supersede_after_publish_race(
        outbox_id: str,
        lease_token: str,
        *,
        now: datetime,
    ) -> bool:
        nonlocal checks
        del outbox_id, lease_token, now
        checks += 1
        return checks == 2

    repository.supersede_waiting_if_stale = supersede_after_publish_race  # type: ignore[method-assign]
    publisher = module.WritingOutboxPublisher(
        repository,
        _FakeEventStore(error=EventSequenceGap(4, 3)),
        clock=lambda: NOW,
    )

    assert await publisher.run_once() == 0
    assert checks == 2
    assert repository.blocked == []


async def test_publisher_blocks_invalid_sequence_and_continues_other_tasks() -> None:
    from inkforge_core.writing import outbox as module

    repository = _FakeOutboxRepository(
        module,
        [
            _outbox_record(
                module,
                id="a-invalid",
                source_sequence=0,
                durable_baseline=0,
            ),
            _outbox_record(
                module,
                id="b-valid",
                task_id="task-2",
                source_event_id="event-2",
                source_sequence=1,
                durable_baseline=0,
                dedupe_key="command-2:terminal",
            ),
        ],
    )
    publisher = module.WritingOutboxPublisher(
        repository,
        _FakeEventStore(),
        clock=lambda: NOW,
    )

    assert await publisher.run_once() == 1
    assert repository.blocked == [
        ("a-invalid", "lease-a-invalid", "OUTBOX_CONTRACT_INVALID")
    ]
    assert [item[0] for item in repository.published] == ["b-valid"]


async def test_publisher_supersedes_stale_waiting_and_continues_other_tasks() -> None:
    from inkforge_core.writing import outbox as module

    repository = _FakeOutboxRepository(
        module,
        [
            _outbox_record(
                module,
                id="waiting-1",
                event_type="artifact_awaiting_user_approval",
            ),
            _outbox_record(
                module,
                id="completed-2",
                task_id="task-2",
                source_event_id="event-2",
                source_sequence=1,
                dedupe_key="command-2:terminal",
            ),
        ],
    )
    repository.superseded.add("waiting-1")
    store = _FakeEventStore()
    publisher = module.WritingOutboxPublisher(repository, store, clock=lambda: NOW)

    assert await publisher.run_once() == 1
    assert [item["task_id"] for item in store.appended] == ["task-2"]
    assert [item[0] for item in repository.published] == ["completed-2"]


async def test_repository_supersedes_waiting_only_after_later_command(
    tmp_path: Path,
) -> None:
    from inkforge_core.db.models import (
        WritingEventOutbox,
        WritingRunCommand,
        WritingTask,
    )
    from inkforge_core.writing import outbox as module

    engine, session_factory = await _create_writing_outbox_database(
        tmp_path / "supersede.db"
    )
    try:
        async with session_factory() as session:
            async with session.begin():
                session.add(
                    WritingTask(
                        id="task-1",
                        novelId="novel-1",
                        chapterId="chapter-1",
                        phase="awaiting_user_review",
                        selectedAgents="writing",
                        targetWordCount=1000,
                        createdAt=NOW - timedelta(hours=1),
                        updatedAt=NOW,
                    )
                )
                session.add(
                    WritingRunCommand(
                        id="command-1",
                        taskId="task-1",
                        kind="start",
                        idempotencyKey="start-1",
                        payloadJson="{}",
                        status="succeeded",
                        attemptCount=1,
                        nextAttemptAt=NOW,
                        createdAt=NOW - timedelta(minutes=10),
                        updatedAt=NOW - timedelta(minutes=1),
                    )
                )
                session.add(
                    WritingEventOutbox(
                        id="waiting-1",
                        taskId="task-1",
                        commandId="command-1",
                        sourceEventId="event-waiting-1",
                        sourceSequence=3,
                        durableBaseline=2,
                        dedupeKey="command-1:waiting",
                        eventType="artifact_awaiting_user_approval",
                        payloadJson='{"taskId":"task-1"}',
                        deliveryState="pending",
                        attemptCount=0,
                        nextAttemptAt=NOW,
                        createdAt=NOW - timedelta(seconds=1),
                        updatedAt=NOW - timedelta(seconds=1),
                    )
                )
        repository = module.WritingOutboxRepository(session_factory)
        first_claim = await repository.claim_due(now=NOW, limit=1, lease_seconds=30)
        first_lease = first_claim[0].lease_token
        assert first_lease is not None
        assert await repository.supersede_waiting_if_stale(
            "waiting-1", first_lease, now=NOW
        ) is False
        assert await repository.schedule_retry(
            "waiting-1",
            first_lease,
            next_attempt_at=NOW,
            error_code="TEST_RETRY",
        ) is True

        async with session_factory() as session:
            async with session.begin():
                session.add(
                    WritingRunCommand(
                        id="command-2",
                        taskId="task-1",
                        kind="artifact_decision",
                        idempotencyKey="decision-1",
                        payloadJson="{}",
                        status="pending",
                        attemptCount=0,
                        nextAttemptAt=NOW,
                        createdAt=NOW,
                        updatedAt=NOW,
                    )
                )

        second_claim = await repository.claim_due(now=NOW, limit=1, lease_seconds=30)
        second_lease = second_claim[0].lease_token
        assert second_lease is not None
        assert await repository.supersede_waiting_if_stale(
            "waiting-1", second_lease, now=NOW
        ) is True
        async with session_factory() as session:
            row = await session.get(WritingEventOutbox, "waiting-1")
            assert row is not None
            assert row.deliveryState == "superseded"
            assert row.leaseToken is None
            assert row.lastErrorCode == "OUTBOX_WAITING_SUPERSEDED"
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ("delivery_state", "lease_token", "lease_expires_at"),
    [
        ("pending", None, None),
        ("delivering", "lease-existing", NOW + timedelta(seconds=30)),
        ("blocked", None, None),
    ],
)
async def test_new_command_transaction_supersedes_unpublished_waiting(
    tmp_path: Path,
    delivery_state: str,
    lease_token: str | None,
    lease_expires_at: datetime | None,
) -> None:
    from inkforge_core.db.models import (
        WritingEventOutbox,
        WritingRunCommand,
        WritingTask,
    )
    from inkforge_core.writing import outbox as module

    engine, session_factory = await _create_writing_outbox_database(
        tmp_path / "new-command-supersede.db"
    )
    try:
        async with session_factory() as session:
            async with session.begin():
                session.add(
                    WritingTask(
                        id="task-1",
                        novelId="novel-1",
                        chapterId="chapter-1",
                        phase="awaiting_user_review",
                        selectedAgents="writing",
                        targetWordCount=1000,
                        createdAt=NOW - timedelta(hours=1),
                        updatedAt=NOW,
                    )
                )
                session.add(
                    WritingRunCommand(
                        id="command-1",
                        taskId="task-1",
                        kind="start",
                        idempotencyKey="start-1",
                        payloadJson="{}",
                        status="succeeded",
                        attemptCount=1,
                        nextAttemptAt=NOW,
                        createdAt=NOW - timedelta(minutes=10),
                        updatedAt=NOW - timedelta(minutes=1),
                    )
                )
                session.add(
                    WritingEventOutbox(
                        id="waiting-1",
                        taskId="task-1",
                        commandId="command-1",
                        sourceEventId="event-waiting-1",
                        sourceSequence=3,
                        durableBaseline=2,
                        dedupeKey="command-1:waiting",
                        eventType="artifact_awaiting_user_approval",
                        payloadJson='{"taskId":"task-1"}',
                        deliveryState=delivery_state,
                        attemptCount=0,
                        nextAttemptAt=NOW,
                        leaseToken=lease_token,
                        leaseExpiresAt=lease_expires_at,
                        createdAt=NOW - timedelta(seconds=1),
                        updatedAt=NOW - timedelta(seconds=1),
                    )
                )
            async with session.begin():
                changed = await module.supersede_waiting_for_new_command(
                    session,
                    task_id="task-1",
                    now=NOW,
                )

        assert changed == 1
        async with session_factory() as session:
            row = await session.get(WritingEventOutbox, "waiting-1")
            assert row is not None
            assert row.deliveryState == "superseded"
            assert row.lastErrorCode == "OUTBOX_WAITING_SUPERSEDED"
            assert row.leaseToken is None
            assert row.leaseExpiresAt is None
    finally:
        await engine.dispose()


async def test_repository_cleanup_deletes_only_old_published_and_superseded(
    tmp_path: Path,
) -> None:
    from inkforge_core.db.models import WritingEventOutbox
    from inkforge_core.writing import outbox as module

    engine, session_factory = await _create_outbox_database(tmp_path / "cleanup.db")
    cutoff = NOW - timedelta(days=7)
    rows: list[Any] = []
    for index, state in enumerate(
        ("pending", "delivering", "blocked", "published", "superseded")
    ):
        row = WritingEventOutbox(
            id=f"old-{state}",
            taskId=f"task-{index}",
            commandId=None,
            sourceEventId=f"event-{index}",
            sourceSequence=1,
            durableBaseline=0,
            dedupeKey=f"dedupe-{index}",
            eventType="completed",
            payloadJson="{}",
            deliveryState=state,
            attemptCount=1,
            nextAttemptAt=cutoff - timedelta(days=1),
            createdAt=cutoff - timedelta(days=1),
            updatedAt=cutoff - timedelta(days=1),
        )
        if state == "delivering":
            row.leaseToken = "lease-old"
            row.leaseExpiresAt = cutoff - timedelta(days=1)
        if state == "published":
            row.redisEventId = "redis-old"
            row.publishedAt = cutoff - timedelta(seconds=1)
        rows.append(row)
    rows.append(
        WritingEventOutbox(
            id="recent-published",
            taskId="task-recent",
            commandId=None,
            sourceEventId="event-recent",
            sourceSequence=1,
            durableBaseline=0,
            dedupeKey="dedupe-recent",
            eventType="completed",
            payloadJson="{}",
            deliveryState="published",
            attemptCount=1,
            nextAttemptAt=NOW,
            redisEventId="redis-recent",
            createdAt=cutoff - timedelta(days=1),
            updatedAt=NOW,
            publishedAt=cutoff,
        )
    )
    try:
        async with session_factory() as session:
            async with session.begin():
                session.add_all(rows)
        repository = module.WritingOutboxRepository(session_factory)

        assert await repository.cleanup_terminal(older_than=cutoff) == 2

        async with session_factory() as session:
            remaining = set(
                await session.scalars(
                    text('SELECT "id" FROM "WritingEventOutbox"')
                )
            )
        assert remaining == {
            "old-pending",
            "old-delivering",
            "old-blocked",
            "recent-published",
        }
    finally:
        await engine.dispose()


async def test_outbox_readiness_fails_for_blocked_or_stale_unpublished_rows(
    tmp_path: Path,
) -> None:
    from inkforge_core.db.models import WritingEventOutbox
    from inkforge_core.writing import outbox as module

    engine, session_factory = await _create_outbox_database(tmp_path / "health.db")
    try:
        repository = module.WritingOutboxRepository(session_factory)
        readiness = module.WritingOutboxReadiness(
            repository,
            stale_after=timedelta(minutes=5),
            clock=lambda: NOW,
        )
        assert await readiness.check() is True

        async with session_factory() as session:
            async with session.begin():
                session.add_all(
                    [
                        WritingEventOutbox(
                            id="blocked",
                            taskId="task-blocked",
                            commandId=None,
                            sourceEventId="event-blocked",
                            sourceSequence=1,
                            durableBaseline=0,
                            dedupeKey="blocked",
                            eventType="error",
                            payloadJson="{}",
                            deliveryState="blocked",
                            attemptCount=1,
                            nextAttemptAt=NOW,
                            createdAt=NOW,
                            updatedAt=NOW,
                        ),
                        WritingEventOutbox(
                            id="stale",
                            taskId="task-stale",
                            commandId=None,
                            sourceEventId="event-stale",
                            sourceSequence=1,
                            durableBaseline=0,
                            dedupeKey="stale",
                            eventType="completed",
                            payloadJson="{}",
                            deliveryState="pending",
                            attemptCount=0,
                            nextAttemptAt=NOW,
                            createdAt=NOW - timedelta(minutes=6),
                            updatedAt=NOW - timedelta(minutes=6),
                        ),
                    ]
                )

        assert await readiness.check() is False
        assert readiness.error_codes() == {
            "writing_outbox": "OUTBOX_BLOCKED_AND_STALE_BACKLOG"
        }
    finally:
        await engine.dispose()


async def test_publisher_run_stops_promptly_and_cleans_only_seven_day_terminal_rows() -> None:
    from inkforge_core.writing import outbox as module

    repository = _FakeOutboxRepository(module, [])
    publisher = module.WritingOutboxPublisher(
        repository,
        _FakeEventStore(),
        clock=lambda: NOW,
        interval_seconds=0.001,
        cleanup_interval_seconds=0.001,
    )

    task = asyncio.create_task(publisher.run())
    await asyncio.sleep(0.01)
    publisher.request_stop()
    await asyncio.wait_for(task, timeout=1)

    assert repository.cleaned_before
    assert set(repository.cleaned_before) == {NOW - timedelta(days=7)}
