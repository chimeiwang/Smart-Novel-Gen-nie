from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import bcrypt
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from inkforge_core.app import create_app
from inkforge_core.auth.dependencies import get_auth_service
from inkforge_core.auth.repository import (
    AuthRepository,
    AuthUser,
    DuplicateUsernameError,
    is_username_unique_violation,
)
from inkforge_core.auth.service import (
    AuthService,
    RedisRateLimiter,
    hash_password,
    utf16_code_unit_length,
    verify_password,
)
from inkforge_core.config import OLD_DEFAULT_JWT_SECRET, Settings
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

TEST_JWT_KEY = "测试专用会话密钥-长度足够"


@dataclass
class FakeRepository:
    users_by_name: dict[str, AuthUser]
    users_by_id: dict[str, AuthUser]
    duplicate: bool = False
    registration_error: Exception | None = None
    lookup_names: list[str] | None = None
    lookup_ids: list[str] | None = None

    def __post_init__(self) -> None:
        self.lookup_names = []
        self.lookup_ids = []

    async def find_by_username(self, username: str) -> AuthUser | None:
        assert self.lookup_names is not None
        self.lookup_names.append(username)
        return self.users_by_name.get(username)

    async def find_by_id(self, user_id: str) -> AuthUser | None:
        assert self.lookup_ids is not None
        self.lookup_ids.append(user_id)
        return self.users_by_id.get(user_id)

    async def register_user(self, username: str, password_hash: str) -> AuthUser:
        if self.registration_error is not None:
            raise self.registration_error
        if self.duplicate:
            raise DuplicateUsernameError
        user = AuthUser(
            id="user-new",
            username=username,
            password_hash=password_hash,
            credit_balance_micros=1_000_000_000,
        )
        self.users_by_name[username] = user
        self.users_by_id[user.id] = user
        return user


class FakeRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, tuple[object, ...]]] = []
        self.results: list[list[int]] = []
        self.error: Exception | None = None
        self.closed = False
        self.ping_result: bool | Exception = True

    async def eval(self, script: str, key_count: int, *args: object) -> list[int]:
        self.calls.append((script, key_count, args))
        if self.error is not None:
            raise self.error
        if self.results:
            return self.results.pop(0)
        return [0, 0, 1, 1]

    async def ping(self) -> bool:
        if isinstance(self.ping_result, Exception):
            raise self.ping_result
        return self.ping_result

    async def aclose(self) -> None:
        self.closed = True


class CloseFailingRedis(FakeRedis):
    async def aclose(self) -> None:
        self.closed = True
        raise RuntimeError("Redis 关闭失败")


class DisposableEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


def build_service(
    repository: FakeRepository,
    *,
    redis: FakeRedis | None = None,
    jwt_key: str = TEST_JWT_KEY,
    environment: str = "test",
) -> AuthService:
    limiter = RedisRateLimiter(redis or FakeRedis(), key_prefix="测试:认证:")
    return AuthService(
        repository=repository,
        rate_limiter=limiter,
        jwt_secret=jwt_key,
        environment=environment,
    )


