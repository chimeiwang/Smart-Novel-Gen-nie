import pytest
from inkforge_core.video.episodes.production_schemas import (
    CreateVideoProductionBaselineRequest,
    StartVideoStoryboardRunRequest,
)
from pydantic import ValidationError


def test_storyboard_run_requires_explicit_stable_scope_and_script_version() -> None:
    request = StartVideoStoryboardRunRequest(
        clientRequestId="storyboard-run-request-01",
        expectedDraftRevision=3,
        scriptVersionId="script-v2",
        operation="episode_storyboard_revise",
        selectedShotIds=["shot-1"],
        instruction="只修订收信镜头",
    )

    assert request.scriptVersionId == "script-v2"
    assert request.selectedShotIds == ["shot-1"]


@pytest.mark.parametrize(
    ("operation", "selected"),
    [
        ("episode_storyboard_generate", ["shot-1"]),
        ("episode_storyboard_revise", []),
        ("episode_storyboard_revise", ["shot-1", "shot-1"]),
    ],
)
def test_storyboard_run_rejects_ambiguous_scope(
    operation: str, selected: list[str]
) -> None:
    with pytest.raises(ValidationError):
        StartVideoStoryboardRunRequest.model_validate(
            {
                "clientRequestId": "storyboard-run-request-02",
                "expectedDraftRevision": 1,
                "scriptVersionId": "script-v1",
                "operation": operation,
                "selectedShotIds": selected,
                "instruction": "生成分镜",
            }
        )


def test_production_baseline_accepts_one_keyframe_per_shot_role() -> None:
    request = CreateVideoProductionBaselineRequest.model_validate(
        {
            "clientRequestId": "production-baseline-request-01",
            "expectedEpisodeRevision": 3,
            "expectedProductionRevision": 1,
            "scriptVersionId": "script-v1",
            "storyboardVersionId": "storyboard-v1",
            "keyframes": [
                {
                    "shotVersionId": "shot-version-1",
                    "role": "initial_state",
                    "assetId": "asset-1",
                },
                {
                    "shotVersionId": "shot-version-1",
                    "role": "end_state",
                    "assetId": "asset-2",
                },
            ],
        }
    )

    assert [item.role for item in request.keyframes] == ["initial_state", "end_state"]


def test_production_baseline_rejects_duplicate_keyframe_role() -> None:
    with pytest.raises(ValidationError):
        CreateVideoProductionBaselineRequest.model_validate(
            {
                "clientRequestId": "production-baseline-request-02",
                "expectedEpisodeRevision": 3,
                "expectedProductionRevision": 1,
                "scriptVersionId": "script-v1",
                "storyboardVersionId": "storyboard-v1",
                "keyframes": [
                    {
                        "shotVersionId": "shot-version-1",
                        "role": "initial_state",
                        "assetId": "asset-1",
                    },
                    {
                        "shotVersionId": "shot-version-1",
                        "role": "initial_state",
                        "assetId": "asset-2",
                    },
                ],
            }
        )
