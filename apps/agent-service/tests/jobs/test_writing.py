from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from inkforge_agents.clients.core import CoreServiceError
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
        self.resource_job_ids: list[str] = []

    def _record_resource(self, resource: Any) -> None:
        self.resource_job_ids.append(str(resource.jobId))

    async def call_tool(
        self, resource: object, agent_id: str, tool_name: str, arguments: object
    ) -> dict[str, Any]:
        self._record_resource(resource)
        del arguments
        assert agent_id == "写作"
        assert tool_name == "get_writing_context"
        return self.context

    async def send_event(
        self, resource: object, *, sequence: int, event: str, data: dict[str, Any]
    ) -> None:
        self._record_resource(resource)
        self.events.append((sequence, event))
        self.event_payloads.append(data)
        self.operations.append((event, sequence))

    async def save_checkpoint(
        self, resource: object, *, sequence: int, checkpoint: dict[str, Any]
    ) -> None:
        self._record_resource(resource)
        self.checkpoints.append((sequence, checkpoint))
        self.operations.append(("checkpoint", sequence))

    async def complete(self, resource: object, *, sequence: int, result: dict[str, Any]) -> None:
        self._record_resource(resource)
        self.completions.append((sequence, result))

    async def fail(self, resource: object, **kwargs: Any) -> None:
        self._record_resource(resource)
        self.failures.append(kwargs)


class Graph:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.inputs: list[dict[str, Any]] = []

    async def ainvoke(self, value: dict[str, Any]) -> dict[str, Any]:
        self.inputs.append(value)
        return {**value, **self.result}


class ArtifactHydration:
    def __init__(self) -> None:
        self.hydrated: list[tuple[Any, dict[str, Any], dict[str, Any]]] = []
        self.released: list[tuple[str, Any]] = []

    def hydrate(
        self,
        resource: Any,
        state: dict[str, Any],
        active_artifact: dict[str, Any],
    ) -> None:
        self.hydrated.append((resource, state, active_artifact))

    def release(self, artifact_id: str, resource: Any) -> None:
        self.released.append((artifact_id, resource))


def _active_artifact() -> dict[str, Any]:
    return {
        "id": "artifact-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "workflowRunId": "workflow-run-1",
        "artifactKey": "authority-key",
        "kind": "chapter_draft",
        "status": "awaiting_user",
        "title": "第一章",
        "summary": "摘要",
        "payload": {"kind": "chapter_draft", "content": "正文"},
        "diff": None,
        "createdByAgent": "写作",
        "reviewerAgent": None,
        "revision": 1,
    }


class WorkflowLog:
    def __init__(self) -> None:
        self.entries: list[tuple[str, object]] = []

    def start_run(self, **kwargs: object) -> None:
        self.entries.append(("开始", kwargs))

    def record_state(self, run_id: str, node: str, changes: dict[str, Any]) -> None:
        self.entries.append(("状态", (run_id, node, changes)))

    def finish_run(self, run_id: str, status: str) -> None:
        self.entries.append(("结束", (run_id, status)))


