from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import pytest
from inkforge_agents.clients.core import CoreServiceError
from inkforge_agents.graph.snapshots import serialize_snapshot, to_typescript_snapshot
from inkforge_agents.graph.state import create_initial_state
from inkforge_agents.jobs.writing import WritingJobHandler
from inkforge_agents.queue.cancellation import JobCancelledError
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


class Cancellation:
    def __init__(self, cancel_on_check: int) -> None:
        self.cancel_on_check = cancel_on_check
        self.checks = 0

    async def ensure_active(self, job_id: str | None) -> None:
        assert job_id == "job-1"
        self.checks += 1
        if self.checks >= self.cancel_on_check:
            raise JobCancelledError()


def _job(*, resume: bool = False, resume_input: dict[str, Any] | None = None) -> QueueJob:
    return QueueJob(
        jobId="job-1",
        kind="writing",
        runId="run-1",
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


def _source_bindings() -> list[dict[str, Any]]:
    return [
        {
            "resourceType": "chapter",
            "resourceId": "chapter-1",
            "exists": True,
            "updatedAt": "2026-08-06T08:00:00Z",
            "contentSha256": "a" * 64,
            "revision": 3,
            "absenceSentinel": None,
        }
    ]


def _explicit_job(
    *,
    resume: bool = False,
    resume_input: dict[str, Any] | None = None,
    payload_updates: dict[str, Any] | None = None,
) -> QueueJob:
    payload: dict[str, Any] = {
        "version": 1,
        "workflow": "long_serial",
        "chapterId": "chapter-1",
        "writingSessionId": "session-1",
        "operation": "write_chapter",
        "target": {"type": "chapter", "id": "chapter-1"},
        "scope": {"kind": "chapter", "chapterId": "chapter-1"},
        "sourceBindings": _source_bindings(),
        "targetWordCount": 5200,
        "userInstruction": "写出雨夜里的不可逆选择",
        "resume": resume,
        "resumeInput": resume_input,
    }
    if payload_updates:
        payload.update(payload_updates)
    return QueueJob(
        jobId="job-1",
        kind="writing",
        runId="run-1",
        taskId="task-1",
        novelId="novel-1",
        userId="user-1",
        priority=10,
        payload=payload,
        createdAt=datetime.now(UTC),
    )


def _long_serial_snapshot() -> dict[str, Any]:
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="写出雨夜里的不可逆选择",
        target_word_count=5200,
    )
    state.update(
        {
            "workflow": "long_serial",
            "target": {"type": "chapter", "id": "chapter-1"},
            "scope": {"kind": "chapter", "chapterId": "chapter-1"},
            "sourceBindings": _source_bindings(),
            "currentOperation": {
                "kind": "write_chapter",
                "targetType": "chapter",
                "targetId": "chapter-1",
                "userGoal": "写出雨夜里的不可逆选择",
                "primaryAgent": "写作",
                "reviewers": ["校验", "编辑"],
                "outputKind": "chapter_text",
                "requiresArtifact": True,
                "requiresUserApproval": True,
                "confidence": 1.0,
                "reasoning": "显式长篇任务按服务端定义执行。",
            },
        }
    )
    return to_typescript_snapshot(serialize_snapshot(state))


