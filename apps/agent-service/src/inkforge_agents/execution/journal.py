"""V2 Step 的 Redis 执行日志；只保存执行边界，不承担业务工作流权威。"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol, cast

from inkforge_contracts.execution import (
    ExecutionCancelRequest,
    ExecutionStepFailure,
    ExecutionStepRequest,
    ExecutionStepResult,
)
from pydantic import JsonValue

JournalState = Literal["accepted", "started", "result", "failure"]
CallbackDeliveryState = Literal["pending", "delivered", "rejected"]
TerminalPayload = ExecutionStepResult | ExecutionStepFailure

_DEFAULT_RETENTION = timedelta(hours=24)
_MIN_RETENTION = timedelta(hours=24)


class AsyncJournalRedis(Protocol):
    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> Awaitable[Any]: ...

    def hgetall(self, name: str) -> Awaitable[Mapping[object, object]]: ...

    def zcard(self, name: str) -> Awaitable[int]: ...

    def ping(self) -> Awaitable[bool]: ...

    def info(self, section: str | None = None) -> Awaitable[Mapping[object, object]]: ...

    def config_get(self, pattern: str = "*", *args: str) -> Awaitable[Mapping[object, object]]: ...

    def get(self, name: str) -> Awaitable[object | None]: ...


class ExecutionJournalError(RuntimeError):
    """执行日志缺失、损坏或状态迁移非法。"""


class ExecutionJournalConflictError(ExecutionJournalError):
    """同一 Step 被不同执行请求或身份复用。"""


class ExecutionJournalStaleFenceError(ExecutionJournalError):
    """执行请求使用了已经失效的 fencing token。"""


class ExecutionJournalCancelledError(ExecutionJournalError):
    """终态写入输给了已经持久化的取消请求。"""


@dataclass(frozen=True, slots=True)
class JournalEntry:
    state: JournalState
    request_hash: str
    input_hash: str
    run_id: str
    step_id: str
    job_id: str
    fencing_token: int
    idempotency_key: str
    novel_id: str | None
    resolved_model: Mapping[str, JsonValue]
    accepted_at: datetime
    started_at: datetime | None
    provider_started_at: datetime | None
    provider_attempts: int
    provider_idempotency_key: str | None
    cancel_request_id: str | None
    terminal: TerminalPayload | None
    result_hash: str | None
    callback_delivery: CallbackDeliveryState
    callback_error_code: str | None


@dataclass(frozen=True, slots=True)
class CancelDecision:
    status: Literal["accepted", "already_cancelled", "already_terminal", "not_found"]
    entry: JournalEntry | None


@dataclass(frozen=True, slots=True)
class AcceptDecision:
    entry: JournalEntry
    created: bool
    refenced: bool


@dataclass(frozen=True, slots=True)
class JournalBacklog:
    callback_pending: int
    callback_rejected: int


@dataclass(frozen=True, slots=True)
class JournalHealth:
    connected: bool
    persistence_ok: bool
    quarantined: bool
    error_code: str | None
    used_memory_bytes: int | None = None
    maxmemory_bytes: int | None = None
    evicted_keys: int | None = None

    @property
    def ready(self) -> bool:
        return (
            self.connected
            and self.persistence_ok
            and not self.quarantined
            and self.error_code is None
        )


@dataclass(frozen=True, slots=True)
class CallbackClaim:
    step_id: str
    request_hash: str
    result_hash: str
    claim_token: str
    attempts: int


class RedisExecutionJournal:
    def __init__(
        self,
        redis: AsyncJournalRedis,
        *,
        prefix: str = "inkforge:executions",
        retention: timedelta = _DEFAULT_RETENTION,
        require_durability: bool = False,
    ) -> None:
        if retention < _MIN_RETENTION:
            raise ValueError("V2 execution journal 保留时间不能少于 24 小时")
        self._redis = redis
        self._prefix = prefix.rstrip(":")
        self._retention_seconds = round(retention.total_seconds())
        self._require_durability = require_durability

    async def accept(
        self,
        request: ExecutionStepRequest,
        resolved_model: Mapping[str, JsonValue],
        *,
        now: datetime | None = None,
    ) -> JournalEntry:
        return (
            await self.accept_with_disposition(
                request,
                resolved_model,
                now=now,
            )
        ).entry

    async def accept_with_disposition(
        self,
        request: ExecutionStepRequest,
        resolved_model: Mapping[str, JsonValue],
        *,
        now: datetime | None = None,
    ) -> AcceptDecision:
        current = _utc(now)
        novel_id = cast(str | None, getattr(request, "novelId", None))
        result = await self._eval(
            _ACCEPT_SCRIPT,
            4,
            self._key(request.stepId),
            self._callback_pending,
            self._callback_rejected,
            self._callback_leased,
            request.requestHash,
            request.inputHash,
            request.runId,
            request.stepId,
            request.jobId,
            request.fencingToken,
            request.idempotencyKey,
            _json_dumps(dict(resolved_model)),
            _millis(current),
            self._retention_seconds,
            novel_id or "",
        )
        code = _text(result[0])
        if code == "conflict":
            raise ExecutionJournalConflictError("同一 Step 的 V2 requestHash 或资源身份冲突")
        if code == "stale_fence":
            raise ExecutionJournalStaleFenceError("V2 execution fencing token 已失效")
        if code != "ok":
            raise ExecutionJournalError("V2 execution journal 受理结果无效")
        disposition = _text(result[2])
        if disposition not in {"created", "existing", "refenced"}:
            raise ExecutionJournalError("V2 execution journal 受理 disposition 无效")
        return AcceptDecision(
            entry=await self.require(request.stepId),
            created=disposition == "created",
            refenced=disposition == "refenced",
        )

    async def mark_started(
        self,
        request: ExecutionStepRequest,
        *,
        now: datetime | None = None,
    ) -> JournalEntry:
        result = await self._eval(
            _START_SCRIPT,
            1,
            self._key(request.stepId),
            request.requestHash,
            request.jobId,
            request.fencingToken,
            _millis(_utc(now)),
            self._retention_seconds,
        )
        code = _text(result)
        if code == "conflict":
            raise ExecutionJournalConflictError("V2 execution started 身份冲突")
        if code == "stale_fence":
            raise ExecutionJournalStaleFenceError("V2 execution started 使用旧 fence")
        if code == "cancelled":
            raise ExecutionJournalCancelledError("V2 execution 已在模型调用前取消")
        if code not in {"started", "result", "failure"}:
            raise ExecutionJournalError("V2 execution journal 无法进入 started")
        return await self.require(request.stepId)

    async def begin_provider_attempt(
        self,
        request: ExecutionStepRequest,
        *,
        now: datetime | None = None,
    ) -> int:
        result = int(
            await self._eval(
                _ATTEMPT_SCRIPT,
                1,
                self._key(request.stepId),
                request.requestHash,
                request.jobId,
                request.fencingToken,
                request.idempotencyKey,
                _millis(_utc(now)),
                self._retention_seconds,
            )
        )
        if result == -1:
            raise ExecutionJournalConflictError("供应商调用前 V2 execution 身份已变化")
        if result == -2:
            raise ExecutionJournalCancelledError("供应商调用前 V2 execution 已取消")
        if result < 1:
            raise ExecutionJournalError("供应商尝试计数未能持久化")
        return result

    async def record_terminal(
        self,
        request: ExecutionStepRequest,
        terminal: TerminalPayload,
    ) -> JournalEntry:
        terminal_kind = "result" if isinstance(terminal, ExecutionStepResult) else "failure"
        cancel_request_id = (
            terminal.cancelRequestId
            if isinstance(terminal, ExecutionStepFailure) and terminal.errorCategory == "cancelled"
            else None
        )
        result = await self._eval(
            _TERMINAL_SCRIPT,
            4,
            self._key(request.stepId),
            self._callback_pending,
            self._callback_rejected,
            self._callback_leased,
            request.requestHash,
            request.jobId,
            request.fencingToken,
            terminal_kind,
            terminal.model_dump_json(by_alias=True),
            terminal.resultHash,
            cancel_request_id or "",
            self._retention_seconds,
            _millis(datetime.now(UTC)),
        )
        code = _text(result)
        if code == "conflict":
            raise ExecutionJournalConflictError("V2 execution 终态身份或结果冲突")
        if code == "stale_fence":
            raise ExecutionJournalStaleFenceError("V2 execution 终态使用旧 fence")
        if code == "cancelled":
            raise ExecutionJournalCancelledError("V2 execution 结果输给了持久化取消")
        if code not in {"stored", "existing"}:
            raise ExecutionJournalError("V2 execution 终态持久化结果无效")
        return await self.require(request.stepId)

    async def request_cancel(
        self,
        request: ExecutionCancelRequest,
    ) -> CancelDecision:
        novel_id = cast(str | None, getattr(request, "novelId", None))
        result = await self._eval(
            _CANCEL_SCRIPT,
            1,
            self._key(request.stepId),
            request.requestHash,
            request.runId,
            request.stepId,
            request.jobId,
            request.fencingToken,
            request.cancelRequestId,
            novel_id or "",
            self._retention_seconds,
        )
        code = _text(result)
        if code == "conflict":
            raise ExecutionJournalConflictError("V2 execution cancelRequestId 冲突")
        if code not in {
            "accepted",
            "already_cancelled",
            "already_terminal",
            "not_found",
        }:
            raise ExecutionJournalError("V2 execution cancel journal 结果无效")
        entry = None if code == "not_found" else await self.require(request.stepId)
        return CancelDecision(status=cast(Any, code), entry=entry)

    async def mark_callback_delivered(
        self,
        *,
        step_id: str,
        request_hash: str,
        result_hash: str,
        claim_token: str | None = None,
    ) -> JournalEntry:
        result = await self._eval(
            _CALLBACK_DELIVERED_SCRIPT,
            4,
            self._key(step_id),
            self._callback_pending,
            self._callback_rejected,
            self._callback_leased,
            request_hash,
            result_hash,
            self._retention_seconds,
            claim_token or "",
        )
        if int(result) != 1:
            raise ExecutionJournalConflictError("V2 execution callback 确认身份冲突")
        return await self.require(step_id)

    async def mark_callback_rejected(
        self,
        *,
        step_id: str,
        request_hash: str,
        result_hash: str,
        error_code: str,
        claim_token: str | None = None,
    ) -> JournalEntry:
        result = await self._eval(
            _CALLBACK_REJECTED_SCRIPT,
            4,
            self._key(step_id),
            self._callback_pending,
            self._callback_rejected,
            self._callback_leased,
            request_hash,
            result_hash,
            error_code,
            self._retention_seconds,
            claim_token or "",
        )
        if int(result) != 1:
            raise ExecutionJournalConflictError("V2 execution callback 拒绝身份冲突")
        return await self.require(step_id)

    async def claim_due_callbacks(
        self,
        *,
        now: datetime | None = None,
        limit: int = 16,
        lease: timedelta = timedelta(seconds=30),
    ) -> tuple[CallbackClaim, ...]:
        if limit < 1 or limit > 100:
            raise ValueError("callback claim 批大小必须为 1..100")
        if lease <= timedelta(0):
            raise ValueError("callback claim 租约必须大于零")
        current = _utc(now)
        result = await self._eval(
            _CLAIM_DUE_CALLBACKS_SCRIPT,
            3,
            self._callback_pending,
            self._callback_leased,
            self._restore_quarantine,
            _millis(current),
            limit,
            _millis(current + lease),
            uuid.uuid4().hex,
        )
        return _parse_claims(result)

    async def claim_callback(
        self,
        step_id: str,
        *,
        now: datetime | None = None,
        lease: timedelta = timedelta(seconds=30),
        force: bool = False,
    ) -> CallbackClaim | None:
        if lease <= timedelta(0):
            raise ValueError("callback claim 租约必须大于零")
        current = _utc(now)
        result = await self._eval(
            _CLAIM_ONE_CALLBACK_SCRIPT,
            4,
            self._key(step_id),
            self._callback_pending,
            self._callback_leased,
            self._restore_quarantine,
            _millis(current),
            _millis(current + lease),
            uuid.uuid4().hex,
            "1" if force else "0",
        )
        claims = _parse_claims(result)
        return claims[0] if claims else None

    async def reschedule_callback(
        self,
        claim: CallbackClaim,
        *,
        error_code: str,
        next_attempt_at: datetime,
    ) -> JournalEntry:
        next_attempt = _utc(next_attempt_at)
        attempts = claim.attempts + 1
        result = await self._eval(
            _RESCHEDULE_CALLBACK_SCRIPT,
            3,
            self._key(claim.step_id),
            self._callback_pending,
            self._callback_leased,
            claim.request_hash,
            claim.result_hash,
            claim.claim_token,
            attempts,
            _millis(next_attempt),
            error_code,
        )
        if int(result) != 1:
            raise ExecutionJournalConflictError("V2 execution callback 重排身份冲突")
        return await self.require(claim.step_id)

    async def backlog(self) -> JournalBacklog:
        try:
            pending = await self._redis.zcard(self._callback_pending)
            leased = await self._redis.zcard(self._callback_leased)
            rejected = await self._redis.zcard(self._callback_rejected)
        except Exception:
            raise ExecutionJournalError("V2 execution journal backlog 不可用") from None
        return JournalBacklog(
            callback_pending=int(pending) + int(leased),
            callback_rejected=int(rejected),
        )

    async def health(self) -> JournalHealth:
        try:
            connected = bool(await self._redis.ping())
            quarantined = await self.is_restore_quarantined()
        except Exception:
            return JournalHealth(
                connected=False,
                persistence_ok=False,
                quarantined=False,
                error_code="EXECUTION_JOURNAL_CONNECTION_FAILED",
            )
        if not connected:
            return JournalHealth(
                connected=False,
                persistence_ok=False,
                quarantined=quarantined,
                error_code="EXECUTION_JOURNAL_CONNECTION_FAILED",
            )
        if not self._require_durability:
            return JournalHealth(
                connected=True,
                persistence_ok=True,
                quarantined=quarantined,
                error_code=(
                    "EXECUTION_JOURNAL_RESTORE_QUARANTINED" if quarantined else None
                ),
            )
        try:
            persistence = {
                _text(key): _text(value).lower()
                for key, value in (await self._redis.info("persistence")).items()
            }
            memory = {
                _text(key): _text(value).lower()
                for key, value in (await self._redis.info("memory")).items()
            }
            stats = {
                _text(key): _text(value).lower()
                for key, value in (await self._redis.info("stats")).items()
            }
            config = {
                _text(key).lower(): _text(value).lower()
                for key, value in (
                    await self._redis.config_get(
                        "appendonly",
                        "appendfsync",
                        "aof-load-truncated",
                        "maxmemory-policy",
                        "maxmemory",
                        "hash-max-listpack-value",
                        "hash-max-listpack-entries",
                    )
                ).items()
            }
        except Exception:
            return JournalHealth(
                connected=True,
                persistence_ok=False,
                quarantined=quarantined,
                error_code="EXECUTION_JOURNAL_PERSISTENCE_UNAVAILABLE",
            )
        persistence_ok = (
            persistence.get("aof_enabled") == "1"
            and persistence.get("aof_last_write_status", "ok") == "ok"
            and config.get("appendonly") == "yes"
            and config.get("appendfsync") == "always"
            and config.get("aof-load-truncated") == "no"
            and config.get("maxmemory-policy") == "noeviction"
            and config.get("hash-max-listpack-value") == "4096"
            and config.get("hash-max-listpack-entries") == "64"
        )
        try:
            used_memory = int(memory.get("used_memory", "0"))
            maxmemory = int(config.get("maxmemory", "0"))
            evicted_keys = int(stats.get("evicted_keys", "0"))
        except ValueError:
            used_memory = 0
            maxmemory = 0
            evicted_keys = 0
            persistence_ok = False
        memory_pressure = maxmemory <= 0 or used_memory * 10 >= maxmemory * 9
        error_code = None
        if quarantined:
            error_code = "EXECUTION_JOURNAL_RESTORE_QUARANTINED"
        elif not persistence_ok:
            error_code = "EXECUTION_JOURNAL_PERSISTENCE_UNSAFE"
        elif evicted_keys > 0:
            error_code = "EXECUTION_JOURNAL_EVICTION_DETECTED"
        elif memory_pressure:
            error_code = "EXECUTION_JOURNAL_MEMORY_PRESSURE"
        return JournalHealth(
            connected=True,
            persistence_ok=persistence_ok,
            quarantined=quarantined,
            error_code=error_code,
            used_memory_bytes=used_memory,
            maxmemory_bytes=maxmemory,
            evicted_keys=evicted_keys,
        )

    async def ensure_available(self) -> None:
        health = await self.health()
        if not health.ready:
            raise ExecutionJournalError(health.error_code or "EXECUTION_JOURNAL_UNAVAILABLE")

    async def is_restore_quarantined(self) -> bool:
        """轻量读取恢复写屏障；供 callback 发送前 fail-closed 复验。"""

        try:
            return await self._redis.get(self._restore_quarantine) is not None
        except Exception:
            raise ExecutionJournalError("V2 execution restore quarantine 不可读") from None

    async def get(self, step_id: str) -> JournalEntry | None:
        try:
            raw = await self._redis.hgetall(self._key(step_id))
        except Exception:
            raise ExecutionJournalError("V2 execution journal 读取不可用") from None
        if not raw:
            return None
        values = {_text(key): _text(value) for key, value in raw.items()}
        return _parse_entry(values)

    async def require(self, step_id: str) -> JournalEntry:
        entry = await self.get(step_id)
        if entry is None:
            raise ExecutionJournalError("V2 execution journal 记录不存在")
        return entry

    def _key(self, step_id: str) -> str:
        return f"{self._prefix}:{step_id}"

    async def _eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> Any:
        try:
            return await self._redis.eval(script, numkeys, *keys_and_args)
        except Exception:
            raise ExecutionJournalError("V2 execution journal 写入不可用") from None

    @property
    def _callback_pending(self) -> str:
        return f"{self._prefix}:callbacks:pending"

    @property
    def _callback_rejected(self) -> str:
        return f"{self._prefix}:callbacks:rejected"

    @property
    def _callback_leased(self) -> str:
        return f"{self._prefix}:callbacks:leased"

    @property
    def _restore_quarantine(self) -> str:
        return f"{self._prefix}:restore:quarantine"


def _parse_entry(values: Mapping[str, str]) -> JournalEntry:
    try:
        state = values["state"]
        if state not in {"accepted", "started", "result", "failure"}:
            raise ValueError
        callback_delivery = values.get("callback_delivery", "pending")
        if callback_delivery not in {"pending", "delivered", "rejected"}:
            raise ValueError
        terminal: TerminalPayload | None = None
        terminal_payload = values.get("terminal_payload")
        result_hash = values.get("result_hash") or None
        if state == "result":
            if result_hash is None or (
                terminal_payload is None and callback_delivery != "delivered"
            ):
                raise ValueError
            if terminal_payload is not None:
                terminal = ExecutionStepResult.model_validate_json(terminal_payload)
        elif state == "failure":
            if result_hash is None or (
                terminal_payload is None and callback_delivery != "delivered"
            ):
                raise ValueError
            if terminal_payload is not None:
                terminal = ExecutionStepFailure.model_validate_json(terminal_payload)
        elif result_hash is not None:
            raise ValueError
        if terminal is not None and terminal.resultHash != result_hash:
            raise ValueError
        if terminal is not None:
            terminal = terminal.model_copy(
                update={
                    "jobId": values["job_id"],
                    "fencingToken": int(values["fencing_token"]),
                    "novelId": values.get("novel_id") or None,
                }
            )
        return JournalEntry(
            state=cast(JournalState, state),
            request_hash=values["request_hash"],
            input_hash=values["input_hash"],
            run_id=values["run_id"],
            step_id=values["step_id"],
            job_id=values["job_id"],
            fencing_token=int(values["fencing_token"]),
            idempotency_key=values["idempotency_key"],
            novel_id=values.get("novel_id") or None,
            resolved_model=cast(
                Mapping[str, JsonValue],
                _json_loads(values["resolved_model"]),
            ),
            accepted_at=_from_millis(values["accepted_ms"]),
            started_at=(_from_millis(values["started_ms"]) if values.get("started_ms") else None),
            provider_started_at=(
                _from_millis(values["provider_started_ms"])
                if values.get("provider_started_ms")
                else None
            ),
            provider_attempts=int(values.get("provider_attempts", "0")),
            provider_idempotency_key=values.get("provider_idempotency_key") or None,
            cancel_request_id=values.get("cancel_request_id") or None,
            terminal=terminal,
            result_hash=result_hash,
            callback_delivery=cast(CallbackDeliveryState, callback_delivery),
            callback_error_code=values.get("callback_error_code") or None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ExecutionJournalError("V2 execution journal 记录损坏") from exc


def _parse_claims(value: object) -> tuple[CallbackClaim, ...]:
    if not isinstance(value, (list, tuple)):
        raise ExecutionJournalError("V2 execution callback claim 返回无效")
    if len(value) % 5 != 0:
        raise ExecutionJournalError("V2 execution callback claim 字段不完整")
    claims: list[CallbackClaim] = []
    try:
        for offset in range(0, len(value), 5):
            claims.append(
                CallbackClaim(
                    step_id=_text(value[offset]),
                    request_hash=_text(value[offset + 1]),
                    result_hash=_text(value[offset + 2]),
                    claim_token=_text(value[offset + 3]),
                    attempts=int(_text(value[offset + 4])),
                )
            )
    except (TypeError, ValueError) as exc:
        raise ExecutionJournalError("V2 execution callback claim 字段损坏") from exc
    return tuple(claims)


def _json_dumps(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _json_loads(value: str) -> object:
    return json.loads(value)


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("V2 execution journal 时间必须包含时区")
    return current.astimezone(UTC)


def _millis(value: datetime) -> int:
    return round(value.timestamp() * 1000)


def _from_millis(value: str) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=UTC)


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


_ACCEPT_SCRIPT = """
local existing_hash = redis.call('HGET', KEYS[1], 'request_hash')
if not existing_hash then
  redis.call('HSET', KEYS[1],
    'state', 'accepted',
    'request_hash', ARGV[1],
    'input_hash', ARGV[2],
    'run_id', ARGV[3],
    'step_id', ARGV[4],
    'job_id', ARGV[5],
    'fencing_token', ARGV[6],
    'idempotency_key', ARGV[7],
    'resolved_model', ARGV[8],
    'accepted_ms', ARGV[9],
    'provider_attempts', '0',
    'callback_delivery', 'pending',
    'novel_id', ARGV[11])
  redis.call('PERSIST', KEYS[1])
  return {'ok', 'accepted', 'created'}
