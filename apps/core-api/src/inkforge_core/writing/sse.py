from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import JsonValue

STREAM_TTL_SECONDS = 86_400


class EventSequenceGap(Exception):
    def __init__(self, expected_sequence: int, received_sequence: int) -> None:
        super().__init__("智能体事件序号不连续，需要从稳定状态对账")
        self.expected_sequence = expected_sequence
        self.received_sequence = received_sequence
        self.recoverable = True


@dataclass(frozen=True, slots=True)
class WritingEvent:
    id: str
    event: str
    data: dict[str, JsonValue]
    occurred_at: datetime
    source_event_id: str | None = None
    sequence: int | None = None


class InMemoryWritingEventStore:
    def __init__(self) -> None:
        self._events: dict[str, list[WritingEvent]] = {}
        self._source_ids: dict[tuple[str, str], WritingEvent] = {}
        self._last_sequences: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def make_event(
        self,
        event_id: str,
        event: str,
        data: dict[str, JsonValue],
        *,
        occurred_at: datetime | None = None,
        source_event_id: str | None = None,
        sequence: int | None = None,
    ) -> WritingEvent:
        return WritingEvent(
            id=event_id,
            event=event,
            data=data,
            occurred_at=occurred_at or datetime.now(UTC),
            source_event_id=source_event_id,
            sequence=sequence,
        )

    async def append(self, task_id: str, event: str, data: dict[str, JsonValue]) -> WritingEvent:
        async with self._lock:
            event_id = str(len(self._events.get(task_id, [])) + 1)
            item = self.make_event(event_id, event, data)
            self._events.setdefault(task_id, []).append(item)
            return item

    async def append_agent_event(
        self,
        task_id: str,
        *,
        source_event_id: str,
        sequence: int,
        event: str,
        data: dict[str, JsonValue],
    ) -> WritingEvent:
        async with self._lock:
            duplicate = self._source_ids.get((task_id, source_event_id))
            if duplicate is not None:
                return duplicate
            expected = self._last_sequences.get(task_id, 0) + 1
            if sequence != expected:
                raise EventSequenceGap(expected, sequence)
            event_id = str(len(self._events.get(task_id, [])) + 1)
            item = self.make_event(
                event_id,
                event,
                data,
                source_event_id=source_event_id,
                sequence=sequence,
            )
            self._events.setdefault(task_id, []).append(item)
            self._source_ids[(task_id, source_event_id)] = item
            self._last_sequences[task_id] = sequence
            return item

    async def replay(self, task_id: str, last_event_id: str | None) -> list[WritingEvent]:
        events = list(self._events.get(task_id, []))
        if last_event_id is None:
            return events
        return [item for item in events if int(item.id) > int(last_event_id)]


_APPEND_AGENT_EVENT_SCRIPT = """
local existing = redis.call('GET', KEYS[2])
if existing then
  return {'duplicate', existing}
end
local last = tonumber(redis.call('GET', KEYS[3]) or '0')
local received = tonumber(ARGV[1])
if received ~= last + 1 then
  return {'gap', tostring(last + 1)}
end
local id = redis.call(
  'XADD', KEYS[1], '*',
  'event', ARGV[2],
  'data', ARGV[3],
  'occurred_at', ARGV[4],
  'source_event_id', ARGV[5],
  'sequence', ARGV[1]
)
redis.call('SET', KEYS[2], id, 'EX', ARGV[6])
redis.call('SET', KEYS[3], ARGV[1], 'EX', ARGV[6])
redis.call('EXPIRE', KEYS[1], ARGV[6])
return {'appended', id}
"""


