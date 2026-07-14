from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from inkforge_contracts.jobs import AgentJobStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QualityDispatchRecord:
    run_id: str
    check_id: str
    user_id: str
    novel_id: str
    chapter_id: str
    source_task_id: str | None
    message: str | None


class QualityDispatchRepository(Protocol):
    async def list_dispatchable_quality_runs(
        self,
        limit: int,
    ) -> list[QualityDispatchRecord]: ...

    async def mark_quality_run_running(self, run_id: str) -> None: ...

    async def record_quality_dispatch_failure(
        self,
        run_id: str,
        error_code: str,
    ) -> None: ...

    async def fail_run(
        self,
        check_id: str,
        user_id: str,
        *,
        run_id: str,
        novel_id: str,
    ) -> None: ...


class QualityDispatchSubmitter(Protocol):
    async def submit(
        self,
        *,
        run_id: str,
        user_id: str,
        check_id: str,
        novel_id: str,
        chapter_id: str,
        source_task_id: str | None,
        message: str | None,
    ) -> AgentJobStatus: ...


class QualityRunDispatcher:
    def __init__(
        self,
        repository: QualityDispatchRepository,
        submitter: QualityDispatchSubmitter,
        *,
        batch_size: int = 20,
        interval_seconds: float = 5.0,
    ) -> None:
        if batch_size < 1 or interval_seconds <= 0:
            raise ValueError("质量检查投递配置无效")
        self._repository = repository
        self._submitter = submitter
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def dispatch(self, record: QualityDispatchRecord) -> bool:
        try:
            agent_status = await self._submitter.submit(
                run_id=record.run_id,
                user_id=record.user_id,
                check_id=record.check_id,
                novel_id=record.novel_id,
                chapter_id=record.chapter_id,
                source_task_id=record.source_task_id,
                message=record.message,
            )
            if agent_status in {"queued", "running"}:
                await self._repository.mark_quality_run_running(record.run_id)
            else:
                await self._repository.fail_run(
                    record.check_id,
                    record.user_id,
                    run_id=record.run_id,
                    novel_id=record.novel_id,
                )
            return True
        except Exception as exc:
            error_code = type(exc).__name__
            try:
                await self._repository.record_quality_dispatch_failure(
                    record.run_id,
                    error_code,
                )
            except Exception:
                logger.exception(
                    "记录质量检查投递失败状态时发生异常",
                    extra={"runId": record.run_id},
                )
            logger.warning(
                "质量检查投递失败，等待后台重试",
                extra={
                    "runId": record.run_id,
                    "checkId": record.check_id,
                    "errorCode": error_code,
                },
            )
            return False

    async def run_once(self) -> int:
        completed = 0
        records = await self._repository.list_dispatchable_quality_runs(self._batch_size)
        for record in records:
            if await self.dispatch(record):
                completed += 1
        return completed

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("质量检查后台领取失败，等待下次重试")
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                pass