end
if existing_hash ~= ARGV[1]
    or redis.call('HGET', KEYS[1], 'input_hash') ~= ARGV[2]
    or redis.call('HGET', KEYS[1], 'run_id') ~= ARGV[3]
    or redis.call('HGET', KEYS[1], 'step_id') ~= ARGV[4]
    or redis.call('HGET', KEYS[1], 'idempotency_key') ~= ARGV[7]
    or (redis.call('HGET', KEYS[1], 'novel_id') or '') ~= ARGV[11] then
  return {'conflict'}
end
local old_fence = tonumber(redis.call('HGET', KEYS[1], 'fencing_token'))
local new_fence = tonumber(ARGV[6])
if new_fence < old_fence then return {'stale_fence'} end
if new_fence == old_fence and redis.call('HGET', KEYS[1], 'job_id') ~= ARGV[5] then
  return {'conflict'}
end
if new_fence > old_fence then
  redis.call('HSET', KEYS[1],
    'job_id', ARGV[5],
    'fencing_token', ARGV[6])
  local state = redis.call('HGET', KEYS[1], 'state')
  local delivery = redis.call('HGET', KEYS[1], 'callback_delivery')
  if (state == 'result' or state == 'failure') and delivery ~= 'delivered' then
    redis.call('HSET', KEYS[1], 'callback_delivery', 'pending')
    redis.call('ZADD', KEYS[2], ARGV[9], KEYS[1])
    redis.call('ZREM', KEYS[3], KEYS[1])
    redis.call('ZREM', KEYS[4], KEYS[1])
    redis.call('HSET', KEYS[1],
      'callback_attempts', '0',
      'callback_next_ms', ARGV[9])
    redis.call('HDEL', KEYS[1],
      'callback_error_code',
      'callback_claim_token',
      'callback_lease_until_ms')
  end
