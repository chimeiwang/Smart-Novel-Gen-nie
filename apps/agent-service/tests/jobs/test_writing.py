from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from inkforge_agents.graph.snapshots import serialize_snapshot, to_typescript_snapshot
from inkforge_agents.graph.state import create_initial_state
from inkforge_agents.jobs.writing import WritingJobHandler
from inkforge_agents.queue.consumer import NonRetryableJobError
from inkforge_agents.queue.repository import QueueJob
from langgraph.types import Interrupt


class CoreClient:
    def __init__(self, context: dict[str, Any]) -> None:
        self.context = context
        self.events: list[tuple[int, str]] = []
        self.event_payloads: list[dict[str, Any]] = []
        self.checkpoints: list[tuple[int, dict[str, Any]]] = []
        self.completions: list[tuple[int, dict[str, Any]]] = []
        self.failures: list[dict[str, Any]] = []
        self.operations: list[tuple[str, int]] = []

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
        del resource
        self.events.append((sequence, event))
        self.event_payloads.append(data)
        self.operations.append((event, sequence))

    async def save_checkpoint(
        self, resource: object, *, sequence: int, checkpoint: dict[str, Any]
    ) -> None:
        del resource
        self.checkpoints.append((sequence, checkpoint))
        self.operations.append(("checkpoint", sequence))

    async def complete(self, resource: object, *, sequence: int, result: dict[str, Any]) -> None:
        del resource
        self.completions.append((sequence, result))

    async def fail(self, resource: object, **kwargs: Any) -> None:
        del resource
        self.failures.append(kwargs)


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
    assert core.event_payloads[0] == {"agentId": "写作", "agentName": "作家"}
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


@pytest.mark.asyncio
async def test_writing_job_publishes_artifact_event_before_waiting_checkpoint() -> None:
    core = CoreClient(
        {
            "workspace": {},
            "planning": {
                "taskId": "task-1",
                "novelId": "novel-1",
                "chapterId": "chapter-1",
                "targetWordCount": 4000,
                "conversationHistory": [],
                "userMessage": "重写场景",
                "graphState": None,
            },
        }
    )
    handler = WritingJobHandler(
        core,
        parent_graph=Graph(
            {
                "phase": "waiting_user",
                "activeAgent": "写作",
                "activeArtifactId": "artifact-1",
                "__interrupt__": [{"type": "artifact_review"}],
            }
        ),
        operation_graph=Graph({}),
    )

    await handler(_job())

    assert core.events == [
        (1, "agent_start"),
        (2, "artifact_awaiting_user_approval"),
    ]
    assert core.event_payloads[1] == {
        "agentId": "写作",
        "artifactId": "artifact-1",
    }
    assert core.checkpoints[0][0] == 3
    assert core.checkpoints[0][1]["eventSequence"] == 3
    assert core.operations == [
        ("agent_start", 1),
        ("artifact_awaiting_user_approval", 2),
        ("checkpoint", 3),
    ]
    assert core.completions == []


@pytest.mark.asyncio
async def test_writing_job_recovers_waiting_state_from_nested_graph_interrupt() -> None:
    core = CoreClient(
        {
            "workspace": {},
            "planning": {
                "taskId": "task-1",
                "novelId": "novel-1",
                "chapterId": "chapter-1",
                "targetWordCount": 4000,
                "conversationHistory": [],
                "userMessage": "规划本章",
                "graphState": None,
            },
        }
    )
    handler = WritingJobHandler(
        core,
        parent_graph=Graph(
            {
                "activeAgent": "剧情",
                "__interrupt__": (
                    Interrupt(
                        {
                            "type": "artifact_review",
                            "artifactId": "artifact-1",
                        }
                    ),
                ),
            }
        ),
        operation_graph=Graph({}),
    )

    await handler(_job())

    assert core.events == [
        (1, "agent_start"),
        (2, "artifact_awaiting_user_approval"),
    ]
    assert core.checkpoints[0][1]["phase"] == "awaiting_user_review"
    assert core.checkpoints[0][1]["activeArtifactId"] == "artifact-1"
    assert core.checkpoints[0][1]["artifactStatus"] == "awaiting_user"
    assert core.completions == []


@pytest.mark.asyncio
async def test_writing_job_replays_artifact_event_before_recovering_failed_checkpoint() -> None:
    class CheckpointFailureCore(CoreClient):
        def __init__(self, context: dict[str, Any]) -> None:
            super().__init__(context)
            self.checkpoint_attempts = 0

        async def send_event(
            self,
            resource: object,
            *,
            sequence: int,
            event: str,
            data: dict[str, Any],
        ) -> None:
            del resource
            identity = (sequence, event)
            if identity not in self.events:
                self.events.append(identity)
                self.event_payloads.append(data)
            self.operations.append((event, sequence))

        async def save_checkpoint(
            self,
            resource: object,
            *,
            sequence: int,
            checkpoint: dict[str, Any],
        ) -> None:
            self.checkpoint_attempts += 1
            if self.checkpoint_attempts == 1:
                raise RuntimeError("模拟 checkpoint 持久化失败")
            await super().save_checkpoint(
                resource,
                sequence=sequence,
                checkpoint=checkpoint,
            )

    core = CheckpointFailureCore(
        {
            "workspace": {},
            "planning": {
                "taskId": "task-1",
                "novelId": "novel-1",
                "chapterId": "chapter-1",
                "targetWordCount": 4000,
                "conversationHistory": [],
                "userMessage": "重写场景",
                "graphState": None,
            },
        }
    )
    handler = WritingJobHandler(
        core,
        parent_graph=Graph(
            {
                "phase": "waiting_user",
                "activeAgent": "写作",
                "activeArtifactId": "artifact-1",
                "__interrupt__": [{"type": "artifact_review"}],
            }
        ),
        operation_graph=Graph({}),
    )

    with pytest.raises(RuntimeError, match="checkpoint 持久化失败"):
        await handler(_job())
    await handler(_job())

    assert core.events == [
        (1, "agent_start"),
        (2, "artifact_awaiting_user_approval"),
    ]
    assert core.operations == [
        ("agent_start", 1),
        ("artifact_awaiting_user_approval", 2),
        ("agent_start", 1),
        ("artifact_awaiting_user_approval", 2),
        ("checkpoint", 3),
    ]
    assert core.checkpoints == [(3, core.checkpoints[0][1])]
    assert core.checkpoints[0][1]["eventSequence"] == 3


@pytest.mark.asyncio
async def test_writing_job_reports_stable_error_instead_of_completion() -> None:
    core = CoreClient(
        {
            "workspace": {},
            "planning": {
                "taskId": "task-1",
                "novelId": "novel-1",
                "chapterId": "chapter-1",
                "targetWordCount": 4000,
                "conversationHistory": [],
                "userMessage": "同步设定",
                "graphState": None,
            },
        }
    )
    handler = WritingJobHandler(
        core,
        parent_graph=Graph(
            {
                "phase": "error",
                "errorMessage": "主责智能体未提交待审核草案控制事件",
            }
        ),
        operation_graph=Graph({}),
    )

    with pytest.raises(NonRetryableJobError):
        await handler(_job())

    assert core.completions == []
    assert core.failures == [
        {
            "sequence": 3,
            "code": "AGENT_RUN_FAILED",
            "message": "主责智能体未提交待审核草案控制事件",
            "recoverable": True,
        }
    ]
