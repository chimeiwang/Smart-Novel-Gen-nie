from __future__ import annotations

from fastapi.testclient import TestClient
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_core.app import create_app
from inkforge_core.config import Settings


class CapturingVerifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def verify_request(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return object()


def payload() -> dict[str, object]:
    return {
        "protocolVersion": "2.0",
        "reconciliationId": "reconciliation-1",
        "runId": "run-1",
        "novelId": "novel-1",
        "stepId": "step-1",
        "reservationRequestId": "reservation-request-1",
        "supplierEvidenceRef": "supplier-report://deepseek/report-1",
        "supplierReportSha256": "a" * 64,
        "decision": "proven_zero",
        "usage": {
            "usageStatus": "unknown",
            "providerAttempts": 0,
            "protocolCorrections": 0,
            "wallTimeMillis": 123,
        },
    }


def test_python_rollback_route_authenticates_exact_scope_then_returns_stable_503() -> None:
    app = create_app(
        settings=Settings(
            environment="test",
            trusted_agent_cidrs=("127.0.0.1/32",),
        )
    )
    verifier = CapturingVerifier()
    app.state.rag_callback_verifier = verifier

    response = TestClient(app, client=("127.0.0.1", 50_000)).put(
        "/internal/v1/workflow-runs/run-1/steps/step-1/billing-reconciliation",
        json=payload(),
        headers={
            "Authorization": "Bearer signed-test-token",
            "Idempotency-Key": "reconciliation-1",
            "X-InkForge-Timestamp": "1800000000",
            "X-InkForge-Body-SHA256": "b" * 64,
        },
    )

    assert response.status_code == 503
    assert response.json()["code"] == "WORKFLOW_BILLING_RECONCILIATION_UNAVAILABLE"
    assert len(verifier.calls) == 1
    call = verifier.calls[0]
    assert call["required_scope"] is ServiceScope.BILLING_RECONCILE
    assert call["task_id"] == "step-1"
    assert call["run_id"] == "run-1"
    assert call["novel_id"] == "novel-1"


def test_python_rollback_route_rejects_untrusted_peer_before_verifier() -> None:
    app = create_app(
        settings=Settings(
            environment="test",
            trusted_agent_cidrs=("127.0.0.1/32",),
        )
    )
    verifier = CapturingVerifier()
    app.state.rag_callback_verifier = verifier

    response = TestClient(app, client=("198.51.100.2", 50_000)).put(
        "/internal/v1/workflow-runs/run-1/steps/step-1/billing-reconciliation",
        json=payload(),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "AGENT_SERVICE_NETWORK_FORBIDDEN"
    assert verifier.calls == []
