from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from inkforge_contracts.jobs import AgentJobAccepted, AgentJobCancelRequest, AgentJobRequest
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_contracts.video_render import (
    SeedanceRenderQueryRequest,
    SeedanceRenderSubmitRequest,
)
from inkforge_core.agent_client import (
    AgentClient,
    PortraitAgentSubmitter,
    QualityAgentSubmitter,
    RagAgentSubmitter,
    SeedanceGatewayRejectedError,
    SeedanceSubmissionUnknownError,
    WritingTaskAgentSubmitter,
    command_job_payload,
)
from inkforge_core.writing.commands import WritingCommandRecord
from inkforge_core.writing.records import TaskRecord
from inkforge_service_auth import SignedServiceRequest


class Signer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def sign_request(self, **kwargs: object) -> SignedServiceRequest:
        self.calls.append(dict(kwargs))
        return SignedServiceRequest(
            token="signed",  # noqa: S106
            headers={
                "Authorization": "Bearer signed",
                "Idempotency-Key": str(kwargs["idempotency_key"]),
                "X-InkForge-Timestamp": "1",
                "X-InkForge-Body-SHA256": "0" * 64,
            },
        )


@pytest.mark.asyncio
async def test_agent_client_signs_exact_body_and_resource_binding() -> None:
    signer = Signer()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/v1/runs"
        assert request.headers["authorization"] == "Bearer signed"
        assert request.headers["content-type"] == "application/json"
        payload = json.loads(request.content)
        return httpx.Response(
            202,
            json={
                "protocolVersion": "1.0",
                "jobId": payload["jobId"],
                "runId": payload["runId"],
                "taskId": payload["taskId"],
                "status": "queued",
            },
        )

    http = httpx.AsyncClient(
        base_url="https://agent.example",
        transport=httpx.MockTransport(handler),
    )
    client = AgentClient(http, signer)
    submitter = WritingTaskAgentSubmitter(client)
    task = TaskRecord(
        id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        writing_session_id="session-1",
        phase="idle",
        graph_state_json=None,
    )

    await submitter.submit(task, resume=False)

    assert signer.calls[0]["scope"] == (ServiceScope.AGENT_RUN,)
    assert signer.calls[0]["task_id"] == "task-1"
    assert signer.calls[0]["novel_id"] == "novel-1"
    assert (
        signer.calls[0]["body"]
        == httpx.Request(
            "POST", "https://agent.example/internal/v1/runs", content=signer.calls[0]["body"]
        ).content
    )
    await http.aclose()


@pytest.mark.asyncio
async def test_agent_client_cancels_the_original_job_with_delete() -> None:
    signer = Signer()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/internal/v1/runs/job-1"
        assert json.loads(request.content) == {
            "protocolVersion": "1.0",
            "runId": "task-1",
            "taskId": "task-1",
            "novelId": "novel-1",
        }
        return httpx.Response(204)

    http = httpx.AsyncClient(
        base_url="https://agent.example",
        transport=httpx.MockTransport(handler),
    )
    client = AgentClient(http, signer)

    await client.cancel(
        "job-1",
        AgentJobCancelRequest(
            protocolVersion="1.0",
            runId="task-1",
            taskId="task-1",
            novelId="novel-1",
        ),
    )

    assert signer.calls[0]["scope"] == (ServiceScope.AGENT_CANCEL,)
    assert signer.calls[0]["idempotency_key"] == "job-1"
    assert signer.calls[0]["task_id"] == "task-1"
    await http.aclose()


