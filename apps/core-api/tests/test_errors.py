from __future__ import annotations

import logging
from typing import Annotated

import pytest
from fastapi import Body, HTTPException
from fastapi.testclient import TestClient
from inkforge_core.app import create_app
from inkforge_core.errors import ApiError
from pydantic import BaseModel, Field


class PositivePayload(BaseModel):
    count: Annotated[int, Field(gt=0)]


def assert_stable_error_envelope(response_body: dict[str, object]) -> None:
    assert set(response_body) == {"code", "message", "details", "requestId"}


def test_public_routes_document_the_stable_error_response() -> None:
    app = create_app(testing=True)

    @app.get("/api/v1/example")
    async def example() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app)

    document = client.get("/api/v1/openapi.json").json()
    for path in ("/api/v1/health/live", "/api/v1/health/ready", "/api/v1/example"):
        responses = document["paths"][path]["get"]["responses"]
        for status_code in ("400", "401", "403", "404", "409", "422", "500", "default"):
            schema = responses[status_code]["content"]["application/json"]["schema"]
            assert schema == {"$ref": "#/components/schemas/ErrorResponse"}
        assert "HTTPValidationError" not in str(responses["422"])


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


@pytest.mark.parametrize(
    ("status_code", "public_message"),
    [
        (400, "请求格式错误"),
        (401, "身份认证失败"),
        (403, "没有访问权限"),
        (404, "请求的资源不存在"),
        (405, "请求方法不被允许"),
        (409, "请求状态冲突"),
        (422, "请求参数校验失败"),
        (418, "请求处理失败"),
    ],
)
def test_http_exception_hides_detail_and_uses_fixed_chinese_message(
    status_code: int,
    public_message: str,
) -> None:
    app = create_app(testing=True)

    @app.get("/api/v1/testing/http-error")
    async def raise_http_error() -> None:
        raise HTTPException(status_code=status_code, detail="数据库密码 secret")

    response = TestClient(app).get("/api/v1/testing/http-error")

    assert response.status_code == status_code
    body = response.json()
    assert_stable_error_envelope(body)
    assert body["message"] == public_message
    assert body["details"] is None
    assert "secret" not in response.text
    assert response.headers["X-Request-ID"] == body["requestId"]


def test_unhandled_exception_hides_internal_text_and_logs_safe_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(testing=True)
    internal_message = "连接 postgres://user:secret@database:5432/inkforge 失败"

    @app.get("/api/v1/testing/crash")
    async def crash() -> None:
        raise RuntimeError(internal_message)

    with caplog.at_level(logging.ERROR, logger="inkforge_core.errors"):
        response = TestClient(app).get(
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
    assert internal_message not in response.text
    assert "secret" not in response.text
    assert response.headers["X-Request-ID"] == body["requestId"]
    assert internal_message not in caplog.text
    assert "secret" not in caplog.text
    error_record = caplog.records[-1]
    assert error_record.getMessage() == "接口发生未处理异常"
    assert error_record.__dict__["requestId"] == "request-crash"
    assert error_record.__dict__["code"] == "INTERNAL_SERVER_ERROR"
    assert error_record.__dict__["exceptionType"] == "RuntimeError"
