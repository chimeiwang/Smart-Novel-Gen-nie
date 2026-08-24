"""P1–P3 公共请求必须在进入数据库前拒绝不完整时间决定。"""

from __future__ import annotations

import pytest
from inkforge_core.video.adaptation.post_production_schemas import (
    EpisodeAudioClipInput,
    EpisodeEditClipInput,
    EpisodeSubtitleCueInput,
    SaveShotKeyframeVersionRequest,
)
from pydantic import ValidationError


def test_keyframe_clear_cannot_carry_take_source() -> None:
    with pytest.raises(ValidationError, match="清除关键帧"):
        SaveShotKeyframeVersionRequest(
            clientRequestId="0123456789abcdef",
            expectedRevision=1,
            role="initial_state",
            assetId=None,
            sourceTakeId="take-1",
            sourceTimeMs=100,
        )


def test_real_take_clip_requires_complete_trim_and_matching_transition() -> None:
    with pytest.raises(ValidationError, match="源入点和出点"):
        EpisodeEditClipInput(
            shotId="shot-1",
            takeId="take-1",
            sourceInMs=None,
            sourceOutMs=None,
            outputDurationMs=1_000,
        )
    with pytest.raises(ValidationError, match="硬切"):
        EpisodeEditClipInput(
            shotId="shot-1",
            takeId="take-1",
            sourceInMs=0,
            sourceOutMs=1_000,
            outputDurationMs=1_000,
            transitionAfter="cut",
            transitionDurationMs=100,
        )


def test_audio_fades_and_subtitle_ranges_cannot_exceed_clip() -> None:
    with pytest.raises(ValidationError, match="淡入淡出"):
        EpisodeAudioClipInput(
            trackKind="music",
            assetId="audio-1",
            timelineStartMs=0,
            sourceInMs=0,
            sourceOutMs=1_000,
            fadeInMs=600,
            fadeOutMs=600,
        )
    with pytest.raises(ValidationError, match="endMs"):
        EpisodeSubtitleCueInput(
            startMs=1_000,
            endMs=1_000,
            text="完整字幕",
        )
