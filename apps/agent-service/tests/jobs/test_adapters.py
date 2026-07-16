from __future__ import annotations

from typing import Any, cast

import pytest
from inkforge_agents.clients.core import RunResource
from inkforge_agents.jobs.adapters import CoreArtifactPort, CoreGraphAgentExecutor, CoreToolGateway
from inkforge_agents.providers.base import ModelUsage
from inkforge_agents.runtime.agent_runner import AgentRunRequest, AgentRunResult
from inkforge_agents.tools.registry import ToolContext


class CoreClient:
    def __init__(self) -> None:
        self.tools: list[tuple[str, str, dict[str, object]]] = []
        self.artifacts: list[dict[str, Any]] = []
        self.resources: list[object] = []
        self.evaluations: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(
        self,
        resource: object,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, Any]:
        self.resources.append(resource)
        self.tools.append((agent_id, tool_name, arguments))
        return {"title": "林舟"}

    async def create_artifact(
        self,
        resource: object,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.resources.append(resource)
        del idempotency_key
        self.artifacts.append(payload)
        return {"id": "artifact-1", "revision": len(self.artifacts)}

    async def submit_evaluation(
        self,
        resource: object,
        artifact_id: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> None:
        del resource, idempotency_key
        self.evaluations.append((artifact_id, payload))


class RecordingRunner:
    def __init__(self) -> None:
        self.requests: list[AgentRunRequest] = []

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        self.requests.append(request)
        return AgentRunResult(
            agentId=request.agentId,
            visibleContent="",
            controlEvents=[],
            toolCalls=[],
            toolResults=[],
            usage=ModelUsage(
                promptTokens=0,
                cachedTokens=0,
                completionTokens=0,
                totalTokens=0,
            ),
            finishReason="completed",
        )


class FakeEmbeddings:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        assert texts == ["文字起源"]
        return [[0.1, 0.2, 0.3]]


def _runtime_context() -> dict[str, Any]:
    return {
        "coreContext": {"workspace": {}, "planning": {}},
        "runResource": {
            "userId": "user-1",
            "novelId": "novel-1",
            "taskId": "task-1",
            "runId": "run-1",
            "jobId": "job-1",
        },
    }


def _resource(*, run_id: str = "run-1", job_id: str = "job-1") -> RunResource:
    return RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId=run_id,
        jobId=job_id,
    )


def _active_artifact(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": "artifact-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "workflowRunId": None,
        "artifactKey": "authority-key",
        "kind": "chapter_draft",
        "status": "under_review",
        "title": "正文草案",
        "summary": "首版",
        "payload": {"kind": "chapter_draft", "content": "完整正文"},
        "diff": None,
        "createdByAgent": "写作",
        "reviewerAgent": "校验",
        "revision": 2,
        "runId": "伪造运行",
        "jobId": "伪造命令",
    }
    value.update(overrides)
    return value


def _hydration_state() -> dict[str, Any]:
    return {
        "taskId": "task-1",
        "userId": "user-1",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "activeArtifactId": "artifact-1",
        "currentOperation": {"kind": "write_chapter", "primaryAgent": "写作"},
        "userMessage": "继续返工",
        "pendingRevision": {"requiredChanges": "补足冲突"},
        "runtimeContext": _runtime_context(),
    }


def test_artifact_port_hydrates_authority_with_current_runtime_identity() -> None:
    port = CoreArtifactPort(CoreClient())  # type: ignore[arg-type]

    port.hydrate(_resource(), _hydration_state(), _active_artifact())

    context = port.review_context("artifact-1")
    assert context["runId"] == "run-1"
    assert context["artifactKey"] == "authority-key"
    assert context["revision"] == 2
    assert "jobId" not in context


@pytest.mark.parametrize(
    "active",
    [
        _active_artifact(novelId="other"),
        _active_artifact(chapterId="other"),
        _active_artifact(artifactKey=""),
        _active_artifact(revision=0),
        _active_artifact(payload=[]),
        _active_artifact(payload={"kind": "outline_draft"}),
    ],
)
def test_artifact_port_rejects_invalid_hydration_identity(active: dict[str, Any]) -> None:
    port = CoreArtifactPort(CoreClient())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="ARTIFACT_REVISION_IDENTITY_MISMATCH"):
        port.hydrate(_resource(), _hydration_state(), active)


def test_artifact_port_rejects_hydration_without_operation_identity() -> None:
    port = CoreArtifactPort(CoreClient())  # type: ignore[arg-type]
    state = _hydration_state()
    state["currentOperation"] = None

    with pytest.raises(RuntimeError, match="ARTIFACT_REVISION_IDENTITY_MISMATCH"):
        port.hydrate(_resource(), state, _active_artifact())


