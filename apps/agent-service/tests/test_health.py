import asyncio
from datetime import timedelta
from pathlib import Path

import inkforge_agents.app as app_module
import pytest
from fastapi.testclient import TestClient
from inkforge_agents.app import create_app
from inkforge_agents.config import Settings
from inkforge_agents.queue.consumer import QueueConsumer
from inkforge_agents.supervision import CoroutineSupervisor
from redis.exceptions import ResponseError


class Consumer:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def run(self) -> None:
        self.started = True
        while not self.stopped:
            import asyncio

            await asyncio.sleep(0.001)

    def request_stop(self) -> None:
        self.stopped = True


def test_liveness_is_independent_of_model_credentials() -> None:
    settings = Settings.model_validate(
        {
            "environment": "production",
            "model_provider": "openai_compatible",
            "openai_api_key": None,
            "openai_base_url": "https://api.deepseek.com/v1",
            "openai_model": "deepseek-v4-flash",
        }
    )
    client = TestClient(create_app(settings=settings))

    assert client.get("/internal/v1/health/live").json() == {
        "status": "ok",
        "service": "agent-service",
    }
    response = client.get("/internal/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["model_provider"] == "failed"


def test_testing_app_is_ready_with_explicit_fake_provider() -> None:
    response = TestClient(create_app(testing=True)).get("/internal/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert "backgroundTasks" not in response.json()


def test_agent_settings_never_accept_database_as_a_service_field() -> None:
    assert "database_url" not in Settings.model_fields


def test_app_lifespan_starts_and_stops_single_queue_consumer() -> None:
    consumer = Consumer()
    app = create_app(testing=True, queue_consumer=consumer)

    with TestClient(app) as client:
        assert client.get("/internal/v1/health/live").status_code == 200
        assert consumer.started is True

    assert consumer.stopped is True


def test_readiness_fails_when_queue_consumer_task_exits_unexpectedly() -> None:
    class CrashedConsumer:
        async def run(self) -> None:
            raise RuntimeError("模拟消费者意外退出")

        def request_stop(self) -> None:
            pass

    settings = Settings.model_validate(
        {
            "environment": "production",
            "model_provider": "fake",
        }
    )
    app = create_app(
        testing=True,
        settings=settings,
        run_queue=object(),  # type: ignore[arg-type]
        core_request_verifier=object(),  # type: ignore[arg-type]
        queue_consumer=CrashedConsumer(),
    )
    app.state.core_client = object()

    with TestClient(app) as client:
        import time

        deadline = time.monotonic() + 1
        while (
            app.state.consumer_supervisor.error_code
            != "BACKGROUND_TASK_BACKOFF"
            and time.monotonic() < deadline
        ):
            time.sleep(0.001)
        response = client.get("/internal/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["queue_consumer"] == "failed"
    assert response.json()["backgroundTasks"] == {
        "queue_consumer": "BACKGROUND_TASK_BACKOFF"
    }


def test_readiness_fails_after_queue_redis_oom() -> None:
    class OomQueue:
        terminal_retention = timedelta(days=7)

        async def purge_terminal(self, *args, **kwargs):
            del args, kwargs
            raise ResponseError("OOM command not allowed when used memory > maxmemory")

    settings = Settings.model_validate(
        {
            "environment": "production",
            "model_provider": "fake",
        }
    )
    consumer = QueueConsumer(OomQueue(), {})  # type: ignore[arg-type]
    app = create_app(
        testing=True,
        settings=settings,
        run_queue=object(),  # type: ignore[arg-type]
        core_request_verifier=object(),  # type: ignore[arg-type]
        queue_consumer=consumer,
    )
    app.state.core_client = object()

    with TestClient(app) as client:
        import time

        deadline = time.monotonic() + 1
        while (
            app.state.consumer_supervisor.error_code
            != "BACKGROUND_TASK_BACKOFF"
            and time.monotonic() < deadline
        ):
            time.sleep(0.001)
        response = client.get("/internal/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["queue_consumer"] == "failed"
    assert response.json()["backgroundTasks"] == {
        "queue_consumer": "BACKGROUND_TASK_BACKOFF"
    }


def test_readiness_recovers_after_queue_consumer_restarts() -> None:
    class FlakyConsumer:
        def __init__(self) -> None:
            self.starts = 0
            self.stopped = False
            self.stop_event = asyncio.Event()

        async def run(self) -> None:
            self.starts += 1
            if self.starts == 1:
                raise RuntimeError("模拟首次崩溃")
            await self.stop_event.wait()

        def request_stop(self) -> None:
            self.stopped = True
            self.stop_event.set()

    import time

    settings = Settings.model_validate(
        {
            "environment": "production",
            "model_provider": "fake",
        }
    )
    consumer = FlakyConsumer()
    app = create_app(
        testing=True,
        settings=settings,
        run_queue=object(),  # type: ignore[arg-type]
        core_request_verifier=object(),  # type: ignore[arg-type]
        queue_consumer=consumer,
    )
    app.state.core_client = object()

    with TestClient(app) as client:
        deadline = time.monotonic() + 2
        while consumer.starts < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        response = client.get("/internal/v1/health/ready")

    assert consumer.starts == 2
    assert response.status_code == 200
    assert response.json()["checks"]["queue_consumer"] == "ok"


@pytest.mark.asyncio
async def test_consumer_supervisor_restarts_without_parallel_instances() -> None:
    starts = 0
    active = 0
    maximum_active = 0
    restarted = asyncio.Event()
    stopped = asyncio.Event()

    async def run() -> None:
        nonlocal starts, active, maximum_active
        starts += 1
        active += 1
        maximum_active = max(maximum_active, active)
        try:
            if starts == 1:
                raise RuntimeError("模拟首次崩溃")
            restarted.set()
            await stopped.wait()
        finally:
            active -= 1

    supervisor = CoroutineSupervisor(
        name="queue_consumer",
        coroutine_factory=run,
        request_stop=stopped.set,
        backoff_base=0.001,
        backoff_max=0.002,
        stability_window=0.01,
    )
    supervisor.start()

    await asyncio.wait_for(restarted.wait(), timeout=1)

    assert starts == 2
    assert maximum_active == 1
    assert supervisor.is_ready() is True
    await supervisor.stop()


@pytest.mark.asyncio
async def test_consumer_supervisor_shutdown_does_not_restart() -> None:
    started = asyncio.Event()
    stopped = asyncio.Event()
    starts = 0

    async def run() -> None:
        nonlocal starts
        starts += 1
        started.set()
        await stopped.wait()

    supervisor = CoroutineSupervisor(
        name="queue_consumer",
        coroutine_factory=run,
        request_stop=stopped.set,
        backoff_base=0.001,
        backoff_max=0.002,
        stability_window=0.01,
    )
    supervisor.start()
    await started.wait()

    await supervisor.stop()
    await asyncio.sleep(0.01)

    assert starts == 1
    assert supervisor.is_ready() is False


@pytest.mark.asyncio
async def test_consumer_supervisor_recovers_after_stability_window() -> None:
    starts = 0
    restarted = asyncio.Event()
    stopped = asyncio.Event()

    async def run() -> None:
        nonlocal starts
        starts += 1
        if starts == 1:
            raise RuntimeError("模拟首次崩溃")
        restarted.set()
        await stopped.wait()

    supervisor = CoroutineSupervisor(
        name="queue_consumer",
        coroutine_factory=run,
        request_stop=stopped.set,
        backoff_base=0.001,
        backoff_max=0.002,
        stability_window=0.02,
        unhealthy_failure_threshold=1,
    )
    supervisor.start()
    try:
        await asyncio.wait_for(restarted.wait(), timeout=1)

        assert supervisor.is_ready() is False
        await asyncio.sleep(0.03)
        assert supervisor.is_ready() is True
    finally:
        await supervisor.stop()


def test_readiness_fails_when_rag_is_enabled_without_embedding_provider() -> None:
    settings = Settings.model_validate(
        {
            "environment": "production",
            "model_provider": "fake",
            "rag_index_enabled": True,
        }
    )
    consumer = Consumer()
    app = create_app(
        testing=True,
        settings=settings,
        run_queue=object(),  # type: ignore[arg-type]
        core_request_verifier=object(),  # type: ignore[arg-type]
        queue_consumer=consumer,
    )
    app.state.core_client = object()

    with TestClient(app) as client:
        response = client.get("/internal/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["rag_indexer"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(("rag_enabled", "handler_expected"), [(False, False), (True, True)])
async def test_rag_handler_requires_agent_side_feature_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rag_enabled: bool,
    handler_expected: bool,
) -> None:
    monkeypatch.setattr(
        app_module,
        "create_agent_callback_signer",
        lambda **_kwargs: object(),
    )
    settings = Settings.model_validate(
        {
            "environment": "test",
            "model_provider": "fake",
            "agent_service_private_key_path": "unused.pem",
            "workflow_human_log_dir": str(tmp_path),
            "rag_embedding_api_key": "test-key",
            "rag_embedding_base_url": "https://embedding.example/v1",
            "rag_embedding_model": "test-embedding",
            "rag_index_enabled": rag_enabled,
        }
    )
    app = create_app(settings=settings, run_queue=object())  # type: ignore[arg-type]

    try:
        assert app.state.embedding_provider is not None
        assert ("rag" in app.state.queue_consumer._handlers) is handler_expected
    finally:
        await app.state.core_http.aclose()
        await app.state.embedding_http.aclose()


@pytest.mark.asyncio
async def test_应用装配向模型运行时传入相同输出预算(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, int] = {}

    class CapturingAgentRuntime:
        def __init__(
            self,
            model_runtime: object,
            registry: object,
            *,
            max_output_tokens: int,
        ) -> None:
            del model_runtime, registry
            captured["agent"] = max_output_tokens

    class CapturingPortraitGenerator:
        def __init__(
            self,
            model_runtime: object,
            *,
            max_output_tokens: int,
        ) -> None:
            del model_runtime
            captured["portrait"] = max_output_tokens

    monkeypatch.setattr(
        app_module,
        "create_agent_callback_signer",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(app_module, "AgentRuntime", CapturingAgentRuntime)
    monkeypatch.setattr(
        app_module,
        "ModelPortraitGenerator",
        CapturingPortraitGenerator,
    )
    settings = Settings.model_validate(
        {
            "environment": "test",
            "model_provider": "fake",
            "agent_service_private_key_path": "unused.pem",
            "workflow_human_log_dir": str(tmp_path),
            "model_max_output_tokens": 456_789,
        }
    )

    app = create_app(settings=settings, run_queue=object())  # type: ignore[arg-type]
    try:
        assert captured == {"agent": 456_789, "portrait": 456_789}
    finally:
        await app.state.core_http.aclose()
