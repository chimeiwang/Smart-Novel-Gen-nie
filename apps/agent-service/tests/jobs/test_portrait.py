from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from inkforge_agents.clients.core import RunResource
from inkforge_agents.jobs.portrait import ModelPortraitGenerator, PortraitJobHandler
from inkforge_agents.providers.base import ModelTurnResult, ModelUsage
from inkforge_agents.queue.repository import QueueJob
from inkforge_agents.runtime.model_runtime import ModelRuntime


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

    async def generate(
        self,
        resource: object,
        source_text: str,
        section: str | None = None,
    ) -> dict[str, str]:
        del resource
        assert section is None
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
        payload={"styleId": "style-1", "section": None},
        createdAt=datetime.now(UTC),
    )

    await handler(job)

    assert core.processing is True
    assert core.result == {
        "mode": "full",
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


class Provider:
    billable = False
    provider_name = "fake"
    model_name = "fake"

    def __init__(self) -> None:
        self.requests = []

    async def complete_turn(self, request):
        self.requests.append(request)
        return ModelTurnResult(
            content="单节结果",
            toolCalls=[],
            usage=ModelUsage(
                promptTokens=1,
                completionTokens=1,
                totalTokens=2,
            ),
        )


@pytest.mark.asyncio
async def test_model_portrait_generator_calls_only_requested_section() -> None:
    provider = Provider()
    generator = ModelPortraitGenerator(ModelRuntime(provider))
    resource = RunResource(
        userId="user-1",
        novelId="style:style-1",
        taskId="task-1",
        runId="task-1",
    )

    result = await generator.generate(resource, "完整参考正文", section="uniqueMarkers")

    assert result == {"uniqueMarkers": "单节结果"}
    assert len(provider.requests) == 1
    assert "独特标记" in provider.requests[0].messages[1].content


class SectionGenerator:
    async def generate(
        self,
        resource: object,
        source_text: str,
        section: str | None = None,
    ) -> dict[str, str]:
        del resource
        assert source_text == "完整参考正文"
        assert section == "uniqueMarkers"
        return {"uniqueMarkers": "新标记"}


@pytest.mark.asyncio
async def test_portrait_job_reports_discriminated_section_result() -> None:
    core = Core()
    handler = PortraitJobHandler(core, SectionGenerator())
    job = QueueJob(
        jobId="portrait-task-1",
        kind="portrait",
        runId="task-1",
        taskId="task-1",
        novelId="style:style-1",
        userId="user-1",
        priority=20,
        payload={"styleId": "style-1", "section": "uniqueMarkers"},
        createdAt=datetime.now(UTC),
    )

    await handler(job)

    assert core.result == {
        "mode": "section",
        "section": "uniqueMarkers",
        "content": "新标记",
        "originalCharCount": 6,
        "usedCharCount": 6,
        "truncated": False,
    }
