"""逐镜清单显式区分模拟和真实生成，并校验冻结参考图模式。"""

from __future__ import annotations

import pytest
from inkforge_contracts.video_render import (
    SeedanceRenderOutput,
    SeedanceRenderSubmitRequest,
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
        VideoShotRenderManifest(
            schemaVersion="video-shot-render-manifest/1.1", **_base(), keyframes=[frame]
        )

    manifest = VideoShotRenderManifest(
        **_base(),
        schemaVersion="video-shot-render-manifest/1.1",
        providerPromptText="图片1严格作为首帧。\n正式逐镜提示词",
        keyframes=[frame],
    )
    assert manifest.schemaVersion == "video-shot-render-manifest/1.1"


def _reference(ordinal: int = 1) -> dict[str, object]:
    return {
        "ordinal": ordinal,
        "canonVersionId": f"canon-v{ordinal}",
        "assetId": f"asset-{ordinal}",
        "sha256": "b" * 64,
        "mimeType": "image/png",
        "duty": "identity",
        "strength": 70,
    }


def _v12() -> dict[str, object]:
    return {
        **_base(),
        "generationMode": "reference",
        "executionMode": "simulated",
        "feeConfirmed": False,
        "references": [_reference()],
    }


def test_current_manifest_freezes_simulation_without_fake_fee_confirmation() -> None:
    manifest = VideoShotRenderManifest.model_validate(_v12())
    restored = VideoShotRenderManifest.model_validate_json(manifest.model_dump_json())

    assert restored.schemaVersion == "video-shot-render-manifest/1.2"
    assert restored.generationMode == "reference"
    assert restored.executionMode == "simulated"
    assert restored.feeConfirmed is False


@pytest.mark.parametrize("field", ["generationMode", "executionMode", "feeConfirmed"])
def test_current_manifest_rejects_unfrozen_execution_fields(field: str) -> None:
    payload = _v12()
    del payload[field]

    with pytest.raises(ValidationError):
        VideoShotRenderManifest.model_validate(payload)


@pytest.mark.parametrize(
    "changes",
    [
        {"generationMode": "auto"},
        {"generationMode": "edit"},
        {"generationMode": "extend"},
        {"durationSeconds": 3},
        {"durationSeconds": 13},
        {"resolution": "1080p"},
        {"references": []},
        {"references": [{**_reference(), "mimeType": "video/mp4"}]},
        {"executionMode": "live", "feeConfirmed": False},
        {"executionMode": "simulated", "feeConfirmed": True},
        {"feeConfirmed": "true"},
    ],
)
def test_current_manifest_rejects_invalid_reference_trials(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        VideoShotRenderManifest.model_validate({**_v12(), **changes})


def test_live_manifest_requires_explicit_fee_confirmation() -> None:
    manifest = VideoShotRenderManifest.model_validate(
        {**_v12(), "executionMode": "live", "feeConfirmed": True}
    )
    assert manifest.feeConfirmed is True


def test_total_reference_limit_includes_keyframes() -> None:
    payload = {
        **_v12(),
        "references": [_reference(index) for index in range(1, 21)],
        "providerPromptText": "首态图片作为参考，不保证生成画面逐像素一致。",
        "keyframes": [
            {
                "ordinal": 1,
                "keyframeVersionId": "frame-v1",
                "role": "initial_state",
                "assetId": "frame-asset-1",
                "sha256": "c" * 64,
                "mimeType": "image/png",
                "duty": "keyframe",
            }
        ],
    }
    with pytest.raises(ValidationError, match="20"):
        VideoShotRenderManifest.model_validate(payload)


def test_old_manifest_does_not_invent_new_execution_policy() -> None:
    manifest = VideoShotRenderManifest(schemaVersion="video-shot-render-manifest/1.1", **_base())
    assert manifest.generationMode is None
    assert manifest.executionMode is None
    assert manifest.feeConfirmed is None


def _submit() -> dict[str, object]:
    return {
        "taskId": "task-1",
        "novelId": "novel-1",
        "inputHash": "a" * 64,
        "generationMode": "reference",
        "executionMode": "simulated",
        "model": "seedance-test",
        "promptText": "完整冻结提示词",
        "ratio": "9:16",
        "durationSeconds": 4,
        "resolution": "720p",
        "generateAudio": True,
        "watermark": False,
        "references": [
            {
                "ordinal": 1,
                "assetId": "asset-1",
                "mimeType": "image/png",
                "url": "urn:inkforge:simulated-asset:asset-1",
                "usageRole": "initial_state",
            }
        ],
    }


@pytest.mark.parametrize("ordinal", [2, 3])
def test_submit_rejects_renumbered_references(ordinal: int) -> None:
    payload = _submit()
    payload["references"] = [
        {
            "ordinal": ordinal,
            "assetId": "asset-1",
            "mimeType": "image/png",
            "url": "urn:inkforge:simulated-asset:asset-1",
        }
    ]
    with pytest.raises(ValidationError, match="冻结顺序"):
        SeedanceRenderSubmitRequest.model_validate(payload)


@pytest.mark.parametrize("mode", ["auto", "edit", "extend"])
def test_submit_rejects_unapproved_generation_modes(mode: str) -> None:
    with pytest.raises(ValidationError):
        SeedanceRenderSubmitRequest.model_validate({**_submit(), "generationMode": mode})


def test_submit_accepts_frozen_keyframe_prefixed_text_without_truncation() -> None:
    prompt = "参考" * 1_250
    submitted = SeedanceRenderSubmitRequest.model_validate({**_submit(), "promptText": prompt})
    assert submitted.promptText == prompt


def test_query_output_preserves_last_frame_media_kind_and_usage() -> None:
    output = SeedanceRenderOutput(
        videoUrl="https://example.test/video.mp4",
        lastFrameUrl="https://example.test/last-frame.png",
        mediaKind="provider_media",
        usage={"completion_tokens": 140, "total_tokens": 140},
    )

    restored = SeedanceRenderOutput.model_validate_json(output.model_dump_json())
    assert restored.lastFrameUrl == "https://example.test/last-frame.png"
    assert restored.mediaKind == "provider_media"
    assert restored.usage == {"completion_tokens": 140, "total_tokens": 140}
