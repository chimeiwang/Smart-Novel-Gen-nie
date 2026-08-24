import pytest
from inkforge_agents.artifacts.patch import (
    PatchApplicationError,
    TextReplacePatch,
    apply_text_patches,
)
from pydantic import ValidationError


def patch(find: str, replace: str) -> TextReplacePatch:
    return TextReplacePatch(kind="text_replace", find=find, replace=replace)


def test_text_replace_patch_is_strict_and_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        TextReplacePatch(kind="text_replace", find="甲", replace=1)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        TextReplacePatch(kind="text_replace", find="甲", replace="乙", extra=True)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        TextReplacePatch(kind="text_replace", find="", replace="乙")


def test_apply_text_patches_uses_unique_original_positions_and_reverse_order() -> None:
    content = "甲乙丙甲丁"
    assert apply_text_patches(
        content,
        [patch("甲丁", "二"), patch("甲乙", "一")],
    ) == "一丙二"


def test_apply_text_patches_allows_empty_replacement() -> None:
    assert apply_text_patches("甲乙丙", [patch("乙", "")]) == "甲丙"


@pytest.mark.parametrize(
    ("content", "patches", "code"),
    [
        (
            "甲乙",
            [{"kind": "unknown", "find": "甲", "replace": "丙"}],
            "PATCH_ARTIFACT_UNSUPPORTED",
        ),
        ("甲乙", [patch("不存在", "丙")], "PATCH_TARGET_NOT_FOUND"),
        ("甲甲", [patch("甲", "乙")], "PATCH_TARGET_AMBIGUOUS"),
        ("甲乙丙", [patch("甲乙", "丁"), patch("乙丙", "戊")], "PATCH_OVERLAP"),
    ],
)
def test_apply_text_patches_rejects_invalid_targets_atomically(
    content: str, patches: list[TextReplacePatch], code: str
) -> None:
    with pytest.raises(PatchApplicationError) as exc_info:
        apply_text_patches(content, patches)
    assert exc_info.value.code == code
    assert str(exc_info.value).startswith(code)


def test_apply_text_patches_does_not_partially_modify_when_later_patch_fails() -> None:
    content = "甲乙丙"

    with pytest.raises(PatchApplicationError) as exc_info:
        apply_text_patches(content, [patch("甲", "已修改"), patch("不存在", "丙")])

    assert exc_info.value.code == "PATCH_TARGET_NOT_FOUND"
    assert content == "甲乙丙"


def test_patch_errors_do_not_leak_content_or_patch_values() -> None:
    source_text = "私密正文"
    target_text = "私密"
    replacement_text = "替换内容"

    with pytest.raises(PatchApplicationError) as exc_info:
        apply_text_patches(
            source_text,
            [
                {
                    "kind": "unsupported",
                    "find": target_text,
                    "replace": replacement_text,
                }
            ],
        )

    error = exc_info.value
    assert target_text not in str(error)
    assert target_text not in repr(error)
    assert replacement_text not in str(error)
    assert replacement_text not in repr(error)
    assert error.__cause__ is None
    assert error.__context__ is None
