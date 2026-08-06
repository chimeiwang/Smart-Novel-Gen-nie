from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from inkforge_agents.clients.core import CoreServiceClient, CoreServiceError, RunResource
from inkforge_contracts.jwt_claims import ServiceScope
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


def _callback_receipt(
    *,
    disposition: str = "applied",
    reason_code: str = "CALLBACK_APPLIED",
    recoverable: bool = False,
) -> dict[str, object]:
    return {
        "protocolVersion": "1.0",
        "disposition": disposition,
        "reasonCode": reason_code,
        "recoverable": recoverable,
        "taskPhase": "active",
        "commandStatus": "processing",
        "outboxEventId": "outbox-event-1",
    }


async def _invoke_writing_boundary(
    client: CoreServiceClient,
    resource: RunResource,
    callback_name: str,
) -> None:
    if callback_name == "event":
        await client.send_event(resource, sequence=1, event="agent_start", data={})
        return
    if callback_name == "checkpoint":
        await client.save_checkpoint(
            resource,
            sequence=2,
            checkpoint={"taskId": "task-1"},
        )
        return
    if callback_name == "complete":
        await client.complete(
            resource,
            sequence=3,
            result={"finalContent": "完成"},
        )
        return
    if callback_name == "fail":
        await client.fail(
            resource,
            sequence=4,
            code="MODEL_ERROR",
            message="失败",
        )
        return
    raise AssertionError(f"未知回调类型：{callback_name}")


@pytest.mark.asyncio
async def test_core_client_signs_tools_events_checkpoint_and_completion() -> None:
    requests: list[tuple[str, str, dict[str, object]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["content-type"] == "application/json"
        payload = json.loads(request.content) if request.content else {}
        requests.append((request.method, request.url.path, payload))
        if "/tools/" in request.url.path:
            return httpx.Response(200, json={"result": {"planning": {"taskId": "task-1"}}})
        if request.url.path.endswith("/index-context"):
            return httpx.Response(200, json={"contentHash": "a" * 64, "chunks": ["正文"]})
        if request.url.path.endswith("/portrait-context"):
            return httpx.Response(
                200,
                json={"sourceText": "完整参考正文", "originalCharCount": 6},
            )
        if request.url.path.endswith("/quality-checks/check-1/context"):
            return httpx.Response(
                200,
                json={
                    "checkId": "check-1",
                    "novelId": "novel-1",
                    "chapterId": "chapter-1",
                    "chapterContent": "完整章节",
                    "message": "检查一致性",
                },
            )
        if request.url.path.endswith(("/events", "/checkpoint", "/complete")):
            return httpx.Response(200, json=_callback_receipt())
        return httpx.Response(204)

    signer = Signer()
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(handler),
    )
    client = CoreServiceClient(http, signer)  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )

    result = await client.call_tool(resource, "编辑", "get_writing_context", {})
    await client.send_event(resource, sequence=1, event="start", data={})
    await client.save_checkpoint(resource, sequence=2, checkpoint={"taskId": "task-1"})
    await client.complete(resource, sequence=3, result={"finalContent": "完成"})
    rag_context = await client.get_rag_context(resource, "reference-1", "a" * 64)
    await client.complete_rag(resource, "reference-1", "a" * 64, [[1.0]])
    portrait = await client.get_portrait_context(resource, "style-1")
    await client.mark_portrait_processing(resource, "style-1")
    await client.complete_portrait(
        resource,
        "style-1",
        {
            "creativeMethodology": "方法",
            "uniqueMarkers": "标记",
            "generationStyle": "风格",
            "expressionFeatures": "表达",
            "styleTraits": "特质",
            "originalCharCount": 6,
            "usedCharCount": 6,
            "truncated": False,
        },
    )
    quality = await client.get_quality_context(resource, "check-1", None, "检查一致性")
    await client.complete_quality(
        resource,
        "check-1",
        {
            "scores": {
                "characterConsistency": 81.0,
                "worldRuleConsistency": 82.0,
                "timelineConsistency": 83.0,
                "causalityConsistency": 84.0,
                "foreshadowingConsistency": 88.0,
            },
            "qualityGate": "pass",
            "issues": [],
            "report": "完整一致性报告",
            "rewriteBrief": None,
        },
    )

    assert result["planning"]["taskId"] == "task-1"
    assert rag_context["chunks"] == ["正文"]
    assert portrait["sourceText"] == "完整参考正文"
    assert quality["chapterContent"] == "完整章节"
    assert [call["scope"] for call in signer.calls] == [
        (ServiceScope.TOOL_READ,),
        (ServiceScope.CALLBACK_EVENT,),
        (ServiceScope.CALLBACK_CHECKPOINT,),
        (ServiceScope.CALLBACK_COMPLETE,),
        (ServiceScope.RAG_INDEX_WRITE,),
        (ServiceScope.RAG_INDEX_WRITE,),
        (ServiceScope.PORTRAIT_WRITE,),
        (ServiceScope.PORTRAIT_WRITE,),
        (ServiceScope.PORTRAIT_WRITE,),
        (ServiceScope.QUALITY_WRITE,),
        (ServiceScope.QUALITY_WRITE,),
    ]
    assert [path for _, path, _ in requests] == [
        "/internal/v1/tools/get_writing_context",
        "/internal/v1/writing/runs/run-1/events",
        "/internal/v1/writing/runs/run-1/checkpoint",
        "/internal/v1/writing/runs/run-1/complete",
        "/internal/v1/novels/novel-1/references/reference-1/index-context",
        "/internal/v1/novels/novel-1/references/reference-1/index-success",
        "/internal/v1/styles/style-1/portrait-tasks/task-1/portrait-context",
        "/internal/v1/styles/style-1/portrait-tasks/task-1/processing",
        "/internal/v1/styles/style-1/portrait-tasks/task-1/success",
        "/internal/v1/quality-checks/check-1/context",
        "/internal/v1/quality-checks/check-1/success",
    ]
    writing_callbacks = [
        payload
        for _, path, payload in requests
        if path.startswith("/internal/v1/writing/runs/")
    ]
    assert writing_callbacks == [
        {
            "protocolVersion": "1.1",
            "eventId": writing_callbacks[0]["eventId"],
            "jobId": "job-1",
            "runId": "run-1",
            "taskId": "task-1",
            "sequence": 1,
            "event": "start",
            "data": {},
            "occurredAt": writing_callbacks[0]["occurredAt"],
        },
        {
            "protocolVersion": "1.1",
            "eventId": writing_callbacks[1]["eventId"],
            "jobId": "job-1",
            "runId": "run-1",
            "taskId": "task-1",
            "sequence": 2,
            "checkpoint": {"taskId": "task-1"},
            "occurredAt": writing_callbacks[1]["occurredAt"],
        },
        {
            "protocolVersion": "1.1",
            "eventId": writing_callbacks[2]["eventId"],
            "jobId": "job-1",
            "runId": "run-1",
            "taskId": "task-1",
            "sequence": 3,
            "result": {"finalContent": "完成"},
            "occurredAt": writing_callbacks[2]["occurredAt"],
        },
    ]
    await http.aclose()


