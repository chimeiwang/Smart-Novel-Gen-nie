from __future__ import annotations

import hashlib

import pytest
from inkforge_contracts import (
    ShortMediumGenerationSummary,
    ShortMediumWritingPlan,
    short_medium_writing_plan_sha256,
)
from inkforge_contracts.short_medium import (
    ShortMediumCheckResult,
    ShortMediumDocumentResult,
    ShortMediumReplacementResult,
    ShortMediumRunPayload,
)
from pydantic import ValidationError


def _writing_plan() -> ShortMediumWritingPlan:
    return ShortMediumWritingPlan(
        version="1",
        targetTotalWordCount=20_000,
        scenes=[
            {"sceneId": "scene-1", "title": "开端", "summary": "主角发现异常。"},
            {"sceneId": "scene-2", "title": "对抗", "summary": "主角正面迎战。"},
            {"sceneId": "scene-3", "title": "结局", "summary": "冲突得到解决。"},
        ],
        writingUnits=[
            {
                "unitId": "unit-1",
                "order": 1,
                "title": "建立冲突",
                "sceneIds": ["scene-1", "scene-2"],
                "entryState": "主角尚未察觉危机。",
                "requiredEvents": ["发现异常", "决定迎战"],
                "exitState": "主角已经进入正面对抗。",
                "targetWordCount": 10_000,
            },
            {
                "unitId": "unit-2",
                "order": 2,
                "title": "解决冲突",
                "sceneIds": ["scene-3"],
                "entryState": "主角正在正面对抗。",
                "requiredEvents": ["完成最终选择"],
                "exitState": "核心冲突已经解决。",
                "targetWordCount": 10_000,
            },
        ],
    )


def _outline_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _writing_plan_hash(content: str, plan: ShortMediumWritingPlan) -> str:
    return short_medium_writing_plan_sha256(_outline_hash(content), plan)


@pytest.mark.parametrize("field", ["scenes", "writingUnits"])
def test_writing_plan_rejects_duplicate_scene_or_unit_identity(field: str) -> None:
    data = _writing_plan().model_dump()
    if field == "scenes":
        data["scenes"].append(
            {"sceneId": "scene-1", "title": "重复场景", "summary": "重复。"}
        )
    else:
        duplicate_unit = data["writingUnits"][1].copy()
        duplicate_unit["unitId"] = "unit-1"
        duplicate_unit["order"] = 3
        data["writingUnits"].append(duplicate_unit)

    with pytest.raises(ValidationError):
        ShortMediumWritingPlan.model_validate(data)


@pytest.mark.parametrize(
    "unit_scene_ids",
    [
        [["scene-1"], ["scene-3"]],
        [["scene-1", "scene-2"], ["scene-2", "scene-3"]],
        [["scene-2", "scene-3"], ["scene-1"]],
    ],
    ids=["missing", "duplicate", "crossed"],
)
def test_writing_plan_requires_each_scene_in_exactly_one_contiguous_unit(
    unit_scene_ids: list[list[str]],
) -> None:
    data = _writing_plan().model_dump()
    for unit, scene_ids in zip(data["writingUnits"], unit_scene_ids, strict=True):
        unit["sceneIds"] = scene_ids

    with pytest.raises(ValidationError):
        ShortMediumWritingPlan.model_validate(data)


def test_writing_plan_requires_continuous_unit_order() -> None:
    data = _writing_plan().model_dump()
    data["writingUnits"][1]["order"] = 3

    with pytest.raises(ValidationError):
        ShortMediumWritingPlan.model_validate(data)


@pytest.mark.parametrize("field", ["sceneIds", "requiredEvents"])
def test_writing_plan_rejects_empty_required_lists(field: str) -> None:
    data = _writing_plan().model_dump()
    data["writingUnits"][0][field] = []

    with pytest.raises(ValidationError):
        ShortMediumWritingPlan.model_validate(data)


@pytest.mark.parametrize("target_total_word_count", [5_999, 80_001])
def test_writing_plan_rejects_invalid_total_word_count(
    target_total_word_count: int,
) -> None:
    data = _writing_plan().model_dump()
    data["targetTotalWordCount"] = target_total_word_count

    with pytest.raises(ValidationError):
        ShortMediumWritingPlan.model_validate(data)


