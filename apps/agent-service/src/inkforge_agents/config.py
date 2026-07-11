from __future__ import annotations

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "test", "production"]
ModelProviderName = Literal["fake", "openai_compatible"]


class Settings(BaseSettings):
    # 同一份 Compose 环境文件会包含其他服务配置，因此忽略本服务不认识的字段。
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_prefix="",
        extra="ignore",
    )

    environment: Environment = "dev"
    model_provider: ModelProviderName = "openai_compatible"
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.deepseek.com/v1"
    openai_model: str = "deepseek-v4-flash"


def create_testing_settings() -> Settings:
    return Settings.model_validate(
        {
            "environment": "test",
            "model_provider": "fake",
            "openai_api_key": None,
        }
    )