def _job(
    *,
    resume: bool = False,
    resume_input: dict[str, Any] | None = None,
    workflow_kind: str = "long_serial",
    operation: str | None = None,
    target_total_word_count: int | None = None,
    source: dict[str, Any] | None = None,
) -> QueueJob:
    return QueueJob(
        jobId="job-1",
        kind="writing",
        runId="run-1",
        taskId="task-1",
        novelId="novel-1",
        userId="user-1",
        priority=10,
        payload={
            "version": 1,
            "resume": resume,
            "chapterId": "chapter-1",
            "writingSessionId": "session-1",
            "resumeInput": resume_input,
            "workflowKind": workflow_kind,
            "operation": operation,
            "targetTotalWordCount": target_total_word_count,
            "source": source,
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
                "conversationHistory": [
                    {"role": "user", "content": "更早的请求"},
                    {"role": "agent", "content": "更早的回答"},
                ],
                "userMessage": "续写本章",
                "graphState": None,
            },
        }
    )
    parent = Graph({"phase": "completed", "finalResponse": "已完成"})
    operation = Graph({})
    handler = WritingJobHandler(
        core,
        parent_graph=parent,
        operation_graph=operation,
        artifacts=ArtifactHydration(),
    )

    await handler(_job())

    assert parent.inputs[0]["targetWordCount"] == 3200
    assert parent.inputs[0]["conversationHistory"] == [
        {"role": "user", "content": "更早的请求"},
        {"role": "agent", "content": "更早的回答"},
    ]
    assert all(
        item.get("content") != "续写本章"
        for item in parent.inputs[0]["conversationHistory"]
    )
    assert parent.inputs[0]["runtimeContext"] == {
        "coreContext": core.context,
        "runResource": {
            "userId": "user-1",
            "novelId": "novel-1",
            "taskId": "task-1",
            "runId": "run-1",
            "jobId": "job-1",
        },
    }
    assert operation.inputs == []
    assert core.events == [(1, "agent_start")]
    assert core.event_payloads[0] == {"agentId": "写作", "agentName": "作家"}
    assert core.checkpoints[0][0] == 2
    assert core.checkpoints[0][1]["eventSequence"] == 2
    assert "runtimeContext" not in core.checkpoints[0][1]
    assert "workspace" not in repr(core.checkpoints[0][1])
    assert "runId" not in repr(core.checkpoints[0][1])
    assert "jobId" not in repr(core.checkpoints[0][1])
    assert core.completions == [(3, {"finalResponse": "已完成"})]
    assert core.resource_job_ids == ["job-1", "job-1", "job-1", "job-1"]


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
            "conversationHistory": [
                {"role": "user", "content": "上一轮请求"},
                {"role": "agent", "content": "上一轮回答"},
            ],
            "userMessage": "",
            "graphState": to_typescript_snapshot(serialize_snapshot(state)),
            "activeArtifact": _active_artifact(),
        },
    }
    core = CoreClient(context)
    parent = Graph({})
    operation = Graph({"phase": "completed", "finalResponse": "已按意见处理"})
    artifacts = ArtifactHydration()
    handler = WritingJobHandler(
        core,
        parent_graph=parent,
        operation_graph=operation,
        artifacts=artifacts,
    )

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
    assert operation.inputs[0]["conversationHistory"] == [
        {"role": "user", "content": "上一轮请求"},
        {"role": "agent", "content": "上一轮回答"},
    ]
    assert operation.inputs[0]["runtimeContext"]["coreContext"] is context
    assert operation.inputs[0]["runtimeContext"]["runResource"]["runId"] == "run-1"
    assert operation.inputs[0]["runtimeContext"]["runResource"]["jobId"] == "job-1"
    assert core.events == [(9, "agent_start")]
    assert core.checkpoints[0][0] == 10
    assert core.completions == [(11, {"finalResponse": "已按意见处理"})]
    assert artifacts.hydrated[0][0].runId == "run-1"
    assert artifacts.hydrated[0][0].jobId == "job-1"
    assert artifacts.hydrated[0][2]["id"] == "artifact-1"
    assert [item[0] for item in artifacts.released] == ["artifact-1"]


def _short_context(*, operation: str = "develop_short_outline") -> dict[str, Any]:
    source: dict[str, Any] = {
        "kind": "short_outline_inspiration",
        "originalInspiration": "城市每天忘记一个人",
    }
    return {
        "workspace": {
            "writingBible": {
                "storyLengthProfile": "short_medium",
                "targetTotalWordCount": 6000,
            }
        },
        "planning": {
            "taskId": "task-1",
            "commandId": "job-1",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "targetWordCount": 6000,
            "workflowKind": "short_medium",
            "operation": operation,
            "targetTotalWordCount": 6000,
            "source": source,
            "conversationHistory": [],
            "userMessage": "根据灵感生成大纲",
            "shortStoryContext": {
                "directEdit": None,
                "revisionRequest": "根据灵感生成大纲",
                "anchors": None,
                "currentOutline": None,
                "originalInspiration": "城市每天忘记一个人",
                "recentConversation": [],
            },
            "graphState": None,
        },
    }


