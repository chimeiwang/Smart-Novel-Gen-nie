"""视频规划任务的 PostgreSQL 耐久投递器。"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from inkforge_contracts.jobs import AgentJobStatus
from pydantic import JsonValue

from ..operations.transient_errors import is_transient_infrastructure_error
from .repository import VideoTaskDispatch

logger = logging.getLogger(__name__)


class VideoDispatchRepository(Protocol):
    async def claim_due_plan_tasks(self, limit: int) -> list[VideoTaskDispatch]: ...

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


class VideoDispatchSubmitter(Protocol):
    async def submit(
        self,
        *,
        user_id: str,
        novel_id: str,
        task_id: str,
        job_id: str,
        payload: dict[str, JsonValue],
    ) -> AgentJobStatus: ...


class VideoTaskDispatcher:
    """从耐久任务表重建 Agent 队列索引，并监督瞬时投递失败。"""

    def __init__(
        self,
        repository: VideoDispatchRepository,
        submitter: VideoDispatchSubmitter,
        *,
        batch_size: int = 20,
        interval_seconds: float = 5.0,
    ) -> None:
        if batch_size < 1 or interval_seconds <= 0:
            raise ValueError("视频任务投递配置无效")
        self._repository = repository
        self._submitter = submitter
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def dispatch(self, record: VideoTaskDispatch) -> bool:
        """投递一条已领取数据库租约的任务；瞬时错误保留为 pending。"""
        try:
            agent_status = await self._submitter.submit(
                user_id=record.user_id,
                novel_id=record.novel_id,
                task_id=record.task_id,
                job_id=record.job_id,
                payload=record.payload.model_dump(mode="json"),
            )
            if agent_status in {"queued", "running"}:
                await self._repository.mark_submitted(record.task_id)
            else:
                await self._repository.settle_dispatch_terminal(
                    record.task_id,
                    agent_status,
                )
            return True
        except Exception as exc:
            transient = is_transient_infrastructure_error(exc)
            error_code = type(exc).__name__
            try:
                await self._repository.record_dispatch_failure(
                    record.task_id,
                    error_code,
                    transient=transient,
                )
            except Exception:
                logger.exception(
                    "记录视频任务投递失败状态时发生异常",
                    extra={"taskId": record.task_id},
                )
                raise
            if not transient:
                raise
            logger.warning(
                "视频任务投递暂时失败，等待后台重试",
                extra={
                    "taskId": record.task_id,
                    "jobId": record.job_id,
                    "errorCode": error_code,
                },
            )
            return False

    async def run_once(self) -> int:
        completed = 0
        records = await self._repository.claim_due_plan_tasks(self._batch_size)
        for record in records:
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
                    "视频任务后台领取暂时失败，等待下次重试",
                    extra={"errorCode": type(exc).__name__},
                )
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                pass
