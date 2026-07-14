from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import timedelta

from .repository import JobKind, QueueClaim, QueueJob, RedisRunQueue

JobHandler = Callable[[QueueJob], Awaitable[None]]

logger = logging.getLogger(__name__)


class NonRetryableJobError(RuntimeError):
    retryable = False


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
    ) -> None:
        if (
            max_attempts < 1
            or poll_interval <= 0
            or infrastructure_retry_base <= 0
            or infrastructure_retry_max < infrastructure_retry_base
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
                infrastructure_failures += 1
                delay = min(
                    self._infrastructure_retry_base
                    * (2 ** min(infrastructure_failures - 1, 10)),
                    self._infrastructure_retry_max,
                )
                logger.exception(
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
        except Exception as exc:
            if getattr(exc, "retryable", True) is False or claim.attempts >= self._max_attempts:
                await self._queue.acknowledge(claim, status="failed")
            else:
                await self._queue.retry(claim, delay=self._retry_delay)
        else:
            await self._queue.acknowledge(claim, status="completed")
        return True

    async def _run_with_heartbeat(
        self,
        claim: QueueClaim,
        handler: JobHandler,
    ) -> None:
        task: asyncio.Future[None] = asyncio.ensure_future(handler(claim.job))
        heartbeat_seconds = max(self._visibility_timeout.total_seconds() / 3, 0.05)
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=heartbeat_seconds)
            if done:
                break
            extended = await self._queue.extend(
                claim,
                visibility_timeout=self._visibility_timeout,
            )
            if not extended:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise RuntimeError("任务租约已失效")
        await task