end
local final_state = redis.call('HGET', KEYS[1], 'state')
local final_delivery = redis.call('HGET', KEYS[1], 'callback_delivery')
if (final_state == 'result' or final_state == 'failure')
    and final_delivery == 'delivered' then
  redis.call('EXPIRE', KEYS[1], ARGV[10])
else
  redis.call('PERSIST', KEYS[1])
end
local disposition = 'existing'
if new_fence > old_fence then disposition = 'refenced' end
return {'ok', redis.call('HGET', KEYS[1], 'state'), disposition}
"""

_START_SCRIPT = """
if redis.call('HGET', KEYS[1], 'request_hash') ~= ARGV[1] then return 'conflict' end
local old_fence = tonumber(redis.call('HGET', KEYS[1], 'fencing_token'))
local new_fence = tonumber(ARGV[3])
if new_fence < old_fence then return 'stale_fence' end
if new_fence ~= old_fence or redis.call('HGET', KEYS[1], 'job_id') ~= ARGV[2] then
  return 'conflict'
end
local state = redis.call('HGET', KEYS[1], 'state')
if state == 'result' or state == 'failure' then return state end
if redis.call('HEXISTS', KEYS[1], 'cancel_request_id') == 1 then return 'cancelled' end
if state == 'accepted' then
  redis.call('HSET', KEYS[1], 'state', 'started', 'started_ms', ARGV[4])
