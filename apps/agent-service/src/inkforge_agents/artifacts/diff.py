from __future__ import annotations

from difflib import unified_diff


def create_text_diff(before: str, after: str) -> str:
    return "".join(
        unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="修改前",
            tofile="修改后",
        )
    )
