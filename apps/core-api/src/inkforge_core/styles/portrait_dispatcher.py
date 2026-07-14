from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PortraitDispatchRecord:
    task_id: str
    style_id: str
    user_id: str
    section: str | None
    status: str
    updated_at: datetime


class PortraitDispatchRepository(Protocol):
    async def list_reconcilable_portrait_tasks(
        self,
        limit: int,
        stale_before: datetime,
    ) -> list[PortraitDispatchRecord]: ...


class PortraitDispatchSubmitter(Protocol):
    async def submit(
        self,
        *,
        user_id: str,
        style_id: str,
        task_id: str,
        run_id: str,
        section: str | None,
    ) -> None: ...


class PortraitTaskDispatcher:
    def __init__(
        self,
        repository: PortraitDispatchRepository,
        submitter: PortraitDispatchSubmitter,
        *,
        batch_size: int = 20,
        interval_seconds: float = 5.0,
        processing_stale_after: timedelta = timedelta(minutes=10),
    ) -> None:
        if (
            batch_size < 1
            or interval_seconds <= 0
            or processing_stale_after <= timedelta(0)
        ):
            raise ValueError("画像任务投递配置无效")
        self._repository = repository
        self._submitter = submitter
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._processing_stale_after = processing_stale_after
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run_once(self) -> int:
        stale_before = (
            datetime.now(UTC).replace(tzinfo=None) - self._processing_stale_after
        )
        completed = 0
        records = await self._repository.list_reconcilable_portrait_tasks(
            self._batch_size,
            stale_before,
        )
        for record in records:
            try:
                await self._submitter.submit(
                    user_id=record.user_id,
                    style_id=record.style_id,
                    task_id=record.task_id,
                    run_id=record.task_id,
                    section=record.section,
                )
                completed += 1
            except Exception as exc:
                logger.warning(
                    "画像任务投递失败，等待后台重试",
                    extra={
                        "taskId": record.task_id,
                        "styleId": record.style_id,
                        "errorCode": type(exc).__name__,
                    },
                )
        return completed

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("画像任务后台领取失败，等待下次重试")
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                pass
