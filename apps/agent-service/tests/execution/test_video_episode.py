"""独立剧本候选沿 V2 单 Step 执行，模型不能越权修改其他场次。"""

from dataclasses import replace

import pytest
from inkforge_agents.execution.video_episode import (
    build_episode_script_request,
    episode_script_context,
    materialize_episode_script_output,
)
from inkforge_contracts.execution import (
    EvidenceManifest,
    EvidenceManifestItem,
    canonical_execution_json_bytes,
    canonical_execution_sha256,
)
from inkforge_contracts.video_episode import VideoEpisodeScriptContext

from .support import rehash_request
from .video_support import Responses, authorized_video_request, invoke_video


def candidate():
    return {
        "overview": {"summary": "来客到访", "creativeIntent": "悬念", "targetDurationSeconds": 60},
        "scenes": [
            {
                "id": None,
                "tempKey": "scene-new",
                "title": "雨夜",
                "locationLabel": "书房",
                "timeLabel": "夜",
                "narrativeTime": "当晚",
                "characterIds": [],
                "lines": [
                    {
                        "id": None,
                        "tempKey": "line-new",
                        "kind": "action",
                        "speakerId": None,
                        "text": "门被推开。",
                        "sourceRefs": [],
                    }
                ],
            }
        ],
        "endingStates": [],
        "dependencies": [],
    }


def episode_request(stage="episode_script", **input_values):
    base = authorized_video_request(stage)
    context = VideoEpisodeScriptContext(
        episodeId="episode-1",
        projectId="project-1",
        novelId=base.novelId,
        episodeTitle="雨夜",
        operation="episode_script_generate",
        draftRevision=1,
        sourceSetVersionId=None,
        baseScriptVersionId=None,
        draft={"scenes": []},
        sources=[],
        characters=[],
        inheritedStates=[],
        selectedSceneIds=[],
        instruction="原创一集雨夜悬念",
    ).model_dump(mode="json")
    item = base.evidenceBundle.items[0].model_copy(
        update={
            "resourceType": "video_episode_script_context",
            "resourceId": "episode-1",
            "contentJson": context,
            "contentSha256": canonical_execution_sha256(context),
            "byteCount": len(canonical_execution_json_bytes(context)),
        }
    )
    manifest = EvidenceManifest(
        bundleId=item.bundleId,
        bundleVersion=1,
        itemCount=1,
        items=[
            EvidenceManifestItem(
                itemId=item.id,
                **item.model_dump(exclude={"id", "bundleId", "contentJson", "contentText"}),
            )
        ],
    )
    bundle = base.evidenceBundle.model_copy(
        update={
            "policyVersion": "evidence.video.episode_script.v1",
            "items": [item],
            "manifest": manifest,
            "manifestSha256": canonical_execution_sha256(
                manifest.model_dump(mode="json", exclude_none=True)
            ),
            "totalBytes": item.byteCount,
        }
    )
    return rehash_request(
        base.model_copy(
            update={
                "operation": "episode_script_generate",
                "evidenceBundle": bundle,
                "input": {
                    "stageKey": stage,
                    "cycle": 0,
                    "candidate": None,
                    "requiredChanges": [],
                    "dependencies": [],
                    **input_values,
                },
                "budget": base.budget.model_copy(update={"maxProtocolCorrections": 0}),
            }
        )
    )


class EpisodeResponses(Responses):
    async def complete_responses(self, request):
        result = await super().complete_responses(request)
        return replace(result, structuredOutput=candidate())


@pytest.mark.asyncio
async def test_script_stage_calls_once_and_returns_candidate_without_adoption():
    provider = EpisodeResponses()
    result, attempts = await invoke_video(provider, episode_request())
    assert result.output["stageKey"] == "episode_script"
    assert result.output["candidate"]["scenes"][0]["tempKey"] == "scene-new"
    assert result.output["review"] is None
    assert result.usage.inputTokens == 100
    assert provider.calls == attempts == 1


def test_script_request_keeps_full_author_instruction_and_no_tools():
    result = build_episode_script_request(episode_request(), "剧本编剧")
    assert result.tools == []
    assert "原创一集雨夜悬念" in result.messages[1].content
    assert result.maxOutputTokens == 32_000


def test_script_cannot_forge_stable_ids_even_for_new_scene():
    raw = candidate()
    raw["scenes"][0]["lines"][0].update(id="invented-id", tempKey=None)
    with pytest.raises(ValueError, match="稳定台词"):
        materialize_episode_script_output(episode_request(), raw)


def test_review_findings_must_point_to_existing_candidate_nodes():
    request = episode_request(
        "episode_script_review",
        candidate=candidate(),
        dependencies=[{"stepId": "previous", "resultHash": "a" * 64}],
    )
    review = {
        "decision": "pass",
        "summary": "可供作者选择",
        "requiredChanges": [],
        "findings": [
            {"code": "clarity", "sceneId": "nonexistent", "lineId": None, "message": "位置不清楚"}
        ],
    }
    with pytest.raises(ValueError, match="不存在"):
        materialize_episode_script_output(request, review)


def test_evidence_cannot_be_substituted_from_another_episode():
    request = episode_request()
    request.evidenceBundle.items[0].contentJson["episodeId"] = "episode-2"
    with pytest.raises(ValueError, match="身份"):
        episode_script_context(request)
