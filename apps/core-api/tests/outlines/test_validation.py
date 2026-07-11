from __future__ import annotations

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.outlines.validation import OutlineNodeSnapshot, validate_outline_node


def node(
    id: str,
    kind: str,
    parent_id: str | None,
    start: int | None,
    end: int | None,
) -> OutlineNodeSnapshot:
    return OutlineNodeSnapshot(id=id, kind=kind, parent_id=parent_id, start=start, end=end)


def test_accepts_exact_three_level_hierarchy_and_contained_ranges() -> None:
    existing = [
        node("stage", "stage", None, 1, 20),
        node("unit", "plot_unit", "stage", 2, 10),
    ]
    validate_outline_node(
        node("group", "chapter_group", "unit", 3, 5), existing, title="  第一幕  "
    )


@pytest.mark.parametrize(
    ("candidate", "code"),
    [
        (node("x", "stage", "stage", 1, 2), "OUTLINE_PARENT_KIND_INVALID"),
        (node("x", "plot_unit", None, 1, 2), "OUTLINE_PARENT_REQUIRED"),
        (node("x", "chapter_group", "stage", 1, 2), "OUTLINE_PARENT_KIND_INVALID"),
        (node("x", "stage", None, 2, None), "OUTLINE_RANGE_PAIR_REQUIRED"),
        (node("x", "stage", None, 0, 2), "OUTLINE_RANGE_INVALID"),
        (node("x", "stage", None, 3, 2), "OUTLINE_RANGE_INVALID"),
    ],
)
def test_rejects_invalid_hierarchy_and_ranges(candidate: OutlineNodeSnapshot, code: str) -> None:
    existing = [node("stage", "stage", None, 1, 20)]
    with pytest.raises(ApiError) as caught:
        validate_outline_node(candidate, existing, title="标题")
    assert caught.value.code == code


def test_rejects_closed_interval_overlap_and_parent_shrink() -> None:
    existing = [
        node("stage", "stage", None, 1, 20),
        node("a", "plot_unit", "stage", 2, 5),
        node("b", "plot_unit", "stage", 6, 10),
    ]
    with pytest.raises(ApiError) as overlap:
        validate_outline_node(node("new", "plot_unit", "stage", 5, 6), existing, title="标题")
    assert overlap.value.code == "OUTLINE_RANGE_OVERLAP"

    with pytest.raises(ApiError) as shrink:
        validate_outline_node(node("stage", "stage", None, 1, 4), existing, title="标题")
    assert shrink.value.code == "OUTLINE_CHILD_RANGE_OUTSIDE_PARENT"


def test_rejects_kind_change_that_orphans_children_and_blank_title() -> None:
    existing = [
        node("stage", "stage", None, 1, 20),
        node("unit", "plot_unit", "stage", 2, 10),
    ]
    with pytest.raises(ApiError) as kind_error:
        validate_outline_node(node("stage", "plot_unit", None, 1, 20), existing, title="标题")
    assert kind_error.value.code in {"OUTLINE_PARENT_REQUIRED", "OUTLINE_CHILD_KIND_INVALID"}

    with pytest.raises(ApiError) as title_error:
        validate_outline_node(node("new", "stage", None, None, None), existing, title=" \n ")
    assert title_error.value.code == "OUTLINE_TITLE_REQUIRED"
