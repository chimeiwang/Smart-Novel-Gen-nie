from __future__ import annotations

from typing import Any


def apply_text_patches(content: str, patches: list[dict[str, Any]]) -> str:
    result = content
    for patch in patches:
        if patch.get("kind") != "text_replace":
            raise ValueError("当前只支持安全文本替换补丁")
        find = patch.get("find")
        replace = patch.get("replace")
        if not isinstance(find, str) or not find or not isinstance(replace, str):
            raise ValueError("文本替换补丁字段无效")
        if result.count(find) != 1:
            raise ValueError("补丁目标必须在草案中唯一命中")
        result = result.replace(find, replace, 1)
    return result
