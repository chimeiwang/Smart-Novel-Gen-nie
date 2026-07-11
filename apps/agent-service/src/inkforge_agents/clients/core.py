from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx
from inkforge_contracts.events import (
    AgentEvent,
    CheckpointCallback,
    RunCompletionCallback,
    RunFailureCallback,
)
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_service_auth import SignedServiceRequest, canonical_json_body
from pydantic import BaseModel, ConfigDict, JsonValue

from ..runtime.model_runtime import ModelCallContext


class RequestSigner(Protocol):
    def sign_request(
        self,
        *,
        body: bytes,
        http_method: str,
        http_path: str,
        query_string: bytes,
        idempotency_key: str,
        scope: Sequence[ServiceScope],
        task_id: str,
        run_id: str,
        novel_id: str,
    ) -> SignedServiceRequest: ...


class RunResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    userId: str
    novelId: str
    taskId: str
    runId: str


class CoreServiceError(RuntimeError):
    def __init__(self, message: str, *, recoverable: bool) -> None:
        super().__init__(message)
        self.recoverable = recoverable


class CoreServiceClient:
    def __init__(self, http: httpx.AsyncClient, signer: RequestSigner) -> None:
        self._http = http
        self._signer = signer

    async def call_tool(
        self,
        resource: RunResource,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, JsonValue],
    ) -> dict[str, Any]:
        value = await self._request(
            "POST",
            f"/internal/v1/tools/{tool_name}",
            {
                "userId": resource.userId,
                "novelId": resource.novelId,
                "taskId": resource.taskId,
                "runId": resource.runId,
                "agentId": agent_id,
                "arguments": arguments,
            },
            scope=ServiceScope.TOOL_READ,
            resource=resource,
            idempotency_key=_idempotency(resource.runId, "tool", tool_name, arguments),
        )
        result = value.get("result")
        if not isinstance(result, dict):
            raise CoreServiceError("核心工具返回格式无效", recoverable=False)
        return result

    async def send_event(
        self,
        resource: RunResource,
        *,
        sequence: int,
        event: str,
        data: dict[str, JsonValue],
    ) -> None:
        event_id = _event_id(resource.runId, sequence, event)
        body = AgentEvent(
            protocolVersion="1.0",
            eventId=event_id,
            runId=resource.runId,
            taskId=resource.taskId,
            sequence=sequence,
            event=event,
            data=data,
            occurredAt=_occurred_at(event_id),
        )
        await self._request(
            "POST",
            f"/internal/v1/writing/runs/{resource.runId}/events",
            body.model_dump(mode="json"),
            scope=ServiceScope.CALLBACK_EVENT,
            resource=resource,
            idempotency_key=event_id,
        )

    async def save_checkpoint(
        self,
        resource: RunResource,
        *,
        sequence: int,
        checkpoint: dict[str, JsonValue],
    ) -> None:
        event_id = _event_id(resource.runId, sequence, "checkpoint")
        body = CheckpointCallback(
            protocolVersion="1.0",
            eventId=event_id,
            runId=resource.runId,
            taskId=resource.taskId,
            sequence=sequence,
            checkpoint=checkpoint,
            occurredAt=_occurred_at(event_id),
        )
        await self._request(
            "PUT",
            f"/internal/v1/writing/runs/{resource.runId}/checkpoint",
            body.model_dump(mode="json"),
            scope=ServiceScope.CALLBACK_CHECKPOINT,
            resource=resource,
            idempotency_key=event_id,
        )

    async def complete(
        self,
        resource: RunResource,
        *,
        sequence: int,
        result: dict[str, JsonValue],
    ) -> None:
        event_id = _event_id(resource.runId, sequence, "complete")
        body = RunCompletionCallback(
            protocolVersion="1.0",
            eventId=event_id,
            runId=resource.runId,
            taskId=resource.taskId,
            sequence=sequence,
            result=result,
            occurredAt=_occurred_at(event_id),
        )
        await self._request(
            "PUT",
            f"/internal/v1/writing/runs/{resource.runId}/complete",
            body.model_dump(mode="json"),
            scope=ServiceScope.CALLBACK_COMPLETE,
            resource=resource,
            idempotency_key=event_id,
        )

    async def fail(
        self,
        resource: RunResource,
        *,
        sequence: int,
        code: str,
        message: str,
        recoverable: bool = True,
    ) -> None:
        event_id = _event_id(resource.runId, sequence, "fail")
        body = RunFailureCallback(
            protocolVersion="1.0",
            eventId=event_id,
            runId=resource.runId,
            taskId=resource.taskId,
            sequence=sequence,
            code=code,
            message=message,
            recoverable=recoverable,
            occurredAt=_occurred_at(event_id),
        )
        await self._request(
            "PUT",
            f"/internal/v1/writing/runs/{resource.runId}/fail",
            body.model_dump(mode="json"),
            scope=ServiceScope.CALLBACK_FAIL,
            resource=resource,
            idempotency_key=event_id,
        )

    async def create_artifact(
        self,
        resource: RunResource,
        payload: dict[str, JsonValue],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/internal/v1/review-artifacts",
            payload,
            scope=ServiceScope.TOOL_WRITE,
            resource=resource,
            idempotency_key=idempotency_key,
        )

    async def submit_evaluation(
        self,
        resource: RunResource,
        artifact_id: str,
        payload: dict[str, JsonValue],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/internal/v1/review-artifacts/{artifact_id}/evaluations",
            payload,
            scope=ServiceScope.TOOL_WRITE,
            resource=resource,
            idempotency_key=idempotency_key,
        )

    async def authorize_model(
        self,
        resource: RunResource,
        payload: dict[str, JsonValue],
        *,
        request_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/internal/v1/billing/authorize",
            payload,
            scope=ServiceScope.BILLING_AUTHORIZE,
            resource=resource,
            idempotency_key=request_id,
        )

    async def report_usage(
        self,
        resource: RunResource,
        payload: dict[str, JsonValue],
        *,
        request_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/internal/v1/billing/usage",
            payload,
            scope=ServiceScope.BILLING_USAGE_WRITE,
            resource=resource,
            idempotency_key=request_id,
        )

    async def get_rag_context(
        self,
        resource: RunResource,
        reference_id: str,
        content_hash: str,
    ) -> dict[str, Any]:
        payload = {
            "userId": resource.userId,
            "taskId": resource.taskId,
            "runId": resource.runId,
            "expectedContentHash": content_hash,
        }
        return await self._request(
            "POST",
            f"/internal/v1/novels/{resource.novelId}/references/{reference_id}/index-context",
            payload,
            scope=ServiceScope.RAG_INDEX_WRITE,
            resource=resource,
            idempotency_key=_idempotency(resource.runId, "rag-context", reference_id, content_hash),
        )

    async def complete_rag(
        self,
        resource: RunResource,
        reference_id: str,
        content_hash: str,
        embeddings: list[list[float]],
    ) -> None:
        payload = {
            "taskId": resource.taskId,
            "runId": resource.runId,
            "expectedContentHash": content_hash,
            "embeddings": embeddings,
        }
        await self._request(
            "PUT",
            f"/internal/v1/novels/{resource.novelId}/references/{reference_id}/index-success",
            payload,
            scope=ServiceScope.RAG_INDEX_WRITE,
            resource=resource,
            idempotency_key=_idempotency(resource.runId, "rag-success", reference_id, content_hash),
        )

    async def fail_rag(
        self,
        resource: RunResource,
        reference_id: str,
        content_hash: str,
        message: str,
    ) -> None:
        payload = {
            "taskId": resource.taskId,
            "runId": resource.runId,
            "expectedContentHash": content_hash,
            "message": message,
        }
        await self._request(
            "PUT",
            f"/internal/v1/novels/{resource.novelId}/references/{reference_id}/index-failure",
            payload,
            scope=ServiceScope.RAG_INDEX_WRITE,
            resource=resource,
            idempotency_key=_idempotency(resource.runId, "rag-failure", reference_id, content_hash),
        )

    async def get_portrait_context(
        self,
        resource: RunResource,
        style_id: str,
    ) -> dict[str, Any]:
        payload = {"runId": resource.runId}
        return await self._request(
            "POST",
            f"/internal/v1/styles/{style_id}/portrait-tasks/{resource.taskId}/portrait-context",
            payload,
            scope=ServiceScope.PORTRAIT_WRITE,
            resource=resource,
            idempotency_key=_idempotency(resource.runId, "portrait-context", style_id),
        )

    async def mark_portrait_processing(
        self,
        resource: RunResource,
        style_id: str,
    ) -> None:
        await self._request(
            "PUT",
            f"/internal/v1/styles/{style_id}/portrait-tasks/{resource.taskId}/processing",
            {"runId": resource.runId},
            scope=ServiceScope.PORTRAIT_WRITE,
            resource=resource,
            idempotency_key=_idempotency(resource.runId, "portrait-processing", style_id),
        )

    async def complete_portrait(
        self,
        resource: RunResource,
        style_id: str,
        result: dict[str, Any],
    ) -> None:
        payload = {"runId": resource.runId, **result}
        await self._request(
            "PUT",
            f"/internal/v1/styles/{style_id}/portrait-tasks/{resource.taskId}/success",
            payload,
            scope=ServiceScope.PORTRAIT_WRITE,
            resource=resource,
            idempotency_key=_idempotency(resource.runId, "portrait-success", style_id),
        )

    async def fail_portrait(
        self,
        resource: RunResource,
        style_id: str,
        message: str,
    ) -> None:
        await self._request(
            "PUT",
            f"/internal/v1/styles/{style_id}/portrait-tasks/{resource.taskId}/failure",
            {"runId": resource.runId, "message": message},
            scope=ServiceScope.PORTRAIT_WRITE,
            resource=resource,
            idempotency_key=_idempotency(resource.runId, "portrait-failure", style_id),
        )

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any],
        *,
        scope: ServiceScope,
        resource: RunResource,
        idempotency_key: str,
    ) -> dict[str, Any]:
        body = canonical_json_body(payload)
        signed = self._signer.sign_request(
            body=body,
            http_method=method,
            http_path=path,
            query_string=b"",
            idempotency_key=idempotency_key,
            scope=(scope,),
            task_id=resource.taskId,
            run_id=resource.runId,
            novel_id=resource.novelId,
        )
        try:
            response = await self._http.request(
                method,
                path,
                content=body,
                headers=signed.headers,
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            value = response.json()
        except httpx.HTTPStatusError as exc:
            recoverable = exc.response.status_code >= 500
            raise CoreServiceError(
                "核心服务拒绝智能体回调",
                recoverable=recoverable,
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise CoreServiceError("核心服务暂时不可用", recoverable=True) from exc
        if not isinstance(value, dict):
            raise CoreServiceError("核心服务响应格式无效", recoverable=False)
        return value


class CoreBillingGateway:
    def __init__(self, client: CoreServiceClient) -> None:
        self._client = client

    async def authorize(
        self,
        context: ModelCallContext,
        payload: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        return await self._client.authorize_model(
            RunResource(
                userId=context.userId,
                novelId=context.novelId,
                taskId=context.taskId,
                runId=context.runId,
            ),
            payload,
            request_id=request_id,
        )

    async def report(
        self,
        context: ModelCallContext,
        payload: dict[str, Any],
        request_id: str,
    ) -> None:
        await self._client.report_usage(
            RunResource(
                userId=context.userId,
                novelId=context.novelId,
                taskId=context.taskId,
                runId=context.runId,
            ),
            payload,
            request_id=request_id,
        )


def _event_id(run_id: str, sequence: int, event: str) -> str:
    digest = hashlib.sha256(f"{run_id}:{sequence}:{event}".encode()).hexdigest()[:32]
    return f"event-{digest}"


def _occurred_at(event_id: str) -> datetime:
    seconds = int(hashlib.sha256(event_id.encode()).hexdigest()[:8], 16)
    return datetime(2020, 1, 1, tzinfo=UTC) + timedelta(seconds=seconds)


def _idempotency(run_id: str, *parts: object) -> str:
    digest = hashlib.sha256(canonical_json_body([run_id, *parts])).hexdigest()[:32]
    return f"request-{digest}"