end
redis.call('PERSIST', KEYS[1])
return 'started'
"""

_ATTEMPT_SCRIPT = """
if redis.call('HGET', KEYS[1], 'request_hash') ~= ARGV[1]
    or redis.call('HGET', KEYS[1], 'job_id') ~= ARGV[2]
    or tonumber(redis.call('HGET', KEYS[1], 'fencing_token')) ~= tonumber(ARGV[3])
    or redis.call('HGET', KEYS[1], 'state') ~= 'started' then
  return -1
end
if redis.call('HEXISTS', KEYS[1], 'cancel_request_id') == 1 then return -2 end
local provider_key = redis.call('HGET', KEYS[1], 'provider_idempotency_key')
if provider_key and provider_key ~= ARGV[4] then return -1 end
redis.call('HSET', KEYS[1], 'provider_idempotency_key', ARGV[4])
if redis.call('HEXISTS', KEYS[1], 'provider_started_ms') == 0 then
  redis.call('HSET', KEYS[1], 'provider_started_ms', ARGV[5])
end
local attempts = redis.call('HINCRBY', KEYS[1], 'provider_attempts', 1)
redis.call('PERSIST', KEYS[1])
return attempts
"""

_TERMINAL_SCRIPT = """
if redis.call('HGET', KEYS[1], 'request_hash') ~= ARGV[1] then return 'conflict' end
local old_fence = tonumber(redis.call('HGET', KEYS[1], 'fencing_token'))
local new_fence = tonumber(ARGV[3])
if new_fence < old_fence then return 'stale_fence' end
if new_fence ~= old_fence or redis.call('HGET', KEYS[1], 'job_id') ~= ARGV[2] then
  return 'conflict'
