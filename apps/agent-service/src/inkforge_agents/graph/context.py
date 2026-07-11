from __future__ import annotations

import json
import re
from typing import Any, Literal

from ..operations.definitions import OperationDefinition


def build_operation_context(
    definition: OperationDefinition,
    source: dict[str, Any],
) -> list[str]:
    return [
        (
            f"当前创作操作：{definition.label}\n"
            f"执行要求：{definition.executionBrief}\n\n"
            "当前操作上下文：\n" + json.dumps(source, ensure_ascii=False, indent=2)
        ),
    ]


def parse_chapter_target(
    message: str,
) -> Literal["current_chapter", "next_chapter"] | None:
    if re.search(r"本章|当前章|这一章|这章|当前段落|这一段|这段", message):
        return "current_chapter"
    if re.search(r"下一章|下章|新一章", message):
        return "next_chapter"
    return None
