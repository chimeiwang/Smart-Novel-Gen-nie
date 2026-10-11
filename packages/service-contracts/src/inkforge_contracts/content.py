"""中立内容计算：稳定 JSON 哈希和统一正文计数。"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from typing import Annotated

from pydantic import Field, StringConstraints

ResourceId = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

StrictPositiveInt = Annotated[int, Field(strict=True, gt=0)]


def _canonical_number(value: int | float | Decimal) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("执行哈希不允许 NaN 或 Infinity")
    decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    if not decimal.is_finite():
        raise ValueError("执行哈希不允许 NaN 或 Infinity")
    if decimal.is_zero():
        return "0"
    return format(decimal.normalize(), "f")


def _canonical_json_text(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float, Decimal)):
        return _canonical_number(value)
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError("执行哈希不允许未配对的 Unicode 代理字符")
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, list):
        return "[" + ",".join(_canonical_json_text(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("执行哈希 JSON 对象 key 必须是字符串")
        entries = (
            f"{_canonical_json_text(key)}:{_canonical_json_text(value[key])}"
            for key in sorted(value)
        )
        return "{" + ",".join(entries) + "}"
    raise TypeError(f"执行哈希不支持类型：{type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    """按 `inkforge-canonical-json/1` 生成跨语言稳定字节。"""

    return _canonical_json_text(value).encode("utf-8")


def canonical_content_sha256(value: object) -> str:
    return _sha256(canonical_json_bytes(value))


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


_IGNORED_CHAPTER_CHARACTERS = frozenset(
    chr(codepoint)
    for codepoint in (
        *range(0x0009, 0x000E),
        0x0020,
        0x0085,
        0x00A0,
        0x1680,
        *range(0x2000, 0x200B),
        0x2028,
        0x2029,
        0x202F,
        0x205F,
        0x3000,
        0xFEFF,
    )
)


def count_chapter_text_length(content: str) -> int:
    """严格对齐 Web countTextLength/Core TextLength，不使用更宽泛的 Python 空白集。"""

    return sum(character not in _IGNORED_CHAPTER_CHARACTERS for character in content)