end
local state = redis.call('HGET', KEYS[1], 'state')
if state == 'result' or state == 'failure' then
  if redis.call('HGET', KEYS[1], 'result_hash') == ARGV[6]
      and state == ARGV[4] then return 'existing' end
  return 'conflict'
end
local existing_cancel = redis.call('HGET', KEYS[1], 'cancel_request_id')
if existing_cancel then
  if ARGV[7] == '' or existing_cancel ~= ARGV[7] then return 'cancelled' end
elseif ARGV[7] ~= '' then
  return 'conflict'
end
redis.call('HSET', KEYS[1],
  'state', ARGV[4],
  'terminal_payload', ARGV[5],
  'result_hash', ARGV[6],
  'callback_delivery', 'pending',
  'callback_attempts', '0',
  'callback_next_ms', ARGV[9])
redis.call('HDEL', KEYS[1],
  'callback_error_code',
  'callback_claim_token',
  'callback_lease_until_ms')
redis.call('ZADD', KEYS[2], ARGV[9], KEYS[1])
redis.call('ZREM', KEYS[3], KEYS[1])
redis.call('ZREM', KEYS[4], KEYS[1])
redis.call('PERSIST', KEYS[1])
return 'stored'
"""

_CANCEL_SCRIPT = """
if redis.call('HGET', KEYS[1], 'request_hash') ~= ARGV[1]
    or redis.call('HGET', KEYS[1], 'run_id') ~= ARGV[2]
    or redis.call('HGET', KEYS[1], 'step_id') ~= ARGV[3]
    or redis.call('HGET', KEYS[1], 'job_id') ~= ARGV[4]
    or tonumber(redis.call('HGET', KEYS[1], 'fencing_token')) ~= tonumber(ARGV[5])
    or (redis.call('HGET', KEYS[1], 'novel_id') or '') ~= ARGV[7] then
  return 'not_found'
