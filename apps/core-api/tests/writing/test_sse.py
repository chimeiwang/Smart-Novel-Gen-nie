import asyncio
import logging
from datetime import UTC, datetime

import fakeredis.aioredis
import pytest
from inkforge_contracts.events import (
    AgentEvent,
    CheckpointCallback,
    RunCompletionCallback,
    RunFailureCallback,
)
from inkforge_core.errors import ApiError
from inkforge_core.writing.outbox import BoundaryEvent
from inkforge_core.writing.schemas import WritingRunOutcome, WritingRunOutcomeResult
from inkforge_core.writing.sse import (
    EventSequenceGap,
    EventSourceConflict,
    InMemoryWritingEventStore,
    RedisWritingEventStore,
    WritingEvent,
    format_heartbeat,
    format_sse_event,
    stream_task_events,
)
from inkforge_core.writing.tasks import CallbackAcceptance, WritingCallbackService


def _run_outcome(
    state: str,
    *,
    code: str = "TEST_OUTCOME",
) -> WritingRunOutcome:
    return WritingRunOutcome(
        state=state,
        code=code,
        taskTerminal=state in {"succeeded", "failed", "cancelled"},
        streamShouldClose=state
        in {"waiting_user", "succeeded", "failed", "cancelled", "inconsistent"},
        reconciliationRequired=state == "inconsistent",
        currentCommand=None,
        result=WritingRunOutcomeResult(kind="none", ready=False),
        observedAt=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_event_ids_are_monotonic_and_replay_starts_after_last_id() -> None:
    store = InMemoryWritingEventStore()
    first = await store.append("task-1", "start", {"taskId": "task-1"})
    second = await store.append("task-1", "agent_chunk", {"chunk": "完整正文"})

    assert first.id == "1"
    assert second.id == "2"
    assert await store.replay("task-1", "1") == [second]


@pytest.mark.asyncio
async def test_redis_replay_uses_compatible_inclusive_range_and_excludes_cursor() -> None:
    class Redis:
        async def xrange(
            self,
            name: str,
            *,
            min: str,
            max: str,
            count: int | None = None,
        ) -> list[tuple[str, dict[str, str]]]:
            del count
            assert name == "writing:events:task-1"
            assert min == "3201885-0"
            assert max == "+"
            fields = {
                "event": "agent_start",
                "data": '{"phase":"active"}',
                "occurred_at": "2026-07-11T09:46:36+00:00",
                "source_event_id": "event-1",
                "sequence": "1",
            }
            return [("3201885-0", fields), ("3201886-0", fields)]

    store = RedisWritingEventStore(Redis())  # type: ignore[arg-type]

    events = await store.replay("task-1", "3201885-0")

    assert [event.id for event in events] == ["3201886-0"]


@pytest.mark.asyncio
async def test_duplicate_callback_is_ignored_and_sequence_gap_is_explicit() -> None:
    store = InMemoryWritingEventStore()
    first = await store.append_agent_event(
        "task-1",
        source_event_id="event-1",
        sequence=1,
        event="agent_start",
        data={"agentId": "写作"},
    )
    duplicate = await store.append_agent_event(
        "task-1",
        source_event_id="event-1",
        sequence=1,
        event="agent_start",
        data={"agentId": "写作"},
    )

    assert duplicate == first
    assert len(await store.replay("task-1", None)) == 1
    with pytest.raises(EventSequenceGap) as error:
        await store.append_agent_event(
            "task-1",
            source_event_id="event-3",
            sequence=3,
            event="agent_chunk",
            data={"chunk": "不能越过第二条"},
        )
    assert error.value.expected_sequence == 2
    assert error.value.received_sequence == 3
    assert error.value.recoverable is True


def test_sse_format_keeps_typed_payload_and_heartbeat() -> None:
    store = InMemoryWritingEventStore()
    event = store.make_event("7", "agent_chunk", {"chunk": "完整正文"})

    rendered = format_sse_event(event)

    assert "id: 7\n" in rendered
    assert "event: agent_chunk\n" in rendered
    assert 'data: {"chunk":"完整正文"}\n\n' in rendered
    assert format_heartbeat() == ": 心跳\n\n"


@pytest.mark.asyncio
async def test_legacy_terminal_event_does_not_close_a_running_outcome() -> None:
    store = InMemoryWritingEventStore()
    await store.append("task-1", "agent_chunk", {"chunk": "旧内容"})
    await store.append("task-1", "completed", {"taskId": "task-1"})
    outcomes = iter([_run_outcome("running"), _run_outcome("succeeded")])

    async def outcome_provider() -> WritingRunOutcome:
        return next(outcomes)

    chunks = [
        chunk
        async for chunk in stream_task_events(
            store,
            "task-1",
            last_event_id="1",
            poll_interval_seconds=0,
            outcome_provider=outcome_provider,
        )
    ]

    assert len(chunks) == 3
    assert "event: run_outcome" in chunks[0]
    assert '"state":"running"' in chunks[0]
    assert "id:" not in chunks[0]
    assert "id: 2" in chunks[1]
    assert "event: completed" in chunks[1]
    assert "event: run_outcome" in chunks[2]
    assert '"state":"succeeded"' in chunks[2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    ["waiting_user", "succeeded", "failed", "cancelled", "inconsistent"],
)
async def test_stream_closes_from_postgres_outcome_without_redis_event(
    state: str,
) -> None:
    store = InMemoryWritingEventStore()

    async def outcome_provider() -> WritingRunOutcome:
        return _run_outcome(state)

    stream = stream_task_events(
        store,
        "task-1",
        last_event_id=None,
        poll_interval_seconds=0.01,
        outcome_provider=outcome_provider,
    )
    first = await anext(stream)

    assert "event: run_outcome" in first
    assert f'"state":"{state}"' in first
    assert "id:" not in first
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), timeout=0.05)