def test_artifact_port_rejects_different_job_owner_and_release() -> None:
    port = CoreArtifactPort(CoreClient())  # type: ignore[arg-type]
    port.hydrate(_resource(), _hydration_state(), _active_artifact())

    with pytest.raises(RuntimeError, match="ARTIFACT_RUNTIME_IDENTITY_MISMATCH"):
        port.hydrate(
            _resource(run_id="run-2", job_id="job-2"),
            _hydration_state(),
            _active_artifact(),
        )
    with pytest.raises(RuntimeError, match="ARTIFACT_RUNTIME_IDENTITY_MISMATCH"):
        port.release("artifact-1", _resource(run_id="run-2", job_id="job-2"))

    assert port.review_context("artifact-1")["runId"] == "run-1"
    port.release("artifact-1", _resource())
    with pytest.raises(RuntimeError, match="缺少待审核草案上下文"):
        port.review_context("artifact-1")


def test_artifact_port_rejects_release_without_owned_record() -> None:
    port = CoreArtifactPort(CoreClient())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="缺少待审核草案上下文"):
        port.release("artifact-1", _resource())


@pytest.mark.asyncio
async def test_restart_hydration_allows_reviser_to_use_authoritative_context() -> None:
    artifacts = CoreArtifactPort(CoreClient())  # type: ignore[arg-type]
    state = _hydration_state()
    artifacts.hydrate(_resource(), state, _active_artifact())
    runner = RecordingRunner()
    executor = CoreGraphAgentExecutor(runner, artifacts)  # type: ignore[arg-type]

    await executor.run(
        "写作",
        state,
        execution_mode="reviser",
        operation_kind="write_chapter",
    )

    assert "完整正文" in runner.requests[0].contextMessages[0]
    assert "authority-key" in runner.requests[0].contextMessages[0]


@pytest.mark.asyncio
async def test_core_tool_gateway_binds_tool_context_to_request() -> None:
    core = CoreClient()
    gateway = CoreToolGateway(core)
    context = ToolContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
        agentId="设定",
    )

    result = await gateway.execute("get_character_detail", context, {"characterId": "c-1"})

    assert result == {"title": "林舟"}
    assert core.tools == [("设定", "get_character_detail", {"characterId": "c-1"})]
    resource = cast(Any, core.resources[0])
    assert resource.runId == "run-1"
    assert resource.jobId == "job-1"


@pytest.mark.asyncio
async def test_semantic_search_adds_query_embedding_before_calling_core() -> None:
    core = CoreClient()
    gateway = CoreToolGateway(core, FakeEmbeddings())
    context = ToolContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        agentId="设定",
    )

    await gateway.execute(
        "semantic_search_references",
        context,
        {"query": "文字起源", "topK": 3},
    )

    assert core.tools == [
        (
            "设定",
            "semantic_search_references",
            {"query": "文字起源", "topK": 3, "query_embedding": [0.1, 0.2, 0.3]},
        )
    ]


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
        "runtimeContext": _runtime_context(),
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
    resource = cast(Any, core.resources[0])
    assert resource.runId == "run-1"
    assert resource.jobId == "job-1"
    assert core.artifacts[0]["status"] == "under_review"
    assert core.artifacts[0]["workflowRunId"] is None
    assert core.artifacts[0]["payload"] == {
        "kind": "chapter_draft",
        "content": "完整正文",
    }
    assert core.artifacts[1]["status"] == "awaiting_user"
    assert core.artifacts[1]["payload"] == core.artifacts[0]["payload"]
    assert port.review_context(artifact_id)["payload"] == {
        "kind": "chapter_draft",
        "content": "完整正文",
    }


@pytest.mark.asyncio
async def test_reviewer_receives_submitted_artifact_without_read_tools() -> None:
    core = CoreClient()
    artifacts = CoreArtifactPort(core)
    artifact_id = await artifacts.submit(
        {
            "userId": "user-1",
            "novelId": "novel-1",
            "taskId": "task-1",
            "chapterId": "chapter-1",
            "activeAgent": "设定",
            "runtimeContext": _runtime_context(),
        },
        {
            "type": "propose_updates",
            "artifactKey": "task-1:sync_lore",
            "summary": "同步设定",
            "updates": {"storyBackground": "新增事实"},
        },
        "设定同步完成。",
    )
    runner = RecordingRunner()
    executor = CoreGraphAgentExecutor(runner, artifacts)  # type: ignore[arg-type]

    await executor.run(
        "校验",
        {
            "userId": "user-1",
            "novelId": "novel-1",
            "taskId": "task-1",
            "userMessage": "修改设定",
            "contextMessages": ["核心服务权威写作上下文：完整上下文"],
            "activeArtifactId": artifact_id,
            "currentOperation": {
                "kind": "revise_lore",
                "primaryAgent": "设定",
            },
            "runtimeContext": _runtime_context(),
        },
        execution_mode="reviewer",
        operation_kind="revise_lore",
    )

    assert runner.requests[0].executionMode == "reviewer"
    assert runner.requests[0].operationKind == "revise_lore"
    assert "当前待审核草案权威内容" in runner.requests[0].contextMessages[-1]
    assert "新增事实" in runner.requests[0].contextMessages[-1]
    assert runner.requests[0].contextMessages == [runner.requests[0].contextMessages[-1]]
    assert runner.requests[0].executionInstructions == []


