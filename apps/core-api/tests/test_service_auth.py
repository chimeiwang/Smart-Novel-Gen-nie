from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_core.app import create_app
from inkforge_core.service_auth import (
    create_agent_callback_verifier,
    create_core_request_signer,
)
from inkforge_service_auth import (
    ServiceAuthenticationError,
    ServiceAuthorizationError,
    ServiceReplayConflictError,
    ServiceReplayUnavailableError,
)


def test_core_exposes_only_fixed_direction_factories(tmp_path: Path) -> None:
    with pytest.raises(ServiceAuthenticationError):
        create_core_request_signer(
            private_key_path=tmp_path / "missing.pem",
            kid="core-v1",
        )
    with pytest.raises(ServiceAuthenticationError):
        create_agent_callback_verifier(
            jwks_path=tmp_path / "missing.jwks.json",
            replay_store=object(),
        )


def test_core_module_does_not_expose_browser_or_reverse_direction_factories() -> None:
    import inkforge_core.service_auth as service_auth

    assert not hasattr(service_auth, "create_browser_signer")
    assert not hasattr(service_auth, "create_agent_request_signer")


def test_core_accepts_rag_write_only_from_agent_direction() -> None:
    import inkforge_core.service_auth as service_auth

    assert ServiceScope.RAG_INDEX_WRITE in service_auth._AGENT_TO_CORE_SCOPES
    assert ServiceScope.QUALITY_WRITE in service_auth._AGENT_TO_CORE_SCOPES
    assert ServiceScope.RAG_INDEX_WRITE not in service_auth._CORE_TO_AGENT_SCOPES
    assert ServiceScope.QUALITY_WRITE not in service_auth._CORE_TO_AGENT_SCOPES


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            ServiceAuthenticationError("内部密钥路径 C:/secret.pem"),
            401,
            "SERVICE_AUTHENTICATION_FAILED",
        ),
        (
            ServiceAuthorizationError(
                "内部令牌 secret-token",
                code="SERVICE_SCOPE_FORBIDDEN",
            ),
            403,
            "SERVICE_SCOPE_FORBIDDEN",
        ),
        (ServiceReplayConflictError(), 409, "SERVICE_TOKEN_REPLAYED"),
        (ServiceReplayUnavailableError(), 503, "SERVICE_REPLAY_STORE_UNAVAILABLE"),
    ],
)
def test_core_app_maps_service_auth_errors_without_leaking_internal_message(
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    app = create_app(testing=True)

    @app.get("/api/v1/testing/service-auth-error")
    async def raise_service_auth_error() -> None:
        raise error

    response = TestClient(app).get(
        "/api/v1/testing/service-auth-error",
        headers={"X-Request-ID": "service-auth-request"},
    )

    assert response.status_code == status_code
    assert response.json()["code"] == code
    assert response.json()["requestId"] == "service-auth-request"
    assert response.json()["details"] is None
    assert "secret" not in response.text
    assert "C:/" not in response.text
