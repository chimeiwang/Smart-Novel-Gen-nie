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
from inkforge_core.writing.sse import (
    EventSequenceGap,
    InMemoryWritingEventStore,
    RedisWritingEventStore,
    format_heartbeat,
    format_sse_event,
    stream_task_events,
)
from inkforge_core.writing.tasks import CallbackAcceptance, WritingCallbackService


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
async def test_stream_replays_after_last_id_and_closes_on_terminal_event() -> None:
    store = InMemoryWritingEventStore()
    await store.append("task-1", "agent_chunk", {"chunk": "旧内容"})
    await store.append("task-1", "completed", {"taskId": "task-1"})

    chunks = [
        chunk
        async for chunk in stream_task_events(
            store,
            "task-1",
            last_event_id="1",
            poll_interval_seconds=0,
        )
    ]

    assert len(chunks) == 1
    assert "id: 2" in chunks[0]
    assert "event: completed" in chunks[0]


@pytest.mark.asyncio
async def test_stream_closes_when_artifact_awaits_user_approval() -> None:
    store = InMemoryWritingEventStore()
    await store.append("task-1", "agent_start", {"phase": "active"})
    await store.append(
        "task-1",
        "artifact_awaiting_user_approval",
        {"agentId": "剧情", "artifactId": "artifact-1"},
    )

    stream = stream_task_events(
        store,
        "task-1",
        last_event_id=None,
        poll_interval_seconds=0.01,
    )
    first = await anext(stream)
    second = await anext(stream)

    assert "event: agent_start" in first
    assert "event: artifact_awaiting_user_approval" in second
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), timeout=0.05)


class FailureRepository:
    def __init__(self) -> None:
        self.code: str | None = None

    async def authorize_callback(
        self, task_id: str, job_id: str
    ) -> CallbackAcceptance:
        assert task_id == "task-1"
        assert job_id == "job-1"
        return CallbackAcceptance(True, 0)

    async def fail_with_command(
        self, task_id: str, job_id: str, code: str, sequence: int
    ) -> CallbackAcceptance:
        assert task_id == "task-1"
        assert job_id == "job-1"
        assert sequence == 1
        self.code = code
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

    events = await store.replay("task-1", None)
    assert repository.code == "PROVIDER_FAILED"
    assert events[0].data["message"] == "智能体运行失败"
    assert "内部地址" not in str(events[0].data)


class CompletionRepository:
    def __init__(self) -> None:
        self.completed: tuple[str, dict[str, object]] | None = None
        self.messages: list[tuple[str, str, str, str, str | None]] = []

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
    ) -> CallbackAcceptance:
        assert job_id == "job-1"
        assert sequence == 1
        self.completed = (task_id, result)
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
async def test_completion_callback_persists_and_streams_visible_agent_response() -> None:
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

    events = await store.replay("task-1", None)
    assert events[0].data["finalContent"] == "这是本轮可见回复。"
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
        ) -> CallbackAcceptance:
            del task_id, job_id, result, visible_response, sequence
            order.extend(["message", "task", "command"])
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

    assert order == ["message", "task", "command", "event"]


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
    ) -> CallbackAcceptance:
        del task_id, job_id, result, visible_response, sequence
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
async def test_database_success_and_first_redis_failure_retries_idempotently() -> None:
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

    with pytest.raises(RuntimeError, match="Redis 发布失败"):
        await service.complete(callback)
    await service.complete(callback)

    assert order == [
        "authorize",
        "validate",
        "database",
        "publish",
        "authorize",
        "validate",
        "database",
        "publish",
    ]
    assert repository.completions == 2
    assert len(await store.replay("task-1", None)) == 1


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
