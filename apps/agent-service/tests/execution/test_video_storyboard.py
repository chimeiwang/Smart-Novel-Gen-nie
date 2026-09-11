"""独立分镜 V2 Step 必须冻结正式剧本、视觉参考和局部镜头范围。"""

from dataclasses import replace

import pytest
from inkforge_agents.execution.video_episode import build_episode_script_request
from inkforge_agents.execution.video_storyboard import (
    build_episode_storyboard_request,
    episode_storyboard_context,
    materialize_episode_storyboard_output,
)
from inkforge_agents.providers.fake import FakeModelProvider
from inkforge_contracts.execution import (
    EvidenceManifest,
    EvidenceManifestItem,
    canonical_execution_json_bytes,
    canonical_execution_sha256,
)
from inkforge_contracts.video_storyboard import VideoStoryboardContext

from .support import rehash_request
from .test_video_episode import episode_request
from .video_support import Responses, authorized_video_request, invoke_video


def _context(operation: str = "episode_storyboard_generate") -> dict[str, object]:
    base = authorized_video_request("episode_storyboard")
    return VideoStoryboardContext.model_validate(
        {
            "episodeId": "episode-real",
            "projectId": "project-real",
            "novelId": base.novelId,
            "episodeTitle": "第一集",
            "operation": operation,
            "draftRevision": 1,
            "draftContentHash": "1" * 64,
            "scriptVersionId": "script-real",
            "scriptContentHash": "2" * 64,
            "baseStoryboardVersionId": None,
            "script": {
                "overview": {},
                "scenes": [
                    {
                        "id": "scene-real",
                        "title": "雨夜送信",
                        "locationLabel": "门前",
                        "timeLabel": "夜",
                        "narrativeTime": "当晚",
                        "characterIds": [],
                        "lines": [
                            {
                                "id": "line-real",
                                "kind": "action",
                                "text": "林岚收回信。",
                            }
                        ],
                    }
                ],
                "endingStates": [],
                "dependencies": [],
            },
            "draft": {"shots": []},
            "stableShotIds": [],
            "selectedShotIds": [],
            "productionDefaults": {
                "model": "doubao-seedance-2-5-260628",
                "ratio": "9:16",
            },
            "availableReferences": [
                {
                    "canonVersionId": "canon-real",
                    "canonContentHash": "3" * 64,
                    "assetId": "asset-real",
                    "sha256": "4" * 64,
                    "mimeType": "image/png",
                    "duty": "identity",
                    "defaultStrength": 75,
                    "settingName": "林岚",
                    "label": "雨夜常服",
                    "includeFeatures": ["黑发"],
                    "excludeFeatures": [],
                }
            ],
            "instruction": "把送信场设计成可制作的竖屏分镜",
        }
    ).model_dump(mode="json")


def candidate() -> dict[str, object]:
    return {
        "shots": [
            {
                "id": None,
                "tempKey": "shot-new",
                "lineage": [],
                "scriptSceneId": "scene-real",
                "scriptLineIds": ["line-real"],
                "title": "收信",
                "action": "林岚把信收入袖中。",
                "framing": "medium",
                "cameraMovement": "static",
                "durationMs": 6000,
                "productionIntent": {
                    "provider": "seedance",
                    "model": "doubao-seedance-2-5-260628",
                    "generationMode": "reference",
                    "executionMode": "simulated",
                    "feeConfirmed": False,
                    "prompt": "林岚把信收入袖中，人物定妆保持一致。",
                    "ratio": "9:16",
                    "durationSeconds": 6,
                    "resolution": "720p",
                    "generateAudio": True,
                    "watermark": False,
                    "outputFormat": "mp4",
                    "references": [{"canonVersionId": "canon-real"}],
                },
            }
        ]
    }


