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


def test_deepseek_base_url_defaults_to_official_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert Settings.model_validate({}).openai_base_url == "https://api.deepseek.com"


def test_queue_terminal_retention_days_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUEUE_TERMINAL_RETENTION_DAYS", "3")

    assert Settings().queue_terminal_retention_days == 3


def test_execution_terminal_retention_is_independent_and_bounded() -> None:
    settings = Settings.model_validate(
        {
            "queue_terminal_retention_days": 7,
            "execution_terminal_retention_hours": 24,
        }
    )

    assert settings.queue_terminal_retention_days == 7
    assert settings.execution_terminal_retention_hours == 24
    for invalid in (0, 23, 169):
        with pytest.raises(ValidationError):
            Settings.model_validate({"execution_terminal_retention_hours": invalid})


def test_agent_parallel_limit_defaults_to_three_and_accepts_lower_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings.model_validate({}).agent_max_concurrency == 3

    monkeypatch.setenv("AGENT_MAX_CONCURRENCY", "1")
    assert Settings().agent_max_concurrency == 1
    monkeypatch.setenv("AGENT_MAX_CONCURRENCY", "2")
    assert Settings().agent_max_concurrency == 2

    for invalid_value in (0, 4):
        with pytest.raises(ValidationError):
            Settings.model_validate({"agent_max_concurrency": invalid_value})


def test_模型最大输出预算默认值与边界() -> None:
    assert Settings.model_validate({}).model_max_output_tokens == 384_000
    assert (
        Settings.model_validate({"model_max_output_tokens": 1}).model_max_output_tokens
        == 1
    )
    assert (
        Settings.model_validate(
            {"model_max_output_tokens": 1_000_000}
        ).model_max_output_tokens
        == 1_000_000
    )

    for invalid_value in (0, 1_000_001):
        with pytest.raises(ValidationError):
            Settings.model_validate({"model_max_output_tokens": invalid_value})


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


def test_production_requires_dedicated_execution_redis_url() -> None:
    missing = Settings.model_validate(
        {
            "environment": "production",
            "redis_url": "redis://redis:6379/0",
        }
    )
    with pytest.raises(ValueError, match="EXECUTION_REDIS_URL"):
        missing.validate_execution_redis_configuration()


def test_production_rejects_normalized_same_execution_redis_db() -> None:
    settings = Settings.model_validate(
        {
            "environment": "production",
            "redis_url": "redis://user:old@REDIS.:6379/0",
            "execution_redis_url": "rediss://user:new@redis/0",
        }
    )

    with pytest.raises(ValueError, match="同一 Redis 实例"):
        settings.validate_execution_redis_configuration()


def test_production_rejects_same_instance_even_when_logical_db_differs() -> None:
    settings = Settings.model_validate(
        {
            "environment": "production",
            "redis_url": "redis://redis:6379/0",
            "execution_redis_url": "redis://redis:6379/1",
        }
    )

    with pytest.raises(ValueError, match="同一 Redis 实例"):
        settings.validate_execution_redis_configuration()


def test_production_accepts_distinct_execution_redis_instance() -> None:
    settings = Settings.model_validate(
        {
            "environment": "production",
            "redis_url": "redis://redis:6379/0",
            "execution_redis_url": "redis://execution-redis:6379/0",
        }
    )

    settings.validate_execution_redis_configuration()
