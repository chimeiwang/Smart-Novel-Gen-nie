from __future__ import annotations

import httpx
from pydantic import ValidationError
from sqlalchemy.exc import (
    DBAPIError,
    DisconnectionError,
    InterfaceError,
    OperationalError,
)
from sqlalchemy.exc import (
    TimeoutError as SqlAlchemyTimeoutError,
)

from ..errors import ApiError

_TRANSIENT_SQLSTATES = frozenset(
    {
        "40001",  # 序列化失败
        "40P01",  # 检测到死锁
        "55P03",  # 暂时无法获得锁
        "57P01",  # 管理员关闭数据库
        "57P02",  # 数据库崩溃关闭
        "57P03",  # 数据库暂时无法连接
    }
)


def is_transient_infrastructure_error(error: BaseException) -> bool:
    """只识别可以由同一后台任务安全重试的基础设施暂态错误。"""

    if isinstance(error, (TypeError, ValidationError)):
        return False
    if isinstance(error, ApiError):
        return _is_transient_agent_api_error(error)
    if isinstance(
        error,
        (
            ConnectionError,
            TimeoutError,
            httpx.TransportError,
            DisconnectionError,
            InterfaceError,
            OperationalError,
            SqlAlchemyTimeoutError,
        ),
    ):
        return True
    if isinstance(error, DBAPIError):
        return bool(error.connection_invalidated) or _sqlstate(error) in _TRANSIENT_SQLSTATES
    return False


def _is_transient_agent_api_error(error: ApiError) -> bool:
    cause = error.__cause__
    if isinstance(cause, httpx.TransportError):
        return True
    if isinstance(cause, httpx.HTTPStatusError):
        status_code = cause.response.status_code
        return status_code == 429 or status_code >= 500
    return False


def _sqlstate(error: DBAPIError) -> str | None:
    original = error.orig
    for name in ("sqlstate", "pgcode"):
        value = getattr(original, name, None)
        if isinstance(value, str):
            return value
    return None
