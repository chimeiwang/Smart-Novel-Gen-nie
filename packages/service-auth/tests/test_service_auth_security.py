from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import traceback
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jwt
import orjson
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from inkforge_contracts.jwt_claims import ServiceJwtClaims, ServiceScope
from inkforge_service_auth import (
    RedisReplayStore,
    ReplayPolicy,
    ServiceAuthenticationError,
    ServiceAuthorizationError,
    ServiceReplayConflictError,
    ServiceReplayUnavailableError,
    ServiceRequestBindingError,
    ServiceTokenSigner,
    ServiceTokenVerifier,
    canonical_json_body,
)
from pydantic import ValidationError

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
NOW_SECONDS = int(NOW.timestamp())


class FakeRedis:
    def __init__(self) -> None:
        self.values: set[str] = set()
        self.calls: list[tuple[str, str, bool, int]] = []
        self.error: Exception | None = None

    async def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool | None:
        await asyncio.sleep(0)
        self.calls.append((key, value, nx, ex))
        if self.error is not None:
            raise self.error
        if key in self.values:
            return None
        self.values.add(key)
        return True


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _write_key_pair(directory: Path, stem: str, kid: str) -> tuple[Path, Path, Ed25519PrivateKey]:
    private_key = Ed25519PrivateKey.generate()
    private_path = directory / f"{stem}.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    jwks_path = directory / f"{stem}.jwks.json"
    jwks_path.write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "kty": "OKP",
                        "crv": "Ed25519",
                        "x": _b64url(public_bytes),
                        "kid": kid,
                        "use": "sig",
                        "alg": "EdDSA",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return private_path, jwks_path, private_key


def _build_auth(
    tmp_path: Path,
    *,
    replay_policy: ReplayPolicy = ReplayPolicy.ALL_SCOPES,
    skew_seconds: int = 10,
) -> tuple[ServiceTokenSigner, ServiceTokenVerifier, FakeRedis]:
    private_path, jwks_path, _ = _write_key_pair(tmp_path, "core", "core-v2")
    redis = FakeRedis()
    signer = ServiceTokenSigner.from_pkcs8_file(
        private_path,
        issuer="core-api",
        subject="core-api",
        audience="agent-service",
        kid="core-v2",
    )
    verifier = ServiceTokenVerifier.from_jwks_file(
        jwks_path,
        expected_issuer="core-api",
        expected_subject="core-api",
        audience="agent-service",
        replay_store=RedisReplayStore(redis, key_prefix="测试:重放:"),
        replay_policy=replay_policy,
        clock_skew_seconds=skew_seconds,
    )
    return signer, verifier, redis


def _issue(
    signer: ServiceTokenSigner,
    *,
    body: bytes | None = None,
    scope: ServiceScope = ServiceScope.AGENT_RUN,
    now_seconds: int = NOW_SECONDS,
    ttl_seconds: int | None = None,
) -> tuple[bytes, Any]:
    request_body = body if body is not None else canonical_json_body({"message": "开始"})
    signed = signer.sign_request(
        body=request_body,
        http_method="POST",
        http_path="/internal/v1/runs",
        idempotency_key="idem-1",
        scope=(scope,),
        task_id="task-1",
        run_id="run-1",
        novel_id="novel-1",
        now=now_seconds,
        ttl_seconds=ttl_seconds,
        jti="jti-1",
    )
    return request_body, signed


async def _verify(
    verifier: ServiceTokenVerifier,
    signed: Any,
    body: bytes,
    *,
    scope: ServiceScope = ServiceScope.AGENT_RUN,
    now_seconds: int = NOW_SECONDS,
    **overrides: Any,
) -> ServiceJwtClaims:
    values: dict[str, Any] = {
        "token": signed.token,
        "body": body,
        "http_method": "POST",
        "http_path": "/internal/v1/runs",
        "idempotency_key": signed.headers["Idempotency-Key"],
        "request_timestamp": signed.headers["X-InkForge-Timestamp"],
        "body_sha256": signed.headers["X-InkForge-Body-SHA256"],
        "required_scope": scope,
        "task_id": "task-1",
        "run_id": "run-1",
        "novel_id": "novel-1",
        "now": now_seconds,
    }
    values.update(overrides)
    return await verifier.verify_request(**values)


