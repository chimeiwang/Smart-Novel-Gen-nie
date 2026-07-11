from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from inkforge_service_auth import RedisReplayStore
from sqlalchemy.ext.asyncio import AsyncEngine

from .auth import router as auth_router
from .auth.readiness import RedisReadiness
from .auth.repository import AuthRepository
from .auth.service import AuthService, RedisRateLimiter
from .chapters.repository import ChapterRepository
from .chapters.router import router as chapters_router
from .chapters.service import ChapterService
from .config import OLD_DEFAULT_JWT_SECRET, Settings, create_testing_settings
from .db.session import DatabaseReadiness, configure_database
from .errors import (
    PUBLIC_ERROR_RESPONSES,
    SafeUnhandledExceptionMiddleware,
    install_exception_handlers,
)
from .http import RequestIdMiddleware
from .lore.repository import LoreRepository
from .lore.router import router as lore_router
from .lore.service import LoreService
from .novels.repository import NovelRepository
from .novels.router import router as novels_router
from .novels.service import NovelService
from .operations import register_readiness_check
from .operations import router as operations_router
from .outlines.repository import OutlineRepository
from .outlines.router import router as outlines_router
from .outlines.service import OutlineService
from .quality.repository import QualityRepository
from .quality.router import router as quality_router
from .quality.service import QualityService
from .references.internal_router import router as references_internal_router
from .references.repository import ReferenceRepository
from .references.router import router as references_router
from .references.service import ReferenceService
from .service_auth import create_agent_callback_verifier, install_service_auth_error_handler


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


def _configure_business_services(app: FastAPI) -> None:
    """使用同一个受控会话工厂组装业务领域服务。"""

    session_factory = getattr(app.state, "database_session_factory", None)
    if session_factory is None:
        return
    novel_repository = NovelRepository(session_factory)
    chapter_repository = ChapterRepository(session_factory)
    quality_repository = QualityRepository(session_factory)
    lore_repository = LoreRepository(session_factory)
    outline_repository = OutlineRepository(session_factory)
    reference_repository = ReferenceRepository(session_factory)
    app.state.novel_service = NovelService(novel_repository)
    app.state.chapter_service = ChapterService(chapter_repository)
    app.state.quality_service = QualityService(quality_repository, submitter=None)
    app.state.lore_service = LoreService(lore_repository)
    app.state.outline_service = OutlineService(outline_repository)
    app.state.reference_service = ReferenceService(reference_repository, submitter=None)


def _configure_rag_callback_auth(app: FastAPI, settings: Settings) -> None:
    """仅在 JWKS 与 Redis 都可用时装配索引回调验签器。"""

    redis = getattr(app.state, "auth_redis", None)
    if settings.agent_service_public_key_path is None or redis is None:
        return
    app.state.rag_callback_verifier = create_agent_callback_verifier(
        jwks_path=settings.agent_service_public_key_path,
        replay_store=RedisReplayStore(redis),
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
    _configure_business_services(app)
    _configure_rag_callback_auth(app, loaded_settings)
    app.add_middleware(SafeUnhandledExceptionMiddleware)
    app.add_middleware(RequestIdMiddleware)
    install_exception_handlers(app)
    install_service_auth_error_handler(app)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(novels_router, prefix="/api/v1")
    app.include_router(chapters_router, prefix="/api/v1")
    app.include_router(quality_router, prefix="/api/v1")
    app.include_router(lore_router, prefix="/api/v1")
    app.include_router(outlines_router, prefix="/api/v1")
    app.include_router(references_router, prefix="/api/v1")
    app.include_router(references_internal_router, include_in_schema=False)
    app.include_router(operations_router, prefix="/api/v1")
    return app
