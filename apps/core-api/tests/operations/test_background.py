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
    registry.start("测试任务", worker)
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
    registry.start("崩溃任务", CrashedWorker())
    await asyncio.sleep(0)

    assert registry.is_ready() is False
    await registry.stop_all()
