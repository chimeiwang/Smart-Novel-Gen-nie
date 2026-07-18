from __future__ import annotations

from typing import Any

import pytest
from inkforge_agents.graph.parent_graph import ParentGraphDependencies, build_parent_graph
from inkforge_agents.graph.state import create_initial_state
from inkforge_agents.operations.graph import OperationDependencies


class AgentExecutor:
    async def run(
        self,
        agent_id: str,
        state: dict[str, Any],
        *,
        execution_mode: str,
        operation_kind: str,
    ) -> dict[str, Any]:
        del state
        assert execution_mode == "primary"
        assert operation_kind == "review_chapter"
        return {"visibleContent": f"{agent_id}回答", "controlEvents": []}


class ArtifactPort:
    def __getattr__(self, name: str) -> None:
        raise AssertionError(name)


class FallbackExecutor:
    async def run(
        self,
        agent_id: str,
        state: dict[str, Any],
        *,
        execution_mode: str,
        operation_kind: str,
    ) -> dict[str, Any]:
        del state
        assert (agent_id, execution_mode, operation_kind) == (
            "编辑",
            "primary",
            "answer_question",
        )
        return {"visibleContent": "请从明确入口启动中短篇流程", "controlEvents": []}


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
    state["conversationHistory"] = [
        {"role": "user", "content": "更早的问题"},
        {"role": "assistant", "content": "更早的回答"},
    ]
    state["runtimeContext"] = {
        "coreContext": {
            "workspace": {
                "novel": {"id": "novel-1", "name": "测试小说"},
                "chapters": [{"id": "chapter-1", "title": "第一章", "content": ""}],
            },
            "planning": {
                "taskId": "task-1",
                "novelId": "novel-1",
                "chapterId": "chapter-1",
            },
        },
        "runResource": {
            "userId": "user-1",
            "novelId": "novel-1",
            "taskId": "task-1",
            "runId": "run-1",
            "jobId": "job-1",
        },
    }

    result = await graph.ainvoke(state)

    assert result["currentOperation"]["kind"] == "review_chapter"
    assert result["agentOutputs"]["编辑"]["visibleContent"] == "编辑回答"
    assert result["phase"] == "completed"
    assert result["conversationHistory"] == state["conversationHistory"]


@pytest.mark.asyncio
async def test_long_parent_graph_does_not_infer_short_operation_from_keywords() -> None:
    graph = build_parent_graph(
        ParentGraphDependencies(
            operation=OperationDependencies(
                agentExecutor=FallbackExecutor(),
                artifacts=ArtifactPort(),  # type: ignore[arg-type]
            )
        )
    )
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="请写中短篇整稿全文",
        workflow_kind="long_serial",
        explicit_operation=None,
    )
    state["runtimeContext"] = {
        "coreContext": {
            "workspace": {"novel": {"id": "novel-1", "name": "测试小说"}},
            "planning": {
                "taskId": "task-1",
                "novelId": "novel-1",
                "chapterId": "chapter-1",
            },
        },
        "runResource": {
            "userId": "user-1",
            "novelId": "novel-1",
            "taskId": "task-1",
            "runId": "run-1",
            "jobId": "job-1",
        },
    }

    result = await graph.ainvoke(state)

    assert result["currentOperation"]["kind"] == "answer_question"
