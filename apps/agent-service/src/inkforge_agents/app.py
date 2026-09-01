from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Protocol, cast

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from inkforge_service_auth import RedisReplayStore

from .clients.core import CoreBillingGateway, CoreServiceClient
from .config import Settings, create_testing_settings
from .execution import load_execution_registry
from .execution.callbacks import ExecutionCallbackClient
from .execution.executor import StatelessExecutionStepExecutor
from .execution.journal import AsyncJournalRedis, RedisExecutionJournal
from .execution.replayer import TerminalCallbackReplayer
from .execution.router import router as execution_router
from .execution.service import ExecutionService
from .graph.parent_graph import ParentGraphDependencies, build_parent_graph
from .jobs.adapters import CoreArtifactPort, CoreGraphAgentExecutor, CoreToolGateway
from .jobs.portrait import ModelPortraitGenerator, PortraitJobHandler
from .jobs.quality import QualityJobHandler
from .jobs.rag import OpenAIEmbeddingProvider, RagJobHandler
from .jobs.short_medium import (
    ModelShortMediumGenerator,
    ShortMediumWritingJobHandler,
    WritingJobDispatcher,
)
from .jobs.video import ModelVideoScenePlanner, VideoPromptJobHandler
from .jobs.video_adaptation import (
    ModelVideoAdaptationPlanner,
    VideoAdaptationJobHandler,
)
from .jobs.video_dispatch import VideoJobDispatcher
from .jobs.writing import WritingJobHandler
from .observability import HumanWorkflowLog, WorkflowModelObserver
from .observability.router import router as debug_router
from .operations.definitions import validate_public_operation_definitions
from .operations.graph import OperationDependencies, build_operation_graph
from .providers.base import ModelProvider
from .providers.seedance import SeedanceProvider
from .providers.seedance_router import router as seedance_router
from .providers.selector import create_model_provider
from .queue.cancellation import RedisRunCancellation
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
from .supervision import CoroutineSupervisor
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
    execution_service: ExecutionService | None = None,
    execution_redis: AsyncJournalRedis | None = None,
) -> FastAPI:
    validate_public_operation_definitions()
    loaded_settings = settings or (create_testing_settings() if testing else Settings())
    execution_registry = load_execution_registry(environment=loaded_settings.environment)
    provider: ModelProvider | None = None
    provider_error: str | None = None
    try:
        provider = create_model_provider(loaded_settings)
    except ValueError as exc:
        provider_error = str(exc)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        consumer = cast(ConsumerPort | None, getattr(app.state, "queue_consumer", None))
        supervisor = (
            CoroutineSupervisor(
                name="queue_consumer",
                coroutine_factory=consumer.run,
                request_stop=consumer.request_stop,
            )
            if consumer is not None
            else None
        )
        if supervisor is not None:
            supervisor.start()
        v2_execution = cast(
            ExecutionService | None,
            getattr(app.state, "execution_service", None),
        )
        replayer = cast(
            TerminalCallbackReplayer | None,
            getattr(v2_execution, "callback_replayer", None),
        )
        replayer_supervisor = (
            CoroutineSupervisor(
                name="execution_callback_replayer",
                coroutine_factory=replayer.run,
                request_stop=replayer.request_stop,
            )
            if replayer is not None
            else None
        )
        if replayer_supervisor is not None:
            install_background_gate = getattr(
                v2_execution,
                "set_background_health_check",
                None,
            )
            if callable(install_background_gate):
                install_background_gate(replayer_supervisor.is_ready)
            replayer_supervisor.start()
        app.state.consumer_supervisor = supervisor
        app.state.consumer_task = supervisor.task if supervisor is not None else None
        app.state.execution_replayer_supervisor = replayer_supervisor
        app.state.execution_replayer_task = (
            replayer_supervisor.task if replayer_supervisor is not None else None
        )
        try:
            yield
        finally:
            if supervisor is not None:
                await supervisor.stop()
            if v2_execution is not None:
                await v2_execution.close()
            if replayer_supervisor is not None:
                await replayer_supervisor.stop()
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
            provider = cast(ModelProvider | None, getattr(app.state, "model_provider", None))
            provider_close = getattr(provider, "aclose", None)
            if provider_close is not None:
                await provider_close()
            redis = getattr(app.state, "redis", None)
            if redis is not None:
                await redis.aclose()
            execution_redis_client = getattr(app.state, "execution_redis", None)
            if execution_redis_client is not None and execution_redis_client is not redis:
                close_execution_redis = getattr(execution_redis_client, "aclose", None)
                if close_execution_redis is not None:
                    await close_execution_redis()

    app = FastAPI(
        title="InkForge 智能体服务",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = loaded_settings
    app.state.execution_registry = execution_registry
    app.state.workflow_log = workflow_log
    app.state.model_provider = provider
    app.state.seedance_provider = SeedanceProvider(
        api_key=loaded_settings.seedance_api_key,
        base_url=loaded_settings.seedance_base_url,
        enabled=loaded_settings.seedance_enabled,
    )
    app.state.model_runtime = (
        ModelRuntime(
            provider,
            max_concurrency=loaded_settings.agent_max_concurrency,
        )
        if provider is not None
        else None
    )
    app.state.model_provider_error = provider_error
    app.state.run_queue = run_queue
    app.state.core_request_verifier = core_request_verifier
    app.state.queue_consumer = queue_consumer
    app.state.consumer_supervisor = None
    app.state.consumer_task = None
    app.state.execution_replayer_supervisor = None
    app.state.execution_replayer_task = None
    app.state.embedding_provider = None
    app.state.runtime_error = None
    app.state.execution_service = execution_service
    app.state.execution_redis = execution_redis
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
        execution_health = None
        v2_execution = cast(
            ExecutionService | None,
            getattr(app.state, "execution_service", None),
        )
        if v2_execution is not None:
            execution_health = await v2_execution.health()
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
                    "queue_consumer": (
                        "ok"
                        if app.state.queue_consumer is not None
                        and getattr(app.state, "consumer_supervisor", None) is not None
                        and app.state.consumer_supervisor.is_ready()
                        and _consumer_is_healthy(app.state.queue_consumer)
                        else "failed"
                    ),
                }
            )
            if not testing or v2_execution is not None:
                checks["execution_journal"] = (
                    "ok" if execution_health is not None and execution_health.ready else "failed"
                )
            if not testing:
                ordinary_redis_ok = await _redis_is_reachable(
                    getattr(app.state, "redis", None)
                )
                checks.update(
                    {
                        "redis": "ok" if ordinary_redis_ok else "failed",
                        "execution_redis": (
                            "ok"
                            if execution_health is not None
                            and execution_health.journal_connected
                            else "failed"
                        ),
                        "execution_journal_persistence": (
                            "ok"
                            if execution_health is not None
                            and execution_health.journal_persistence_ok
                            and not execution_health.journal_quarantined
                            else "failed"
                        ),
                    }
                )
            replayer_supervisor = cast(
                CoroutineSupervisor | None,
                getattr(app.state, "execution_replayer_supervisor", None),
            )
            if not testing or replayer_supervisor is not None:
                checks["execution_callback_replayer"] = (
                    "ok"
                    if replayer_supervisor is not None and replayer_supervisor.is_ready()
                    else "failed"
                )
            if loaded_settings.rag_index_enabled:
                checks["rag_indexer"] = (
                    "ok" if app.state.embedding_provider is not None else "failed"
                )
        ready = all(value == "ok" for value in checks.values())
        content: dict[str, object] = {
            "status": "ready" if ready else "not_ready",
            "checks": checks,
            # 只暴露 canonical manifest 摘要，不暴露合同路径、Profile 内容或供应商凭据。
            "executionManifestFingerprint": execution_registry.manifest_fingerprint,
        }
        if checks.get("queue_consumer") == "failed":
            supervisor = cast(
                CoroutineSupervisor | None,
                getattr(app.state, "consumer_supervisor", None),
            )
            content["backgroundTasks"] = {
                "queue_consumer": (
                    supervisor.error_code
                    if supervisor is not None
                    else "BACKGROUND_TASK_NOT_REGISTERED"
                )
                or _consumer_health_error_code(app.state.queue_consumer)
                or "BACKGROUND_TASK_NOT_RUNNING"
            }
        if checks.get("execution_callback_replayer") == "failed":
            replayer_supervisor = cast(
                CoroutineSupervisor | None,
                getattr(app.state, "execution_replayer_supervisor", None),
            )
            background_tasks = cast(
                dict[str, object],
                content.setdefault("backgroundTasks", {}),
            )
            background_tasks["execution_callback_replayer"] = (
                replayer_supervisor.error_code
                if replayer_supervisor is not None
                else "BACKGROUND_TASK_NOT_REGISTERED"
            )
        if execution_health is not None:
            content["executionCallbacks"] = {
                "pending": execution_health.callback_pending,
                "rejected": execution_health.callback_rejected,
                "errorCode": execution_health.error_code,
            }
            content["executionAdmission"] = {
                "active": execution_health.admission_active,
                "capacity": execution_health.admission_capacity,
                "saturated": execution_health.admission_saturated,
            }
            content["executionJournal"] = {
                "connected": execution_health.journal_connected,
                "persistenceOk": execution_health.journal_persistence_ok,
                "restoreQuarantined": execution_health.journal_quarantined,
                "usedMemoryBytes": execution_health.journal_used_memory_bytes,
                "maxmemoryBytes": execution_health.journal_maxmemory_bytes,
                "evictedKeys": execution_health.journal_evicted_keys,
            }
        return JSONResponse(
            status_code=200 if ready else 503,
            content=content,
        )

    install_service_auth_error_handler(app)
    app.include_router(execution_router)
    app.include_router(runs_router)
    app.include_router(seedance_router)
    app.include_router(debug_router)
    return app


