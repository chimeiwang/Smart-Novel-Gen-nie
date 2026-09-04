import re

_NON_BLANK = re.compile(
    r"[^\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a"
    r"\u2028\u2029\u202f\u205f\u3000\ufeff]"
)


def has_complete_text(value: object) -> bool:
    """只校验统一 Unicode 空白，不改写完整输入。"""
    return isinstance(value, str) and _NON_BLANK.search(value) is not None
