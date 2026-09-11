from __future__ import annotations

from copy import deepcopy

import pytest
from inkforge_contracts.video_storyboard import (
    VideoStoryboardContext,
    VideoStoryboardProposal,
    VideoStoryboardStageInput,
    merge_video_storyboard_proposal,
)
from pydantic import ValidationError


def _reference() -> dict[str, object]:
    return {
        "canonVersionId": "canon-v1",
        "canonContentHash": "1" * 64,
        "assetId": "asset-1",
        "sha256": "2" * 64,
        "mimeType": "image/png",
        "duty": "identity",
        "defaultStrength": 72,
        "settingName": "林岚",
        "label": "常服",
        "includeFeatures": ["黑发"],
        "excludeFeatures": ["现代首饰"],
    }


def _intent(prompt: str) -> dict[str, object]:
    return {
        "provider": "seedance",
        "model": "doubao-seedance-2-5-260628",
        "generationMode": "reference",
        "executionMode": "simulated",
        "feeConfirmed": False,
        "prompt": prompt,
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
                "canonContentHash": "1" * 64,
                "assetId": "asset-1",
                "sha256": "2" * 64,
                "mimeType": "image/png",
                "duty": "identity",
                "strength": 72,
            }
        ],
    }


def _shot(shot_id: str, scene_id: str, line_id: str, action: str) -> dict[str, object]:
    return {
        "id": shot_id,
        "tempKey": None,
        "lineage": [],
        "scriptSceneId": scene_id,
        "scriptLineIds": [line_id],
        "title": action,
        "action": action,
        "framing": "medium",
        "cameraMovement": "static",
        "durationMs": 6_000,
        "productionIntent": _intent(action),
    }


def _context() -> VideoStoryboardContext:
    return VideoStoryboardContext.model_validate(
        {
            "episodeId": "episode-1",
            "projectId": "project-1",
            "novelId": "novel-1",
            "episodeTitle": "第一集",
            "operation": "episode_storyboard_revise",
            "draftRevision": 4,
            "draftContentHash": "3" * 64,
            "scriptVersionId": "script-v1",
            "scriptContentHash": "4" * 64,
            "baseStoryboardVersionId": None,
            "script": {
                "overview": {},
                "scenes": [
                    {
                        "id": "scene-1",
                        "title": "送信",
                        "locationLabel": "门前",
                        "timeLabel": "雨夜",
                        "narrativeTime": "当晚",
                        "characterIds": [],
                        "lines": [
                            {
                                "id": "line-1",
                                "kind": "action",
                                "text": "林岚收回信。",
                            }
                        ],
                    },
                    {
                        "id": "scene-2",
                        "title": "回忆",
                        "locationLabel": "书房",
                        "timeLabel": "白日",
                        "narrativeTime": "三日前",
                        "characterIds": [],
                        "lines": [
                            {
                                "id": "line-2",
                                "kind": "action",
                                "text": "顾舟写下地址。",
                            }
                        ],
                    },
                ],
                "endingStates": [],
                "dependencies": [],
            },
            "draft": {
                "shots": [
                    _shot("shot-1", "scene-1", "line-1", "林岚握紧信封"),
                    _shot("shot-2", "scene-2", "line-2", "顾舟低头写字"),
                ]
            },
            "stableShotIds": ["shot-1", "shot-2"],
            "selectedShotIds": ["shot-1"],
            "productionDefaults": {
                "model": "doubao-seedance-2-5-260628",
                "ratio": "9:16",
            },
            "availableReferences": [_reference()],
            "instruction": "只加强收回信的动作",
        }
    )


def _proposal() -> VideoStoryboardProposal:
    value = _shot("shot-1", "scene-1", "line-1", "林岚把信收入袖中")
    value["productionIntent"] = {
        key: item
        for key, item in value["productionIntent"].items()  # type: ignore[union-attr]
        if key != "references"
    } | {"references": [{"canonVersionId": "canon-v1"}]}
    return VideoStoryboardProposal.model_validate({"shots": [value]})


