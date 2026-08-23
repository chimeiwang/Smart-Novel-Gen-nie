from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from ..providers.base import (
    ModelFinishReason,
    ModelProvider,
    ModelStructuredOutputRoute,
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
    policyId: str = "未提供"
    thinkingMode: str = "未提供"
    reasoningEffort: str | None = None
    reasoningTokens: int | None = None
    promptCacheMissTokens: int | None = None
    providerResponseId: str | None = None


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

    @property
    def provider_name(self) -> str:
        """暴露冻结任务可核验的供应商身份，不向规划器泄漏 Provider 实现。"""

        return self._provider.provider_name

    @property
    def model_name(self) -> str:
        """暴露实际模型名，规划任务必须在预占调用额度前校验其冻结值。"""

        return self._provider.model_name

    def supports_structured_output(self, route: ModelStructuredOutputRoute) -> bool:
        """在业务预占前查询 Provider 的显式能力，未知实现一律按不支持处理。"""

        checker = getattr(self._provider, "supports_structured_output", None)
        return bool(checker(route)) if callable(checker) else False

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
        # 结构化输出 Schema 会随请求一并发送给供应商，也会占用输入上下文与计费额度；
        # 因此预授权估算必须与旧工具 Schema 一样把它纳入，不能只统计消息正文。
        structured_output_size = (
            len(request.structuredOutput.model_dump_json())
            if request.structuredOutput is not None
            else 0
        )
        estimated_prompt_tokens = (
            sum(len(message.content) for message in request.messages)
            + sum(len(tool.model_dump_json()) for tool in request.tools)
            + structured_output_size
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
                    "promptCacheMissTokens": result.diagnostics.promptCacheMissTokens,
                    "completionTokens": result.usage.completionTokens,
                    "reasoningTokens": result.diagnostics.reasoningTokens,
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
        if request.structuredOutput is not None:
            # 视频导演草案包含冻结原文、设定和未通过审核的模型输出。人工工作流日志只保留
            # 传输路由、格式名与已经脱敏的稳定诊断，不得复制请求正文、响应草案或 JSON Schema。
            diagnostic = result.structuredOutputDiagnostic
            safe_output = (
                ""
                if diagnostic is None
                else (
                    "结构化诊断："
                    f"code={diagnostic.code}, "
                    f"pointer={diagnostic.jsonPointer}, "
                    f"keyword={diagnostic.keyword}"
                )
            )
            self._observer.record_model_call(
                ModelCallLogRecord(
                    context=context,
                    provider=self._provider.provider_name,
                    model=self._provider.model_name,
                    billingRequestId=billing_request_id,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "结构化输出调用："
                                f"route={request.structuredOutput.route}, "
                                f"format={request.structuredOutput.name}；"
                                "输入正文与模型草案未写入人工日志"
                            ),
                        }
                    ],
                    output=safe_output,
                    usage=result.usage,
                    finishReason=result.finishReason,
                    rawFinishReason=result.rawFinishReason,
                )
            )
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
                policyId=request.policy.policyId,
                thinkingMode=request.policy.thinkingMode,
                reasoningEffort=request.policy.reasoningEffort,
                reasoningTokens=result.diagnostics.reasoningTokens,
                promptCacheMissTokens=result.diagnostics.promptCacheMissTokens,
                providerResponseId=result.providerResponseId,
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
