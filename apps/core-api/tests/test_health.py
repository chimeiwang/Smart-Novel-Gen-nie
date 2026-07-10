from __future__ import annotations

from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from inkforge_core.app import create_app


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


@pytest.mark.parametrize(
    "request_id",
    [" ", "a" * 129, "contains\x00control", "contains\x1fcontrol", "contains\x7fcontrol"],
)
def test_invalid_request_id_is_replaced_with_uuid(
    client: TestClient, request_id: str
) -> None:
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
