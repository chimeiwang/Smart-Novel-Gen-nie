from __future__ import annotations

import asyncio
from typing import Any

import pytest
from inkforge_agents.providers.base import (
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
    ModelUsageDiagnostics,
)
from inkforge_agents.runtime.model_policy import LEGACY_PROVIDER_DEFAULT, REPORT_NO_THINKING
from inkforge_agents.runtime.model_runtime import (
    ModelCallContext,
    ModelCallFailureLogRecord,
    ModelCallLogRecord,
    ModelRuntime,
)


class Provider:
    billable = True
    provider_name = "openai_compatible"
    model_name = "deepseek-v4-flash"

    def __init__(self) -> None:
        self.requests: list[ModelTurnRequest] = []

    def supports_structured_output(self, route: str) -> bool:
        return route == "responses_json_schema_v1"

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
        self.calls: list[ModelCallLogRecord] = []
        self.failures: list[ModelCallFailureLogRecord] = []

    def record_model_call(self, record: ModelCallLogRecord) -> None:
        self.calls.append(record)

    def record_model_failure(self, record: ModelCallFailureLogRecord) -> None:
        self.failures.append(record)


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
        policy=LEGACY_PROVIDER_DEFAULT,
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


def test_model_runtime_exposes_provider_identity_for_frozen_task_preflight() -> None:
    runtime = ModelRuntime(Provider())  # type: ignore[arg-type]

    assert runtime.provider_name == "openai_compatible"
    assert runtime.model_name == "deepseek-v4-flash"
    assert runtime.supports_structured_output("responses_json_schema_v1") is True
    assert runtime.supports_structured_output("chat_json_output_v1") is False


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
        policy=LEGACY_PROVIDER_DEFAULT,
    )
    context = ModelCallContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        agentId="写作",
    )
    tasks = [asyncio.create_task(runtime.run_turn(request, context=context)) for _ in range(4)]
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
        policy=LEGACY_PROVIDER_DEFAULT,
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
async def test_billable_runtime_reports_provider_token_details_without_rebilling() -> None:
    class DetailedProvider(Provider):
        async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
            result = await super().complete_turn(request)
            return result.model_copy(
                update={
                    "diagnostics": ModelUsageDiagnostics(
                        promptCacheMissTokens=80,
                        reasoningTokens=12,
                    )
                }
            )

    billing = Billing()
    runtime = ModelRuntime(DetailedProvider(), billing=billing)  # type: ignore[arg-type]
    await runtime.run_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "明细"}],
            tools=[],
            maxOutputTokens=128,
            policy=LEGACY_PROVIDER_DEFAULT,
        ),
        context=ModelCallContext(
            userId="user-1",
            novelId="novel-1",
            taskId="task-1",
            runId="run-1",
            agentId="写作",
        ),
    )

    assert billing.usages[0]["promptCacheMissTokens"] == 80
    assert billing.usages[0]["reasoningTokens"] == 12


