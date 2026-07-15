from __future__ import annotations

import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

JobKind = Literal["writing", "portrait", "rag", "quality"]
JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
_PRIORITY_FACTOR = 10_000_000_000_000
_DEFAULT_TERMINAL_RETENTION = timedelta(days=7)
_MIN_TERMINAL_RETENTION = timedelta(hours=24)
_MAX_PURGE_BATCH = 1000
_MAX_CORRUPT_CLEANUP = 100


class AsyncRedis(Protocol):
    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> Awaitable[Any]: ...

    def hget(self, name: str, key: str) -> Awaitable[Any]: ...

    def zrem(self, name: str, *values: object) -> Awaitable[Any]: ...


class QueueJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobId: str = Field(min_length=1, max_length=256)
    kind: JobKind
    runId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
    userId: str = Field(min_length=1, max_length=256)
    priority: int = Field(ge=0, le=99)
    payload: dict[str, JsonValue]
    createdAt: AwareDatetime


class QueueClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job: QueueJob
    leaseToken: str
    attempts: int = Field(ge=1)


class RedisRunQueue:
    def __init__(
        self,
        redis: AsyncRedis,
        *,
        prefix: str = "inkforge:runs",
        terminal_retention: timedelta = _DEFAULT_TERMINAL_RETENTION,
    ) -> None:
        if terminal_retention < _MIN_TERMINAL_RETENTION:
            raise ValueError("终态保留时间不能少于 24 小时")
        self._redis = redis
        self._prefix = prefix.rstrip(":")
        self._terminal_retention = terminal_retention

    @property
    def terminal_retention(self) -> timedelta:
        return self._terminal_retention

    @property
    def _ready(self) -> str:
        return f"{self._prefix}:ready"

    @property
    def _processing(self) -> str:
        return f"{self._prefix}:processing"

    @property
    def _payloads(self) -> str:
        return f"{self._prefix}:payloads"

    @property
    def _statuses(self) -> str:
        return f"{self._prefix}:statuses"

    @property
    def _leases(self) -> str:
        return f"{self._prefix}:leases"

    @property
    def _attempts(self) -> str:
        return f"{self._prefix}:attempts"

    @property
    def _scores(self) -> str:
        return f"{self._prefix}:scores"

    @property
    def _terminal(self) -> str:
        return f"{self._prefix}:terminal"

    async def enqueue(self, job: QueueJob, *, force: bool = False) -> bool:
        created_ms = int(job.createdAt.timestamp() * 1000)
        score = job.priority * _PRIORITY_FACTOR + created_ms
        result = await self._redis.eval(
            _ENQUEUE_SCRIPT,
            6,
            self._ready,
            self._processing,
            self._payloads,
            self._statuses,
            self._leases,
            self._scores,
            job.jobId,
            job.model_dump_json(),
            score,
            "1" if force else "0",
        )
        return bool(result)

    async def claim(
        self,
        *,
        visibility_timeout: timedelta,
        now: datetime | None = None,
    ) -> QueueClaim | None:
        current = _utc(now)
        lease_token = str(uuid.uuid4())
        deadline_ms = int((current + visibility_timeout).timestamp() * 1000)
        result = await self._redis.eval(
            _CLAIM_SCRIPT,
            7,
            self._ready,
            self._processing,
            self._payloads,
            self._statuses,
            self._leases,
            self._attempts,
            self._scores,
            int(current.timestamp() * 1000),
            _PRIORITY_FACTOR,
            deadline_ms,
            lease_token,
            _MAX_CORRUPT_CLEANUP,
        )
        if not result:
            return None
        payload = _text(result[0])
        attempts = int(result[1])
        return QueueClaim(
            job=QueueJob.model_validate_json(payload),
            leaseToken=lease_token,
            attempts=attempts,
        )

    async def extend(
        self,
        claim: QueueClaim,
        *,
        visibility_timeout: timedelta,
        now: datetime | None = None,
    ) -> bool:
        deadline_ms = int((_utc(now) + visibility_timeout).timestamp() * 1000)
        result = await self._redis.eval(
            _EXTEND_SCRIPT,
            3,
            self._processing,
            self._statuses,
            self._leases,
            claim.job.jobId,
            claim.leaseToken,
            deadline_ms,
        )
        return bool(result)

    async def acknowledge(
        self,
        claim: QueueClaim,
        *,
        status: JobStatus,
        now: datetime | None = None,
    ) -> bool:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("确认任务必须使用终态")
        result = await self._redis.eval(
            _ACK_SCRIPT,
            8,
            self._processing,
            self._payloads,
            self._statuses,
            self._leases,
            self._attempts,
            self._scores,
            self._ready,
            self._terminal,
            claim.job.jobId,
            claim.leaseToken,
            status,
            int(_utc(now).timestamp() * 1000),
        )
        return bool(result)

    async def retry(
        self,
        claim: QueueClaim,
        *,
        delay: timedelta,
        now: datetime | None = None,
    ) -> bool:
        ready_ms = int((_utc(now) + delay).timestamp() * 1000)
        score = claim.job.priority * _PRIORITY_FACTOR + ready_ms
        result = await self._redis.eval(
            _RETRY_SCRIPT,
            5,
            self._ready,
            self._processing,
            self._statuses,
            self._leases,
            self._scores,
            claim.job.jobId,
            claim.leaseToken,
            score,
        )
        return bool(result)

    async def recover_expired(self, *, now: datetime | None = None) -> int:
        result = await self._redis.eval(
            _RECOVER_SCRIPT,
            8,
            self._ready,
            self._processing,
            self._payloads,
            self._statuses,
            self._leases,
            self._attempts,
            self._scores,
            self._terminal,
            int(_utc(now).timestamp() * 1000),
        )
        return int(result)

    async def cancel(self, job_id: str, *, now: datetime | None = None) -> bool:
        result = await self._redis.eval(
            _CANCEL_SCRIPT,
            8,
            self._ready,
            self._processing,
            self._payloads,
            self._statuses,
            self._leases,
            self._attempts,
            self._scores,
            self._terminal,
            job_id,
            int(_utc(now).timestamp() * 1000),
        )
        return bool(result)

    async def purge_terminal(self, cutoff: datetime, *, limit: int = 100) -> int:
        if limit < 1 or limit > _MAX_PURGE_BATCH:
            raise ValueError("终态清理批次必须在 1 到 1000 之间")
        result = await self._redis.eval(
            _PURGE_TERMINAL_SCRIPT,
            2,
            self._statuses,
            self._terminal,
            int(_utc(cutoff).timestamp() * 1000),
            limit,
        )
        return int(result)

    async def backfill_legacy_terminal(
        self,
        *,
        cursor: int,
        now: datetime | None = None,
        limit: int = 100,
    ) -> tuple[int, int]:
        if cursor < 0:
            raise ValueError("终态回填游标不能为负数")
        if limit < 1 or limit > _MAX_PURGE_BATCH:
            raise ValueError("终态回填批次必须在 1 到 1000 之间")
        result = await self._redis.eval(
            _BACKFILL_LEGACY_TERMINAL_SCRIPT,
            8,
            self._ready,
            self._processing,
            self._payloads,
            self._statuses,
            self._leases,
            self._attempts,
            self._scores,
            self._terminal,
            cursor,
            int(_utc(now).timestamp() * 1000),
            limit,
        )
        return int(result[0]), int(result[1])

    async def status(self, job_id: str) -> JobStatus | None:
        value = await self._redis.hget(self._statuses, job_id)
        if value is None:
            return None
        status = _text(value)
        if status not in {"queued", "running", "completed", "failed", "cancelled"}:
            raise RuntimeError("队列状态损坏")
        return status  # type: ignore[return-value]


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("队列时间必须包含时区")
    return current.astimezone(UTC)


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