@asynccontextmanager
async def auth_client(service: AuthService) -> AsyncIterator[tuple[FastAPI, AsyncClient]]:
    app = create_app(testing=True)
    app.dependency_overrides[get_auth_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield app, client


def empty_repository() -> FakeRepository:
    return FakeRepository(users_by_name={}, users_by_id={})


@pytest.mark.asyncio
async def test_register_normalizes_username_and_returns_decimal_balance() -> None:
    repository = empty_repository()
    async with auth_client(build_service(repository)) as (_, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={"username": "  Alice_1  ", "password": "密码1234", "confirmPassword": "密码1234"},
        )

    assert response.status_code == 201
    assert response.json() == {
        "id": "user-new",
        "username": "alice_1",
        "creditBalanceMicros": "1000000000",
    }
    assert "inkforge-token=" in response.headers["set-cookie"]


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["ab", "a.b", "中文名", "a" * 33])
async def test_register_rejects_username_outside_legacy_rule(username: str) -> None:
    async with auth_client(build_service(empty_repository())) as (_, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={"username": username, "password": "123456", "confirmPassword": "123456"},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_USERNAME"
    assert "set-cookie" not in response.headers


def test_utf16_password_length_matches_javascript_semantics() -> None:
    assert utf16_code_unit_length("😀😀😀") == 6
    assert utf16_code_unit_length("😀😀a") == 5


@pytest.mark.asyncio
async def test_register_uses_utf16_code_units_for_minimum_password_length() -> None:
    async with auth_client(build_service(empty_repository())) as (_, client):
        accepted = await client.post(
            "/api/v1/auth/register",
            json={"username": "emoji_ok", "password": "😀😀😀", "confirmPassword": "😀😀😀"},
        )
        rejected = await client.post(
            "/api/v1/auth/register",
            json={"username": "emoji_no", "password": "😀😀a", "confirmPassword": "😀😀a"},
        )

    assert accepted.status_code == 201
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "PASSWORD_TOO_SHORT"


@pytest.mark.asyncio
async def test_register_does_not_trim_password_and_requires_exact_confirmation() -> None:
    async with auth_client(build_service(empty_repository())) as (_, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "password": "123456 ", "confirmPassword": "123456"},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "PASSWORD_MISMATCH"


@pytest.mark.asyncio
async def test_register_preserves_bcryptjs_truncation_for_password_over_72_bytes() -> None:
    shared_prefix = "a" * 72
    password = shared_prefix + "第一个后缀"
    compatible_password = shared_prefix + "另一个后缀"
    repository = empty_repository()
    async with auth_client(build_service(repository)) as (_, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "password": password, "confirmPassword": password},
        )

    assert response.status_code == 201
    created = repository.users_by_name["alice"]
    assert await verify_password(password, created.password_hash) is True
    assert await verify_password(compatible_password, created.password_hash) is True


@pytest.mark.asyncio
async def test_auth_input_rejects_unreasonably_large_password() -> None:
    oversized_password = "a" * 4097
    async with auth_client(build_service(empty_repository())) as (_, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "alice",
                "password": oversized_password,
                "confirmPassword": oversized_password,
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_register_duplicate_username_uses_stable_conflict() -> None:
    repository = empty_repository()
    repository.duplicate = True
    async with auth_client(build_service(repository)) as (_, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "password": "123456", "confirmPassword": "123456"},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "USERNAME_EXISTS"
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_register_failure_never_sets_cookie_or_exposes_exception() -> None:
    repository = empty_repository()
    repository.registration_error = RuntimeError("数据库地址和密钥不得泄露")
    async with auth_client(build_service(repository)) as (_, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "password": "123456", "confirmPassword": "123456"},
        )

    assert response.status_code == 500
    assert "set-cookie" not in response.headers
    assert "数据库地址" not in response.text
    assert "密钥" not in response.text


@pytest.mark.asyncio
async def test_login_only_normalizes_non_empty_username_without_registration_regex() -> None:
    password_hash = await hash_password("123456")
    user = AuthUser("user-1", "legacy.name", password_hash, 7)
    repository = FakeRepository({"legacy.name": user}, {user.id: user})
    async with auth_client(build_service(repository)) as (_, client):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "  LEGACY.Name ", "password": "123456"},
        )

    assert response.status_code == 200
    assert response.json()["username"] == "legacy.name"
    assert repository.lookup_names == ["legacy.name"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("username", "password"),
    [("missing", "123456"), ("alice", "wrong-password"), ("alice", "")],
)
async def test_login_returns_same_error_for_all_invalid_credentials(
    username: str, password: str
) -> None:
    password_hash = await hash_password("123456")
    user = AuthUser("user-1", "alice", password_hash, 0)
    repository = FakeRepository({"alice": user}, {user.id: user})
    async with auth_client(build_service(repository)) as (_, client):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"
    assert response.json()["message"] == "用户名或密码错误"
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_login_bad_stored_hash_is_invalid_credentials() -> None:
    user = AuthUser("user-1", "alice", "不是有效哈希", 0)
    repository = FakeRepository({"alice": user}, {user.id: user})
    async with auth_client(build_service(repository)) as (_, client):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "123456"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_invalid_unicode_password_is_still_invalid_credentials() -> None:
    password_hash = await hash_password("123456")
    user = AuthUser("user-1", "alice", password_hash, 0)
    repository = FakeRepository({"alice": user}, {user.id: user})
    async with auth_client(build_service(repository)) as (_, client):
        response = await client.post(
            "/api/v1/auth/login",
            content=b'{"username":"alice","password":"\\ud800"}',
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_missing_user_still_checks_fixed_dummy_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    checked_hashes: list[str] = []

    async def recording_verify(password: str, password_hash: str) -> bool:
        del password
        checked_hashes.append(password_hash)
        return False

    monkeypatch.setattr("inkforge_core.auth.service.verify_password", recording_verify)
    async with auth_client(build_service(empty_repository())) as (_, client):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "missing", "password": "123456"},
        )

    assert response.status_code == 401
    assert len(checked_hashes) == 1
    assert checked_hashes[0].startswith("$2b$12$")