def test_local_revision_preserves_every_unselected_shot_and_frozen_reference_fact() -> None:
    document = merge_video_storyboard_proposal(_context(), _proposal())

    assert [shot.id for shot in document.shots] == ["shot-1", "shot-2"]
    assert document.shots[0].action == "林岚把信收入袖中"
    assert document.shots[1].action == "顾舟低头写字"
    reference = document.shots[0].productionIntent.references[0]
    assert reference.assetId == "asset-1"
    assert reference.sha256 == "2" * 64
    assert reference.strength == 72


def test_local_revision_rejects_full_document_or_new_temporary_identity() -> None:
    value = _proposal().model_dump(mode="json")
    value["shots"].append(
        {
            **_shot("shot-2", "scene-2", "line-2", "越权修改"),
            "productionIntent": {
                **_proposal().shots[0].productionIntent.model_dump(mode="json"),
            },
        }
    )
    with pytest.raises(ValueError, match="恰好包含"):
        merge_video_storyboard_proposal(
            _context(), VideoStoryboardProposal.model_validate(value)
        )

    value = _proposal().model_dump(mode="json")
    value["shots"][0]["id"] = None
    value["shots"][0]["tempKey"] = "new-shot"
    with pytest.raises(ValueError, match="稳定镜头"):
        merge_video_storyboard_proposal(
            _context(), VideoStoryboardProposal.model_validate(value)
        )


def test_candidate_cannot_switch_execution_or_reference_outside_frozen_evidence() -> None:
    value = _proposal().model_dump(mode="json")
    value["shots"][0]["productionIntent"]["model"] = "other-model"
    with pytest.raises(ValueError, match="执行参数"):
        merge_video_storyboard_proposal(
            _context(), VideoStoryboardProposal.model_validate(value)
        )

    value = _proposal().model_dump(mode="json")
    value["shots"][0]["productionIntent"]["references"] = [
        {"canonVersionId": "not-frozen"}
    ]
    with pytest.raises(ValueError, match="未冻结"):
        merge_video_storyboard_proposal(
            _context(), VideoStoryboardProposal.model_validate(value)
        )


def test_context_requires_exact_stable_shot_order_and_selected_subset() -> None:
    value = _context().model_dump(mode="json")
    value["stableShotIds"] = ["shot-2", "shot-1"]
    with pytest.raises(ValidationError, match="身份及顺序"):
        VideoStoryboardContext.model_validate(value)

    value = _context().model_dump(mode="json")
    value["selectedShotIds"] = ["foreign-shot"]
    with pytest.raises(ValidationError, match="冻结工作稿"):
        VideoStoryboardContext.model_validate(value)


def test_stage_rework_requires_candidate_review_and_two_dependencies() -> None:
    with pytest.raises(ValidationError, match="返工必须"):
        VideoStoryboardStageInput(
            stageKey="episode_storyboard",
            cycle=1,
            candidate=_proposal(),
            requiredChanges=["补足动作"],
            dependencies=[{"stepId": "step-1", "resultHash": "5" * 64}],
        )


def test_generate_accepts_new_temp_key_but_not_selected_scope() -> None:
    value = deepcopy(_context().model_dump(mode="json"))
    value["operation"] = "episode_storyboard_generate"
    value["selectedShotIds"] = []
    context = VideoStoryboardContext.model_validate(value)
    candidate = _proposal().model_dump(mode="json")
    candidate["shots"][0]["id"] = None
    candidate["shots"][0]["tempKey"] = "opening-shot"
    candidate["shots"][0]["lineage"] = []

    document = merge_video_storyboard_proposal(
        context, VideoStoryboardProposal.model_validate(candidate)
    )

    assert document.shots[0].id is None
    assert document.shots[0].tempKey == "opening-shot"