@pytest.mark.asyncio
async def test_terminal_outcome_still_replays_available_legacy_boundary() -> None:
    store = InMemoryWritingEventStore()
    await store.append("task-1", "completed", {"taskId": "task-1"})

    async def outcome_provider() -> WritingRunOutcome:
        return _run_outcome("succeeded")

    chunks = [
        chunk
        async for chunk in stream_task_events(
            store,
            "task-1",
            last_event_id=None,
            outcome_provider=outcome_provider,
            poll_interval_seconds=0,
        )
    ]

    assert ["event: run_outcome" in chunk for chunk in chunks] == [
        True,
        False,
        True,
    ]
    assert chunks[0] == chunks[-1]
    assert "event: completed" in chunks[1]
    assert "id: 1" in chunks[1]


@pytest.mark.asyncio
async def test_terminal_stream_hides_superseded_outbox_boundary() -> None:
    store = InMemoryWritingEventStore()
    await store.append_agent_event(
        "task-1",
        source_event_id="waiting-superseded",
        sequence=1,
        event="artifact_awaiting_user_approval",
        data={"taskId": "task-1"},
    )

    async def outcome_provider() -> WritingRunOutcome:
        return _run_outcome("succeeded")

    async def visibility_provider(
        events: list[WritingEvent],
    ) -> dict[str, str]:
        return {event.id: "skip" for event in events}

    chunks = [
        chunk
        async for chunk in stream_task_events(
            store,
            "task-1",
            last_event_id=None,
            outcome_provider=outcome_provider,
            event_visibility_provider=visibility_provider,
        )
    ]

    assert len(chunks) == 1
    assert "event: run_outcome" in chunks[0]
    assert "artifact_awaiting_user_approval" not in chunks[0]


class FailureRepository:
    def __init__(self) -> None:
        self.code: str | None = None
        self.boundary: BoundaryEvent | None = None

    async def authorize_callback(
        self, task_id: str, job_id: str
    ) -> CallbackAcceptance:
        assert task_id == "task-1"
        assert job_id == "job-1"
        return CallbackAcceptance(True, 0)

    async def fail_with_command(
        self,
        task_id: str,
        job_id: str,
        code: str,
        sequence: int,
        boundary: BoundaryEvent,
    ) -> CallbackAcceptance:
        assert task_id == "task-1"
        assert job_id == "job-1"
        assert sequence == 1
        self.code = code
        self.boundary = boundary
        return CallbackAcceptance(True, 0)

    async def save_checkpoint(
        self,
        task_id: str,
        job_id: str,
        serialized: str,
        phase: str,
        sequence: int,
    ) -> CallbackAcceptance:
        raise AssertionError((task_id, job_id, serialized, phase, sequence))

    async def complete(self, task_id: str, result: dict[str, object]) -> None:
        raise AssertionError((task_id, result))