@pytest.mark.asyncio
async def test_short_outline_job_bypasses_parent_and_uses_explicit_operation() -> None:
    context = _short_context()
    parent = Graph({"phase": "completed", "finalResponse": "不应调用"})
    operation = Graph({"phase": "completed", "finalResponse": "短篇大纲完成"})
    handler = WritingJobHandler(
        CoreClient(context),
        parent_graph=parent,
        operation_graph=operation,
        artifacts=ArtifactHydration(),
    )

    await handler(
        _job(
            workflow_kind="short_medium",
            operation="develop_short_outline",
            target_total_word_count=6000,
            source=context["planning"]["source"],
        )
    )

    assert parent.inputs == []
    assert operation.inputs[0]["currentOperation"]["kind"] == "develop_short_outline"
    assert operation.inputs[0]["currentOperation"]["confidence"] == 1
    assert operation.inputs[0]["workflowKind"] == "short_medium"
    assert operation.inputs[0]["explicitOperation"] == "develop_short_outline"
    assert operation.inputs[0]["commandId"] == "job-1"


@pytest.mark.asyncio
async def test_short_identity_mismatch_fails_before_any_graph_call() -> None:
    context = _short_context()
    context["planning"]["targetTotalWordCount"] = 7000
    parent = Graph({})
    operation = Graph({})
    handler = WritingJobHandler(
        CoreClient(context),
        parent_graph=parent,
        operation_graph=operation,
        artifacts=ArtifactHydration(),
    )

    with pytest.raises(ValueError, match="WRITING_JOB_IDENTITY_MISMATCH"):
        await handler(
            _job(
                workflow_kind="short_medium",
                operation="develop_short_outline",
                target_total_word_count=6000,
                source=context["planning"]["source"],
            )
        )

    assert parent.inputs == []
    assert operation.inputs == []


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["initial", "current_job", "resume"])
async def test_short_story_placeholder_fails_before_every_graph_path(path: str) -> None:
    context = _short_context(operation="write_short_story")
    source = {
        "kind": "approved_short_outline",
        "outlineArtifactId": "artifact-1",
        "outlineRevision": 2,
        "outlineHash": "a" * 64,
    }
    context["planning"]["source"] = source
    resume = path == "resume"
    if path != "initial":
        state = create_initial_state(
            task_id="task-1",
            user_id="user-1",
            novel_id="novel-1",
            chapter_id="chapter-1",
            user_message="生成完整正文",
            target_word_count=6000,
            workflow_kind="short_medium",
            explicit_operation="write_short_story",
            command_id="job-1" if path == "current_job" else "previous-command",
            target_total_word_count=6000,
            command_source=source,
        )
        state["currentOperation"] = {
            "kind": "write_short_story",
            "userGoal": "生成完整正文",
        }
        state["phase"] = "completed" if path == "current_job" else "active"
        if path == "current_job":
            state["finalResponse"] = "不得重放的旧整稿结果"
        snapshot = to_typescript_snapshot(serialize_snapshot(state))
        if path == "current_job":
            snapshot["callbackJobId"] = "job-1"
        context["planning"]["graphState"] = snapshot
    parent = Graph({})
    operation = Graph({})
    core = CoreClient(context)
    artifacts = ArtifactHydration()
    handler = WritingJobHandler(
        core,
        parent_graph=parent,
        operation_graph=operation,
        artifacts=artifacts,
    )

    with pytest.raises(ValueError, match="SHORT_STORY_WORKFLOW_NOT_IMPLEMENTED"):
        await handler(
            _job(
                resume=resume,
                resume_input={"userMessage": "继续生成整稿"} if resume else None,
                workflow_kind="short_medium",
                operation="write_short_story",
                target_total_word_count=6000,
                source=source,
            )
        )

    assert parent.inputs == []
    assert operation.inputs == []
    assert core.events == []
    assert core.checkpoints == []
    assert core.completions == []
    assert core.failures == []
    assert artifacts.hydrated == []


