"""视频生成供应商中立边界的状态与来源约束。"""

from __future__ import annotations

import pytest
from inkforge_agents.providers.video_generation import (
    VideoGenerationOutput,
    VideoGenerationReference,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoGenerationSubmission,
)
from pydantic import ValidationError


def test_request_rejects_reference_order_drift() -> None:
    with pytest.raises(ValidationError, match="冻结顺序"):
        VideoGenerationRequest(
            task_id="task-1",
            input_hash="a" * 64,
            generation_mode="reference",
            input_profile="image_reference_v1",
            execution_mode="simulated",
            model="provider-model",
            prompt_text="冻结提示词",
            ratio="9:16",
            duration_seconds=5,
            resolution="720p",
            output_format="mp4",
            generate_audio=True,
            watermark=False,
            references=[
                VideoGenerationReference(
                    ordinal=2,
                    asset_id="asset-1",
                    modality="image",
                    mime_type="image/png",
                    transport_url="urn:inkforge:simulated-asset:asset-1",
                )
            ],
        )


def test_current_image_profile_rejects_unreleased_media_modalities() -> None:
    with pytest.raises(ValidationError, match="不能混入"):
        VideoGenerationRequest.model_validate(
            {
                "task_id": "task-1",
                "input_hash": "a" * 64,
                "generation_mode": "reference",
                "input_profile": "image_reference_v1",
                "execution_mode": "simulated",
                "model": "provider-model",
                "prompt_text": "冻结提示词",
                "ratio": "9:16",
                "duration_seconds": 5,
                "resolution": "720p",
                "output_format": "mp4",
                "generate_audio": True,
                "watermark": False,
                "references": [
                    {
                        "ordinal": 1,
                        "asset_id": "audio-1",
                        "modality": "audio",
                        "mime_type": "audio/mpeg",
                        "transport_url": "asset://audio-1",
                        "source_duration_seconds": 5,
                    }
                ],
            }
        )


def test_multimodal_profile_keeps_documented_output_choices() -> None:
    request = VideoGenerationRequest(
        task_id="task-1",
        input_hash="a" * 64,
        generation_mode="reference",
        input_profile="multimodal_reference_v1",
        execution_mode="simulated",
        model="provider-model",
        prompt_text="冻结提示词",
        ratio="adaptive",
        duration_seconds=-1,
        resolution="1080p",
        output_format="mov",
        generate_audio=True,
        watermark=False,
    )

    assert request.references == []
    assert request.duration_seconds == -1


def test_reference_rejects_mime_type_from_another_modality() -> None:
    with pytest.raises(ValidationError, match="模态"):
        VideoGenerationReference(
            ordinal=1,
            asset_id="video-1",
            modality="video",
            mime_type="image/png",
            transport_url="asset://video-1",
            source_duration_seconds=5,
        )


def test_submission_origin_must_match_execution_mode() -> None:
    with pytest.raises(ValidationError, match="模拟标记"):
        VideoGenerationSubmission(
            task_id="task-1",
            provider_task_id="provider-task-1",
            execution_mode="live",
            simulated=True,
        )


def test_simulated_success_is_explicit_placeholder() -> None:
    result = VideoGenerationResult(
        task_id="task-1",
        provider_task_id="simulated-task-1",
        execution_mode="simulated",
        status="succeeded",
        output=VideoGenerationOutput(
            video_url="inkforge-simulated://task-1",
            media_kind="simulated_placeholder",
        ),
    )

    assert result.output is not None
    assert result.output.media_kind == "simulated_placeholder"


@pytest.mark.parametrize(
    ("execution_mode", "media_kind"),
    [("simulated", "provider_media"), ("live", "simulated_placeholder")],
)
def test_success_rejects_media_origin_mismatch(
    execution_mode: str,
    media_kind: str,
) -> None:
    with pytest.raises(ValidationError, match="媒体来源"):
        VideoGenerationResult.model_validate(
            {
                "task_id": "task-1",
                "provider_task_id": "provider-task-1",
                "execution_mode": execution_mode,
                "status": "succeeded",
                "output": {
                    "video_url": "https://result.example/take.mp4",
                    "media_kind": media_kind,
                },
            }
        )


@pytest.mark.parametrize("status", ["queued", "running"])
def test_in_progress_result_cannot_carry_terminal_payload(status: str) -> None:
    with pytest.raises(ValidationError, match="不能提前携带"):
        VideoGenerationResult.model_validate(
            {
                "task_id": "task-1",
                "provider_task_id": "provider-task-1",
                "execution_mode": "live",
                "status": status,
                "output": {
                    "video_url": "https://result.example/take.mp4",
                    "media_kind": "provider_media",
                },
            }
        )


@pytest.mark.parametrize("status", ["failed", "expired", "cancelled"])
def test_failed_terminal_result_requires_error(status: str) -> None:
    with pytest.raises(ValidationError, match="必须且只能携带错误"):
        VideoGenerationResult.model_validate(
            {
                "task_id": "task-1",
                "provider_task_id": "provider-task-1",
                "execution_mode": "live",
                "status": status,
            }
        )