@pytest.mark.asyncio
async def test_password_hash_uses_cost_12_and_verification_runs_in_worker_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Any, tuple[Any, ...]]] = []

    async def fake_to_thread(function: Any, *args: Any) -> Any:
        calls.append((function, args))
        return function(*args)

    monkeypatch.setattr("inkforge_core.auth.service.asyncio.to_thread", fake_to_thread)
    password_hash = await hash_password("123456")
    assert password_hash.split("$")[2] == "12"
    assert await verify_password("123456", password_hash) is True
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_legacy_bcryptjs_verification_truncates_utf8_to_72_bytes() -> None:
    prefix = b"a" * 72
    legacy_hash = bcrypt.hashpw(prefix, bcrypt.gensalt(rounds=12)).decode("ascii")
    assert await verify_password("a" * 72 + "后缀", legacy_hash) is True


@pytest.mark.asyncio
async def test_node_bcryptjs_fixed_hash_is_accepted() -> None:
    # 该夹具由仓库当前 bcryptjs 使用固定成本和固定盐直接生成。
    node_bcryptjs_hash = "$2b$12$abcdefghijklmnopqrstuu54EclbqC8XduEGLYgonKPRJ3bZnTXsi"
    assert await verify_password("a" * 72 + "后缀", node_bcryptjs_hash) is True


@pytest.mark.asyncio
async def test_cookie_security_attributes_follow_environment() -> None:
    password_hash = await hash_password("123456")
    user = AuthUser("user-1", "alice", password_hash, 0)
    repository = FakeRepository({"alice": user}, {user.id: user})

    async with auth_client(build_service(repository, environment="test")) as (_, client):
        development = await client.post(
            "/api/v1/auth/login", json={"username": "alice", "password": "123456"}
        )
    async with auth_client(build_service(repository, environment="production")) as (_, client):
        production = await client.post(
            "/api/v1/auth/login", json={"username": "alice", "password": "123456"}
        )

    development_cookie = development.headers["set-cookie"]
    production_cookie = production.headers["set-cookie"]
    for value in (development_cookie, production_cookie):
        assert "HttpOnly" in value
        assert "Path=/" in value
        assert "SameSite=lax" in value
        assert "Max-Age=2592000" in value
    assert "Secure" not in development_cookie
    assert "Secure" in production_cookie


@pytest.mark.asyncio
async def test_me_reloads_user_and_rejects_deleted_user() -> None:
    password_hash = await hash_password("123456")
    user = AuthUser("user-1", "alice", password_hash, 12)
    repository = FakeRepository({"alice": user}, {user.id: user})
    service = build_service(repository)
    token = service.create_session_token(user.id)
    async with auth_client(service) as (_, client):
        client.cookies.set("inkforge-token", token)
        valid = await client.get("/api/v1/auth/me")
        repository.users_by_id.clear()
        deleted = await client.get("/api/v1/auth/me")

    assert valid.status_code == 200
    assert valid.json()["creditBalanceMicros"] == "12"
    assert repository.lookup_ids == ["user-1", "user-1"]
    assert deleted.status_code == 401
    assert deleted.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_me_rejects_missing_and_invalid_cookie() -> None:
    async with auth_client(build_service(empty_repository())) as (_, client):
        missing = await client.get("/api/v1/auth/me")
        client.cookies.set("inkforge-token", "invalid-token")
        invalid = await client.get("/api/v1/auth/me")

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.json()["code"] == "UNAUTHENTICATED"
    assert invalid.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_logout_is_idempotent_and_clears_cookie_on_same_path() -> None:
    async with auth_client(build_service(empty_repository())) as (_, client):
        client.cookies.set("inkforge-token", "invalid-token")
        response = await client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("inkforge-token=")
    assert "Path=/" in cookie
    assert "Max-Age=0" in cookie