@pytest.mark.asyncio
async def test_explicit_long_serial_job_bypasses_parent_with_trusted_operation() -> None:
    context = {
        "workspace": {},
        "planning": {
            "chapterId": "chapter-from-planning",
            "targetWordCount": 100,
            "conversationHistory": [],
            "userMessage": "让自然语言分类器自行决定",
            "graphState": None,
        },
    }
    parent = Graph({"phase": "error", "errorMessage": "不应进入父图"})
    operation = Graph({"phase": "completed", "finalResponse": "草案已生成"})
    handler = WritingJobHandler(
        CoreClient(context),
        parent_graph=parent,
        operation_graph=operation,
        artifacts=ArtifactHydration(),
    )

    await handler(_explicit_job())

    assert parent.inputs == []
    explicit = operation.inputs[0]
    assert explicit["workflow"] == "long_serial"
    assert explicit["chapterId"] == "chapter-1"
    assert explicit["targetWordCount"] == 5200
    assert explicit["userMessage"] == "写出雨夜里的不可逆选择"
    assert explicit["target"] == {"type": "chapter", "id": "chapter-1"}
    assert explicit["scope"] == {"kind": "chapter", "chapterId": "chapter-1"}
    assert explicit["sourceBindings"] == _source_bindings()
    assert explicit["currentOperation"] == {
        "kind": "write_chapter",
        "targetType": "chapter",
        "targetId": "chapter-1",
        "userGoal": "写出雨夜里的不可逆选择",
        "primaryAgent": "写作",
        "reviewers": ["校验", "编辑"],
        "outputKind": "chapter_text",
        "requiresArtifact": True,
        "requiresUserApproval": True,
        "confidence": 1.0,
        "reasoning": "显式长篇任务按服务端 Operation 定义执行。",
    }


@pytest.mark.asyncio
async def test_explicit_selection_snapshot_is_preserved_in_agent_state() -> None:
    content = "甲😀乙"
    full_hash = hashlib.sha256(content.encode()).hexdigest()
    selected_hash = hashlib.sha256("😀".encode()).hexdigest()
    context = {
        "workspace": {},
        "planning": {"graphState": None},
    }
    operation = Graph({"phase": "completed", "finalResponse": "ok"})
    handler = WritingJobHandler(
        CoreClient(context),
        parent_graph=Graph({"phase": "error"}),
        operation_graph=operation,
        artifacts=ArtifactHydration(),
    )
    await handler(
        _explicit_job(
            payload_updates={
                "operation": "rewrite_chapter_selection",
                "selectionTarget": {
                    "resourceType": "chapter_content",
                    "resourceId": "chapter-1",
                    "baseUpdatedAt": "2026-08-06T08:00:00Z",
                    "baseContentHash": full_hash,
                    "selectionStart": 1,
                    "selectionEnd": 2,
                    "selectedTextHash": selected_hash,
                },
                "selectionSnapshot": {
                    "resourceType": "chapter_content",
                    "resourceId": "chapter-1",
                    "baseUpdatedAt": "2026-08-06T08:00:00Z",
                    "baseContentHash": full_hash,
                    "selectionStart": 1,
                    "selectionEnd": 2,
                    "selectedTextHash": selected_hash,
                    "selectedText": "😀",
                    "contextBefore": "甲",
                    "contextAfter": "乙",
                    "sourceSnapshot": {
                        "resourceType": "chapter_content",
                        "resourceId": "chapter-1",
                        "content": content,
                        "updatedAt": "2026-08-06T08:00:00Z",
                        "contentSha256": full_hash,
                    },
                },
            }
        )
    )
    state = operation.inputs[0]
    assert state["selectionTarget"]["resourceType"] == "chapter_content"
    assert state["selectionSnapshot"]["selectedText"] == "😀"


@pytest.mark.asyncio
async def test_writing_handler_cancellation_before_start_event_has_no_core_side_effects() -> None:
    context = {
        "workspace": {},
        "planning": {
            "chapterId": "chapter-1",
            "targetWordCount": 100,
            "conversationHistory": [],
            "userMessage": "写作",
            "graphState": None,
        },
    }
    core = CoreClient(context)
    handler = WritingJobHandler(
        core,
        parent_graph=Graph({"phase": "completed", "finalResponse": "不应提交"}),
        operation_graph=Graph({}),
        artifacts=ArtifactHydration(),
        cancellation=Cancellation(cancel_on_check=3),
    )

    with pytest.raises(JobCancelledError):
        await handler(_job())

    assert core.events == []
    assert core.checkpoints == []
    assert core.completions == []
    assert core.failures == []


