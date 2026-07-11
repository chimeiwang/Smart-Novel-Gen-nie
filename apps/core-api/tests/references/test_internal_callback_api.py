from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import UTC, datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_core.app import create_app
from inkforge_service_auth import RedisReplayStore, ServiceTokenSigner, ServiceTokenVerifier

HASH = "a" * 64


class RecordingVerifier:
    def __init__(self) -> None:
        self.kwargs = None

    async def verify_request(self, **kwargs):
        self.kwargs = kwargs
        return object()


class FakeRedis:
    def __init__(self) -> None:
        self.keys: set[str] = set()

    async def set(self, key: str, value: str, *, nx: bool, ex: int):
        del value, nx, ex
        if key in self.keys:
            return None
        self.keys.add(key)
        return True


class RecordingService:
    def __init__(self) -> None:
        self.completed = None
        self.failed = None

    async def complete_index(self, novel_id, reference_id, expected_hash, embeddings):
        self.completed = (novel_id, reference_id, expected_hash, embeddings)
        now = datetime(2026, 7, 11, tzinfo=UTC)
        return {
            "id": reference_id,
            "title": "资料",
            "type": "note",
            "content": "正文",
            "sourceUrl": None,
            "ragStatus": "ready",
            "contentHash": expected_hash,
            "errorMessage": None,
            "createdAt": now,
            "updatedAt": now,
        }

    async def fail_index(self, novel_id, reference_id, expected_hash, message):
        self.failed = (novel_id, reference_id, expected_hash, message)


def headers(body: bytes) -> dict[str, str]:
    return {
        "Authorization": "Bearer signed-token",
        "Idempotency-Key": "callback-1",
        "X-InkForge-Timestamp": "1",
        "X-InkForge-Body-SHA256": hashlib.sha256(body).hexdigest(),
        "Content-Type": "application/json",
    }


def signed_auth(tmp_path, body: bytes, path: str):
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
    raw_public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    encoded_public = base64.urlsafe_b64encode(raw_public).rstrip(b"=").decode()
    jwks_path = tmp_path / "agent.jwks.json"
    jwks_path.write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "kty": "OKP",
                        "crv": "Ed25519",
                        "x": encoded_public,
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
        allowed_scopes=frozenset({ServiceScope.RAG_INDEX_WRITE}),
    )
    verifier = ServiceTokenVerifier.from_jwks_file(
        jwks_path,
        expected_issuer="agent-service",
        expected_subject="agent-service",
        audience="core-api",
        replay_store=RedisReplayStore(FakeRedis()),
        allowed_scopes=frozenset({ServiceScope.RAG_INDEX_WRITE}),
    )
    signed = signer.sign_request(
        body=body,
        http_method="PUT",
        http_path=path,
        query_string=b"",
        idempotency_key="callback-real-1",
        scope=(ServiceScope.RAG_INDEX_WRITE,),
        task_id="task-1",
        run_id="run-1",
        novel_id="novel-1",
        now=int(time.time()),
        jti="callback-real-jti-1",
    )
    return verifier, dict(signed.headers)


def test_browser_cookie_route_cannot_write_embeddings() -> None:
    paths = create_app(testing=True).openapi()["paths"]
    assert "/api/v1/novels/{novel_id}/references/{reference_id}/index" not in paths


def test_internal_callback_returns_503_when_service_verifier_is_not_configured() -> None:
    app = create_app(testing=True)
    app.state.reference_service = RecordingService()
    response = TestClient(app).put(
        "/api/v1/internal/novels/novel-1/references/reference-1/index-success",
        json={
            "taskId": "task-1",
            "runId": "run-1",
            "expectedContentHash": HASH,
            "embeddings": [[1.0]],
        },
    )
    assert response.status_code == 503
    assert response.json()["code"] == "RAG_CALLBACK_AUTH_UNAVAILABLE"


def test_success_callback_binds_raw_body_path_scope_and_resources() -> None:
    app = create_app(testing=True)
    verifier = RecordingVerifier()
    service = RecordingService()
    app.state.rag_callback_verifier = verifier
    app.state.reference_service = service
    body = (
        '{"taskId":"task-1","runId":"run-1","expectedContentHash":"'
        + HASH
        + '","embeddings":[[1.0]]}'
    ).encode()
    response = TestClient(app).put(
        "/api/v1/internal/novels/novel-1/references/reference-1/index-success",
        content=body,
        headers=headers(body),
    )
    assert response.status_code == 200
    assert verifier.kwargs["body"] == body
    assert verifier.kwargs["http_method"] == "PUT"
    assert verifier.kwargs["http_path"].endswith("/index-success")
    assert verifier.kwargs["query_string"] == b""
    assert verifier.kwargs["required_scope"] is ServiceScope.RAG_INDEX_WRITE
    assert verifier.kwargs["task_id"] == "task-1"
    assert verifier.kwargs["run_id"] == "run-1"
    assert verifier.kwargs["novel_id"] == "novel-1"
    assert service.completed == ("novel-1", "reference-1", HASH, [[1.0]])


def test_failure_callback_uses_same_signed_boundary() -> None:
    app = create_app(testing=True)
    verifier = RecordingVerifier()
    service = RecordingService()
    app.state.rag_callback_verifier = verifier
    app.state.reference_service = service
    body = (
        '{"taskId":"task-1","runId":"run-1","expectedContentHash":"'
        + HASH
        + '","message":"嵌入服务失败"}'
    ).encode()
    response = TestClient(app).put(
        "/api/v1/internal/novels/novel-1/references/reference-1/index-failure",
        content=body,
        headers=headers(body),
    )
    assert response.status_code == 204
    assert verifier.kwargs["required_scope"] is ServiceScope.RAG_INDEX_WRITE
    assert service.failed == ("novel-1", "reference-1", HASH, "嵌入服务失败")


def test_real_ed25519_callback_consumes_redis_replay_token(tmp_path) -> None:
    app = create_app(testing=True)
    service = RecordingService()
    app.state.reference_service = service
    path = "/api/v1/internal/novels/novel-1/references/reference-1/index-success"
    body = (
        '{"taskId":"task-1","runId":"run-1","expectedContentHash":"'
        + HASH
        + '","embeddings":[[1.0]]}'
    ).encode()
    verifier, signed_headers = signed_auth(tmp_path, body, path)
    app.state.rag_callback_verifier = verifier
    client = TestClient(app)
    first = client.put(
        path, content=body, headers={**signed_headers, "Content-Type": "application/json"}
    )
    second = client.put(
        path, content=body, headers={**signed_headers, "Content-Type": "application/json"}
    )
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["code"] == "SERVICE_TOKEN_REPLAYED"


def test_real_signed_failure_callback_rejects_body_tampering(tmp_path) -> None:
    app = create_app(testing=True)
    service = RecordingService()
    app.state.reference_service = service
    path = "/api/v1/internal/novels/novel-1/references/reference-1/index-failure"
    body = (
        '{"taskId":"task-1","runId":"run-1","expectedContentHash":"' + HASH + '","message":"失败"}'
    ).encode()
    verifier, signed_headers = signed_auth(tmp_path, body, path)
    app.state.rag_callback_verifier = verifier
    client = TestClient(app)
    request_headers = {**signed_headers, "Content-Type": "application/json"}
    accepted = client.put(path, content=body, headers=request_headers)
    tampered = client.put(
        path, content=body.replace("失败".encode(), "篡改".encode()), headers=request_headers
    )
    assert accepted.status_code == 204
    assert tampered.status_code == 401
    assert tampered.json()["code"] == "SERVICE_REQUEST_BINDING_INVALID"
