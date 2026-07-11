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
