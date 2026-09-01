"""V2 Step 的受理、恢复、取消、执行和 Core 回调生命周期。"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from time import monotonic
from typing import Literal

from inkforge_contracts.execution import (
    ExecutionCancelAccepted,
    ExecutionCancelRequest,
    ExecutionStepAccepted,
    ExecutionStepFailure,
    ExecutionStepProgress,
    ExecutionStepRequest,
    ResolvedModelRef,
    StepUsage,
    canonical_execution_sha256,
)
from pydantic import JsonValue, ValidationError

from .callbacks import ExecutionCallbackClient, ExecutionCallbackError
from .executor import (
    ExecutionCapabilityError,
    ExecutionProviderGateClosed,
    FailureCategory,
    ResolvedExecutionStep,
    StatelessExecutionStepExecutor,
)
from .journal import (
    ExecutionJournalCancelledError,
    ExecutionJournalConflictError,
    ExecutionJournalError,
    JournalEntry,
    RedisExecutionJournal,
    TerminalPayload,
)
from .registry import ExecutionRegistry
from .replayer import TerminalCallbackReplayer


@dataclass(frozen=True, slots=True)
class ExecutionServiceHealth:
    ready: bool
    callback_pending: int
    callback_rejected: int
    error_code: str | None
    admission_active: int = 0
    admission_capacity: int = 0
    admission_saturated: bool = False
    journal_connected: bool = False
    journal_persistence_ok: bool = False
    journal_quarantined: bool = False
    journal_used_memory_bytes: int | None = None
    journal_maxmemory_bytes: int | None = None
    journal_evicted_keys: int | None = None


class ExecutionAdmissionSaturatedError(RuntimeError):
    """只拒绝尚无 journal 的新工作；调用方可安全保留 lease 后重投。"""

    retry_after_seconds = 1


class ExecutionServiceUnavailableError(RuntimeError):
    """新执行基础设施门已关闭；终态重放与取消仍保持可用。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(slots=True)
class _ActiveExecution:
    job_id: str
    fencing_token: int
    cancel_event: asyncio.Event
    task: asyncio.Task[None]
    holds_admission: bool


class _ProgressSequence:
    def __init__(self) -> None:
        self._value = 0
        self._lock = asyncio.Lock()

    async def next(self) -> int:
        async with self._lock:
            self._value += 1
            return self._value


