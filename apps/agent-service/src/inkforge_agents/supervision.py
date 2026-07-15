from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any, Literal

logger = logging.getLogger(__name__)

SupervisorState = Literal["starting", "running", "backoff", "stopped"]
CoroutineFactory = Callable[[], Coroutine[Any, Any, None]]
StopCallback = Callable[[], None]


class CoroutineSupervisor:
    def __init__(
        self,
        *,
        name: str,
        coroutine_factory: CoroutineFactory,
        request_stop: StopCallback,
        backoff_base: float = 1.0,
        backoff_max: float = 30.0,
        stability_window: float = 60.0,
        unhealthy_failure_threshold: int = 3,
    ) -> None:
        if (
            not name
            or backoff_base <= 0
            or backoff_max < backoff_base
            or stability_window <= 0
            or unhealthy_failure_threshold < 1
        ):
            raise ValueError("协程监督器配置无效")
        self._name = name
        self._coroutine_factory = coroutine_factory
        self._request_stop = request_stop
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._stability_window = stability_window
        self._unhealthy_failure_threshold = unhealthy_failure_threshold
        self._state: SupervisorState = "starting"
        self._consecutive_failures = 0
        self._stop_requested = False
        self._stop_event = asyncio.Event()
        self._supervisor_task: asyncio.Task[None] | None = None
        self._inner_task: asyncio.Task[None] | None = None

    @property
    def task(self) -> asyncio.Task[None] | None:
        return self._supervisor_task

    @property
    def error_code(self) -> str | None:
        if self.is_ready():
            return None
        if self._state == "backoff":
            return "BACKGROUND_TASK_BACKOFF"
        if self._consecutive_failures >= self._unhealthy_failure_threshold:
            return "BACKGROUND_TASK_REPEATED_FAILURE"
        if self._supervisor_task is not None and self._supervisor_task.done():
            return "BACKGROUND_SUPERVISOR_STOPPED"
        return "BACKGROUND_TASK_NOT_RUNNING"

    def start(self) -> None:
        if self._supervisor_task is not None:
            raise RuntimeError(f"后台任务已启动：{self._name}")
        if self._stop_requested:
            raise RuntimeError(f"后台任务已停止：{self._name}")
        self._supervisor_task = asyncio.create_task(
            self._supervise(),
            name=f"inkforge:{self._name}:supervisor",
        )

    def is_ready(self) -> bool:
        return (
            not self._stop_requested
            and self._state == "running"
            and self._consecutive_failures < self._unhealthy_failure_threshold
            and self._supervisor_task is not None
            and not self._supervisor_task.done()
            and self._inner_task is not None
            and not self._inner_task.done()
        )

    async def stop(self) -> None:
        self._stop_requested = True
        self._stop_event.set()
        try:
            self._request_stop()
        except Exception:
            logger.exception(
                "请求后台任务停止时发生异常",
                extra={
                    "backgroundTaskName": self._name,
                    "errorCode": "BACKGROUND_STOP_FAILED",
                },
            )
        if self._supervisor_task is not None:
            await asyncio.gather(self._supervisor_task, return_exceptions=True)

    async def _supervise(self) -> None:
        while not self._stop_requested:
            self._state = "running"
            started_at = asyncio.get_running_loop().time()
            error_code = "BACKGROUND_TASK_RETURNED"
            try:
                self._inner_task = asyncio.create_task(
                    self._coroutine_factory(),
                    name=f"inkforge:{self._name}:worker",
                )
                done, _ = await asyncio.wait(
                    {self._inner_task},
                    timeout=self._stability_window,
                )
                if not done:
                    self._consecutive_failures = 0
                await self._inner_task
            except asyncio.CancelledError:
                if self._inner_task is not None and not self._inner_task.done():
                    self._inner_task.cancel()
                    await asyncio.gather(self._inner_task, return_exceptions=True)
                raise
            except Exception as exc:
                error_code = type(exc).__name__
            finally:
                ran_for = asyncio.get_running_loop().time() - started_at
                self._inner_task = None

            if self._stop_requested:
                self._state = "stopped"
                return

            if ran_for >= self._stability_window:
                self._consecutive_failures = 0
            self._consecutive_failures += 1
            self._state = "backoff"
            delay = min(
                self._backoff_base
                * (2 ** min(self._consecutive_failures - 1, 10)),
                self._backoff_max,
            )
            logger.error(
                "后台任务意外结束，等待监督器重启",
                extra={
                    "backgroundTaskName": self._name,
                    "errorCode": error_code,
                    "consecutiveFailures": self._consecutive_failures,
                    "retryDelaySeconds": delay,
                },
            )
            await self._wait_or_stop(delay)

        self._state = "stopped"

    async def _wait_or_stop(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass
