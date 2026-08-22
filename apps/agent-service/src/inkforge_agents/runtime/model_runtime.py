from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from ..providers.base import (
    ModelFinishReason,
    ModelProvider,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
)


class ModelCallContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    userId: str
    novelId: str
    taskId: str
    runId: str
    agentId: str


class ModelCallLogRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: ModelCallContext
    provider: str
    model: str
    billingRequestId: str | None
    messages: list[dict[str, str]]
    output: str
    usage: ModelUsage
    finishReason: ModelFinishReason
    rawFinishReason: str | None


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
    def record_model_call(self, record: ModelCallLogRecord) -> None: ...


class ModelRuntime:
    def __init__(
        self,
        provider: ModelProvider,
        *,
        billing: BillingPort | None = None,
        observer: ModelCallObserver | None = None,
        max_concurrency: int = 1,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("模型调用并发数必须为正整数")
        self._provider = provider
        self._billing = billing
        self._observer = observer
        self._max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @property
    def max_concurrency(self) -> int:
        return self._max_concurrency

    async def run_turn(
        self,
        request: ModelTurnRequest,
        *,
        context: ModelCallContext | None = None,
    ) -> ModelTurnResult:
        async with self._semaphore:
            return await self._run_turn_limited(request, context=context)

    async def _run_turn_limited(
        self,
        request: ModelTurnRequest,
        *,
        context: ModelCallContext | None = None,
    ) -> ModelTurnResult:
        if not self._provider.billable or self._billing is None:
            result = await _complete_provider(self._provider, request)
            self._record(context, request, result, billing_request_id=None)
            return result
        if context is None:
            raise ValueError("真实模型调用缺少运行资源上下文")

        request_id = _model_request_id(context, request)
        estimated_prompt_tokens = sum(len(message.content) for message in request.messages) + sum(
            len(tool.model_dump_json()) for tool in request.tools
        )
        try:
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
        except Exception as exc:
            raise RuntimeError("MODEL_AUTHORIZATION_FAILED：模型授权失败") from exc
        granted_max = authorization.get("maxOutputTokens")
        grant_token = authorization.get("grantToken")
        grant_request_id = authorization.get("requestId")
        if (
            type(granted_max) is not int
            or granted_max <= 0
            or granted_max > request.maxOutputTokens
        ):
            raise RuntimeError("模型授权输出上限无效")
        if not isinstance(grant_token, str) or not grant_token:
            raise RuntimeError("模型授权缺少 grantToken")
        if not isinstance(grant_request_id, str) or not grant_request_id:
            raise RuntimeError("模型授权缺少 requestId")

        provider_request = (
            request
            if granted_max == request.maxOutputTokens
            else request.model_copy(update={"maxOutputTokens": granted_max})
        )
        result = await _complete_provider(self._provider, provider_request)
        try:
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
        except Exception as exc:
            raise RuntimeError("MODEL_USAGE_REPORT_FAILED：模型用量回报失败") from exc
        self._record(
            context,
            request,
            result,
            billing_request_id=grant_request_id,
        )
        return result

    def _record(
        self,
        context: ModelCallContext | None,
        request: ModelTurnRequest,
        result: ModelTurnResult,
        *,
        billing_request_id: str | None,
    ) -> None:
        if self._observer is None or context is None:
            return
        self._observer.record_model_call(
            ModelCallLogRecord(
                context=context,
                provider=self._provider.provider_name,
                model=self._provider.model_name,
                billingRequestId=billing_request_id,
                messages=[
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                ],
                output=result.content,
                usage=result.usage,
                finishReason=result.finishReason,
                rawFinishReason=result.rawFinishReason,
            )
        )


async def _complete_provider(
    provider: ModelProvider,
    request: ModelTurnRequest,
) -> ModelTurnResult:
    try:
        return await provider.complete_turn(request)
    except Exception as exc:
        raise RuntimeError("MODEL_PROVIDER_FAILED：模型供应商调用失败") from exc


def _model_request_id(
    context: ModelCallContext,
    request: ModelTurnRequest,
) -> str:
    digest = hashlib.sha256(
        (context.model_dump_json() + "\n" + request.model_dump_json()).encode()
    ).hexdigest()[:32]
    return f"model-{digest}"