class ExecutionService:
    def __init__(
        self,
        *,
        journal: RedisExecutionJournal,
        registry: ExecutionRegistry,
        executor: StatelessExecutionStepExecutor,
        callbacks: ExecutionCallbackClient,
        progress_interval_seconds: float = 10.0,
        callback_retry_base_seconds: float = 0.05,
        progress_attempts: int = 3,
        terminal_callback_attempts: int = 5,
        pending_backlog_limit: int = 100,
        max_active_executions: int = 3,
    ) -> None:
        if progress_interval_seconds <= 0:
            raise ValueError("V2 progress interval 必须大于零")
        if callback_retry_base_seconds < 0:
            raise ValueError("V2 callback retry 退避不能为负数")
        if progress_attempts < 1 or terminal_callback_attempts < 1:
            raise ValueError("V2 callback 尝试次数必须为正整数")
        if pending_backlog_limit < 1:
            raise ValueError("V2 callback pending 门限必须为正整数")
        if max_active_executions < 1:
            raise ValueError("V2 execution admission 容量必须为正整数")
        self._journal = journal
        self._registry = registry
        self._executor = executor
        self._callbacks = callbacks
        self._progress_interval_seconds = progress_interval_seconds
        self._callback_retry_base_seconds = callback_retry_base_seconds
        self._progress_attempts = progress_attempts
        self._terminal_callback_attempts = terminal_callback_attempts
        self._pending_backlog_limit = pending_backlog_limit
        self._max_active_executions = max_active_executions
        self._active: dict[str, _ActiveExecution] = {}
        self._admitted_steps: set[str] = set()
        self._admission_lock = asyncio.Lock()
        self._lock = asyncio.Lock()
        self._closed = False
        self._error_code: str | None = None
        self._background_health_check: Callable[[], bool] | None = None
        self._callback_replayer = TerminalCallbackReplayer(
            journal,
            callbacks,
            retry_base_seconds=callback_retry_base_seconds,
        )

    @property
    def callback_replayer(self) -> TerminalCallbackReplayer:
        return self._callback_replayer

    def set_background_health_check(self, check: Callable[[], bool]) -> None:
        self._background_health_check = check

    async def submit(self, request: ExecutionStepRequest) -> ExecutionStepAccepted:
        if self._closed:
            raise RuntimeError("V2 execution service 已停止")
        existing = await self._journal.get(request.stepId)
        if existing is None or existing.state not in {"result", "failure"}:
            # restore quarantine、AOF write error 或错误持久化配置必须在任何
            # 新模型副作用之前 fail-closed；已持久化终态可以幂等读取，但
            # quarantine 解除前仍不得把 pending callback 发往 Core。
            await self._ensure_callback_and_journal_gate()
        resolved: ResolvedExecutionStep | None = None
        resolved_model: Mapping[str, JsonValue]
        if existing is None or existing.state not in {"result", "failure"}:
            try:
                resolved = self._executor.resolve(request, self._registry)
            except ExecutionCapabilityError:
                if existing is None:
                    raise
                # 已受理执行必须用 journal 冻结的部署身份收敛，不能因为当前部署
                # 已下线而让恢复入口直接 4xx、永远没有终态。
                resolved_model = existing.resolved_model
            else:
                resolved_model = resolved.resolved_model.model_dump(mode="json")
        else:
            # 已持久化终态的 refence/replay 不依赖当前部署 Profile，避免恢复通道
            # 被新工作 admission 或配置下线堵死。
            resolved_model = existing.resolved_model

        holds_admission = False
        async with self._admission_lock:
            current = await self._journal.get(request.stepId)
            if current is None:
                if len(self._admitted_steps) >= self._max_active_executions:
                    raise ExecutionAdmissionSaturatedError("V2 execution admission 已饱和")
                self._admitted_steps.add(request.stepId)
                holds_admission = True
            elif current.state in {"result", "failure"}:
                resolved_model = current.resolved_model
                resolved = None
            try:
                decision = await self._journal.accept_with_disposition(
                    request,
                    resolved_model,
                )
            except BaseException:
                if holds_admission:
                    self._admitted_steps.discard(request.stepId)
                raise
            if holds_admission and not decision.created:
                self._admitted_steps.discard(request.stepId)
                holds_admission = False
        entry = decision.entry
        try:
            frozen_model = ResolvedModelRef.model_validate(entry.resolved_model)
        except ValidationError as exc:
            if holds_admission:
                await self._release_admission(request.stepId)
            raise ExecutionJournalConflictError("V2 journal 解析模型损坏") from exc
        if (
            frozen_model.deploymentProfileKey
            != request.modelProfile.deploymentProfileKey
            or frozen_model.reasoningMode != request.modelProfile.reasoningMode
        ):
            if holds_admission:
                await self._release_admission(request.stepId)
            raise ExecutionJournalConflictError("V2 journal 解析模型与逻辑 Profile 不一致")
        if resolved is not None:
            resolved = replace(
                resolved,
                structured_output_route=frozen_model.structuredOutputRoute,
                resolved_model=frozen_model,
            )

        accepted = ExecutionStepAccepted(
            protocolVersion="2.0",
            jobId=request.jobId,
            runId=request.runId,
            novelId=request.novelId,
            stepId=request.stepId,
            fencingToken=request.fencingToken,
            requestHash=request.requestHash,
            resolvedModel=frozen_model,
            status="queued",
            acceptedAt=entry.accepted_at,
        )
        try:
            await self._schedule(
                request,
                resolved,
                entry=entry,
                created=decision.created,
                refenced=decision.refenced,
                holds_admission=holds_admission,
            )
        except BaseException:
            if holds_admission:
                await self._release_admission(request.stepId)
            raise
        return accepted

    async def cancel(
        self,
        request: ExecutionCancelRequest,
    ) -> ExecutionCancelAccepted:
        decision = await self._journal.request_cancel(request)
        if decision.status == "accepted" and decision.entry is not None:
            async with self._lock:
                active = self._active.get(request.stepId)
                if (
                    active is not None
                    and active.job_id == request.jobId
                    and active.fencing_token == request.fencingToken
                ):
                    active.cancel_event.set()
                else:
                    self._spawn_cancel_terminal(request, decision.entry)
        return ExecutionCancelAccepted(
            protocolVersion="2.0",
            cancelRequestId=request.cancelRequestId,
            runId=request.runId,
            novelId=request.novelId,
            stepId=request.stepId,
            jobId=request.jobId,
            fencingToken=request.fencingToken,
            status=decision.status,
            acceptedAt=datetime.now(UTC),
        )

    async def health(self) -> ExecutionServiceHealth:
        async with self._admission_lock:
            admission_active = len(self._admitted_steps)
        admission_saturated = admission_active >= self._max_active_executions
        journal_health = await self._journal.health()
        try:
            backlog = await self._journal.backlog()
        except Exception:
            return ExecutionServiceHealth(
                ready=False,
                callback_pending=0,
                callback_rejected=0,
                error_code="EXECUTION_JOURNAL_UNAVAILABLE",
                admission_active=admission_active,
                admission_capacity=self._max_active_executions,
                admission_saturated=admission_saturated,
                journal_connected=journal_health.connected,
                journal_persistence_ok=journal_health.persistence_ok,
                journal_quarantined=journal_health.quarantined,
                journal_used_memory_bytes=journal_health.used_memory_bytes,
                journal_maxmemory_bytes=journal_health.maxmemory_bytes,
                journal_evicted_keys=journal_health.evicted_keys,
            )
        error_code = self._error_code or journal_health.error_code
        if (
            error_code is None
            and self._background_health_check is not None
            and not self._background_health_check()
        ):
            error_code = "EXECUTION_CALLBACK_REPLAYER_UNHEALTHY"
        if backlog.callback_rejected > 0:
            error_code = "EXECUTION_CALLBACK_REJECTED_BACKLOG"
        elif backlog.callback_pending > self._pending_backlog_limit:
            error_code = "EXECUTION_CALLBACK_PENDING_BACKLOG"
        return ExecutionServiceHealth(
            ready=error_code is None,
            callback_pending=backlog.callback_pending,
            callback_rejected=backlog.callback_rejected,
            error_code=error_code,
            admission_active=admission_active,
            admission_capacity=self._max_active_executions,
            admission_saturated=admission_saturated,
            journal_connected=journal_health.connected,
            journal_persistence_ok=journal_health.persistence_ok,
            journal_quarantined=journal_health.quarantined,
            journal_used_memory_bytes=journal_health.used_memory_bytes,
            journal_maxmemory_bytes=journal_health.maxmemory_bytes,
            journal_evicted_keys=journal_health.evicted_keys,
        )

    async def wait_idle(self) -> None:
        while True:
            async with self._lock:
                tasks = [active.task for active in self._active.values()]
            if not tasks:
                return
            await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self) -> None:
        self._closed = True
        async with self._lock:
            tasks = [active.task for active in self._active.values()]
            for task in tasks:
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _schedule(
        self,
        request: ExecutionStepRequest,
        resolved: ResolvedExecutionStep | None,
        *,
        entry: JournalEntry,
        created: bool,
        refenced: bool,
        holds_admission: bool,
    ) -> None:
        async with self._lock:
            current = self._active.get(request.stepId)
            if current is not None:
                if (
                    current.job_id == request.jobId
                    and current.fencing_token == request.fencingToken
                ):
                    if holds_admission:
                        await self._release_admission(request.stepId)
                    return
                holds_admission = holds_admission or current.holds_admission
                current.task.cancel()
                current.cancel_event.set()

            if entry.state in {"result", "failure"}:
                if entry.callback_delivery == "delivered":
                    if current is not None:
                        self._active.pop(request.stepId, None)
                    if holds_admission:
                        await self._release_admission(request.stepId)
                    return
                if entry.callback_delivery == "rejected" and not refenced:
                    if current is not None:
                        self._active.pop(request.stepId, None)
                    if holds_admission:
                        await self._release_admission(request.stepId)
                    return
                task = asyncio.create_task(self._replay_terminal(request.stepId))
            else:
                if resolved is None:
                    task = asyncio.create_task(
                        self._persist_unavailable_model(request, entry)
                    )
                else:
                    force_unknown = (
                        request.dispatchMode == "running_recovery" and created
                    ) or (
                        entry.state == "started"
                        and not _safe_started_recovery(entry, request, resolved)
                    )
                    task = asyncio.create_task(
                        self._execute(
                            request,
                            resolved,
                            resume_started=(
                                entry.state == "started" and not force_unknown
                            ),
                            force_outcome_unknown=force_unknown,
                        )
                    )
            active = _ActiveExecution(
                job_id=request.jobId,
                fencing_token=request.fencingToken,
                cancel_event=asyncio.Event(),
                task=task,
                holds_admission=holds_admission,
            )
            self._active[request.stepId] = active
            task.add_done_callback(partial(self._queue_cleanup, request.stepId))

    def _spawn_cancel_terminal(
        self,
        request: ExecutionCancelRequest,
        entry: JournalEntry,
    ) -> None:
        current = self._active.get(request.stepId)
        holds_admission = current.holds_admission if current is not None else False
        if current is not None:
            current.cancel_event.set()
            current.task.cancel()
        task = asyncio.create_task(self._cancel_without_request(request, entry))
        active = _ActiveExecution(
            job_id=request.jobId,
            fencing_token=request.fencingToken,
            cancel_event=asyncio.Event(),
            task=task,
            holds_admission=holds_admission,
        )
        self._active[request.stepId] = active
        task.add_done_callback(partial(self._queue_cleanup, request.stepId))

    def _queue_cleanup(
        self,
        step_id: str,
        task: asyncio.Task[None],
    ) -> None:
        asyncio.create_task(self._remove_active(step_id, task))

    async def _remove_active(
        self,
        step_id: str,
        task: asyncio.Task[None],
    ) -> None:
        holds_admission = False
        async with self._lock:
            current = self._active.get(step_id)
            if current is not None and current.task is task:
                self._active.pop(step_id, None)
                holds_admission = current.holds_admission
        if holds_admission:
            await self._release_admission(step_id)
        if task.cancelled():
            return
        try:
            error = task.exception()
        except asyncio.CancelledError:
            return
        if error is not None:
            self._error_code = "EXECUTION_BACKGROUND_TASK_FAILED"

    async def _release_admission(self, step_id: str) -> None:
        async with self._admission_lock:
            self._admitted_steps.discard(step_id)

    async def _execute(
        self,
        request: ExecutionStepRequest,
        resolved: ResolvedExecutionStep,
        *,
        resume_started: bool,
        force_outcome_unknown: bool,
    ) -> None:
        entry = await self._journal.require(request.stepId)
        if force_outcome_unknown:
            terminal = _failure_from_entry(
                entry,
                resolved.resolved_model,
                category="model_outcome_unknown",
                code="MODEL_OUTCOME_UNKNOWN",
                outcome_unknown=True,
                usage=_entry_unknown_usage(entry),
            )
            await self._journal.record_terminal(request, terminal)
            await self._deliver_terminal(terminal)
            return
        if entry.cancel_request_id is not None:
            terminal = _failure_from_entry(
                entry,
                resolved.resolved_model,
                category="cancelled",
                code="RUN_CANCELLED",
                outcome_unknown=False,
                usage=_entry_unknown_usage(entry),
                cancel_request_id=entry.cancel_request_id,
            )
            await self._journal.record_terminal(request, terminal)
            await self._deliver_terminal(terminal)
            return
        if not _resolved_model_available(resolved, self._executor):
            outcome_unknown = entry.provider_attempts > 0
            terminal = _failure_from_entry(
                entry,
                resolved.resolved_model,
                category=(
                    "model_outcome_unknown" if outcome_unknown else "provider_terminal"
                ),
                code=(
                    "MODEL_OUTCOME_UNKNOWN"
                    if outcome_unknown
                    else "MODEL_PROFILE_UNAVAILABLE"
                ),
                outcome_unknown=outcome_unknown,
                usage=_entry_unknown_usage(entry),
            )
            await self._journal.record_terminal(request, terminal)
            await self._deliver_terminal(terminal)
            return

        try:
            # 纯本地、无副作用的构造与输入/schema/budget 校验必须发生在
            # Core preparing 授权门之前；失败时 providerAttempts 保持 0。
            model_request = self._executor.build_model_request(request, resolved)
        except Exception:
            terminal = _failure_from_entry(
                entry,
                resolved.resolved_model,
                category="validation",
                code="STEP_INPUT_BUDGET_EXCEEDED",
                outcome_unknown=False,
                usage=_entry_unknown_usage(entry),
            )
            await self._journal.record_terminal(request, terminal)
            await self._deliver_terminal(terminal)
            return

        sequence = _ProgressSequence()
        started = monotonic()
        preparing = await self._send_progress(
            request,
            resolved_model=resolved.resolved_model,
            sequence=await sequence.next(),
            phase="preparing",
            elapsed_seconds=0,
            usage=_entry_unknown_usage(entry),
        )
        if preparing == "stale":
            await self._persist_stale_failure(request, resolved, entry)
            return
        if preparing == "retry_exhausted":
            # journal 保持 accepted；Core lease 到期后会以同一逻辑请求和新 fence 重派。
            return
        if preparing == "rejected":
            terminal = _failure_from_entry(
                entry,
                resolved.resolved_model,
                category="internal",
                code="EXECUTION_PROGRESS_REJECTED",
                outcome_unknown=False,
                usage=_entry_unknown_usage(entry),
            )
            await self._journal.record_terminal(request, terminal)
            await self._deliver_terminal(terminal)
            return
        if not resume_started:
            try:
                entry = await self._journal.mark_started(request)
            except ExecutionJournalCancelledError:
                entry = await self._journal.require(request.stepId)
                await self._persist_cancelled(request, resolved, entry)
                return

        waiting = await self._send_progress(
            request,
            resolved_model=resolved.resolved_model,
            sequence=await sequence.next(),
            phase="waiting_provider",
            elapsed_seconds=max(0, round(monotonic() - started)),
            usage=_entry_unknown_usage(entry),
        )
        if waiting != "accepted":
            if waiting == "stale":
                await self._persist_stale_failure(request, resolved, entry)
            elif waiting == "rejected":
                terminal = _failure_from_entry(
                    entry,
                    resolved.resolved_model,
                    category="internal",
                    code="EXECUTION_PROGRESS_REJECTED",
                    outcome_unknown=False,
                    usage=_entry_unknown_usage(entry),
                )
                await self._journal.record_terminal(request, terminal)
                await self._deliver_terminal(terminal)
            # retry_exhausted 保留 started/0-attempt；running_recovery 可安全首次尝试。
            return

        cancel_event = await self._cancel_event(request.stepId)
        stale_fence_event = asyncio.Event()
        progress_rejected_event = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._heartbeat(
                request,
                resolved_model=resolved.resolved_model,
                sequence=sequence,
                started=started,
                cancel_event=cancel_event,
                stale_fence_event=stale_fence_event,
                progress_rejected_event=progress_rejected_event,
            )
        )
        try:
            try:
                async def begin_provider_attempt() -> int:
                    await self._ensure_provider_side_effects_allowed()
                    return await self._journal.begin_provider_attempt(request)

                outcome = await self._executor.call_provider(
                    request,
                    model_request,
                    begin_attempt=begin_provider_attempt,
                    cancel_event=cancel_event,
                )
            except ExecutionJournalCancelledError:
                latest = await self._journal.require(request.stepId)
                await self._persist_cancelled(request, resolved, latest)
                return
            except ExecutionProviderGateClosed:
                # journal 保持 started；0 次尝试可安全首次恢复，已有尝试继续按
                # 供应商幂等/结果未知矩阵由 Core 租约恢复，不伪造终态。
                return
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

        latest = await self._journal.require(request.stepId)
        if stale_fence_event.is_set():
            await self._persist_stale_failure(request, resolved, latest)
            return
        if progress_rejected_event.is_set():
            if outcome.result is not None:
                # Provider 与 heartbeat 同时完成时保留已完整取得的真实结果。
                provider_terminal = self._executor.terminal_from_outcome(
                    request,
                    resolved,
                    replace(
                        outcome,
                        failure_category=None,
                        failure_code=None,
                        outcome_unknown=False,
                    ),
                )
                await self._journal.record_terminal(request, provider_terminal)
                await self._deliver_terminal(provider_terminal)
                return
            outcome_unknown = latest.provider_attempts > 0
            rejected_terminal = _failure_from_entry(
                latest,
                resolved.resolved_model,
                category=(
                    "model_outcome_unknown" if outcome_unknown else "internal"
                ),
                code=(
                    "MODEL_OUTCOME_UNKNOWN"
                    if outcome_unknown
                    else "EXECUTION_PROGRESS_REJECTED"
                ),
                outcome_unknown=outcome_unknown,
                usage=_entry_unknown_usage(latest),
            )
            await self._journal.record_terminal(request, rejected_terminal)
            await self._deliver_terminal(rejected_terminal)
            return
        computed_terminal = self._executor.terminal_from_outcome(
            request,
            resolved,
            outcome,
            cancel_request_id=latest.cancel_request_id,
        )
        try:
            stored = await self._journal.record_terminal(request, computed_terminal)
        except ExecutionJournalCancelledError:
            latest = await self._journal.require(request.stepId)
            computed_terminal = self._executor.terminal_from_outcome(
                request,
                resolved,
                outcome,
                cancel_request_id=latest.cancel_request_id,
            )
            stored = await self._journal.record_terminal(request, computed_terminal)
        persisted_terminal = stored.terminal
        if persisted_terminal is None:
            raise ExecutionJournalConflictError("V2 journal 终态缺少 payload")
        await self._send_progress(
            request,
            resolved_model=resolved.resolved_model,
            sequence=await sequence.next(),
            phase="validating",
            elapsed_seconds=max(0, round(monotonic() - started)),
            usage=persisted_terminal.usage,
        )
        await self._send_progress(
            request,
            resolved_model=resolved.resolved_model,
            sequence=await sequence.next(),
            phase="reporting",
            elapsed_seconds=max(0, round(monotonic() - started)),
            usage=persisted_terminal.usage,
        )
        await self._deliver_terminal(persisted_terminal)

    async def _heartbeat(
        self,
        request: ExecutionStepRequest,
        *,
        resolved_model: ResolvedModelRef,
        sequence: _ProgressSequence,
        started: float,
        cancel_event: asyncio.Event,
        stale_fence_event: asyncio.Event,
        progress_rejected_event: asyncio.Event,
    ) -> None:
        while not cancel_event.is_set():
            await asyncio.sleep(self._progress_interval_seconds)
            entry = await self._journal.require(request.stepId)
            delivery = await self._send_progress(
                request,
                resolved_model=resolved_model,
                sequence=await sequence.next(),
                phase="waiting_provider",
                elapsed_seconds=max(0, round(monotonic() - started)),
                usage=_entry_unknown_usage(entry),
            )
            if delivery == "stale":
                stale_fence_event.set()
                cancel_event.set()
                return
            if delivery == "rejected":
                progress_rejected_event.set()
                cancel_event.set()
                return

    async def _send_progress(
        self,
        request: ExecutionStepRequest,
        *,
        resolved_model: ResolvedModelRef,
        sequence: int,
        phase: Literal["preparing", "waiting_provider", "validating", "reporting"],
        elapsed_seconds: int,
        usage: StepUsage,
    ) -> Literal["accepted", "stale", "rejected", "retry_exhausted"]:
        progress = ExecutionStepProgress(
            protocolVersion="2.0",
            progressId=_progress_id(request, sequence, phase),
            jobId=request.jobId,
            runId=request.runId,
            novelId=request.novelId,
            stepId=request.stepId,
            fencingToken=request.fencingToken,
            requestHash=request.requestHash,
            resolvedModel=resolved_model,
            sequence=sequence,
            phase=phase,
            progressCode=f"execution.{phase}",
            elapsedSeconds=elapsed_seconds,
            waitingOnProvider=phase == "waiting_provider",
            usage=usage,
            occurredAt=datetime.now(UTC),
        )
        for attempt in range(1, self._progress_attempts + 1):
            try:
                receipt = await self._callbacks.send_progress(progress)
            except ExecutionCallbackError as exc:
                if not exc.retryable:
                    return "rejected"
                if attempt == self._progress_attempts:
                    return "retry_exhausted"
                await asyncio.sleep(self._callback_delay(attempt))
                continue
            return "stale" if receipt.status == "stale" else "accepted"
        return "retry_exhausted"

    async def _persist_unavailable_model(
        self,
        request: ExecutionStepRequest,
        entry: JournalEntry,
    ) -> None:
        try:
            resolved_model = ResolvedModelRef.model_validate(entry.resolved_model)
        except ValidationError as exc:
            raise ExecutionJournalConflictError("V2 journal 解析模型损坏") from exc
        outcome_unknown = entry.provider_attempts > 0
        terminal = _failure_from_entry(
            entry,
            resolved_model,
            category=(
                "model_outcome_unknown" if outcome_unknown else "provider_terminal"
            ),
            code=(
                "MODEL_OUTCOME_UNKNOWN"
                if outcome_unknown
                else "MODEL_PROFILE_UNAVAILABLE"
            ),
            outcome_unknown=outcome_unknown,
            usage=_entry_unknown_usage(entry),
        )
        await self._journal.record_terminal(request, terminal)
        await self._deliver_terminal(terminal)

    async def _deliver_terminal(self, terminal: TerminalPayload) -> None:
        entry = await self._journal.require(terminal.stepId)
        if entry.callback_delivery == "delivered":
            return
        if entry.callback_delivery == "rejected":
            return
        if await self._journal.is_restore_quarantined():
            # provider in-flight 可能在 restore marker 之后才完成；终态已经
            # 耐久落入 pending，此时不得再产生任何 terminal HTTP 副作用。
            return
        self._callback_replayer.wake()
        await self._callback_replayer.deliver_immediately(
            terminal.stepId,
            max_attempts=self._terminal_callback_attempts,
        )

    async def _replay_terminal(self, step_id: str) -> None:
        entry = await self._journal.require(step_id)
        terminal = entry.terminal
        if terminal is None:
            raise ExecutionJournalConflictError("V2 journal 终态缺少 payload")
        await self._deliver_terminal(terminal)

    async def _cancel_without_request(
        self,
        request: ExecutionCancelRequest,
        entry: JournalEntry,
    ) -> None:
        resolved_model = ResolvedModelRef.model_validate(entry.resolved_model)
        terminal = _failure_from_entry(
            entry,
            resolved_model,
            category="cancelled",
            code="RUN_CANCELLED",
            outcome_unknown=False,
            usage=_entry_unknown_usage(entry),
            cancel_request_id=request.cancelRequestId,
        )
        stored = await self._journal.record_terminal(
            _request_identity_from_cancel(request, entry),
            terminal,
        )
        persisted_terminal = stored.terminal
        if persisted_terminal is None:
            raise ExecutionJournalConflictError("V2 journal 取消终态缺少 payload")
        await self._deliver_terminal(persisted_terminal)

    async def _persist_cancelled(
        self,
        request: ExecutionStepRequest,
        resolved: ResolvedExecutionStep,
        entry: JournalEntry,
    ) -> None:
        terminal = _failure_from_entry(
            entry,
            resolved.resolved_model,
            category="cancelled",
            code="RUN_CANCELLED",
            outcome_unknown=False,
            usage=_entry_unknown_usage(entry),
            cancel_request_id=entry.cancel_request_id,
        )
        await self._journal.record_terminal(request, terminal)
        await self._deliver_terminal(terminal)

    async def _persist_stale_failure(
        self,
        request: ExecutionStepRequest,
        resolved: ResolvedExecutionStep,
        entry: JournalEntry,
    ) -> None:
        terminal = _failure_from_entry(
            entry,
            resolved.resolved_model,
            category="internal",
            code="STALE_EXECUTION_FENCE",
            outcome_unknown=False,
            usage=_entry_unknown_usage(entry),
        )
        await self._journal.record_terminal(request, terminal)
        await self._deliver_terminal(terminal)

    async def _cancel_event(self, step_id: str) -> asyncio.Event:
        async with self._lock:
            active = self._active.get(step_id)
            if active is None:
                raise ExecutionJournalConflictError("V2 active execution 不存在")
            return active.cancel_event

    def _callback_delay(self, attempt: int) -> float:
        return float(min(30.0, self._callback_retry_base_seconds * (2 ** (attempt - 1))))

    async def _ensure_provider_side_effects_allowed(self) -> None:
        try:
            await self._ensure_callback_and_journal_gate()
        except (ExecutionJournalError, ExecutionServiceUnavailableError) as exc:
            code = (
                exc.code
                if isinstance(exc, ExecutionServiceUnavailableError)
                else str(exc)
            )
            raise ExecutionProviderGateClosed(code) from None

    async def _ensure_callback_and_journal_gate(self) -> None:
        await self._journal.ensure_available()
        backlog = await self._journal.backlog()
        if self._error_code is not None:
            raise ExecutionServiceUnavailableError(self._error_code)
        if (
            self._background_health_check is not None
            and not self._background_health_check()
        ):
            raise ExecutionServiceUnavailableError(
                "EXECUTION_CALLBACK_REPLAYER_UNHEALTHY"
            )
        if backlog.callback_rejected > 0:
            raise ExecutionServiceUnavailableError(
                "EXECUTION_CALLBACK_REJECTED_BACKLOG"
            )
        if backlog.callback_pending > self._pending_backlog_limit:
            raise ExecutionServiceUnavailableError(
                "EXECUTION_CALLBACK_PENDING_BACKLOG"
            )