@pytest.mark.asyncio
async def test_core_client_uses_stable_idempotency_keys_for_retries() -> None:
    signer = Signer()
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=_callback_receipt())
        ),
    )
    client = CoreServiceClient(http, signer)  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )

    await client.fail(resource, sequence=4, code="MODEL_ERROR", message="失败")
    await client.fail(resource, sequence=4, code="MODEL_ERROR", message="失败")
    await client.fail(
        resource.model_copy(update={"jobId": "job-2"}),
        sequence=4,
        code="MODEL_ERROR",
        message="失败",
    )

    assert signer.calls[0]["idempotency_key"] == signer.calls[1]["idempotency_key"]
    assert signer.calls[0]["idempotency_key"] != signer.calls[2]["idempotency_key"]
    assert signer.calls[0]["body"] == signer.calls[1]["body"]
    failure_payload = json.loads(signer.calls[0]["body"])
    assert failure_payload["protocolVersion"] == "1.1"
    assert failure_payload["jobId"] == "job-1"
    await http.aclose()


@pytest.mark.asyncio
async def test_artifact_writes_bind_job_to_signed_body_and_idempotency_key() -> None:
    signer = Signer()
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "artifact-1", "revision": 1})

    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(handler),
    )
    client = CoreServiceClient(http, signer)  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )
    payload = {
        "runId": "run-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "jobId": "untrusted-job",
        "kind": "chapter_draft",
    }

    await client.create_artifact(resource, payload, idempotency_key="artifact-job-1")
    await client.create_artifact(
        resource.model_copy(update={"jobId": "job-2"}),
        payload,
        idempotency_key="artifact-job-2",
    )

    first_body = json.loads(requests[0].content)
    assert first_body["jobId"] == "job-1"
    assert signer.calls[0]["body"] == requests[0].content
    assert signer.calls[0]["idempotency_key"] != signer.calls[1]["idempotency_key"]
    await http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_name", ["event", "checkpoint", "complete", "fail"])
async def test_writing_boundary_rejects_missing_callback_receipt(
    callback_name: str,
) -> None:
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(lambda request: httpx.Response(204)),
    )
    client = CoreServiceClient(http, Signer())  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )

    with pytest.raises(CoreServiceError) as caught:
        await _invoke_writing_boundary(client, resource, callback_name)

    assert caught.value.code == "CALLBACK_RECEIPT_MISSING"
    assert caught.value.recoverable is True
    await http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"{"),
        httpx.Response(200, json={"disposition": "applied"}),
    ],
)
async def test_writing_boundary_rejects_invalid_callback_receipt(
    response: httpx.Response,
) -> None:
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(lambda request: response),
    )
    client = CoreServiceClient(http, Signer())  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )

    with pytest.raises(CoreServiceError) as caught:
        await client.save_checkpoint(
            resource,
            sequence=2,
            checkpoint={"taskId": "task-1"},
        )

    assert caught.value.code == "CALLBACK_RECEIPT_INVALID"
    assert caught.value.recoverable is True
    await http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("recoverable", [True, False])
async def test_writing_boundary_maps_rejected_receipt_recoverability(
    recoverable: bool,
) -> None:
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=_callback_receipt(
                    disposition="rejected",
                    reason_code="CALLBACK_IDENTITY_REJECTED",
                    recoverable=recoverable,
                ),
            )
        ),
    )
    client = CoreServiceClient(http, Signer())  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )

    with pytest.raises(CoreServiceError) as caught:
        await client.complete(
            resource,
            sequence=3,
            result={"finalContent": "完成"},
        )

    assert caught.value.code == "CALLBACK_IDENTITY_REJECTED"
    assert caught.value.recoverable is recoverable
    await http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_name", ["event", "checkpoint", "complete", "fail"])
@pytest.mark.parametrize("disposition", ["applied", "already_applied"])
async def test_writing_boundary_accepts_applied_receipts(
    callback_name: str,
    disposition: str,
) -> None:
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=_callback_receipt(disposition=disposition),
            )
        ),
    )
    client = CoreServiceClient(http, Signer())  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )

    await _invoke_writing_boundary(client, resource, callback_name)

    await http.aclose()
