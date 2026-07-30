from __future__ import annotations

from datetime import UTC, datetime

import pytest
from inkforge_agents.jobs.short_medium import WritingJobDispatcher
from inkforge_agents.queue.repository import QueueJob


def _job(workflow: str | None) -> QueueJob:
    payload = {} if workflow is None else {"workflow": workflow}
    return QueueJob(
        jobId="job-1",
        kind="writing",
        runId="run-1",
        taskId="task-1",
        novelId="novel-1",
        userId="user-1",
        priority=10,
        payload=payload,
        createdAt=datetime.now(UTC),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("workflow", [None, "long_serial"])
async def test_dispatcher_keeps_existing_writing_path(workflow: str | None) -> None:
    called: list[str] = []

    async def long_handler(job: QueueJob) -> None:
        called.append(f"long:{job.jobId}")

    async def short_handler(job: QueueJob) -> None:
        called.append(f"short:{job.jobId}")

    dispatcher = WritingJobDispatcher(long_handler, short_handler)
    await dispatcher(_job(workflow))

    assert called == ["long:job-1"]


@pytest.mark.asyncio
async def test_dispatcher_routes_short_medium_without_entering_long_graph() -> None:
    called: list[str] = []

    async def long_handler(job: QueueJob) -> None:
        called.append(f"long:{job.jobId}")

    async def short_handler(job: QueueJob) -> None:
        called.append(f"short:{job.jobId}")

    dispatcher = WritingJobDispatcher(long_handler, short_handler)
    await dispatcher(_job("short_medium"))

    assert called == ["short:job-1"]