def storyboard_request(stage: str = "episode_storyboard", **input_values):
    base = authorized_video_request(stage)
    context = _context()
    item = base.evidenceBundle.items[0].model_copy(
        update={
            "resourceType": "video_episode_storyboard_context",
            "resourceId": "episode-real",
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
            "policyVersion": "evidence.video.episode_storyboard.v1",
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
                "operation": "episode_storyboard_generate",
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


class StoryboardResponses(Responses):
    async def complete_responses(self, request):
        result = await super().complete_responses(request)
        return replace(result, structuredOutput=candidate())


@pytest.mark.asyncio
async def test_storyboard_stage_calls_once_and_only_returns_unapplied_candidate() -> None:
    provider = StoryboardResponses()
    result, attempts = await invoke_video(provider, storyboard_request())

    assert result.output["stageKey"] == "episode_storyboard"
    assert result.output["candidate"]["shots"][0]["tempKey"] == "shot-new"
    assert result.output["review"] is None
    assert provider.calls == attempts == 1


def test_storyboard_request_keeps_instruction_and_has_no_tools() -> None:
    request = build_episode_storyboard_request(storyboard_request(), "分镜师")

    assert request.tools == []
    assert "把送信场设计成可制作的竖屏分镜" in request.messages[1].content
    assert request.maxOutputTokens == 48_000


def test_storyboard_candidate_cannot_reference_unfrozen_canon_or_live_execution() -> None:
    value = candidate()
    value["shots"][0]["productionIntent"]["references"] = [  # type: ignore[index]
        {"canonVersionId": "canon-forged"}
    ]
    with pytest.raises(ValueError, match="未冻结"):
        materialize_episode_storyboard_output(storyboard_request(), value)

    value = candidate()
    value["shots"][0]["productionIntent"].update(  # type: ignore[index,union-attr]
        executionMode="live", feeConfirmed=True
    )
    with pytest.raises(ValueError):
        materialize_episode_storyboard_output(storyboard_request(), value)


def test_storyboard_review_must_reference_real_candidate_shot() -> None:
    request = storyboard_request(
        "episode_storyboard_review",
        candidate=candidate(),
        dependencies=[{"stepId": "previous", "resultHash": "5" * 64}],
    )
    review = {
        "decision": "pass",
        "summary": "可供作者选择",
        "requiredChanges": [],
        "findings": [
            {
                "code": "shot_clarity",
                "shotId": "not-found",
                "scriptSceneId": "scene-real",
                "message": "动作不清楚",
            }
        ],
    }
    with pytest.raises(ValueError, match="不存在"):
        materialize_episode_storyboard_output(request, review)


def test_storyboard_evidence_cannot_be_substituted_between_episodes() -> None:
    request = storyboard_request()
    request.evidenceBundle.items[0].contentJson["episodeId"] = "episode-other"
    with pytest.raises(ValueError, match="身份"):
        episode_storyboard_context(request)


@pytest.mark.asyncio
async def test_fake_provider_uses_real_frozen_script_and_reference_ids() -> None:
    model_request = build_episode_storyboard_request(storyboard_request(), "分镜师")
    result = await FakeModelProvider().complete_turn(model_request)

    assert result.structuredOutput is not None
    shot = result.structuredOutput["shots"][0]
    assert shot["scriptSceneId"] == "scene-real"
    assert shot["scriptLineIds"] == ["line-real"]
    assert shot["productionIntent"]["references"][0]["canonVersionId"] == "canon-real"


@pytest.mark.asyncio
async def test_fake_provider_builds_p1_script_from_real_source_snapshot() -> None:
    request = episode_request()
    context = request.evidenceBundle.items[0].contentJson
    context["sources"] = [
        {
            "sourceSnapshotId": "snapshot-real",
            "chapterId": "chapter-real",
            "chapterTitle": "第一章",
            "sourceHash": "6" * 64,
            "selectedRanges": [
                {
                    "sourceSnapshotId": "snapshot-real",
                    "start": 0,
                    "end": 4,
                    "text": "雨夜送信",
                    "textHash": "fc8f345ad5ad21a9b65986d135b710f380b57539ecf29483d93b172b6557b4d0",
                }
            ],
        }
    ]
    item = request.evidenceBundle.items[0].model_copy(
        update={
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
    request = rehash_request(
        request.model_copy(
            update={
                "evidenceBundle": request.evidenceBundle.model_copy(
                    update={
                        "items": [item],
                        "manifest": manifest,
                        "manifestSha256": canonical_execution_sha256(
                            manifest.model_dump(mode="json", exclude_none=True)
                        ),
                        "totalBytes": item.byteCount,
                    }
                )
            }
        )
    )
    model_request = build_episode_script_request(request, "编剧")
    result = await FakeModelProvider().complete_turn(model_request)

    assert result.structuredOutput is not None
    source_ref = result.structuredOutput["scenes"][0]["lines"][0]["sourceRefs"][0]
    assert source_ref["sourceSnapshotId"] == "snapshot-real"
