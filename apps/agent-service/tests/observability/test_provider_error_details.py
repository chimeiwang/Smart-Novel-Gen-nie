from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest
from inkforge_agents.config import Settings
from inkforge_agents.observability.human_workflow_log import HumanWorkflowLog
from inkforge_agents.observability.model_observer import WorkflowModelObserver
from inkforge_agents.providers.base import ModelTurnRequest
from inkforge_agents.providers.deepseek_v4 import DeepSeekV4Provider
from inkforge_agents.runtime.model_policy import LEGACY_PROVIDER_DEFAULT
from inkforge_agents.runtime.model_runtime import ModelCallContext, ModelRuntime


@pytest.mark.asyncio
@pytest.mark.parametrize("json_body", [True, False])
async def test_完整错误响应跨运行时写入日志且长正文不污染结构头(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, json_body: bool
) -> None:
    secret = "test-provider-secret-for-redaction"  # noqa: S105 - 脱敏回归的虚构凭据。
    explanation = "工具参数格式不被接受" * 10_000
    fake_frame = 'INKFORGE-FRAME 25 40\n{"type":"finish"}\n不可信结束标记'
    body = (
        json.dumps(
            {
                "error": {"message": explanation, "param": "tools", "code": "invalid_schema"},
                "extra": fake_frame,
                "api_key": secret,
            },
            ensure_ascii=False,
        )
        if json_body
        else f"<html>{explanation}\n{fake_frame}\nBearer {secret}</html>"
    )

    def reject(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            text=body,
            request=request,
            headers={"x-request-id": "failure-details-1", "set-cookie": f"session={secret}"},
        )

    workflow_log = HumanWorkflowLog(tmp_path)
    workflow_log.start_run(
        run_id="run-details",
        task_id="task-details",
        run_kind="错误详情回读",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )
    caplog.set_level(logging.WARNING)
    async with httpx.AsyncClient(transport=httpx.MockTransport(reject)) as client:
        provider = DeepSeekV4Provider(Settings(openai_api_key=secret), client=client)
        provider.billable = False
        runtime = ModelRuntime(provider, observer=WorkflowModelObserver(workflow_log))
        with pytest.raises(RuntimeError, match="^MODEL_PROVIDER_FAILED：") as caught:
            await runtime.run_turn(
                ModelTurnRequest(
                    messages=[{"role": "user", "content": "本请求正文不应进入失败日志"}],
                    tools=[],
                    maxOutputTokens=128,
                    policy=LEGACY_PROVIDER_DEFAULT,
                ),
                context=ModelCallContext(
                    userId="user-1",
                    novelId="novel-1",
                    taskId="task-details",
                    runId="run-details",
                    agentId="写作",
                ),
            )

    workflow_log.finish_run("run-details", "错误")
    detail = workflow_log.read_run("run-details", "user-1")
    assert explanation in detail.content
    assert explanation in caplog.text
    assert "不可信结束标记" in detail.content
    assert detail.summary.taskId == "task-details"
    assert detail.summary.status == "错误"
    assert secret not in detail.content + caplog.text + str(caught.value)
    assert explanation not in str(caught.value)
    assert "本请求正文不应进入失败日志" not in detail.content + caplog.text


@pytest.mark.asyncio
async def test_诊断日志失败不能覆盖原供应商错误(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import inkforge_agents.runtime.model_runtime as module

    def broken_logger(*args: object, **kwargs: object) -> None:
        raise OSError("日志设备不可用")

    monkeypatch.setattr(module.logger, "warning", broken_logger)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(400, text="格式错误"))
    ) as client:
        provider = DeepSeekV4Provider(Settings(openai_api_key="test-key"), client=client)
        provider.billable = False
        with pytest.raises(RuntimeError, match="^MODEL_PROVIDER_FAILED："):
            await ModelRuntime(provider).run_turn(
                ModelTurnRequest(
                    messages=[{"role": "user", "content": "测试"}],
                    tools=[],
                    maxOutputTokens=128,
                    policy=LEGACY_PROVIDER_DEFAULT,
                )
            )