def test_writing_plan_hash_binds_outline_content_and_units() -> None:
    plan = _writing_plan()
    outline_hash = _outline_hash("故事蓝图")
    original = short_medium_writing_plan_sha256(outline_hash, plan)

    assert original == short_medium_writing_plan_sha256(outline_hash, plan)
    assert original != short_medium_writing_plan_sha256(_outline_hash("另一版蓝图"), plan)

    changed_plan = plan.model_copy(deep=True)
    changed_plan.writingUnits[0].requiredEvents.append("承担后果")
    assert original != short_medium_writing_plan_sha256(outline_hash, changed_plan)


def test_generate_manuscript_requires_source_outline_version() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="generate_manuscript",
            documentType="manuscript",
            chapterId="chapter-1",
            sourceOutlineVersionId=None,
        )


def test_generate_manuscript_keeps_immutable_outline_snapshot() -> None:
    outline = "蓝图原文"
    plan = _writing_plan()
    payload = ShortMediumRunPayload(
        workflow="short_medium",
        operation="generate_manuscript",
        documentType="manuscript",
        chapterId="chapter-1",
        sourceOutlineVersionId="outline-version-1",
        sourceOutlineContent=outline,
        sourceOutlineContentHash=hashlib.sha256(outline.encode("utf-8")).hexdigest(),
        targetTotalWordCount=20_000,
        writingPlan=plan,
        writingPlanHash=_writing_plan_hash(outline, plan),
    )

    assert payload.sourceOutlineContent == outline
    assert payload.writingPlan == plan


def test_generate_manuscript_requires_immutable_outline_snapshot() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="generate_manuscript",
            documentType="manuscript",
            chapterId="chapter-1",
            sourceOutlineVersionId="outline-version-1",
            sourceOutlineContent=None,
            sourceOutlineContentHash="a" * 64,
            targetTotalWordCount=20_000,
            writingPlan=_writing_plan(),
            writingPlanHash="a" * 64,
        )


def test_manuscript_payload_requires_frozen_plan() -> None:
    outline = "故事蓝图"

    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="generate_manuscript",
            documentType="manuscript",
            chapterId="chapter-1",
            sourceOutlineVersionId="outline-version-1",
            sourceOutlineContent=outline,
            sourceOutlineContentHash=_outline_hash(outline),
            targetTotalWordCount=20_000,
        )


def test_manuscript_payload_rejects_tampered_plan_hash() -> None:
    outline = "故事蓝图"

    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="generate_manuscript",
            documentType="manuscript",
            chapterId="chapter-1",
            sourceOutlineVersionId="outline-version-1",
            sourceOutlineContent=outline,
            sourceOutlineContentHash=_outline_hash(outline),
            targetTotalWordCount=20_000,
            writingPlan=_writing_plan(),
            writingPlanHash="a" * 64,
        )


def test_non_manuscript_operation_rejects_writing_plan_identity() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="generate_outline",
            documentType="outline",
            sourceKind="idea",
            sourceText="一个悬疑故事",
            writingPlan=_writing_plan(),
            writingPlanHash="a" * 64,
        )


def test_replace_selection_requires_complete_selection_identity() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="replace_selection",
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId="version-1",
            baseContentHash="a" * 64,
            selectionStart=2,
            selectionEnd=5,
            selectedText="冲突",
            selectedTextHash="b" * 64,
            contextBefore=None,
            contextAfter="之后",
            userInstruction="加强冲突",
        )


def test_replace_selection_requires_original_selected_text() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="replace_selection",
            documentType="outline",
            baseVersionId="version-1",
            baseContentHash="a" * 64,
            selectionStart=2,
            selectionEnd=5,
            selectedText=None,
            selectedTextHash="b" * 64,
            userInstruction="加强冲突",
        )


def test_replace_selection_rejects_empty_or_reversed_codepoint_range() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="replace_selection",
            documentType="outline",
            baseVersionId="version-1",
            baseContentHash="a" * 64,
            selectionStart=5,
            selectionEnd=5,
            selectedText="冲突",
            selectedTextHash="b" * 64,
            userInstruction="改得更紧凑",
        )


def test_full_check_requires_manuscript_version() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="full_check",
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=None,
        )


