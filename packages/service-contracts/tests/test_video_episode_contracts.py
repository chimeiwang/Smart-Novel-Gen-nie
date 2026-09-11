"""剧本身份、取材范围和局部修订权限的跨服务硬边界。"""

import hashlib

import pytest
from inkforge_contracts.video_episode import (
    VideoEpisodeScriptContext,
    VideoEpisodeScriptDocument,
    VideoEpisodeScriptProposal,
    VideoEpisodeScriptStageInput,
    merge_video_episode_proposal,
)
from pydantic import ValidationError


def scene(scene_id="scene-1", line_id="line-1", text="林岚推门。"):
    return {
        "id": scene_id,
        "title": "雨夜",
        "locationLabel": "书房",
        "timeLabel": "夜",
        "narrativeTime": "当晚",
        "characterIds": ["character-1"],
        "lines": [
            {
                "id": line_id,
                "kind": "action",
                "speakerId": None,
                "text": text,
                "sourceRefs": [{"sourceSnapshotId": "snapshot-1", "start": 5, "end": 10}],
            }
        ],
    }


def context():
    text = "林岚推门。"
    return VideoEpisodeScriptContext.model_validate(
        {
            "episodeId": "episode-1",
            "projectId": "project-1",
            "novelId": "novel-1",
            "episodeTitle": "雨夜",
            "operation": "episode_script_revise",
            "draftRevision": 3,
            "sourceSetVersionId": "source-set-1",
            "baseScriptVersionId": None,
            "draft": {"scenes": [scene(), scene("scene-2", "line-2", "他看向窗外。")]},
            "sources": [
                {
                    "sourceSnapshotId": "snapshot-1",
                    "chapterId": "chapter-1",
                    "chapterTitle": "旧雨",
                    "sourceHash": "a" * 64,
                    "selectedRanges": [
                        {
                            "sourceSnapshotId": "snapshot-1",
                            "start": 5,
                            "end": 10,
                            "text": text,
                            "textHash": hashlib.sha256(text.encode()).hexdigest(),
                        }
                    ],
                }
            ],
            "characters": [{"id": "character-1", "name": "林岚", "description": "主角"}],
            "inheritedStates": [],
            "selectedSceneIds": ["scene-1"],
            "instruction": "让动作更清楚",
        }
    )


def proposal():
    return VideoEpisodeScriptProposal.model_validate(
        {
            "overview": None,
            "scenes": [scene(text="林岚缓缓推门。")],
            "endingStates": None,
            "dependencies": None,
        }
    )


def test_partial_revision_preserves_every_unselected_field_and_stable_node_identity():
    frozen = context()
    merged = merge_video_episode_proposal(frozen, proposal())
    assert merged.scenes[0].id == "scene-1"
    assert merged.scenes[0].lines[0].text == "林岚缓缓推门。"
    assert merged.scenes[1] == frozen.draft.scenes[1]
    assert merged.overview == frozen.draft.overview
    assert frozen.draft.scenes[0].lines[0].text == "林岚推门。"


@pytest.mark.parametrize(
    "mutation", ["scope", "globals", "unknown_id", "cross_scene_line", "source", "speaker"]
)
def test_candidate_cannot_expand_revision_or_forge_bindings(mutation):
    value = proposal().model_dump(mode="json")
    first = value["scenes"][0]
    if mutation == "scope":
        value["scenes"].append(scene("scene-2", "line-2"))
    elif mutation == "globals":
        value["endingStates"] = []
    elif mutation == "unknown_id":
        first["lines"][0]["id"] = "invented-stable-id"
    elif mutation == "cross_scene_line":
        first["lines"][0]["id"] = "line-2"
    elif mutation == "source":
        first["lines"][0]["sourceRefs"][0]["start"] = 0
    else:
        first["characterIds"] = ["unknown-character"]
    with pytest.raises(ValueError):
        merge_video_episode_proposal(context(), VideoEpisodeScriptProposal.model_validate(value))


@pytest.mark.parametrize("fields", [{}, {"id": "scene-1", "tempKey": "new-scene"}])
def test_new_nodes_require_exactly_one_identity(fields):
    value = scene()
    value.pop("id")
    value.update(fields)
    with pytest.raises(ValidationError):
        VideoEpisodeScriptDocument.model_validate({"scenes": [value]})


def test_selected_evidence_is_exact_text_not_entire_chapter_or_utf16_offsets():
    value = context().model_dump(mode="json")
    fragment = value["sources"][0]["selectedRanges"][0]
    fragment.update(
        text="😀人物", start=8, end=11, textHash=hashlib.sha256("😀人物".encode()).hexdigest()
    )
    VideoEpisodeScriptContext.model_validate(value)
    fragment["end"] = 12
    with pytest.raises(ValidationError, match="Unicode"):
        VideoEpisodeScriptContext.model_validate(value)


def test_revision_must_select_a_saved_scene():
    value = context().model_dump(mode="json")
    value["selectedSceneIds"] = []
    with pytest.raises(ValidationError, match="至少一个"):
        VideoEpisodeScriptContext.model_validate(value)


def test_review_requires_previous_candidate_and_retry_requires_two_dependencies():
    with pytest.raises(ValidationError):
        VideoEpisodeScriptStageInput(
            stageKey="episode_script_review",
            cycle=0,
            candidate=None,
            requiredChanges=[],
            dependencies=[],
        )
    with pytest.raises(ValidationError):
        VideoEpisodeScriptStageInput(
            stageKey="episode_script",
            cycle=1,
            candidate=proposal(),
            requiredChanges=["修正承接"],
            dependencies=[],
        )
