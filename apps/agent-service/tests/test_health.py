from pathlib import Path

import inkforge_agents.app as app_module
import pytest
from fastapi.testclient import TestClient
from inkforge_agents.app import create_app
from inkforge_agents.config import Settings


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
        while not app.state.consumer_task.done() and time.monotonic() < deadline:
            time.sleep(0.001)
        response = client.get("/internal/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["queue_consumer"] == "failed"


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