def test_full_check_requires_immutable_manuscript_snapshot() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="full_check",
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId="manuscript-version-1",
            baseContent=None,
            baseContentHash="a" * 64,
        )


def test_outline_generation_requires_authoritative_source() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="generate_outline",
            documentType="outline",
            sourceKind="idea",
            sourceText=None,
        )


def test_operation_rejects_fields_owned_by_another_operation() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="generate_outline",
            documentType="outline",
            selectionStart=0,
        )


def test_document_result_matches_generation_operation_and_document() -> None:
    summary = ShortMediumGenerationSummary(
        targetWordCount=20_000,
        actualWordCount=19_000,
        toleranceLowerBound=14_000,
        toleranceUpperBound=26_000,
        lengthStatus="within_tolerance",
    )
    result = ShortMediumDocumentResult(
        resultType="short_medium_document",
        operation="generate_manuscript",
        documentType="manuscript",
        content="完整正文",
        sourceOutlineVersionId="outline-version-1",
        writingPlanHash="a" * 64,
        completedWritingUnitIds=["unit-1", "unit-2"],
        generationSummary=summary,
    )

    assert result.content == "完整正文"

    with pytest.raises(ValidationError):
        ShortMediumDocumentResult(
            resultType="short_medium_document",
            operation="generate_outline",
            documentType="manuscript",
            content="错误文档",
        )


def test_outline_result_requires_plan_and_hash_bound_to_content() -> None:
    content = "故事蓝图"
    plan = _writing_plan()

    with pytest.raises(ValidationError):
        ShortMediumDocumentResult(
            resultType="short_medium_document",
            operation="generate_outline",
            documentType="outline",
            content=content,
        )

    result = ShortMediumDocumentResult(
        resultType="short_medium_document",
        operation="generate_outline",
        documentType="outline",
        content=content,
        writingPlan=plan,
        writingPlanHash=_writing_plan_hash(content, plan),
    )
    assert result.writingPlan == plan

    with pytest.raises(ValidationError):
        ShortMediumDocumentResult(
            resultType="short_medium_document",
            operation="generate_outline",
            documentType="outline",
            content=content,
            writingPlan=plan,
            writingPlanHash="a" * 64,
        )


@pytest.mark.parametrize(
    "missing_field",
    ["writingPlanHash", "completedWritingUnitIds", "generationSummary"],
)
def test_manuscript_result_requires_plan_and_completed_unit_identity(
    missing_field: str,
) -> None:
    data = {
        "resultType": "short_medium_document",
        "operation": "generate_manuscript",
        "documentType": "manuscript",
        "content": "完整正文",
        "sourceOutlineVersionId": "outline-version-1",
        "writingPlanHash": "a" * 64,
        "completedWritingUnitIds": ["unit-1", "unit-2"],
        "generationSummary": {
            "targetWordCount": 20_000,
            "actualWordCount": 19_000,
            "toleranceLowerBound": 14_000,
            "toleranceUpperBound": 26_000,
            "lengthStatus": "within_tolerance",
        },
    }
    del data[missing_field]

    with pytest.raises(ValidationError):
        ShortMediumDocumentResult.model_validate(data)


def test_replacement_result_only_contains_replacement_text() -> None:
    selection_identity = {
        "baseVersionId": "version-1",
        "baseContentHash": "a" * 64,
        "selectionStart": 2,
        "selectionEnd": 5,
        "selectedTextHash": "b" * 64,
    }

    value = ShortMediumReplacementResult(
        resultType="short_medium_replacement",
        operation="replace_selection",
        documentType="manuscript",
        replacement="新文本",
        **selection_identity,
    )
    assert value.replacement == "新文本"

    with pytest.raises(ValidationError):
        ShortMediumReplacementResult(
            resultType="short_medium_replacement",
            operation="replace_selection",
            documentType="manuscript",
            replacement="新文本",
            content="不允许携带完整正文",
            **selection_identity,
        )


def test_check_result_is_bound_to_manuscript_version() -> None:
    result = ShortMediumCheckResult(
        resultType="short_medium_check",
        operation="full_check",
        documentType="manuscript",
        baseVersionId="manuscript-version-1",
        report={"summary": "结尾已兑现开篇承诺", "issues": []},
    )

    assert result.baseVersionId == "manuscript-version-1"
