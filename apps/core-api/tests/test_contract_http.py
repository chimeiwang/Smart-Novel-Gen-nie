from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from inkforge_contracts import AgentEvent  # type: ignore[import-untyped]
from inkforge_core.app import create_app


def create_contract_client() -> TestClient:
    app = create_app(testing=True)

    @app.post("/api/v1/testing/agent-event", response_model=AgentEvent)
    async def echo_agent_event(event: AgentEvent) -> AgentEvent:
        return event

    return TestClient(app)


def valid_event() -> AgentEvent:
    return AgentEvent(
        protocolVersion="1.0",
        eventId="event-1",
        runId="run-1",
        taskId="task-1",
        sequence=1,
        event="agent_started",
        data={"agentId": "写作", "attempt": 1},
        occurredAt=datetime(2026, 7, 10, 8, 30, tzinfo=UTC),
    )


def test_agent_event_round_trips_through_fastapi_json() -> None:
    event = valid_event()

    response = create_contract_client().post(
        "/api/v1/testing/agent-event",
        json=event.model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json() == event.model_dump(mode="json")
    assert response.json()["occurredAt"] == "2026-07-10T08:30:00Z"


def test_naive_event_time_returns_stable_validation_envelope() -> None:
    payload = valid_event().model_dump(mode="json")
    payload["occurredAt"] = "2026-07-10T08:30:00"

    response = create_contract_client().post(
        "/api/v1/testing/agent-event",
        json=payload,
        headers={"X-Request-ID": "request-contract-validation"},
    )

    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"code", "message", "details", "requestId"}
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "请求参数校验失败"
    assert body["requestId"] == "request-contract-validation"
    assert body["details"] == [
        {
            "path": ["body", "occurredAt"],
            "message": "日期时间必须包含时区信息",
            "type": "timezone_aware",
        }
    ]
    assert response.headers["X-Request-ID"] == body["requestId"]
