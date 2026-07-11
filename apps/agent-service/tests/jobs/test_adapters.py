from __future__ import annotations

from typing import Any

import pytest
from inkforge_agents.jobs.adapters import CoreArtifactPort, CoreToolGateway
from inkforge_agents.tools.registry import ToolContext


class CoreClient:
    def __init__(self) -> None:
        self.tools: list[tuple[str, str, dict[str, object]]] = []
        self.artifacts: list[dict[str, Any]] = []

    async def call_tool(
        self,
        resource: object,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, Any]:
        del resource
        self.tools.append((agent_id, tool_name, arguments))
        return {"title": "林舟"}

    async def create_artifact(
        self,
        resource: object,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        del resource, idempotency_key
        self.artifacts.append(payload)
        return {"id": "artifact-1", "revision": len(self.artifacts)}


@pytest.mark.asyncio
async def test_core_tool_gateway_binds_tool_context_to_request() -> None:
    core = CoreClient()
    gateway = CoreToolGateway(core)
    context = ToolContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="task-1",
        agentId="设定",
    )

    result = await gateway.execute("get_character_detail", context, {"characterId": "c-1"})

    assert result == {"title": "林舟"}
    assert core.tools == [("设定", "get_character_detail", {"characterId": "c-1"})]


@pytest.mark.asyncio
async def test_artifact_port_creates_revision_and_marks_awaiting_user() -> None:
    core = CoreClient()
    port = CoreArtifactPort(core)
    state = {
        "userId": "user-1",
        "novelId": "novel-1",
        "taskId": "task-1",
        "chapterId": "chapter-1",
        "activeAgent": "写作",
    }
    event = {
        "type": "begin_artifact_output",
        "kind": "chapter_draft",
        "summary": "正文草案",
        "artifactKey": "task-1:chapter",
    }

    artifact_id = await port.submit(state, event, "完整正文")
    await port.mark_awaiting_user(artifact_id)

    assert artifact_id == "artifact-1"
    assert core.artifacts[0]["status"] == "under_review"
    assert core.artifacts[0]["payload"] == {
        "kind": "chapter_draft",
        "content": "完整正文",
    }
    assert core.artifacts[1]["status"] == "awaiting_user"
    assert core.artifacts[1]["payload"] == core.artifacts[0]["payload"]
