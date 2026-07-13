from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from inkforge_agents.jobs.portrait import PortraitJobHandler
from inkforge_agents.queue.repository import QueueJob


class Core:
    def __init__(self) -> None:
        self.processing = False
        self.result: dict[str, Any] | None = None

    async def get_portrait_context(self, resource: object, style_id: str) -> dict[str, Any]:
        del resource
        assert style_id == "style-1"
        return {"sourceText": "完整参考正文", "originalCharCount": 6}

    async def mark_portrait_processing(self, resource: object, style_id: str) -> None:
        del resource, style_id
        self.processing = True

    async def complete_portrait(
        self, resource: object, style_id: str, result: dict[str, Any]
    ) -> None:
        del resource, style_id
        self.result = result

    async def fail_portrait(self, *args: object, **kwargs: object) -> None:
        raise AssertionError((args, kwargs))


class Generator:
    def __init__(self, workflow_log: WorkflowLog) -> None:
        self._workflow_log = workflow_log

    async def generate(self, resource: object, source_text: str) -> dict[str, str]:
        del resource
        assert self._workflow_log.entries[0][0] == "开始"
        assert source_text == "完整参考正文"
        return {
            "creativeMethodology": "方法",
            "uniqueMarkers": "标记",
            "generationStyle": "风格",
            "expressionFeatures": "表达",
            "styleTraits": "特质",
        }


class WorkflowLog:
    def __init__(self) -> None:
        self.entries: list[tuple[str, object]] = []

    def start_run(self, **metadata: object) -> None:
        self.entries.append(("开始", metadata))

    def finish_run(self, run_id: str, status: str) -> None:
        self.entries.append(("结束", (run_id, status)))


@pytest.mark.asyncio
async def test_portrait_job_uses_full_source_and_reports_all_sections() -> None:
    core = Core()
    workflow_log = WorkflowLog()
    handler = PortraitJobHandler(
        core,
        Generator(workflow_log),
        workflow_log=workflow_log,
    )
    job = QueueJob(
        jobId="portrait-task-1",
        kind="portrait",
        runId="task-1",
        taskId="task-1",
        novelId="style:style-1",
        userId="user-1",
        priority=20,
        payload={"styleId": "style-1"},
        createdAt=datetime.now(UTC),
    )

    await handler(job)

    assert core.processing is True
    assert core.result == {
        "creativeMethodology": "方法",
        "uniqueMarkers": "标记",
        "generationStyle": "风格",
        "expressionFeatures": "表达",
        "styleTraits": "特质",
        "originalCharCount": 6,
        "usedCharCount": 6,
        "truncated": False,
    }
    assert workflow_log.entries == [
        (
            "开始",
            {
                "run_id": "task-1",
                "task_id": "task-1",
                "run_kind": "文风画像",
                "user_id": "user-1",
                "novel_id": "style:style-1",
                "chapter_id": None,
            },
        ),
        ("结束", ("task-1", "完成")),
    ]
