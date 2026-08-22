from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from inkforge_agents.app import create_app
from inkforge_agents.observability import HumanWorkflowLog
from inkforge_agents.providers.base import ModelUsage
from inkforge_agents.runtime.model_runtime import ModelCallContext, ModelCallLogRecord
from inkforge_contracts.jwt_claims import ServiceScope


class Verifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def verify_request(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        return object()


def _headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer signed",
        "Idempotency-Key": "debug-request-1",
        "X-InkForge-Timestamp": "1",
        "X-InkForge-Body-SHA256": "0" * 64,
    }


def test_signed_debug_api_filters_user_and_returns_complete_content(tmp_path: Path) -> None:
    workflow_log = HumanWorkflowLog(tmp_path)
    workflow_log.start_run(
        run_id="run-1",
        task_id="task-1",
        run_kind="初次运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
    )
    workflow_log.record_model_call(
        ModelCallLogRecord(
            context=ModelCallContext(
                userId="user-1",
                novelId="novel-1",
                taskId="task-1",
                runId="run-1",
                agentId="写作",
            ),
            provider="openai_compatible",
            model="deepseek-v4-flash",
            billingRequestId="billing-request-1",
            messages=[{"role": "user", "content": "完整请求"}],
            output="完整响应",
            usage=ModelUsage(
                promptTokens=10,
                cachedTokens=2,
                completionTokens=20,
                totalTokens=30,
            ),
            finishReason="stop",
            rawFinishReason="stop",
        )
    )
    workflow_log.finish_run("run-1", "完成")
    verifier = Verifier()
    client = TestClient(
        create_app(
            testing=True,
            core_request_verifier=verifier,
            workflow_log=workflow_log,
        ),
        client=("127.0.0.1", 50000),
    )

    listed = client.get(
        "/internal/v1/debug/workflow-runs",
        params={"userId": "user-1"},
        headers=_headers(),
    )
    detail = client.get(
        "/internal/v1/debug/workflow-runs/run-1",
        params={"userId": "user-1"},
        headers={**_headers(), "Idempotency-Key": "debug-request-2"},
    )

    assert listed.status_code == 200
    assert [item["runId"] for item in listed.json()["runs"]] == ["run-1"]
    assert detail.status_code == 200
    assert "完整请求" in detail.json()["content"]
    assert "完整响应" in detail.json()["content"]
    assert "任务标识：task-1" in detail.json()["content"]
    assert "运行标识：run-1" in detail.json()["content"]
    assert "计费请求标识：billing-request-1" in detail.json()["content"]
    assert "模型：openai_compatible/deepseek-v4-flash" in detail.json()["content"]
    assert "Token 消耗：输入 10 | 缓存 2 | 输出 20 | 合计 30" in detail.json()["content"]
    assert "grantToken" not in detail.json()["content"]
    assert verifier.calls[0]["required_scope"] is ServiceScope.AGENT_DEBUG_READ
    assert verifier.calls[0]["query_string"] == b"userId=user-1"


def test_debug_api_rejects_missing_service_identity(tmp_path: Path) -> None:
    response = TestClient(
        create_app(
            testing=True,
            core_request_verifier=Verifier(),
            workflow_log=HumanWorkflowLog(tmp_path),
        ),
        client=("127.0.0.1", 50000),
    ).get("/internal/v1/debug/workflow-runs", params={"userId": "user-1"})

    assert response.status_code == 401
