from __future__ import annotations

from typing import Any

import pytest
from inkforge_agents.graph.state import create_initial_state
from inkforge_agents.operations.contracts import (
    CreativeOperation,
    create_default_operation_for_agent,
)
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
        del state
        if event.get("type") == "begin_artifact_output":
            assert content == "完整正文"
        if event.get("type") == "submit_beat_plan":
            assert content == "章节规划正文"
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
    assert interrupted["phase"] == "waiting_user"

    completed = await graph.ainvoke(Command(resume={"decision": "approve"}), config)
    assert completed["phase"] == "completed"
    assert artifacts.actions == ["submit", "await", "apply"]


@pytest.mark.asyncio
async def test_new_graph_instance_resumes_from_stable_user_decision_state() -> None:
    artifacts = ArtifactPort()
    original = build_operation_graph(
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
    interrupted = await original.ainvoke(
        state,
        {"configurable": {"thread_id": "old-instance"}},
    )
    stable = {key: value for key, value in interrupted.items() if key != "__interrupt__"}
    stable["resumeDecision"] = {"decision": "approve"}

    replacement = build_operation_graph(
        OperationDependencies(agentExecutor=AgentExecutor(), artifacts=artifacts)
    )
    completed = await replacement.ainvoke(stable)

    assert completed["phase"] == "completed"
    assert completed["artifactStatus"] == "applied"
    assert artifacts.actions == ["submit", "await", "apply"]


class RetryArtifactExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run(self, agent_id: str, state: dict[str, Any]) -> dict[str, Any]:
        del agent_id
        self.calls.append(state)
        if len(self.calls) == 1:
            return {"visibleContent": "章节规划正文", "controlEvents": []}
        return {
            "visibleContent": "章节规划正文",
            "controlEvents": [{"type": "submit_beat_plan", "summary": "章节规划"}],
        }


@pytest.mark.asyncio
async def test_operation_graph_retries_once_when_primary_agent_omits_artifact_event() -> None:
    executor = RetryArtifactExecutor()
    artifacts = ArtifactPort()
    graph = build_operation_graph(
        OperationDependencies(agentExecutor=executor, artifacts=artifacts),
        checkpointer=InMemorySaver(),
    )
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="规划本章",
    )
    state["currentOperation"] = CreativeOperation(
        kind="plan_chapter",
        targetType="chapter",
        userGoal="规划本章",
        primaryAgent="剧情",
        reviewers=[],
        outputKind="beat_plan",
        requiresArtifact=True,
        requiresUserApproval=True,
        confidence=1,
        reasoning="测试",
    )

    result = await graph.ainvoke(state, {"configurable": {"thread_id": "retry-artifact"}})

    assert result["__interrupt__"]
    assert len(executor.calls) == 2
    assert "必须提交待审核草案控制事件" in executor.calls[1]["contextMessages"][-1]
    assert artifacts.actions == ["submit", "await"]


class ReviewerFailureExecutor:
    async def run(self, agent_id: str, state: dict[str, Any]) -> dict[str, Any]:
        del state
        if agent_id == "写作":
            return {
                "visibleContent": "ARTIFACT_OUTPUT_START\n完整正文\nARTIFACT_OUTPUT_END",
                "controlEvents": [
                    {
                        "type": "begin_artifact_output",
                        "kind": "chapter_draft",
                        "summary": "正文草案",
                    }
                ],
            }
        raise RuntimeError("复审服务暂时不可用")


@pytest.mark.asyncio
async def test_operation_graph_degrades_reviewer_failure_to_block_result() -> None:
    artifacts = ArtifactPort()
    graph = build_operation_graph(
        OperationDependencies(agentExecutor=ReviewerFailureExecutor(), artifacts=artifacts),
        checkpointer=InMemorySaver(),
    )
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="重写场景",
    )
    state["currentOperation"] = create_default_operation_for_agent("写作", "重写场景")

    result = await graph.ainvoke(state, {"configurable": {"thread_id": "review-failure"}})

    assert result["__interrupt__"]
    assert result["artifactStatus"] == "awaiting_user"
    assert result["reviewResults"][0]["verdict"] == "block"


class SplitBuilderRetryExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, agent_id: str, state: dict[str, Any]) -> dict[str, Any]:
        del agent_id, state
        self.calls += 1
        if self.calls == 1:
            return {
                "visibleContent": "开始整理设定变化。",
                "controlEvents": [
                    {
                        "type": "start_update_builder",
                        "artifactKey": "task-1:sync_lore",
                        "summary": "同步设定",
                    }
                ],
            }
        return {
            "visibleContent": "设定变化已整理完成。",
            "controlEvents": [
                {
                    "type": "append_update_batch",
                    "artifactKey": "task-1:sync_lore",
                    "updates": {"storyBackground": "已发生的事实变化"},
                },
                {
                    "type": "finish_update_builder",
                    "artifactKey": "task-1:sync_lore",
                    "summary": "同步设定",
                },
            ],
        }


@pytest.mark.asyncio
async def test_operation_graph_combines_builder_events_across_artifact_retry() -> None:
    executor = SplitBuilderRetryExecutor()
    artifacts = ArtifactPort()
    graph = build_operation_graph(
        OperationDependencies(agentExecutor=executor, artifacts=artifacts),
        checkpointer=InMemorySaver(),
    )
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="批量修改设定",
    )
    state["currentOperation"] = CreativeOperation(
        kind="revise_lore",
        targetType="lore",
        userGoal="批量修改设定",
        primaryAgent="设定",
        reviewers=[],
        outputKind="lore_proposal",
        requiresArtifact=True,
        requiresUserApproval=True,
        confidence=1,
        reasoning="测试",
    )

    result = await graph.ainvoke(state, {"configurable": {"thread_id": "builder-retry"}})

    assert result["__interrupt__"]
    assert executor.calls == 2
    assert artifacts.actions == ["submit", "await"]


@pytest.mark.asyncio
async def test_removed_sync_lore_snapshot_fails_with_explicit_message() -> None:
    graph = build_operation_graph(
        OperationDependencies(agentExecutor=AgentExecutor(), artifacts=ArtifactPort()),
        checkpointer=InMemorySaver(),
    )
    state = create_initial_state(
        task_id="task-legacy",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="同步设定",
    )
    state["currentOperation"] = CreativeOperation(
        kind="sync_lore",
        targetType="lore",
        userGoal="同步设定",
        primaryAgent="设定",
        reviewers=["校验"],
        outputKind="sync_proposal",
        requiresArtifact=True,
        requiresUserApproval=True,
        confidence=1,
        reasoning="历史快照",
    )

    with pytest.raises(ValueError, match="同步设定流程已移除"):
        await graph.ainvoke(state, {"configurable": {"thread_id": "legacy-sync-lore"}})


class MixedBeatPlanExecutor:
    async def run(self, agent_id: str, state: dict[str, Any]) -> dict[str, Any]:
        del state
        if agent_id == "剧情":
            return {
                "visibleContent": "章节规划正文",
                "controlEvents": [
                    {
                        "type": "begin_artifact_output",
                        "kind": "outline_draft",
                        "summary": "通用草案",
                        "artifactKey": "task-1:plan_chapter",
                    },
                    {
                        "type": "submit_beat_plan",
                        "title": "第一章计划",
                        "beatCount": 1,
                        "summary": "章节计划草案",
                        "chapterGoal": "推进当前章节",
                        "totalEstimatedWords": 1000,
                    },
                ],
            }
        return {
            "visibleContent": "复审通过",
            "controlEvents": [
                {
                    "type": "submit_evaluation",
                    "artifactKey": "task-1:plan_chapter",
                    "verdict": "pass",
                    "summary": "通过",
                }
            ],
        }


@pytest.mark.asyncio
async def test_plan_chapter_prefers_beat_plan_event_over_generic_artifact_event() -> None:
    artifacts = ArtifactPort()
    graph = build_operation_graph(
        OperationDependencies(agentExecutor=MixedBeatPlanExecutor(), artifacts=artifacts),
        checkpointer=InMemorySaver(),
    )
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="规划本章",
    )
    state["currentOperation"] = CreativeOperation(
        kind="plan_chapter",
        targetType="chapter",
        userGoal="规划本章",
        primaryAgent="剧情",
        reviewers=["编辑"],
        outputKind="beat_plan",
        requiresArtifact=True,
        requiresUserApproval=True,
        confidence=1,
        reasoning="测试",
    )

    result = await graph.ainvoke(
        state,
        {"configurable": {"thread_id": "mixed-beat-plan"}},
    )

    assert result["__interrupt__"]
    assert artifacts.actions == ["submit", "await"]