@pytest.mark.asyncio
async def test_failure_callback_does_not_expose_provider_message_in_browser_event() -> None:
    repository = FailureRepository()
    store = InMemoryWritingEventStore()
    service = WritingCallbackService(repository, store)

    await service.fail(
        RunFailureCallback(
            protocolVersion="1.1",
            eventId="event-1",
            jobId="job-1",
            runId="run-1",
            taskId="task-1",
            sequence=1,
            code="PROVIDER_FAILED",
            message="供应商返回了包含内部地址的原始错误",
            recoverable=False,
            occurredAt=datetime.now(UTC),
        )
    )

    assert repository.code == "PROVIDER_FAILED"
    assert repository.boundary is not None
    assert repository.boundary.payload["message"] == "智能体运行失败"
    assert "内部地址" not in str(repository.boundary.payload)
    assert await store.replay("task-1", None) == []


class CompletionRepository:
    def __init__(self) -> None:
        self.completed: tuple[str, dict[str, object]] | None = None
        self.messages: list[tuple[str, str, str, str, str | None]] = []
        self.boundary: BoundaryEvent | None = None

    async def authorize_callback(
        self, task_id: str, job_id: str
    ) -> CallbackAcceptance:
        assert task_id == "task-1"
        assert job_id == "job-1"
        return CallbackAcceptance(True, 0)

    async def persist_workflow_message(
        self,
        task_id: str,
        *,
        role: str,
        content: str,
        event_type: str,
        agent_id: str | None = None,
    ) -> None:
        self.messages.append((task_id, role, content, event_type, agent_id))

    async def complete_with_message_and_command(
        self,
        task_id: str,
        job_id: str,
        result: dict[str, object],
        visible_response: str,
        sequence: int,
        boundary: BoundaryEvent,
    ) -> CallbackAcceptance:
        assert job_id == "job-1"
        assert sequence == 1
        self.completed = (task_id, result)
        self.boundary = boundary
        if visible_response:
            self.messages.append((task_id, "agent", visible_response, "done", None))
        return CallbackAcceptance(True, 0)

    async def save_checkpoint(
        self,
        task_id: str,
        job_id: str,
        serialized: str,
        phase: str,
        sequence: int,
    ) -> CallbackAcceptance:
        raise AssertionError((task_id, job_id, serialized, phase, sequence))

    async def fail_with_command(
        self, task_id: str, job_id: str, code: str, sequence: int
    ) -> CallbackAcceptance:
        raise AssertionError((task_id, job_id, code, sequence))


@pytest.mark.asyncio
async def test_completion_callback_persists_visible_response_and_outbox_boundary() -> None:
    repository = CompletionRepository()
    store = InMemoryWritingEventStore()
    service = WritingCallbackService(repository, store)

    await service.complete(
        RunCompletionCallback(
            protocolVersion="1.1",
            eventId="event-1",
            jobId="job-1",
            runId="run-1",
            taskId="task-1",
            sequence=1,
            result={"finalResponse": "这是本轮可见回复。"},
            occurredAt=datetime.now(UTC),
        )
    )

    assert await store.replay("task-1", None) == []
    assert repository.boundary is not None
    assert repository.boundary.event_type == "completed"
    assert repository.boundary.payload["taskId"] == "task-1"
    assert len(str(repository.boundary.payload["resultSha256"])) == 64
    assert repository.messages == [
        ("task-1", "agent", "这是本轮可见回复。", "done", None)
    ]
    assert repository.completed == (
        "task-1",
        {"finalResponse": "这是本轮可见回复。"},
    )


