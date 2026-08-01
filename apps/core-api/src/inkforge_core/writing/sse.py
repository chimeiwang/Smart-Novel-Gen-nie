from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import JsonValue

from .schemas import WritingRunOutcome

STREAM_TTL_SECONDS = 86_400
ReplayDisposition = Literal["emit", "skip", "wait"]


class EventSequenceGap(Exception):
    def __init__(self, expected_sequence: int, received_sequence: int) -> None:
        super().__init__("智能体事件序号不连续，需要从稳定状态对账")
        self.expected_sequence = expected_sequence
        self.received_sequence = received_sequence
        self.recoverable = True


class EventSourceConflict(Exception):
    """同一来源事件标识对应了不同的规范化事件。"""


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
        durable_baseline: int = 0,
        allow_rebase: bool = False,
    ) -> WritingEvent:
        async with self._lock:
            duplicate = self._source_ids.get((task_id, source_event_id))
            if duplicate is not None:
                if not _same_agent_event(
                    duplicate,
                    sequence=sequence,
                    event=event,
                    data=data,
                ):
                    raise EventSourceConflict
                return duplicate
            last_sequence = self._last_sequences.get(task_id)
            expected = _expected_sequence(
                last_sequence,
                sequence=sequence,
                durable_baseline=durable_baseline,
                allow_rebase=allow_rebase,
            )
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

    async def validate_agent_event(
        self,
        task_id: str,
        *,
        source_event_id: str,
        sequence: int,
        durable_baseline: int,
        allow_rebase: bool,
        event: str | None = None,
        data: dict[str, JsonValue] | None = None,
    ) -> bool:
        async with self._lock:
            duplicate = self._source_ids.get((task_id, source_event_id))
            if duplicate is not None:
                if (
                    event is not None
                    and data is not None
                    and not _same_agent_event(
                        duplicate,
                        sequence=sequence,
                        event=event,
                        data=data,
                    )
                ):
                    raise EventSourceConflict
                return False
            last_sequence = self._last_sequences.get(task_id)
            if (
                last_sequence is None
                and allow_rebase
                and sequence <= durable_baseline
            ):
                return False
            expected = _expected_sequence(
                last_sequence,
                sequence=sequence,
                durable_baseline=durable_baseline,
                allow_rebase=allow_rebase,
            )
            if sequence != expected:
                raise EventSequenceGap(expected, sequence)
            return True

    async def validate_agent_event_source(
        self,
        task_id: str,
        *,
        source_event_id: str,
        sequence: int,
        event: str,
        data: dict[str, JsonValue],
    ) -> bool:
        """核验来源标识；未见过返回 True，完全重复返回 False。"""
        async with self._lock:
            duplicate = self._source_ids.get((task_id, source_event_id))
            if duplicate is None:
                return True
            if not _same_agent_event(
                duplicate,
                sequence=sequence,
                event=event,
                data=data,
            ):
                raise EventSourceConflict
            return False

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
local received = tonumber(ARGV[1])
local last_raw = redis.call('GET', KEYS[3])
local durable_baseline = tonumber(ARGV[7])
local allow_rebase = ARGV[8] == '1'
local expected = 1
if last_raw then
  local last = tonumber(last_raw)
  if allow_rebase and last <= durable_baseline and received > durable_baseline then
    expected = received
  else
    expected = last + 1
  end
elseif allow_rebase and received > durable_baseline then
  expected = received
end
if received ~= expected then
  return {'gap', tostring(expected)}
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
        durable_baseline: int = 0,
        allow_rebase: bool = False,
    ) -> WritingEvent:
        occurred_at = datetime.now(UTC)
        result = await self._redis.eval(
            _APPEND_AGENT_EVENT_SCRIPT,
            3,
            _stream_key(task_id),
            _source_key(task_id, source_event_id),
            _sequence_key(task_id),
            str(sequence),
            event,
            _encode_data(data),
            occurred_at.isoformat(),
            source_event_id,
            str(self._ttl_seconds),
            str(durable_baseline),
            "1" if allow_rebase else "0",
        )
        state, value = (_text(result[0]), _text(result[1]))
        if state == "gap":
            raise EventSequenceGap(int(value), sequence)
        if state == "duplicate":
            existing = await self._read_event(task_id, value)
            if existing is None:
                raise RuntimeError("重复事件对应的短期流已失效，需要状态对账")
            if not _same_agent_event(
                existing,
                sequence=sequence,
                event=event,
                data=data,
            ):
                raise EventSourceConflict
            return existing
        return WritingEvent(
            value,
            event,
            data,
            occurred_at,
            source_event_id=source_event_id,
            sequence=sequence,
        )

    async def validate_agent_event(
        self,
        task_id: str,
        *,
        source_event_id: str,
        sequence: int,
        durable_baseline: int,
        allow_rebase: bool,
        event: str | None = None,
        data: dict[str, JsonValue] | None = None,
    ) -> bool:
        source_event, raw_last_sequence = await self._redis.mget(
            _source_key(task_id, source_event_id),
            _sequence_key(task_id),
        )
        if source_event is not None:
            if event is not None and data is not None:
                existing = await self._read_event(task_id, _text(source_event))
                if existing is None:
                    raise RuntimeError("重复事件对应的短期流已失效，需要状态对账")
                if not _same_agent_event(
                    existing,
                    sequence=sequence,
                    event=event,
                    data=data,
                ):
                    raise EventSourceConflict
            return False
        last_sequence = (
            int(_text(raw_last_sequence)) if raw_last_sequence is not None else None
        )
        if (
            last_sequence is None
            and allow_rebase
            and sequence <= durable_baseline
        ):
            return False
        expected = _expected_sequence(
            last_sequence,
            sequence=sequence,
            durable_baseline=durable_baseline,
            allow_rebase=allow_rebase,
        )
        if sequence != expected:
            raise EventSequenceGap(expected, sequence)
        return True

    async def validate_agent_event_source(
        self,
        task_id: str,
        *,
        source_event_id: str,
        sequence: int,
        event: str,
        data: dict[str, JsonValue],
    ) -> bool:
        raw_event_id = await self._redis.get(
            _source_key(task_id, source_event_id)
        )
        if raw_event_id is None:
            return True
        existing = await self._read_event(task_id, _text(raw_event_id))
        if existing is None:
            raise RuntimeError("重复事件对应的短期流已失效，需要状态对账")
        if not _same_agent_event(
            existing,
            sequence=sequence,
            event=event,
            data=data,
        ):
            raise EventSourceConflict
        return False

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