@pytest.mark.asyncio
async def test_writing_job_id_is_stable_per_checkpoint_and_changes_on_resume() -> None:
    captured: list[object] = []

    class Client:
        async def submit(self, request: AgentJobRequest) -> AgentJobAccepted:
            captured.append(request)
            return AgentJobAccepted(
                jobId=request.jobId,
                runId=request.runId,
                taskId=request.taskId,
                status="queued",
            )

    submitter = WritingTaskAgentSubmitter(Client())  # type: ignore[arg-type]
    base = TaskRecord(
        id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        writing_session_id=None,
        phase="idle",
        graph_state_json=None,
    )
    await submitter.submit(base, resume=False)
    await submitter.submit(base, resume=False)
    resumed = replace(base, graph_state_json='{"phase":"waiting"}')
    await submitter.submit(resumed, resume=True)

    assert captured[0].jobId == captured[1].jobId
    assert captured[0].jobId != captured[2].jobId


@pytest.mark.asyncio
async def test_writing_command_uses_command_id_as_job_id() -> None:
    captured: list[object] = []

    class Client:
        async def submit(self, request: AgentJobRequest) -> AgentJobAccepted:
            captured.append(request)
            return AgentJobAccepted(
                jobId=request.jobId,
                runId=request.runId,
                taskId=request.taskId,
                status="completed",
            )

    submitter = WritingTaskAgentSubmitter(Client())  # type: ignore[arg-type]
    task = TaskRecord(
        id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        writing_session_id="session-1",
        phase="active",
        graph_state_json=None,
    )
    command = WritingCommandRecord(
        id="command-stable",
        task=task,
        kind="resume",
        payload={"resume": True, "chapterId": "chapter-1", "force": True},
        status="pending",
        attempt_count=0,
    )

    status = await submitter.submit_command(command)

    assert captured[0].jobId == "command-stable"
    assert captured[0].payload == command.payload
    assert captured[0].force is True
    assert status == "completed"


@pytest.mark.asyncio
async def test_writing_command_envelope_only_submits_validated_job() -> None:
    captured: list[AgentJobRequest] = []

    class Client:
        async def submit(self, request: AgentJobRequest) -> AgentJobAccepted:
            captured.append(request)
            return AgentJobAccepted(
                jobId=request.jobId,
                runId=request.runId,
                taskId=request.taskId,
                status="queued",
            )

    task = TaskRecord(
        id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        writing_session_id=None,
        phase="idle",
        graph_state_json=None,
    )
    job = {
        "resume": False,
        "chapterId": "chapter-1",
        "writingSessionId": None,
        "resumeInput": None,
    }
    envelope = {
        "_inkforgeCommand": {
            "schemaVersion": 1,
            "clientRequestId": "request-00000001",
            "commandKind": "start",
            "resourceIdentity": {
                "novelId": "novel-1",
                "chapterId": "chapter-1",
            },
            "normalizedBody": {"userInstruction": "继续"},
            "requestFingerprint": "a" * 64,
        },
        "job": job,
    }
    command = WritingCommandRecord(
        id="command-envelope",
        task=task,
        kind="start",
        payload=envelope,
        status="pending",
        attempt_count=0,
    )

    status = await WritingTaskAgentSubmitter(  # type: ignore[arg-type]
        Client()
    ).submit_command(command)

    assert captured[0].payload == job
    assert captured[0].payload != envelope
    assert status == "queued"
    assert command_job_payload(job) == job


def test_command_job_payload_rejects_malformed_new_envelope() -> None:
    with pytest.raises(ValueError, match="job"):
        command_job_payload(
            {
                "_inkforgeCommand": {
                    "schemaVersion": 1,
                    "clientRequestId": "request-00000001",
                    "commandKind": "start",
                    "resourceIdentity": {},
                    "normalizedBody": {},
                    "requestFingerprint": "a" * 64,
                },
                "quality": {},
            }
        )


