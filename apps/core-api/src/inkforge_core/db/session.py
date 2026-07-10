from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import monotonic
from typing import cast

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import Settings
from ..operations import register_readiness_check
from .schema_guard import SchemaVerificationResult, verify_live_schema_with_engine

SCHEMA_CONTRACT_PATH = Path(__file__).with_name("schema-contract.json")
_ASYNCPG_SSL_MODES = frozenset({"disable", "prefer", "require", "verify-ca", "verify-full"})
SchemaVerifier = Callable[[AsyncEngine, Path], Awaitable[SchemaVerificationResult]]
MonotonicClock = Callable[[], float]


def normalize_database_url(database_url: str) -> URL:
    """解析数据库地址并安全切换到 asyncpg 驱动。"""

    url = make_url(database_url)
    if url.get_backend_name() not in {"postgres", "postgresql"}:
        raise ValueError("核心接口服务只允许连接 PostgreSQL 数据库。")
    if url.drivername not in {"postgres", "postgresql", "postgresql+asyncpg"}:
        raise ValueError("数据库地址使用了不受支持的 PostgreSQL 驱动。")
    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    if sslmode is not None:
        if not isinstance(sslmode, str) or sslmode not in _ASYNCPG_SSL_MODES:
            raise ValueError("数据库地址包含不受支持的 SSL 模式。")
        existing_ssl = query.get("ssl")
        if existing_ssl is not None and existing_ssl != sslmode:
            raise ValueError("数据库地址包含冲突的 SSL 配置。")
        query["ssl"] = sslmode
    return url.set(drivername="postgresql+asyncpg", query=query)


def create_database_engine(database_url: str) -> AsyncEngine:
    """创建受单机资源预算约束的异步数据库引擎。"""

    return create_async_engine(
        normalize_database_url(database_url),
        pool_size=5,
        max_overflow=0,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """创建不在提交后隐式过期对象的异步会话工厂。"""

    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def check_database_connection(engine: AsyncEngine) -> bool:
    """使用无副作用查询验证数据库连接。"""

    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT 1"))
    return cast(int, result.scalar_one()) == 1


class DatabaseReadiness:
    """复用主连接池并限制结构目录检查频率。"""

    def __init__(
        self,
        engine: AsyncEngine,
        contract_path: Path,
        *,
        schema_verifier: SchemaVerifier | None = None,
        monotonic_clock: MonotonicClock = monotonic,
        success_ttl_seconds: float = 30.0,
        failure_ttl_seconds: float = 5.0,
    ) -> None:
        self._engine = engine
        self._contract_path = contract_path
        self._schema_verifier = schema_verifier or verify_live_schema_with_engine
        self._clock = monotonic_clock
        self._success_ttl_seconds = success_ttl_seconds
        self._failure_ttl_seconds = failure_ttl_seconds
        self._schema_lock = asyncio.Lock()
        self._schema_ready: bool | None = None
        self._schema_checked_at = 0.0

    async def check_connection(self) -> bool:
        try:
            return await check_database_connection(self._engine)
        except Exception:
            return False

    async def check_schema(self) -> bool:
        cached = self._cached_schema_result()
        if cached is not None:
            return cached
        async with self._schema_lock:
            cached = self._cached_schema_result()
            if cached is not None:
                return cached
            try:
                result = await self._schema_verifier(self._engine, self._contract_path)
                self._schema_ready = result.ready
            except Exception:
                self._schema_ready = False
            self._schema_checked_at = self._clock()
            return self._schema_ready

    async def warm_up(self) -> None:
        await asyncio.gather(self.check_connection(), self.check_schema())

    def _cached_schema_result(self) -> bool | None:
        if self._schema_ready is None:
            return None
        ttl = self._success_ttl_seconds if self._schema_ready else self._failure_ttl_seconds
        if self._clock() - self._schema_checked_at < ttl:
            return self._schema_ready
        return None


def configure_database(app: FastAPI, settings: Settings) -> None:
    """配置数据库资源，并把连通性和结构守卫接入就绪检查。"""

    if settings.database_url is None:
        return
    database_url = settings.database_url.get_secret_value()
    engine = create_database_engine(database_url)
    readiness = DatabaseReadiness(engine, SCHEMA_CONTRACT_PATH)
    app.state.database_engine = engine
    app.state.database_session_factory = create_session_factory(engine)
    app.state.database_readiness = readiness
    register_readiness_check(app, "database", readiness.check_connection)
    register_readiness_check(app, "database_schema", readiness.check_schema)
