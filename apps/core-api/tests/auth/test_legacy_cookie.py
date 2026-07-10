from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from inkforge_core.auth.service import AuthService, InvalidSessionToken

from .test_auth_api import TEST_JWT_KEY, FakeRepository, build_service, empty_repository


def test_session_token_uses_hs256_string_subject_and_thirty_day_lifetime() -> None:
    jwt_key = TEST_JWT_KEY
    service = build_service(empty_repository(), jwt_key=jwt_key)
    token = service.create_session_token("user-1")
    header = jwt.get_unverified_header(token)
    payload = jwt.decode(token, jwt_key, algorithms=["HS256"])

    assert header["alg"] == "HS256"
    assert payload["sub"] == "user-1"
    assert isinstance(payload["sub"], str)
    assert payload["exp"] - payload["iat"] == 30 * 24 * 60 * 60
    assert "iss" not in payload
    assert "aud" not in payload
    assert "jti" not in payload


def test_python_accepts_legacy_jose_cookie_without_new_claims() -> None:
    # 该夹具由仓库当前 jose 使用固定声明和 HS256 直接生成。
    node_jose_fixture = (
        "eyJhbGciOiJIUzI1NiJ9."
        "eyJzdWIiOiJsZWdhY3ktdXNlciIsImlhdCI6MTcwMDAwMDAwMCwiZXhwIjo0MTAyNDQ0ODAwfQ."
        "g4qCrC8KNtFeH0fwQQEvn2TFb-V1mXpEPwePYy5NRUg"
    )
    service = build_service(empty_repository(), jwt_key=TEST_JWT_KEY)

    assert service.verify_session_token(node_jose_fixture) == "legacy-user"


def test_legacy_verifier_can_read_python_token() -> None:
    jwt_key = TEST_JWT_KEY
    service = build_service(empty_repository(), jwt_key=jwt_key)
    token = service.create_session_token("user-1")

    legacy_payload = jwt.decode(
        token,
        jwt_key,
        algorithms=["HS256"],
        options={"verify_aud": False},
    )
    assert legacy_payload["sub"] == "user-1"


@pytest.mark.parametrize(
    "token",
    [
        "不是令牌",
        jwt.encode(
            {"sub": 123, "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(days=1)},
            TEST_JWT_KEY,
            algorithm="HS256",
        ),
    ],
)
def test_invalid_or_non_string_subject_is_rejected(token: str) -> None:
    service = build_service(empty_repository())
    with pytest.raises(InvalidSessionToken):
        service.verify_session_token(token)


def test_auth_service_contract_can_be_satisfied_by_fake_repository() -> None:
    repository = FakeRepository({}, {})
    service: AuthService = build_service(repository)
    assert service is not None
