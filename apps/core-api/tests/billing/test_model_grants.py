from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from inkforge_contracts.jwt_claims import WRITE_SERVICE_SCOPES, ServiceScope
from inkforge_core.billing.grants import ModelGrantCodec, ModelGrantError
from inkforge_core.billing.repository import AuthorizationContext
from inkforge_core.billing.schemas import AuthorizeModelCallRequest, ModelGrantClaims
from inkforge_core.billing.service import BillingService
from pydantic import ValidationError


def _write_private_key(path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def _claims(now: datetime, *, lifetime_seconds: int = 120) -> ModelGrantClaims:
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
        exp=int((now + timedelta(seconds=lifetime_seconds)).timestamp()),
    )


class AuthorizationRepository:
    async def get_authorization_context(
        self, user_id: str, task_id: str, novel_id: str
    ) -> AuthorizationContext:
        del user_id, task_id, novel_id
        return AuthorizationContext(balance_micros=100_000_000)


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


def test_model_grant_accepts_1200_seconds_and_rejects_longer_lifetime() -> None:
    now = datetime.now(UTC).replace(microsecond=0)

    claims = _claims(now, lifetime_seconds=1200)

    assert claims.exp - claims.iat == 1200
    with pytest.raises(ValidationError, match="模型授权令牌有效期无效"):
        _claims(now, lifetime_seconds=1201)


def test_model_grant_remains_valid_after_old_300_second_limit(tmp_path: Path) -> None:
    key_path = tmp_path / "core.pem"
    _write_private_key(key_path)
    codec = ModelGrantCodec.from_private_key_path(key_path)
    now = datetime.now(UTC).replace(microsecond=0)
    claims = _claims(now, lifetime_seconds=1200)
    token = codec.issue(claims)

    assert codec.verify(token, now=now + timedelta(seconds=413)) == claims
    with pytest.raises(ModelGrantError):
        codec.verify(token, now=now + timedelta(seconds=1231))


def test_model_grant_applies_its_own_30_second_issued_at_tolerance(
    tmp_path: Path,
) -> None:
    key_path = tmp_path / "core.pem"
    _write_private_key(key_path)
    codec = ModelGrantCodec.from_private_key_path(key_path)
    now = datetime.now(UTC).replace(microsecond=0)

    tolerated = codec.issue(_claims(now + timedelta(seconds=30)))
    too_early = codec.issue(_claims(now + timedelta(seconds=31)))

    assert codec.verify(tolerated, now=now).iat == int(
        (now + timedelta(seconds=30)).timestamp()
    )
    with pytest.raises(ModelGrantError):
        codec.verify(too_early, now=now)


@pytest.mark.asyncio
async def test_authorize_issues_1200_second_model_grant() -> None:
    now = datetime(2026, 8, 1, 5, 0, tzinfo=UTC)
    codec = ModelGrantCodec(Ed25519PrivateKey.generate())
    service = BillingService(AuthorizationRepository(), codec)  # type: ignore[arg-type]

    response = await service.authorize(
        AuthorizeModelCallRequest(
            userId="user-1",
            novelId="novel-1",
            taskId="task-1",
            runId="run-1",
            agentId="写作",
            provider="openai_compatible",
            model="deepseek-v4-flash",
            estimatedPromptTokens=100,
            requestedMaxOutputTokens=1024,
        ),
        now=now,
    )

    claims = codec.verify(response.grantToken, now=now)
    assert claims.exp - claims.iat == 1200
    assert response.expiresAt == now + timedelta(seconds=1200)


def test_billing_scopes_have_correct_direction_and_replay_policy() -> None:
    assert ServiceScope.BILLING_AUTHORIZE.value == "billing:authorize"
    assert ServiceScope.BILLING_USAGE_WRITE.value == "billing:usage:write"
    assert ServiceScope.BILLING_AUTHORIZE not in WRITE_SERVICE_SCOPES
    assert ServiceScope.BILLING_USAGE_WRITE in WRITE_SERVICE_SCOPES