def test_claims_reject_unknown_fields_and_empty_scope() -> None:
    base = {
        "iss": "core-api",
        "sub": "core-api",
        "aud": "agent-service",
        "scope": ["agent:run"],
        "task_id": "task-1",
        "run_id": "run-1",
        "novel_id": "novel-1",
        "jti": "jti-1",
        "iat": NOW_SECONDS,
        "exp": NOW_SECONDS + 120,
        "body_sha256": "0" * 64,
        "idempotency_key": "idem-1",
        "request_timestamp": NOW_SECONDS,
        "http_method": "POST",
        "http_path": "/internal/v1/runs",
    }
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ServiceJwtClaims.model_validate({**base, "unknown": "value"})
    with pytest.raises(ValidationError):
        ServiceJwtClaims.model_validate({**base, "scope": []})


def test_claims_reject_ttl_over_300_seconds_and_non_integer_time(tmp_path: Path) -> None:
    signer = _standalone_signer(tmp_path)
    body, signed = _issue(signer, ttl_seconds=300)
    claims = jwt.decode(
        signed.token,
        signer.public_key,
        algorithms=["EdDSA"],
        audience="agent-service",
        issuer="core-api",
        subject="core-api",
        options={"verify_exp": False, "verify_iat": False},
    )
    assert body
    with pytest.raises(ValidationError, match="300"):
        ServiceJwtClaims.model_validate({**claims, "exp": claims["iat"] + 301})
    with pytest.raises(ValidationError):
        ServiceJwtClaims.model_validate({**claims, "iat": float(claims["iat"])})
    with pytest.raises(ValidationError, match="request_timestamp"):
        ServiceJwtClaims.model_validate(
            {**claims, "request_timestamp": claims["request_timestamp"] + 1}
        )


def _standalone_signer(tmp_path: Path) -> ServiceTokenSigner:
    private_path, _, _ = _write_key_pair(tmp_path, "standalone", "core-v1")
    return ServiceTokenSigner.from_pkcs8_file(
        private_path,
        issuer="core-api",
        subject="core-api",
        audience="agent-service",
        kid="core-v1",
    )


def test_signer_uses_fixed_headers_and_exact_orjson_body(tmp_path: Path) -> None:
    signer = _standalone_signer(tmp_path)
    body = canonical_json_body({"b": 2, "a": "中文"})
    assert body == orjson.dumps({"b": 2, "a": "中文"})
    request_body, signed = _issue(signer, body=body)
    assert jwt.get_unverified_header(signed.token) == {
        "alg": "EdDSA",
        "kid": "core-v1",
        "typ": "JWT",
    }
    assert signed.headers["X-InkForge-Body-SHA256"] == hashlib.sha256(request_body).hexdigest()
    assert signed.headers["Authorization"] == f"Bearer {signed.token}"


@pytest.mark.parametrize(
    "path",
    (
        "/internal//v1/runs",
        "/internal/./v1/runs",
        "/internal/v1/runs/",
        "/internal/%2e%2e/runs",
    ),
)
def test_signer_rejects_non_canonical_path_aliases(tmp_path: Path, path: str) -> None:
    signer = _standalone_signer(tmp_path)
    with pytest.raises(ValueError, match="规范"):
        signer.sign_request(
            body=b"{}",
            http_method="POST",
            http_path=path,
            idempotency_key="idem-1",
            scope=(ServiceScope.AGENT_RUN,),
            task_id="task-1",
            run_id="run-1",
            novel_id="novel-1",
            now=NOW_SECONDS,
        )


def test_signer_cannot_accept_or_expose_an_in_memory_private_key(tmp_path: Path) -> None:
    signer = _standalone_signer(tmp_path)
    with pytest.raises(TypeError):
        ServiceTokenSigner(
            private_key=Ed25519PrivateKey.generate(),
            issuer="core-api",
            subject="core-api",
            audience="agent-service",
            kid="core-v1",
        )
    assert not hasattr(signer, "private_key")


