from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from .auth import router as auth_router
from .auth.readiness import RedisReadiness
from .auth.repository import AuthRepository
from .auth.service import AuthService, RedisRateLimiter
from .config import OLD_DEFAULT_JWT_SECRET, Settings, create_testing_settings
from .db.session import DatabaseReadiness, configure_database
from .errors import (
    PUBLIC_ERROR_RESPONSES,
    SafeUnhandledExceptionMiddleware,
    install_exception_handlers,
)
from .http import RequestIdMiddleware
from .operations import register_readiness_check
from .operations import router as operations_router
from .service_auth import install_service_auth_error_handler


def _configure_auth(app: FastAPI, settings: Settings) -> None:
    """按需创建小型 Redis 连接池，并组装浏览器认证服务。"""

    session_factory = getattr(app.state, "database_session_factory", None)
    if session_factory is None or settings.redis_url is None:
        return

    from redis.asyncio import Redis

    redis = Redis.from_url(
        settings.redis_url.get_secret_value(),
        decode_responses=False,
        max_connections=4,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )
    configured_secret = (
        settings.jwt_secret.get_secret_value()
        if settings.jwt_secret is not None
        else OLD_DEFAULT_JWT_SECRET
    )
    app.state.auth_redis = redis
    redis_readiness = RedisReadiness(redis)
    app.state.redis_readiness = redis_readiness
    register_readiness_check(app, "redis", redis_readiness.check)
    app.state.auth_service = AuthService(
        repository=AuthRepository(session_factory),
        rate_limiter=RedisRateLimiter(redis),
        jwt_secret=configured_secret,
        environment=settings.environment,
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """在应用退出时释放已创建的数据库连接池。"""

    try:
        readiness = cast(
            DatabaseReadiness | None,
            getattr(app.state, "database_readiness", None),
        )
        if readiness is not None:
            await readiness.warm_up()
        yield
    finally:
        auth_redis = getattr(app.state, "auth_redis", None)
        try:
            if auth_redis is not None:
                await auth_redis.aclose()
        finally:
            engine = cast(AsyncEngine | None, getattr(app.state, "database_engine", None))
            if engine is not None:
                await engine.dispose()


def create_app(*, testing: bool = False, settings: Settings | None = None) -> FastAPI:
    loaded_settings = settings
    if loaded_settings is None:
        loaded_settings = create_testing_settings() if testing else Settings()

    app = FastAPI(
        title="InkForge Core API",
        version="0.1.0",
        lifespan=_lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        swagger_ui_oauth2_redirect_url="/api/v1/docs/oauth2-redirect",
        responses=PUBLIC_ERROR_RESPONSES,
    )
    app.state.settings = loaded_settings
    app.state.readiness_checks = {}
    register_readiness_check(app, "configuration", lambda: True)
    configure_database(app, loaded_settings)
    _configure_auth(app, loaded_settings)
    app.add_middleware(SafeUnhandledExceptionMiddleware)
    app.add_middleware(RequestIdMiddleware)
    install_exception_handlers(app)
    install_service_auth_error_handler(app)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(operations_router, prefix="/api/v1")
    return app
