from __future__ import annotations

import pytest
from inkforge_agents.runtime.errors import (
    ModelExecutionError,
    ProviderTransportError,
    ReviewExecutionError,
    UnknownJobExecutionError,
)


def test_safe_to_retry_implies_retryable() -> None:
    with pytest.raises(ValueError, match="safeToRetry"):
        ModelExecutionError(
            code="MODEL_PROVIDER_FAILED",
            category="provider",
            stage="reviewer",
            retryable=False,
            safeToRetry=True,
            publicMessage="模型供应商调用失败",
        )


def test_model_execution_error_keeps_typed_failure_fields() -> None:
    error = ReviewExecutionError(
        code="REVIEW_SUBMISSION_FAILED",
        category="protocol",
        stage="reviewer",
        retryable=True,
        safeToRetry=True,
        publicMessage="复审提交失败",
        requestId="request-1",
        usageReported=True,
    )

    assert str(error) == "复审提交失败"
    assert error.code == "REVIEW_SUBMISSION_FAILED"
    assert error.category == "protocol"
    assert error.stage == "reviewer"
    assert error.retryable is True
    assert error.safeToRetry is True
    assert error.requestId == "request-1"
    assert error.usageReported is True


def test_provider_transport_error_exposes_retry_flags() -> None:
    error = ProviderTransportError(
        "供应商连接中断",
        retryable=True,
        safe_to_retry=True,
    )

    assert str(error) == "供应商连接中断"
    assert error.retryable is True
    assert error.safe_to_retry is True


def test_unknown_job_error_is_runtime_error() -> None:
    assert isinstance(UnknownJobExecutionError("未知任务"), RuntimeError)
