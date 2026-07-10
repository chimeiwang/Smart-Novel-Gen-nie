from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from inkforge_agents.service_auth import (
    create_agent_callback_signer,
    create_core_request_verifier,
    install_service_auth_error_handler,
)
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_core.service_auth import (
    create_agent_callback_verifier,
    create_core_request_signer,
)
from inkforge_service_auth import (
    RedisReplayStore,
    ServiceAuthorizationError,
    ServiceTokenSigner,
    canonical_json_body,
)


class DirectionRedis:
    def __init__(self) -> None:
        self.keys: set[str] = set()

    async def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool | None:
        assert value == "1"
        assert nx is True
        assert ex > 0
        if key in self.keys:
            return None
        self.keys.add(key)
        return True


def _write_pair(directory: Path, stem: str, kid: str) -> tuple[Path, Path]:
    private_key = Ed25519PrivateKey.generate()
    private_path = directory / f"{stem}.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    os.chmod(private_path, 0o600)
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    jwks_path = directory / f"{stem}.jwks.json"
    jwks_path.write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "kty": "OKP",
                        "crv": "Ed25519",
                        "x": base64.urlsafe_b64encode(public_bytes)
                        .rstrip(b"=")
                        .decode("ascii"),
                        "kid": kid,
                        "use": "sig",
                        "alg": "EdDSA",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return private_path, jwks_path


@pytest.mark.asyncio
async def test_core_to_agent_and_agent_to_core_use_independent_keys(tmp_path: Path) -> None:
    core_private, core_jwks = _write_pair(tmp_path, "core", "core-v1")
    agent_private, agent_jwks = _write_pair(tmp_path, "agent", "agent-v1")
    core_signer = create_core_request_signer(private_key_path=core_private, kid="core-v1")
    agent_verifier = create_core_request_verifier(
        jwks_path=core_jwks,
        replay_store=RedisReplayStore(DirectionRedis()),
    )
    agent_signer = create_agent_callback_signer(
        private_key_path=agent_private,
        kid="agent-v1",
    )
    core_verifier = create_agent_callback_verifier(
        jwks_path=agent_jwks,
        replay_store=RedisReplayStore(DirectionRedis()),
    )

    for signer, verifier, scope, path, idempotency_key in (
        (
            core_signer,
            agent_verifier,
            ServiceScope.AGENT_RUN,
            "/internal/v1/runs",
            "core-idem",
        ),
        (
            agent_signer,
            core_verifier,
            ServiceScope.CALLBACK_CHECKPOINT,
            "/internal/v1/callbacks/checkpoint",
            "agent-idem",
        ),
    ):
        body = canonical_json_body({"direction": idempotency_key})
        signed = signer.sign_request(
            body=body,
            http_method="POST",
            http_path=path,
            query_string=b"",
            idempotency_key=idempotency_key,
            scope=(scope,),
            task_id="task-1",
            run_id="run-1",
            novel_id="novel-1",
            now=1_800_000_000,
        )
        claims = await verifier.verify_request(
            token=signed.token,
            body=body,
            http_method="POST",
            http_path=path,
            query_string=b"",
            idempotency_key=idempotency_key,
            request_timestamp=signed.headers["X-InkForge-Timestamp"],
            body_sha256=signed.headers["X-InkForge-Body-SHA256"],
            required_scope=scope,
            task_id="task-1",
            run_id="run-1",
            novel_id="novel-1",
            now=1_800_000_000,
        )
        assert claims.scope == (scope,)

    assert core_signer.public_key.public_bytes_raw() != agent_signer.public_key.public_bytes_raw()


def test_service_wrappers_hide_generic_auth_types_and_declare_public_surface() -> None:
    import inkforge_agents.service_auth as agent_auth
    import inkforge_core.service_auth as core_auth

    assert core_auth.__all__ == [
        "create_agent_callback_verifier",
        "create_core_request_signer",
        "install_service_auth_error_handler",
    ]
    assert agent_auth.__all__ == [
        "create_agent_callback_signer",
        "create_core_request_verifier",
        "install_service_auth_error_handler",
    ]
    for module in (core_auth, agent_auth):
        assert not hasattr(module, "ServiceTokenSigner")
        assert not hasattr(module, "ServiceTokenVerifier")


