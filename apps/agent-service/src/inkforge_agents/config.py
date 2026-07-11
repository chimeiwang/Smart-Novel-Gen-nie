from __future__ import annotations

from typing import Annotated, Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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
    redis_url: SecretStr | None = None
    trusted_core_cidrs: Annotated[tuple[str, ...], NoDecode] = ()
    core_service_public_key_path: str | None = None
    agent_service_private_key_path: str | None = None
    agent_service_key_id: str = "agent-service-v1"
    core_api_url: str = "http://core-api:8000"
    rag_embedding_api_key: SecretStr | None = None
    rag_embedding_base_url: str | None = None
    rag_embedding_model: str | None = None


def create_testing_settings() -> Settings:
    return Settings.model_validate(
        {
            "environment": "test",
            "model_provider": "fake",
            "openai_api_key": None,
            "trusted_core_cidrs": ("127.0.0.1/32", "::1/128"),
        }
    )
