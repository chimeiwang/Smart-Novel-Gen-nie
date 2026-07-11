from __future__ import annotations

import base64
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_core.app import create_app
from inkforge_core.config import Settings
from inkforge_service_auth import RedisReplayStore, ServiceTokenSigner, ServiceTokenVerifier

PATH = "/internal/v1/styles/style-1/portrait-tasks/task-1/processing"


class FakeRedis:
    def __init__(self) -> None:
        self.keys: set[str] = set()

    async def set(self, key: str, value: str, *, nx: bool, ex: int):
        del value, nx, ex
        if key in self.keys:
            return None
        self.keys.add(key)
        return True


class RecordingStyleService:
    def __init__(self) -> None:
        self.processing = None

    async def mark_processing(self, style_id, task_id, body):
        self.processing = (style_id, task_id, body.runId)
        return {
            "id": task_id,
            "styleId": style_id,
            "status": "processing",
            "errorMessage": None,
            "createdAt": datetime(2026, 7, 11, tzinfo=UTC),
            "updatedAt": datetime(2026, 7, 11, tzinfo=UTC),
        }


def signed_headers(tmp_path: Path, body: bytes) -> tuple[ServiceTokenVerifier, dict[str, str]]:
    private_key = Ed25519PrivateKey.generate()
    private_path = tmp_path / "agent.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    os.chmod(private_path, 0o600)
    public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    jwks_path = tmp_path / "agent.jwks.json"
    jwks_path.write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "kty": "OKP",
                        "crv": "Ed25519",
                        "x": base64.urlsafe_b64encode(public).rstrip(b"=").decode(),
                        "kid": "agent-v1",
                        "use": "sig",
                        "alg": "EdDSA",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    signer = ServiceTokenSigner.from_pkcs8_file(
        private_path,
        issuer="agent-service",
        subject="agent-service",
        audience="core-api",
        kid="agent-v1",
        allowed_scopes=frozenset({ServiceScope.PORTRAIT_WRITE}),
    )
    verifier = ServiceTokenVerifier.from_jwks_file(
        jwks_path,
        expected_issuer="agent-service",
        expected_subject="agent-service",
        audience="core-api",
        replay_store=RedisReplayStore(FakeRedis()),
        allowed_scopes=frozenset({ServiceScope.PORTRAIT_WRITE}),
    )
    signed = signer.sign_request(
        body=body,
        http_method="PUT",
        http_path=PATH,
        query_string=b"",
        idempotency_key="portrait-callback-1",
        scope=(ServiceScope.PORTRAIT_WRITE,),
        task_id="task-1",
        run_id="task-1",
        novel_id="style:style-1",
        now=int(time.time()),
        jti="portrait-callback-jti-1",
    )
    return verifier, {**signed.headers, "Content-Type": "application/json"}


def test_real_portrait_callback_is_signed_namespaced_and_replay_protected(
    tmp_path: Path,
) -> None:
    app = create_app(settings=Settings(environment="test", trusted_agent_cidrs=("127.0.0.1/32",)))
    service = RecordingStyleService()
    body = b'{"runId":"task-1"}'
    verifier, headers = signed_headers(tmp_path, body)
    app.state.rag_callback_verifier = verifier
    app.state.style_service = service
    client = TestClient(app, client=("127.0.0.1", 50000))
    first = client.put(PATH, content=body, headers=headers)
    replay = client.put(PATH, content=body, headers=headers)
    assert first.status_code == 200
    assert service.processing == ("style-1", "task-1", "task-1")
    assert replay.status_code == 409
    assert replay.json()["code"] == "SERVICE_TOKEN_REPLAYED"


def test_portrait_callback_rejects_untrusted_direct_peer(tmp_path: Path) -> None:
    app = create_app(settings=Settings(environment="test", trusted_agent_cidrs=("127.0.0.1/32",)))
    body = b'{"runId":"task-1"}'
    verifier, headers = signed_headers(tmp_path, body)
    app.state.rag_callback_verifier = verifier
    app.state.style_service = RecordingStyleService()
    response = TestClient(app, client=("198.51.100.2", 50000)).put(
        PATH,
        content=body,
        headers={**headers, "X-Forwarded-For": "127.0.0.1"},
    )
    assert response.status_code == 403


def test_agent_to_core_scope_whitelist_contains_only_minimal_portrait_write() -> None:
    from inkforge_core import service_auth

    assert ServiceScope.PORTRAIT_WRITE in service_auth._AGENT_TO_CORE_SCOPES
    assert ServiceScope.PORTRAIT_WRITE not in service_auth._CORE_TO_AGENT_SCOPES