@pytest.mark.asyncio
async def test_explicit_long_serial_job_rejects_untrusted_agent_field() -> None:
    context = {
        "workspace": {},
        "planning": {
            "chapterId": "chapter-1",
            "conversationHistory": [],
            "userMessage": "原请求",
            "graphState": None,
        },
    }
    parent = Graph({})
    operation = Graph({})
    handler = WritingJobHandler(
        CoreClient(context),
        parent_graph=parent,
        operation_graph=operation,
        artifacts=ArtifactHydration(),
    )

    with pytest.raises(ValueError, match="显式长篇任务载荷无效"):
        await handler(_explicit_job(payload_updates={"primaryAgent": "剧情"}))

    assert parent.inputs == []
    assert operation.inputs == []


@pytest.mark.asyncio
async def test_long_serial_resume_reuses_snapshot_without_parent_classification() -> None:
    context = {
        "workspace": {},
        "planning": {
            "chapterId": "chapter-1",
            "conversationHistory": [],
            "userMessage": "",
            "graphState": _long_serial_snapshot(),
        },
    }
    parent = Graph({"phase": "error", "errorMessage": "不应重新分类"})
    operation = Graph({"phase": "completed", "finalResponse": "继续完成"})
    handler = WritingJobHandler(
        CoreClient(context),
        parent_graph=parent,
        operation_graph=operation,
        artifacts=ArtifactHydration(),
    )

    await handler(_job(resume=True, resume_input={"userMessage": "保留视角，继续"}))

    assert parent.inputs == []
    resumed = operation.inputs[0]
    assert resumed["userMessage"] == "保留视角，继续"
    assert resumed["resumeDecision"] is None
    assert resumed["currentOperation"]["kind"] == "write_chapter"
    assert resumed["currentOperation"]["primaryAgent"] == "写作"
    assert resumed["scope"] == {"kind": "chapter", "chapterId": "chapter-1"}
    assert resumed["sourceBindings"] == _source_bindings()


@pytest.mark.asyncio
async def test_full_explicit_long_serial_resume_matches_authoritative_snapshot() -> None:
    context = {
        "workspace": {},
        "planning": {
            "chapterId": "chapter-1",
            "conversationHistory": [],
            "userMessage": "",
            "graphState": _long_serial_snapshot(),
        },
    }
    parent = Graph({"phase": "error", "errorMessage": "不应重新分类"})
    operation = Graph({"phase": "completed", "finalResponse": "继续完成"})
    handler = WritingJobHandler(
        CoreClient(context),
        parent_graph=parent,
        operation_graph=operation,
        artifacts=ArtifactHydration(),
    )

    await handler(
        _explicit_job(
            resume=True,
            resume_input={"userMessage": "保留视角，继续"},
        )
    )

    assert parent.inputs == []
    resumed = operation.inputs[0]
    assert resumed["userMessage"] == "保留视角，继续"
    assert resumed["resumeDecision"] is None
    assert resumed["currentOperation"]["kind"] == "write_chapter"
    assert resumed["scope"] == {"kind": "chapter", "chapterId": "chapter-1"}


@pytest.mark.asyncio
async def test_full_explicit_long_serial_decision_resume_injects_decision() -> None:
    context = {
        "workspace": {},
        "planning": {
            "chapterId": "chapter-1",
            "conversationHistory": [],
            "userMessage": "",
            "graphState": _long_serial_snapshot(),
        },
    }
    parent = Graph({"phase": "error", "errorMessage": "不应重新分类"})
    operation = Graph({"phase": "completed", "finalResponse": "决定已处理"})
    handler = WritingJobHandler(
        CoreClient(context),
        parent_graph=parent,
        operation_graph=operation,
        artifacts=ArtifactHydration(),
    )

    await handler(
        _explicit_job(
            resume=True,
            resume_input={
                "artifactId": "artifact-1",
                "decision": "approve",
                "userMessage": "采用并继续",
            },
        )
    )

    assert parent.inputs == []
    resumed = operation.inputs[0]
    assert resumed["resumeDecision"] == {
        "artifactId": "artifact-1",
        "decision": "approve",
        "userMessage": "采用并继续",
    }
    assert resumed["userMessage"] == "采用并继续"
    assert resumed["sourceBindings"] == _source_bindings()


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
async def test_writing_job_persists_waiting_boundary_only_through_checkpoint() -> None:
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

    assert core.events == [(1, "agent_start")]
    assert core.checkpoints[0][0] == 2
    assert core.checkpoints[0][1]["eventSequence"] == 2
    assert core.operations == [
        ("agent_start", 1),
        ("checkpoint", 2),
    ]
    assert core.completions == []