_ENQUEUE_SCRIPT = """
local status = redis.call('HGET', KEYS[4], ARGV[1])
if status == 'running' then
  return 0
end
if status == 'completed' or status == 'failed' or status == 'cancelled' then
  return 0
end
if status == 'queued' and ARGV[4] ~= '1' then
  return 0
end
redis.call('HSET', KEYS[3], ARGV[1], ARGV[2])
redis.call('HSET', KEYS[4], ARGV[1], 'queued')
redis.call('HSET', KEYS[6], ARGV[1], ARGV[3])
redis.call('ZREM', KEYS[2], ARGV[1])
redis.call('HDEL', KEYS[5], ARGV[1])
redis.call('ZADD', KEYS[1], ARGV[3], ARGV[1])
return 1
"""

_CLAIM_SCRIPT = """
local factor = tonumber(ARGV[2])
local now = tonumber(ARGV[1])
local cleaned = 0
for priority = 0, 99 do
  local minimum = priority * factor
  local maximum = minimum + now
  while true do
    local candidates = redis.call(
      'ZRANGEBYSCORE', KEYS[1], minimum, maximum, 'LIMIT', 0, 1
    )
    if #candidates == 0 then break end
    local job_id = candidates[1]
    local status = redis.call('HGET', KEYS[4], job_id)
    local payload = redis.call('HGET', KEYS[3], job_id)
    if status == 'queued' and payload then
      redis.call('ZREM', KEYS[1], job_id)
      redis.call('ZADD', KEYS[2], ARGV[3], job_id)
      redis.call('HSET', KEYS[4], job_id, 'running')
      redis.call('HSET', KEYS[5], job_id, ARGV[4])
      local attempts = redis.call('HINCRBY', KEYS[6], job_id, 1)
      return {payload, attempts}
    end
    redis.call('ZREM', KEYS[1], job_id)
    local terminal = status == 'completed' or status == 'failed' or status == 'cancelled'
    local active = status == 'queued' or status == 'running'
    if (not payload and not terminal) or (not terminal and not active) then
      redis.call('HDEL', KEYS[3], job_id)
      redis.call('HDEL', KEYS[4], job_id)
      redis.call('HDEL', KEYS[5], job_id)
      redis.call('HDEL', KEYS[6], job_id)
      redis.call('HDEL', KEYS[7], job_id)
    end
    cleaned = cleaned + 1
    if cleaned >= tonumber(ARGV[5]) then return nil end
  end
end
return nil
"""