end
local state = redis.call('HGET', KEYS[1], 'state')
if state == 'result' then return 'already_terminal' end
if state == 'failure' then
  if redis.call('HEXISTS', KEYS[1], 'cancel_request_id') == 1 then
    return 'already_cancelled'
  end
  return 'already_terminal'
end
local existing = redis.call('HGET', KEYS[1], 'cancel_request_id')
if existing then
  if existing == ARGV[6] then return 'already_cancelled' end
  return 'conflict'
end
redis.call('HSET', KEYS[1], 'cancel_request_id', ARGV[6])
redis.call('PERSIST', KEYS[1])
return 'accepted'
"""

_CALLBACK_DELIVERED_SCRIPT = """
if redis.call('HGET', KEYS[1], 'request_hash') ~= ARGV[1]
    or redis.call('HGET', KEYS[1], 'result_hash') ~= ARGV[2] then
  return 0
end
local state = redis.call('HGET', KEYS[1], 'state')
if state ~= 'result' and state ~= 'failure' then return 0 end
local active_claim = redis.call('HGET', KEYS[1], 'callback_claim_token')
if active_claim and (ARGV[4] == '' or active_claim ~= ARGV[4]) then return 0 end
redis.call('HSET', KEYS[1], 'callback_delivery', 'delivered')
local compact_names = {
  'state',
  'request_hash',
  'input_hash',
  'run_id',
  'step_id',
  'job_id',
  'fencing_token',
  'idempotency_key',
  'novel_id',
  'resolved_model',
  'accepted_ms',
  'started_ms',
  'provider_started_ms',
  'provider_attempts',
  'provider_idempotency_key',
  'cancel_request_id',
  'result_hash'
}
local compact = {}
for _, name in ipairs(compact_names) do
  local value = redis.call('HGET', KEYS[1], name)
  if value then
    table.insert(compact, name)
    table.insert(compact, value)
  end
