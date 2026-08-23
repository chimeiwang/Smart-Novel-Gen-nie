"""视频场景来源绑定和创建幂等测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from inkforge_contracts.video import LongSerialSettingSnapshot, VideoPlanJobPayload
from inkforge_core.db.models import Chapter, VideoGenerationTask, VideoProject
from inkforge_core.errors import ApiError
from inkforge_core.video.repository import (
    _utf16_offset_to_codepoint_index,
    _validate_create_replay_payload,
    _validated_chapter_selection,
)
from inkforge_core.video.schemas import ApproveVideoSceneRequest, CreateVideoSceneRequest
from pydantic import ValidationError

_UPDATED_AT = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)


def _request(**changes: object) -> CreateVideoSceneRequest:
    values: dict[str, object] = {
        "clientRequestId": "0123456789abcdef",
        "chapterId": "chapter-1",
        "title": "雨夜异响",
        "expectedChapterUpdatedAt": _UPDATED_AT,
        "selectionStartUtf16": 1,
        "selectionEndUtf16": 4,
        "selectedText": "😀乙",
        "durationSeconds": 15,
    }
    values.update(changes)
    return CreateVideoSceneRequest.model_validate(values)


def _chapter() -> Chapter:
    return Chapter(
        id="chapter-1",
        novelId="novel-1",
        title="第一章",
        content="甲😀乙丙",
        updatedAt=_UPDATED_AT.replace(tzinfo=None),
    )


def test_utf16_offsets_convert_to_codepoints_and_reject_half_surrogate() -> None:
    value = "甲😀乙"

    assert _utf16_offset_to_codepoint_index(value, 0) == 0
    assert _utf16_offset_to_codepoint_index(value, 1) == 1
    assert _utf16_offset_to_codepoint_index(value, 3) == 2
    assert _utf16_offset_to_codepoint_index(value, 4) == 3
    with pytest.raises(ValueError, match="代理对"):
        _utf16_offset_to_codepoint_index(value, 2)
    with pytest.raises(ValueError, match="超出"):
        _utf16_offset_to_codepoint_index(value, 5)


def test_core_rederives_exact_selection_from_locked_chapter() -> None:
    selected = _validated_chapter_selection(_chapter(), _request())

    assert selected == "😀乙"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"expectedChapterUpdatedAt": _UPDATED_AT + timedelta(seconds=1)}, "已经变化"),
        ({"selectedText": "😀丙"}, "不一致"),
        ({"selectionStartUtf16": 2}, "已经失效"),
        ({"selectionEndUtf16": 99}, "已经失效"),
    ],
)
def test_core_rejects_stale_tampered_or_invalid_selection(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ApiError) as caught:
        _validated_chapter_selection(_chapter(), _request(**changes))

    assert caught.value.status_code == 409
    assert caught.value.code == "VIDEO_SOURCE_CHANGED"
    assert message in caught.value.message


def test_create_request_rejects_empty_or_reversed_range() -> None:
    with pytest.raises(ValidationError, match="selectionEndUtf16"):
        _request(selectionStartUtf16=4, selectionEndUtf16=4, selectedText="乙")
    with pytest.raises(ValidationError):
        _request(selectedText="甲" * 2_001, selectionEndUtf16=2_002)


def test_approve_request_requires_stable_id_and_positive_revision() -> None:
    request = ApproveVideoSceneRequest(
        clientRequestId=" 0123456789abcdef ",
        expectedArtifactRevision=2,
    )

    assert request.clientRequestId == "0123456789abcdef"
    with pytest.raises(ValidationError):
        ApproveVideoSceneRequest(
            clientRequestId="too-short",
            expectedArtifactRevision=2,
        )
    with pytest.raises(ValidationError):
        ApproveVideoSceneRequest(
            clientRequestId="0123456789abcdef",
            expectedArtifactRevision=0,
        )


def test_scene_create_idempotency_replay_requires_same_frozen_input() -> None:
    project = VideoProject(
        id="project-1",
        novelId="novel-1",
        title="项目",
        targetAspectRatio="16:9",
    )
    payload = VideoPlanJobPayload(
        projectId=project.id,
        sceneId="scene-1",
        chapterId="chapter-1",
        title="雨夜异响",
        sourceText="😀乙",
        durationSeconds=15,
        ratio="16:9",
        settingSnapshot=LongSerialSettingSnapshot.from_entries([]),
    )
    task = VideoGenerationTask(
        id="task-1",
        projectId=project.id,
        sceneId=payload.sceneId,
        kind="plan",
        requestJson=payload.model_dump_json(),
    )

    assert _validate_create_replay_payload(task, project, _request()) == payload
    with pytest.raises(ApiError) as caught:
        _validate_create_replay_payload(
            task,
            project,
            _request(selectedText="😀丙"),
        )
    assert caught.value.code == "VIDEO_SCENE_IDEMPOTENCY_CONFLICT"