@pytest.mark.asyncio
async def test_application_lifespan_closes_auth_redis_pool() -> None:
    from inkforge_core.app import _lifespan

    redis = FakeRedis()
    app = create_app(testing=True)
    app.state.auth_redis = redis
    async with _lifespan(app):
        assert redis.closed is False

    assert redis.closed is True


@pytest.mark.asyncio
async def test_redis_close_failure_does_not_skip_database_disposal() -> None:
    from inkforge_core.app import _lifespan

    redis = CloseFailingRedis()
    engine = DisposableEngine()
    app = create_app(testing=True)
    app.state.auth_redis = redis
    app.state.database_engine = engine
    with pytest.raises(RuntimeError, match="Redis 关闭失败"):
        async with _lifespan(app):
            pass

    assert redis.closed is True
    assert engine.disposed is True


@pytest.mark.asyncio
async def test_application_configures_small_bounded_redis_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from redis.asyncio import Redis

    captured: dict[str, Any] = {}
    redis = FakeRedis()

    def fake_from_url(url: str, **kwargs: Any) -> FakeRedis:
        captured["url"] = url
        captured.update(kwargs)
        return redis

    monkeypatch.setattr(Redis, "from_url", fake_from_url)
    app = create_app(
        settings=Settings.model_validate(
            {
                "environment": "dev",
                "database_url": "postgresql://user:password@database:5432/inkforge",
                "redis_url": "redis://redis:6379/0",
                "jwt_secret": TEST_JWT_KEY,
            }
        )
    )
    try:
        assert "redis" in app.state.readiness_checks
        assert await app.state.readiness_checks["redis"]() is True
        assert captured == {
            "url": "redis://redis:6379/0",
            "decode_responses": False,
            "max_connections": 4,
            "socket_connect_timeout": 1.0,
            "socket_timeout": 1.0,
        }
    finally:
        await app.state.database_engine.dispose()


@pytest.mark.asyncio
async def test_rate_limit_key_does_not_include_plain_username_and_has_retry_after() -> None:
    redis = FakeRedis()
    redis.results = [[1, 31_000, 6, 6]]
    async with auth_client(build_service(empty_repository(), redis=redis)) as (_, client):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "Sensitive_User", "password": "123456"},
        )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "31"
    assert response.json()["code"] == "RATE_LIMITED"
    assert len(redis.calls) == 1
    _, key_count, args = redis.calls[0]
    source_key, account_key, source_limit, source_window, account_limit, account_window = args
    assert key_count == 2
    assert "sensitive_user" not in str(source_key)
    assert "sensitive_user" not in str(account_key)
    assert (source_limit, source_window) == (20, 60_000)
    assert (account_limit, account_window) == (5, 60_000)


@pytest.mark.asyncio
async def test_register_uses_separate_rate_limit_strategy() -> None:
    redis = FakeRedis()
    async with auth_client(build_service(empty_repository(), redis=redis)) as (_, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "password": "123456", "confirmPassword": "123456"},
        )

    assert response.status_code == 201
    _, key_count, args = redis.calls[0]
    assert key_count == 2
    assert args[2:] == (3, 3_600_000, 3, 3_600_000)


@pytest.mark.asyncio
async def test_redis_failure_fails_closed_without_sensitive_details() -> None:
    redis = FakeRedis()
    redis.error = ConnectionError("redis://:密码@内部地址")
    async with auth_client(build_service(empty_repository(), redis=redis)) as (_, client):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "123456"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "RATE_LIMIT_UNAVAILABLE"
    assert "内部地址" not in response.text
    assert "密码" not in response.text


def test_unique_violation_only_accepts_exact_postgresql_constraint() -> None:
    class DriverError(Exception):
        constraint_name = "User_username_key"

    class WrongDriverError(Exception):
        constraint_name = "Other_key"

    matching = IntegrityError("语句", {}, DriverError())
    wrong = IntegrityError("包含 User_username_key 的异常文本", {}, WrongDriverError())
    assert is_username_unique_violation(matching) is True
    assert is_username_unique_violation(wrong) is False


