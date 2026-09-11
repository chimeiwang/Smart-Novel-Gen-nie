"""章节影视化公共写入请求的边界测试。"""

from __future__ import annotations

import pytest
from inkforge_core.video.adaptation.schemas import (
    CreateVisualCanonCandidateRequest,
    RetryShotRenderRequest,
    StartPromptRunRequest,
    StartShotRenderRequest,
)
from pydantic import ValidationError


def test_visual_candidate_requires_explicit_revision() -> None:
    payload = {
        "clientRequestId": "0123456789abcdef",
        "settingKind": "character",
        "settingId": "character-1",
        "duty": "identity",
        "variantKey": "identity-1",
        "label": "日常定妆",
        "candidateAssetId": "asset-1",
    }
    with pytest.raises(ValidationError, match="expectedRevision"):
        CreateVisualCanonCandidateRequest.model_validate(payload)
    for revision in [0, 2]:
        request = CreateVisualCanonCandidateRequest.model_validate(
            {**payload, "expectedRevision": revision}
        )
        assert request.expectedRevision == revision
    with pytest.raises(ValidationError, match="expectedRevision"):
        CreateVisualCanonCandidateRequest.model_validate({**payload, "expectedRevision": -1})


def test_prompt_run_rejects_duplicate_shot_targets() -> None:
    with pytest.raises(ValidationError, match="不能重复"):
        StartPromptRunRequest(
            clientRequestId="0123456789abcdef",
            expectedAdaptationRevision=1,
            shotPlanVersionId="plan-1",
            shotIds=["shot-1", "shot-1"],
        )


def test_trial_defaults_to_no_fee_confirmation() -> None:
    created = StartShotRenderRequest(
        clientRequestId="0123456789abcdef",
        expectedPromptRevision=1,
        generationMode="reference",
        durationSeconds=4,
    )
    retried = RetryShotRenderRequest(clientRequestId="0123456789abcdef")
    assert created.feeConfirmed is False
    assert retried.feeConfirmed is False


@pytest.mark.parametrize(
    "changes",
    [
        {"generationMode": "auto"},
        {"durationSeconds": 3},
        {"durationSeconds": 13},
        {"resolution": "480p"},
        {"resolution": "1080p"},
        {"feeConfirmed": "true"},
    ],
)
def test_trial_rejects_inputs_outside_first_release(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        StartShotRenderRequest.model_validate(
            {
                "clientRequestId": "0123456789abcdef",
                "expectedPromptRevision": 1,
                "generationMode": "reference",
                "durationSeconds": 4,
                **changes,
            }
        )
