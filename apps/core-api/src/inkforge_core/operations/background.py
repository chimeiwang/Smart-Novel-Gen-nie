from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol


class BackgroundWorker(Protocol):
    async def run(self) -> None: ...

    def request_stop(self) -> None: ...


@dataclass(frozen=True, slots=True)
class BackgroundTaskRegistration:
    name: str
    worker: BackgroundWorker
    task: asyncio.Task[None]


class BackgroundTaskRegistry:
    def __init__(self) -> None:
        self._items: dict[str, BackgroundTaskRegistration] = {}

    def start(self, name: str, worker: BackgroundWorker) -> None:
        if name in self._items:
            raise ValueError(f"后台任务已注册：{name}")
        self._items[name] = BackgroundTaskRegistration(
            name=name,
            worker=worker,
            task=asyncio.create_task(worker.run(), name=f"inkforge:{name}"),
        )

    def is_ready(self) -> bool:
        return bool(self._items) and all(not item.task.done() for item in self._items.values())

    async def stop_all(self) -> None:
        for item in self._items.values():
            item.worker.request_stop()
        if self._items:
            await asyncio.gather(
                *(item.task for item in self._items.values()),
                return_exceptions=True,
            )
