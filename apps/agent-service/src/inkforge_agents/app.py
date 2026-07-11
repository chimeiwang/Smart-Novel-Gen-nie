from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol, cast

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from inkforge_service_auth import RedisReplayStore

from .clients.core import CoreBillingGateway, CoreServiceClient
from .config import Settings, create_testing_settings
from .graph.parent_graph import ParentGraphDependencies, build_parent_graph
from .jobs.adapters import CoreArtifactPort, CoreGraphAgentExecutor, CoreToolGateway
from .jobs.portrait import ModelPortraitGenerator, PortraitJobHandler
from .jobs.quality import QualityJobHandler
from .jobs.rag import OpenAIEmbeddingProvider, RagJobHandler
from .jobs.writing import WritingJobHandler
from .observability import HumanWorkflowLog, WorkflowModelObserver
from .observability.router import router as debug_router
from .operations.graph import OperationDependencies, build_operation_graph
from .providers.base import ModelProvider
from .providers.selector import create_model_provider
from .queue.consumer import JobHandler, QueueConsumer
from .queue.repository import JobKind, RedisRunQueue
from .runs.router import CoreRequestVerifier
from .runs.router import router as runs_router
from .runtime.agent_runner import AgentRunner
from .runtime.agent_runtime import AgentRuntime
from .runtime.model_runtime import ModelRuntime
from .service_auth import (
    create_agent_callback_signer,
    create_core_request_verifier,
    install_service_auth_error_handler,
)
from .tools.registry import build_default_registry


class ConsumerPort(Protocol):
    async def run(self) -> None: ...

    def request_stop(self) -> None: ...


def create_app(
    *,
    testing: bool = False,
    settings: Settings | None = None,
    run_queue: RedisRunQueue | None = None,
    core_request_verifier: CoreRequestVerifier | None = None,
    queue_consumer: ConsumerPort | None = None,
    workflow_log: HumanWorkflowLog | None = None,
) -> FastAPI:
    loaded_settings = settings or (create_testing_settings() if testing else Settings())
    provider: ModelProvider | None = None
    provider_error: str | None = None
    try:
        provider = create_model_provider(loaded_settings)
    except ValueError as exc:
        provider_error = str(exc)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        consumer = cast(ConsumerPort | None, getattr(app.state, "queue_consumer", None))
        task = asyncio.create_task(consumer.run()) if consumer is not None else None
        app.state.consumer_task = task
        try:
            yield
        finally:
            if consumer is not None:
                consumer.request_stop()
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)
            core_http = cast(
                httpx.AsyncClient | None,
                getattr(app.state, "core_http", None),
            )
            if core_http is not None:
                await core_http.aclose()
            embedding_http = cast(
                httpx.AsyncClient | None,
                getattr(app.state, "embedding_http", None),
            )
            if embedding_http is not None:
                await embedding_http.aclose()
            redis = getattr(app.state, "redis", None)
            if redis is not None:
                await redis.aclose()

    app = FastAPI(
        title="InkForge 智能体服务",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = loaded_settings
    app.state.workflow_log = workflow_log
    app.state.model_provider = provider
    app.state.model_runtime = ModelRuntime(provider) if provider is not None else None
    app.state.model_provider_error = provider_error
    app.state.run_queue = run_queue
    app.state.core_request_verifier = core_request_verifier
    app.state.queue_consumer = queue_consumer
    app.state.runtime_error = None
    if not testing:
        _configure_runtime(app, loaded_settings)

    @app.get("/internal/v1/health/live", include_in_schema=False)
    async def liveness() -> dict[str, str]:
        return {"status": "ok", "service": "agent-service"}

    @app.get("/internal/v1/health/ready", include_in_schema=False)
    async def readiness() -> JSONResponse:
        checks = {
            "model_provider": "ok" if app.state.model_provider is not None else "failed",
        }
        if loaded_settings.environment == "production":
            checks.update(
                {
                    "run_queue": "ok" if app.state.run_queue is not None else "failed",
                    "service_auth": (
                        "ok" if app.state.core_request_verifier is not None else "failed"
                    ),
                    "core_client": (
                        "ok" if getattr(app.state, "core_client", None) is not None else "failed"
                    ),
                    "queue_consumer": ("ok" if app.state.queue_consumer is not None else "failed"),
                }
            )
        ready = all(value == "ok" for value in checks.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ready" if ready else "not_ready",
                "checks": checks,
            },
        )

    install_service_auth_error_handler(app)
    app.include_router(runs_router)
    app.include_router(debug_router)
    return app


