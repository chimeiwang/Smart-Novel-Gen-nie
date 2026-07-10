from __future__ import annotations

import secrets
from collections.abc import Mapping
from datetime import UTC, datetime
from threading import Lock
from time import time_ns
from typing import Any

from sqlalchemy.orm import DeclarativeBase

_BASE36_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
_COUNTER_MODULUS = 36**4
_COUNTER_LOCK = Lock()
_COUNTER = secrets.randbelow(_COUNTER_MODULUS)
_PROCESS_FINGERPRINT = secrets.randbelow(_COUNTER_MODULUS)


def _base36(value: int, width: int) -> str:
    encoded = ""
    while value:
        value, remainder = divmod(value, 36)
        encoded = _BASE36_ALPHABET[remainder] + encoded
    return encoded.rjust(width, "0")[-width:]


def generate_id() -> str:
    """生成与 Prisma cuid() 相同布局和长度的 CUID v1 字符串。"""

    # 布局固定为 c + 8 位毫秒时间 + 4 位计数器 + 4 位进程指纹 + 8 位随机数。
    global _COUNTER
    with _COUNTER_LOCK:
        counter = _COUNTER
        _COUNTER = (_COUNTER + 1) % _COUNTER_MODULUS
    timestamp = time_ns() // 1_000_000
    random_value = secrets.randbelow(36**8)
    return (
        "c"
        + _base36(timestamp, 8)
        + _base36(counter, 4)
        + _base36(_PROCESS_FINGERPRINT, 4)
        + _base36(random_value, 8)
    )


def utc_now() -> datetime:
    """返回精确到毫秒的协调世界时无时区时间。"""

    current = datetime.now(UTC).replace(tzinfo=None)
    return current.replace(microsecond=(current.microsecond // 1000) * 1000)


class Base(DeclarativeBase):
    """所有核心接口服务对象关系映射的统一基类。"""

    def __init__(self, **values: Any) -> None:
        initial_values: Mapping[str, Any] = values
        if "id" not in initial_values and hasattr(type(self), "id"):
            initial_values = {**initial_values, "id": generate_id()}
        for name, value in initial_values.items():
            if not hasattr(type(self), name):
                raise TypeError(f"{type(self).__name__} 不接受属性：{name}")
            setattr(self, name, value)