@pytest.mark.asyncio
async def test_long_explicit_operation_bypasses_parent() -> None:
    context = {
        "workspace": {},
        "planning": {
            "taskId": "task-1",
            "commandId": "job-1",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "targetWordCount": 4000,
            "workflowKind": "long_serial",
            "operation": "write_chapter",
            "targetTotalWordCount": None,
            "source": None,
            "conversationHistory": [],
            "userMessage": "写正文",
            "graphState": None,
        },
    }
    parent = Graph({"phase": "completed"})
    operation = Graph({"phase": "completed"})
    handler = WritingJobHandler(
        CoreClient(context),
        parent_graph=parent,
        operation_graph=operation,
        artifacts=ArtifactHydration(),
    )
    await handler(_job(operation="write_chapter"))
    assert parent.inputs == []
    assert operation.inputs[0]["currentOperation"]["kind"] == "write_chapter"


@pytest.mark.asyncio
async def test_approve_resume_does_not_require_active_artifact_hydration() -> None:
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="初始请求",
    )
    state["activeArtifactId"] = "artifact-1"
    state["phase"] = "waiting_user"
    context = {
        "workspace": {},
        "planning": {
            "taskId": "task-1",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "conversationHistory": [],
            "userMessage": "",
            "graphState": to_typescript_snapshot(serialize_snapshot(state)),
            "activeArtifact": None,
        },
    }
    operation = Graph({"phase": "completed", "finalResponse": "已应用"})
    artifacts = ArtifactHydration()
    handler = WritingJobHandler(
        CoreClient(context),
        parent_graph=Graph({}),
        operation_graph=operation,
        artifacts=artifacts,
    )

    await handler(
        _job(
            resume=True,
            resume_input={"decision": "approve", "artifactId": "artifact-1"},
        )
    )

    assert len(operation.inputs) == 1
    assert artifacts.hydrated == []
    assert artifacts.released == []


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
        artifacts=ArtifactHydration(),
        workflow_log=workflow_log,
    )

    await handler(_job())

    assert [entry[0] for entry in workflow_log.entries] == ["开始", "状态", "状态", "结束"]
    assert workflow_log.entries[0][1] == {
        "run_id": "run-1",
        "task_id": "task-1",
        "run_kind": "初次运行",
        "user_id": "user-1",
        "novel_id": "novel-1",
        "chapter_id": "chapter-1",
    }
    assert workflow_log.entries[-1] == ("结束", ("run-1", "完成"))


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
        artifacts=ArtifactHydration(),
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
        artifacts=ArtifactHydration(),
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
    artifacts = ArtifactHydration()
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
        artifacts=artifacts,
    )

    with pytest.raises(RuntimeError, match="checkpoint 持久化失败"):
        await handler(_job())
    assert artifacts.released == []
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
        artifacts=ArtifactHydration(),
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


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_mode", ["graph_exception", "stable_error"])
async def test_writing_job_keeps_failure_callback_transport_errors_retryable(
    failure_mode: str,
) -> None:
    class FailingCallbackCore(CoreClient):
        async def fail(self, resource: object, **kwargs: Any) -> None:
            del resource, kwargs
            raise CoreServiceError("核心服务暂时不可用", recoverable=True)

    class RaisingGraph(Graph):
        async def ainvoke(self, value: dict[str, Any]) -> dict[str, Any]:
            self.inputs.append(value)
            raise RuntimeError("图执行失败")

    core = FailingCallbackCore(
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
    parent: Graph = (
        RaisingGraph({})
        if failure_mode == "graph_exception"
        else Graph({"phase": "error", "errorMessage": "稳定错误"})
    )
    handler = WritingJobHandler(
        core,
        parent_graph=parent,
        operation_graph=Graph({}),
        artifacts=ArtifactHydration(),
    )

    with pytest.raises(CoreServiceError, match="核心服务暂时不可用") as caught:
        await handler(_job())

    assert caught.value.recoverable is True


@pytest.mark.asyncio
async def test_initial_job_retry_replays_its_terminal_checkpoint_without_rerunning_graph() -> None:
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="初始请求",
    )
    state["phase"] = "completed"
    state["finalResponse"] = "首次执行已经完成的正文"
    state["eventSequence"] = 2
    snapshot = to_typescript_snapshot(serialize_snapshot(state))
    snapshot["callbackJobId"] = "job-1"
    core = CoreClient(
        {
            "workspace": {},
            "planning": {
                "taskId": "task-1",
                "novelId": "novel-1",
                "chapterId": "chapter-1",
                "targetWordCount": 4000,
                "conversationHistory": [],
                "userMessage": "初始请求",
                "graphState": snapshot,
            },
        }
    )
    parent = Graph({"phase": "completed", "finalResponse": "不应重新生成"})
    operation = Graph({"phase": "completed", "finalResponse": "不应重新恢复"})
    handler = WritingJobHandler(
        core,
        parent_graph=parent,
        operation_graph=operation,
        artifacts=ArtifactHydration(),
    )

    await handler(_job())

    assert parent.inputs == []
    assert operation.inputs == []
    assert core.events == []
    assert core.completions == [
        (3, {"finalResponse": "首次执行已经完成的正文"})
    ]


