from __future__ import annotations

from ipaddress import ip_network
from typing import Annotated, Literal, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["dev", "test", "production"]
OLD_DEFAULT_JWT_SECRET = "inkforge-default-" + "secret-change-me"

_PRODUCTION_REQUIRED_FIELDS = (
    "database_url",
    "redis_url",
    "jwt_secret",
    "trusted_proxy_cidrs",
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
    trusted_proxy_cidrs: Annotated[tuple[str, ...], NoDecode] = ()
    core_service_private_key_path: str | None = None
    agent_service_public_key_path: str | None = None
    agent_service_url: str | None = None

    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, value: object) -> object:
        if value not in {"dev", "test", "production"}:
            raise ValueError("environment 必须是 dev、test 或 production")
        return value

    @field_validator("trusted_proxy_cidrs", mode="before")
    @classmethod
    def validate_trusted_proxy_cidrs(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            candidates = tuple(item.strip() for item in value.split(",") if item.strip())
        elif isinstance(value, (list, tuple)):
            candidates = tuple(str(item).strip() for item in value if str(item).strip())
        else:
            raise ValueError("可信代理网段必须是列表或逗号分隔文本")
        normalized: list[str] = []
        for candidate in candidates:
            try:
                normalized.append(str(ip_network(candidate, strict=False)))
            except ValueError as exc:
                raise ValueError("可信代理网段无效") from exc
        return tuple(normalized)

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
        if (
            self.jwt_secret is not None
            and self.jwt_secret.get_secret_value() == OLD_DEFAULT_JWT_SECRET
        ):
            raise ValueError("生产环境禁止使用旧默认会话签名密钥")
        if (
            self.jwt_secret is not None
            and len(self.jwt_secret.get_secret_value().encode()) < 32
        ):
            raise ValueError("生产环境会话签名密钥至少需要 32 个 UTF-8 字节")
        return self


def create_testing_settings() -> Settings:
    return Settings.model_validate(
        {
            "environment": "test",
            "database_url": None,
            "redis_url": None,
            "jwt_secret": None,
            "trusted_proxy_cidrs": (),
            "core_service_private_key_path": None,
            "agent_service_public_key_path": None,
            "agent_service_url": None,
        }
    )


def _has_non_blank_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, SecretStr):
        return bool(value.get_secret_value().strip())
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return bool(value)
    return True
