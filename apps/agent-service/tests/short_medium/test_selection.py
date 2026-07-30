from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import pytest
from inkforge_agents.jobs.short_medium import ShortMediumWritingJobHandler
from inkforge_agents.providers.base import ModelTurnResult, ModelUsage
from inkforge_agents.queue.repository import QueueJob

from .test_graph import Core


class Generator:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def generate(self, resource: object, request: Any) -> ModelTurnResult:
        del resource
        self.requests.append(request)
        return ModelTurnResult(
            content="替换文字",
            toolCalls=[],
            finishReason="stop",
            rawFinishReason="stop",
            usage=ModelUsage(promptTokens=1, completionTokens=4, totalTokens=5),
        )


@pytest.mark.asyncio
async def test_selection_prompt_and_result_never_include_full_document_field() -> None:
    core = Core()
    generator = Generator()
    handler = ShortMediumWritingJobHandler(core, generator)
    selected_text = "旧文字"
    job = QueueJob(
        jobId="job-short-1",
        kind="writing",
        runId="run-short-1",
        taskId="task-short-1",
        novelId="novel-1",
        userId="user-1",
        priority=10,
        payload={
            "workflow": "short_medium",
            "operation": "replace_selection",
            "documentType": "manuscript",
            "chapterId": "chapter-1",
            "baseVersionId": "version-1",
            "baseContentHash": "a" * 64,
            "sourceOutlineVersionId": "outline-version-1",
            "selectionStart": 1,
            "selectionEnd": 3,
            "selectedText": selected_text,
            "selectedTextHash": hashlib.sha256(
                selected_text.encode("utf-8")
            ).hexdigest(),
            "contextBefore": "之前",
            "contextAfter": "之后",
            "userInstruction": "加强冲突",
        },
        createdAt=datetime.now(UTC),
    )

    await handler(job)

    prompt = "\n".join(message.content for message in generator.requests[0].messages)
    assert "只返回替换文本" in prompt
    assert "单中心冲突" in prompt
    assert "压缩人物和线索" in prompt
    assert "结尾兑现" in prompt
    result = core.completions[0][2]
    assert result["replacement"] == "替换文字"
    assert "content" not in result