def format_run_outcome(outcome: WritingRunOutcome) -> str:
    payload = json.dumps(
        outcome.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"event: run_outcome\ndata: {payload}\n\n"


async def stream_task_events(
    store: Any,
    task_id: str,
    *,
    last_event_id: str | None,
    outcome_provider: Callable[[], Awaitable[WritingRunOutcome]],
    event_visibility_provider: Callable[
        [list[WritingEvent]],
        Awaitable[dict[str, ReplayDisposition]],
    ]
    | None = None,
    poll_interval_seconds: float = 1.0,
    heartbeat_interval_seconds: float = 15.0,
) -> AsyncIterator[str]:
    cursor = last_event_id
    elapsed_without_event = 0.0
    outcome = await outcome_provider()
    outcome_fingerprint = _outcome_fingerprint(outcome)
    yield format_run_outcome(outcome)
    if outcome.streamShouldClose:
        terminal_events, cursor = await _replay_visible_events(
            store,
            task_id,
            cursor,
            event_visibility_provider,
        )
        for event in terminal_events:
            yield format_sse_event(event)
        if terminal_events:
            yield format_run_outcome(outcome)
        return
    while True:
        events, cursor = await _replay_visible_events(
            store,
            task_id,
            cursor,
            event_visibility_provider,
        )
        if events:
            elapsed_without_event = 0.0
            for event in events:
                yield format_sse_event(event)
        outcome = await outcome_provider()
        current_fingerprint = _outcome_fingerprint(outcome)
        if current_fingerprint != outcome_fingerprint:
            yield format_run_outcome(outcome)
            outcome_fingerprint = current_fingerprint
        if outcome.streamShouldClose:
            return
        if events:
            continue
        await asyncio.sleep(poll_interval_seconds)
        elapsed_without_event += poll_interval_seconds
        if elapsed_without_event >= heartbeat_interval_seconds:
            yield format_heartbeat()
            elapsed_without_event = 0.0


def _outcome_fingerprint(outcome: WritingRunOutcome) -> str:
    return json.dumps(
        outcome.model_dump(mode="json", exclude={"observedAt"}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


async def _replay_visible_events(
    store: Any,
    task_id: str,
    cursor: str | None,
    visibility_provider: Callable[
        [list[WritingEvent]],
        Awaitable[dict[str, ReplayDisposition]],
    ]
    | None,
) -> tuple[list[WritingEvent], str | None]:
    replayed = await store.replay(task_id, cursor)
    if not replayed:
        return [], cursor
    dispositions = (
        await visibility_provider(replayed)
        if visibility_provider is not None
        else {event.id: "emit" for event in replayed}
    )
    visible: list[WritingEvent] = []
    next_cursor = cursor
    for event in replayed:
        disposition = dispositions.get(event.id, "wait")
        if disposition == "wait":
            break
        next_cursor = event.id
        if disposition == "emit":
            visible.append(event)
    return visible, next_cursor


def _stream_key(task_id: str) -> str:
    return f"writing:events:{task_id}"


def _source_key(task_id: str, source_event_id: str) -> str:
    return f"writing:event-source:{task_id}:{source_event_id}"


def _sequence_key(task_id: str) -> str:
    return f"writing:event-sequence:{task_id}"


def _expected_sequence(
    last_sequence: int | None,
    *,
    sequence: int,
    durable_baseline: int,
    allow_rebase: bool,
) -> int:
    if (
        allow_rebase
        and sequence > durable_baseline
        and (last_sequence is None or last_sequence <= durable_baseline)
    ):
        return sequence
    if last_sequence is not None:
        return last_sequence + 1
    return 1


def _same_agent_event(
    existing: WritingEvent,
    *,
    sequence: int,
    event: str,
    data: dict[str, JsonValue],
) -> bool:
    return (
        existing.source_event_id is not None
        and existing.sequence == sequence
        and existing.event == event
        and existing.data == data
    )


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
