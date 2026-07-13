from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

import httpx
from fastapi import FastAPI
from inkforge_service_auth import RedisReplayStore
from sqlalchemy.ext.asyncio import AsyncEngine

from .agent_client import (
    AgentClient,
    PortraitAgentSubmitter,
    QualityAgentSubmitter,
    RagAgentSubmitter,
    WritingTaskAgentSubmitter,
)
from .auth import router as auth_router
from .auth.readiness import RedisReadiness
from .auth.repository import AuthRepository
from .auth.service import AuthService, RedisRateLimiter
from .billing.grants import ModelGrantCodec
from .billing.repository import BillingRepository
from .billing.router import internal_router as billing_internal_router
from .billing.router import router as billing_router
from .billing.service import BillingService
from .chapters.repository import ChapterRepository
from .chapters.router import router as chapters_router
from .chapters.service import ChapterService
from .config import OLD_DEFAULT_JWT_SECRET, Settings, create_testing_settings
from .db.session import DatabaseReadiness, configure_database
from .debug import router as debug_router
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
from .quality.internal_router import router as quality_internal_router
from .quality.repository import QualityRepository
from .quality.router import router as quality_router
from .quality.service import QualityService
from .references.internal_router import router as references_internal_router
from .references.repository import ReferenceRepository
from .references.router import router as references_router
from .references.service import ReferenceService
from .reviews.apply import FormalArtifactApplier
from .reviews.formal_writes import FormalWriteRepository
from .reviews.internal_router import router as reviews_internal_router
from .reviews.repository import ReviewRepository
from .reviews.router import router as reviews_router
from .reviews.service import ReviewService
from .reviews.updates import AgentUpdatesExecutor
from .service_auth import (
    create_agent_callback_verifier,
    create_core_request_signer,
    install_service_auth_error_handler,
)
from .styles.internal_router import router as styles_internal_router
from .styles.repository import StyleRepository
from .styles.router import router as styles_router
from .styles.service import StyleService
from .styles.storage import StyleStorage
from .writing.callbacks import router as writing_callback_router
from .writing.context import WritingContextRepository, WritingContextService
from .writing.read_tool_service import WritingReadToolService
from .writing.read_tools import ALL_AGENT_IDS, register_read_tools
from .writing.reconciler import WritingRunReconciler
from .writing.repository import WritingRepository
from .writing.router import router as writing_router
from .writing.service import WritingService
from .writing.sse import InMemoryWritingEventStore, RedisWritingEventStore
from .writing.tasks import (
    WritingCallbackService,
    WritingTaskRepository,
    WritingTaskService,
)
from .writing.tool_gateway import ToolGateway, ToolRequest
from .writing.tool_gateway import internal_router as tool_internal_router


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


def _configure_business_services(app: FastAPI, settings: Settings) -> None:
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
    style_repository = StyleRepository(session_factory)
    billing_repository = BillingRepository(session_factory)
    writing_repository = WritingRepository(session_factory)
    review_repository = ReviewRepository(session_factory)
    context_repository = WritingContextRepository(session_factory)
    writing_task_repository = WritingTaskRepository(session_factory)
    app.state.novel_service = NovelService(novel_repository)
    app.state.chapter_service = ChapterService(chapter_repository)
    agent_client = cast(AgentClient | None, getattr(app.state, "agent_client", None))
    app.state.quality_service = QualityService(
        quality_repository,
        submitter=QualityAgentSubmitter(agent_client) if agent_client else None,
    )
    app.state.lore_service = LoreService(lore_repository)
    app.state.outline_service = OutlineService(outline_repository)
    reference_service = ReferenceService(
        reference_repository,
        submitter=RagAgentSubmitter(agent_client) if agent_client else None,
    )
    app.state.reference_service = reference_service
    app.state.style_service = StyleService(
        style_repository,
        StyleStorage(app.state.settings.uploads_root),
        submitter=PortraitAgentSubmitter(agent_client) if agent_client else None,
    )
    grant_codec = (
        ModelGrantCodec.from_private_key_path(settings.core_service_private_key_path)
        if settings.core_service_private_key_path is not None
        else None
    )
    app.state.billing_service = BillingService(billing_repository, grant_codec)
    app.state.writing_service = WritingService(writing_repository)
    updates_executor = AgentUpdatesExecutor(
        lore_repository,
        outline_repository,
        reference_repository,
    )
    artifact_applier = FormalArtifactApplier(
        FormalWriteRepository(session_factory),
        updates_executor,
    )
    app.state.review_repository = review_repository
    app.state.review_service = ReviewService(review_repository, artifact_applier)
    context_service = WritingContextService(context_repository, novel_repository)
    app.state.writing_context_service = context_service
    tool_gateway = ToolGateway(context_repository)

    async def get_writing_context(request: ToolRequest) -> dict[str, object]:
        return await context_service.build(request.user_id, request.task_id)

    read_tool_service = WritingReadToolService(
        context_service,
        outline_repository,
        review_repository,
        reference_service,
    )
    app.state.writing_read_tool_service = read_tool_service
    tool_gateway.register("get_writing_context", ALL_AGENT_IDS, True, get_writing_context)
    register_read_tools(tool_gateway, read_tool_service)
    app.state.tool_gateway = tool_gateway
    redis = getattr(app.state, "auth_redis", None)
    event_store = (
        RedisWritingEventStore(redis) if redis is not None else InMemoryWritingEventStore()
    )
    app.state.writing_event_store = event_store
    app.state.writing_task_repository = writing_task_repository
    writing_submitter = WritingTaskAgentSubmitter(agent_client) if agent_client else None
    app.state.writing_task_service = WritingTaskService(
        writing_task_repository,
        submitter=writing_submitter,
    )
    if writing_submitter is not None and getattr(app.state, "writing_reconciler", None) is None:
        app.state.writing_reconciler = WritingRunReconciler(
            writing_task_repository,
            writing_submitter,
            batch_size=20,
            interval_seconds=30,
        )
    app.state.writing_callback_service = WritingCallbackService(
        writing_task_repository, event_store
    )