def test_private_key_loader_rejects_public_key_and_non_pkcs8(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    public_path = tmp_path / "public.pem"
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    with pytest.raises(ServiceAuthenticationError, match="PKCS8"):
        ServiceTokenSigner.from_pkcs8_file(
            public_path,
            issuer="core-api",
            subject="core-api",
            audience="agent-service",
            kid="core-v1",
        )


@pytest.mark.asyncio
async def test_valid_token_verifies_all_bindings_and_consumes_jti(tmp_path: Path) -> None:
    signer, verifier, redis = _build_auth(tmp_path)
    body, signed = _issue(signer)
    claims = await _verify(verifier, signed, body)
    assert claims.task_id == "task-1"
    assert claims.run_id == "run-1"
    assert claims.novel_id == "novel-1"
    assert redis.calls == [("测试:重放:jti-1", "1", True, 130)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task_id", "task-2"),
        ("run_id", "run-2"),
        ("novel_id", "novel-2"),
    ],
)
async def test_resource_binding_mismatch_is_forbidden(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    signer, verifier, redis = _build_auth(tmp_path)
    body, signed = _issue(signer)
    with pytest.raises(ServiceAuthorizationError) as captured:
        await _verify(verifier, signed, body, **{field: value})
    assert captured.value.code == "SERVICE_RESOURCE_MISMATCH"
    assert field in str(captured.value)
    assert redis.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("body", b"different"),
        ("http_method", "PUT"),
        ("http_path", "/internal/v1/other"),
        ("idempotency_key", "idem-2"),
        ("request_timestamp", str(NOW_SECONDS + 1)),
        ("body_sha256", "f" * 64),
    ],
)
async def test_request_binding_mismatch_precedes_resource_and_replay(
    tmp_path: Path,
    override: str,
    value: object,
) -> None:
    signer, verifier, redis = _build_auth(tmp_path)
    body, signed = _issue(signer)
    request_body = value if override == "body" else body
    kwargs = {"novel_id": "novel-2"}
    if override != "body":
        kwargs[override] = value
    with pytest.raises(ServiceRequestBindingError):
        await _verify(verifier, signed, request_body, **kwargs)
    assert redis.calls == []


@pytest.mark.asyncio
async def test_scope_check_precedes_replay(tmp_path: Path) -> None:
    signer, verifier, redis = _build_auth(tmp_path)
    body, signed = _issue(signer, scope=ServiceScope.TOOL_READ)
    with pytest.raises(ServiceAuthorizationError) as captured:
        await _verify(verifier, signed, body, scope=ServiceScope.TOOL_WRITE)
    assert captured.value.code == "SERVICE_SCOPE_FORBIDDEN"
    assert redis.calls == []


@pytest.mark.asyncio
async def test_reused_jti_has_stable_conflict_semantics(tmp_path: Path) -> None:
    signer, verifier, _ = _build_auth(tmp_path)
    body, signed = _issue(signer)
    await _verify(verifier, signed, body)
    with pytest.raises(ServiceReplayConflictError) as captured:
        await _verify(verifier, signed, body)
    assert captured.value.status_code == 409
    assert captured.value.code == "SERVICE_TOKEN_REPLAYED"


@pytest.mark.asyncio
async def test_concurrent_jti_consumption_allows_only_one_request(tmp_path: Path) -> None:
    signer, verifier, _ = _build_auth(tmp_path)
    body, signed = _issue(signer)

    async def consume() -> ServiceJwtClaims | Exception:
        try:
            return await _verify(verifier, signed, body)
        except Exception as exc:
            return exc

    results = await asyncio.gather(consume(), consume())
    assert sum(isinstance(result, ServiceJwtClaims) for result in results) == 1
    assert sum(isinstance(result, ServiceReplayConflictError) for result in results) == 1


@pytest.mark.asyncio
async def test_write_scope_fails_closed_when_redis_is_unavailable(tmp_path: Path) -> None:
    signer, verifier, redis = _build_auth(
        tmp_path,
        replay_policy=ReplayPolicy.WRITE_SCOPES_ONLY,
    )
    redis.error = ConnectionError("包含敏感地址的底层错误")
    body, signed = _issue(signer, scope=ServiceScope.TOOL_WRITE)
    with pytest.raises(ServiceReplayUnavailableError) as captured:
        await _verify(verifier, signed, body, scope=ServiceScope.TOOL_WRITE)
    assert captured.value.code == "SERVICE_REPLAY_STORE_UNAVAILABLE"
    assert "敏感地址" not in str(captured.value)
    rendered_traceback = "".join(
        traceback.format_exception(
            type(captured.value),
            captured.value,
            captured.value.__traceback__,
        )
    )
    assert "敏感地址" not in rendered_traceback