@pytest.mark.asyncio
async def test_completed_event_is_appended_after_durable_state() -> None:
    order: list[str] = []

    class OrderedRepository(CompletionRepository):
        async def complete_with_message_and_command(
            self,
            task_id: str,
            job_id: str,
            result: dict[str, object],
            visible_response: str,
            sequence: int,
            boundary: BoundaryEvent,
        ) -> CallbackAcceptance:
            del task_id, job_id, result, visible_response, sequence, boundary
            order.extend(["message", "task", "command", "outbox"])
            return CallbackAcceptance(True, 0)

    class OrderedEventStore(InMemoryWritingEventStore):
        async def append_agent_event(self, *args, **kwargs):
            order.append("event")
            return await super().append_agent_event(*args, **kwargs)

    service = WritingCallbackService(OrderedRepository(), OrderedEventStore())
    await service.complete(
        RunCompletionCallback(
            protocolVersion="1.1",
            eventId="event-1",
            jobId="job-1",
            runId="run-1",
            taskId="task-1",
            sequence=1,
            result={"finalResponse": "完成"},
            occurredAt=datetime.now(UTC),
        )
    )

    assert order == ["message", "task", "command", "outbox"]


class CheckpointGapRepository:
    def __init__(self, order: list[str]) -> None:
        self.order = order
        self.saved = False

    async def authorize_callback(
        self, task_id: str, job_id: str
    ) -> CallbackAcceptance:
        assert task_id == "task-1"
        assert job_id == "job-1"
        self.order.append("authorize")
        return CallbackAcceptance(True, 20)

    async def save_checkpoint(self, *args: object) -> CallbackAcceptance:
        del args
        self.order.append("database")
        self.saved = True
        return CallbackAcceptance(True, 20)


class SequenceGapStore(InMemoryWritingEventStore):
    def __init__(self, order: list[str]) -> None:
        super().__init__()
        self.order = order

    async def validate_agent_event(self, *args: object, **kwargs: object) -> bool:
        del args, kwargs
        self.order.append("validate")
        raise EventSequenceGap(21, 22)

    async def append_agent_event(self, *args: object, **kwargs: object):
        del args, kwargs
        raise AssertionError("序号缺口时不能发布事件")


@pytest.mark.asyncio
async def test_checkpoint_sequence_gap_does_not_mutate_database() -> None:
    order: list[str] = []
    repository = CheckpointGapRepository(order)
    service = WritingCallbackService(
        repository,  # type: ignore[arg-type]
        SequenceGapStore(order),
    )

    with pytest.raises(ApiError) as captured:
        await service.save_checkpoint(
            CheckpointCallback(
                protocolVersion="1.1",
                eventId="event-22",
                jobId="job-1",
                runId="task-1",
                taskId="task-1",
                sequence=22,
                checkpoint={
                    "taskId": "task-1",
                    "userId": "user-1",
                    "novelId": "novel-1",
                    "chapterId": "chapter-1",
                    "targetWordCount": 4000,
                    "conversationHistory": [],
                    "phase": "active",
                    "eventSequence": 22,
                },
                occurredAt=datetime.now(UTC),
            ),
            user_id="user-1",
            novel_id="novel-1",
        )

    assert captured.value.code == "AGENT_EVENT_SEQUENCE_GAP"
    assert repository.saved is False
    assert order == ["authorize", "validate"]


@pytest.mark.asyncio
async def test_redis_store_rebases_missing_sequence_from_durable_checkpoint() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    store = RedisWritingEventStore(redis)

    should_publish = await store.validate_agent_event(
        "task-1",
        source_event_id="event-21",
        sequence=21,
        durable_baseline=20,
        allow_rebase=True,
    )
    event = await store.append_agent_event(
        "task-1",
        source_event_id="event-21",
        sequence=21,
        event="agent_start",
        data={"agentId": "写作"},
        durable_baseline=20,
        allow_rebase=True,
    )

    assert should_publish is True
    assert event.sequence == 21
    assert await redis.get("writing:event-sequence:task-1") == b"21"


