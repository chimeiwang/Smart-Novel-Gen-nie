from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Protocol

from inkforge_contracts.jobs import AgentJobStatus

from ..operations.transient_errors import is_transient_infrastructure_error
from .commands import WritingCommandRecord

logger = logging.getLogger(__name__)


class CommandDispatchRepository(Protocol):
    async def claim_due(
        self,
        limit: int,
        active_stale_before: datetime,
    ) -> list[WritingCommandRecord]: ...

    async def mark_agent_active(self, command_id: str) -> WritingCommandRecord: ...

    async def settle_dispatch_terminal(
        self,
        command_id: str,
        agent_status: AgentJobStatus,
    ) -> WritingCommandRecord: ...

    async def record_dispatch_failure(
        self, command_id: str, error_code: str
    ) -> WritingCommandRecord: ...


class CommandSubmitter(Protocol):
    async def submit_command(
        self, command: WritingCommandRecord
    ) -> AgentJobStatus: ...


class WritingRunCommandDispatcher:
    def __init__(
        self,
        repository: CommandDispatchRepository,
        submitter: CommandSubmitter,
        *,
        batch_size: int = 20,
        interval_seconds: float = 2,
        active_stale_after: timedelta = timedelta(minutes=10),
    ) -> None:
        if (
            batch_size < 1
            or interval_seconds <= 0
            or active_stale_after <= timedelta(0)
        ):
            raise ValueError("写作命令投递配置无效")
        self._repository = repository
        self._submitter = submitter
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._active_stale_after = active_stale_after
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run_once(self) -> int:
        completed = 0
        active_stale_before = (
            datetime.now(UTC).replace(tzinfo=None) - self._active_stale_after
        )
        commands = await self._repository.claim_due(
            self._batch_size,
            active_stale_before,
        )
        for command in commands:
            try:
                agent_status = await self._submitter.submit_command(command)
                if agent_status in {"queued", "running"}:
                    await self._repository.mark_agent_active(command.id)
                else:
                    await self._repository.settle_dispatch_terminal(
                        command.id,
                        agent_status,
                    )
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
                    raise
                if not is_transient_infrastructure_error(exc):
                    raise
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
            except Exception as exc:
                if not is_transient_infrastructure_error(exc):
                    raise
                logger.warning(
                    "写作命令后台领取暂时失败，等待下次重试",
                    extra={"errorCode": type(exc).__name__},
                )
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                pass