@pytest.mark.asyncio
async def test_static_policy_can_skip_read_replay_but_never_write_replay(tmp_path: Path) -> None:
    signer, verifier, redis = _build_auth(
        tmp_path,
        replay_policy=ReplayPolicy.WRITE_SCOPES_ONLY,
    )
    read_body, read_signed = _issue(signer, scope=ServiceScope.TOOL_READ)
    await _verify(verifier, read_signed, read_body, scope=ServiceScope.TOOL_READ)
    await _verify(verifier, read_signed, read_body, scope=ServiceScope.TOOL_READ)
    assert redis.calls == []

    write_body, write_signed = _issue(signer, scope=ServiceScope.TOOL_WRITE)
    await _verify(verifier, write_signed, write_body, scope=ServiceScope.TOOL_WRITE)
    assert len(redis.calls) == 1


@pytest.mark.asyncio
async def test_expiry_ttl_and_clock_skew_are_strictly_limited(tmp_path: Path) -> None:
    signer, verifier, _ = _build_auth(tmp_path, skew_seconds=10)
    with pytest.raises(ValueError, match="300"):
        _issue(signer, ttl_seconds=301)
    other_path = tmp_path / "other"
    other_path.mkdir()
    with pytest.raises(ValueError, match="30"):
        _build_auth(other_path, skew_seconds=31)

    body, signed = _issue(signer)
    await _verify(verifier, signed, body, now_seconds=NOW_SECONDS + 10)
    with pytest.raises(ServiceRequestBindingError, match="时间"):
        await _verify(verifier, signed, body, now_seconds=NOW_SECONDS + 11)

    expired_body, expired_signed = _issue(signer, now_seconds=NOW_SECONDS - 131)
    with pytest.raises(ServiceAuthenticationError, match="过期"):
        await _verify(verifier, expired_signed, expired_body)

    future_body, future_signed = _issue(signer, now_seconds=NOW_SECONDS + 11)
    with pytest.raises(ServiceAuthenticationError, match="尚未生效"):
        await _verify(verifier, future_signed, future_body)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("issuer", "subject", "audience"),
    [
        ("other", "core-api", "agent-service"),
        ("core-api", "other", "agent-service"),
        ("core-api", "core-api", "other"),
    ],
)
async def test_strict_service_identity_rejects_wrong_values(
    tmp_path: Path,
    issuer: str,
    subject: str,
    audience: str,
) -> None:
    private_path, jwks_path, _ = _write_key_pair(tmp_path, "core", "core-v2")
    signer = ServiceTokenSigner.from_pkcs8_file(
        private_path,
        issuer=issuer,
        subject=subject,
        audience=audience,
        kid="core-v2",
    )
    verifier = ServiceTokenVerifier.from_jwks_file(
        jwks_path,
        expected_issuer="core-api",
        expected_subject="core-api",
        audience="agent-service",
        replay_store=RedisReplayStore(FakeRedis()),
    )
    body, signed = _issue(signer)
    with pytest.raises(ServiceAuthenticationError):
        await _verify(verifier, signed, body)


@pytest.mark.asyncio
async def test_unknown_kid_and_algorithm_confusion_are_rejected(tmp_path: Path) -> None:
    signer, verifier, _ = _build_auth(tmp_path)
    body, signed = _issue(signer)
    wrong_kid = jwt.encode(
        jwt.decode(signed.token, options={"verify_signature": False}),
        signer._private_key,
        algorithm="EdDSA",
        headers={"alg": "EdDSA", "typ": "JWT", "kid": "unknown"},
    )
    with pytest.raises(ServiceAuthenticationError, match="kid"):
        await _verify(verifier, replace(signed, token=wrong_kid), body)

    confused = jwt.encode(
        jwt.decode(signed.token, options={"verify_signature": False}),
        "browser-hs256-secret-with-at-least-32-bytes",
        algorithm="HS256",
        headers={"alg": "HS256", "typ": "JWT", "kid": "core-v2"},
    )
    with pytest.raises(ServiceAuthenticationError, match="算法"):
        await _verify(verifier, replace(signed, token=confused), body)


