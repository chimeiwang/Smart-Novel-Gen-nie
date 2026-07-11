from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from inkforge_contracts.jwt_claims import WRITE_SERVICE_SCOPES, ServiceScope
from inkforge_core.billing.grants import ModelGrantCodec, ModelGrantError
from inkforge_core.billing.schemas import ModelGrantClaims


def _write_private_key(path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def _claims(now: datetime) -> ModelGrantClaims:
    return ModelGrantClaims(
        requestId="request-1",
        taskId="task-1",
        runId="run-1",
        novelId="novel-1",
        userId="user-1",
        provider="openai_compatible",
        model="deepseek-v4-flash",
        agentId="写作",
        maxOutputTokens=1024,
        billable=True,
        iat=int(now.timestamp()),
        exp=int((now + timedelta(minutes=2)).timestamp()),
    )


def test_model_grant_is_signed_and_bound_to_full_authorization(tmp_path: Path) -> None:
    key_path = tmp_path / "core.pem"
    _write_private_key(key_path)
    codec = ModelGrantCodec.from_private_key_path(key_path)
    now = datetime.now(UTC).replace(microsecond=0)

    token = codec.issue(_claims(now))

    assert codec.verify(token, now=now) == _claims(now)


def test_model_grant_rejects_tampered_payload(tmp_path: Path) -> None:
    key_path = tmp_path / "core.pem"
    _write_private_key(key_path)
    codec = ModelGrantCodec.from_private_key_path(key_path)
    now = datetime.now(UTC).replace(microsecond=0)
    token = codec.issue(_claims(now))
    header, payload, signature = token.split(".")
    decoded = jwt.api_jws.get_unverified_header(token)
    assert decoded["alg"] == "EdDSA"

    with pytest.raises(ModelGrantError):
        codec.verify(f"{header}.{payload[:-1]}A.{signature}", now=now)


def test_billing_scopes_have_correct_direction_and_replay_policy() -> None:
    assert ServiceScope.BILLING_AUTHORIZE.value == "billing:authorize"
    assert ServiceScope.BILLING_USAGE_WRITE.value == "billing:usage:write"
    assert ServiceScope.BILLING_AUTHORIZE not in WRITE_SERVICE_SCOPES
    assert ServiceScope.BILLING_USAGE_WRITE in WRITE_SERVICE_SCOPES
