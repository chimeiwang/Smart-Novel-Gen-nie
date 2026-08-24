"""逐镜渲染清单必须兼容 P0 历史，并冻结 P1 关键帧供应商文本。"""

from __future__ import annotations

import pytest
from inkforge_contracts.video_render import (
    ShotRenderKeyframeManifest,
    VideoShotRenderManifest,
)
from pydantic import ValidationError


def _base() -> dict[str, object]:
    return {
        "adaptationId": "adaptation-1",
        "projectId": "project-1",
        "novelId": "novel-1",
        "shotId": "shot-1",
        "shotKey": "S01",
        "shotPlanVersionId": "plan-1",
        "promptVersionId": "prompt-1",
        "promptContentHash": "a" * 64,
        "promptText": "正式逐镜提示词",
        "sourceTimelineDurationMs": 5_000,
        "model": "doubao-seedance-2-5",
        "ratio": "9:16",
        "durationSeconds": 5,
    }


def test_p0_manifest_remains_readable() -> None:
    manifest = VideoShotRenderManifest(
        schemaVersion="video-shot-render-manifest/1.0",
        **_base(),
    )

    assert manifest.providerPromptText is None
    assert manifest.keyframes == []


def test_p1_keyframe_requires_frozen_provider_prompt() -> None:
    frame = ShotRenderKeyframeManifest(
        ordinal=1,
        keyframeVersionId="frame-v1",
        role="initial_state",
        assetId="asset-1",
        sha256="b" * 64,
        mimeType="image/png",
        duty="keyframe",
    )
    with pytest.raises(ValidationError, match="providerPromptText"):
        VideoShotRenderManifest(**_base(), keyframes=[frame])

    manifest = VideoShotRenderManifest(
        **_base(),
        providerPromptText="图片1严格作为首帧。\n正式逐镜提示词",
        keyframes=[frame],
    )
    assert manifest.schemaVersion == "video-shot-render-manifest/1.1"
