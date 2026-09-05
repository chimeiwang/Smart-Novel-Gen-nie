"""中短篇 V2 冻结原文与单段输出契约。"""

import hashlib

import pytest
from inkforge_contracts.short_medium_execution import (
    ShortMediumContentOutput,
    ShortMediumContentResult,
    ShortMediumContextV2,
    ShortMediumPriorSegment,
    ShortMediumStepInput,
    materialize_short_medium_output,
)
from pydantic import ValidationError


def context(operation="generate_outline", *, target=15000):
    value = dict.fromkeys(ShortMediumContextV2.model_fields)
    value.update(
        workflow="short_medium",
        operation=operation,
        documentType="outline",
        targetTotalWordCount=target,
        sourceKind="idea",
        sourceText=" 完整素材\n",
    )
    if operation == "generate_manuscript":
        value.update(
            documentType="manuscript",
            chapterId="chapter-1",
            sourceOutlineVersionId="outline-1",
            sourceOutlineContent=" 蓝图\n",
            sourceOutlineContentHash=hashlib.sha256(" 蓝图\n".encode()).hexdigest(),
        )
    return value


def test_context_preserves_twenty_exact_fields_and_whitespace():
    source = context()
    assert len(source) == 20
    assert ShortMediumContextV2.model_validate(source).model_dump() == source
    source.pop("baseContent")
    with pytest.raises(ValidationError):
        ShortMediumContextV2.model_validate(source)


@pytest.mark.parametrize(("target", "count"), [(6000, 1), (15000, 1), (15001, 2), (80000, 6)])
def test_segment_count_is_core_frozen_target_ceiling(target, count):
    assert (
        ShortMediumContextV2.model_validate(
            context("generate_manuscript", target=target)
        ).segment_count
        == count
    )


@pytest.mark.parametrize(
    "value",
    [
        {"segmentIndex": True, "segmentCount": 1},
        {"segmentIndex": 1, "segmentCount": 1},
        {"segmentIndex": 0, "segmentCount": 7},
    ],
)
def test_invalid_segment_identity_rejected(value):
    with pytest.raises(ValidationError):
        ShortMediumStepInput.model_validate(value)


def test_result_hash_is_program_derived_from_full_utf8():
    content = " \n😀完整原文\n "
    output = materialize_short_medium_output("generate_manuscript", {"content": content})
    assert output == {
        "content": content,
        "contentSha256": hashlib.sha256(content.encode()).hexdigest(),
    }
    assert ShortMediumContentResult.model_validate(output).content == content
    assert ShortMediumContentOutput(content=" ").content == " "
    with pytest.raises(ValidationError):
        ShortMediumContentOutput(content="")
    with pytest.raises(ValidationError):
        ShortMediumContentOutput.model_validate(output)
    with pytest.raises(ValidationError):
        ShortMediumContentResult.model_validate({**output, "contentSha256": "0" * 64})
    assert ShortMediumPriorSegment.model_validate({"index": 0, **output}).content == content


def test_selection_reconstructs_full_unicode_base():
    source = context("replace_selection")
    text = "前😀后"
    source.update(
        baseVersionId="base-1",
        baseContent=text,
        baseContentHash=hashlib.sha256(text.encode()).hexdigest(),
        sourceKind=None,
        sourceText=None,
        selectionStart=1,
        selectionEnd=2,
        selectedText="😀",
        selectedTextHash=hashlib.sha256("😀".encode()).hexdigest(),
        contextBefore="前",
        contextAfter="后",
        userInstruction=" 修改 ",
    )
    assert ShortMediumContextV2.model_validate(source).selectedText == "😀"
    for field, value in [
        ("selectionEnd", 3),
        ("contextBefore", "错"),
        ("baseContentHash", "0" * 64),
    ]:
        with pytest.raises(ValidationError):
            ShortMediumContextV2.model_validate({**source, field: value})
