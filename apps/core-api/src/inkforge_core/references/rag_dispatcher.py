from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from inkforge_contracts.jobs import AgentJobStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RagDispatchRecord:
    user_id: str
    novel_id: str
    reference_id: str
    content_hash: str


class RagDispatchRepository(Protocol):
    async def list_pending_rag_documents(
        self,
        limit: int,
    ) -> list[RagDispatchRecord]: ...

    async def mark_rag_dispatch_terminal(
        self,
        novel_id: str,
        reference_id: str,
        content_hash: str,
        agent_status: AgentJobStatus,
    ) -> None: ...


class RagDispatchSubmitter(Protocol):
    async def submit(
        self,
        user_id: str,
        novel_id: str,
        reference_id: str,
        content_hash: str,
    ) -> AgentJobStatus: ...


class RagIndexDispatcher:
    def __init__(
        self,
        repository: RagDispatchRepository,
        submitter: RagDispatchSubmitter,
        *,
        batch_size: int = 20,
        interval_seconds: float = 5.0,
    ) -> None:
        if batch_size < 1 or interval_seconds <= 0:
            raise ValueError("检索索引投递配置无效")
        self._repository = repository
        self._submitter = submitter
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run_once(self) -> int:
        completed = 0
        records = await self._repository.list_pending_rag_documents(self._batch_size)
        for record in records:
            try:
                agent_status = await self._submitter.submit(
                    record.user_id,
                    record.novel_id,
                    record.reference_id,
                    record.content_hash,
                )
                if agent_status not in {"queued", "running"}:
                    await self._repository.mark_rag_dispatch_terminal(
                        record.novel_id,
                        record.reference_id,
                        record.content_hash,
                        agent_status,
                    )
                completed += 1
            except Exception as exc:
                logger.warning(
                    "检索索引投递失败，等待后台重试",
                    extra={
                        "referenceId": record.reference_id,
                        "errorCode": type(exc).__name__,
                    },
                )
        return completed

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("检索索引后台领取失败，等待下次重试")
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                pass
