from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from .records import TaskRecord

logger = logging.getLogger(__name__)


class ReconciliationRepository(Protocol):
    async def list_reconcilable(self, limit: int) -> list[TaskRecord]: ...


class ReconciliationSubmitter(Protocol):
    async def reconcile(self, task: TaskRecord) -> None: ...


class WritingRunReconciler:
    def __init__(
        self,
        repository: ReconciliationRepository,
        submitter: ReconciliationSubmitter,
        *,
        batch_size: int = 50,
        interval_seconds: float = 30,
    ) -> None:
        if batch_size < 1 or interval_seconds <= 0:
            raise ValueError("运行对账配置无效")
        self._repository = repository
        self._submitter = submitter
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run_once(self) -> int:
        completed = 0
        for task in await self._repository.list_reconcilable(self._batch_size):
            try:
                await self._submitter.reconcile(task)
                completed += 1
            except Exception:
                logger.warning(
                    "写作运行对账提交失败",
                    extra={"taskId": task.id},
                )
        return completed

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("写作运行后台领取失败，等待下次重试")
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                pass
