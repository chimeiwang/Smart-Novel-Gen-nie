from __future__ import annotations

from typing import Literal, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "test", "production"]

_PRODUCTION_REQUIRED_FIELDS = (
    "database_url",
    "redis_url",
    "jwt_secret",
    "core_service_private_key_path",
    "agent_service_public_key_path",
    "agent_service_url",
)


class Settings(BaseSettings):
    # 部署环境可能共享配置源；忽略无关字段可避免其他服务的配置阻止本服务启动。
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_prefix="",
        extra="ignore",
    )

    environment: Environment = "dev"
    database_url: SecretStr | None = None
    redis_url: SecretStr | None = None
    jwt_secret: SecretStr | None = None
    core_service_private_key_path: str | None = None
    agent_service_public_key_path: str | None = None
    agent_service_url: str | None = None

    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, value: object) -> object:
        if value not in {"dev", "test", "production"}:
            raise ValueError("environment 必须是 dev、test 或 production")
        return value

    @model_validator(mode="after")
    def validate_production_configuration(self) -> Self:
        if self.environment != "production":
            return self

        missing_fields = [
            field_name
            for field_name in _PRODUCTION_REQUIRED_FIELDS
            if not _has_non_blank_value(getattr(self, field_name))
        ]
        if missing_fields:
            joined_fields = "、".join(missing_fields)
            raise ValueError(f"生产环境缺少必需配置：{joined_fields}")
        return self


def create_testing_settings() -> Settings:
    return Settings.model_validate(
        {
            "environment": "test",
            "database_url": None,
            "redis_url": None,
            "jwt_secret": None,
            "core_service_private_key_path": None,
            "agent_service_public_key_path": None,
            "agent_service_url": None,
        }
    )


def _has_non_blank_value(value: SecretStr | str | None) -> bool:
    if value is None:
        return False
    raw_value = value.get_secret_value() if isinstance(value, SecretStr) else value
    return bool(raw_value.strip())