@pytest.mark.asyncio
async def test_executor_marks_primary_and_reviser_modes_explicitly() -> None:
    runner = RecordingRunner()
    executor = CoreGraphAgentExecutor(runner, CoreArtifactPort(CoreClient()))  # type: ignore[arg-type]
    base_state = {
        "userId": "user-1",
        "novelId": "novel-1",
        "taskId": "task-1",
        "userMessage": "续写章节",
        "contextMessages": [],
        "currentOperation": {"kind": "write_chapter", "primaryAgent": "写作"},
        "runtimeContext": _runtime_context(),
    }

    await executor.run(
        "写作",
        base_state,
        execution_mode="primary",
        operation_kind="write_chapter",
    )
    assert runner.requests[-1].executionMode == "primary"
    assert runner.requests[-1].operationKind == "write_chapter"

    core = CoreClient()
    artifacts = CoreArtifactPort(core)
    artifact_id = await artifacts.submit(
        {
            **base_state,
            "chapterId": "chapter-1",
            "activeAgent": "写作",
        },
        {
            "type": "begin_artifact_output",
            "kind": "chapter_draft",
            "summary": "正文草案",
            "artifactKey": "task-1:chapter",
        },
        "原正文",
    )
    executor = CoreGraphAgentExecutor(runner, artifacts)  # type: ignore[arg-type]
    await executor.run(
        "写作",
        {
            **base_state,
            "activeArtifactId": artifact_id,
            "pendingRevision": {"requiredChanges": "补足冲突"},
        },
        execution_mode="reviser",
        operation_kind="write_chapter",
    )
    assert runner.requests[-1].executionMode == "reviser"
    assert runner.requests[-1].operationKind == "write_chapter"
    revision_context = runner.requests[-1].contextMessages[-1]
    assert all(
        key in revision_context
        for key in (
            "artifactId",
            "artifactKey",
            "revision",
            "kind",
            "artifactIteration",
            "requiredChanges",
            "payload",
        )
    )
    assert "补足冲突" in revision_context
    instructions = "\n".join(runner.requests[-1].executionInstructions)
    assert "补足冲突" not in instructions
    assert "submit_evaluation" not in instructions
    assert "get_active_review_artifact" not in instructions
    assert "审阅" not in instructions


@pytest.mark.asyncio
async def test_executor_rejects_missing_operation_kind() -> None:
    runner = RecordingRunner()
    executor = CoreGraphAgentExecutor(runner, CoreArtifactPort(CoreClient()))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="当前 Operation kind 无效"):
        await executor.run(
            "编辑",
            {
                "userId": "user-1",
                "novelId": "novel-1",
                "taskId": "task-1",
                "userMessage": "回答问题",
                "currentOperation": {},
                "runtimeContext": _runtime_context(),
            },
            execution_mode="primary",
            operation_kind="answer_question",
        )


@pytest.mark.asyncio
async def test_evaluation_uses_local_artifact_identity_not_model_locators() -> None:
    core = CoreClient()
    port = CoreArtifactPort(core)
    state = {
        "chapterId": "chapter-1",
        "activeAgent": "写作",
        "runtimeContext": _runtime_context(),
    }
    artifact_id = await port.submit(
        state,
        {
            "type": "begin_artifact_output",
            "kind": "chapter_draft",
            "summary": "正文草案",
            "artifactKey": "authority-key",
        },
        "正文",
    )

    await port.submit_evaluation(
        state,
        artifact_id,
        "校验",
        {
            "type": "submit_evaluation",
            "artifactId": "spoofed-artifact",
            "artifactKey": "spoofed-key",
            "verdict": "pass",
            "summary": "通过",
        },
    )

    submitted_id, payload = core.evaluations[0]
    assert submitted_id == artifact_id
    assert payload["revision"] == 1
    assert "artifactKey" not in payload
    assert "artifactId" not in payload


class MismatchingRevisionCore(CoreClient):
    async def create_artifact(
        self,
        resource: object,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        response = await super().create_artifact(
            resource,
            payload,
            idempotency_key=idempotency_key,
        )
        if len(self.artifacts) > 1:
            return {"id": "artifact-other", "revision": 2}
        return response


@pytest.mark.asyncio
async def test_revision_rejects_core_returning_different_artifact_id() -> None:
    core = MismatchingRevisionCore()
    port = CoreArtifactPort(core)
    state = {
        "chapterId": "chapter-1",
        "activeAgent": "写作",
        "runtimeContext": _runtime_context(),
    }
    artifact_id = await port.submit(
        state,
        {
            "type": "begin_artifact_output",
            "kind": "chapter_draft",
            "summary": "初稿",
            "artifactKey": "authority-key",
        },
        "正文",
    )
    state["activeArtifactId"] = artifact_id

    with pytest.raises(RuntimeError, match="ARTIFACT_REVISION_IDENTITY_MISMATCH"):
        await port.revise(
            state,
            {
                "type": "begin_artifact_output",
                "kind": "chapter_draft",
                "summary": "返工",
                "artifactKey": "authority-key",
            },
            "返工正文",
        )
