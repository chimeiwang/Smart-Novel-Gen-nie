from __future__ import annotations

from ipaddress import ip_network
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Literal, Self

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["dev", "test", "production"]
OLD_DEFAULT_JWT_SECRET = "inkforge-default-" + "secret-change-me"

_PRODUCTION_REQUIRED_FIELDS = (
    "database_url",
    "redis_url",
    "jwt_secret",
    "trusted_proxy_cidrs",
    "trusted_agent_cidrs",
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
    trusted_agent_cidrs: Annotated[
        tuple[str, ...],
        NoDecode,
        Field(validation_alias=AliasChoices("trusted_agent_cidrs", "AGENT_SERVICE_CIDRS")),
    ] = ()
    core_service_private_key_path: str | None = None
    core_service_key_id: str = "core-api-v1"
    agent_service_public_key_path: str | None = None
    agent_service_url: str | None = None
    uploads_root: str = "/data/uploads"
    workflow_event_debug_enabled: bool = False
    rag_index_enabled: bool = False

    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, value: object) -> object:
        if value not in {"dev", "test", "production"}:
            raise ValueError("environment 必须是 dev、test 或 production")
        return value

    @field_validator("trusted_proxy_cidrs", mode="before")
    @classmethod
    def validate_trusted_proxy_cidrs(cls, value: object) -> tuple[str, ...]:
        return _normalize_cidrs(value, "可信代理网段")

    @field_validator("trusted_agent_cidrs", mode="before")
    @classmethod
    def validate_trusted_agent_cidrs(cls, value: object) -> tuple[str, ...]:
        return _normalize_cidrs(value, "可信智能体网段")

    @field_validator("uploads_root", mode="before")
    @classmethod
    def validate_uploads_root(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("上传根目录必须是绝对路径")
        normalized = value.strip()
        if (
            not normalized
            or "\x00" in normalized
            or not (
                PurePosixPath(normalized).is_absolute() or PureWindowsPath(normalized).is_absolute()
            )
        ):
            raise ValueError("上传根目录必须是绝对路径")
        return normalized

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
        if self.jwt_secret is not None and len(self.jwt_secret.get_secret_value().encode()) < 32:
            raise ValueError("生产环境会话签名密钥至少需要 32 个 UTF-8 字节")
        return self


def _normalize_cidrs(value: object, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        candidates = tuple(item.strip() for item in value.split(",") if item.strip())
    elif isinstance(value, (list, tuple)):
        candidates = tuple(str(item).strip() for item in value if str(item).strip())
    else:
        raise ValueError(f"{label}必须是列表或逗号分隔文本")
    normalized: list[str] = []
    for candidate in candidates:
        try:
            normalized.append(str(ip_network(candidate, strict=False)))
        except ValueError as exc:
            raise ValueError(f"{label}无效") from exc
    return tuple(normalized)


def create_testing_settings() -> Settings:
    return Settings.model_validate(
        {
            "environment": "test",
            "database_url": None,
            "redis_url": None,
            "jwt_secret": None,
            "trusted_proxy_cidrs": (),
            "trusted_agent_cidrs": (),
            "core_service_private_key_path": None,
            "core_service_key_id": "core-api-v1",
            "agent_service_public_key_path": None,
            "agent_service_url": None,
            "uploads_root": "/data/uploads",
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