@pytest.mark.asyncio
async def test_quality_job_id_uses_unique_workflow_run_id() -> None:
    captured: list[object] = []

    class Client:
        async def submit(self, request: AgentJobRequest) -> AgentJobAccepted:
            captured.append(request)
            return AgentJobAccepted(
                jobId=request.jobId,
                runId=request.runId,
                taskId=request.taskId,
                status="failed",
            )

    submitter = QualityAgentSubmitter(Client())  # type: ignore[arg-type]
    first_status = await submitter.submit(
        run_id="run-1",
        user_id="user-1",
        check_id="check-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        source_task_id="source-task-1",
        message="检查时间线",
    )
    second_status = await submitter.submit(
        run_id="run-2",
        user_id="user-1",
        check_id="check-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        source_task_id=None,
        message=None,
    )

    assert captured[0].jobId == "quality-run-1"
    assert captured[0].runId == "run-1"
    assert captured[0].taskId == "source-task-1"
    assert captured[1].jobId == "quality-run-2"
    assert captured[1].runId == "run-2"
    assert captured[1].taskId == "run-2"
    assert first_status == second_status == "failed"


@pytest.mark.asyncio
async def test_portrait_and_rag_submitters_propagate_agent_job_status() -> None:
    class Client:
        async def submit(self, request: AgentJobRequest) -> AgentJobAccepted:
            return AgentJobAccepted(
                jobId=request.jobId,
                runId=request.runId,
                taskId=request.taskId,
                status="cancelled",
            )

    client = Client()
    portrait = PortraitAgentSubmitter(client)
    rag = RagAgentSubmitter(client)

    assert (
        await portrait.submit(
            user_id="user-1",
            style_id="style-1",
            task_id="task-1",
            run_id="task-1",
            section=None,
        )
        == "cancelled"
    )
    assert (
        await rag.submit(
            "user-1",
            "novel-1",
            "reference-1",
            "a" * 64,
            datetime(2026, 8, 7, tzinfo=UTC),
        )
        == "cancelled"
    )


@pytest.mark.asyncio
async def test_rag_submitter_separates_stable_task_from_generation_job_identity() -> None:
    captured: list[AgentJobRequest] = []

    class Client:
        async def submit(self, request: AgentJobRequest) -> AgentJobAccepted:
            captured.append(request)
            return AgentJobAccepted(
                jobId=request.jobId,
                runId=request.runId,
                taskId=request.taskId,
                status="queued",
            )

    submitter = RagAgentSubmitter(Client())  # type: ignore[arg-type]
    content_hash = "a" * 64
    expected_task_digest = hashlib.sha256(
        f"rag:reference-1:{content_hash}".encode()
    ).hexdigest()[:32]
    first_generation = datetime(2026, 8, 7, 1, 2, 3, 456000, tzinfo=UTC)
    second_generation = first_generation + timedelta(milliseconds=1)

    await submitter.submit(
        "user-1", "novel-1", "reference-1", content_hash, first_generation
    )
    await submitter.submit(
        "user-1", "novel-1", "reference-1", content_hash, first_generation
    )
    await submitter.submit(
        "user-1", "novel-1", "reference-1", content_hash, second_generation
    )

    assert len(captured) == 3
    assert captured[0].model_dump() == captured[1].model_dump()
    assert captured[0].taskId == captured[2].taskId == f"rag-{expected_task_digest}"
    expected_first_run_digest = hashlib.sha256(
        f"rag:reference-1:{content_hash}:2026-08-07T01:02:03.456Z".encode()
    ).hexdigest()[:32]
    assert captured[0].runId == f"rag-{expected_first_run_digest}"
    assert captured[0].jobId == captured[0].runId
    assert captured[2].jobId == captured[2].runId
    assert captured[0].jobId != captured[2].jobId


@pytest.mark.asyncio
async def test_agent_debug_query_signs_exact_path_and_query() -> None:
    signer = Signer()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/v1/debug/workflow-runs/run-1"
        assert request.url.query == b"userId=user-1"
        return httpx.Response(
            200,
            json={
                "summary": {
                    "runId": "run-1",
                    "taskId": "task-1",
                    "runKind": "初次运行",
                    "userId": "user-1",
                    "novelId": "novel-1",
                    "chapterId": "chapter-1",
                    "startedAt": "2026-07-11T00:00:00Z",
                    "endedAt": "2026-07-11T00:01:00Z",
                    "status": "完成",
                },
                "content": "完整日志",
            },
        )

    http = httpx.AsyncClient(
        base_url="https://agent.example",
        transport=httpx.MockTransport(handler),
    )
    client = AgentClient(http, signer)

    result = await client.get_workflow_runs("user-1", "run-1")

    assert result["content"] == "完整日志"
    assert signer.calls[0]["scope"] == (ServiceScope.AGENT_DEBUG_READ,)
    assert signer.calls[0]["query_string"] == b"userId=user-1"
    assert signer.calls[0]["task_id"] == "debug"
    await http.aclose()


