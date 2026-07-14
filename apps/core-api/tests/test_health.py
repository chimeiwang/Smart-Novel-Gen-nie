from __future__ import annotations

import asyncio
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from inkforge_core.app import create_app
from inkforge_core.http import get_request_id


class Reconciler:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        self.started = True
        await self.stop_event.wait()

    def request_stop(self) -> None:
        self.stopped = True
        self.stop_event.set()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(testing=True))


def test_live_returns_exact_response_without_external_dependencies(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "core-api"}


def test_ready_reports_loaded_test_configuration(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "core-api",
        "checks": {"configuration": "ok"},
    }


def test_core_lifespan_starts_and_stops_writing_reconciler() -> None:
    reconciler = Reconciler()
    app = create_app(testing=True, writing_reconciler=reconciler)

    with TestClient(app) as client:
        assert client.get("/api/v1/health/live").status_code == 200
        assert reconciler.started is True

    assert reconciler.stopped is True


def test_core_lifespan_starts_and_stops_command_dispatcher() -> None:
    dispatcher = Reconciler()
    app = create_app(testing=True, writing_command_dispatcher=dispatcher)

    with TestClient(app) as client:
        assert client.get("/api/v1/health/live").status_code == 200
        assert dispatcher.started is True

    assert dispatcher.stopped is True


def test_ready_aggregates_sync_and_async_checks_and_returns_503_on_failure() -> None:
    app = create_app(testing=True)

    async def schema_check() -> bool:
        await asyncio.sleep(0)
        return True

    app.state.readiness_checks = {
        "configuration": lambda: True,
        "database": lambda: False,
        "schema": schema_check,
    }

    response = TestClient(app).get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "service": "core-api",
        "checks": {
            "configuration": "ok",
            "database": "failed",
            "schema": "ok",
        },
    }
    document = app.openapi()
    schema = document["paths"]["/api/v1/health/ready"]["get"]["responses"]["503"]["content"][
        "application/json"
    ]["schema"]
    assert schema == {"$ref": "#/components/schemas/ReadyHealthResponse"}


def test_missing_request_id_generates_uuid(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    request_id = response.headers["X-Request-ID"]
    assert str(UUID(request_id)) == request_id


def test_valid_request_id_is_trimmed_and_preserved(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": "  upstream-request-42  "},
    )

    assert response.headers["X-Request-ID"] == "upstream-request-42"


async def test_request_id_context_is_isolated_between_concurrent_asgi_requests() -> None:
    app = create_app(testing=True)
    barrier = asyncio.Barrier(2)

    @app.get("/api/v1/testing/request-id-context")
    async def read_request_id_after_wait() -> dict[str, str]:
        await barrier.wait()
        await asyncio.sleep(0)
        return {"requestId": get_request_id()}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first_response, second_response = await asyncio.gather(
            client.get(
                "/api/v1/testing/request-id-context",
                headers={"X-Request-ID": "concurrent-first"},
            ),
            client.get(
                "/api/v1/testing/request-id-context",
                headers={"X-Request-ID": "concurrent-second"},
            ),
        )

    assert first_response.json() == {"requestId": "concurrent-first"}
    assert second_response.json() == {"requestId": "concurrent-second"}
    assert first_response.headers["X-Request-ID"] == "concurrent-first"
    assert second_response.headers["X-Request-ID"] == "concurrent-second"

    request_id_after_completion = get_request_id()
    assert request_id_after_completion not in {"concurrent-first", "concurrent-second"}
    assert str(UUID(request_id_after_completion)) == request_id_after_completion


@pytest.mark.parametrize(
    "request_id",
    [" ", "a" * 129, "contains\x00control", "contains\x1fcontrol", "contains\x7fcontrol"],
)
def test_invalid_request_id_is_replaced_with_uuid(client: TestClient, request_id: str) -> None:
    response = client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": request_id},
    )

    generated = response.headers["X-Request-ID"]
    assert generated != request_id.strip()
    assert str(UUID(generated)) == generated


def test_all_routes_are_versioned_and_openapi_can_be_generated(client: TestClient) -> None:
    response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    document = response.json()
    assert document["info"]["title"] == "InkForge Core API"
    assert document["info"]["version"] == "0.1.0"
    app = cast(FastAPI, client.app)
    route_paths = [route.path for route in app.routes if hasattr(route, "path")]
    assert all(path.startswith("/api/v1") for path in route_paths)