@pytest.mark.asyncio
async def test_billable_runtime_classifies_authorization_failure() -> None:
    class FailingBilling(Billing):
        async def authorize(
            self,
            context: ModelCallContext,
            payload: dict[str, Any],
            request_id: str,
        ) -> dict[str, Any]:
            del context, payload, request_id
            raise RuntimeError("授权服务不可用")

    runtime = ModelRuntime(Provider(), billing=FailingBilling())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="^MODEL_AUTHORIZATION_FAILED："):
        await runtime.run_turn(
            ModelTurnRequest(
                messages=[{"role": "user", "content": "正文"}],
                tools=[],
                maxOutputTokens=128,
                policy=LEGACY_PROVIDER_DEFAULT,
            ),
            context=ModelCallContext(
                userId="user-1",
                novelId="novel-1",
                taskId="task-1",
                runId="run-1",
                agentId="写作",
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("recoverable", [True, False])
async def test_billable_runtime_preserves_explicit_authorization_retry_decision(
    recoverable: bool,
) -> None:
    class BillingFailure(RuntimeError):
        def __init__(self) -> None:
            self.recoverable = recoverable
            super().__init__("授权服务拒绝请求")

    class FailingBilling(Billing):
        async def authorize(
            self,
            context: ModelCallContext,
            payload: dict[str, Any],
            request_id: str,
        ) -> dict[str, Any]:
            del context, payload, request_id
            raise BillingFailure()

    runtime = ModelRuntime(Provider(), billing=FailingBilling())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="^MODEL_AUTHORIZATION_FAILED：") as caught:
        await runtime.run_turn(
            ModelTurnRequest(
                messages=[{"role": "user", "content": "正文"}],
                tools=[],
                maxOutputTokens=128,
                policy=LEGACY_PROVIDER_DEFAULT,
            ),
            context=ModelCallContext(
                userId="user-1",
                novelId="novel-1",
                taskId="task-1",
                runId="run-1",
                agentId="写作",
            ),
        )

    assert getattr(caught.value, "retryable", None) is recoverable


@pytest.mark.asyncio
async def test_billable_runtime_classifies_provider_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingProvider(Provider):
        async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
            del request
            raise RuntimeError("供应商拒绝请求")

    observer = ModelObserver()
    caplog.set_level("WARNING", logger="inkforge_agents.runtime.model_runtime")
    runtime = ModelRuntime(  # type: ignore[arg-type]
        FailingProvider(),
        billing=Billing(),
        observer=observer,
    )

    with pytest.raises(RuntimeError, match="^MODEL_PROVIDER_FAILED："):
        await runtime.run_turn(
            ModelTurnRequest(
                messages=[{"role": "user", "content": "正文"}],
                tools=[],
                maxOutputTokens=128,
                policy=LEGACY_PROVIDER_DEFAULT,
            ),
            context=ModelCallContext(
                userId="user-1",
                novelId="novel-1",
                taskId="task-1",
                runId="run-1",
                agentId="写作",
            ),
        )

    assert len(observer.failures) == 1
    failure = observer.failures[0]
    assert failure.context.taskId == "task-1"
    assert failure.provider == "openai_compatible"
    assert failure.model == "deepseek-v4-flash"
    assert failure.failureCode == "unexpected_error"
    assert failure.exceptionType == "RuntimeError"
    assert failure.messageCount == 1
    assert failure.toolCount == 0
    assert failure.requestedMaxOutputTokens == 128
    assert failure.elapsedMs >= 0
    assert "task_id=task-1" in caplog.text
    assert "run_id=run-1" in caplog.text
    assert "failure_code=unexpected_error" in caplog.text
    assert "供应商拒绝请求" not in caplog.text


@pytest.mark.asyncio
async def test_billable_runtime_classifies_usage_report_failure_without_logging() -> None:
    class FailingBilling(Billing):
        async def report(
            self,
            context: ModelCallContext,
            payload: dict[str, Any],
            request_id: str,
        ) -> None:
            await super().report(context, payload, request_id)
            raise RuntimeError("用量服务不可用")

    provider = Provider()
    billing = FailingBilling()
    observer = ModelObserver()
    runtime = ModelRuntime(  # type: ignore[arg-type]
        provider,
        billing=billing,
        observer=observer,
    )

    with pytest.raises(RuntimeError, match="^MODEL_USAGE_REPORT_FAILED："):
        await runtime.run_turn(
            ModelTurnRequest(
                messages=[{"role": "user", "content": "正文"}],
                tools=[],
                maxOutputTokens=128,
                policy=LEGACY_PROVIDER_DEFAULT,
            ),
            context=ModelCallContext(
                userId="user-1",
                novelId="novel-1",
                taskId="task-1",
                runId="run-1",
                agentId="写作",
            ),
        )

    assert len(provider.requests) == 1
    assert len(billing.usages) == 1
    assert observer.calls == []


@pytest.mark.asyncio
async def test_结构化输出模式把响应_schema_纳入预授权估算() -> None:
    """Responses 的 JSON Schema 不是免费元数据，必须计入本轮输入预算。"""

    billing = Billing()
    runtime = ModelRuntime(Provider(), billing=billing)  # type: ignore[arg-type]
    request = ModelTurnRequest(
        messages=[{"role": "user", "content": "生成导演草案"}],
        tools=[],
        maxOutputTokens=2_048,
        policy=REPORT_NO_THINKING,
        structuredOutput={
            "route": "responses_json_schema_v1",
            "name": "director_draft",
            "jsonSchema": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
                "additionalProperties": False,
            },
        },
    )

    await runtime.run_turn(
        request,
        context=ModelCallContext(
            userId="user-1",
            novelId="novel-1",
            taskId="task-1",
            runId="run-1",
            agentId="视频导演",
        ),
    )

    assert request.structuredOutput is not None
    assert billing.authorizations[0]["estimatedPromptTokens"] == (
        len("生成导演草案") + len(request.structuredOutput.model_dump_json())
    )


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
        policy=LEGACY_PROVIDER_DEFAULT,
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
        policy=LEGACY_PROVIDER_DEFAULT,
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
            policy=LEGACY_PROVIDER_DEFAULT,
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
        policy=LEGACY_PROVIDER_DEFAULT,
    )

    await runtime.run_turn(request, context=context)

    assert len(observer.calls) == 1
    record = observer.calls[0]
    assert record.context == context
    assert record.provider == "openai_compatible"
    assert record.model == "deepseek-v4-flash"
    assert record.billingRequestId == ("grant-request-1" if billable else None)
    assert record.messages == [{"role": "user", "content": "完整请求" * 5000}]
    assert record.output == "完成"
    assert record.usage == ModelUsage(
        promptTokens=100,
        cachedTokens=20,
        completionTokens=30,
        totalTokens=130,
    )
    assert record.finishReason == "stop"
    assert record.rawFinishReason == "stop"


