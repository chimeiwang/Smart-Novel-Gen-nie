from __future__ import annotations

from typing import Any

import pytest
from inkforge_agents.graph.parent_graph import ParentGraphDependencies, build_parent_graph
from inkforge_agents.graph.state import create_initial_state
from inkforge_agents.operations.graph import OperationDependencies


class AgentExecutor:
    async def run(self, agent_id: str, state: dict[str, Any]) -> dict[str, Any]:
        del state
        return {"visibleContent": f"{agent_id}回答", "controlEvents": []}


class ArtifactPort:
    def __getattr__(self, name: str) -> None:
        raise AssertionError(name)


@pytest.mark.asyncio
async def test_parent_graph_routes_command_through_operation_subgraph() -> None:
    graph = build_parent_graph(
        ParentGraphDependencies(
            operation=OperationDependencies(
                agentExecutor=AgentExecutor(),
                artifacts=ArtifactPort(),  # type: ignore[arg-type]
            )
        )
    )
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="@编辑 这个设定是否有卖点",
    )

    result = await graph.ainvoke(state)

    assert result["currentOperation"]["kind"] == "review_chapter"
    assert result["agentOutputs"]["编辑"]["visibleContent"] == "编辑回答"
    assert result["phase"] == "completed"
