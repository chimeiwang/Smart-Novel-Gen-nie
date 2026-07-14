from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from .commands import WritingCommandRecord

logger = logging.getLogger(__name__)


class CommandDispatchRepository(Protocol):
    async def claim_due(self, limit: int) -> list[WritingCommandRecord]: ...

    async def mark_submitted(self, command_id: str) -> WritingCommandRecord: ...

    async def record_dispatch_failure(
        self, command_id: str, error_code: str
    ) -> WritingCommandRecord: ...


class CommandSubmitter(Protocol):
    async def submit_command(self, command: WritingCommandRecord) -> None: ...


class WritingRunCommandDispatcher:
    def __init__(
        self,
        repository: CommandDispatchRepository,
        submitter: CommandSubmitter,
        *,
        batch_size: int = 20,
        interval_seconds: float = 2,
    ) -> None:
        if batch_size < 1 or interval_seconds <= 0:
            raise ValueError("写作命令投递配置无效")
        self._repository = repository
        self._submitter = submitter
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run_once(self) -> int:
        completed = 0
        commands = await self._repository.claim_due(self._batch_size)
        for command in commands:
            try:
                await self._submitter.submit_command(command)
                await self._repository.mark_submitted(command.id)
                completed += 1
            except Exception as exc:
                error_code = type(exc).__name__
                try:
                    await self._repository.record_dispatch_failure(command.id, error_code)
                except Exception:
                    logger.exception(
                        "记录写作命令投递失败状态时发生异常",
                        extra={"commandId": command.id, "taskId": command.task.id},
                    )
                logger.warning(
                    "写作命令投递失败，等待后台重试",
                    extra={
                        "commandId": command.id,
                        "taskId": command.task.id,
                        "errorCode": error_code,
                    },
                )
        return completed

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("写作命令后台领取失败，等待下次重试")
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                pass
