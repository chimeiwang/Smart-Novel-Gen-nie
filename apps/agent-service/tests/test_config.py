import pytest
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
