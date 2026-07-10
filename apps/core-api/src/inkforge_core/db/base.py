from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import DeclarativeBase


def generate_id() -> str:
    """生成可由新旧应用共同读取的字符串标识。"""

    return uuid4().hex


def utc_now() -> datetime:
    """返回精确到毫秒的协调世界时无时区时间。"""

    current = datetime.now(UTC).replace(tzinfo=None)
    return current.replace(microsecond=(current.microsecond // 1000) * 1000)


class Base(DeclarativeBase):
    """所有核心接口服务对象关系映射的统一基类。"""
