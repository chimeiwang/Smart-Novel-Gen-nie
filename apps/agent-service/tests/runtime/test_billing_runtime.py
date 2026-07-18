from __future__ import annotations

from typing import Any

import pytest
from inkforge_agents.providers.base import (
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
)
from inkforge_agents.runtime.model_runtime import ModelCallContext, ModelRuntime


class Provider:
    billable = True
    provider_name = "openai_compatible"
    model_name = "deepseek-v4-flash"

    def __init__(self) -> None:
        self.requests: list[ModelTurnRequest] = []

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        self.requests.append(request)
        return ModelTurnResult(
            content="完成",
            toolCalls=[],
            finishReason="stop",
            rawFinishReason="stop",
            usage=ModelUsage(
                promptTokens=100,
                cachedTokens=20,
                completionTokens=30,
                totalTokens=130,
            ),
        )


class Billing:
    def __init__(self) -> None:
        self.authorizations: list[dict[str, Any]] = []
        self.usages: list[dict[str, Any]] = []

    async def authorize(
        self,
        context: ModelCallContext,
        payload: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        del context
        self.authorizations.append({**payload, "requestId": request_id})
        return {
            "requestId": "grant-request-1",
            "grantToken": "grant",
            "maxOutputTokens": payload["requestedMaxOutputTokens"],
            "billable": True,
        }

    async def report(
        self,
        context: ModelCallContext,
        payload: dict[str, Any],
        request_id: str,
    ) -> None:
        del context
        self.usages.append({**payload, "requestId": request_id})


class ModelObserver:
    def __init__(self) -> None:
        self.calls: list[
            tuple[ModelCallContext, list[dict[str, str]], str, str, str | None]
        ] = []

    def record_model_call(
        self,
        context: ModelCallContext,
        messages: list[dict[str, str]],
        output: str,
        finish_reason: str,
        raw_finish_reason: str | None,
    ) -> None:
        self.calls.append(
            (context, messages, output, finish_reason, raw_finish_reason)
        )


@pytest.mark.asyncio
async def test_billable_runtime_authorizes_then_reports_exact_usage() -> None:
    billing = Billing()
    runtime = ModelRuntime(Provider(), billing=billing)  # type: ignore[arg-type]
    context = ModelCallContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        agentId="写作",
    )
    request = ModelTurnRequest(
        messages=[{"role": "user", "content": "正文" * 10_000}],
        tools=[],
        maxOutputTokens=4096,
    )

    result = await runtime.run_turn(request, context=context)

    assert result.content == "完成"
    assert billing.authorizations[0]["requestedMaxOutputTokens"] == 4096
    assert billing.usages[0]["promptTokens"] == 100
    assert billing.usages[0]["cachedTokens"] == 20
    assert billing.usages[0]["completionTokens"] == 30
    assert billing.usages[0]["totalTokens"] == 130
    assert billing.usages[0]["grantToken"] == "grant"
    assert billing.usages[0]["requestId"] == "grant-request-1"


@pytest.mark.asyncio
async def test_计费运行时使用较小授权且不修改原请求() -> None:
    class ReducedBilling(Billing):
        async def authorize(
            self,
            context: ModelCallContext,
            payload: dict[str, Any],
            request_id: str,
        ) -> dict[str, Any]:
            authorization = await super().authorize(context, payload, request_id)
            authorization["maxOutputTokens"] = 1_024
            return authorization

    provider = Provider()
    billing = ReducedBilling()
    runtime = ModelRuntime(provider, billing=billing)  # type: ignore[arg-type]
    context = ModelCallContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        agentId="写作",
    )
    request = ModelTurnRequest(
        messages=[{"role": "user", "content": "正文"}],
        tools=[],
        maxOutputTokens=4_096,
    )

    await runtime.run_turn(request, context=context)

    assert billing.authorizations[0]["requestedMaxOutputTokens"] == 4_096
    assert request.maxOutputTokens == 4_096
    assert provider.requests[0] is not request
    assert provider.requests[0].maxOutputTokens == 1_024


@pytest.mark.asyncio
@pytest.mark.parametrize("granted_max", [0, -1, 4_097])
async def test_计费运行时在调用供应商前拒绝非法授权(
    granted_max: int,
) -> None:
    class InvalidBilling(Billing):
        async def authorize(
            self,
            context: ModelCallContext,
            payload: dict[str, Any],
            request_id: str,
        ) -> dict[str, Any]:
            authorization = await super().authorize(context, payload, request_id)
            authorization["maxOutputTokens"] = granted_max
            return authorization

    provider = Provider()
    billing = InvalidBilling()
    runtime = ModelRuntime(provider, billing=billing)  # type: ignore[arg-type]
    request = ModelTurnRequest(
        messages=[{"role": "user", "content": "正文"}],
        tools=[],
        maxOutputTokens=4_096,
    )

    with pytest.raises(RuntimeError, match="模型授权输出上限无效"):
        await runtime.run_turn(
            request,
            context=ModelCallContext(
                userId="user-1",
                novelId="novel-1",
                taskId="task-1",
                runId="run-1",
                agentId="写作",
            ),
        )

    assert provider.requests == []
    assert billing.usages == []


@pytest.mark.asyncio
async def test_fake_runtime_never_calls_billing() -> None:
    class FakeProvider(Provider):
        billable = False
        provider_name = "fake"

    billing = Billing()
    runtime = ModelRuntime(FakeProvider(), billing=billing)  # type: ignore[arg-type]
    await runtime.run_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "测试"}],
            tools=[],
            maxOutputTokens=128,
        ),
        context=ModelCallContext(
            userId="user-1",
            novelId="novel-1",
            taskId="task-1",
            runId="run-1",
            agentId="编辑",
        ),
    )

    assert billing.authorizations == []
    assert billing.usages == []


@pytest.mark.asyncio
@pytest.mark.parametrize("billable", [False, True])
async def test_runtime_records_complete_messages_without_tool_schema(billable: bool) -> None:
    class SelectedProvider(Provider):
        pass

    SelectedProvider.billable = billable
    observer = ModelObserver()
    billing = Billing()
    runtime = ModelRuntime(  # type: ignore[arg-type]
        SelectedProvider(),
        billing=billing,
        observer=observer,
    )
    context = ModelCallContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        agentId="写作",
    )
    request = ModelTurnRequest(
        messages=[{"role": "user", "content": "完整请求" * 5000}],
        tools=[{"name": "secret_tool", "description": "不应记录", "parameters": {}}],
        maxOutputTokens=128,
    )

    await runtime.run_turn(request, context=context)

    assert observer.calls == [
        (
            context,
            [{"role": "user", "content": "完整请求" * 5000}],
            "完成",
            "stop",
            "stop",
        )
    ]