class RedisWritingEventStore:
    def __init__(self, redis: Any, *, ttl_seconds: int = STREAM_TTL_SECONDS) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def append(self, task_id: str, event: str, data: dict[str, JsonValue]) -> WritingEvent:
        occurred_at = datetime.now(UTC)
        stream = _stream_key(task_id)
        raw_id = await self._redis.xadd(
            stream,
            {
                "event": event,
                "data": _encode_data(data),
                "occurred_at": occurred_at.isoformat(),
                "source_event_id": "",
                "sequence": "",
            },
        )
        await self._redis.expire(stream, self._ttl_seconds)
        return WritingEvent(_text(raw_id), event, data, occurred_at)

    async def append_agent_event(
        self,
        task_id: str,
        *,
        source_event_id: str,
        sequence: int,
        event: str,
        data: dict[str, JsonValue],
    ) -> WritingEvent:
        occurred_at = datetime.now(UTC)
        result = await self._redis.eval(
            _APPEND_AGENT_EVENT_SCRIPT,
            3,
            _stream_key(task_id),
            f"writing:event-source:{task_id}:{source_event_id}",
            f"writing:event-sequence:{task_id}",
            str(sequence),
            event,
            _encode_data(data),
            occurred_at.isoformat(),
            source_event_id,
            str(self._ttl_seconds),
        )
        state, value = (_text(result[0]), _text(result[1]))
        if state == "gap":
            raise EventSequenceGap(int(value), sequence)
        if state == "duplicate":
            existing = await self._read_event(task_id, value)
            if existing is None:
                raise RuntimeError("重复事件对应的短期流已失效，需要状态对账")
            return existing
        return WritingEvent(
            value,
            event,
            data,
            occurred_at,
            source_event_id=source_event_id,
            sequence=sequence,
        )

    async def replay(self, task_id: str, last_event_id: str | None) -> list[WritingEvent]:
        minimum = "-" if last_event_id is None else last_event_id
        records = await self._redis.xrange(_stream_key(task_id), min=minimum, max="+")
        if last_event_id is not None:
            records = [item for item in records if _text(item[0]) != last_event_id]
        return [_decode_record(item_id, fields) for item_id, fields in records]

    async def _read_event(self, task_id: str, event_id: str) -> WritingEvent | None:
        records = await self._redis.xrange(
            _stream_key(task_id), min=event_id, max=event_id, count=1
        )
        if not records:
            return None
        item_id, fields = records[0]
        return _decode_record(item_id, fields)


def format_sse_event(event: WritingEvent) -> str:
    payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event.id}\nevent: {event.event}\ndata: {payload}\n\n"


def format_heartbeat() -> str:
    return ": 心跳\n\n"


async def stream_task_events(
    store: Any,
    task_id: str,
    *,
    last_event_id: str | None,
    poll_interval_seconds: float = 1.0,
    heartbeat_interval_seconds: float = 15.0,
) -> AsyncIterator[str]:
    cursor = last_event_id
    elapsed_without_event = 0.0
    while True:
        events = await store.replay(task_id, cursor)
        if events:
            elapsed_without_event = 0.0
            for event in events:
                yield format_sse_event(event)
                cursor = event.id
                if event.event in {
                    "done",
                    "completed",
                    "error",
                    "artifact_awaiting_user_approval",
                }:
                    return
            continue
        await asyncio.sleep(poll_interval_seconds)
        elapsed_without_event += poll_interval_seconds
        if elapsed_without_event >= heartbeat_interval_seconds:
            yield format_heartbeat()
            elapsed_without_event = 0.0


def _stream_key(task_id: str) -> str:
    return f"writing:events:{task_id}"


def _encode_data(data: dict[str, JsonValue]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _decode_record(item_id: object, fields: dict[object, object]) -> WritingEvent:
    normalized = {_text(key): _text(value) for key, value in fields.items()}
    occurred_at = datetime.fromisoformat(normalized["occurred_at"])
    return WritingEvent(
        id=_text(item_id),
        event=normalized["event"],
        data=json.loads(normalized["data"]),
        occurred_at=occurred_at,
        source_event_id=normalized.get("source_event_id") or None,
        sequence=(int(normalized["sequence"]) if normalized.get("sequence") else None),
    )


def _text(value: object) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)
