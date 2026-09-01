"""独立重放尚未送达 Core 的 V2 execution 终态；绝不调用模型。"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Literal

from inkforge_contracts.execution import ExecutionStepResult

from .callbacks import ExecutionCallbackClient, ExecutionCallbackError
from .journal import (
    CallbackClaim,
    ExecutionJournalConflictError,
    RedisExecutionJournal,
)

DeliveryOutcome = Literal["delivered", "rejected", "retry", "quarantined"]


class TerminalCallbackReplayer:
    """用 Redis claim/lease 保障多进程下的有界、可恢复终态投递。"""

    def __init__(
        self,
        journal: RedisExecutionJournal,
        callbacks: ExecutionCallbackClient,
        *,
        batch_size: int = 1,
        claim_lease: timedelta = timedelta(seconds=30),
        poll_interval_seconds: float = 0.5,
        retry_base_seconds: float = 0.5,
        retry_max_seconds: float = 30.0,
    ) -> None:
        if not 1 <= batch_size <= 100:
            raise ValueError("terminal callback replay 批大小必须为 1..100")
        if claim_lease <= timedelta(0):
            raise ValueError("terminal callback replay 租约必须大于零")
        if poll_interval_seconds <= 0:
            raise ValueError("terminal callback replay 轮询间隔必须大于零")
        if retry_base_seconds < 0 or retry_max_seconds <= 0:
            raise ValueError("terminal callback replay 退避配置无效")
        if retry_base_seconds > retry_max_seconds:
            raise ValueError("terminal callback replay 基础退避不能大于上限")
        self._journal = journal
        self._callbacks = callbacks
        self._batch_size = batch_size
        self._claim_lease = claim_lease
        self._poll_interval_seconds = poll_interval_seconds
        self._retry_base_seconds = retry_base_seconds
        self._retry_max_seconds = retry_max_seconds
        self._stop_event = asyncio.Event()
        self._wake_event = asyncio.Event()
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running and not self._stop_event.is_set()

    def wake(self) -> None:
        self._wake_event.set()

    def request_stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()

    async def run(self) -> None:
        if self._running:
            raise RuntimeError("terminal callback replayer 已在运行")
        self._running = True
        try:
            while not self._stop_event.is_set():
                claims = await self._journal.claim_due_callbacks(
                    limit=self._batch_size,
                    lease=self._claim_lease,
                )
                if claims:
                    for claim in claims:
                        if self._stop_event.is_set():
                            return
                        await self._deliver_claim(claim)
                    continue
                await self._wait_for_work()
        finally:
            self._running = False

    async def deliver_immediately(
        self,
        step_id: str,
        *,
        max_attempts: int = 1,
    ) -> DeliveryOutcome | None:
        """新终态先做少量同步投递；失败事实仍由后台 replayer 接管。"""

        if max_attempts < 1:
            raise ValueError("terminal callback 立即投递次数必须为正整数")
        for attempt in range(max_attempts):
            claim = await self._journal.claim_callback(
                step_id,
                lease=self._claim_lease,
            )
            if claim is None:
                return None
            outcome, retry_delay = await self._deliver_claim(claim)
            if outcome != "retry" or attempt + 1 >= max_attempts:
                return outcome
            if retry_delay > 0:
                await asyncio.sleep(retry_delay)
        return None

    async def _deliver_claim(
        self,
        claim: CallbackClaim,
    ) -> tuple[DeliveryOutcome, float]:
        entry = await self._journal.require(claim.step_id)
        terminal = entry.terminal
        if (
            terminal is None
            or entry.request_hash != claim.request_hash
            or terminal.resultHash != claim.result_hash
        ):
            raise ExecutionJournalConflictError("V2 execution callback claim 与终态不一致")
        if await self._journal.is_restore_quarantined():
            # claim 可能早于 restore marker 已经取得；尽量贴近 HTTP 前二次
            # 复验并把完整终态放回 pending，隔离本身不是 supervisor 异常。
            already_delivered = await self._reschedule_or_observe_refence(
                claim,
                "EXECUTION_JOURNAL_RESTORE_QUARANTINED",
                0.0,
            )
            return ("delivered" if already_delivered else "quarantined"), 0.0
        try:
            if isinstance(terminal, ExecutionStepResult):
                receipt = await self._callbacks.send_result(terminal)
            else:
                receipt = await self._callbacks.send_failure(terminal)
        except ExecutionCallbackError as exc:
            if not exc.retryable:
                await self._journal.mark_callback_rejected(
                    step_id=claim.step_id,
                    request_hash=claim.request_hash,
                    result_hash=claim.result_hash,
                    error_code=exc.code,
                    claim_token=claim.claim_token,
                )
                return "rejected", 0.0
            delay = self._retry_delay(claim)
            already_delivered = await self._reschedule_or_observe_refence(
                claim, exc.code, delay
            )
            if already_delivered:
                return "delivered", 0.0
            self.wake()
            return "retry", delay
        if receipt.status == "stale":
            # Core 已换到更新但尚未终态的 fence。完整终态必须留在 journal；
            # 新 execution submit 会原子重绑 job/fence 并立即唤醒同一终态回放。
            delay = self._retry_delay(claim)
            already_delivered = await self._reschedule_or_observe_refence(
                claim,
                "EXECUTION_CALLBACK_STALE_FENCE",
                delay,
            )
            if already_delivered:
                return "delivered", 0.0
            self.wake()
            return "retry", delay
        await self._journal.mark_callback_delivered(
            step_id=claim.step_id,
            request_hash=claim.request_hash,
            result_hash=claim.result_hash,
            claim_token=claim.claim_token,
        )
        return "delivered", 0.0

    async def _reschedule_or_observe_refence(
        self,
        claim: CallbackClaim,
        error_code: str,
        delay: float,
    ) -> bool:
        try:
            await self._journal.reschedule_callback(
                claim,
                error_code=error_code,
                next_attempt_at=datetime.now(UTC) + timedelta(seconds=delay),
            )
            return False
        except ExecutionJournalConflictError:
            # 新 fence 受理会清除旧 claim 并自行把未送达终态放回 pending；
            # 只在精确同一终态仍待投递时把冲突解释为该合法竞态。
            entry = await self._journal.require(claim.step_id)
            if (
                entry.state in {"result", "failure"}
                and entry.request_hash == claim.request_hash
                and entry.result_hash == claim.result_hash
                and entry.callback_delivery in {"pending", "delivered"}
            ):
                return entry.callback_delivery == "delivered"
            raise

    def _retry_delay(self, claim: CallbackClaim) -> float:
        if self._retry_base_seconds == 0:
            return 0.0
        exponential = self._retry_base_seconds * (2 ** min(claim.attempts, 16))
        bounded = min(self._retry_max_seconds, exponential)
        digest = hashlib.sha256(
            f"{claim.step_id}:{claim.result_hash}:{claim.attempts + 1}".encode()
        ).digest()
        ratio = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
        jittered = bounded * (0.8 + ratio * 0.4)
        return float(min(self._retry_max_seconds, jittered))

    async def _wait_for_work(self) -> None:
        self._wake_event.clear()
        try:
            await asyncio.wait_for(
                self._wake_event.wait(),
                timeout=self._poll_interval_seconds,
            )
        except TimeoutError:
            pass