def _configure_runtime(app: FastAPI, settings: Settings) -> None:
    try:
        settings.validate_execution_redis_configuration()
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
                max_connections=8,
                socket_connect_timeout=2.0,
                socket_timeout=5.0,
            )
            app.state.redis = redis
        execution_redis = getattr(app.state, "execution_redis", None)
        if execution_redis is None and settings.execution_redis_url is not None:
            from redis.asyncio import Redis

            execution_redis = Redis.from_url(
                settings.execution_redis_url.get_secret_value(),
                decode_responses=False,
                max_connections=4,
                socket_connect_timeout=2.0,
                socket_timeout=5.0,
            )
            app.state.execution_redis = execution_redis
        if app.state.run_queue is None and redis is not None:
            app.state.run_queue = RedisRunQueue(
                redis,
                terminal_retention=timedelta(days=settings.queue_terminal_retention_days),
            )
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
                embedding_provider: OpenAIEmbeddingProvider | None = None
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
                    embedding_provider = OpenAIEmbeddingProvider(
                        embedding_http,
                        model=settings.rag_embedding_model,
                    )
                app.state.embedding_provider = embedding_provider
                model_runtime = ModelRuntime(
                    provider,
                    billing=CoreBillingGateway(core),
                    observer=WorkflowModelObserver(workflow_log),
                    max_concurrency=settings.agent_max_concurrency,
                )
                gateway = CoreToolGateway(core, embedding_provider)
                registry = build_default_registry(gateway)
                cancellation = RedisRunCancellation(queue)
                runner = AgentRunner(
                    AgentRuntime(
                        model_runtime,
                        registry,
                        max_output_tokens=settings.model_max_output_tokens,
                        cancellation=cancellation,
                    ),
                    registry,
                )
                artifacts = CoreArtifactPort(core)
                dependencies = OperationDependencies(
                    agentExecutor=CoreGraphAgentExecutor(runner, artifacts),
                    artifacts=artifacts,
                    cancellation=cancellation,
                )
                long_serial_writing = WritingJobHandler(
                    core,
                    parent_graph=build_parent_graph(
                        ParentGraphDependencies(operation=dependencies)
                    ),
                    operation_graph=build_operation_graph(dependencies),
                    artifacts=artifacts,
                    workflow_log=workflow_log,
                    cancellation=cancellation,
                )
                short_medium_writing = ShortMediumWritingJobHandler(
                    core,
                    ModelShortMediumGenerator(
                        model_runtime,
                        max_output_tokens=settings.model_max_output_tokens,
                    ),
                    workflow_log=workflow_log,
                )
                writing = WritingJobDispatcher(
                    long_serial_writing,
                    short_medium_writing,
                )
                app.state.model_runtime = model_runtime
                handlers: dict[JobKind, JobHandler] = {"writing": writing}
                handlers["portrait"] = PortraitJobHandler(
                    core,
                    ModelPortraitGenerator(
                        model_runtime,
                        max_output_tokens=settings.model_max_output_tokens,
                    ),
                    workflow_log=workflow_log,
                )
                handlers["quality"] = QualityJobHandler(
                    core,
                    runner,
                    workflow_log=workflow_log,
                )
                # 视频规划与写作共用模型并发门和计费授权，但使用独立任务语义。
                handlers["video"] = VideoJobDispatcher(
                    VideoPromptJobHandler(
                        core,
                        ModelVideoScenePlanner(
                            model_runtime,
                            max_output_tokens=settings.model_max_output_tokens,
                        ),
                        workflow_log=workflow_log,
                    ),
                    VideoAdaptationJobHandler(
                        core,
                        ModelVideoAdaptationPlanner(
                            model_runtime,
                            max_output_tokens=settings.model_max_output_tokens,
                        ),
                        workflow_log=workflow_log,
                    ),
                )
                if settings.rag_index_enabled and embedding_provider is not None:
                    handlers["rag"] = RagJobHandler(core, embedding_provider)
                app.state.queue_consumer = QueueConsumer(
                    queue,
                    handlers,
                    max_concurrency=settings.agent_max_concurrency,
                )
            if (
                app.state.execution_service is None
                and execution_redis is not None
                and provider is not None
            ):
                model_runtime = cast(ModelRuntime, app.state.model_runtime)
                journal = RedisExecutionJournal(
                    cast(AsyncJournalRedis, execution_redis),
                    retention=timedelta(
                        hours=settings.execution_terminal_retention_hours
                    ),
                    require_durability=settings.environment == "production",
                )
                app.state.execution_service = ExecutionService(
                    journal=journal,
                    registry=app.state.execution_registry,
                    executor=StatelessExecutionStepExecutor(
                        model_runtime,
                        max_output_tokens=settings.model_max_output_tokens,
                    ),
                    callbacks=ExecutionCallbackClient(core_http, signer),
                    max_active_executions=settings.agent_max_concurrency,
                )
    except (OSError, ValueError) as exc:
        app.state.runtime_error = str(exc)


def _consumer_is_healthy(consumer: object) -> bool:
    check = getattr(consumer, "is_healthy", None)
    return bool(check()) if callable(check) else True


def _consumer_health_error_code(consumer: object) -> str | None:
    error_code = getattr(consumer, "health_error_code", None)
    return error_code if isinstance(error_code, str) and error_code else None


async def _redis_is_reachable(redis: object | None) -> bool:
    if redis is None:
        return False
    ping = getattr(redis, "ping", None)
    if not callable(ping):
        return False
    try:
        return bool(await ping())
    except Exception:
        return False
