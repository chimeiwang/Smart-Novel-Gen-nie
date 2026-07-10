from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import CreditLedger, User

SIGNUP_BONUS_MICROS = 1_000_000_000
USERNAME_UNIQUE_CONSTRAINT = "User_username_key"


@dataclass(frozen=True, slots=True)
class AuthUser:
    id: str
    username: str
    password_hash: str
    credit_balance_micros: int


class DuplicateUsernameError(Exception):
    """表示注册用户名与并发提交或现有记录冲突。"""


class AuthRepositoryPort(Protocol):
    async def find_by_username(self, username: str) -> AuthUser | None: ...

    async def find_by_id(self, user_id: str) -> AuthUser | None: ...

    async def register_user(self, username: str, password_hash: str) -> AuthUser: ...


class AuthRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_by_username(self, username: str) -> AuthUser | None:
        async with self._session_factory() as session:
            result = await session.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
        return _to_auth_user(user)

    async def find_by_id(self, user_id: str) -> AuthUser | None:
        async with self._session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
        return _to_auth_user(user)

    async def register_user(self, username: str, password_hash: str) -> AuthUser:
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    user = User(
                        username=username,
                        passwordHash=password_hash,
                        creditBalanceMicros=SIGNUP_BONUS_MICROS,
                    )
                    session.add(user)
                    await session.flush()
                    ledger = CreditLedger(
                        userId=user.id,
                        type="signup_bonus",
                        amountMicros=SIGNUP_BONUS_MICROS,
                        balanceAfterMicros=SIGNUP_BONUS_MICROS,
                        note="注册赠送 1000 积分",
                        promptTokens=0,
                        completionTokens=0,
                        cachedTokens=0,
                        totalTokens=0,
                    )
                    session.add(ledger)
                    await session.flush()
                snapshot = _to_auth_user(user)
        except IntegrityError as exc:
            if is_username_unique_violation(exc):
                raise DuplicateUsernameError from exc
            raise
        if snapshot is None:
            raise RuntimeError("注册事务未返回用户")
        return snapshot


def is_username_unique_violation(exc: IntegrityError) -> bool:
    """只根据驱动暴露的约束名识别用户名唯一约束冲突。"""

    current: BaseException | None = exc.orig
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if getattr(current, "constraint_name", None) == USERNAME_UNIQUE_CONSTRAINT:
            return True
        diagnostic = getattr(current, "diag", None)
        if getattr(diagnostic, "constraint_name", None) == USERNAME_UNIQUE_CONSTRAINT:
            return True
        cause = current.__cause__
        current = cause if isinstance(cause, BaseException) else current.__context__
    return False


def _to_auth_user(user: User | None) -> AuthUser | None:
    if user is None:
        return None
    return AuthUser(
        id=user.id,
        username=user.username,
        password_hash=user.passwordHash,
        credit_balance_micros=user.creditBalanceMicros,
    )