async def _seed_agent_events(
    store: InMemoryWritingEventStore | RedisWritingEventStore,
) -> None:
    for sequence in range(1, 6):
        await store.append_agent_event(
            "task-1",
            source_event_id=f"event-{sequence}",
            sequence=sequence,
            event="agent_chunk",
            data={"chunk": str(sequence)},
        )


def _make_event_store(
    backend: str,
) -> InMemoryWritingEventStore | RedisWritingEventStore:
    if backend == "memory":
        return InMemoryWritingEventStore()
    return RedisWritingEventStore(fakeredis.aioredis.FakeRedis())


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["memory", "redis"])
async def test_real_database_baseline_does_not_hide_a_redis_sequence_gap(
    backend: str,
) -> None:
    accepted_store = _make_event_store(backend)
    rejected_store = _make_event_store(backend)
    for store in (accepted_store, rejected_store):
        for sequence in range(1, 22):
            await store.append_agent_event(
                "task-1",
                source_event_id=f"event-{sequence}",
                sequence=sequence,
                event="agent_chunk",
                data={"chunk": str(sequence)},
            )

    accepted = await accepted_store.append_agent_event(
        "task-1",
        source_event_id="terminal-22",
        sequence=22,
        event="error",
        data={"taskId": "task-1"},
        durable_baseline=20,
        allow_rebase=True,
    )
    with pytest.raises(EventSequenceGap) as captured:
        await rejected_store.append_agent_event(
            "task-1",
            source_event_id="terminal-23",
            sequence=23,
            event="error",
            data={"taskId": "task-1"},
            durable_baseline=20,
            allow_rebase=True,
        )

    assert accepted.sequence == 22
    assert captured.value.expected_sequence == 22
    assert captured.value.received_sequence == 23


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["memory", "redis"])
async def test_store_rebases_lagging_sequence_from_durable_checkpoint(
    backend: str,
) -> None:
    store = _make_event_store(backend)
    await _seed_agent_events(store)

    event = await store.append_agent_event(
        "task-1",
        source_event_id="event-21",
        sequence=21,
        event="completed",
        data={"taskId": "task-1"},
        durable_baseline=20,
        allow_rebase=True,
    )

    assert event.sequence == 21


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["memory", "redis"])
async def test_store_rejects_gap_when_durable_checkpoint_cannot_cover_it(
    backend: str,
) -> None:
    store = _make_event_store(backend)
    await _seed_agent_events(store)

    with pytest.raises(EventSequenceGap) as captured:
        await store.append_agent_event(
            "task-1",
            source_event_id="event-21",
            sequence=21,
            event="completed",
            data={"taskId": "task-1"},
            durable_baseline=4,
            allow_rebase=True,
        )

    assert captured.value.expected_sequence == 6
    assert captured.value.received_sequence == 21


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["memory", "redis"])
async def test_rebased_source_event_id_is_idempotent(backend: str) -> None:
    store = _make_event_store(backend)
    await _seed_agent_events(store)
    first = await store.append_agent_event(
        "task-1",
        source_event_id="event-21",
        sequence=21,
        event="completed",
        data={"taskId": "task-1"},
        durable_baseline=20,
        allow_rebase=True,
    )

    duplicate = await store.append_agent_event(
        "task-1",
        source_event_id="event-21",
        sequence=21,
        event="completed",
        data={"taskId": "task-1"},
        durable_baseline=20,
        allow_rebase=True,
    )

    assert duplicate == first
    assert len(await store.replay("task-1", None)) == 6

    with pytest.raises(EventSourceConflict):
        await store.append_agent_event(
            "task-1",
            source_event_id="event-21",
            sequence=21,
            event="error",
            data={"code": "CHANGED"},
            durable_baseline=20,
            allow_rebase=True,
        )


class DuplicateEventRepository:
    async def authorize_callback(
        self, task_id: str, job_id: str
    ) -> CallbackAcceptance:
        del task_id, job_id
        return CallbackAcceptance(True, 0)

    async def mark_command_processing(
        self, task_id: str, job_id: str, sequence: int
    ) -> CallbackAcceptance:
        del task_id, job_id, sequence
        raise AssertionError("重复或冲突事件不能再次推进命令")


