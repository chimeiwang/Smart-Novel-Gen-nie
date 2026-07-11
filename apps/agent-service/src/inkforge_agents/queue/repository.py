from __future__ import annotations

import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

JobKind = Literal["writing", "portrait", "rag", "quality"]
JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
_PRIORITY_FACTOR = 10_000_000_000_000


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
    def __init__(self, redis: AsyncRedis, *, prefix: str = "inkforge:runs") -> None:
        self._redis = redis
        self._prefix = prefix.rstrip(":")

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
            6,
            self._ready,
            self._processing,
            self._payloads,
            self._statuses,
            self._leases,
            self._attempts,
            int(current.timestamp() * 1000),
            _PRIORITY_FACTOR,
            deadline_ms,
            lease_token,
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

    async def acknowledge(self, claim: QueueClaim, *, status: JobStatus) -> bool:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("确认任务必须使用终态")
        result = await self._redis.eval(
            _ACK_SCRIPT,
            5,
            self._processing,
            self._payloads,
            self._statuses,
            self._leases,
            self._attempts,
            claim.job.jobId,
            claim.leaseToken,
            status,
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
            4,
            self._ready,
            self._processing,
            self._statuses,
            self._leases,
            claim.job.jobId,
            claim.leaseToken,
            score,
        )
        return bool(result)

    async def recover_expired(self, *, now: datetime | None = None) -> int:
        result = await self._redis.eval(
            _RECOVER_SCRIPT,
            5,
            self._ready,
            self._processing,
            self._statuses,
            self._leases,
            self._scores,
            int(_utc(now).timestamp() * 1000),
        )
        return int(result)

    async def cancel(self, job_id: str) -> bool:
        result = await self._redis.eval(
            _CANCEL_SCRIPT,
            5,
            self._ready,
            self._processing,
            self._payloads,
            self._statuses,
            self._leases,
            job_id,
        )
        return bool(result)

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
if (status == 'completed' or status == 'failed' or status == 'cancelled') and ARGV[4] ~= '1' then
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
local candidates = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
if #candidates == 0 then return nil end
local score = tonumber(candidates[2])
if (score % tonumber(ARGV[2])) > tonumber(ARGV[1]) then return nil end
local job_id = candidates[1]
local payload = redis.call('HGET', KEYS[3], job_id)
if not payload then
  redis.call('ZREM', KEYS[1], job_id)
  redis.call('HDEL', KEYS[4], job_id)
  return nil
end
redis.call('ZREM', KEYS[1], job_id)
redis.call('ZADD', KEYS[2], ARGV[3], job_id)
redis.call('HSET', KEYS[4], job_id, 'running')
redis.call('HSET', KEYS[5], job_id, ARGV[4])
local attempts = redis.call('HINCRBY', KEYS[6], job_id, 1)
return {payload, attempts}
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
return 1
"""

_RETRY_SCRIPT = """
if redis.call('HGET', KEYS[3], ARGV[1]) ~= 'running' then return 0 end
if redis.call('HGET', KEYS[4], ARGV[1]) ~= ARGV[2] then return 0 end
redis.call('ZREM', KEYS[2], ARGV[1])
redis.call('HSET', KEYS[3], ARGV[1], 'queued')
redis.call('HDEL', KEYS[4], ARGV[1])
redis.call('ZADD', KEYS[1], ARGV[3], ARGV[1])
return 1
"""

_RECOVER_SCRIPT = """
local jobs = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', ARGV[1])
local recovered = 0
for _, job_id in ipairs(jobs) do
  if redis.call('HGET', KEYS[3], job_id) == 'running' then
    local score = redis.call('HGET', KEYS[5], job_id)
    if score then
      redis.call('ZADD', KEYS[1], score, job_id)
      redis.call('HSET', KEYS[3], job_id, 'queued')
      recovered = recovered + 1
    end
  end
  redis.call('ZREM', KEYS[2], job_id)
  redis.call('HDEL', KEYS[4], job_id)
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
return 1
"""
