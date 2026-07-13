import asyncio
from datetime import UTC, datetime

import pytest
from inkforge_contracts.events import RunCompletionCallback, RunFailureCallback
from inkforge_core.writing.sse import (
    EventSequenceGap,
    InMemoryWritingEventStore,
    RedisWritingEventStore,
    format_heartbeat,
    format_sse_event,
    stream_task_events,
)
from inkforge_core.writing.tasks import WritingCallbackService


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

    async def fail(self, task_id: str, code: str) -> None:
        assert task_id == "task-1"
        self.code = code

    async def save_checkpoint(self, task_id: str, serialized: str, phase: str) -> None:
        raise AssertionError((task_id, serialized, phase))

    async def complete(self, task_id: str, result: dict[str, object]) -> None:
        raise AssertionError((task_id, result))


@pytest.mark.asyncio
async def test_failure_callback_does_not_expose_provider_message_in_browser_event() -> None:
    repository = FailureRepository()
    store = InMemoryWritingEventStore()
    service = WritingCallbackService(repository, store)

    await service.fail(
        RunFailureCallback(
            protocolVersion="1.0",
            eventId="event-1",
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

    async def complete(self, task_id: str, result: dict[str, object]) -> None:
        self.completed = (task_id, result)

    async def save_checkpoint(self, task_id: str, serialized: str, phase: str) -> None:
        raise AssertionError((task_id, serialized, phase))

    async def fail(self, task_id: str, code: str) -> None:
        raise AssertionError((task_id, code))


@pytest.mark.asyncio
async def test_completion_callback_persists_and_streams_visible_agent_response() -> None:
    repository = CompletionRepository()
    store = InMemoryWritingEventStore()
    service = WritingCallbackService(repository, store)

    await service.complete(
        RunCompletionCallback(
            protocolVersion="1.0",
            eventId="event-1",
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
