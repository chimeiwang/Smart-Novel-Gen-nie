from __future__ import annotations

from typing import Annotated

from fastapi import Body, HTTPException
from fastapi.testclient import TestClient
from inkforge_core.app import create_app
from inkforge_core.errors import ApiError
from pydantic import BaseModel, Field


class PositivePayload(BaseModel):
    count: Annotated[int, Field(gt=0)]


def assert_stable_error_envelope(response_body: dict[str, object]) -> None:
    assert set(response_body) == {"code", "message", "details", "requestId"}


def test_not_found_uses_exact_stable_error_envelope() -> None:
    response = TestClient(create_app(testing=True)).get(
        "/api/v1/not-found",
        headers={"X-Request-ID": "request-not-found"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "请求的资源不存在",
        "details": None,
        "requestId": "request-not-found",
    }
    assert response.headers["X-Request-ID"] == response.json()["requestId"]


def test_api_error_preserves_business_details() -> None:
    app = create_app(testing=True)

    @app.get("/api/v1/testing/api-error")
    async def raise_api_error() -> None:
        raise ApiError(
            status_code=409,
            code="ARTIFACT_CONFLICT",
            message="草案状态已变化",
            details={"artifactId": "artifact-1"},
        )

    response = TestClient(app).get(
        "/api/v1/testing/api-error",
        headers={"X-Request-ID": "request-conflict"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "ARTIFACT_CONFLICT",
        "message": "草案状态已变化",
        "details": {"artifactId": "artifact-1"},
        "requestId": "request-conflict",
    }


def test_request_validation_error_keeps_path_and_chinese_message() -> None:
    app = create_app(testing=True)

    @app.post("/api/v1/testing/positive")
    async def require_positive(payload: Annotated[PositivePayload, Body()]) -> PositivePayload:
        return payload

    response = TestClient(app).post(
        "/api/v1/testing/positive",
        json={"count": 0},
        headers={"X-Request-ID": "request-validation"},
    )

    assert response.status_code == 422
    body = response.json()
    assert_stable_error_envelope(body)
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "请求参数校验失败"
    assert body["requestId"] == "request-validation"
    assert body["details"] == [
        {
            "path": ["body", "count"],
            "message": "输入值必须大于 0",
            "type": "greater_than",
        }
    ]


def test_http_exception_uses_stable_error_envelope() -> None:
    app = create_app(testing=True)

    @app.get("/api/v1/testing/http-error")
    async def raise_http_error() -> None:
        raise HTTPException(status_code=403, detail="没有访问权限")

    response = TestClient(app).get("/api/v1/testing/http-error")

    assert response.status_code == 403
    body = response.json()
    assert_stable_error_envelope(body)
    assert body["code"] == "HTTP_ERROR"
    assert body["message"] == "没有访问权限"
    assert body["details"] is None
    assert response.headers["X-Request-ID"] == body["requestId"]


def test_unhandled_exception_hides_internal_text() -> None:
    app = create_app(testing=True)

    @app.get("/api/v1/testing/crash")
    async def crash() -> None:
        raise RuntimeError("数据库密码 secret-value 泄露")

    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/testing/crash",
        headers={"X-Request-ID": "request-crash"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body == {
        "code": "INTERNAL_SERVER_ERROR",
        "message": "服务器内部错误",
        "details": None,
        "requestId": "request-crash",
    }
    assert "secret-value" not in response.text
    assert response.headers["X-Request-ID"] == body["requestId"]
