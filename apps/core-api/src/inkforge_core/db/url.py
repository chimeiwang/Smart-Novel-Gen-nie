from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.engine import URL, make_url

_ASYNCPG_SSL_MODES = frozenset(
    {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
)


@dataclass(frozen=True)
class AsyncpgConnectionOptions:
    """已净化的 asyncpg 地址和驱动连接参数。"""

    url: URL
    connect_args: dict[str, object]


def asyncpg_connection_options(database_url: str) -> AsyncpgConnectionOptions:
    """把 libpq 地址转换为 SQLAlchemy asyncpg 可接受的参数。"""

    try:
        url = make_url(database_url)
    except Exception:
        raise ValueError("无法解析数据库地址。") from None
    if url.get_backend_name() not in {"postgres", "postgresql"}:
        raise ValueError("核心接口服务只允许连接 PostgreSQL 数据库。")
    if url.drivername not in {"postgres", "postgresql", "postgresql+asyncpg"}:
        raise ValueError("数据库地址使用了不受支持的 PostgreSQL 驱动。")

    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    native_ssl = query.pop("ssl", None)
    if sslmode is not None and native_ssl is not None and sslmode != native_ssl:
        raise ValueError("数据库地址包含冲突的 SSL 配置。")
    selected_ssl = sslmode if sslmode is not None else native_ssl
    if selected_ssl is not None and (
        not isinstance(selected_ssl, str) or selected_ssl not in _ASYNCPG_SSL_MODES
    ):
        raise ValueError("数据库地址包含不受支持的 SSL 模式。")

    application_name = query.pop("application_name", None)
    if application_name is not None and (
        not isinstance(application_name, str) or not application_name.strip()
    ):
        raise ValueError("数据库地址包含无效的应用名称。")
    if query:
        raise ValueError("数据库地址包含不受支持的连接参数。")

    connect_args: dict[str, object] = {}
    if selected_ssl is not None:
        connect_args["ssl"] = selected_ssl
    if application_name is not None:
        connect_args["server_settings"] = {"application_name": application_name}
    return AsyncpgConnectionOptions(
        url=url.set(drivername="postgresql+asyncpg", query={}),
        connect_args=connect_args,
    )


def normalize_database_url(database_url: str) -> URL:
    """返回不含驱动不兼容查询参数的 asyncpg 地址。"""

    return asyncpg_connection_options(database_url).url
