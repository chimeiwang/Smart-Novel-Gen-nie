"""单集队列迁移的权限、有限返工和重投恢复回归。"""

import copy
import hashlib
from datetime import UTC, datetime

import pytest
from inkforge_agents.jobs.video_episode import EpisodeJobHandler
from inkforge_agents.providers.base import ModelTurnResult, ModelUsage
from inkforge_agents.queue.consumer import NonRetryableJobError
from inkforge_agents.queue.repository import QueueJob
from inkforge_contracts.video_episode import VideoEpisodeScriptContext, VideoEpisodeScriptProposal
from inkforge_contracts.video_storyboard import VideoStoryboardContext, VideoStoryboardProposal


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


class Core:
    def __init__(self, checkpoint=None, fail_complete=False):
        self.checkpoint = checkpoint
        self.result = None
        self.failure = None
        self.fail_complete = fail_complete
        self.saved = []

    async def get_episode_progress(self, resource):
        return {
            "status": "completed" if self.result is not None else "running",
            "checkpoint": self.checkpoint,
        }

    async def save_episode_checkpoint(self, resource, checkpoint):
        self.checkpoint = copy.deepcopy(checkpoint)
        self.saved.append(copy.deepcopy(checkpoint))

    async def complete_episode(self, resource, result):
        if self.fail_complete:
            raise ConnectionError("回调暂不可用")
        self.result = result

    async def fail_episode(self, resource, code, message):
        self.failure = code


class Model:
    def __init__(self, reviews=None, candidate=None):
        self.calls = []
        self.reviews = list(reviews or [review()])
        self.candidate = candidate or proposal().model_dump(mode="json")

    async def run_turn(self, request, **kwargs):
        self.calls.append((request, kwargs))
        output = self.reviews.pop(0) if kwargs["reviewer"] else self.candidate
        return ModelTurnResult(
            content="",
            toolCalls=[],
            structuredOutput=output,
            finishReason="stop",
            usage=ModelUsage(promptTokens=1, cachedTokens=0, completionTokens=1, totalTokens=2),
        )


def review(decision="pass"):
    return {
        "decision": decision,
        "summary": "检查完成",
        "requiredChanges": ["调整动作"] if decision == "revise" else [],
        "findings": [],
    }


def job():
    return QueueJob(
        jobId="video-episode-task-1",
        kind="video",
        runId="task-1",
        taskId="task-1",
        novelId="novel-1",
        userId="user-1",
        priority=50,
        createdAt=datetime.now(UTC),
        payload={
            "workflow": "episode_script_revise",
            "episodeId": "episode-1",
            "context": context().model_dump(mode="json"),
            "input": {"instruction": "让动作更清楚"},
        },
    )


@pytest.mark.asyncio
async def test_revision_scope_and_complete_candidate_survive_normal_queue():
    core, model = Core(), Model()
    await EpisodeJobHandler(core, model, max_output_tokens=4000)(job())
    assert core.result["candidate"] == proposal().model_dump(mode="json")
    assert core.failure is None
    assert len(model.calls) == 2
    assert all(call[0].maxOutputTokens == 4000 for call in model.calls)
    assert all(call[1]["lane"] == "batch_media" for call in model.calls)
    assert all(call[1]["context"].taskId == "task-1" for call in model.calls)


@pytest.mark.asyncio
async def test_revision_is_bounded_even_if_second_review_still_requests_changes():
    core, model = Core(), Model(reviews=[review("revise"), review("revise")])
    await EpisodeJobHandler(core, model, max_output_tokens=4000)(job())
    assert len(model.calls) == 4
    assert core.result["review"]["decision"] == "revise"


@pytest.mark.asyncio
async def test_callback_replay_uses_saved_candidate_without_model_calls():
    core, model = Core(fail_complete=True), Model()
    handler = EpisodeJobHandler(core, model, max_output_tokens=4000)
    with pytest.raises(ConnectionError):
        await handler(job())
    assert core.checkpoint["phase"] == "complete"
    core.fail_complete = False
    await handler(job())
    assert len(model.calls) == 2
    assert core.result["candidate"] == proposal().model_dump(mode="json")


@pytest.mark.asyncio
async def test_resume_review_never_regenerates_saved_candidate():
    core = Core(
        {
            "phase": "review",
            "cycle": 0,
            "candidate": proposal().model_dump(mode="json"),
            "review": None,
        }
    )
    model = Model()
    await EpisodeJobHandler(core, model, max_output_tokens=4000)(job())
    assert len(model.calls) == 1
    assert model.calls[0][1]["reviewer"] is True


@pytest.mark.asyncio
async def test_unknown_started_call_is_not_repeated():
    core = Core({"phase": "generate_started", "cycle": 0, "candidate": None, "review": None})
    model = Model()
    await EpisodeJobHandler(core, model, max_output_tokens=4000)(job())
    assert core.failure == "MODEL_OUTCOME_UNKNOWN"
    assert not model.calls


@pytest.mark.asyncio
async def test_candidate_cannot_expand_selected_scene_scope():
    invalid = proposal().model_dump(mode="json")
    invalid["scenes"].append(scene("scene-2", "line-2"))
    core, model = Core(), Model(candidate=invalid)
    with pytest.raises(NonRetryableJobError):
        await EpisodeJobHandler(core, model, max_output_tokens=4000)(job())
    assert core.result is None
    assert core.failure == "EPISODE_GENERATION_FAILED"


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "workflow",
    ["episode_script", "episode_script_revise", "episode_storyboard", "episode_storyboard_revise"],
)
async def test_all_four_episode_business_operations_use_plain_queue(workflow):
    current_job = job()
    storyboard = workflow.startswith("episode_storyboard")
    frozen = (_context() if storyboard else context()).model_dump(mode="json")
    candidate = (_proposal() if storyboard else proposal()).model_dump(mode="json")
    if not workflow.endswith("_revise"):
        frozen["operation"] = workflow + "_generate"
        frozen["selectedShotIds" if storyboard else "selectedSceneIds"] = []
        if not storyboard:
            candidate.update(overview={}, endingStates=[], dependencies=[])
    current_job.payload.update(workflow=workflow, context=frozen)
    core, model = Core(), Model(candidate=candidate)
    await EpisodeJobHandler(core, model, max_output_tokens=4000)(current_job)
    expected = (
        VideoStoryboardProposal if storyboard else VideoEpisodeScriptProposal
    ).model_validate(candidate)
    assert core.result["candidate"] == expected.model_dump(mode="json")
    assert len(model.calls) == 2
    assert all(call[0].structuredOutput.route == "chat_json_output_v1" for call in model.calls)


@pytest.mark.asyncio
async def test_successful_callback_logs_core_failure_without_another_model_call():
    class RejectedCore(Core):
        async def get_episode_progress(self, resource):
            return {
                "status": "failed" if self.result is not None else "running",
                "checkpoint": self.checkpoint,
            }

    class WorkflowLog:
        def __init__(self):
            self.finished = []

        def start_run(self, **kwargs):
            pass

        def finish_run(self, run_id, status):
            self.finished.append((run_id, status))

    core, model, log = RejectedCore(), Model(), WorkflowLog()
    handler = EpisodeJobHandler(core, model, max_output_tokens=4000, workflow_log=log)
    with pytest.raises(NonRetryableJobError, match="候选"):
        await handler(job())
    assert log.finished == [("task-1", "failed")]
    assert len(model.calls) == 2
    assert core.failure is None