def _configure_runtime(app: FastAPI, settings: Settings) -> None:
    try:
        workflow_log = cast(HumanWorkflowLog | None, app.state.workflow_log)
        if workflow_log is None:
            workflow_log = HumanWorkflowLog(settings.workflow_human_log_dir)
            app.state.workflow_log = workflow_log
        redis = getattr(app.state, "redis", None)
        if redis is None and settings.redis_url is not None:
            from redis.asyncio import Redis

            redis = Redis.from_url(
                settings.redis_url.get_secret_value(),
                decode_responses=False,
                max_connections=4,
                socket_connect_timeout=2.0,
                socket_timeout=5.0,
            )
            app.state.redis = redis
        if app.state.run_queue is None and redis is not None:
            app.state.run_queue = RedisRunQueue(redis)
        if (
            app.state.core_request_verifier is None
            and redis is not None
            and settings.core_service_public_key_path is not None
        ):
            app.state.core_request_verifier = create_core_request_verifier(
                jwks_path=settings.core_service_public_key_path,
                replay_store=RedisReplayStore(redis),
            )
        if settings.agent_service_private_key_path is not None:
            signer = create_agent_callback_signer(
                private_key_path=settings.agent_service_private_key_path,
                kid=settings.agent_service_key_id,
            )
            core_http = httpx.AsyncClient(
                base_url=settings.core_api_url,
                timeout=httpx.Timeout(15, connect=2),
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
            )
            core = CoreServiceClient(core_http, signer)
            app.state.core_http = core_http
            app.state.core_client = core
            provider = cast(ModelProvider | None, app.state.model_provider)
            queue = cast(RedisRunQueue | None, app.state.run_queue)
            if provider is not None and queue is not None and app.state.queue_consumer is None:
                model_runtime = ModelRuntime(
                    provider,
                    billing=CoreBillingGateway(core),
                    observer=WorkflowModelObserver(workflow_log),
                )
                gateway = CoreToolGateway(core)
                registry = build_default_registry(gateway)
                runner = AgentRunner(AgentRuntime(model_runtime, registry), registry)
                artifacts = CoreArtifactPort(core)
                dependencies = OperationDependencies(
                    agentExecutor=CoreGraphAgentExecutor(runner, artifacts),
                    artifacts=artifacts,
                )
                writing = WritingJobHandler(
                    core,
                    parent_graph=build_parent_graph(
                        ParentGraphDependencies(operation=dependencies)
                    ),
                    operation_graph=build_operation_graph(dependencies),
                    workflow_log=workflow_log,
                )
                app.state.model_runtime = model_runtime
                handlers: dict[JobKind, JobHandler] = {"writing": writing}
                handlers["portrait"] = PortraitJobHandler(
                    core,
                    ModelPortraitGenerator(model_runtime),
                )
                handlers["quality"] = QualityJobHandler(core, runner)
                if (
                    settings.rag_embedding_api_key is not None
                    and settings.rag_embedding_base_url
                    and settings.rag_embedding_model
                ):
                    embedding_base = settings.rag_embedding_base_url.rstrip("/")
                    if not embedding_base.endswith("/v1"):
                        embedding_base += "/v1"
                    embedding_http = httpx.AsyncClient(
                        base_url=embedding_base,
                        headers={
                            "Authorization": "Bearer "
                            + settings.rag_embedding_api_key.get_secret_value()
                        },
                        timeout=httpx.Timeout(30, connect=3),
                        limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
                    )
                    app.state.embedding_http = embedding_http
                    handlers["rag"] = RagJobHandler(
                        core,
                        OpenAIEmbeddingProvider(
                            embedding_http,
                            model=settings.rag_embedding_model,
                        ),
                    )
                app.state.queue_consumer = QueueConsumer(queue, handlers)
    except (OSError, ValueError) as exc:
        app.state.runtime_error = str(exc)
