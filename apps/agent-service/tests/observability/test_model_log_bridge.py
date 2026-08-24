from __future__ import annotations

from pathlib import Path

import pytest
from inkforge_agents.observability.human_workflow_log import HumanWorkflowLog
from inkforge_agents.observability.model_observer import WorkflowModelObserver
from inkforge_agents.providers.base import (
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
    ModelUsageDiagnostics,
    ProviderTransportError,
)
from inkforge_agents.runtime.model_policy import LEGACY_PROVIDER_DEFAULT
from inkforge_agents.runtime.model_runtime import (
    ModelCallContext,
    ModelCallLogRecord,
    ModelRuntime,
)


class LongOutputProvider:
    billable = False
    provider_name = "bridge-test"
    model_name = "bridge-test-model"

    def __init__(self, output: str) -> None:
        self._output = output

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        del request
        return ModelTurnResult(
            content=self._output,
            reasoningContent="这段推理不得进入人工日志正文",
            providerResponseId="response-bridge-1",
            toolCalls=[],
            usage=ModelUsage(
                promptTokens=10,
                cachedTokens=0,
                completionTokens=20,
                totalTokens=30,
            ),
            finishReason="length",
            rawFinishReason="max_tokens",
            diagnostics=ModelUsageDiagnostics(
                promptCacheMissTokens=3,
                reasoningTokens=4,
                providerUsageKeys=["completion_tokens_details", "prompt_tokens"],
            ),
        )


class FailingProvider:
    billable = False
    provider_name = "openai_compatible"
    model_name = "deepseek-v4-flash"

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        del request
        raise ProviderTransportError(
            code="timeout_error",
            statusCode=None,
            requestId="provider-request-123",
        )


@pytest.mark.asyncio
async def test_model_runtime_records_complete_provider_result_in_human_log(
    tmp_path: Path,
) -> None:
    workflow_log = HumanWorkflowLog(tmp_path)
    workflow_log.start_run(
        run_id="run-bridge",
        task_id="task-bridge",
        run_kind="桥接测试",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
    )
    request_text = "完整请求" * 5_000
    output_text = "完整响应" * 8_000
    runtime = ModelRuntime(
        LongOutputProvider(output_text),
        observer=WorkflowModelObserver(workflow_log),
    )

    await runtime.run_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": request_text}],
            tools=[],
            maxOutputTokens=8192,
            policy=LEGACY_PROVIDER_DEFAULT,
        ),
        context=ModelCallContext(
            userId="user-1",
            novelId="novel-1",
            taskId="task-bridge",
            runId="run-bridge",
            agentId="写作",
        ),
    )

    written = workflow_log.finish_run("run-bridge", "错误").read_text(encoding="utf-8")
    assert request_text in written
    assert output_text in written
    assert "任务标识：task-bridge" in written
    assert "运行标识：run-bridge" in written
    assert "计费请求标识：无" in written
    assert "模型：bridge-test/bridge-test-model" in written
    assert "Token 消耗：输入 10 | 缓存 0 | 输出 20 | 合计 30" in written
    assert "完成原因：length" in written
    assert "供应商原始原因：max_tokens" in written
    assert "policyId：legacy:provider-default" in written
    assert "思考模式：provider_default" in written
    assert "推理强度：未设置" in written
    assert "推理 Token：4" in written
    assert "缓存未命中 Token：3" in written
    assert "供应商响应标识：response-bridge-1" in written
    assert "这段推理不得进入人工日志正文" not in written
    assert "grantToken" not in written


@pytest.mark.asyncio
async def test_model_runtime_records_safe_provider_failure_in_human_log(
    tmp_path: Path,
) -> None:
    workflow_log = HumanWorkflowLog(tmp_path)
    workflow_log.start_run(
        run_id="run-failure",
        task_id="task-failure",
        run_kind="失败诊断",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
    )
    runtime = ModelRuntime(
        FailingProvider(),
        observer=WorkflowModelObserver(workflow_log),
    )
    private_prompt = "SECRET_PROMPT_MUST_NOT_LEAK"

    with pytest.raises(RuntimeError, match="^MODEL_PROVIDER_FAILED："):
        await runtime.run_turn(
            ModelTurnRequest(
                messages=[{"role": "user", "content": private_prompt}],
                tools=[
                    {
                        "name": "secret_tool",
                        "description": "SECRET_TOOL_MUST_NOT_LEAK",
                        "parameters": {"type": "object"},
                    }
                ],
                maxOutputTokens=4096,
                policy=LEGACY_PROVIDER_DEFAULT,
            ),
            context=ModelCallContext(
                userId="user-1",
                novelId="novel-1",
                taskId="task-failure",
                runId="run-failure",
                agentId="写作",
            ),
        )

    written = workflow_log.finish_run("run-failure", "错误").read_text(encoding="utf-8")
    assert '"type":"model_failure"' in written
    assert "M01 模型调用失败" in written
    assert "任务标识：task-failure" in written
    assert "运行标识：run-failure" in written
    assert "错误分类：timeout_error" in written
    assert "异常类型：ProviderTransportError" in written
    assert "供应商请求标识：provider-request-123" in written
    assert "消息数：1" in written
    assert "工具数：1" in written
    assert "请求输出上限：4096" in written
    assert private_prompt not in written
    assert "SECRET_TOOL_MUST_NOT_LEAK" not in written


@pytest.mark.parametrize(
    ("reasoning_tokens", "expected_visible", "expected_text"),
    [(4, 16, "可见输出 Token：16"), (None, None, "可见输出 Token：未提供")],
)
def test_human_log_header_and_text_derive_visible_completion_tokens(
    tmp_path: Path,
    reasoning_tokens: int | None,
    expected_visible: int | None,
    expected_text: str,
) -> None:
    workflow_log = HumanWorkflowLog(tmp_path)
    workflow_log.start_run(
        run_id="run-visible",
        task_id="task-visible",
        run_kind="诊断测试",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )
    workflow_log.record_model_call(
        ModelCallLogRecord(
            context=ModelCallContext(
                userId="user-1",
                novelId="novel-1",
                taskId="task-visible",
                runId="run-visible",
                agentId="校验",
            ),
            provider="openai_compatible",
            model="deepseek-v4-flash",
            billingRequestId=None,
            messages=[{"role": "user", "content": "测试"}],
            output="完成",
            usage=ModelUsage(
                promptTokens=10,
                cachedTokens=0,
                completionTokens=20,
                totalTokens=30,
            ),
            finishReason="stop",
            rawFinishReason="stop",
            policyId="v1:quality-no-thinking",
            thinkingMode="disabled",
            reasoningTokens=reasoning_tokens,
        )
    )
    written = workflow_log.finish_run("run-visible", "完成").read_text(encoding="utf-8")
    expected_json = (
        '"visibleCompletionTokens":null'
        if expected_visible is None
        else f'"visibleCompletionTokens":{expected_visible}'
    )
    assert expected_json in written
    assert expected_text in written