def _configure_rag_callback_auth(app: FastAPI, settings: Settings) -> None:
    """仅在 JWKS 与 Redis 都可用时装配索引回调验签器。"""

    redis = getattr(app.state, "auth_redis", None)
    if settings.agent_service_public_key_path is None or redis is None:
        return
    app.state.rag_callback_verifier = create_agent_callback_verifier(
        jwks_path=settings.agent_service_public_key_path,
        replay_store=RedisReplayStore(redis),
    )


def _configure_agent_client(app: FastAPI, settings: Settings) -> None:
    if settings.core_service_private_key_path is None or settings.agent_service_url is None:
        return
    signer = create_core_request_signer(
        private_key_path=settings.core_service_private_key_path,
        kid=settings.core_service_key_id,
    )
    http = httpx.AsyncClient(
        base_url=settings.agent_service_url,
        timeout=httpx.Timeout(10, connect=2),
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
    )
    app.state.agent_http = http
    app.state.agent_client = AgentClient(http, signer)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """在应用退出时释放已创建的数据库连接池。"""

    reconciler = getattr(app.state, "writing_reconciler", None)
    reconciler_task = asyncio.create_task(reconciler.run()) if reconciler is not None else None
    try:
        readiness = cast(
            DatabaseReadiness | None,
            getattr(app.state, "database_readiness", None),
        )
        if readiness is not None:
            await readiness.warm_up()
        yield
    finally:
        if reconciler is not None:
            reconciler.request_stop()
        if reconciler_task is not None:
            await asyncio.gather(reconciler_task, return_exceptions=True)
        auth_redis = getattr(app.state, "auth_redis", None)
        try:
            if auth_redis is not None:
                await auth_redis.aclose()
        finally:
            agent_http = cast(
                httpx.AsyncClient | None,
                getattr(app.state, "agent_http", None),
            )
            try:
                if agent_http is not None:
                    await agent_http.aclose()
            finally:
                engine = cast(
                    AsyncEngine | None,
                    getattr(app.state, "database_engine", None),
                )
                if engine is not None:
                    await engine.dispose()


def create_app(
    *,
    testing: bool = False,
    settings: Settings | None = None,
    writing_reconciler: object | None = None,
) -> FastAPI:
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
    app.state.writing_reconciler = writing_reconciler
    app.state.readiness_checks = {}
    register_readiness_check(app, "configuration", lambda: True)
    configure_database(app, loaded_settings)
    _configure_auth(app, loaded_settings)
    _configure_agent_client(app, loaded_settings)
    _configure_business_services(app, loaded_settings)
    _configure_rag_callback_auth(app, loaded_settings)
    app.add_middleware(SafeUnhandledExceptionMiddleware)
    app.add_middleware(RequestIdMiddleware)
    install_exception_handlers(app)
    install_service_auth_error_handler(app)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(novels_router, prefix="/api/v1")
    app.include_router(chapters_router, prefix="/api/v1")
    app.include_router(quality_router, prefix="/api/v1")
    app.include_router(quality_internal_router, include_in_schema=False)
    app.include_router(lore_router, prefix="/api/v1")
    app.include_router(outlines_router, prefix="/api/v1")
    app.include_router(references_router, prefix="/api/v1")
    app.include_router(styles_router, prefix="/api/v1")
    app.include_router(billing_router, prefix="/api/v1")
    app.include_router(writing_router, prefix="/api/v1")
    app.include_router(reviews_router, prefix="/api/v1")
    app.include_router(debug_router, prefix="/api/v1")
    app.include_router(references_internal_router, include_in_schema=False)
    app.include_router(styles_internal_router, include_in_schema=False)
    app.include_router(billing_internal_router, include_in_schema=False)
    app.include_router(tool_internal_router, include_in_schema=False)
    app.include_router(writing_callback_router, include_in_schema=False)
    app.include_router(reviews_internal_router, include_in_schema=False)
    app.include_router(operations_router, prefix="/api/v1")
    return app
