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
    async def generate(self, resource: object, source_text: str) -> dict[str, str]:
        del resource
        assert source_text == "完整参考正文"
        return {
            "creativeMethodology": "方法",
            "uniqueMarkers": "标记",
            "generationStyle": "风格",
            "expressionFeatures": "表达",
            "styleTraits": "特质",
        }


@pytest.mark.asyncio
async def test_portrait_job_uses_full_source_and_reports_all_sections() -> None:
    core = Core()
    handler = PortraitJobHandler(core, Generator())
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
