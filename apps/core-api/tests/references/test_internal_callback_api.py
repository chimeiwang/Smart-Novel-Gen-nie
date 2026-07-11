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
from inkforge_core.config import Settings
from inkforge_service_auth import RedisReplayStore, ServiceTokenSigner, ServiceTokenVerifier

HASH = "a" * 64
INTERNAL_SUCCESS_PATH = (
    "/internal/v1/novels/novel-1/references/reference-1/index-success"
)
INTERNAL_FAILURE_PATH = (
    "/internal/v1/novels/novel-1/references/reference-1/index-failure"
)
INTERNAL_CONTEXT_PATH = (
    "/internal/v1/novels/novel-1/references/reference-1/index-context"
)


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

    async def get_index_context(self, user_id, novel_id, reference_id, expected_hash):
        self.context = (user_id, novel_id, reference_id, expected_hash)
        return {"contentHash": expected_hash, "chunks": ["正文"]}


def headers(body: bytes) -> dict[str, str]:
    return {
        "Authorization": "Bearer signed-token",
        "Idempotency-Key": "callback-1",
        "X-InkForge-Timestamp": "1",
        "X-InkForge-Body-SHA256": hashlib.sha256(body).hexdigest(),
        "Content-Type": "application/json",
    }


def internal_app():
    return create_app(
        settings=Settings(
            environment="test",
            trusted_agent_cidrs=("127.0.0.1/32",),
        )
    )


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


def test_internal_callbacks_are_hidden_from_public_openapi() -> None:
    paths = internal_app().openapi()["paths"]
    assert not any(path.startswith("/internal/") for path in paths)


def test_internal_callback_is_not_mounted_under_public_api_prefix() -> None:
    app = internal_app()
    response = TestClient(app, client=("127.0.0.1", 50000)).put(
        "/api/v1/internal/novels/novel-1/references/reference-1/index-success",
        json={},
    )
    assert response.status_code == 404


def test_internal_callback_returns_503_when_agent_network_is_not_configured() -> None:
    app = create_app(testing=True)
    app.state.rag_callback_verifier = RecordingVerifier()
    app.state.reference_service = RecordingService()
    response = TestClient(app, client=("127.0.0.1", 50000)).put(
        INTERNAL_SUCCESS_PATH,
        json={
            "taskId": "task-1",
            "runId": "run-1",
            "expectedContentHash": HASH,
            "embeddings": [[1.0]],
        },
    )
    assert response.status_code == 503
    assert response.json()["code"] == "AGENT_SERVICE_NETWORK_UNAVAILABLE"


def test_internal_callback_returns_503_when_service_verifier_is_not_configured() -> None:
    app = internal_app()
    app.state.reference_service = RecordingService()
    response = TestClient(app, client=("127.0.0.1", 50000)).put(
        INTERNAL_SUCCESS_PATH,
        json={
            "taskId": "task-1",
            "runId": "run-1",
            "expectedContentHash": HASH,
            "embeddings": [[1.0]],
        },
    )
    assert response.status_code == 503
    assert response.json()["code"] == "RAG_CALLBACK_AUTH_UNAVAILABLE"


