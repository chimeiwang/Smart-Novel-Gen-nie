from __future__ import annotations

from typing import Protocol

from .repository import RedisRunQueue


class JobCancelledError(RuntimeError):
    retryable = False

    def __init__(self) -> None:
        super().__init__("运行任务已取消")


class RunCancellationPort(Protocol):
    async def ensure_active(self, job_id: str | None) -> None: ...


class RedisRunCancellation:
    def __init__(self, queue: RedisRunQueue) -> None:
        self._queue = queue

    async def ensure_active(self, job_id: str | None) -> None:
        if not job_id:
            raise RuntimeError("取消检查缺少队列任务标识")
        if await self._queue.status(job_id) == "cancelled":
            raise JobCancelledError()
