from __future__ import annotations

from copy import deepcopy
from typing import Any


class ArtifactPatchError(ValueError):
    """表示复审补丁无法安全、唯一地应用。"""


def apply_text_replace_patch(payload: dict[str, Any], find: str, replace: str) -> dict[str, Any]:
    if not find:
        raise ArtifactPatchError("文本补丁查找内容不能为空")
    target_field = "markdown" if payload.get("kind") == "freeform_markdown" else "content"
    content = payload.get(target_field)
    if not isinstance(content, str):
        raise ArtifactPatchError(f"text_replace 不支持 {payload.get('kind')} 草案")
    count = content.count(find)
    if count != 1:
        raise ArtifactPatchError(f"text_replace 需要唯一匹配，实际匹配 {count} 次")
    result = deepcopy(payload)
    result[target_field] = content.replace(find, replace, 1)
    return result
