from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Literal, Protocol

logger = logging.getLogger(__name__)

BackgroundState = Literal["starting", "running", "backoff", "stopped"]
CoroutineFactory = Callable[[], Coroutine[Any, Any, None]]
StopCallback = Callable[[], None]


class BackgroundWorker(Protocol):
    async def run(self) -> None: ...

    def request_stop(self) -> None: ...


@dataclass(slots=True)
class BackgroundTaskRegistration:
    name: str
    coroutine_factory: CoroutineFactory
    request_stop: StopCallback
    supervisor_task: asyncio.Task[None] | None = None
    inner_task: asyncio.Task[None] | None = None
    state: BackgroundState = "starting"
    consecutive_failures: int = 0
    stop_requested: bool = False


class BackgroundTaskRegistry:
    def __init__(
        self,
        *,
        backoff_base: float = 1.0,
        backoff_max: float = 30.0,
        stability_window: float = 60.0,
        unhealthy_failure_threshold: int = 3,
    ) -> None:
        if (
            backoff_base <= 0
            or backoff_max < backoff_base
            or stability_window <= 0
            or unhealthy_failure_threshold < 1
        ):
            raise ValueError("后台监督器配置无效")
        self._items: dict[str, BackgroundTaskRegistration] = {}
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._stability_window = stability_window
        self._unhealthy_failure_threshold = unhealthy_failure_threshold
        self._stopping = False
        self._stop_event = asyncio.Event()

    def start(
        self,
        name: str,
        coroutine_factory: CoroutineFactory,
        request_stop: StopCallback,
    ) -> None:
        if self._stopping:
            raise RuntimeError("后台监督器正在停止")
        if name in self._items:
            raise ValueError(f"后台任务已注册：{name}")
        registration = BackgroundTaskRegistration(
            name=name,
            coroutine_factory=coroutine_factory,
            request_stop=request_stop,
        )
        registration.supervisor_task = asyncio.create_task(
            self._supervise(registration),
            name=f"inkforge:{name}:supervisor",
        )
        self._items[name] = registration

    def is_ready(self) -> bool:
        return bool(self._items) and all(
            self._registration_is_ready(item) for item in self._items.values()
        )

    def error_code(self, name: str) -> str | None:
        item = self._items.get(name)
        if item is None:
            return "BACKGROUND_TASK_NOT_REGISTERED"
        if self._registration_is_ready(item):
            return None
        if item.state == "backoff":
            return "BACKGROUND_TASK_BACKOFF"
        if item.consecutive_failures >= self._unhealthy_failure_threshold:
            return "BACKGROUND_TASK_REPEATED_FAILURE"
        if item.supervisor_task is not None and item.supervisor_task.done():
            return "BACKGROUND_SUPERVISOR_STOPPED"
        return "BACKGROUND_TASK_NOT_RUNNING"

    def error_codes(self) -> dict[str, str]:
        errors: dict[str, str] = {}
        for name in self._items:
            error_code = self.error_code(name)
            if error_code is not None:
                errors[name] = error_code
        return errors

    async def stop_all(self) -> None:
        self._stopping = True
        self._stop_event.set()
        for item in self._items.values():
            item.stop_requested = True
            try:
                item.request_stop()
            except Exception:
                logger.exception(
                    "请求后台任务停止时发生异常",
                    extra={
                        "backgroundTaskName": item.name,
                        "errorCode": "BACKGROUND_STOP_FAILED",
                    },
                )
        tasks = [
            item.supervisor_task
            for item in self._items.values()
            if item.supervisor_task is not None
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _registration_is_ready(self, item: BackgroundTaskRegistration) -> bool:
        return (
            not self._stopping
            and item.state == "running"
            and item.consecutive_failures < self._unhealthy_failure_threshold
            and item.supervisor_task is not None
            and not item.supervisor_task.done()
            and item.inner_task is not None
            and not item.inner_task.done()
        )

    async def _supervise(self, item: BackgroundTaskRegistration) -> None:
        while not self._stopping and not item.stop_requested:
            item.state = "running"
            started_at = asyncio.get_running_loop().time()
            error_code = "BACKGROUND_TASK_RETURNED"
            try:
                item.inner_task = asyncio.create_task(
                    item.coroutine_factory(),
                    name=f"inkforge:{item.name}:worker",
                )
                done, _ = await asyncio.wait(
                    {item.inner_task},
                    timeout=self._stability_window,
                )
                if not done:
                    item.consecutive_failures = 0
                await item.inner_task
            except asyncio.CancelledError:
                if item.inner_task is not None and not item.inner_task.done():
                    item.inner_task.cancel()
                    await asyncio.gather(item.inner_task, return_exceptions=True)
                raise
            except Exception as exc:
                error_code = type(exc).__name__
            finally:
                ran_for = asyncio.get_running_loop().time() - started_at
                item.inner_task = None

            if self._stopping or item.stop_requested:
                item.state = "stopped"
                return

            if ran_for >= self._stability_window:
                item.consecutive_failures = 0
            item.consecutive_failures += 1
            item.state = "backoff"
            delay = min(
                self._backoff_base * (2 ** min(item.consecutive_failures - 1, 10)),
                self._backoff_max,
            )
            logger.error(
                "后台任务意外结束，等待监督器重启",
                extra={
                    "backgroundTaskName": item.name,
                    "errorCode": error_code,
                    "consecutiveFailures": item.consecutive_failures,
                    "retryDelaySeconds": delay,
                },
            )
            await self._wait_or_stop(delay)

        item.state = "stopped"

    async def _wait_or_stop(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass
