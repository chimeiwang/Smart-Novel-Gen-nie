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

    assert result["planning"]["taskId"] == "task-1"
    assert [call["scope"] for call in signer.calls] == [
        (ServiceScope.TOOL_READ,),
        (ServiceScope.CALLBACK_EVENT,),
        (ServiceScope.CALLBACK_CHECKPOINT,),
        (ServiceScope.CALLBACK_COMPLETE,),
    ]
    assert [path for _, path, _ in requests] == [
        "/internal/v1/tools/get_writing_context",
        "/internal/v1/writing/runs/run-1/events",
        "/internal/v1/writing/runs/run-1/checkpoint",
        "/internal/v1/writing/runs/run-1/complete",
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
