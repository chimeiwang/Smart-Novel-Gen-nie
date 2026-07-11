from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from inkforge_agents.graph.snapshots import serialize_snapshot, to_typescript_snapshot
from inkforge_agents.graph.state import create_initial_state
from inkforge_agents.jobs.writing import WritingJobHandler
from inkforge_agents.queue.repository import QueueJob


class CoreClient:
    def __init__(self, context: dict[str, Any]) -> None:
        self.context = context
        self.events: list[tuple[int, str]] = []
        self.checkpoints: list[tuple[int, dict[str, Any]]] = []
        self.completions: list[tuple[int, dict[str, Any]]] = []

    async def call_tool(
        self, resource: object, agent_id: str, tool_name: str, arguments: object
    ) -> dict[str, Any]:
        del resource, arguments
        assert agent_id == "写作"
        assert tool_name == "get_writing_context"
        return self.context

    async def send_event(
        self, resource: object, *, sequence: int, event: str, data: dict[str, Any]
    ) -> None:
        del resource, data
        self.events.append((sequence, event))

    async def save_checkpoint(
        self, resource: object, *, sequence: int, checkpoint: dict[str, Any]
    ) -> None:
        del resource
        self.checkpoints.append((sequence, checkpoint))

    async def complete(self, resource: object, *, sequence: int, result: dict[str, Any]) -> None:
        del resource
        self.completions.append((sequence, result))

    async def fail(self, *args: object, **kwargs: object) -> None:
        raise AssertionError((args, kwargs))


class Graph:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.inputs: list[dict[str, Any]] = []

    async def ainvoke(self, value: dict[str, Any]) -> dict[str, Any]:
        self.inputs.append(value)
        return {**value, **self.result}


class WorkflowLog:
    def __init__(self) -> None:
        self.entries: list[tuple[str, object]] = []

    def start_run(self, **kwargs: object) -> None:
        self.entries.append(("开始", kwargs))

    def record_state(self, run_id: str, node: str, changes: dict[str, Any]) -> None:
        self.entries.append(("状态", (run_id, node, changes)))

    def finish_run(self, run_id: str, status: str) -> None:
        self.entries.append(("结束", (run_id, status)))


def _job(*, resume: bool = False, resume_input: dict[str, Any] | None = None) -> QueueJob:
    return QueueJob(
        jobId="job-1",
        kind="writing",
        runId="task-1",
        taskId="task-1",
        novelId="novel-1",
        userId="user-1",
        priority=10,
        payload={
            "resume": resume,
            "chapterId": "chapter-1",
            "writingSessionId": "session-1",
            "resumeInput": resume_input,
        },
        createdAt=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_new_writing_job_runs_parent_graph_and_persists_completion() -> None:
    core = CoreClient(
        {
            "workspace": {"novel": {"title": "测试小说"}},
            "planning": {
                "taskId": "task-1",
                "novelId": "novel-1",
                "chapterId": "chapter-1",
                "targetWordCount": 3200,
                "conversationHistory": [{"role": "user", "content": "续写本章"}],
                "userMessage": "续写本章",
                "graphState": None,
            },
        }
    )
    parent = Graph({"phase": "completed", "finalResponse": "已完成"})
    operation = Graph({})
    handler = WritingJobHandler(core, parent_graph=parent, operation_graph=operation)

    await handler(_job())

    assert parent.inputs[0]["targetWordCount"] == 3200
    assert parent.inputs[0]["conversationHistory"] == [{"role": "user", "content": "续写本章"}]
    assert operation.inputs == []
    assert core.events == [(1, "agent_start")]
    assert core.checkpoints[0][0] == 2
    assert core.checkpoints[0][1]["eventSequence"] == 2
    assert core.completions == [(3, {"finalResponse": "已完成"})]


@pytest.mark.asyncio
async def test_resume_writing_job_uses_flat_snapshot_and_continues_sequence() -> None:
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="初始请求",
    )
    state["eventSequence"] = 8
    state["activeArtifactId"] = "artifact-1"
    state["phase"] = "waiting_user"
    context = {
        "workspace": {},
        "planning": {
            "taskId": "task-1",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "targetWordCount": 4000,
            "conversationHistory": [],
            "userMessage": "",
            "graphState": to_typescript_snapshot(serialize_snapshot(state)),
        },
    }
    core = CoreClient(context)
    parent = Graph({})
    operation = Graph({"phase": "completed", "finalResponse": "已按意见处理"})
    handler = WritingJobHandler(core, parent_graph=parent, operation_graph=operation)

    await handler(
        _job(
            resume=True,
            resume_input={
                "decision": "revise",
                "artifactId": "artifact-1",
                "userMessage": "加强冲突",
            },
        )
    )

    assert parent.inputs == []
    assert operation.inputs[0]["resumeDecision"] == {
        "decision": "revise",
        "artifactId": "artifact-1",
        "userMessage": "加强冲突",
    }
    assert core.events == [(9, "agent_start")]
    assert core.checkpoints[0][0] == 10
    assert core.completions == [(11, {"finalResponse": "已按意见处理"})]


@pytest.mark.asyncio
async def test_writing_job_records_human_workflow_states() -> None:
    core = CoreClient(
        {
            "workspace": {},
            "planning": {
                "taskId": "task-1",
                "novelId": "novel-1",
                "chapterId": "chapter-1",
                "targetWordCount": 4000,
                "conversationHistory": [],
                "userMessage": "继续写作",
                "graphState": None,
            },
        }
    )
    workflow_log = WorkflowLog()
    handler = WritingJobHandler(
        core,
        parent_graph=Graph({"phase": "completed", "finalResponse": "完成"}),
        operation_graph=Graph({}),
        workflow_log=workflow_log,
    )

    await handler(_job())

    assert [entry[0] for entry in workflow_log.entries] == ["开始", "状态", "状态", "结束"]
    assert workflow_log.entries[0][1] == {
        "run_id": "task-1",
        "task_id": "task-1",
        "run_kind": "初次运行",
        "user_id": "user-1",
        "novel_id": "novel-1",
        "chapter_id": "chapter-1",
    }
    assert workflow_log.entries[-1] == ("结束", ("task-1", "完成"))
