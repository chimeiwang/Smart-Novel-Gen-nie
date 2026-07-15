from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta

from redis.exceptions import (
    BusyLoadingError,
    ResponseError,
)
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)
from redis.exceptions import (
    TimeoutError as RedisTimeoutError,
)

from .repository import JobKind, QueueClaim, QueueJob, RedisRunQueue

JobHandler = Callable[[QueueJob], Awaitable[None]]

logger = logging.getLogger(__name__)


class NonRetryableJobError(RuntimeError):
    retryable = False


class _QueueHeartbeatInfrastructureError(RuntimeError):
    pass


class QueueConsumer:
    def __init__(
        self,
        queue: RedisRunQueue,
        handlers: Mapping[JobKind, JobHandler],
        *,
        visibility_timeout: timedelta = timedelta(minutes=5),
        max_attempts: int = 3,
        retry_delay: timedelta = timedelta(seconds=2),
        poll_interval: float = 0.25,
        infrastructure_retry_base: float = 0.5,
        infrastructure_retry_max: float = 10.0,
        infrastructure_failure_threshold: int = 3,
        terminal_purge_interval: float = 60.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            max_attempts < 1
            or poll_interval <= 0
            or infrastructure_retry_base <= 0
            or infrastructure_retry_max < infrastructure_retry_base
            or infrastructure_failure_threshold < 1
            or terminal_purge_interval <= 0
        ):
            raise ValueError("消费者配置无效")
        self._queue = queue
        self._handlers = dict(handlers)
        self._visibility_timeout = visibility_timeout
        self._max_attempts = max_attempts
        self._retry_delay = retry_delay
        self._poll_interval = poll_interval
        self._infrastructure_retry_base = infrastructure_retry_base
        self._infrastructure_retry_max = infrastructure_retry_max
        self._infrastructure_failure_threshold = infrastructure_failure_threshold
        self._terminal_purge_interval = terminal_purge_interval
        self._clock = clock or (lambda: datetime.now(UTC))
        self._last_terminal_purge_at: datetime | None = None
        self._legacy_terminal_cursor = 0
        self._legacy_terminal_backfill_complete = False
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        infrastructure_failures = 0
        while not self._stop.is_set():
            try:
                processed = await self.run_once()
                infrastructure_failures = 0
            except Exception as exc:
                if not _is_transient_infrastructure_error(exc):
                    raise
                infrastructure_failures += 1
                if (
                    _is_redis_write_rejection(exc)
                    or infrastructure_failures >= self._infrastructure_failure_threshold
                ):
                    logger.error(
                        "队列基础设施连续失败，交给监督器重启",
                        extra={
                            "errorCode": type(exc).__name__,
                            "consecutiveFailures": infrastructure_failures,
                        },
                    )
                    raise
                delay = min(
                    self._infrastructure_retry_base
                    * (2 ** min(infrastructure_failures - 1, 10)),
                    self._infrastructure_retry_max,
                )
                logger.warning(
                    "队列基础设施访问失败，等待后重试",
                    extra={
                        "errorCode": type(exc).__name__,
                        "retryDelaySeconds": delay,
                    },
                )
                await self._wait_or_stop(delay)
                continue
            if not processed:
                await self._wait_or_stop(self._poll_interval)

    async def _wait_or_stop(self, delay_seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=delay_seconds)
        except TimeoutError:
            pass

    async def run_once(self) -> bool:
        await self._backfill_legacy_terminal_if_pending()
        await self._purge_terminal_if_due()
        await self._queue.recover_expired()
        claim = await self._queue.claim(visibility_timeout=self._visibility_timeout)
        if claim is None:
            return False
        handler = self._handlers.get(claim.job.kind)
        if handler is None:
            await self._queue.acknowledge(claim, status="failed")
            return True
        try:
            await self._run_with_heartbeat(claim, handler)
        except _QueueHeartbeatInfrastructureError as exc:
            await self._queue.retry(claim, delay=self._retry_delay)
            cause = exc.__cause__
            if isinstance(cause, Exception):
                raise cause from exc
            raise
        except Exception as exc:
            retryable = _job_retry_decision(exc)
            if retryable is None:
                await self._queue.acknowledge(claim, status="failed")
                raise
            if not retryable or claim.attempts >= self._max_attempts:
                await self._queue.acknowledge(claim, status="failed")
            else:
                await self._queue.retry(claim, delay=self._retry_delay)
        else:
            await self._queue.acknowledge(claim, status="completed")
        return True

    async def _backfill_legacy_terminal_if_pending(self) -> None:
        if self._legacy_terminal_backfill_complete:
            return
        backfill = getattr(self._queue, "backfill_legacy_terminal", None)
        if not callable(backfill):
            self._legacy_terminal_backfill_complete = True
            return
        cursor, _ = await backfill(
            cursor=self._legacy_terminal_cursor,
            now=self._clock(),
        )
        self._legacy_terminal_cursor = cursor
        self._legacy_terminal_backfill_complete = cursor == 0

    async def _purge_terminal_if_due(self) -> None:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("消费者时钟必须包含时区")
        current = now.astimezone(UTC)
        if (
            self._last_terminal_purge_at is not None
            and (current - self._last_terminal_purge_at).total_seconds()
            < self._terminal_purge_interval
        ):
            return
        await self._queue.purge_terminal(current - self._queue.terminal_retention)
        self._last_terminal_purge_at = current

    async def _run_with_heartbeat(
        self,
        claim: QueueClaim,
        handler: JobHandler,
    ) -> None:
        task: asyncio.Future[None] = asyncio.ensure_future(handler(claim.job))
        heartbeat_seconds = max(self._visibility_timeout.total_seconds() / 3, 0.05)
        try:
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=heartbeat_seconds)
                if done:
                    break
                try:
                    extended = await self._queue.extend(
                        claim,
                        visibility_timeout=self._visibility_timeout,
                    )
                except Exception as exc:
                    if _is_transient_infrastructure_error(exc):
                        raise _QueueHeartbeatInfrastructureError from exc
                    raise
                if not extended:
                    raise RuntimeError("任务租约已失效")
            await task
        except BaseException:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise


def _job_retry_decision(exc: Exception) -> bool | None:
    retryable = getattr(exc, "retryable", None)
    if isinstance(retryable, bool):
        return retryable
    recoverable = getattr(exc, "recoverable", None)
    if isinstance(recoverable, bool):
        return recoverable
    return None


def _is_transient_infrastructure_error(exc: Exception) -> bool:
    if isinstance(
        exc,
        (
            ConnectionError,
            TimeoutError,
            RedisConnectionError,
            RedisTimeoutError,
            BusyLoadingError,
        ),
    ):
        return True
    return _is_redis_write_rejection(exc)


def _is_redis_write_rejection(exc: Exception) -> bool:
    if not isinstance(exc, ResponseError):
        return False
    message = str(exc).upper()
    return any(marker in message for marker in ("OOM", "MISCONF", "READONLY"))