_EXTEND_SCRIPT = """
if redis.call('HGET', KEYS[2], ARGV[1]) ~= 'running' then return 0 end
if redis.call('HGET', KEYS[3], ARGV[1]) ~= ARGV[2] then return 0 end
redis.call('ZADD', KEYS[1], ARGV[3], ARGV[1])
return 1
"""

_ACK_SCRIPT = """
if redis.call('HGET', KEYS[3], ARGV[1]) ~= 'running' then return 0 end
if redis.call('HGET', KEYS[4], ARGV[1]) ~= ARGV[2] then return 0 end
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('HDEL', KEYS[2], ARGV[1])
redis.call('HSET', KEYS[3], ARGV[1], ARGV[3])
redis.call('HDEL', KEYS[4], ARGV[1])
redis.call('HDEL', KEYS[5], ARGV[1])
redis.call('HDEL', KEYS[6], ARGV[1])
redis.call('ZREM', KEYS[7], ARGV[1])
redis.call('ZADD', KEYS[8], ARGV[4], ARGV[1])
return 1
"""

_RETRY_SCRIPT = """
if redis.call('HGET', KEYS[3], ARGV[1]) ~= 'running' then return 0 end
if redis.call('HGET', KEYS[4], ARGV[1]) ~= ARGV[2] then return 0 end
redis.call('ZREM', KEYS[2], ARGV[1])
redis.call('HSET', KEYS[3], ARGV[1], 'queued')
redis.call('HDEL', KEYS[4], ARGV[1])
redis.call('ZADD', KEYS[1], ARGV[3], ARGV[1])
redis.call('HSET', KEYS[5], ARGV[1], ARGV[3])
return 1
"""

_RECOVER_SCRIPT = """
local jobs = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', ARGV[1])
local recovered = 0
for _, job_id in ipairs(jobs) do
  if redis.call('HGET', KEYS[4], job_id) == 'running' then
    local score = redis.call('HGET', KEYS[7], job_id)
    local payload = redis.call('HGET', KEYS[3], job_id)
    if score and payload then
      redis.call('ZADD', KEYS[1], score, job_id)
      redis.call('HSET', KEYS[4], job_id, 'queued')
      recovered = recovered + 1
    else
      redis.call('ZREM', KEYS[1], job_id)
      redis.call('HDEL', KEYS[3], job_id)
      redis.call('HSET', KEYS[4], job_id, 'failed')
      redis.call('HDEL', KEYS[6], job_id)
      redis.call('HDEL', KEYS[7], job_id)
      redis.call('ZADD', KEYS[8], ARGV[1], job_id)
    end
  end
  redis.call('ZREM', KEYS[2], job_id)
  redis.call('HDEL', KEYS[5], job_id)
end
return recovered
"""

_CANCEL_SCRIPT = """
local status = redis.call('HGET', KEYS[4], ARGV[1])
if not status or status == 'completed' or status == 'failed' or status == 'cancelled' then
  return 0
end
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('ZREM', KEYS[2], ARGV[1])
redis.call('HDEL', KEYS[3], ARGV[1])
redis.call('HSET', KEYS[4], ARGV[1], 'cancelled')
redis.call('HDEL', KEYS[5], ARGV[1])
redis.call('HDEL', KEYS[6], ARGV[1])
redis.call('HDEL', KEYS[7], ARGV[1])
redis.call('ZADD', KEYS[8], ARGV[2], ARGV[1])
return 1
"""

_PURGE_TERMINAL_SCRIPT = """
local jobs = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', ARGV[1], 'LIMIT', 0, ARGV[2])
if #jobs == 0 then return 0 end
redis.call('HDEL', KEYS[1], unpack(jobs))
redis.call('ZREM', KEYS[2], unpack(jobs))
return #jobs
"""

_BACKFILL_LEGACY_TERMINAL_SCRIPT = """
local scan = redis.call('HSCAN', KEYS[4], ARGV[1], 'COUNT', ARGV[3])
local next_cursor = scan[1]
local entries = scan[2]
local migrated = 0
for index = 1, #entries, 2 do
  local job_id = entries[index]
  local status = entries[index + 1]
  local terminal = status == 'completed' or status == 'failed' or status == 'cancelled'
  if terminal then
    if not redis.call('ZSCORE', KEYS[8], job_id) then
      redis.call('ZADD', KEYS[8], ARGV[2], job_id)
      migrated = migrated + 1
    end
    redis.call('ZREM', KEYS[1], job_id)
    redis.call('ZREM', KEYS[2], job_id)
    redis.call('HDEL', KEYS[3], job_id)
    redis.call('HDEL', KEYS[5], job_id)
    redis.call('HDEL', KEYS[6], job_id)
    redis.call('HDEL', KEYS[7], job_id)
  end
end
return {next_cursor, migrated}
"""