def _safe_started_recovery(
    entry: JournalEntry,
    request: ExecutionStepRequest,
    resolved: ResolvedExecutionStep,
) -> bool:
    if request.dispatchMode != "running_recovery":
        return False
    if entry.provider_attempts == 0:
        # journal started 已持久化但 attempt AOF 尚不存在，证明没有供应商副作用；
        # 即使 Provider 不支持幂等，也可以执行第一次尝试。
        return entry.provider_idempotency_key is None
    return (
        resolved.resolved_model.supportsRequestIdempotency
        and entry.provider_idempotency_key == request.idempotencyKey
    )


def _resolved_model_available(
    resolved: ResolvedExecutionStep,
    executor: StatelessExecutionStepExecutor,
) -> bool:
    return executor.matches_resolved_model(
        resolved.resolved_model,
        resolved.profile,
    )


def _entry_unknown_usage(entry: JournalEntry) -> StepUsage:
    elapsed = 0
    if entry.provider_started_at is not None:
        elapsed = max(
            0,
            round(
                (datetime.now(UTC) - entry.provider_started_at).total_seconds()
                * 1000
            ),
        )
    return StepUsage(
        usageStatus="unknown",
        providerAttempts=entry.provider_attempts,
        protocolCorrections=0,
        wallTimeMillis=elapsed,
    )


