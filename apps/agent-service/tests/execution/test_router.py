from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from inkforge_agents.app import create_app
from inkforge_agents.config import Settings
from inkforge_agents.execution.service import (
    ExecutionAdmissionSaturatedError,
    ExecutionServiceHealth,
    ExecutionServiceUnavailableError,
)
from inkforge_contracts.execution import (
    ExecutionCancelAccepted,
    ExecutionCancelRequest,
    ExecutionStepAccepted,
    ExecutionStepRequest,
)
from inkforge_contracts.jwt_claims import ServiceScope

from .support import execution_cancel, execution_request, rehash_request, resolved_model


class Verifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def verify_request(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        return object()


class Service:
    def __init__(
        self,
        *,
        ready: bool = True,
        saturated: bool = False,
        unavailable: bool = False,
    ) -> None:
        self.submissions: list[ExecutionStepRequest] = []
        self.cancellations: list[ExecutionCancelRequest] = []
        self.ready = ready
        self.saturated = saturated
        self.unavailable = unavailable

    async def submit(self, request: ExecutionStepRequest) -> ExecutionStepAccepted:
        self.submissions.append(request)
        if self.saturated:
            raise ExecutionAdmissionSaturatedError("测试 admission 饱和")
        if self.unavailable:
            raise ExecutionServiceUnavailableError(
                "EXECUTION_CALLBACK_REJECTED_BACKLOG"
            )
        return ExecutionStepAccepted(
            protocolVersion="2.0",
            jobId=request.jobId,
            runId=request.runId,
            novelId=request.novelId,
            stepId=request.stepId,
            fencingToken=request.fencingToken,
            requestHash=request.requestHash,
            resolvedModel=resolved_model(),
            status="queued",
            acceptedAt=datetime.now(UTC),
        )

    async def cancel(self, request: ExecutionCancelRequest) -> ExecutionCancelAccepted:
        self.cancellations.append(request)
        return ExecutionCancelAccepted(
            protocolVersion="2.0",
            cancelRequestId=request.cancelRequestId,
            runId=request.runId,
            novelId=request.novelId,
            stepId=request.stepId,
            jobId=request.jobId,
            fencingToken=request.fencingToken,
            status="accepted",
            acceptedAt=datetime.now(UTC),
        )

    async def close(self) -> None:
        pass

    async def health(self) -> ExecutionServiceHealth:
        return ExecutionServiceHealth(
            ready=self.ready,
            callback_pending=2 if not self.ready else 0,
            callback_rejected=1 if not self.ready else 0,
            error_code=("EXECUTION_CALLBACK_REJECTED_BACKLOG" if not self.ready else None),
            admission_active=3 if self.saturated else 1,
            admission_capacity=3,
            admission_saturated=self.saturated,
        )


def _client(service: Service, verifier: Verifier) -> TestClient:
    return TestClient(
        create_app(
            testing=True,
            execution_service=service,  # type: ignore[arg-type]
            core_request_verifier=verifier,
        ),
        client=("127.0.0.1", 50_000),
    )


def _headers(idempotency_key: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer signed",
        "Idempotency-Key": idempotency_key,
        "X-InkForge-Timestamp": "1",
        "X-InkForge-Body-SHA256": "0" * 64,
    }


def test_submit_uses_exact_execution_scope_and_step_resource_binding() -> None:
    service = Service()
    verifier = Verifier()
    body = execution_request()

    with _client(service, verifier) as client:
        response = client.post(
            "/internal/v1/executions",
            json=body.model_dump(mode="json", by_alias=True),
            headers=_headers(body.idempotencyKey),
        )

    assert response.status_code == 202
    assert response.json()["resolvedModel"] == resolved_model().model_dump(mode="json")
    assert service.submissions == [body]
    assert verifier.calls[0]["required_scope"] == ServiceScope.EXECUTION_SUBMIT
    assert verifier.calls[0]["task_id"] == body.stepId
    assert verifier.calls[0]["run_id"] == body.runId
    assert verifier.calls[0]["novel_id"] == body.novelId


def test_unhealthy_execution_gate_returns_retryable_503_not_conflict() -> None:
    service = Service(ready=False, unavailable=True)
    verifier = Verifier()
    body = execution_request()

    with _client(service, verifier) as client:
        response = client.post(
            "/internal/v1/executions",
            json=body.model_dump(mode="json", by_alias=True),
            headers=_headers(body.idempotencyKey),
        )

    assert response.status_code == 503
    assert "保护门" in response.json()["detail"]
    assert response.status_code != 409


def test_submit_accepts_explicit_null_novel_but_rejects_header_drift() -> None:
    service = Service()
    verifier = Verifier()
    body = rehash_request(execution_request().model_copy(update={"novelId": None}))

    with _client(service, verifier) as client:
        response = client.post(
            "/internal/v1/executions",
            json=body.model_dump(mode="json", by_alias=True),
            headers=_headers("different-idempotency-key"),
        )

    assert response.status_code == 409
    assert service.submissions == []
    assert verifier.calls[0]["novel_id"] is None


def test_new_execution_saturation_returns_retryable_503() -> None:
    service = Service(saturated=True)
    verifier = Verifier()
    body = execution_request()

    with _client(service, verifier) as client:
        response = client.post(
            "/internal/v1/executions",
            json=body.model_dump(mode="json", by_alias=True),
            headers=_headers(body.idempotencyKey),
        )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert response.json() == {
        "protocolVersion": "2.0",
        "errorCode": "EXECUTION_ADMISSION_SATURATED",
        "retryable": True,
        "retryAfterSeconds": 1,
    }


def test_cancel_uses_put_path_and_requires_path_body_job_identity() -> None:
    service = Service()
    verifier = Verifier()
    cancel = execution_cancel(execution_request())

    with _client(service, verifier) as client:
        accepted = client.put(
            f"/internal/v1/executions/{cancel.jobId}/cancel",
            json=cancel.model_dump(mode="json", by_alias=True),
            headers=_headers(cancel.cancelRequestId),
        )
        conflict = client.put(
            "/internal/v1/executions/wrong-job/cancel",
            json=cancel.model_dump(mode="json", by_alias=True),
            headers=_headers(cancel.cancelRequestId),
        )

    assert accepted.status_code == 202
    assert accepted.json()["status"] == "accepted"
    assert conflict.status_code == 409
    assert service.cancellations == [cancel]
    assert verifier.calls[0]["required_scope"] == ServiceScope.EXECUTION_CANCEL
    assert verifier.calls[0]["task_id"] == cancel.stepId


def test_production_readiness_exposes_and_gates_callback_backlog() -> None:
    class Consumer:
        def __init__(self) -> None:
            self.stop_event: asyncio.Event | None = None

        async def run(self) -> None:
            stop_event = asyncio.Event()
            self.stop_event = stop_event
            await stop_event.wait()

        def request_stop(self) -> None:
            stop_event = self.stop_event
            if stop_event is not None:
                stop_event.set()

    settings = Settings.model_validate(
        {
            "environment": "production",
            "model_provider": "fake",
            "trusted_core_cidrs": ("127.0.0.1/32",),
        }
    )
    service = Service(ready=False)
    app = create_app(
        testing=True,
        settings=settings,
        run_queue=object(),  # type: ignore[arg-type]
        queue_consumer=Consumer(),
        execution_service=service,  # type: ignore[arg-type]
        core_request_verifier=Verifier(),
    )
    app.state.core_client = object()

    with TestClient(app) as client:
        response = client.get("/internal/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["execution_journal"] == "failed"
    assert response.json()["executionCallbacks"] == {
        "pending": 2,
        "rejected": 1,
        "errorCode": "EXECUTION_CALLBACK_REJECTED_BACKLOG",
    }
    assert response.json()["executionAdmission"] == {
        "active": 1,
        "capacity": 3,
        "saturated": False,
    }


def test_transient_execution_saturation_is_visible_but_does_not_fail_readiness() -> None:
    class Consumer:
        def __init__(self) -> None:
            self.stop_event: asyncio.Event | None = None

        async def run(self) -> None:
            stop_event = asyncio.Event()
            self.stop_event = stop_event
            await stop_event.wait()

        def request_stop(self) -> None:
            stop_event = self.stop_event
            if stop_event is not None:
                stop_event.set()

    settings = Settings.model_validate(
        {
            "environment": "production",
            "model_provider": "fake",
            "trusted_core_cidrs": ("127.0.0.1/32",),
        }
    )
    app = create_app(
        testing=True,
        settings=settings,
        run_queue=object(),  # type: ignore[arg-type]
        queue_consumer=Consumer(),
        execution_service=Service(saturated=True),  # type: ignore[arg-type]
        core_request_verifier=Verifier(),
    )
    app.state.core_client = object()

    with TestClient(app) as client:
        response = client.get("/internal/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["checks"]["execution_journal"] == "ok"
    assert response.json()["executionAdmission"] == {
        "active": 3,
        "capacity": 3,
        "saturated": True,
    }