@pytest.mark.asyncio
async def test_writing_job_preserves_blocked_cas_failure_at_waiting_boundary() -> None:
    core = CoreClient(
        {
            "workspace": {},
            "planning": {
                "taskId": "task-1",
                "novelId": "novel-1",
                "chapterId": "chapter-1",
                "targetWordCount": 4000,
                "conversationHistory": [],
                "userMessage": "局部修订",
                "graphState": None,
            },
        }
    )
    handler = WritingJobHandler(
        core,
        parent_graph=Graph(
            {
                "phase": "waiting_user",
                "artifactStatus": "blocked",
                "patchFailureCode": "ARTIFACT_REVISION_CONFLICT",
                "patchFailureMessage": "草案已被其他操作修改，请重新审核当前草案。",
                "activeArtifactId": "artifact-1",
                "__interrupt__": [
                    {"type": "artifact_review", "artifactId": "artifact-1"}
                ],
            }
        ),
        operation_graph=Graph({}),
        artifacts=ArtifactHydration(),
    )

    await handler(_job())

    checkpoint = core.checkpoints[0][1]
    assert checkpoint["phase"] == "awaiting_user_review"
    assert checkpoint["artifactStatus"] == "blocked"
    assert checkpoint["patchFailureCode"] == "ARTIFACT_REVISION_CONFLICT"
    assert checkpoint["patchFailureMessage"] == "草案已被其他操作修改，请重新审核当前草案。"
    assert checkpoint.get("errorMessage") is None
    assert checkpoint["operationStage"] == "局部修订无法安全应用"
    assert core.failures == []
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

    assert core.events == [(1, "agent_start")]
    assert core.checkpoints[0][0] == 2
    assert core.checkpoints[0][1]["phase"] == "awaiting_user_review"
    assert core.checkpoints[0][1]["activeArtifactId"] == "artifact-1"
    assert core.checkpoints[0][1]["artifactStatus"] == "awaiting_user"
    assert core.completions == []


@pytest.mark.asyncio
async def test_writing_job_retries_same_waiting_checkpoint_without_separate_event() -> None:
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

    assert core.events == [(1, "agent_start")]
    assert core.operations == [
        ("agent_start", 1),
        ("agent_start", 1),
        ("checkpoint", 2),
    ]
    assert core.checkpoints == [(2, core.checkpoints[0][1])]
    assert core.checkpoints[0][1]["eventSequence"] == 2


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
@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (RuntimeError("MODEL_PROVIDER_FAILED：供应商调用失败"), "MODEL_PROVIDER_FAILED"),
        (RuntimeError("普通图执行失败"), "AGENT_RUN_FAILED"),
    ],
)
async def test_writing_job_reports_stable_failure_code(
    failure: RuntimeError,
    expected_code: str,
) -> None:
    class RaisingGraph(Graph):
        async def ainvoke(self, value: dict[str, Any]) -> dict[str, Any]:
            self.inputs.append(value)
            raise failure

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
    handler = WritingJobHandler(
        core,
        parent_graph=RaisingGraph({}),
        operation_graph=Graph({}),
        artifacts=ArtifactHydration(),
    )

    with pytest.raises(NonRetryableJobError):
        await handler(_job())

    assert core.failures[0]["code"] == expected_code


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
