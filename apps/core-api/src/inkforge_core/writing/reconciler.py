from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from ..operations.transient_errors import is_transient_infrastructure_error
from .records import TaskRecord

logger = logging.getLogger(__name__)


class ReconciliationRepository(Protocol):
    async def list_reconcilable(self, limit: int) -> list[TaskRecord]: ...

    async def create_reconciliation_command(self, task: TaskRecord) -> bool: ...


class ImmediateCommandDispatcher(Protocol):
    async def run_once(self) -> int: ...


class WritingRunReconciler:
    def __init__(
        self,
        repository: ReconciliationRepository,
        dispatcher: ImmediateCommandDispatcher,
        *,
        batch_size: int = 50,
        interval_seconds: float = 30,
    ) -> None:
        if batch_size < 1 or interval_seconds <= 0:
            raise ValueError("运行对账配置无效")
        self._repository = repository
        self._dispatcher = dispatcher
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run_once(self) -> int:
        created = 0
        for task in await self._repository.list_reconcilable(self._batch_size):
            try:
                if await self._repository.create_reconciliation_command(task):
                    created += 1
            except Exception as exc:
                if not is_transient_infrastructure_error(exc):
                    raise
                logger.warning(
                    "写作运行对账命令创建失败",
                    extra={"taskId": task.id, "errorCode": type(exc).__name__},
                )
        if created:
            await self._dispatcher.run_once()
        return created

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception as exc:
                if not is_transient_infrastructure_error(exc):
                    raise
                logger.warning(
                    "写作运行后台领取暂时失败，等待下次重试",
                    extra={"errorCode": type(exc).__name__},
                )
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                pass
