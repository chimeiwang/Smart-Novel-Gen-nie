import pytest
from inkforge_agents.config import Settings
from inkforge_agents.providers.deepseek_v4 import DeepSeekV4Provider
from inkforge_agents.providers.fake import FakeModelProvider
from inkforge_agents.providers.openai_compatible import OpenAICompatibleProvider
from inkforge_agents.providers.selector import create_model_provider


def test_only_explicit_fake_provider_selects_fake() -> None:
    fake = Settings.model_validate({"environment": "test", "model_provider": "fake"})
    assert isinstance(create_model_provider(fake), FakeModelProvider)

    real = Settings.model_validate(
        {
            "environment": "test",
            "model_provider": "openai_compatible",
            "openai_api_key": "test-key",
            "openai_base_url": "https://example.com/v1",
            "openai_model": "deepseek-v4-flash",
        }
    )
    assert isinstance(create_model_provider(real), OpenAICompatibleProvider)


def test_real_provider_without_credentials_does_not_fall_back_to_fake() -> None:
    settings = Settings.model_validate(
        {"environment": "test", "model_provider": "openai_compatible"}
    )

    with pytest.raises(ValueError, match="真实模型提供方缺少"):
        create_model_provider(settings)


def test_explicit_compatibility_profile_selects_deepseek_without_url_guessing() -> None:
    deepseek = Settings.model_validate(
        {
            "environment": "test",
            "model_provider": "openai_compatible",
            "openai_compatibility_profile": "deepseek_v4",
            "openai_api_key": "test-key",
            "openai_base_url": "https://example.com/v1",
        }
    )
    assert isinstance(create_model_provider(deepseek), DeepSeekV4Provider)

def test_optional_strict_base_url_normalizes_empty_environment_value() -> None:
    assert Settings.model_validate({"openai_strict_base_url": "  "}).openai_strict_base_url is None
    assert (
        Settings.model_validate(
            {"openai_strict_base_url": " https://gateway.example/deepseek-beta "}
        ).openai_strict_base_url
        == "https://gateway.example/deepseek-beta"
    )
