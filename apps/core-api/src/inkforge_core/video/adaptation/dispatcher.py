"""章节影视化 PostgreSQL 耐久任务投递器。"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from inkforge_contracts.jobs import AgentJobStatus
from pydantic import JsonValue

from ...operations.transient_errors import is_transient_infrastructure_error
from .repository import AdaptationTaskDispatch

logger = logging.getLogger(__name__)


class AdaptationDispatchRepository(Protocol):
    async def claim_due_tasks(self, limit: int) -> list[AdaptationTaskDispatch]: ...

    async def mark_submitted(self, task_id: str) -> None: ...

    async def record_dispatch_failure(
        self,
        task_id: str,
        error_code: str,
        *,
        transient: bool,
    ) -> None: ...

    async def settle_dispatch_terminal(
        self,
        task_id: str,
        agent_status: AgentJobStatus,
    ) -> None: ...


class AdaptationDispatchSubmitter(Protocol):
    async def submit(
        self,
        *,
        user_id: str,
        novel_id: str,
        task_id: str,
        job_id: str,
        payload: dict[str, JsonValue],
    ) -> AgentJobStatus: ...


class VideoAdaptationTaskDispatcher:
    """把新 AdaptationTask 投递到现有 video 队列，不复用旧 Scene 任务表。"""

    def __init__(
        self,
        repository: AdaptationDispatchRepository,
        submitter: AdaptationDispatchSubmitter,
        *,
        batch_size: int = 20,
        interval_seconds: float = 5.0,
    ) -> None:
        if batch_size < 1 or interval_seconds <= 0:
            raise ValueError("章节影视化任务投递配置无效")
        self._repository = repository
        self._submitter = submitter
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def dispatch(self, record: AdaptationTaskDispatch) -> bool:
        try:
            status = await self._submitter.submit(
                user_id=record.user_id,
                novel_id=record.novel_id,
                task_id=record.task_id,
                job_id=record.job_id,
                payload=record.payload.model_dump(mode="json"),
            )
            if status in {"queued", "running"}:
                await self._repository.mark_submitted(record.task_id)
            else:
                await self._repository.settle_dispatch_terminal(record.task_id, status)
            return True
        except Exception as exc:
            transient = is_transient_infrastructure_error(exc)
            await self._repository.record_dispatch_failure(
                record.task_id,
                type(exc).__name__,
                transient=transient,
            )
            if not transient:
                raise
            logger.warning(
                "章节影视化任务投递暂时失败",
                extra={"taskId": record.task_id, "jobId": record.job_id},
            )
            return False

    async def run_once(self) -> int:
        completed = 0
        for record in await self._repository.claim_due_tasks(self._batch_size):
            if await self.dispatch(record):
                completed += 1
        return completed

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception as exc:
                if not is_transient_infrastructure_error(exc):
                    raise
                logger.warning(
                    "章节影视化任务后台领取暂时失败",
                    extra={"errorCode": type(exc).__name__},
                )
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                pass