@pytest.mark.asyncio
async def test_direction_factories_reject_scopes_owned_by_the_other_direction(
    tmp_path: Path,
) -> None:
    core_private, core_jwks = _write_pair(tmp_path, "core-scope", "core-v1")
    agent_private, agent_jwks = _write_pair(tmp_path, "agent-scope", "agent-v1")
    core_signer = create_core_request_signer(private_key_path=core_private, kid="core-v1")
    agent_signer = create_agent_callback_signer(
        private_key_path=agent_private,
        kid="agent-v1",
    )
    body = canonical_json_body({"scope": "越权"})

    for signer, forbidden_scope in (
        (core_signer, ServiceScope.TOOL_WRITE),
        (agent_signer, ServiceScope.AGENT_RUN),
    ):
        with pytest.raises(ServiceAuthorizationError, match="权限范围"):
            signer.sign_request(
                body=body,
                http_method="POST",
                http_path="/internal/v1/scope",
                query_string=b"",
                idempotency_key="scope-idem",
                scope=(forbidden_scope,),
                task_id="task-1",
                run_id="run-1",
                novel_id="novel-1",
                now=1_800_000_000,
            )

    agent_verifier = create_core_request_verifier(
        jwks_path=core_jwks,
        replay_store=RedisReplayStore(DirectionRedis()),
    )
    core_verifier = create_agent_callback_verifier(
        jwks_path=agent_jwks,
        replay_store=RedisReplayStore(DirectionRedis()),
    )
    for verifier, forbidden_scope in (
        (agent_verifier, ServiceScope.CALLBACK_EVENT),
        (core_verifier, ServiceScope.AGENT_CANCEL),
    ):
        with pytest.raises(ServiceAuthorizationError, match="权限范围"):
            await verifier.verify_request(
                token=str(object()),
                body=body,
                http_method="POST",
                http_path="/internal/v1/scope",
                query_string=b"",
                idempotency_key="scope-idem",
                request_timestamp="1800000000",
                body_sha256="0" * 64,
                required_scope=forbidden_scope,
                task_id="task-1",
                run_id="run-1",
                novel_id="novel-1",
                now=1_800_000_000,
            )

    mixed_scope_signer = ServiceTokenSigner.from_pkcs8_file(
        core_private,
        issuer="core-api",
        subject="core-api",
        audience="agent-service",
        kid="core-v1",
    )
    mixed_scope_token = mixed_scope_signer.sign_request(
        body=body,
        http_method="POST",
        http_path="/internal/v1/scope",
        query_string=b"",
        idempotency_key="mixed-scope-idem",
        scope=(ServiceScope.AGENT_RUN, ServiceScope.CALLBACK_EVENT),
        task_id="task-1",
        run_id="run-1",
        novel_id="novel-1",
        now=1_800_000_000,
    )
    with pytest.raises(ServiceAuthorizationError, match="权限范围"):
        await agent_verifier.verify_request(
            token=mixed_scope_token.token,
            body=body,
            http_method="POST",
            http_path="/internal/v1/scope",
            query_string=b"",
            idempotency_key="mixed-scope-idem",
            request_timestamp=mixed_scope_token.headers["X-InkForge-Timestamp"],
            body_sha256=mixed_scope_token.headers["X-InkForge-Body-SHA256"],
            required_scope=ServiceScope.AGENT_RUN,
            task_id="task-1",
            run_id="run-1",
            novel_id="novel-1",
            now=1_800_000_000,
        )


def test_asgi_request_uses_exact_body_and_raw_query_bytes(tmp_path: Path) -> None:
    core_private, core_jwks = _write_pair(tmp_path, "asgi-core", "core-v1")
    signer = create_core_request_signer(private_key_path=core_private, kid="core-v1")
    verifier = create_core_request_verifier(
        jwks_path=core_jwks,
        replay_store=RedisReplayStore(DirectionRedis()),
    )
    app = FastAPI()
    install_service_auth_error_handler(app)
    observed_queries: list[bytes] = []

    @app.post("/internal/v1/bound")
    async def bound_request(request: Request) -> dict[str, bool]:
        body = await request.body()
        raw_query = request.scope["query_string"]
        observed_queries.append(raw_query)
        authorization = request.headers["Authorization"]
        await verifier.verify_request(
            token=authorization.removeprefix("Bearer "),
            body=body,
            http_method=request.method,
            http_path=request.url.path,
            query_string=raw_query,
            idempotency_key=request.headers["Idempotency-Key"],
            request_timestamp=request.headers["X-InkForge-Timestamp"],
            body_sha256=request.headers["X-InkForge-Body-SHA256"],
            required_scope=ServiceScope.AGENT_RUN,
            task_id="task-1",
            run_id="run-1",
            novel_id="novel-1",
            now=1_800_000_000,
        )
        return {"verified": True}

    body = canonical_json_body({"content": "原始正文"})
    raw_query = b"value=%2F&name=%E4%B8%AD%E6%96%87"
    signed = signer.sign_request(
        body=body,
        http_method="POST",
        http_path="/internal/v1/bound",
        query_string=raw_query,
        idempotency_key="asgi-idem",
        scope=(ServiceScope.AGENT_RUN,),
        task_id="task-1",
        run_id="run-1",
        novel_id="novel-1",
        now=1_800_000_000,
    )
    client = TestClient(app)

    valid = client.post(
        "/internal/v1/bound?value=%2F&name=%E4%B8%AD%E6%96%87",
        content=body,
        headers=dict(signed.headers),
    )
    tampered_query = client.post(
        "/internal/v1/bound?value=/&name=%E4%B8%AD%E6%96%87",
        content=body,
        headers=dict(signed.headers),
    )
    tampered_body = client.post(
        "/internal/v1/bound?value=%2F&name=%E4%B8%AD%E6%96%87",
        content=b"{}",
        headers=dict(signed.headers),
    )

    assert valid.status_code == 200
    assert valid.json() == {"verified": True}
    assert observed_queries[0] == raw_query
    assert tampered_query.status_code == 401
    assert tampered_query.json()["code"] == "SERVICE_REQUEST_BINDING_INVALID"
    assert tampered_body.status_code == 401
    assert tampered_body.json()["code"] == "SERVICE_REQUEST_BINDING_INVALID"
