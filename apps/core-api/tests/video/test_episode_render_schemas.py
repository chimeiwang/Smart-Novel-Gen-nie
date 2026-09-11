"""独立剧集逐镜生成契约必须只暴露制作基线身份。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from inkforge_core.video.episodes.render_router import router
from inkforge_core.video.episodes.render_schemas import VideoEpisodeProductionShotInput
from pydantic import ValidationError


def _input() -> dict[str, object]:
    return {
        "schemaVersion": "video-production-shot-input/1.0",
        "shotId": "shot-1",
        "shotVersionId": "shot-version-1",
        "shotVersionNo": 1,
        "shotContentHash": "a" * 64,
        "scriptSceneId": "scene-1",
        "scriptLineIds": ["line-1"],
        "provider": "seedance",
        "model": "doubao-seedance-2-5-260628",
        "generationMode": "reference",
        "executionMode": "simulated",
        "feeConfirmed": False,
        "promptVersionId": "prompt-1",
        "prompt": "完整冻结的逐镜提示词",
        "ratio": "9:16",
        "durationSeconds": 6,
        "resolution": "720p",
        "generateAudio": True,
        "watermark": False,
        "outputFormat": "mp4",
        "references": [
            {
                "ordinal": 1,
                "canonVersionId": "canon-v1",
                "canonContentHash": "b" * 64,
                "assetId": "asset-1",
                "sha256": "c" * 64,
                "mimeType": "image/png",
                "duty": "identity",
                "strength": 70,
            }
        ],
    }


def test_production_input_accepts_exact_simulated_snapshot() -> None:
    frozen = VideoEpisodeProductionShotInput.model_validate(_input())
    assert frozen.executionMode == "simulated"
    assert frozen.feeConfirmed is False
    assert frozen.references[0].ordinal == 1


def test_production_input_12_freezes_rights_and_utc_lock_time() -> None:
    value = _input()
    value["schemaVersion"] = "video-production-shot-input/1.2"
    value["references"] = [
        {
            **value["references"][0],  # type: ignore[index]
            "rightsStatus": "confirmed",
            "lockedAt": "2026-09-10T00:00:00Z",
        }
    ]
    value["keyframes"] = [
        {
            "ordinal": 1,
            "keyframeVersionId": "keyframe-v1",
            "role": "initial_state",
            "assetId": "frame-1",
            "sha256": "d" * 64,
            "mimeType": "image/png",
            "duty": "keyframe",
            "rightsStatus": "confirmed",
            "lockedAt": "2026-09-10T00:00:00Z",
            "contentHash": "e" * 64,
        }
    ]

    frozen = VideoEpisodeProductionShotInput.model_validate(value)
    assert frozen.references[0].lockedAt is not None
    assert frozen.keyframes[0].rightsStatus == "confirmed"

    del value["references"][0]["lockedAt"]  # type: ignore[index]
    with pytest.raises(ValidationError):
        VideoEpisodeProductionShotInput.model_validate(value)


def test_production_input_11_freezes_keyframes_and_combined_image_limit() -> None:
    keyframe = {
        "ordinal": 1,
        "keyframeVersionId": "keyframe-v1",
        "role": "initial_state",
        "assetId": "frame-1",
        "sha256": "d" * 64,
        "mimeType": "image/png",
        "duty": "keyframe",
        "contentHash": "e" * 64,
    }
    frozen = VideoEpisodeProductionShotInput.model_validate(
        {
            **_input(),
            "schemaVersion": "video-production-shot-input/1.1",
            "keyframes": [keyframe],
        }
    )
    assert frozen.keyframes[0].keyframeVersionId == "keyframe-v1"

    with pytest.raises(ValidationError):
        VideoEpisodeProductionShotInput.model_validate(
            {
                **_input(),
                "schemaVersion": "video-production-shot-input/1.1",
                "references": [
                    {
                        **_input()["references"][0],  # type: ignore[index]
                        "ordinal": index,
                        "canonVersionId": f"canon-{index}",
                    }
                    for index in range(1, 21)
                ],
                "keyframes": [keyframe],
            }
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"executionMode": "simulated", "feeConfirmed": True},
        {"executionMode": "live", "feeConfirmed": False},
        {"executionMode": "live", "feeConfirmed": True},
        {"durationSeconds": 3},
        {"resolution": "1080p"},
        {"references": []},
        {
            "references": [
                {
                    **_input()["references"][0],  # type: ignore[index]
                    "ordinal": 2,
                }
            ]
        },
    ],
)
def test_production_input_rejects_non_frozen_generation_facts(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        VideoEpisodeProductionShotInput.model_validate({**_input(), **changes})


def test_episode_render_routes_use_only_episode_baseline_and_stable_shot_ids() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    paths = set(app.openapi()["paths"])

    assert (
        "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}"
        "/shots/{shot_id}/render-tasks"
    ) in paths
    assert "/api/v1/video/episodes/{episode_id}/render-tasks/{task_id}" in paths
    assert (
        "/api/v1/video/episodes/{episode_id}/render-tasks/{task_id}/retry" in paths
    )
    assert "/api/v1/video/episodes/{episode_id}/takes/{take_id}/content" in paths
    assert all("adaptation" not in path for path in paths)