def test_production_rejects_old_default_browser_jwt_secret() -> None:
    values = {
        "environment": "production",
        "database_url": "postgresql://user:password@database:5432/inkforge",
        "redis_url": "redis://redis:6379/0",
        "jwt_secret": OLD_DEFAULT_JWT_SECRET,
        "trusted_proxy_cidrs": ["172.16.0.0/12"],
        "trusted_agent_cidrs": ["10.20.0.0/16"],
        "core_service_private_key_path": "/run/secrets/core-private.pem",
        "agent_service_public_key_path": "/run/secrets/agent-public.pem",
        "agent_service_url": "http://agent-service:8001",
    }
    with pytest.raises(ValidationError, match="禁止使用旧默认"):
        Settings.model_validate(values)


def test_auth_service_rejects_blank_key_in_all_environments() -> None:
    blank_jwt_key = "   "
    with pytest.raises(ValueError, match="不能为空"):
        AuthService(
            repository=empty_repository(),
            rate_limiter=RedisRateLimiter(FakeRedis()),
            jwt_secret=blank_jwt_key,
            environment="test",
        )
    with pytest.raises(ValueError, match="禁止使用旧默认"):
        AuthService(
            repository=empty_repository(),
            rate_limiter=RedisRateLimiter(FakeRedis()),
            jwt_secret=OLD_DEFAULT_JWT_SECRET,
            environment="production",
        )


class RecordingSession:
    def __init__(self, *, fail_ledger: bool = False) -> None:
        self.added: list[Any] = []
        self.flush_count = 0
        self.committed = False
        self.rolled_back = False
        self.fail_ledger = fail_ledger

    async def __aenter__(self) -> RecordingSession:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        try:
            yield
        except Exception:
            self.rolled_back = True
            raise
        else:
            self.committed = True

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1
        if self.fail_ledger and self.flush_count == 2:
            raise RuntimeError("流水写入失败")


@pytest.mark.asyncio
async def test_repository_creates_user_and_signup_ledger_in_one_transaction() -> None:
    session = RecordingSession()
    repository = AuthRepository(lambda: session)  # type: ignore[arg-type]
    user = await repository.register_user("alice", "哈希")

    assert session.committed is True
    assert session.rolled_back is False
    assert [type(item).__name__ for item in session.added] == ["User", "CreditLedger"]
    created_user, ledger = session.added
    assert created_user.creditBalanceMicros == 1_000_000_000
    assert ledger.userId == created_user.id
    assert ledger.type == "signup_bonus"
    assert ledger.amountMicros == 1_000_000_000
    assert ledger.balanceAfterMicros == 1_000_000_000
    assert ledger.note == "注册赠送 1000 积分"
    assert ledger.promptTokens == 0
    assert ledger.completionTokens == 0
    assert ledger.cachedTokens == 0
    assert ledger.totalTokens == 0
    assert user.username == "alice"


@pytest.mark.asyncio
async def test_repository_rolls_back_user_when_ledger_insert_fails() -> None:
    session = RecordingSession(fail_ledger=True)
    repository = AuthRepository(lambda: session)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="流水写入失败"):
        await repository.register_user("alice", "哈希")

    assert session.committed is False
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_public_auth_schema_does_not_expose_secrets() -> None:
    app = create_app(testing=True)
    schema = app.openapi()
    forbidden_keys = {"passwordHash", "jwt_secret", "token", "secret"}

    def collect_keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {
                nested_key
                for nested_value in value.values()
                for nested_key in collect_keys(nested_value)
            }
        if isinstance(value, list):
            return {
                nested_key
                for nested_value in value
                for nested_key in collect_keys(nested_value)
            }
        return set()

    assert forbidden_keys.isdisjoint(collect_keys(schema))
    components = schema["components"]["schemas"]
    for request_schema in ("LoginRequest", "RegisterRequest"):
        password_schema = components[request_schema]["properties"]["password"]
        assert password_schema["format"] == "password"
        assert password_schema["writeOnly"] is True
        assert password_schema["maxLength"] == 4096
