from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class TextReplacePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["text_replace"]
    find: str = Field(min_length=1)
    replace: str


class PatchApplicationError(ValueError):
    """局部 patch 无法安全应用时返回的脱敏错误。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _validate_patch(raw_patch: TextReplacePatch | Mapping[str, object]) -> TextReplacePatch:
    try:
        return (
            raw_patch
            if isinstance(raw_patch, TextReplacePatch)
            else TextReplacePatch.model_validate(raw_patch)
        )
    except (ValidationError, TypeError, ValueError) as exc:
        raise PatchApplicationError("PATCH_ARTIFACT_UNSUPPORTED") from exc


def _find_all(content: str, target: str) -> list[int]:
    starts: list[int] = []
    start = content.find(target)
    while start != -1:
        starts.append(start)
        # 步进一个字符，确保重叠命中也不会被漏掉。
        start = content.find(target, start + 1)
    return starts


def apply_text_patches(
    content: str,
    patches: Sequence[TextReplacePatch | Mapping[str, object]],
) -> str:
    """在原正文上原子、确定性地应用文本替换 patch。"""

    located: list[tuple[int, int, TextReplacePatch]] = []
    for raw_patch in patches:
        patch = _validate_patch(raw_patch)
        matches = _find_all(content, patch.find)
        if not matches:
            raise PatchApplicationError("PATCH_TARGET_NOT_FOUND")
        if len(matches) != 1:
            raise PatchApplicationError("PATCH_TARGET_AMBIGUOUS")
        start = matches[0]
        located.append((start, start + len(patch.find), patch))

    ordered = sorted(located, key=lambda item: item[0])
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current[0] < previous[1]:
            raise PatchApplicationError("PATCH_OVERLAP")

    result = content
    for start, end, patch in reversed(ordered):
        result = result[:start] + patch.replace + result[end:]
    return result
