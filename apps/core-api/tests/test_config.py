from __future__ import annotations

import pytest
from inkforge_core.app import create_app
from inkforge_core.config import Settings
from pydantic import SecretStr, ValidationError

PRODUCTION_VALUES = {
    "environment": "production",
    "database_url": "postgresql://user:password@database:5432/inkforge",
    "redis_url": "redis://:redis-secret@redis:6379/0",
    "jwt_secret": "production-only-secret-at-least-32-bytes",
    "trusted_proxy_cidrs": ["172.16.0.0/12"],
    "trusted_agent_cidrs": ["10.20.0.0/16"],
    "core_service_private_key_path": "/run/secrets/core-private.pem",
    "agent_service_public_key_path": "/run/secrets/agent-public.pem",
    "agent_service_url": "http://agent-service:8001",
}

CRITICAL_FIELDS = [
    "database_url",
    "redis_url",
    "jwt_secret",
    "trusted_proxy_cidrs",
    "trusted_agent_cidrs",
    "core_service_private_key_path",
    "agent_service_public_key_path",
    "agent_service_url",
]


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = dict(PRODUCTION_VALUES)
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.mark.parametrize("field", CRITICAL_FIELDS)
@pytest.mark.parametrize("missing_value", [None, "", "   "])
def test_production_rejects_each_missing_or_blank_critical_setting(
    field: str, missing_value: str | None
) -> None:
    with pytest.raises(ValidationError, match="生产环境缺少必需配置"):
        production_settings(**{field: missing_value})


def test_production_accepts_complete_explicit_configuration() -> None:
    settings = production_settings()

    assert settings.environment == "production"
    assert isinstance(settings.database_url, SecretStr)
    assert isinstance(settings.redis_url, SecretStr)
    assert isinstance(settings.jwt_secret, SecretStr)
    assert settings.jwt_secret.get_secret_value() == PRODUCTION_VALUES["jwt_secret"]
    assert settings.trusted_proxy_cidrs == ("172.16.0.0/12",)
    assert settings.trusted_agent_cidrs == ("10.20.0.0/16",)


def test_session_cookie_secure_requires_explicit_insecure_http_override() -> None:
    assert production_settings().session_cookie_secure is True
    assert production_settings(allow_insecure_http_auth=True).session_cookie_secure is False
    assert Settings(environment="dev").session_cookie_secure is False


def test_production_rejects_short_jwt_secret_without_echoing_it() -> None:
    short_jwt_key = "不可用于生产"
    with pytest.raises(ValidationError) as caught:
        production_settings(jwt_secret=short_jwt_key)

    rendered_error = str(caught.value)
    assert "至少需要 32 个 UTF-8 字节" in rendered_error
    assert short_jwt_key not in rendered_error


def test_trusted_proxy_cidrs_accept_comma_separated_environment_value() -> None:
    settings = Settings.model_validate(
        {
            "environment": "dev",
            "trusted_proxy_cidrs": "172.16.0.0/12, 2001:db8::/32",
        }
    )
    assert settings.trusted_proxy_cidrs == ("172.16.0.0/12", "2001:db8::/32")


def test_trusted_proxy_cidrs_load_from_comma_separated_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "172.16.0.0/12,2001:db8::/32")
    settings = Settings(environment="dev")
    assert settings.trusted_proxy_cidrs == ("172.16.0.0/12", "2001:db8::/32")


def test_invalid_trusted_proxy_cidr_is_rejected() -> None:
    with pytest.raises(ValidationError, match="可信代理网段无效"):
        Settings.model_validate(
            {"environment": "dev", "trusted_proxy_cidrs": ["不是网段"]}
        )


def test_trusted_agent_cidrs_load_from_required_environment_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_SERVICE_CIDRS", "10.20.0.0/16,2001:db8:1::/48")
    settings = Settings(environment="dev")
    assert settings.trusted_agent_cidrs == ("10.20.0.0/16", "2001:db8:1::/48")


def test_invalid_trusted_agent_cidr_is_rejected() -> None:
    with pytest.raises(ValidationError, match="可信智能体网段无效"):
        Settings.model_validate(
            {"environment": "dev", "trusted_agent_cidrs": ["不是网段"]}
        )


def test_sensitive_settings_are_masked_in_repr_dump_and_validation_error() -> None:
    settings = production_settings()
    secret_values = (
        PRODUCTION_VALUES["database_url"],
        PRODUCTION_VALUES["redis_url"],
        PRODUCTION_VALUES["jwt_secret"],
    )

    rendered_settings = repr(settings)
    rendered_dump = repr(settings.model_dump())
    for secret in secret_values:
        assert secret not in rendered_settings
        assert secret not in rendered_dump

    invalid_values: dict[str, object] = dict(PRODUCTION_VALUES)
    invalid_values["agent_service_url"] = " "
    with pytest.raises(ValidationError) as caught:
        Settings.model_validate(invalid_values)
    rendered_error = str(caught.value)
    for secret in secret_values:
        assert secret not in rendered_error


def test_dev_and_test_do_not_have_default_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)

    assert Settings(environment="dev").jwt_secret is None
    assert Settings(environment="test").jwt_secret is None


def test_testing_app_does_not_read_bad_production_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "secret-database-url")
    monkeypatch.setenv("REDIS_URL", "secret-redis-url")
    monkeypatch.setenv("JWT_SECRET", "secret-jwt")
    monkeypatch.setenv("CORE_SERVICE_PRIVATE_KEY_PATH", "secret-core-key")
    monkeypatch.setenv("AGENT_SERVICE_PUBLIC_KEY_PATH", "secret-agent-key")
    monkeypatch.setenv("AGENT_SERVICE_URL", "secret-agent-url")

    app = create_app(testing=True)
    settings = app.state.settings

    assert settings.environment == "test"
    assert settings.database_url is None
    assert settings.redis_url is None
    assert settings.jwt_secret is None
    assert settings.trusted_proxy_cidrs == ()
    assert settings.trusted_agent_cidrs == ()
    assert settings.core_service_private_key_path is None
    assert settings.agent_service_public_key_path is None
    assert settings.agent_service_url is None


def test_create_app_uses_explicit_settings_instance() -> None:
    settings = Settings(environment="dev", agent_service_url="http://localhost:8001")

    app = create_app(settings=settings)

    assert app.state.settings is settings
