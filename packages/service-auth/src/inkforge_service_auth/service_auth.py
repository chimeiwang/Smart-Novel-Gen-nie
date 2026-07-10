from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import jwt
import orjson
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from inkforge_contracts.jwt_claims import WRITE_SERVICE_SCOPES, ServiceJwtClaims, ServiceScope
from jwt import InvalidTokenError
from pydantic import ValidationError

DEFAULT_TOKEN_TTL_SECONDS = 120
MAX_TOKEN_TTL_SECONDS = 300
DEFAULT_CLOCK_SKEW_SECONDS = 10
MAX_CLOCK_SKEW_SECONDS = 30


class ReplayPolicy(StrEnum):
    ALL_SCOPES = "all_scopes"
    WRITE_SCOPES_ONLY = "write_scopes_only"


class ServiceAuthError(Exception):
    def __init__(self, message: str, *, code: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class ServiceAuthenticationError(ServiceAuthError):
    def __init__(self, message: str = "服务身份认证失败") -> None:
        super().__init__(message, code="SERVICE_AUTHENTICATION_FAILED", status_code=401)


class ServiceRequestBindingError(ServiceAuthError):
    def __init__(self, message: str = "服务请求绑定校验失败") -> None:
        super().__init__(message, code="SERVICE_REQUEST_BINDING_INVALID", status_code=401)


class ServiceAuthorizationError(ServiceAuthError):
    def __init__(self, message: str, *, code: str = "SERVICE_AUTHORIZATION_FAILED") -> None:
        super().__init__(message, code=code, status_code=403)


class ServiceReplayConflictError(ServiceAuthError):
    def __init__(self) -> None:
        super().__init__("服务令牌已被使用", code="SERVICE_TOKEN_REPLAYED", status_code=409)


class ServiceReplayUnavailableError(ServiceAuthError):
    def __init__(self) -> None:
        super().__init__(
            "服务请求重放保护暂不可用",
            code="SERVICE_REPLAY_STORE_UNAVAILABLE",
            status_code=503,
        )


class AsyncRedisSet(Protocol):
    async def set(self, key: str, value: str, *, nx: bool, ex: int) -> object: ...


class ReplayStore(Protocol):
    async def consume(self, jti: str, *, ttl_seconds: int) -> bool: ...


class RedisReplayStore:
    def __init__(self, redis: AsyncRedisSet, *, key_prefix: str = "service-auth:replay:") -> None:
        self._redis = redis
        self._key_prefix = key_prefix

    async def consume(self, jti: str, *, ttl_seconds: int) -> bool:
        result = await self._redis.set(
            f"{self._key_prefix}{jti}",
            "1",
            nx=True,
            ex=ttl_seconds,
        )
        return bool(result)


@dataclass(frozen=True, slots=True)
class SignedServiceRequest:
    token: str
    headers: Mapping[str, str]


def canonical_json_body(value: object) -> bytes:
    return orjson.dumps(value)


def canonical_http_method(value: str) -> str:
    method = value.strip().upper()
    if not method.isascii() or not method.isalpha() or not 3 <= len(method) <= 16:
        raise ValueError("HTTP 方法无效")
    return method


def canonical_http_path(value: str) -> str:
    if (
        not value.startswith("/")
        or "?" in value
        or "#" in value
        or "\\" in value
        or "%" in value
        or any(ord(character) < 0x21 or ord(character) == 0x7F for character in value)
    ):
        raise ValueError("HTTP 路径必须是不含查询参数和编码别名的规范绝对路径")
    if value == "/":
        return value
    segments = value.split("/")[1:]
    if (
        len(value) > 2048
        or value.endswith("/")
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        raise ValueError("HTTP 路径不是规范路径")
    return value


def _utc_seconds(value: int | datetime | None) -> int:
    if value is None:
        return int(time.time())
    if isinstance(value, bool):
        raise ValueError("时间必须使用 UTC 秒")
    if isinstance(value, int):
        return value
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("时间必须包含时区")
    return int(value.timestamp())


def _validate_ttl(ttl_seconds: int) -> int:
    if isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= MAX_TOKEN_TTL_SECONDS:
        raise ValueError("服务令牌有效期必须在 1 到 300 秒之间")
    return ttl_seconds


def _validate_skew(clock_skew_seconds: int) -> int:
    if (
        isinstance(clock_skew_seconds, bool)
        or not 0 <= clock_skew_seconds <= MAX_CLOCK_SKEW_SECONDS
    ):
        raise ValueError("服务令牌时钟偏差必须在 0 到 30 秒之间")
    return clock_skew_seconds


class ServiceTokenSigner:
    def __init__(
        self,
        *,
        private_key_path: str | Path,
        issuer: str,
        subject: str,
        audience: str,
        kid: str,
        default_ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
    ) -> None:
        self._private_key = _load_private_key(private_key_path)
        self.public_key = self._private_key.public_key()
        self._issuer = _non_blank(issuer, "签发者")
        self._subject = _non_blank(subject, "主体")
        self._audience = _non_blank(audience, "受众")
        self._kid = _non_blank(kid, "kid")
        self._default_ttl_seconds = _validate_ttl(default_ttl_seconds)

    @classmethod
    def from_pkcs8_file(
        cls,
        path: str | Path,
        *,
        issuer: str,
        subject: str,
        audience: str,
        kid: str,
        default_ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
    ) -> ServiceTokenSigner:
        return cls(
            private_key_path=path,
            issuer=issuer,
            subject=subject,
            audience=audience,
            kid=kid,
            default_ttl_seconds=default_ttl_seconds,
        )

    def sign_request(
        self,
        *,
        body: bytes,
        http_method: str,
        http_path: str,
        idempotency_key: str,
        scope: Sequence[ServiceScope],
        task_id: str,
        run_id: str,
        novel_id: str,
        now: int | datetime | None = None,
        ttl_seconds: int | None = None,
        jti: str | None = None,
    ) -> SignedServiceRequest:
        if not isinstance(body, bytes):
            raise TypeError("请求体必须是原始字节")
        issued_at = _utc_seconds(now)
        lifetime = _validate_ttl(
            self._default_ttl_seconds if ttl_seconds is None else ttl_seconds
        )
        digest = hashlib.sha256(body).hexdigest()
        method = canonical_http_method(http_method)
        path = canonical_http_path(http_path)
        idempotency = _non_blank(idempotency_key, "Idempotency-Key")
        claims = ServiceJwtClaims(
            iss=self._issuer,
            sub=self._subject,
            aud=self._audience,
            scope=tuple(scope),
            task_id=task_id,
            run_id=run_id,
            novel_id=novel_id,
            jti=jti or str(uuid.uuid4()),
            iat=issued_at,
            exp=issued_at + lifetime,
            body_sha256=digest,
            idempotency_key=idempotency,
            request_timestamp=issued_at,
            http_method=method,
            http_path=path,
        )
        token = jwt.encode(
            claims.model_dump(mode="json"),
            self._private_key,
            algorithm="EdDSA",
            headers={"alg": "EdDSA", "typ": "JWT", "kid": self._kid},
        )
        return SignedServiceRequest(
            token=token,
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": idempotency,
                "X-InkForge-Timestamp": str(issued_at),
                "X-InkForge-Body-SHA256": digest,
            },
        )


class ServiceTokenVerifier:
    def __init__(
        self,
        *,
        jwks_path: str | Path,
        expected_issuer: str,
        expected_subject: str,
        audience: str,
        replay_store: ReplayStore,
        replay_policy: ReplayPolicy = ReplayPolicy.ALL_SCOPES,
        clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
    ) -> None:
        public_keys = _load_jwks(jwks_path)
        if not 1 <= len(public_keys) <= 2:
            raise ServiceAuthenticationError("JWKS 必须包含当前密钥和至多一个上一密钥")
        if not isinstance(replay_policy, ReplayPolicy):
            raise ValueError("服务令牌重放策略无效")
        self._public_keys = dict(public_keys)
        self._expected_issuer = _non_blank(expected_issuer, "签发者")
        self._expected_subject = _non_blank(expected_subject, "主体")
        self._audience = _non_blank(audience, "受众")
        self._replay_store = replay_store
        self._replay_policy = replay_policy
        self._clock_skew_seconds = _validate_skew(clock_skew_seconds)

    @classmethod
    def from_jwks_file(
        cls,
        path: str | Path,
        *,
        expected_issuer: str,
        expected_subject: str,
        audience: str,
        replay_store: ReplayStore,
        replay_policy: ReplayPolicy = ReplayPolicy.ALL_SCOPES,
        clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
    ) -> ServiceTokenVerifier:
        _validate_skew(clock_skew_seconds)
        return cls(
            jwks_path=path,
            expected_issuer=expected_issuer,
            expected_subject=expected_subject,
            audience=audience,
            replay_store=replay_store,
            replay_policy=replay_policy,
            clock_skew_seconds=clock_skew_seconds,
        )

    async def verify_request(
        self,
        *,
        token: str,
        body: bytes,
        http_method: str,
        http_path: str,
        idempotency_key: str,
        request_timestamp: str,
        body_sha256: str,
        required_scope: ServiceScope,
        task_id: str,
        run_id: str,
        novel_id: str,
        now: int | datetime | None = None,
    ) -> ServiceJwtClaims:
        current_time = _utc_seconds(now)
        claims = self._authenticate_token(token, now=current_time)
        self._verify_request_binding(
            claims,
            body=body,
            http_method=http_method,
            http_path=http_path,
            idempotency_key=idempotency_key,
            request_timestamp=request_timestamp,
            body_sha256=body_sha256,
            now=current_time,
        )
        self._verify_resources(
            claims,
            task_id=task_id,
            run_id=run_id,
            novel_id=novel_id,
        )
        if required_scope not in claims.scope:
            raise ServiceAuthorizationError(
                "服务令牌缺少所需权限范围",
                code="SERVICE_SCOPE_FORBIDDEN",
            )
        if self._must_consume_replay(required_scope):
            ttl_seconds = max(1, claims.exp + self._clock_skew_seconds - current_time)
            try:
                consumed = await self._replay_store.consume(
                    claims.jti,
                    ttl_seconds=ttl_seconds,
                )
            except Exception:
                raise ServiceReplayUnavailableError() from None
            if not consumed:
                raise ServiceReplayConflictError()
        return claims

    def _authenticate_token(self, token: str, *, now: int) -> ServiceJwtClaims:
        try:
            header = jwt.get_unverified_header(token)
        except (InvalidTokenError, ValueError, TypeError):
            raise ServiceAuthenticationError() from None
        if set(header) != {"alg", "typ", "kid"}:
            raise ServiceAuthenticationError("服务令牌头字段无效")
        if header.get("alg") != "EdDSA":
            raise ServiceAuthenticationError("服务令牌算法无效")
        if header.get("typ") != "JWT":
            raise ServiceAuthenticationError("服务令牌类型无效")
        kid = header.get("kid")
        if not isinstance(kid, str) or kid not in self._public_keys:
            raise ServiceAuthenticationError("服务令牌 kid 未知")
        try:
            payload = jwt.decode(
                token,
                self._public_keys[kid],
                algorithms=["EdDSA"],
                audience=self._audience,
                issuer=self._expected_issuer,
                subject=self._expected_subject,
                options={
                    "require": [
                        "iss",
                        "sub",
                        "aud",
                        "scope",
                        "task_id",
                        "run_id",
                        "novel_id",
                        "jti",
                        "iat",
                        "exp",
                        "body_sha256",
                        "idempotency_key",
                        "request_timestamp",
                        "http_method",
                        "http_path",
                    ],
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
            claims = ServiceJwtClaims.model_validate(payload)
        except (InvalidTokenError, ValidationError, ValueError, TypeError):
            raise ServiceAuthenticationError() from None
        if claims.iat > now + self._clock_skew_seconds:
            raise ServiceAuthenticationError("服务令牌尚未生效")
        if claims.exp < now - self._clock_skew_seconds:
            raise ServiceAuthenticationError("服务令牌已过期")
        return claims

    def _verify_request_binding(
        self,
        claims: ServiceJwtClaims,
        *,
        body: bytes,
        http_method: str,
        http_path: str,
        idempotency_key: str,
        request_timestamp: str,
        body_sha256: str,
        now: int,
    ) -> None:
        try:
            if not request_timestamp.isascii() or str(int(request_timestamp)) != request_timestamp:
                raise ValueError
            timestamp = int(request_timestamp)
            method = canonical_http_method(http_method)
            path = canonical_http_path(http_path)
        except (AttributeError, TypeError, ValueError):
            raise ServiceRequestBindingError("服务请求绑定头格式无效") from None
        if abs(now - timestamp) > self._clock_skew_seconds:
            raise ServiceRequestBindingError("服务请求时间超出允许偏差")
        expected_digest = hashlib.sha256(body).hexdigest()
        if not hmac.compare_digest(body_sha256, expected_digest) or not hmac.compare_digest(
            claims.body_sha256,
            expected_digest,
        ):
            raise ServiceRequestBindingError("服务请求体摘要不匹配")
        bindings = (
            (claims.request_timestamp, timestamp, "请求时间"),
            (claims.idempotency_key, idempotency_key, "幂等键"),
            (claims.http_method, method, "HTTP 方法"),
            (claims.http_path, path, "HTTP 路径"),
        )
        for claim_value, request_value, label in bindings:
            if claim_value != request_value:
                raise ServiceRequestBindingError(f"服务请求{label}不匹配")

    @staticmethod
    def _verify_resources(
        claims: ServiceJwtClaims,
        *,
        task_id: str,
        run_id: str,
        novel_id: str,
    ) -> None:
        resources = (
            ("task_id", claims.task_id, task_id),
            ("run_id", claims.run_id, run_id),
            ("novel_id", claims.novel_id, novel_id),
        )
        for field_name, claim_value, requested_value in resources:
            if claim_value != requested_value:
                raise ServiceAuthorizationError(
                    f"服务令牌资源绑定不匹配：{field_name}",
                    code="SERVICE_RESOURCE_MISMATCH",
                )

    def _must_consume_replay(self, required_scope: ServiceScope) -> bool:
        return (
            self._replay_policy is ReplayPolicy.ALL_SCOPES
            or required_scope in WRITE_SERVICE_SCOPES
        )


def _load_jwks(path: str | Path) -> dict[str, Ed25519PublicKey]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(document, dict) or set(document) != {"keys"}:
            raise ValueError
        keys = document["keys"]
        if not isinstance(keys, list) or not 1 <= len(keys) <= 2:
            raise ValueError
        loaded: dict[str, Ed25519PublicKey] = {}
        for item in keys:
            if not isinstance(item, dict) or set(item) != {
                "kty",
                "crv",
                "x",
                "kid",
                "use",
                "alg",
            }:
                raise ValueError
            if (
                item["kty"] != "OKP"
                or item["crv"] != "Ed25519"
                or item["use"] != "sig"
                or item["alg"] != "EdDSA"
                or not isinstance(item["kid"], str)
                or not item["kid"]
                or item["kid"] in loaded
                or not isinstance(item["x"], str)
            ):
                raise ValueError
            raw_key = jwt.utils.base64url_decode(item["x"].encode("ascii"))
            loaded[item["kid"]] = Ed25519PublicKey.from_public_bytes(raw_key)
        return loaded
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        raise ServiceAuthenticationError("无法加载本地 Ed25519 JWKS") from None


def _load_private_key(path: str | Path) -> Ed25519PrivateKey:
    try:
        private_bytes = Path(path).read_bytes()
        if not private_bytes.startswith(b"-----BEGIN PRIVATE KEY-----"):
            raise ValueError
        loaded = serialization.load_pem_private_key(private_bytes, password=None)
        if not isinstance(loaded, Ed25519PrivateKey):
            raise ValueError
        return loaded
    except (OSError, TypeError, ValueError):
        raise ServiceAuthenticationError("无法加载 Ed25519 PKCS8 私钥") from None


def _non_blank(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label}不能为空")
    return normalized
