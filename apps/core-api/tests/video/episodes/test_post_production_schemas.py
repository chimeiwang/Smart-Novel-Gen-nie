from __future__ import annotations

import pytest
from inkforge_core.app import create_app
from inkforge_core.video.episodes.post_production_schemas import (
    CreateVideoEpisodeEditVersionRequest,
    CreateVideoEpisodeMixVersionRequest,
)
from pydantic import ValidationError


def _edit_request() -> dict[str, object]:
    return {
        "clientRequestId": "cli_edit_0123456789",
        "expectedHeadRevision": 1,
        "basedOnVersionId": None,
        "clips": [
            {
                "tempKey": "clip_a",
                "adoptionId": "adoption_a",
                "takeId": "take_a",
                "sourceInMs": 0,
                "sourceOutMs": 1_000,
                "sourceAudioMode": "keep",
            }
        ],
        "omissions": [{"shotVersionId": "shot_version_b", "reason": "节奏删减"}],
    }


def test_edit_contract_allows_same_adoption_in_distinct_clips() -> None:
    request = _edit_request()
    request["clips"] = [
        request["clips"][0],  # type: ignore[index]
        {
            "tempKey": "clip_b",
            "adoptionId": "adoption_a",
            "takeId": "take_a",
            "sourceInMs": 1_000,
            "sourceOutMs": 2_000,
            "sourceAudioMode": "mute",
            "transitionAfter": "fade_black",
            "transitionDurationMs": 300,
        },
    ]

    parsed = CreateVideoEpisodeEditVersionRequest.model_validate(request)

    assert [clip.sourceAudioMode for clip in parsed.clips] == ["keep", "mute"]
    assert {clip.adoptionId for clip in parsed.clips} == {"adoption_a"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sourceOutMs", 400),
        ("sourceAudioMode", "auto"),
        ("transitionDurationMs", 800),
    ],
)
def test_edit_contract_rejects_invalid_clip_ranges_and_audio_mode(
    field: str, value: object
) -> None:
    request = _edit_request()
    request["clips"][0][field] = value  # type: ignore[index]

    with pytest.raises(ValidationError):
        CreateVideoEpisodeEditVersionRequest.model_validate(request)


def test_edit_contract_rejects_duplicate_omission() -> None:
    request = _edit_request()
    request["omissions"] = [
        {"shotVersionId": "shot_version_b", "reason": "节奏删减"},
        {"shotVersionId": "shot_version_b", "reason": "重复决定"},
    ]

    with pytest.raises(ValidationError):
        CreateVideoEpisodeEditVersionRequest.model_validate(request)


def test_mix_contract_requires_valid_subtitle_and_audio_ranges() -> None:
    payload = {
        "clientRequestId": "cli_mix_0123456789",
        "expectedHeadRevision": 1,
        "editVersionId": "edit_a",
        "audioClips": [
            {
                "trackKind": "dialogue",
                "assetId": "audio_a",
                "shotVersionId": "shot_version_a",
                "timelineStartMs": 0,
                "sourceInMs": 0,
                "sourceOutMs": 1_000,
                "fadeInMs": 100,
                "fadeOutMs": 100,
            }
        ],
        "subtitleCues": [
            {
                "shotVersionId": "shot_version_a",
                "scriptLineId": "line_a",
                "startMs": 0,
                "endMs": 900,
                "text": "对白",
            }
        ],
    }

    parsed = CreateVideoEpisodeMixVersionRequest.model_validate(payload)
    assert parsed.subtitleCues[0].scriptLineId == "line_a"

    payload["subtitleCues"][0]["endMs"] = 0  # type: ignore[index]
    with pytest.raises(ValidationError):
        CreateVideoEpisodeMixVersionRequest.model_validate(payload)


def test_episode_post_production_openapi_is_separate_and_bounded() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]
    edit_path = (
        "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}"
        "/edit-versions"
    )
    export_path = (
        "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}"
        "/export-tasks"
    )

    assert paths[edit_path]["post"]["tags"] == ["VideoEpisodePostProduction"]
    parameters = {item["name"]: item for item in paths[edit_path]["get"]["parameters"]}
    assert parameters["limit"]["schema"]["maximum"] == 100
    before_schema = parameters["beforeVersionNo"]["schema"]
    assert any(item.get("minimum") == 1 for item in before_schema.get("anyOf", [before_schema]))
    assert paths[export_path]["post"]["responses"]["202"]