def test_internal_callback_rejects_direct_peer_outside_agent_network() -> None:
    app = internal_app()
    app.state.rag_callback_verifier = RecordingVerifier()
    app.state.reference_service = RecordingService()
    response = TestClient(app, client=("198.51.100.10", 50000)).put(
        INTERNAL_SUCCESS_PATH,
        json={
            "taskId": "task-1",
            "runId": "run-1",
            "expectedContentHash": HASH,
            "embeddings": [[1.0]],
        },
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "AGENT_SERVICE_NETWORK_FORBIDDEN"


def test_success_callback_binds_raw_body_path_scope_and_resources() -> None:
    app = internal_app()
    verifier = RecordingVerifier()
    service = RecordingService()
    app.state.rag_callback_verifier = verifier
    app.state.reference_service = service
    body = (
        '{"taskId":"task-1","runId":"run-1","expectedContentHash":"'
        + HASH
        + '","embeddings":[[1.0]]}'
    ).encode()
    response = TestClient(app, client=("127.0.0.1", 50000)).put(
        INTERNAL_SUCCESS_PATH,
        content=body,
        headers=headers(body),
    )
    assert response.status_code == 200
    assert verifier.kwargs["body"] == body
    assert verifier.kwargs["http_method"] == "PUT"
    assert verifier.kwargs["http_path"] == INTERNAL_SUCCESS_PATH
    assert verifier.kwargs["query_string"] == b""
    assert verifier.kwargs["required_scope"] is ServiceScope.RAG_INDEX_WRITE
    assert verifier.kwargs["task_id"] == "task-1"
    assert verifier.kwargs["run_id"] == "run-1"
    assert verifier.kwargs["novel_id"] == "novel-1"
    assert service.completed == ("novel-1", "reference-1", HASH, [[1.0]])


def test_failure_callback_uses_same_signed_boundary() -> None:
    app = internal_app()
    verifier = RecordingVerifier()
    service = RecordingService()
    app.state.rag_callback_verifier = verifier
    app.state.reference_service = service
    body = (
        '{"taskId":"task-1","runId":"run-1","expectedContentHash":"'
        + HASH
        + '","message":"嵌入服务失败"}'
    ).encode()
    response = TestClient(app, client=("127.0.0.1", 50000)).put(
        INTERNAL_FAILURE_PATH,
        content=body,
        headers=headers(body),
    )
    assert response.status_code == 204
    assert verifier.kwargs["required_scope"] is ServiceScope.RAG_INDEX_WRITE
    assert service.failed == ("novel-1", "reference-1", HASH, "嵌入服务失败")


def test_index_context_revalidates_user_and_signed_resources() -> None:
    app = internal_app()
    verifier = RecordingVerifier()
    service = RecordingService()
    app.state.rag_callback_verifier = verifier
    app.state.reference_service = service
    body = (
        '{"userId":"user-1","taskId":"task-1","runId":"run-1",'
        '"expectedContentHash":"' + HASH + '"}'
    ).encode()

    response = TestClient(app, client=("127.0.0.1", 50000)).post(
        INTERNAL_CONTEXT_PATH,
        content=body,
        headers=headers(body),
    )

    assert response.status_code == 200
    assert response.json() == {"contentHash": HASH, "chunks": ["正文"]}
    assert verifier.kwargs["required_scope"] is ServiceScope.RAG_INDEX_WRITE
    assert service.context == ("user-1", "novel-1", "reference-1", HASH)


def test_real_ed25519_callback_consumes_redis_replay_token(tmp_path) -> None:
    app = internal_app()
    service = RecordingService()
    app.state.reference_service = service
    path = INTERNAL_SUCCESS_PATH
    body = (
        '{"taskId":"task-1","runId":"run-1","expectedContentHash":"'
        + HASH
        + '","embeddings":[[1.0]]}'
    ).encode()
    verifier, signed_headers = signed_auth(tmp_path, body, path)
    app.state.rag_callback_verifier = verifier
    client = TestClient(app, client=("127.0.0.1", 50000))
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
    app = internal_app()
    service = RecordingService()
    app.state.reference_service = service
    path = INTERNAL_FAILURE_PATH
    body = (
        '{"taskId":"task-1","runId":"run-1","expectedContentHash":"' + HASH + '","message":"失败"}'
    ).encode()
    verifier, signed_headers = signed_auth(tmp_path, body, path)
    app.state.rag_callback_verifier = verifier
    client = TestClient(app, client=("127.0.0.1", 50000))
    request_headers = {**signed_headers, "Content-Type": "application/json"}
    accepted = client.put(path, content=body, headers=request_headers)
    tampered = client.put(
        path, content=body.replace("失败".encode(), "篡改".encode()), headers=request_headers
    )
    assert accepted.status_code == 204
    assert tampered.status_code == 401
    assert tampered.json()["code"] == "SERVICE_REQUEST_BINDING_INVALID"
