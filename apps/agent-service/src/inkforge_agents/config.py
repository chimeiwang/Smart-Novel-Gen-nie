from __future__ import annotations

from ipaddress import ip_network
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["dev", "test", "production"]
ModelProviderName = Literal["fake", "openai_compatible"]
OpenAICompatibilityProfile = Literal["generic", "deepseek_v4"]


class Settings(BaseSettings):
    # 同一份 Compose 环境文件会包含其他服务配置，因此忽略本服务不认识的字段。
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_prefix="",
        extra="ignore",
    )

    environment: Environment = "dev"
    model_provider: ModelProviderName = "openai_compatible"
    openai_compatibility_profile: OpenAICompatibilityProfile = "generic"
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.deepseek.com"
    openai_strict_base_url: str | None = None
    openai_model: str = "deepseek-v4-flash"
    model_max_output_tokens: int = Field(default=384_000, ge=1, le=1_000_000)
    agent_max_concurrency: int = Field(default=3, ge=1, le=3)
    redis_url: SecretStr | None = None
    queue_terminal_retention_days: int = Field(default=7, ge=1)
    trusted_core_cidrs: Annotated[tuple[str, ...], NoDecode] = ()
    core_service_public_key_path: str | None = None
    agent_service_private_key_path: str | None = None
    agent_service_key_id: str = "agent-service-v1"
    core_api_url: str = "http://core-api:8000"
    # 开发环境使用仓库内可写目录；生产 Compose 会显式覆盖为持久化卷路径。
    workflow_human_log_dir: str = "./.data/agent-logs"
    rag_embedding_api_key: SecretStr | None = None
    rag_embedding_base_url: str | None = None
    rag_embedding_model: str | None = None
    rag_index_enabled: bool = False
    # 火山密钥只属于 Agent/供应商网关；默认关闭真实付费调用。
    seedance_api_key: SecretStr | None = None
    seedance_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    seedance_model: str = "doubao-seedance-2-5-260628"
    seedance_enabled: bool = False

    @field_validator("openai_strict_base_url", mode="before")
    @classmethod
    def normalize_optional_openai_strict_base_url(cls, value: object) -> str | None:
        # 环境变量中的空值表示未配置，避免把空字符串传给模型客户端。
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("trusted_core_cidrs", mode="before")
    @classmethod
    def validate_trusted_core_cidrs(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            candidates = tuple(item.strip() for item in value.split(",") if item.strip())
        elif isinstance(value, (list, tuple)):
            candidates = tuple(str(item).strip() for item in value if str(item).strip())
        else:
            raise ValueError("可信核心服务网段必须是列表或逗号分隔文本")
        normalized: list[str] = []
        for candidate in candidates:
            try:
                normalized.append(str(ip_network(candidate, strict=False)))
            except ValueError as exc:
                raise ValueError("可信核心服务网段无效") from exc
        return tuple(normalized)


def create_testing_settings() -> Settings:
    return Settings.model_validate(
        {
            "environment": "test",
            "model_provider": "fake",
            "openai_api_key": None,
            "trusted_core_cidrs": ("127.0.0.1/32", "::1/128"),
        }
    )
