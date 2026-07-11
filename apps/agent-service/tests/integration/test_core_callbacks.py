from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from inkforge_agents.clients.core import CoreServiceClient, RunResource
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


@pytest.mark.asyncio
async def test_core_client_signs_tools_events_checkpoint_and_completion() -> None:
    requests: list[tuple[str, str, dict[str, object]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
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
            "result": "报告",
            "scores": {"overall": 9.0},
            "qualityGate": "pass",
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
    await http.aclose()


@pytest.mark.asyncio
async def test_core_client_uses_stable_idempotency_keys_for_retries() -> None:
    signer = Signer()
    http = httpx.AsyncClient(
        base_url="https://core.example",
        transport=httpx.MockTransport(lambda request: httpx.Response(204)),
    )
    client = CoreServiceClient(http, signer)  # type: ignore[arg-type]
    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
    )

    await client.fail(resource, sequence=4, code="MODEL_ERROR", message="失败")
    await client.fail(resource, sequence=4, code="MODEL_ERROR", message="失败")

    assert signer.calls[0]["idempotency_key"] == signer.calls[1]["idempotency_key"]
    assert signer.calls[0]["body"] == signer.calls[1]["body"]
    await http.aclose()