@pytest.mark.asyncio
async def test_结构化输出人工日志不记录正文_schema_或草案() -> None:
    class StructuredProvider(Provider):
        billable = False

        async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
            self.requests.append(request)
            return ModelTurnResult(
                content="",
                toolCalls=[],
                structuredOutput={"title": "不能进入日志的草案秘密"},
                finishReason="stop",
                rawFinishReason="response.completed",
                usage=ModelUsage(
                    promptTokens=10,
                    completionTokens=5,
                    totalTokens=15,
                ),
            )

    observer = ModelObserver()
    runtime = ModelRuntime(
        StructuredProvider(),  # type: ignore[arg-type]
        observer=observer,
    )
    context = ModelCallContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        agentId="视频导演",
    )
    request = ModelTurnRequest(
        messages=[{"role": "user", "content": "章节正文秘密"}],
        tools=[],
        maxOutputTokens=1_024,
        policy=REPORT_NO_THINKING,
        structuredOutput={
            "route": "responses_json_schema_v1",
            "name": "director_draft",
            "jsonSchema": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Schema秘密",
                    }
                },
                "required": ["title"],
                "additionalProperties": False,
            },
        },
    )

    await runtime.run_turn(request, context=context)

    serialized = repr(observer.calls)
    assert "章节正文秘密" not in serialized
    assert "Schema秘密" not in serialized
    assert "不能进入日志的草案秘密" not in serialized
    assert "responses_json_schema_v1" in serialized
    assert "director_draft" in serialized


@pytest.mark.asyncio
async def test_结构化输出人工日志只记录安全诊断() -> None:
    """失败草案不进日志，但稳定路径与关键字必须可供现场法证。"""

    class InvalidStructuredProvider(Provider):
        billable = False

        async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
            del request
            return ModelTurnResult(
                content="",
                toolCalls=[],
                structuredOutputDiagnostic={
                    "code": "schema_violation",
                    "jsonPointer": "/assets/0/duty",
                    "keyword": "enum",
                },
                finishReason="stop",
                rawFinishReason="response.completed",
                usage=ModelUsage(promptTokens=10, completionTokens=5, totalTokens=15),
            )

    observer = ModelObserver()
    runtime = ModelRuntime(InvalidStructuredProvider(), observer=observer)
    request = ModelTurnRequest(
        messages=[{"role": "user", "content": "不能进入日志的失败草案秘密"}],
        tools=[],
        maxOutputTokens=1_024,
        policy=REPORT_NO_THINKING,
        structuredOutput={
            "route": "responses_json_schema_v1",
            "name": "director_draft",
            "jsonSchema": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        },
    )

    await runtime.run_turn(
        request,
        context=ModelCallContext(
            userId="user-1",
            novelId="novel-1",
            taskId="task-1",
            runId="run-1",
            agentId="视频导演",
        ),
    )

    serialized = repr(observer.calls)
    assert "不能进入日志的失败草案秘密" not in serialized
    assert "code=schema_violation" in serialized
    assert "pointer=/assets/0/duty" in serialized
    assert "keyword=enum" in serialized
