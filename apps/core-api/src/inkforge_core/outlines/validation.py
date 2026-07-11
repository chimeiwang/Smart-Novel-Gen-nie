from __future__ import annotations

from dataclasses import dataclass

from ..errors import ApiError

_PARENT_KIND: dict[str, str | None] = {
    "stage": None,
    "plot_unit": "stage",
    "chapter_group": "plot_unit",
}


@dataclass(frozen=True, slots=True)
class OutlineNodeSnapshot:
    id: str
    kind: str
    parent_id: str | None
    start: int | None
    end: int | None


def validate_outline_node(
    candidate: OutlineNodeSnapshot,
    existing: list[OutlineNodeSnapshot],
    *,
    title: str,
) -> None:
    """验证单个节点在小说完整节点快照中的结构和闭区间规则。"""

    if not title.strip():
        raise _invalid("OUTLINE_TITLE_REQUIRED", "大纲节点标题不能为空")
    if candidate.kind not in _PARENT_KIND:
        raise _invalid("OUTLINE_KIND_INVALID", "大纲节点类型无效")
    if (candidate.start is None) != (candidate.end is None):
        raise _invalid("OUTLINE_RANGE_PAIR_REQUIRED", "章节范围必须同时提供起止序号")
    if candidate.start is not None and candidate.end is not None:
        if candidate.start <= 0 or candidate.end <= 0 or candidate.start > candidate.end:
            raise _invalid("OUTLINE_RANGE_INVALID", "章节范围必须为有效正整数闭区间")

    by_id = {item.id: item for item in existing if item.id != candidate.id}
    required_parent_kind = _PARENT_KIND[candidate.kind]
    if required_parent_kind is None:
        if candidate.parent_id is not None:
            raise _invalid("OUTLINE_PARENT_KIND_INVALID", "阶段节点必须位于顶层")
    elif candidate.parent_id is None:
        raise _invalid("OUTLINE_PARENT_REQUIRED", "该大纲节点必须指定父节点")
    else:
        parent = by_id.get(candidate.parent_id)
        if parent is None:
            raise _invalid("OUTLINE_PARENT_NOT_FOUND", "父大纲节点不存在")
        if parent.kind != required_parent_kind:
            raise _invalid("OUTLINE_PARENT_KIND_INVALID", "父子大纲节点类型不兼容")
        if not _contains(parent, candidate):
            raise _invalid("OUTLINE_RANGE_OUTSIDE_PARENT", "子节点章节范围必须位于父节点内")

    children = [item for item in existing if item.parent_id == candidate.id]
    expected_child_kind = next(
        (kind for kind, parent_kind in _PARENT_KIND.items() if parent_kind == candidate.kind), None
    )
    if any(child.kind != expected_child_kind for child in children):
        raise _invalid("OUTLINE_CHILD_KIND_INVALID", "修改后子节点类型将与父节点不兼容")
    if any(not _contains(candidate, child) for child in children):
        raise _invalid("OUTLINE_CHILD_RANGE_OUTSIDE_PARENT", "修改后的章节范围不能排除现有子节点")

    for sibling in existing:
        if sibling.id == candidate.id or sibling.parent_id != candidate.parent_id:
            continue
        if _overlaps(candidate, sibling):
            raise _invalid("OUTLINE_RANGE_OVERLAP", "同级大纲节点章节范围不能重叠")


def _contains(parent: OutlineNodeSnapshot, child: OutlineNodeSnapshot) -> bool:
    if child.start is None and child.end is None:
        return True
    if parent.start is None or parent.end is None or child.start is None or child.end is None:
        return False
    return parent.start <= child.start and child.end <= parent.end


def _overlaps(left: OutlineNodeSnapshot, right: OutlineNodeSnapshot) -> bool:
    if left.start is None or left.end is None or right.start is None or right.end is None:
        return False
    return left.start <= right.end and right.start <= left.end


def _invalid(code: str, message: str) -> ApiError:
    return ApiError(status_code=422, code=code, message=message)