end
redis.call('DEL', KEYS[1])
redis.call('HSET', KEYS[1], unpack(compact))
redis.call('HSET', KEYS[1], 'callback_delivery', 'delivered')
redis.call('ZREM', KEYS[2], KEYS[1])
redis.call('ZREM', KEYS[3], KEYS[1])
redis.call('ZREM', KEYS[4], KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
"""

_CALLBACK_REJECTED_SCRIPT = """
if redis.call('HGET', KEYS[1], 'request_hash') ~= ARGV[1]
    or redis.call('HGET', KEYS[1], 'result_hash') ~= ARGV[2] then
  return 0
end
local state = redis.call('HGET', KEYS[1], 'state')
if state ~= 'result' and state ~= 'failure' then return 0 end
local active_claim = redis.call('HGET', KEYS[1], 'callback_claim_token')
if active_claim and (ARGV[5] == '' or active_claim ~= ARGV[5]) then return 0 end
redis.call('HSET', KEYS[1],
  'callback_delivery', 'rejected',
  'callback_error_code', ARGV[3])
redis.call('HDEL', KEYS[1],
  'callback_claim_token',
  'callback_lease_until_ms',
  'callback_next_ms')
redis.call('ZREM', KEYS[2], KEYS[1])
redis.call('ZADD', KEYS[3], 0, KEYS[1])
redis.call('ZREM', KEYS[4], KEYS[1])
redis.call('PERSIST', KEYS[1])
return 1
"""

_CLAIM_DUE_CALLBACKS_SCRIPT = """
if redis.call('EXISTS', KEYS[3]) == 1 then return {} end
local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', ARGV[1], 'LIMIT', 0, ARGV[2])
for _, key in ipairs(expired) do
  redis.call('ZREM', KEYS[2], key)
  if redis.call('HGET', key, 'callback_delivery') == 'pending' then
    redis.call('HDEL', key, 'callback_claim_token', 'callback_lease_until_ms')
    redis.call('ZADD', KEYS[1], ARGV[1], key)
  end
end
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, ARGV[2])
local result = {}
local index = 0
for _, key in ipairs(due) do
  local state = redis.call('HGET', key, 'state')
  local delivery = redis.call('HGET', key, 'callback_delivery')
  local result_hash = redis.call('HGET', key, 'result_hash')
  if (state == 'result' or state == 'failure')
      and delivery == 'pending'
      and result_hash then
    index = index + 1
    local token = ARGV[4] .. ':' .. tostring(index)
    redis.call('ZREM', KEYS[1], key)
    redis.call('ZADD', KEYS[2], ARGV[3], key)
    redis.call('HSET', key,
      'callback_claim_token', token,
      'callback_lease_until_ms', ARGV[3])
    table.insert(result, redis.call('HGET', key, 'step_id'))
    table.insert(result, redis.call('HGET', key, 'request_hash'))
    table.insert(result, result_hash)
    table.insert(result, token)
    table.insert(result, redis.call('HGET', key, 'callback_attempts') or '0')
  else
    redis.call('ZREM', KEYS[1], key)
  end
