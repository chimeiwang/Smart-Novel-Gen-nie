from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from inkforge_core.auth.dependencies import get_current_user
from inkforge_core.auth.repository import AuthUser
from inkforge_core.config import create_testing_settings
from inkforge_core.debug.router import router
from inkforge_core.errors import install_exception_handlers


class AgentDebugClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def get_workflow_runs(self, user_id: str, run_id: str | None = None) -> object:
        self.calls.append((user_id, run_id))
        summary = {
            "runId": run_id or "run-1",
            "taskId": "task-1",
            "runKind": "初次运行",
            "userId": "user-1",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "startedAt": "2026-07-11T00:00:00Z",
            "endedAt": "2026-07-11T00:01:00Z",
            "status": "完成",
        }
        if run_id is None:
            return {"runs": [summary]}
        return {"summary": summary, "content": "完整日志"}


def _app(*, enabled: bool = True) -> tuple[FastAPI, AgentDebugClient]:
    app = FastAPI()
    settings = create_testing_settings().model_copy(
        update={"workflow_event_debug_enabled": enabled}
    )
    client = AgentDebugClient()
    app.state.settings = settings
    app.state.agent_client = client
    install_exception_handlers(app)
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="user-1",
        username="alice",
        password_hash="",
        credit_balance_micros=0,
    )
    app.include_router(router, prefix="/api/v1")
    return app, client


def test_browser_debug_api_forwards_authenticated_user_only() -> None:
    app, agent = _app()
    client = TestClient(app)

    listed = client.get("/api/v1/debug/workflow-runs")
    detail = client.get("/api/v1/debug/workflow-runs/run-1")

    assert listed.status_code == 200
    assert detail.status_code == 200
    assert detail.json()["content"] == "完整日志"
    assert agent.calls == [("user-1", None), ("user-1", "run-1")]


def test_browser_debug_api_is_hidden_when_disabled() -> None:
    app, agent = _app(enabled=False)

    response = TestClient(app).get("/api/v1/debug/workflow-runs")

    assert response.status_code == 404
    assert agent.calls == []
