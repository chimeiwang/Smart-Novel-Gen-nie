from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from .config import Settings, create_testing_settings
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
    app.add_middleware(SafeUnhandledExceptionMiddleware)
    app.add_middleware(RequestIdMiddleware)
    install_exception_handlers(app)
    install_service_auth_error_handler(app)
    app.include_router(operations_router, prefix="/api/v1")
    return app
