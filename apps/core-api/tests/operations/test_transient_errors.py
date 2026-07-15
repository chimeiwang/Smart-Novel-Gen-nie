from __future__ import annotations

import httpx
import pytest
from inkforge_contracts.jobs import AgentJobAccepted
from inkforge_core.errors import ApiError
from inkforge_core.operations.transient_errors import (
    is_transient_infrastructure_error,
)
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError


def _agent_submit_error(cause: Exception) -> ApiError:
    error = ApiError(
        status_code=503,
        code="AGENT_RUN_SUBMIT_FAILED",
        message="智能体运行提交失败",
    )
    error.__cause__ = cause
    return error


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://agent.example/internal/v1/runs")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("智能体服务响应失败", request=request, response=response)


@pytest.mark.parametrize(
    "error",
    [
        ConnectionError("连接中断"),
        TimeoutError("连接超时"),
        OperationalError("SELECT 1", {}, ConnectionError("数据库断开")),
        _agent_submit_error(
            httpx.ConnectError(
                "智能体服务暂时不可用",
                request=httpx.Request("POST", "https://agent.example/internal/v1/runs"),
            )
        ),
        _agent_submit_error(_http_status_error(503)),
    ],
)
def test_transient_infrastructure_errors_are_retryable(error: Exception) -> None:
    assert is_transient_infrastructure_error(error) is True


def test_deterministic_and_unknown_errors_are_not_retryable() -> None:
    with pytest.raises(ValidationError) as captured:
        AgentJobAccepted.model_validate({})

    assert is_transient_infrastructure_error(TypeError("调用契约错误")) is False
    assert is_transient_infrastructure_error(captured.value) is False
    assert is_transient_infrastructure_error(RuntimeError("未知程序错误")) is False
    assert is_transient_infrastructure_error(
        _agent_submit_error(ValueError("响应契约错误"))
    ) is False
    assert is_transient_infrastructure_error(
        _agent_submit_error(_http_status_error(400))
    ) is False
