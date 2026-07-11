from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from inkforge_agents.service_auth import (
    create_agent_callback_signer,
    create_core_request_verifier,
    install_service_auth_error_handler,
)
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_service_auth import ServiceAuthenticationError, ServiceAuthorizationError


def test_agent_exposes_only_fixed_direction_factories(tmp_path: Path) -> None:
    with pytest.raises(ServiceAuthenticationError):
        create_agent_callback_signer(
            private_key_path=tmp_path / "missing.pem",
            kid="agent-v1",
        )
    with pytest.raises(ServiceAuthenticationError):
        create_core_request_verifier(
            jwks_path=tmp_path / "missing.jwks.json",
            replay_store=object(),
        )


def test_agent_module_does_not_expose_database_or_reverse_direction_factories() -> None:
    import inkforge_agents.service_auth as service_auth

    assert not hasattr(service_auth, "DATABASE_URL")
    assert not hasattr(service_auth, "create_core_request_signer")


def test_agent_to_core_whitelist_contains_only_rag_write_direction() -> None:
    import inkforge_agents.service_auth as service_auth

    assert ServiceScope.RAG_INDEX_WRITE in service_auth._AGENT_TO_CORE_SCOPES
    assert ServiceScope.RAG_INDEX_WRITE not in service_auth._CORE_TO_AGENT_SCOPES


def test_agent_wrapper_installs_service_auth_error_handler() -> None:
    app = FastAPI()
    install_service_auth_error_handler(app)

    @app.get("/internal/v1/testing/service-auth-error")
    async def raise_service_auth_error() -> None:
        raise ServiceAuthorizationError(
            "内部数据库地址 postgres://secret",
            code="SERVICE_RESOURCE_MISMATCH",
        )

    response = TestClient(app).get("/internal/v1/testing/service-auth-error")

    assert response.status_code == 403
    assert response.json() == {
        "code": "SERVICE_RESOURCE_MISMATCH",
        "message": "服务调用权限不足",
        "details": None,
    }
    assert "postgres" not in response.text
    assert "secret" not in response.text
