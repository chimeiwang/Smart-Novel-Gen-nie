from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
import pytest
from inkforge_agents.execution.callbacks import (
    ExecutionCallbackClient,
    ExecutionCallbackError,
)
from inkforge_contracts.execution import (
    ExecutionCallbackReceipt,
    ExecutionStepProgress,
    ExecutionStepResult,
    StepUsage,
)
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_service_auth import SignedServiceRequest

from .support import execution_request, execution_result, resolved_model


class Signer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def sign_request(self, **kwargs: object) -> SignedServiceRequest:
        self.calls.append(dict(kwargs))
        return SignedServiceRequest(
            token="signed",  # noqa: S106
            headers={
                "Authorization": "Bearer signed",
                "Idempotency-Key": str(kwargs["idempotency_key"]),
                "X-InkForge-Timestamp": "1",
                "X-InkForge-Body-SHA256": "0" * 64,
            },
        )


def _progress() -> ExecutionStepProgress:
    request = execution_request()
    return ExecutionStepProgress(
        protocolVersion="2.0",
        progressId="progress-1",
        jobId=request.jobId,
        runId=request.runId,
        novelId=request.novelId,
        stepId=request.stepId,
        fencingToken=request.fencingToken,
        requestHash=request.requestHash,
        resolvedModel=resolved_model(),
        sequence=1,
        phase="preparing",
        progressCode="execution.preparing",
        elapsedSeconds=0,
        waitingOnProvider=False,
        usage=StepUsage(
            usageStatus="unknown",
            providerAttempts=0,
            protocolCorrections=0,
            wallTimeMillis=0,
        ),
        occurredAt=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_progress_uses_exact_path_scope_and_nullable_resource_binding() -> None:
    signer = Signer()
    progress = _progress()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            request=request,
            json=_receipt(progress, status="duplicate").model_dump(mode="json"),
        )

    http = httpx.AsyncClient(
        base_url="http://core.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        receipt = await ExecutionCallbackClient(http, signer).send_progress(progress)
    finally:
        await http.aclose()

    assert receipt.status == "duplicate"
    assert requests[0].method == "PUT"
    assert requests[0].url.path == ("/internal/v1/workflow-runs/run-1/steps/step-1/progress")
    assert json.loads(requests[0].content)["progressId"] == progress.progressId
    assert signer.calls[0]["scope"] == (ServiceScope.EXECUTION_PROGRESS,)
    assert signer.calls[0]["task_id"] == progress.stepId
    assert signer.calls[0]["novel_id"] == progress.novelId


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "retryable"),
    [
        (401, False),
        (409, False),
        (408, True),
        (425, True),
        (429, True),
        (500, True),
        (503, True),
    ],
)
async def test_callback_http_errors_have_fixed_retry_boundary(
    status_code: int,
    retryable: bool,
) -> None:
    progress = _progress()
    http = httpx.AsyncClient(
        base_url="http://core.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(status_code, request=request)),
    )
    try:
        with pytest.raises(ExecutionCallbackError) as captured:
            await ExecutionCallbackClient(http, Signer()).send_progress(progress)
    finally:
        await http.aclose()

    assert captured.value.retryable is retryable


@pytest.mark.asyncio
async def test_terminal_receipt_identity_mismatch_is_permanent_rejection() -> None:
    result = execution_result(execution_request())
    receipt = _receipt(result, status="accepted").model_copy(update={"jobId": "other-job"})
    http = httpx.AsyncClient(
        base_url="http://core.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                json=receipt.model_dump(mode="json"),
            )
        ),
    )
    try:
        with pytest.raises(ExecutionCallbackError) as captured:
            await ExecutionCallbackClient(http, Signer()).send_result(result)
    finally:
        await http.aclose()

    assert captured.value.code == "EXECUTION_CALLBACK_RECEIPT_MISMATCH"
    assert captured.value.retryable is False


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [201, 202, 204, 302])
async def test_only_exact_http_200_can_confirm_terminal_receipt(
    status_code: int,
) -> None:
    result = execution_result(execution_request())
    http = httpx.AsyncClient(
        base_url="http://core.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code, request=request)
        ),
    )
    try:
        with pytest.raises(ExecutionCallbackError) as captured:
            await ExecutionCallbackClient(http, Signer()).send_result(result)
    finally:
        await http.aclose()

    assert captured.value.code == "EXECUTION_CALLBACK_RECEIPT_INVALID"
    assert captured.value.retryable is True


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"", b'{"protocolVersion":"2.0"'])
async def test_truncated_or_malformed_http_200_receipt_is_retryable(body: bytes) -> None:
    result = execution_result(execution_request())
    http = httpx.AsyncClient(
        base_url="http://core.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, content=body)
        ),
    )
    try:
        with pytest.raises(ExecutionCallbackError) as captured:
            await ExecutionCallbackClient(http, Signer()).send_result(result)
    finally:
        await http.aclose()

    assert captured.value.code == "EXECUTION_CALLBACK_RECEIPT_INVALID"
    assert captured.value.retryable is True


def _receipt(
    callback: ExecutionStepProgress | ExecutionStepResult,
    *,
    status: Literal["accepted", "duplicate", "stale", "superseded"],
) -> ExecutionCallbackReceipt:
    return ExecutionCallbackReceipt(
        protocolVersion="2.0",
        runId=callback.runId,
        stepId=callback.stepId,
        jobId=callback.jobId,
        fencingToken=callback.fencingToken,
        requestHash=callback.requestHash,
        status=status,
        receivedAt=datetime.now(UTC),
    )
