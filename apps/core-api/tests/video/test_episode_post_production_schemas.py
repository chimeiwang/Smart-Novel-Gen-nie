"""独立剧集基础后期公共契约的边界测试。"""

from __future__ import annotations

import pytest
from inkforge_core.video.episodes.post_production_schemas import (
    CreateVideoEpisodeEditVersionRequest,
    CreateVideoEpisodeMixVersionRequest,
    VideoEpisodeEditClipInput,
)
from pydantic import ValidationError


def _clip(*, temp_key: str = "clip-a", source_audio_mode: str = "keep") -> dict[str, object]:
    return {
        "tempKey": temp_key,
        "adoptionId": "adoption-a",
        "takeId": "take-a",
        "sourceInMs": 0,
        "sourceOutMs": 4_000,
        "sourceAudioMode": source_audio_mode,
        "transitionAfter": "cut",
        "transitionDurationMs": 0,
    }


def test_edit_allows_reusing_one_take_as_two_independent_clips() -> None:
    request = CreateVideoEpisodeEditVersionRequest.model_validate(
        {
            "clientRequestId": "edit-request-0001",
            "expectedHeadRevision": 1,
            "clips": [
                _clip(temp_key="clip-a"),
                {
                    **_clip(temp_key="clip-b", source_audio_mode="mute"),
                    "sourceInMs": 4_000,
                    "sourceOutMs": 8_000,
                },
            ],
            "omissions": [{"shotVersionId": "shot-version-b", "reason": "节奏调整"}],
        }
    )

    assert [clip.tempKey for clip in request.clips] == ["clip-a", "clip-b"]
    assert [clip.sourceAudioMode for clip in request.clips] == ["keep", "mute"]


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"sourceOutMs": 400}, "500"),
        ({"transitionAfter": "cut", "transitionDurationMs": 100}, "硬切"),
        ({"transitionAfter": "fade_black", "transitionDurationMs": 0}, "淡黑"),
        ({"sourceAudioMode": "auto"}, "Input should be 'keep' or 'mute'"),
    ],
)
def test_edit_clip_rejects_ambiguous_or_invalid_timeline_facts(
    patch: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        VideoEpisodeEditClipInput.model_validate({**_clip(), **patch})


def test_edit_rejects_duplicate_clip_and_omission_identities() -> None:
    with pytest.raises(ValidationError, match="粗剪片段临时身份不能重复"):
        CreateVideoEpisodeEditVersionRequest.model_validate(
            {
                "clientRequestId": "edit-request-0002",
                "expectedHeadRevision": 1,
                "clips": [_clip(), _clip()],
            }
        )
    with pytest.raises(ValidationError, match="同一镜头版本不能重复省略"):
        CreateVideoEpisodeEditVersionRequest.model_validate(
            {
                "clientRequestId": "edit-request-0003",
                "expectedHeadRevision": 1,
                "clips": [_clip()],
                "omissions": [
                    {"shotVersionId": "shot-version-b", "reason": "删镜一"},
                    {"shotVersionId": "shot-version-b", "reason": "删镜二"},
                ],
            }
        )


def test_mix_rejects_invalid_audio_fades_and_subtitle_ranges() -> None:
    base = {
        "clientRequestId": "mix-request-00001",
        "expectedHeadRevision": 1,
        "editVersionId": "edit-version-a",
    }
    with pytest.raises(ValidationError, match="淡入淡出总时长"):
        CreateVideoEpisodeMixVersionRequest.model_validate(
            {
                **base,
                "audioClips": [
                    {
                        "trackKind": "music",
                        "assetId": "audio-a",
                        "timelineStartMs": 0,
                        "sourceInMs": 0,
                        "sourceOutMs": 1_000,
                        "fadeInMs": 600,
                        "fadeOutMs": 600,
                    }
                ],
            }
        )
    with pytest.raises(ValidationError, match="endMs 必须大于 startMs"):
        CreateVideoEpisodeMixVersionRequest.model_validate(
            {
                **base,
                "subtitleCues": [
                    {
                        "shotVersionId": "shot-version-a",
                        "scriptLineId": "line-a",
                        "startMs": 1_000,
                        "endMs": 1_000,
                        "text": "顾舟接过信。",
                    }
                ],
            }
        )
