from __future__ import annotations

import asyncio
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
async def test_model_runtime_limits_process_wide_parallel_calls() -> None:
    class BlockingProvider(Provider):
        billable = False

        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.maximum = 0
            self.started = 0
            self.capacity_reached = asyncio.Event()
            self.release = asyncio.Event()

        async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
            self.active += 1
            self.started += 1
            self.maximum = max(self.maximum, self.active)
            if self.started == 3:
                self.capacity_reached.set()
            try:
                await self.release.wait()
                return await super().complete_turn(request)
            finally:
                self.active -= 1

    provider = BlockingProvider()
    runtime = ModelRuntime(
        provider,  # type: ignore[arg-type]
        max_concurrency=3,
    )
    request = ModelTurnRequest(
        messages=[{"role": "user", "content": "并发测试"}],
        tools=[],
        maxOutputTokens=128,
    )
    tasks = [asyncio.create_task(runtime.run_turn(request)) for _ in range(4)]
    try:
        await asyncio.wait_for(provider.capacity_reached.wait(), timeout=1)
        await asyncio.sleep(0.01)
        assert provider.started == 3
        assert provider.maximum == 3
    finally:
        provider.release.set()
        await asyncio.gather(*tasks)

    assert provider.started == 4
    assert provider.maximum == 3


def test_model_runtime_rejects_non_positive_parallel_limit() -> None:
    with pytest.raises(ValueError, match="模型调用并发数必须为正整数"):
        ModelRuntime(Provider(), max_concurrency=0)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_model_runtime_limits_billable_authorizations() -> None:
    class BlockingBilling(Billing):
        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.maximum = 0
            self.capacity_reached = asyncio.Event()
            self.release = asyncio.Event()

        async def authorize(
            self,
            context: ModelCallContext,
            payload: dict[str, Any],
            request_id: str,
        ) -> dict[str, Any]:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            if self.active == 3:
                self.capacity_reached.set()
            try:
                await self.release.wait()
                return await super().authorize(context, payload, request_id)
            finally:
                self.active -= 1

    billing = BlockingBilling()
    runtime = ModelRuntime(
        Provider(),  # type: ignore[arg-type]
        billing=billing,
        max_concurrency=3,
    )
    request = ModelTurnRequest(
        messages=[{"role": "user", "content": "计费并发测试"}],
        tools=[],
        maxOutputTokens=128,
    )
    context = ModelCallContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        agentId="写作",
    )
    tasks = [
        asyncio.create_task(runtime.run_turn(request, context=context))
        for _ in range(4)
    ]
    try:
        await asyncio.wait_for(billing.capacity_reached.wait(), timeout=1)
        await asyncio.sleep(0.01)
        assert len(billing.authorizations) == 0
        assert billing.maximum == 3
    finally:
        billing.release.set()
        await asyncio.gather(*tasks)

    assert len(billing.authorizations) == 4
    assert billing.maximum == 3


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
