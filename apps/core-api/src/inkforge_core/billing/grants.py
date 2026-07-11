from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jwt import InvalidTokenError
from pydantic import ValidationError

from .schemas import ModelGrantClaims


class ModelGrantError(Exception):
    """表示模型授权令牌无效、被篡改或已过期。"""


class ModelGrantCodec:
    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._private_key = private_key
        self._public_key = private_key.public_key()

    @classmethod
    def from_private_key_path(cls, path: str | Path) -> ModelGrantCodec:
        try:
            loaded = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
        except (OSError, TypeError, ValueError):
            raise ModelGrantError("无法加载模型授权签名密钥") from None
        if not isinstance(loaded, Ed25519PrivateKey):
            raise ModelGrantError("模型授权签名密钥必须使用 Ed25519")
        return cls(loaded)

    def issue(self, claims: ModelGrantClaims) -> str:
        payload = claims.model_dump(mode="json")
        payload.update({"iss": "core-api", "aud": "agent-service"})
        return jwt.encode(
            payload,
            self._private_key,
            algorithm="EdDSA",
            headers={"alg": "EdDSA", "typ": "JWT"},
        )

    def verify(self, token: str, *, now: datetime | None = None) -> ModelGrantClaims:
        current = now or datetime.now(UTC)
        current_seconds = int(current.timestamp())
        try:
            header = jwt.get_unverified_header(token)
            if set(header) != {"alg", "typ"} or header != {"alg": "EdDSA", "typ": "JWT"}:
                raise ValueError
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=["EdDSA"],
                audience="agent-service",
                issuer="core-api",
                options={"require": ["iss", "aud", "iat", "exp"], "verify_exp": False},
            )
            payload.pop("iss")
            payload.pop("aud")
            claims = ModelGrantClaims.model_validate(payload)
            if claims.iat > current_seconds + 30 or claims.exp < current_seconds - 30:
                raise ValueError
            return claims
        except (InvalidTokenError, ValidationError, KeyError, TypeError, ValueError):
            raise ModelGrantError("模型授权令牌无效或已过期") from None
