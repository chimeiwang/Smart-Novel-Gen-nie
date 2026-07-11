from __future__ import annotations

from typing import Any

import pytest
from inkforge_agents.graph.state import create_initial_state
from inkforge_agents.operations.contracts import create_default_operation_for_agent
from inkforge_agents.operations.graph import OperationDependencies, build_operation_graph
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command


class AgentExecutor:
    async def run(self, agent_id: str, state: dict[str, Any]) -> dict[str, Any]:
        if agent_id == "写作":
            return {
                "visibleContent": "ARTIFACT_OUTPUT_START\n完整正文\nARTIFACT_OUTPUT_END",
                "controlEvents": [
                    {
                        "type": "begin_artifact_output",
                        "kind": "chapter_draft",
                        "summary": "正文草案",
                        "artifactKey": "task-1:write_chapter",
                    }
                ],
            }
        return {
            "visibleContent": f"{agent_id}复审通过",
            "controlEvents": [
                {
                    "type": "submit_evaluation",
                    "artifactKey": "task-1:write_chapter",
                    "verdict": "pass",
                    "summary": f"{agent_id}通过",
                }
            ],
        }


class ArtifactPort:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def submit(self, state: dict[str, Any], event: dict[str, Any], content: str) -> str:
        del state, event
        assert content == "完整正文"
        self.actions.append("submit")
        return "artifact-1"

    async def apply_patch(self, artifact_id: str, patches: list[dict[str, Any]]) -> None:
        del artifact_id, patches
        self.actions.append("patch")

    async def revise(self, state: dict[str, Any], event: dict[str, Any], content: str) -> str:
        del state, event, content
        self.actions.append("revise")
        return "artifact-1"

    async def mark_awaiting_user(self, artifact_id: str) -> None:
        del artifact_id
        self.actions.append("await")

    async def apply(self, artifact_id: str) -> None:
        del artifact_id
        self.actions.append("apply")

    async def discard(self, artifact_id: str) -> None:
        del artifact_id
        self.actions.append("discard")


@pytest.mark.asyncio
async def test_operation_graph_interrupts_and_resumes_user_approval() -> None:
    artifacts = ArtifactPort()
    graph = build_operation_graph(
        OperationDependencies(agentExecutor=AgentExecutor(), artifacts=artifacts),
        checkpointer=InMemorySaver(),
    )
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="续写本章",
    )
    state["currentOperation"] = create_default_operation_for_agent("写作", "续写本章")
    config = {"configurable": {"thread_id": "task-1"}}

    interrupted = await graph.ainvoke(state, config)
    assert interrupted["__interrupt__"]
    assert interrupted["activeArtifactId"] == "artifact-1"

    completed = await graph.ainvoke(Command(resume={"decision": "approve"}), config)
    assert completed["phase"] == "completed"
    assert artifacts.actions == ["submit", "await", "apply"]
