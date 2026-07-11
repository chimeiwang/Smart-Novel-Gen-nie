from fastapi.testclient import TestClient
from inkforge_agents.app import create_app
from inkforge_agents.config import Settings


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