@pytest.mark.asyncio
async def test_current_job_nonterminal_snapshot_uses_fresh_runtime_identity() -> None:
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="初始请求",
    )
    state["phase"] = "active"
    snapshot = to_typescript_snapshot(serialize_snapshot(state))
    snapshot["callbackJobId"] = "job-1"
    context = {
        "workspace": {"novel": {"name": "当前作品"}},
        "planning": {
            "taskId": "task-1",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "targetWordCount": 4000,
            "conversationHistory": [],
            "userMessage": "初始请求",
            "graphState": snapshot,
        },
    }
    core = CoreClient(context)
    operation = Graph({"phase": "completed", "finalResponse": "恢复完成"})
    handler = WritingJobHandler(
        core,
        parent_graph=Graph({}),
        operation_graph=operation,
        artifacts=ArtifactHydration(),
    )

    await handler(_job())

    assert operation.inputs[0]["runtimeContext"] == {
        "coreContext": context,
        "runResource": {
            "userId": "user-1",
            "novelId": "novel-1",
            "taskId": "task-1",
            "runId": "run-1",
            "jobId": "job-1",
        },
    }


@pytest.mark.asyncio
async def test_current_job_terminal_snapshot_is_attached_before_settlement() -> None:
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="初始请求",
    )
    state["phase"] = "completed"
    state["activeArtifactId"] = "artifact-1"
    snapshot = to_typescript_snapshot(serialize_snapshot(state))
    snapshot["callbackJobId"] = "job-1"
    context = {
        "workspace": {},
        "planning": {
            "taskId": "task-1",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "targetWordCount": 4000,
            "conversationHistory": [],
            "userMessage": "初始请求",
            "graphState": snapshot,
            "activeArtifact": _active_artifact(),
        },
    }

    class InspectingHandler(WritingJobHandler):
        seen_state: dict[str, Any] | None = None

        async def _settle_recovered_state(
            self,
            resource: Any,
            run_id: str,
            recovered: Any,
            owned_artifact_id: str | None = None,
        ) -> bool:
            self.seen_state = recovered
            return await super()._settle_recovered_state(
                resource,
                run_id,
                recovered,
                owned_artifact_id,
            )

    artifacts = ArtifactHydration()
    handler = InspectingHandler(
        CoreClient(context),
        parent_graph=Graph({}),
        operation_graph=Graph({}),
        artifacts=artifacts,
    )

    await handler(_job())

    assert handler.seen_state is not None
    assert handler.seen_state["runtimeContext"]["runResource"]["runId"] == "run-1"
    assert handler.seen_state["runtimeContext"]["runResource"]["jobId"] == "job-1"
    assert artifacts.hydrated[0][2]["id"] == "artifact-1"
    assert [item[0] for item in artifacts.released] == ["artifact-1"]
