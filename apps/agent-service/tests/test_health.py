import asyncio
import re
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import fakeredis
import fakeredis.aioredis
import inkforge_agents.app as app_module
import pytest
from fastapi.testclient import TestClient
from inkforge_agents.app import create_app
from inkforge_agents.config import Settings
from inkforge_agents.execution.callbacks import ExecutionCallbackClient
from inkforge_agents.execution.executor import StatelessExecutionStepExecutor
from inkforge_agents.execution.journal import (
    AsyncJournalRedis,
    ExecutionJournalError,
    RedisExecutionJournal,
)
from inkforge_agents.execution.registry import load_execution_registry
from inkforge_agents.execution.service import ExecutionService, ExecutionServiceHealth
from inkforge_agents.providers.fake import FakeModelProvider
from inkforge_agents.queue.cancellation import RedisRunCancellation
from inkforge_agents.queue.consumer import QueueConsumer
from inkforge_agents.runtime.model_runtime import ModelRuntime
from inkforge_agents.supervision import CoroutineSupervisor
from inkforge_contracts.execution import ExecutionStepRequest
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
    assert re.fullmatch(
        r"[0-9a-f]{64}", response.json()["executionManifestFingerprint"]
    )


def test_testing_app_is_ready_with_explicit_fake_provider() -> None:
    app = create_app(testing=True)
    response = TestClient(app).get("/internal/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    fingerprint = response.json()["executionManifestFingerprint"]
    assert isinstance(fingerprint, str)
    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    assert fingerprint == app.state.execution_registry.manifest_fingerprint
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


class StrictHealthRedis(fakeredis.aioredis.FakeRedis):
    """仅替代外部 Redis 的配置元数据；journal、Lua 与生产健康计算保持真实。"""

    async def info(self, section: str | None = None, **kwargs: Any) -> dict[str, object]:
        del kwargs
        return {
            "persistence": {"aof_enabled": 1, "aof_last_write_status": "ok"},
            "memory": {"used_memory": 1024},
            "stats": {"evicted_keys": 0},
        }.get(section or "", {})

    async def config_get(self, *args: Any, **kwargs: Any) -> dict[str, str]:
        del args, kwargs
        return {
            "appendonly": "yes", "appendfsync": "always", "aof-load-truncated": "no",
            "maxmemory-policy": "noeviction", "maxmemory": "33554432",
            "hash-max-listpack-value": "4096", "hash-max-listpack-entries": "64",
        }


class PollObservedJournal(RedisExecutionJournal):
    def __init__(self, redis: AsyncJournalRedis) -> None:
        super().__init__(redis, require_durability=True)
        self.poll_attempts = 0
        self.two_polls = asyncio.Event()

    async def claim_due_callbacks(self, **kwargs: Any) -> Any:
        try:
            return await super().claim_due_callbacks(**kwargs)
        finally:
            self.poll_attempts += 1
            if self.poll_attempts >= 2:
                self.two_polls.set()


class NoCallProvider(FakeModelProvider):
    calls = 0

    async def complete_turn(self, request: Any) -> Any:
        self.calls += 1
        raise AssertionError("迁移前空 journal 待机不得调用模型")


class NoCallCallbacks:
    calls = 0

    async def send_progress(self, callback: Any) -> Any:
        self.calls += 1
        raise AssertionError("迁移前空 journal 待机不得发出回调")

    send_result = send_progress
    send_failure = send_progress


def _production_journal_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from redis.asyncio import Redis

    server = fakeredis.FakeServer()
    redis = StrictHealthRedis(server=server)
    state = fakeredis.FakeRedis(server=server)
    ordinary = fakeredis.aioredis.FakeRedis()
    monkeypatch.setattr(Redis, "from_url", lambda *args, **kwargs: ordinary)
    journal = PollObservedJournal(cast(AsyncJournalRedis, redis))
    provider = NoCallProvider()
    callbacks = NoCallCallbacks()
    execution = ExecutionService(
        journal=journal,
        registry=load_execution_registry(environment="production"),
        executor=StatelessExecutionStepExecutor(ModelRuntime(provider), max_output_tokens=10_000),
        callbacks=cast(ExecutionCallbackClient, callbacks),
    )
    settings = Settings.model_validate({
        "environment": "production", "model_provider": "fake",
        "redis_url": "redis://ordinary.invalid:6379/0",
        "execution_redis_url": "redis://execution.invalid:6379/0",
        "workflow_human_log_dir": str(tmp_path),
    })
    app = create_app(
        testing=False,
        settings=settings,
        run_queue=object(),  # type: ignore[arg-type]
        core_request_verifier=object(),  # type: ignore[arg-type]
        queue_consumer=Consumer(),
        execution_service=execution,
        execution_redis=cast(AsyncJournalRedis, redis),
    )
    app.state.core_client = object()
    assert app.state.runtime_error is None
    return app, journal, state, provider, callbacks


def test_production_lifespan_empty_uninitialized_journal_is_readonly_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    app, journal, state, provider, callbacks = _production_journal_app(monkeypatch, tmp_path)
    assert state.dbsize() == 0
    with TestClient(app) as client:
        assert client.portal is not None

        async def wait_for_two_polls() -> None:
            await asyncio.wait_for(journal.two_polls.wait(), timeout=3)
            await asyncio.sleep(0)

        client.portal.call(wait_for_two_polls)
        response = client.get("/internal/v1/health/ready")
        assert response.status_code == 200, response.json()
        checks = response.json()["checks"]
        assert checks["execution_callback_replayer"] == "ok"
        assert checks["execution_journal"] == "ok"
        assert checks["execution_journal_persistence"] == "ok"
        assert checks["execution_redis"] == "ok"
        assert checks["redis"] == "ok"
        assert app.state.execution_replayer_supervisor.is_ready()

        async def cannot_accept_before_named_initialization() -> None:
            # 这里只探测 journal 的原子准入门，不构造或派发模型业务请求。
            request = ExecutionStepRequest.model_construct(
                stepId="step-before-initialization", runId="run-before-initialization",
                jobId="job-before-initialization", novelId="novel-before-initialization",
                requestHash="a" * 64, inputHash="b" * 64, fencingToken=1,
                idempotencyKey="request-before-initialization",
            )
            with pytest.raises(ExecutionJournalError):
                await journal.accept(request, {"provider": "fake"})

        client.portal.call(cannot_accept_before_named_initialization)
        assert state.dbsize() == 0
        assert state.get("inkforge:executions:drain:index-version") is None
        assert provider.calls == callbacks.calls == 0
    assert not app.state.execution_replayer_supervisor.is_ready()


@pytest.mark.parametrize("damage", [
    "orphan", "drain:active", "callbacks:pending", "callbacks:leased", "callbacks:rejected",
    "invalid_marker", "restore:quarantine", "other",
])
def test_production_lifespan_nonempty_uninitialized_journal_stays_unready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, damage: str,
) -> None:
    app, journal, state, provider, callbacks = _production_journal_app(monkeypatch, tmp_path)
    prefix = "inkforge:executions:"
    if damage == "orphan":
        state.hset(prefix + "orphan", mapping={"state": "accepted"})
    elif damage == "invalid_marker":
        state.set(prefix + "drain:index-version", "2")
    elif damage.startswith(("drain:", "callbacks:")):
        state.zadd(prefix + damage, {prefix + "orphan": 1})
    else:
        state.set(prefix + damage, "synthetic-test-fact")
    before = {key: state.dump(key) for key in state.scan_iter()}

    with TestClient(app) as client:
        assert client.portal is not None

        deadline = time.monotonic() + 1
        while (
            app.state.execution_replayer_supervisor.error_code != "BACKGROUND_TASK_BACKOFF"
            and time.monotonic() < deadline
        ):
            time.sleep(0.001)
        response = client.get("/internal/v1/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["execution_callback_replayer"] == "failed"
        assert not app.state.execution_replayer_supervisor.is_ready()
        assert {key: state.dump(key) for key in state.scan_iter()} == before
        assert provider.calls == callbacks.calls == 0


def test_readiness_fails_when_terminal_callback_replayer_crashes() -> None:
    class CrashedReplayer:
        async def run(self) -> None:
            raise RuntimeError("模拟终态重放器崩溃")

        def request_stop(self) -> None:
            pass

    class Execution:
        callback_replayer = CrashedReplayer()

        async def health(self) -> ExecutionServiceHealth:
            return ExecutionServiceHealth(
                ready=True,
                callback_pending=0,
                callback_rejected=0,
                error_code=None,
                admission_active=0,
                admission_capacity=3,
                admission_saturated=False,
                journal_connected=True,
                journal_persistence_ok=True,
                journal_quarantined=False,
            )

        async def close(self) -> None:
            pass

    settings = Settings.model_validate(
        {"environment": "production", "model_provider": "fake"}
    )
    consumer = Consumer()
    app = create_app(
        testing=True,
        settings=settings,
        run_queue=object(),  # type: ignore[arg-type]
        core_request_verifier=object(),  # type: ignore[arg-type]
        queue_consumer=consumer,
        execution_service=Execution(),  # type: ignore[arg-type]
    )
    app.state.core_client = object()

    with TestClient(app) as client:
        import time

        deadline = time.monotonic() + 1
        while (
            app.state.execution_replayer_supervisor.error_code
            != "BACKGROUND_TASK_BACKOFF"
            and time.monotonic() < deadline
        ):
            time.sleep(0.001)
        response = client.get("/internal/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["execution_callback_replayer"] == "failed"
    assert response.json()["backgroundTasks"]["execution_callback_replayer"] == (
        "BACKGROUND_TASK_BACKOFF"
    )


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


def test_readiness_fails_while_parallel_consumer_drains_after_failure() -> None:
    class DrainingConsumer(Consumer):
        def is_healthy(self) -> bool:
            return False

        @property
        def health_error_code(self) -> str:
            return "BACKGROUND_TASK_FAILURE_DRAINING"

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
        queue_consumer=DrainingConsumer(),
    )
    app.state.core_client = object()

    with TestClient(app) as client:
        response = client.get("/internal/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["queue_consumer"] == "failed"
    assert response.json()["backgroundTasks"] == {
        "queue_consumer": "BACKGROUND_TASK_FAILURE_DRAINING"
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
async def test_runtime_uses_one_shared_agent_parallel_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
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
            "agent_max_concurrency": 1,
        }
    )
    app = create_app(settings=settings, run_queue=object())  # type: ignore[arg-type]

    try:
        assert app.state.queue_consumer.max_concurrency == 1
        assert app.state.model_runtime.max_concurrency == 1
    finally:
        await app.state.core_http.aclose()


@pytest.mark.asyncio
async def test_应用装配向模型运行时传入相同输出预算并复用工作流日志(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    class CapturingAgentRuntime:
        def __init__(
            self,
            model_runtime: object,
            registry: object,
            *,
            max_output_tokens: int,
            cancellation: object | None = None,
        ) -> None:
            del model_runtime, registry
            captured["agent"] = max_output_tokens
            captured["cancellation"] = cancellation

    class CapturingPortraitGenerator:
        def __init__(
            self,
            model_runtime: object,
            *,
            max_output_tokens: int,
        ) -> None:
            del model_runtime
            captured["portrait"] = max_output_tokens

    class CapturingShortMediumGenerator:
        def __init__(
            self,
            model_runtime: object,
            *,
            max_output_tokens: int,
        ) -> None:
            del model_runtime
            captured["short"] = max_output_tokens

    class CapturingShortMediumHandler:
        def __init__(
            self,
            core: object,
            generator: object,
            *,
            workflow_log: object | None = None,
        ) -> None:
            del core, generator
            captured["short_log"] = workflow_log

        async def __call__(self, job: object) -> None:
            del job

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
    monkeypatch.setattr(
        app_module,
        "ModelShortMediumGenerator",
        CapturingShortMediumGenerator,
    )
    monkeypatch.setattr(
        app_module,
        "ShortMediumWritingJobHandler",
        CapturingShortMediumHandler,
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
        assert captured["agent"] == 456_789
        assert captured["portrait"] == 456_789
        assert captured["short"] == 456_789
        assert isinstance(captured["cancellation"], RedisRunCancellation)
        assert captured["short_log"] is not None
        assert captured["short_log"] is app.state.workflow_log
    finally:
        await app.state.core_http.aclose()