@pytest.mark.asyncio
async def test_process_event_duplicate_and_conflict_return_distinct_receipts() -> None:
    store = InMemoryWritingEventStore()
    await store.append_agent_event(
        "task-1",
        source_event_id="event-1",
        sequence=1,
        event="agent_start",
        data={"agentId": "写作"},
    )
    service = WritingCallbackService(
        DuplicateEventRepository(),  # type: ignore[arg-type]
        store,
    )
    base = {
        "protocolVersion": "1.1",
        "eventId": "event-1",
        "jobId": "job-1",
        "runId": "task-1",
        "taskId": "task-1",
        "sequence": 1,
        "event": "agent_start",
        "occurredAt": datetime.now(UTC),
    }

    duplicate = await service.accept_event(
        AgentEvent.model_validate({**base, "data": {"agentId": "写作"}})
    )
    conflict = await service.accept_event(
        AgentEvent.model_validate({**base, "data": {"agentId": "编辑"}})
    )

    assert duplicate.disposition == "already_applied"
    assert conflict.disposition == "rejected"
    assert conflict.reasonCode == "WRITING_EVENT_SOURCE_CONFLICT"


@pytest.mark.asyncio
async def test_redis_store_does_not_rebase_old_sequence_at_or_below_checkpoint() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    store = RedisWritingEventStore(redis)

    should_publish = await store.validate_agent_event(
        "task-1",
        source_event_id="event-20",
        sequence=20,
        durable_baseline=20,
        allow_rebase=True,
    )

    assert should_publish is False
    assert await redis.get("writing:event-sequence:task-1") is None
    assert await redis.xlen("writing:events:task-1") == 0


class RetryingRepository:
    def __init__(self, order: list[str], *, baseline: int = 20) -> None:
        self.order = order
        self.baseline = baseline
        self.completions = 0

    async def authorize_callback(
        self, task_id: str, job_id: str
    ) -> CallbackAcceptance:
        assert task_id == "task-1"
        assert job_id == "job-1"
        self.order.append("authorize")
        return CallbackAcceptance(True, self.baseline, self.completions > 0)

    async def complete_with_message_and_command(
        self,
        task_id: str,
        job_id: str,
        result: dict[str, object],
        visible_response: str,
        sequence: int,
        boundary: BoundaryEvent,
    ) -> CallbackAcceptance:
        del task_id, job_id, result, visible_response, sequence, boundary
        self.order.append("database")
        self.completions += 1
        return CallbackAcceptance(True, self.baseline, self.completions > 1)


class PublishOnceFailureStore(InMemoryWritingEventStore):
    def __init__(self, order: list[str]) -> None:
        super().__init__()
        self.order = order
        self.publish_attempts = 0

    async def validate_agent_event(self, *args: object, **kwargs: object) -> bool:
        del args, kwargs
        self.order.append("validate")
        return True

    async def append_agent_event(self, *args: object, **kwargs: object):
        self.order.append("publish")
        self.publish_attempts += 1
        if self.publish_attempts == 1:
            raise RuntimeError("模拟 Redis 发布失败")
        return await super().append_agent_event(*args, **kwargs)


@pytest.mark.asyncio
async def test_terminal_database_commit_does_not_wait_for_redis() -> None:
    order: list[str] = []
    repository = RetryingRepository(order)
    store = PublishOnceFailureStore(order)
    service = WritingCallbackService(repository, store)  # type: ignore[arg-type]
    callback = RunCompletionCallback(
        protocolVersion="1.1",
        eventId="event-21",
        jobId="job-1",
        runId="task-1",
        taskId="task-1",
        sequence=21,
        result={"finalResponse": "完成"},
        occurredAt=datetime.now(UTC),
    )

    await service.complete(callback)

    assert order == ["database"]
    assert repository.completions == 1
    assert store.publish_attempts == 0
    assert await store.replay("task-1", None) == []


class OldSequenceRepository(RetryingRepository):
    async def mark_command_processing(
        self, task_id: str, job_id: str, sequence: int
    ) -> CallbackAcceptance:
        del task_id, job_id, sequence
        raise AssertionError("旧序号不能推进命令状态")


