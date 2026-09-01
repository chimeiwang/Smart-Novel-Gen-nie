"""只在受双门禁的 E2E Agent 进程中注入的可控 Fake Provider。"""

from __future__ import annotations

import hashlib
import json

import httpx
from inkforge_agents.providers.base import (
    ModelStructuredOutputRoute,
    ModelTurnRequest,
    ModelTurnResult,
)
from inkforge_agents.providers.fake import FakeModelProvider


class ControlledFakeModelProvider:
    """通过外部测试控制器提供确定性等待点，并且不暴露任何业务路由。"""

    billable = False
    provider_name = FakeModelProvider.provider_name
    model_name = FakeModelProvider.model_name
    transport_profile = FakeModelProvider.transport_profile
    endpoint_profile = FakeModelProvider.endpoint_profile
    capability_version = FakeModelProvider.capability_version
    supports_request_idempotency = FakeModelProvider.supports_request_idempotency

    def __init__(self, *, control_url: str, control_token: str) -> None:
        if not control_url or len(control_token.encode("utf-8")) < 32:
            raise ValueError("E2E Fake Provider 控制参数无效")
        self._delegate = FakeModelProvider()
        self._token = control_token
        self._http = httpx.AsyncClient(
            base_url=control_url,
            headers={"X-InkForge-E2E-Token": control_token},
            timeout=httpx.Timeout(None, connect=2.0),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
            trust_env=False,
        )

    def supports_structured_output(self, route: ModelStructuredOutputRoute) -> bool:
        return self._delegate.supports_structured_output(route)

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        idempotency_key = request.requestIdempotencyKey
        if idempotency_key is None:
            # E2E 只控制 V2；闲置的 V1 消费器仍可保持与普通 Fake Provider 同形。
            return await self._delegate.complete_turn(request)
        request_sha256 = hashlib.sha256(
            json.dumps(
                request.model_dump(mode="json", by_alias=True, exclude_none=True),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        response = await self._http.post(
            "/control/provider/reached",
            json={
                "idempotencyKey": idempotency_key,
                "requestSha256": request_sha256,
            },
        )
        response.raise_for_status()
        result = await self._delegate.complete_turn(request)
        completed = await self._http.post(
            "/control/provider/completed",
            json={
                "idempotencyKey": idempotency_key,
                "requestSha256": request_sha256,
            },
        )
        completed.raise_for_status()
        return result

    async def aclose(self) -> None:
        await self._http.aclose()
