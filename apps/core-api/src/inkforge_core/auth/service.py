from __future__ import annotations

import asyncio
import hashlib
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol, cast

import bcrypt
import jwt

from ..config import OLD_DEFAULT_JWT_SECRET
from ..errors import ApiError
from .repository import AuthRepositoryPort, AuthUser, DuplicateUsernameError

COOKIE_NAME = "inkforge-token"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
_USERNAME_PATTERN = re.compile(r"^[a-z0-9_-]{3,32}$")
_DUMMY_PASSWORD_HASH = "$2b$12$" + "C6UzMDM.H6dfI/f/IKcEe.5mGuDVYXrHD1Lh5MJ5CnCGg9iMi2D0S"
_RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
local ttl = redis.call('PTTL', KEYS[1])
return {count, ttl}
"""


class InvalidSessionToken(Exception):
    """表示浏览器会话令牌无法通过兼容性校验。"""


class AsyncRedisRateLimit(Protocol):
    async def eval(
        self,
        script: str,
        key_count: int,
        key: str,
        limit: int,
        window_ms: int,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    limit: int
    window_ms: int


RATE_LIMIT_POLICIES: dict[Literal["login", "register"], RateLimitPolicy] = {
    "login": RateLimitPolicy(limit=5, window_ms=60_000),
    "register": RateLimitPolicy(limit=3, window_ms=3_600_000),
}


class RedisRateLimiter:
    def __init__(self, redis: AsyncRedisRateLimit, *, key_prefix: str = "auth:limit:") -> None:
        self._redis = redis
        self._key_prefix = key_prefix

    async def check(
        self,
        action: Literal["login", "register"],
        *,
        client_identity: str,
        username: str,
    ) -> None:
        policy = RATE_LIMIT_POLICIES[action]
        identity_digest = hashlib.sha256(
            f"{client_identity}\0{username}".encode()
        ).hexdigest()
        key = f"{self._key_prefix}{action}:{identity_digest}"
        try:
            raw_result = await self._redis.eval(
                _RATE_LIMIT_SCRIPT,
                1,
                key,
                policy.limit,
                policy.window_ms,
            )
            result = cast(list[object] | tuple[object, ...], raw_result)
            count = int(cast(int | bytes | str, result[0]))
            ttl_ms = int(cast(int | bytes | str, result[1]))
        except Exception as exc:
            raise ApiError(
                status_code=503,
                code="RATE_LIMIT_UNAVAILABLE",
                message="认证服务暂时不可用",
            ) from exc
        if count > policy.limit:
            retry_after = max(1, math.ceil(max(ttl_ms, 0) / 1000))
            raise ApiError(
                status_code=429,
                code="RATE_LIMITED",
                message="请求过于频繁，请稍后重试",
                headers={"Retry-After": str(retry_after)},
            )


class AuthService:
    def __init__(
        self,
        *,
        repository: AuthRepositoryPort,
        rate_limiter: RedisRateLimiter,
        jwt_secret: str,
        environment: str,
    ) -> None:
        if not jwt_secret.strip():
            raise ValueError("会话签名密钥不能为空")
        if environment == "production" and jwt_secret == OLD_DEFAULT_JWT_SECRET:
            raise ValueError("生产环境禁止使用旧默认会话签名密钥")
        self._repository = repository
        self._rate_limiter = rate_limiter
        self._jwt_secret = jwt_secret
        self.environment = environment

    async def register(
        self,
        username: str,
        password: str,
        confirm_password: str,
        *,
        client_identity: str,
    ) -> AuthUser:
        normalized_username = normalize_username(username)
        await self._rate_limiter.check(
            "register",
            client_identity=client_identity,
            username=normalized_username,
        )
        if _USERNAME_PATTERN.fullmatch(normalized_username) is None:
            raise ApiError(
                status_code=400,
                code="INVALID_USERNAME",
                message="用户名只能包含 3-32 位小写字母、数字、下划线或短横线",
            )
        if utf16_code_unit_length(password) < 6:
            raise ApiError(
                status_code=400,
                code="PASSWORD_TOO_SHORT",
                message="密码至少 6 位",
            )
        if password != confirm_password:
            raise ApiError(
                status_code=400,
                code="PASSWORD_MISMATCH",
                message="两次输入的密码不一致",
            )
        password_bytes = _encode_password(password)
        if len(password_bytes) > 72:
            raise ApiError(
                status_code=400,
                code="PASSWORD_TOO_LONG",
                message="密码的 UTF-8 编码不能超过 72 字节",
            )
        password_hash = await hash_password(password)
        try:
            return await self._repository.register_user(normalized_username, password_hash)
        except DuplicateUsernameError as exc:
            raise ApiError(
                status_code=409,
                code="USERNAME_EXISTS",
                message="用户名已存在",
            ) from exc

    async def login(
        self,
        username: str,
        password: str,
        *,
        client_identity: str,
    ) -> AuthUser:
        normalized_username = normalize_username(username)
        await self._rate_limiter.check(
            "login",
            client_identity=client_identity,
            username=normalized_username,
        )
        user = (
            await self._repository.find_by_username(normalized_username)
            if normalized_username
            else None
        )
        password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
        password_valid = await verify_password(password, password_hash)
        if user is None or not password or not password_valid:
            raise _invalid_credentials()
        return user

    async def get_current_user(self, token: str | None) -> AuthUser:
        if token is None:
            raise _unauthenticated()
        try:
            user_id = self.verify_session_token(token)
        except InvalidSessionToken as exc:
            raise _unauthenticated() from exc
        user = await self._repository.find_by_id(user_id)
        if user is None:
            raise _unauthenticated()
        return user

    def create_session_token(self, user_id: str) -> str:
        now = datetime.now(UTC).replace(microsecond=0)
        return jwt.encode(
            {
                "sub": user_id,
                "iat": now,
                "exp": now + timedelta(seconds=SESSION_MAX_AGE_SECONDS),
            },
            self._jwt_secret,
            algorithm="HS256",
        )

    def verify_session_token(self, token: str) -> str:
        try:
            payload = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=["HS256"],
                options={
                    "require": ["sub", "iat", "exp"],
                    "verify_aud": False,
                },
            )
        except jwt.PyJWTError as exc:
            raise InvalidSessionToken from exc
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise InvalidSessionToken
        return subject


def normalize_username(username: str) -> str:
    return username.strip().lower()


def utf16_code_unit_length(value: str) -> int:
    return len(value.encode("utf-16-le", errors="surrogatepass")) // 2


async def hash_password(password: str) -> str:
    password_bytes = _encode_password(password)
    if len(password_bytes) > 72:
        raise ValueError("密码的 UTF-8 编码不能超过 72 字节")
    hashed = await asyncio.to_thread(bcrypt.hashpw, password_bytes, bcrypt.gensalt(rounds=12))
    return hashed.decode("ascii")


async def verify_password(password: str, password_hash: str) -> bool:
    try:
        password_bytes = password.encode("utf-8")[:72]
        hash_bytes = password_hash.encode("ascii")
        return await asyncio.to_thread(bcrypt.checkpw, password_bytes, hash_bytes)
    except (UnicodeError, ValueError):
        return False


def _encode_password(password: str) -> bytes:
    try:
        return password.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ApiError(
            status_code=400,
            code="INVALID_PASSWORD_ENCODING",
            message="密码包含无效字符",
        ) from exc


def _invalid_credentials() -> ApiError:
    return ApiError(
        status_code=401,
        code="INVALID_CREDENTIALS",
        message="用户名或密码错误",
    )


def _unauthenticated() -> ApiError:
    return ApiError(
        status_code=401,
        code="UNAUTHENTICATED",
        message="请先登录",
    )
