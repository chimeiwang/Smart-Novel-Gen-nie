from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import Settings, create_testing_settings
from .providers.base import ModelProvider
from .providers.selector import create_model_provider
from .runtime.model_runtime import ModelRuntime


def create_app(*, testing: bool = False, settings: Settings | None = None) -> FastAPI:
    loaded_settings = settings or (create_testing_settings() if testing else Settings())
    provider: ModelProvider | None = None
    provider_error: str | None = None
    try:
        provider = create_model_provider(loaded_settings)
    except ValueError as exc:
        provider_error = str(exc)

    app = FastAPI(
        title="InkForge 智能体服务",
        version="0.1.0",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = loaded_settings
    app.state.model_provider = provider
    app.state.model_runtime = ModelRuntime(provider) if provider is not None else None
    app.state.model_provider_error = provider_error

    @app.get("/internal/v1/health/live", include_in_schema=False)
    async def liveness() -> dict[str, str]:
        return {"status": "ok", "service": "agent-service"}

    @app.get("/internal/v1/health/ready", include_in_schema=False)
    async def readiness() -> JSONResponse:
        ready = app.state.model_provider is not None
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ready" if ready else "not_ready",
                "checks": {"model_provider": "ok" if ready else "failed"},
            },
        )

    return app
