"""画像来源只冻结完整原文与元数据；输出不提前执行 Core 的 strip 投影。"""

import hashlib

import pytest
from inkforge_contracts.style_execution import (
    StylePortraitContextV2,
    StylePortraitReference,
    StylePortraitSectionOutput,
    StylePortraitStepInput,
)
from pydantic import ValidationError


def source_context():
    content = " \ufeff完整😀\r\n "
    source = f"参考资料：全部.txt\n\n{content}"
    return {
        "styleId": "style-1",
        "mode": "full",
        "section": None,
        "references": [
            {
                "referenceId": "reference-1",
                "filename": "全部.txt",
                "charCount": 4,
                "content": content,
                "contentSha256": hashlib.sha256(content.encode()).hexdigest(),
            }
        ],
        "originalCharCount": 4,
        "sourceTextSha256": hashlib.sha256(source.encode()).hexdigest(),
    }


@pytest.mark.parametrize(
    ("model", "fields"),
    [
        (
            StylePortraitContextV2,
            {"styleId", "mode", "section", "references", "originalCharCount", "sourceTextSha256"},
        ),
        (
            StylePortraitReference,
            {"referenceId", "filename", "charCount", "content", "contentSha256"},
        ),
        (StylePortraitStepInput, {"section"}),
        (StylePortraitSectionOutput, {"content"}),
    ],
)
def test_portrait_schema_is_exact_closed_and_all_fields_required(model, fields):
    schema = model.model_json_schema()
    assert set(schema["required"]) == set(schema["properties"]) == fields
    assert schema["additionalProperties"] is False
    for key in ("content", "filename"):
        if key in fields:
            assert "maxLength" not in schema["properties"][key]


def test_context_serializes_explicit_null_and_keeps_complete_source():
    source = source_context()
    context = StylePortraitContextV2.model_validate(source)
    assert context.model_dump() == source
    assert '"section":null' in context.model_dump_json()
    assert context.source_text == "参考资料：全部.txt\n\n \ufeff完整😀\r\n "
    assert context.originalCharCount == 4
    assert "maxItems" not in context.model_json_schema()["properties"]["references"]


@pytest.mark.parametrize(
    "changes",
    [
        {"mode": "section"},
        {"section": "styleTraits"},
        {"section": "不支持的节"},
        {"originalCharCount": "4"},
        {"originalCharCount": True},
        {"originalCharCount": -1},
        {"originalCharCount": 5},
        {"sourceTextSha256": "0" * 64},
        {"references": []},
        {"sourceText": "不能保存第二份拼接正文"},
        {"userInstruction": "不能增加画像指令"},
    ],
)
def test_context_rejects_wrong_mode_count_hash_or_extra_source(changes):
    with pytest.raises(ValidationError):
        StylePortraitContextV2.model_validate(source_context() | changes)


def test_full_mode_section_is_required_nullable_and_single_mode_is_exact():
    missing = source_context()
    del missing["section"]
    with pytest.raises(ValidationError):
        StylePortraitContextV2.model_validate(missing)
    single = source_context() | {"mode": "section", "section": "generationStyle"}
    assert StylePortraitContextV2.model_validate(single).section == "generationStyle"


@pytest.mark.parametrize(
    "changes",
    [
        {"filename": ""},
        {"content": ""},
        {"content": "被改写的原文"},
        {"contentSha256": "0" * 64},
        {"charCount": "4"},
        {"charCount": True},
        {"charCount": -1},
        {"storagePath": "不可冻结本机路径"},
    ],
)
def test_reference_requires_complete_hashed_original_and_strict_metadata(changes):
    with pytest.raises(ValidationError):
        StylePortraitReference.model_validate(source_context()["references"][0] | changes)


def test_metadata_count_is_not_replaced_by_length_of_text_or_wrapper():
    reference = source_context()["references"][0]
    assert StylePortraitReference.model_validate(reference | {"charCount": 100}).charCount == 100
    duplicate = source_context()
    duplicate["references"] *= 2
    duplicate["originalCharCount"] *= 2
    with pytest.raises(ValidationError, match="重复引用"):
        StylePortraitContextV2.model_validate(duplicate)


@pytest.mark.parametrize("content", ["\ufeff", " \ufeff \n", " 原始😀\r\n "])
def test_output_preserves_bom_and_all_original_whitespace(content):
    assert StylePortraitSectionOutput(content=content).content == content


@pytest.mark.parametrize("content", ["", " \t\r\n\u0085\u3000", None, 3, False])
def test_output_rejects_only_wrong_type_or_old_python_strip_empty(content):
    with pytest.raises(ValidationError):
        StylePortraitSectionOutput(content=content)


def test_step_input_accepts_only_one_known_section():
    assert StylePortraitStepInput(section="styleTraits").model_dump() == {"section": "styleTraits"}
    for value in (
        {},
        {"section": None},
        {"section": "unknown"},
        {"section": "styleTraits", "previous": "旧节"},
    ):
        with pytest.raises(ValidationError):
            StylePortraitStepInput.model_validate(value)