end
return result
"""

_CLAIM_ONE_CALLBACK_SCRIPT = """
if redis.call('EXISTS', KEYS[4]) == 1 then return {} end
local leased_until = redis.call('ZSCORE', KEYS[3], KEYS[1])
if leased_until then
  if tonumber(leased_until) > tonumber(ARGV[1]) then return {} end
  redis.call('ZREM', KEYS[3], KEYS[1])
  redis.call('HDEL', KEYS[1], 'callback_claim_token', 'callback_lease_until_ms')
  if redis.call('HGET', KEYS[1], 'callback_delivery') == 'pending' then
    redis.call('ZADD', KEYS[2], ARGV[1], KEYS[1])
  end
end
local due = redis.call('ZSCORE', KEYS[2], KEYS[1])
if not due then return {} end
if ARGV[4] ~= '1' and tonumber(due) > tonumber(ARGV[1]) then return {} end
local state = redis.call('HGET', KEYS[1], 'state')
local delivery = redis.call('HGET', KEYS[1], 'callback_delivery')
local result_hash = redis.call('HGET', KEYS[1], 'result_hash')
if (state ~= 'result' and state ~= 'failure')
    or delivery ~= 'pending'
    or not result_hash then
  redis.call('ZREM', KEYS[2], KEYS[1])
  return {}
end
redis.call('ZREM', KEYS[2], KEYS[1])
redis.call('ZADD', KEYS[3], ARGV[2], KEYS[1])
redis.call('HSET', KEYS[1],
  'callback_claim_token', ARGV[3],
  'callback_lease_until_ms', ARGV[2])
return {
  redis.call('HGET', KEYS[1], 'step_id'),
  redis.call('HGET', KEYS[1], 'request_hash'),
  result_hash,
  ARGV[3],
  redis.call('HGET', KEYS[1], 'callback_attempts') or '0'
}
"""

_RESCHEDULE_CALLBACK_SCRIPT = """
if redis.call('HGET', KEYS[1], 'request_hash') ~= ARGV[1]
    or redis.call('HGET', KEYS[1], 'result_hash') ~= ARGV[2]
    or redis.call('HGET', KEYS[1], 'callback_claim_token') ~= ARGV[3]
    or redis.call('HGET', KEYS[1], 'callback_delivery') ~= 'pending' then
  return 0
end
redis.call('HSET', KEYS[1],
  'callback_attempts', ARGV[4],
  'callback_next_ms', ARGV[5],
  'callback_error_code', ARGV[6])
redis.call('HDEL', KEYS[1], 'callback_claim_token', 'callback_lease_until_ms')
redis.call('ZREM', KEYS[3], KEYS[1])
redis.call('ZADD', KEYS[2], ARGV[5], KEYS[1])
redis.call('PERSIST', KEYS[1])
return 1
"""
