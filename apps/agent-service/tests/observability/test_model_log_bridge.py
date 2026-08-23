from __future__ import annotations

from pathlib import Path

import pytest
from inkforge_agents.observability.human_workflow_log import HumanWorkflowLog
from inkforge_agents.observability.model_observer import WorkflowModelObserver
from inkforge_agents.providers.base import (
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
)
from inkforge_agents.runtime.model_policy import LEGACY_PROVIDER_DEFAULT
from inkforge_agents.runtime.model_runtime import ModelCallContext, ModelRuntime


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
            toolCalls=[],
            usage=ModelUsage(
                promptTokens=10,
                cachedTokens=0,
                completionTokens=20,
                totalTokens=30,
            ),
            finishReason="length",
            rawFinishReason="max_tokens",
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

    written = workflow_log.finish_run("run-bridge", "错误").read_text(
        encoding="utf-8"
    )
    assert request_text in written
    assert output_text in written
    assert "任务标识：task-bridge" in written
    assert "运行标识：run-bridge" in written
    assert "计费请求标识：无" in written
    assert "模型：bridge-test/bridge-test-model" in written
    assert "Token 消耗：输入 10 | 缓存 0 | 输出 20 | 合计 30" in written
    assert "完成原因：length" in written
    assert "供应商原始原因：max_tokens" in written
    assert "grantToken" not in written
