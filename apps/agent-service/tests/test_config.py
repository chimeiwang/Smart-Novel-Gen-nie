from datetime import timedelta

import inkforge_agents.app as app_module
import pytest
from inkforge_agents.app import create_app
from inkforge_agents.config import Settings
from pydantic import ValidationError


def test_trusted_core_cidrs_accept_comma_separated_environment_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRUSTED_CORE_CIDRS", "127.0.0.1/32, ::1/128")

    settings = Settings()

    assert settings.trusted_core_cidrs == ("127.0.0.1/32", "::1/128")


def test_trusted_core_cidrs_reject_invalid_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRUSTED_CORE_CIDRS", "not-a-network")

    with pytest.raises(ValidationError, match="可信核心服务网段无效"):
        Settings()


def test_queue_terminal_retention_days_defaults_to_seven_and_rejects_zero() -> None:
    assert Settings.model_validate({}).queue_terminal_retention_days == 7

    with pytest.raises(ValidationError):
        Settings.model_validate({"queue_terminal_retention_days": 0})


def test_queue_terminal_retention_days_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUEUE_TERMINAL_RETENTION_DAYS", "3")

    assert Settings().queue_terminal_retention_days == 3


def test_runtime_passes_terminal_retention_setting_to_queue() -> None:
    settings = Settings.model_validate(
        {
            "model_provider": "fake",
            "queue_terminal_retention_days": 3,
        }
    )
    app = create_app(testing=True, settings=settings)
    app.state.redis = object()

    app_module._configure_runtime(app, settings)

    assert app.state.run_queue.terminal_retention == timedelta(days=3)