@pytest.mark.asyncio
async def test_event_at_persisted_sequence_is_noop_before_database_mutation() -> None:
    order: list[str] = []
    repository = OldSequenceRepository(order, baseline=20)
    service = WritingCallbackService(
        repository,  # type: ignore[arg-type]
        InMemoryWritingEventStore(),
    )

    await service.accept_event(
        AgentEvent(
            protocolVersion="1.1",
            eventId="event-20",
            jobId="job-1",
            runId="task-1",
            taskId="task-1",
            sequence=20,
            event="agent_start",
            data={},
            occurredAt=datetime.now(UTC),
        )
    )

    assert order == ["authorize"]


@pytest.mark.asyncio
async def test_sequence_noop_uses_non_identity_error_code(caplog: pytest.LogCaptureFixture) -> None:
    order: list[str] = []
    repository = OldSequenceRepository(order, baseline=20)
    service = WritingCallbackService(
        repository,  # type: ignore[arg-type]
        InMemoryWritingEventStore(),
    )
    caplog.set_level(logging.WARNING)

    await service.accept_event(
        AgentEvent(
            protocolVersion="1.1",
            eventId="event-20",
            jobId="job-1",
            runId="task-1",
            taskId="task-1",
            sequence=20,
            event="agent_start",
            data={},
            occurredAt=datetime.now(UTC),
        )
    )

    assert "WRITING_CALLBACK_SEQUENCE_STALE" in caplog.text
    assert "WRITING_JOB_MISMATCH" not in caplog.text


class AlreadyAppliedRepository(OldSequenceRepository):
    async def authorize_callback(
        self, task_id: str, job_id: str
    ) -> CallbackAcceptance:
        acceptance = await super().authorize_callback(task_id, job_id)
        return CallbackAcceptance(
            acceptance.accepted,
            acceptance.persisted_sequence,
            already_applied=True,
        )


@pytest.mark.asyncio
async def test_state_noop_uses_non_identity_error_code(caplog: pytest.LogCaptureFixture) -> None:
    order: list[str] = []
    service = WritingCallbackService(
        AlreadyAppliedRepository(order, baseline=20),  # type: ignore[arg-type]
        InMemoryWritingEventStore(),
    )
    caplog.set_level(logging.WARNING)

    await service.accept_event(
        AgentEvent(
            protocolVersion="1.1",
            eventId="event-21",
            jobId="job-1",
            runId="task-1",
            taskId="task-1",
            sequence=21,
            event="agent_start",
            data={},
            occurredAt=datetime.now(UTC),
        )
    )

    assert "WRITING_CALLBACK_ALREADY_APPLIED" in caplog.text
    assert "WRITING_JOB_MISMATCH" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("already_applied", [False, True])
async def test_process_event_checks_source_content_before_state_or_sequence_noop(
    already_applied: bool,
) -> None:
    order: list[str] = []
    store = InMemoryWritingEventStore()
    await store.append_agent_event(
        "task-1",
        source_event_id="event-1",
        sequence=1,
        event="agent_start",
        data={"agentId": "写作"},
    )
    await store.append_agent_event(
        "task-1",
        source_event_id="event-2",
        sequence=2,
        event="agent_done",
        data={"agentId": "写作"},
    )
    repository = (
        AlreadyAppliedRepository(order, baseline=2)
        if already_applied
        else OldSequenceRepository(order, baseline=2)
    )
    service = WritingCallbackService(repository, store)  # type: ignore[arg-type]
    base = {
        "protocolVersion": "1.1",
        "eventId": "event-1",
        "jobId": "job-1",
        "runId": "task-1",
        "taskId": "task-1",
        "sequence": 1,
        "event": "agent_start",
        "occurredAt": datetime.now(UTC),
    }

    duplicate = await service.accept_event(
        AgentEvent.model_validate({**base, "data": {"agentId": "写作"}})
    )
    conflict = await service.accept_event(
        AgentEvent.model_validate({**base, "data": {"agentId": "编辑"}})
    )

    assert duplicate.disposition == "already_applied"
    assert conflict.disposition == "rejected"
    assert conflict.reasonCode == "WRITING_EVENT_SOURCE_CONFLICT"