def _failure_from_entry(
    entry: JournalEntry,
    resolved_model: ResolvedModelRef,
    *,
    category: FailureCategory,
    code: str,
    outcome_unknown: bool,
    usage: StepUsage,
    cancel_request_id: str | None = None,
) -> ExecutionStepFailure:
    payload: dict[str, object] = {
        "errorCategory": category,
        "errorCode": code,
        "outcomeUnknown": outcome_unknown,
        "retryable": False,
        "resolvedModel": resolved_model.model_dump(mode="json", exclude_none=True),
        "usage": usage.model_dump(mode="json", exclude_none=True),
    }
    if cancel_request_id is not None:
        payload["cancelRequestId"] = cancel_request_id
    return ExecutionStepFailure(
        protocolVersion="2.0",
        jobId=entry.job_id,
        runId=entry.run_id,
        novelId=entry.novel_id,
        stepId=entry.step_id,
        fencingToken=entry.fencing_token,
        requestHash=entry.request_hash,
        inputHash=entry.input_hash,
        resolvedModel=resolved_model,
        errorCategory=category,
        errorCode=code,
        retryable=False,
        outcomeUnknown=outcome_unknown,
        cancelRequestId=cancel_request_id,
        resultHash=canonical_execution_sha256(payload),
        usage=usage,
        failedAt=datetime.now(UTC),
    )


def _progress_id(
    request: ExecutionStepRequest,
    sequence: int,
    phase: str,
) -> str:
    digest = hashlib.sha256(
        f"{request.stepId}:{request.fencingToken}:{sequence}:{phase}".encode()
    ).hexdigest()[:32]
    return f"progress-{digest}"


def _request_identity_from_cancel(
    cancel: ExecutionCancelRequest,
    entry: JournalEntry,
) -> ExecutionStepRequest:
    """只供 journal 终态 CAS；绝不用于模型执行或重建缺失请求正文。"""

    return ExecutionStepRequest.model_construct(
        protocolVersion="2.0",
        jobId=cancel.jobId,
        runId=cancel.runId,
        novelId=cancel.novelId,
        stepId=cancel.stepId,
        fencingToken=cancel.fencingToken,
        requestHash=cancel.requestHash,
        inputHash=entry.input_hash,
    )
