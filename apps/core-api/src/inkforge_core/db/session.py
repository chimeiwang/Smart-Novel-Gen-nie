from __future__ import annotations

from pathlib import Path
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
from .schema_guard import verify_live_schema

SCHEMA_CONTRACT_PATH = Path(__file__).with_name("schema-contract.json")


def normalize_database_url(database_url: str) -> URL:
    """解析数据库地址并安全切换到 asyncpg 驱动。"""

    url = make_url(database_url)
    if url.get_backend_name() not in {"postgres", "postgresql"}:
        raise ValueError("核心接口服务只允许连接 PostgreSQL 数据库。")
    if url.drivername not in {"postgres", "postgresql", "postgresql+asyncpg"}:
        raise ValueError("数据库地址使用了不受支持的 PostgreSQL 驱动。")
    return url.set(drivername="postgresql+asyncpg")


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


def configure_database(app: FastAPI, settings: Settings) -> None:
    """配置数据库资源，并把连通性和结构守卫接入就绪检查。"""

    if settings.database_url is None:
        return
    database_url = settings.database_url.get_secret_value()
    engine = create_database_engine(database_url)
    app.state.database_engine = engine
    app.state.database_session_factory = create_session_factory(engine)

    async def database_check() -> bool:
        return await check_database_connection(engine)

    async def schema_check() -> bool:
        result = await verify_live_schema(database_url, SCHEMA_CONTRACT_PATH)
        return result.ready

    register_readiness_check(app, "database", database_check)
    register_readiness_check(app, "database_schema", schema_check)