@pytest.mark.asyncio
async def test_seedance_short_calls_use_dedicated_scope_and_poll_identity() -> None:
    signer = Signer()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/internal/v1/video/seedance/tasks":
            return httpx.Response(
                202,
                json={"taskId": "render-1", "providerTaskId": "provider-1"},
            )
        assert request.url.path == (
            "/internal/v1/video/seedance/tasks/provider-1/query"
        )
        return httpx.Response(
            200,
            json={
                "taskId": "render-1",
                "providerTaskId": "provider-1",
                "status": "running",
                "output": None,
                "error": None,
            },
        )

    http = httpx.AsyncClient(
        base_url="https://agent.example",
        transport=httpx.MockTransport(handler),
    )
    client = AgentClient(http, signer)
    submitted = await client.submit_seedance_render(
        SeedanceRenderSubmitRequest(
            taskId="render-1",
            novelId="novel-1",
            inputHash="a" * 64,
            model="seedance-test",
            promptText="完整提示词",
            ratio="9:16",
            durationSeconds=5,
            resolution="720p",
            generateAudio=True,
            watermark=False,
            references=[],
        )
    )
    queried = await client.query_seedance_render(
        SeedanceRenderQueryRequest(
            taskId="render-1",
            novelId="novel-1",
            providerTaskId=submitted.providerTaskId,
            pollCount=3,
        )
    )

    assert queried.status == "running"
    assert [call["scope"] for call in signer.calls] == [
        (ServiceScope.VIDEO_RENDER,),
        (ServiceScope.VIDEO_RENDER,),
    ]
    assert signer.calls[0]["idempotency_key"] == "render-submit-render-1"
    assert signer.calls[1]["idempotency_key"] == "render-query-render-1-3"
    assert all(call["task_id"] == "render-1" for call in signer.calls)
    assert all(call["novel_id"] == "novel-1" for call in signer.calls)
    await http.aclose()


def _seedance_submit_request() -> SeedanceRenderSubmitRequest:
    return SeedanceRenderSubmitRequest(
        taskId="render-1",
        novelId="novel-1",
        inputHash="a" * 64,
        model="seedance-test",
        promptText="完整提示词",
        ratio="9:16",
        durationSeconds=5,
        resolution="720p",
        generateAudio=True,
        watermark=False,
        references=[],
    )


@pytest.mark.asyncio
async def test_seedance_submit_treats_agent_5xx_as_unknown_to_avoid_double_charge() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "供应商响应回传失败"})

    http = httpx.AsyncClient(
        base_url="https://agent.example",
        transport=httpx.MockTransport(handler),
    )
    client = AgentClient(http, Signer())

    with pytest.raises(SeedanceSubmissionUnknownError):
        await client.submit_seedance_render(_seedance_submit_request())

    await http.aclose()


@pytest.mark.asyncio
async def test_seedance_submit_preserves_definite_agent_4xx_rejection() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "输入参数无效"})

    http = httpx.AsyncClient(
        base_url="https://agent.example",
        transport=httpx.MockTransport(handler),
    )
    client = AgentClient(http, Signer())

    with pytest.raises(SeedanceGatewayRejectedError) as captured:
        await client.submit_seedance_render(_seedance_submit_request())

    assert captured.value.status_code == 422
    assert captured.value.detail == "输入参数无效"
    await http.aclose()
