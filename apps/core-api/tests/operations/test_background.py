from __future__ import annotations

import asyncio

import pytest
from inkforge_core.operations.background import BackgroundTaskRegistry


class Worker:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    async def run(self) -> None:
        self.started.set()
        await self.stopped.wait()

    def request_stop(self) -> None:
        self.stopped.set()


@pytest.mark.asyncio
async def test_background_registry_reports_only_running_tasks_as_ready() -> None:
    worker = Worker()
    registry = BackgroundTaskRegistry()
    registry.start("测试任务", worker.run, worker.request_stop)
    await worker.started.wait()

    assert registry.is_ready() is True

    worker.request_stop()
    await asyncio.sleep(0)
    assert registry.is_ready() is False
    await registry.stop_all()


@pytest.mark.asyncio
async def test_background_registry_reports_crashed_task_as_not_ready() -> None:
    class CrashedWorker:
        async def run(self) -> None:
            raise RuntimeError("模拟后台任务崩溃")

        def request_stop(self) -> None:
            pass

    registry = BackgroundTaskRegistry()
    worker = CrashedWorker()
    registry.start("崩溃任务", worker.run, worker.request_stop)
    for _ in range(100):
        if registry.error_code("崩溃任务") == "BACKGROUND_TASK_BACKOFF":
            break
        await asyncio.sleep(0)

    assert registry.is_ready() is False
    assert registry.error_codes() == {
        "崩溃任务": "BACKGROUND_TASK_BACKOFF",
    }
    await registry.stop_all()


@pytest.mark.asyncio
async def test_background_registry_restarts_crashed_worker_without_overlap() -> None:
    class FlakyWorker:
        def __init__(self) -> None:
            self.starts = 0
            self.active = 0
            self.maximum_active = 0
            self.restarted = asyncio.Event()
            self.stopped = asyncio.Event()

        async def run(self) -> None:
            self.starts += 1
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            try:
                if self.starts == 1:
                    raise RuntimeError("模拟首次崩溃")
                self.restarted.set()
                await self.stopped.wait()
            finally:
                self.active -= 1

        def request_stop(self) -> None:
            self.stopped.set()

    worker = FlakyWorker()
    registry = BackgroundTaskRegistry(
        backoff_base=0.001,
        backoff_max=0.002,
        stability_window=0.01,
    )
    registry.start("可恢复任务", worker.run, worker.request_stop)

    await asyncio.wait_for(worker.restarted.wait(), timeout=1)

    assert worker.starts == 2
    assert worker.maximum_active == 1
    assert registry.is_ready() is True
    await registry.stop_all()


@pytest.mark.asyncio
async def test_background_registry_is_not_ready_during_restart_backoff() -> None:
    first_crash = asyncio.Event()

    async def crash() -> None:
        first_crash.set()
        raise RuntimeError("模拟持续崩溃")

    registry = BackgroundTaskRegistry(
        backoff_base=0.05,
        backoff_max=0.05,
        stability_window=0.01,
    )
    registry.start("退避任务", crash, lambda: None)
    await asyncio.wait_for(first_crash.wait(), timeout=1)
    await asyncio.sleep(0)

    assert registry.is_ready() is False
    assert registry.error_code("退避任务") == "BACKGROUND_TASK_BACKOFF"
    await registry.stop_all()


@pytest.mark.asyncio
async def test_background_registry_shutdown_does_not_restart_worker() -> None:
    worker = Worker()
    starts = 0

    async def run() -> None:
        nonlocal starts
        starts += 1
        await worker.run()

    registry = BackgroundTaskRegistry(
        backoff_base=0.001,
        backoff_max=0.002,
        stability_window=0.01,
    )
    registry.start("关闭任务", run, worker.request_stop)
    await worker.started.wait()

    await registry.stop_all()
    await asyncio.sleep(0.01)

    assert starts == 1
    assert registry.is_ready() is False


@pytest.mark.asyncio
async def test_background_registry_recovers_readiness_after_stability_window() -> None:
    starts = 0
    restarted = asyncio.Event()
    stopped = asyncio.Event()

    async def run() -> None:
        nonlocal starts
        starts += 1
        if starts == 1:
            raise RuntimeError("模拟首次崩溃")
        restarted.set()
        await stopped.wait()

    registry = BackgroundTaskRegistry(
        backoff_base=0.001,
        backoff_max=0.002,
        stability_window=0.02,
        unhealthy_failure_threshold=1,
    )
    registry.start("稳定恢复任务", run, stopped.set)
    try:
        await asyncio.wait_for(restarted.wait(), timeout=1)

        assert registry.is_ready() is False
        await asyncio.sleep(0.03)
        assert registry.is_ready() is True
    finally:
        await registry.stop_all()
