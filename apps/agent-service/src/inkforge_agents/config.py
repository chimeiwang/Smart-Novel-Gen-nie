from __future__ import annotations

from ipaddress import ip_network
from typing import Annotated, Literal
from urllib.parse import unquote, urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
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
    # V2 execution journal 使用独立、持久化的 Redis；不得复用普通队列实例。
    execution_redis_url: SecretStr | None = None
    queue_terminal_retention_days: int = Field(default=7, ge=1)
    execution_terminal_retention_hours: int = Field(default=24, ge=24, le=168)
    # 只供跨进程 E2E 注入现有 ModelProvider 接口的测试实现。生产与开发环境只要
    # 出现任一控制面配置就必须在应用创建前失败，且服务本身不暴露测试路由。
    e2e_execution_control_url: str | None = None
    e2e_execution_control_token: SecretStr | None = None
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

    def validate_execution_redis_configuration(self) -> None:
        """校验真实运行时的双 Redis 边界；测试可直接注入内存 journal。"""

        if self.environment != "production":
            return
        if self.redis_url is None or self.execution_redis_url is None:
            raise ValueError("生产环境必须分别配置 REDIS_URL 与 EXECUTION_REDIS_URL")
        ordinary = _redis_endpoint_identity(self.redis_url)
        execution = _redis_endpoint_identity(self.execution_redis_url)
        if ordinary == execution:
            raise ValueError("生产环境的 REDIS_URL 与 EXECUTION_REDIS_URL 不能指向同一 Redis 实例")

    @model_validator(mode="after")
    def validate_e2e_execution_control(self) -> Settings:
        url = (
            self.e2e_execution_control_url.strip()
            if self.e2e_execution_control_url is not None
            else ""
        )
        token = (
            self.e2e_execution_control_token.get_secret_value()
            if self.e2e_execution_control_token is not None
            else ""
        )
        if not url and not token:
            return self
        if self.environment != "test":
            raise ValueError("E2E execution 控制面只允许 ENVIRONMENT=test")
        if not url or not token:
            raise ValueError("E2E execution 控制 URL 与令牌必须同时配置")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("E2E execution 控制 URL 必须是无凭据的内部 HTTP 地址")
        if len(token.encode("utf-8")) < 32:
            raise ValueError("E2E execution 控制令牌至少需要 32 个 UTF-8 字节")
        self.e2e_execution_control_url = url.rstrip("/")
        return self


def create_testing_settings() -> Settings:
    return Settings.model_validate(
        {
            "environment": "test",
            "model_provider": "fake",
            "openai_api_key": None,
            "trusted_core_cidrs": ("127.0.0.1/32", "::1/128"),
        }
    )


def _redis_endpoint_identity(value: SecretStr) -> tuple[str, str, int]:
    """忽略凭据、大小写、默认端口和逻辑 DB，只比较物理 Redis 实例。"""

    raw = value.get_secret_value().strip()
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme in {"redis", "rediss"}:
        if parsed.hostname is None:
            raise ValueError("Redis URL 缺少主机")
        try:
            port = parsed.port or 6379
        except ValueError as exc:
            raise ValueError("Redis URL 端口无效") from exc
        path = unquote(parsed.path or "").strip("/")
        try:
            database = int(path or "0")
        except ValueError as exc:
            raise ValueError("Redis URL DB 必须是非负整数") from exc
        if database < 0:
            raise ValueError("Redis URL DB 必须是非负整数")
        return ("tcp", parsed.hostname.rstrip(".").lower(), port)
    if scheme == "unix":
        path = unquote(parsed.path)
        if not path:
            raise ValueError("Unix Redis URL 缺少 socket 路径")
        query = {
            key: value
            for item in parsed.query.split("&")
            if item
            for key, _, value in (item.partition("="),)
        }
        try:
            database = int(query.get("db", "0"))
        except ValueError as exc:
            raise ValueError("Redis URL DB 必须是非负整数") from exc
        if database < 0:
            raise ValueError("Redis URL DB 必须是非负整数")
        return ("unix", path, 0)
    raise ValueError("Redis URL 只允许 redis、rediss 或 unix scheme")
