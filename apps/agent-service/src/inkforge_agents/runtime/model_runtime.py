from __future__ import annotations

import hashlib
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from ..providers.base import ModelProvider, ModelTurnRequest, ModelTurnResult


class ModelCallContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    userId: str
    novelId: str
    taskId: str
    runId: str
    agentId: str


class BillingPort(Protocol):
    async def authorize(
        self,
        context: ModelCallContext,
        payload: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]: ...

    async def report(
        self,
        context: ModelCallContext,
        payload: dict[str, Any],
        request_id: str,
    ) -> None: ...


class ModelCallObserver(Protocol):
    def record_model_call(
        self,
        context: ModelCallContext,
        messages: list[dict[str, str]],
        output: str,
        finish_reason: str,
        raw_finish_reason: str | None,
    ) -> None: ...


class ModelRuntime:
    def __init__(
        self,
        provider: ModelProvider,
        *,
        billing: BillingPort | None = None,
        observer: ModelCallObserver | None = None,
    ) -> None:
        self._provider = provider
        self._billing = billing
        self._observer = observer

    async def run_turn(
        self,
        request: ModelTurnRequest,
        *,
        context: ModelCallContext | None = None,
    ) -> ModelTurnResult:
        if not self._provider.billable or self._billing is None:
            result = await self._provider.complete_turn(request)
            self._record(context, request, result)
            return result
        if context is None:
            raise ValueError("真实模型调用缺少运行资源上下文")

        request_id = _model_request_id(context, request)
        estimated_prompt_tokens = sum(len(message.content) for message in request.messages) + sum(
            len(tool.model_dump_json()) for tool in request.tools
        )
        authorization = await self._billing.authorize(
            context,
            {
                "userId": context.userId,
                "novelId": context.novelId,
                "taskId": context.taskId,
                "runId": context.runId,
                "agentId": context.agentId,
                "provider": self._provider.provider_name,
                "model": self._provider.model_name,
                "estimatedPromptTokens": estimated_prompt_tokens,
                "requestedMaxOutputTokens": request.maxOutputTokens,
            },
            request_id,
        )
        granted_max = authorization.get("maxOutputTokens")
        grant_token = authorization.get("grantToken")
        grant_request_id = authorization.get("requestId")
        if not isinstance(granted_max, int) or granted_max < request.maxOutputTokens:
            raise RuntimeError("模型授权输出上限低于本轮请求值")
        if not isinstance(grant_token, str) or not grant_token:
            raise RuntimeError("模型授权缺少 grantToken")
        if not isinstance(grant_request_id, str) or not grant_request_id:
            raise RuntimeError("模型授权缺少 requestId")

        result = await self._provider.complete_turn(request)
        await self._billing.report(
            context,
            {
                "requestId": grant_request_id,
                "taskId": context.taskId,
                "runId": context.runId,
                "novelId": context.novelId,
                "grantToken": grant_token,
                "promptTokens": result.usage.promptTokens,
                "cachedTokens": result.usage.cachedTokens,
                "completionTokens": result.usage.completionTokens,
                "totalTokens": result.usage.totalTokens,
            },
            grant_request_id,
        )
        self._record(context, request, result)
        return result

    def _record(
        self,
        context: ModelCallContext | None,
        request: ModelTurnRequest,
        result: ModelTurnResult,
    ) -> None:
        if self._observer is None or context is None:
            return
        self._observer.record_model_call(
            context,
            [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            result.content,
            result.finishReason,
            result.rawFinishReason,
        )


def _model_request_id(
    context: ModelCallContext,
    request: ModelTurnRequest,
) -> str:
    digest = hashlib.sha256(
        (context.model_dump_json() + "\n" + request.model_dump_json()).encode()
    ).hexdigest()[:32]
    return f"model-{digest}"
