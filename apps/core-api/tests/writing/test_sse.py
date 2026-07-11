from datetime import UTC, datetime

import pytest
from inkforge_contracts.events import RunFailureCallback
from inkforge_core.writing.sse import (
    EventSequenceGap,
    InMemoryWritingEventStore,
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