@pytest.mark.asyncio
async def test_current_and_previous_jwks_keys_are_accepted(tmp_path: Path) -> None:
    old_private_path, old_jwks_path, _ = _write_key_pair(tmp_path, "old", "core-v1")
    new_private_path, new_jwks_path, _ = _write_key_pair(tmp_path, "new", "core-v2")
    old_key = json.loads(old_jwks_path.read_text(encoding="utf-8"))["keys"][0]
    new_key = json.loads(new_jwks_path.read_text(encoding="utf-8"))["keys"][0]
    combined_path = tmp_path / "combined.jwks.json"
    combined_path.write_text(json.dumps({"keys": [new_key, old_key]}), encoding="utf-8")
    verifier = ServiceTokenVerifier.from_jwks_file(
        combined_path,
        expected_issuer="core-api",
        expected_subject="core-api",
        audience="agent-service",
        replay_store=RedisReplayStore(FakeRedis()),
        replay_policy=ReplayPolicy.WRITE_SCOPES_ONLY,
    )

    for private_path, kid, jti in (
        (new_private_path, "core-v2", "jti-new"),
        (old_private_path, "core-v1", "jti-old"),
    ):
        signer = ServiceTokenSigner.from_pkcs8_file(
            private_path,
            issuer="core-api",
            subject="core-api",
            audience="agent-service",
            kid=kid,
        )
        body = canonical_json_body({"key": kid})
        signed = signer.sign_request(
            body=body,
            http_method="POST",
            http_path="/internal/v1/runs",
            idempotency_key=f"idem-{kid}",
            scope=(ServiceScope.AGENT_RUN,),
            task_id="task-1",
            run_id="run-1",
            novel_id="novel-1",
            now=NOW_SECONDS,
            jti=jti,
        )
        await _verify(
            verifier,
            signed,
            body,
            idempotency_key=f"idem-{kid}",
        )


def test_jwks_rejects_private_material_duplicate_kid_and_more_than_two_keys(tmp_path: Path) -> None:
    _, jwks_path, _ = _write_key_pair(tmp_path, "key", "core-v1")
    key = json.loads(jwks_path.read_text(encoding="utf-8"))["keys"][0]
    cases = (
        {"keys": [{**key, "d": "secret"}]},
        {"keys": [key, key]},
        {"keys": [key, {**key, "kid": "core-v2"}, {**key, "kid": "core-v3"}]},
    )
    for index, case in enumerate(cases):
        path = tmp_path / f"invalid-{index}.json"
        path.write_text(json.dumps(case), encoding="utf-8")
        with pytest.raises(ServiceAuthenticationError):
            ServiceTokenVerifier.from_jwks_file(
                path,
                expected_issuer="core-api",
                expected_subject="core-api",
                audience="agent-service",
                replay_store=RedisReplayStore(FakeRedis()),
            )


def test_verifier_only_loads_jwks_and_rejects_unknown_replay_policy(tmp_path: Path) -> None:
    _, jwks_path, private_key = _write_key_pair(tmp_path, "core", "core-v1")
    with pytest.raises(TypeError):
        ServiceTokenVerifier(
            public_keys={"core-v1": private_key.public_key()},
            expected_issuer="core-api",
            expected_subject="core-api",
            audience="agent-service",
            replay_store=RedisReplayStore(FakeRedis()),
        )
    with pytest.raises(ValueError, match="重放策略"):
        ServiceTokenVerifier.from_jwks_file(
            jwks_path,
            expected_issuer="core-api",
            expected_subject="core-api",
            audience="agent-service",
            replay_store=RedisReplayStore(FakeRedis()),
            replay_policy="disabled",  # type: ignore[arg-type]
        )


def test_authentication_errors_do_not_expose_token_key_or_claims(tmp_path: Path) -> None:
    _, verifier, _ = _build_auth(tmp_path)
    sensitive = "eyJ-secret-token"

    async def verify() -> None:
        with pytest.raises(ServiceAuthenticationError) as captured:
            await verifier.verify_request(
                token=sensitive,
                body=b"{}",
                http_method="POST",
                http_path="/internal/v1/runs",
                idempotency_key="idem-1",
                request_timestamp=str(NOW_SECONDS),
                body_sha256=hashlib.sha256(b"{}").hexdigest(),
                required_scope=ServiceScope.AGENT_RUN,
                task_id="task-1",
                run_id="run-1",
                novel_id="novel-1",
                now=NOW_SECONDS,
            )
        rendered = str(captured.value)
        assert sensitive not in rendered
        assert "task-1" not in rendered

    asyncio.run(verify())
