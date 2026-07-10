from fastapi import FastAPI

from .config import Settings, create_testing_settings
from .errors import (
    PUBLIC_ERROR_RESPONSES,
    SafeUnhandledExceptionMiddleware,
    install_exception_handlers,
)
from .http import RequestIdMiddleware
from .operations import register_readiness_check
from .operations import router as operations_router


def create_app(*, testing: bool = False, settings: Settings | None = None) -> FastAPI:
    loaded_settings = settings
    if loaded_settings is None:
        loaded_settings = create_testing_settings() if testing else Settings()

    app = FastAPI(
        title="InkForge Core API",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        swagger_ui_oauth2_redirect_url="/api/v1/docs/oauth2-redirect",
        responses=PUBLIC_ERROR_RESPONSES,
    )
    app.state.settings = loaded_settings
    app.state.readiness_checks = {}
    register_readiness_check(app, "configuration", lambda: True)
    app.add_middleware(SafeUnhandledExceptionMiddleware)
    app.add_middleware(RequestIdMiddleware)
    install_exception_handlers(app)
    app.include_router(operations_router, prefix="/api/v1")
    return app
