from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi import Request
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_contracts.video import (
    AssetBinding,
    CameraBeatSpec,
    CompiledAssetBinding,
    LongSerialSettingSnapshot,
    SceneAssetsStageArguments,
    ScenePromptSpec,
    SeedanceOutputSpec,
    SeedancePromptPackage,
    StoryPlanStageArguments,
    VideoPlanCallReservationRequest,
    VideoPlanCompletionCallback,
    VideoPlanFailureCallback,
    VideoPlanJobPayload,
    VideoPlanProgressQuery,
    VideoStoryPlanCheckpointCallback,
    calculate_video_plan_input_fingerprint,
)
from inkforge_core.db.models import (
    ReviewArtifact,
    VideoGenerationTask,
    VideoProject,
    VideoScene,
    WritingBible,
)
from inkforge_core.errors import ApiError
from inkforge_core.video.internal_router import _verify_callback
from inkforge_core.video.internal_router import router as internal_router
from inkforge_core.video.plan_result import (
    decode_video_plan_terminal_result,
    encode_video_plan_terminal_result,
)
from inkforge_core.video.repository import (
    VideoRepository,
    _load_active_plan_progress,
    _retry_plan_progress_json,
    _validate_callback_binding,
)


def _story_plan(
    *,
    title: str = "雨夜对峙",
    schema_version: str = "2.0",
) -> StoryPlanStageArguments:
    """创建满足紧凑文本、素材闭合与连续时间轴门禁的故事规范。"""

    beat = {
        "beatId": "beat-01",
        "startSecond": 0,
        "endSecond": 4,
        "dramaticPurpose": "建立威胁",
        "performanceDirection": "沈砚压低呼吸并侧耳判断声源",
        "blocking": "沈砚停在门框内侧，身体朝向门外",
        "actionUnits": [
            {
                "subject": "沈砚",
                "action": "侧耳判断异响",
                "visibleResult": "视线锁定门外",
            }
        ],
        "actionComplexity": "simple",
        "sound": "雨滴敲击铁皮，门外传来一次脚步声",
        "referencedAssetIds": ["asset01"],
    }
    if schema_version == "2.0":
        beat["sourceEventAliasesByAction"] = [[]]
    return StoryPlanStageArguments.model_validate(
        {
            "schemaVersion": schema_version,
            "title": title,
            "summary": "沈砚在雨夜发现门后异响",
            "dramaticArc": "警觉逐步升级为正面对峙",
            "visualStyle": "潮湿冷峻的现实主义质感",
            "globalDirection": "动作必须由雨声中的异响触发",
            "assets": [
                {
                    "assetId": "asset01",
                    "modality": "audio",
                    "duty": "ambience",
                    "bindingScope": "scene_direct",
                    "settingReference": None,
                    "featureDomain": "ambience",
                    "keyframeRole": None,
                    "targetEntity": "门外雨声",
                    "includeFeatures": ["雨滴敲击铁皮"],
                    "excludeFeatures": [],
                }
            ],
            "beats": [beat],
            "negativeConstraints": ["禁止无动机改变人物位置"],
        }
    )


def _story_plan_with_misplaced_initial_state() -> StoryPlanStageArguments:
    """构造旧规则下合法、但把初态提前到普通道具入画拍的故事检查点。"""

    return StoryPlanStageArguments.model_validate(
        {
            "title": "潮汐机关",
            "summary": "铜扣先入画，随后才启动机关。",
            "dramaticArc": "从观察升级为不可逆启动。",
            "visualStyle": "低饱和冷调写实。",
            "globalDirection": "保持机关动作顺序清晰。",
            "assets": [
                {
                    "assetId": "asset01",
                    "modality": "image",
                    "duty": "prop",
                    "bindingScope": "scene_direct",
                    "settingReference": None,
                    "featureDomain": "prop",
                    "keyframeRole": None,
                    "targetEntity": "黄铜铜扣",
                    "includeFeatures": ["磨损边缘"],
                    "excludeFeatures": ["现代刻字"],
                },
                {
                    "assetId": "asset02",
                    "modality": "image",
                    "duty": "keyframe",
                    "bindingScope": "scene_direct",
                    "settingReference": None,
                    "featureDomain": "keyframe",
                    "keyframeRole": "initial_state",
                    "targetEntity": "铜扣插入机关前初态",
                    "includeFeatures": ["铜扣与齿槽初始位置"],
                    "excludeFeatures": ["碎裂结果"],
                },
            ],
            "beats": [
                {
                    "beatId": "beat-01",
                    "startSecond": 0,
                    "endSecond": 4,
                    "dramaticPurpose": "建立铜扣",
                    "performanceDirection": "人物低头观察铜扣",
                    "blocking": "人物与铜扣位于画面左侧",
                    "actionUnits": [
                        {
                            "subject": "人物",
                            "action": "拿起铜扣",
                            "visibleResult": "铜扣进入画面",
                        }
                    ],
                    "actionComplexity": "simple",
                    "sound": "手指摩擦金属声",
                    "referencedAssetIds": ["asset01", "asset02"],
                },
                {
                    "beatId": "beat-02",
                    "startSecond": 4,
                    "endSecond": 8,
                    "dramaticPurpose": "启动机关",
                    "performanceDirection": "人物收紧手指后松开",
                    "blocking": "铜扣从左侧移入中央齿槽",
                    "actionUnits": [
                        {
                            "subject": "铜扣",
                            "action": "插入齿槽",
                            "visibleResult": "机关开始转动",
                        }
                    ],
                    "actionComplexity": "mechanical_sequence",
                    "sound": "金属卡合与齿轮转动声",
                    "referencedAssetIds": ["asset01"],
                },
            ],
            "negativeConstraints": ["禁止现代机械外观"],
        }
    )


def _scene_assets_plan(*, title: str = "雨夜对峙") -> SceneAssetsStageArguments:
    story = _story_plan(title=title)
    payload = story.model_dump(mode="json", exclude={"beats"})
    payload["schemaVersion"] = "1.0"
    return SceneAssetsStageArguments.model_validate(payload)


def _resources(
    *,
    status: str = "submitted",
    result_json: str | None = None,
) -> tuple[VideoGenerationTask, VideoScene, VideoProject, WritingBible]:
    """建立六重身份一致且属于长篇的规划任务事实。"""

    payload = VideoPlanJobPayload(
        projectId="project-1",
        sceneId="scene-1",
        chapterId="chapter-1",
        title="雨夜对峙",
        sourceText="沈砚在雨夜听见门后异响。",
        durationSeconds=15,
        ratio="16:9",
        settingSnapshot=LongSerialSettingSnapshot.from_entries([]),
        planningRoute="responses_json_schema_v1",
        directorDraftVersion="1.1",
    )
    task = VideoGenerationTask(
        id="task-1",
        jobId="video-plan-task-1",
        projectId="project-1",
        sceneId="scene-1",
        kind="plan",
        provider="deepseek",
        status=status,
        idempotencyKey="video-plan:scene-1:1",
        requestJson=payload.model_dump_json(),
        resultJson=result_json,
        updatedAt=datetime.now(UTC),
    )
    scene = VideoScene(id="scene-1", projectId="project-1")
    project = VideoProject(
        id="project-1",
        novelId="novel-1",
        title="视频项目",
        mode="highlight",
    )
    bible = WritingBible(
        id="bible-1",
        novelId="novel-1",
        storyLengthProfile="long_serial",
    )
    return task, scene, project, bible


def _identity() -> dict[str, str]:
    return {
        "protocolVersion": "1.0",
        "jobId": "video-plan-task-1",
        "runId": "task-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "projectId": "project-1",
        "sceneId": "scene-1",
    }


def _reserve(
    *,
    event_id: str,
    checkpoint_stage: str,
    stage: str,
    expected_calls: int,
) -> VideoPlanCallReservationRequest:
    return VideoPlanCallReservationRequest.model_validate(
        {
            **_identity(),
            "eventId": event_id,
            "checkpointStage": checkpoint_stage,
            "stage": stage,
            "expectedReservedCalls": expected_calls,
        }
    )


def _checkpoint(
    *,
    event_id: str,
    checkpoint_stage: str,
    reserved_calls: int,
    scene_assets_plan: SceneAssetsStageArguments | None = None,
    story_plan: StoryPlanStageArguments | None = None,
) -> VideoStoryPlanCheckpointCallback:
    return VideoStoryPlanCheckpointCallback.model_validate(
        {
            **_identity(),
            "eventId": event_id,
            "checkpointStage": checkpoint_stage,
            "sceneAssetsPlan": (
                scene_assets_plan.model_dump(mode="json") if scene_assets_plan is not None else None
            ),
            "storyPlan": (story_plan.model_dump(mode="json") if story_plan is not None else None),
            "attemptState": {
                "reservedCalls": reserved_calls,
                "pendingStage": None,
            },
        }
    )


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        del args


class _CheckpointSession:
    """为进度事务提供锁定资源、latest task 与长篇事实。"""

    def __init__(
        self,
        task: VideoGenerationTask,
        scene: VideoScene,
        project: VideoProject,
        bible: WritingBible,
        *,
        latest_task_id: str | None = None,
    ) -> None:
        self.task = task
        self.scene = scene
        self.project = project
        self.bible = bible
        self.latest_task_id = latest_task_id or task.id
        self.scalar_calls = 0
        self.added: list[object] = []

    async def __aenter__(self) -> _CheckpointSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    def begin(self) -> _Transaction:
        return _Transaction()

    async def get(
        self,
        model: object,
        object_id: str,
        *,
        with_for_update: bool = False,
    ) -> object | None:
        del with_for_update
        candidates = {
            VideoGenerationTask: self.task,
            VideoScene: self.scene,
            VideoProject: self.project,
        }
        value = candidates.get(model)
        return value if value is not None and value.id == object_id else None

    async def scalar(self, statement: object) -> object | None:
        del statement
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return self.latest_task_id
        if self.scalar_calls == 2:
            return self.bible
        if self.scalar_calls == 3:
            # 首次成功候选没有既存 ReviewArtifact。
            return None
        raise AssertionError("视频规划事务执行了未预期的额外查询")

    def add(self, value: object) -> None:
        self.added.append(value)


class _CheckpointSessionFactory:
    def __init__(
        self,
        task: VideoGenerationTask,
        scene: VideoScene,
        project: VideoProject,
        bible: WritingBible,
        *,
        latest_task_id: str | None = None,
    ) -> None:
        self._resources = (task, scene, project, bible)
        self._latest_task_id = latest_task_id
        self.sessions: list[_CheckpointSession] = []

    def __call__(self) -> _CheckpointSession:
        session = _CheckpointSession(
            *self._resources,
            latest_task_id=self._latest_task_id,
        )
        self.sessions.append(session)
        return session


@pytest.mark.asyncio
async def test_empty_progress_and_first_reservation_are_durable_and_idempotent() -> None:
    task, scene, project, bible = _resources()
    factory = _CheckpointSessionFactory(task, scene, project, bible)
    repository = VideoRepository(factory)  # type: ignore[arg-type]

    empty = await repository.get_plan_progress(VideoPlanProgressQuery.model_validate(_identity()))
    assert empty.checkpointStage == "empty"
    assert empty.inputFingerprint == calculate_video_plan_input_fingerprint(
        VideoPlanJobPayload.model_validate_json(task.requestJson)
    )
    assert empty.attemptState.reservedCalls == 0
    assert empty.attemptState.pendingStage is None

    request = _reserve(
        event_id="reserve-assets-1",
        checkpoint_stage="empty",
        stage="scene_assets",
        expected_calls=0,
    )
    first = await repository.reserve_plan_call(request)
    replay = await repository.reserve_plan_call(request)

    assert replay == first
    assert first.reservedCallsBefore == 0
    assert first.attemptState.reservedCalls == 1
    assert first.attemptState.pendingStage == "scene_assets"
    durable = _load_active_plan_progress(task.resultJson)
    assert len(durable.reservations) == 1
    assert json.loads(task.resultJson or "{}")["kind"] == ("video_plan_progress_checkpoint")

    with pytest.raises(ApiError) as reused_event:
        await repository.reserve_plan_call(
            _reserve(
                event_id="reserve-assets-1",
                checkpoint_stage="empty",
                stage="scene_assets",
                expected_calls=1,
            )
        )
    assert reused_event.value.code == "VIDEO_PLAN_RESERVATION_EVENT_CONFLICT"


@pytest.mark.asyncio
async def test_progress_rejects_corrupted_frozen_input_before_model_reservation() -> None:
    """冻结任务载荷损坏时必须在 Agent 预留任何模型调用前失败。"""

    task, scene, project, bible = _resources()
    task.requestJson = "{}"
    repository = VideoRepository(  # type: ignore[arg-type]
        _CheckpointSessionFactory(task, scene, project, bible)
    )

    with pytest.raises(ApiError) as caught:
        await repository.get_plan_progress(VideoPlanProgressQuery.model_validate(_identity()))

    assert caught.value.code == "VIDEO_PLAN_INPUT_INVALID"


@pytest.mark.asyncio
async def test_progress_rejects_non_deepseek_plan_task() -> None:
    """阶段恢复端点不能被其他供应商或视频生成任务借用。"""

    task, scene, project, bible = _resources()
    task.provider = "seedance"
    repository = VideoRepository(  # type: ignore[arg-type]
        _CheckpointSessionFactory(task, scene, project, bible)
    )

    with pytest.raises(ApiError) as caught:
        await repository.get_plan_progress(VideoPlanProgressQuery.model_validate(_identity()))

    assert caught.value.code == "VIDEO_PLAN_TASK_REQUIRED"


@pytest.mark.asyncio
async def test_checkpoint_advances_monotonically_and_preserves_attempt_ledger() -> None:
    task, scene, project, bible = _resources()
    factory = _CheckpointSessionFactory(task, scene, project, bible)
    repository = VideoRepository(factory)  # type: ignore[arg-type]
    assets = _scene_assets_plan()
    story = _story_plan()

    await repository.reserve_plan_call(
        _reserve(
            event_id="reserve-assets-1",
            checkpoint_stage="empty",
            stage="scene_assets",
            expected_calls=0,
        )
    )
    assets_checkpoint = _checkpoint(
        event_id="checkpoint-assets",
        checkpoint_stage="scene_assets",
        reserved_calls=1,
        scene_assets_plan=assets,
    )
    await repository.save_story_plan_checkpoint(assets_checkpoint)
    await repository.save_story_plan_checkpoint(assets_checkpoint)

    after_assets = await repository.get_plan_progress(
        VideoPlanProgressQuery.model_validate(_identity())
    )
    assert after_assets.checkpointStage == "scene_assets"
    assert after_assets.sceneAssetsPlan == assets
    assert after_assets.storyPlan is None
    assert after_assets.attemptState.reservedCalls == 1
    assert after_assets.attemptState.pendingStage is None

    await repository.reserve_plan_call(
        _reserve(
            event_id="reserve-story-1",
            checkpoint_stage="scene_assets",
            stage="story_beats",
            expected_calls=1,
        )
    )
    await repository.save_story_plan_checkpoint(
        _checkpoint(
            event_id="checkpoint-story",
            checkpoint_stage="story",
            reserved_calls=2,
            story_plan=story,
        )
    )
    after_story = await repository.get_plan_progress(
        VideoPlanProgressQuery.model_validate(_identity())
    )
    assert after_story.checkpointStage == "story"
    assert after_story.storyPlan == story
    assert after_story.sceneAssetsPlan is None
    assert after_story.attemptState.reservedCalls == 2
    assert len(_load_active_plan_progress(task.resultJson).reservations) == 2
    assert all(session.added == [] for session in factory.sessions)


def test_failed_story_checkpoint_seeds_new_retry_without_old_reservations() -> None:
    """显式重试只继承 canonical 故事，不继承旧任务 pending 与调用事件。"""

    task, _scene, _project, _bible = _resources(status="failed")
    source_payload = VideoPlanJobPayload.model_validate_json(task.requestJson)
    progress_json = json.dumps(
        {
            "kind": "video_plan_progress_checkpoint",
            "schemaVersion": "2.0",
            "checkpointStage": "story",
            "sceneAssetsPlan": None,
            "storyPlan": _story_plan().model_dump(mode="json"),
            "attemptState": {
                "reservedCalls": 3,
                "inheritedCalls": 0,
                "pendingStage": "cinematography",
            },
            "inheritedFromTaskId": None,
            "inheritedInputFingerprint": None,
            "reservations": [
                {
                    "eventId": "reserve-assets",
                    "checkpointStage": "empty",
                    "stage": "scene_assets",
                    "reservedCallsBefore": 0,
                },
                {
                    "eventId": "reserve-story",
                    "checkpointStage": "scene_assets",
                    "stage": "story_beats",
                    "reservedCallsBefore": 1,
                },
                {
                    "eventId": "reserve-camera",
                    "checkpointStage": "story",
                    "stage": "cinematography",
                    "reservedCallsBefore": 2,
                },
            ],
        },
        ensure_ascii=False,
    )
    task.resultJson = encode_video_plan_terminal_result(
        progress_json=progress_json,
        status="failed",
        event_id="fail-1",
        result={"code": "VIDEO_PLAN_FAILED", "message": "失败", "recoverable": True},
    )
    target_payload = source_payload.model_copy(update={"directorDraftVersion": "1.4"})

    inherited_json = _retry_plan_progress_json(
        task,
        source_payload=source_payload,
        target_payload=target_payload,
    )

    assert inherited_json is not None
    inherited = _load_active_plan_progress(inherited_json)
    assert inherited.checkpoint_stage == "story"
    assert inherited.story_plan == _story_plan()
    assert inherited.attempt_state.reservedCalls == 0
    assert inherited.attempt_state.inheritedCalls == 2
    assert inherited.attempt_state.pendingStage is None
    assert inherited.reservations == ()
    assert inherited.inherited_from_task_id == task.id

    reservation = VideoPlanCallReservationRequest.model_validate(
        {
            **_identity(),
            "eventId": "retry-camera",
            "checkpointStage": "story",
            "stage": "cinematography",
            "expectedReservedCalls": 0,
            "inheritedCalls": 2,
        }
    )
    assert reservation.inheritedCalls == 2


def test_prompt_overflow_retry_discards_story_checkpoint() -> None:
    """最终 Provider 超长时必须从素材重跑，摄影不能独自缩短上游 canonical 内容。"""

    task, _scene, _project, _bible = _resources(status="failed")
    payload = VideoPlanJobPayload.model_validate_json(task.requestJson)
    progress_json = json.dumps(
        {
            "kind": "video_plan_progress_checkpoint",
            "schemaVersion": "2.0",
            "checkpointStage": "story",
            "sceneAssetsPlan": None,
            "storyPlan": _story_plan().model_dump(mode="json"),
            "attemptState": {
                "reservedCalls": 3,
                "inheritedCalls": 0,
                "pendingStage": "cinematography",
            },
            "inheritedFromTaskId": None,
            "inheritedInputFingerprint": None,
            "reservations": [
                {
                    "eventId": "reserve-assets",
                    "checkpointStage": "empty",
                    "stage": "scene_assets",
                    "reservedCallsBefore": 0,
                },
                {
                    "eventId": "reserve-story",
                    "checkpointStage": "scene_assets",
                    "stage": "story_beats",
                    "reservedCallsBefore": 1,
                },
                {
                    "eventId": "reserve-camera",
                    "checkpointStage": "story",
                    "stage": "cinematography",
                    "reservedCallsBefore": 2,
                },
            ],
        },
        ensure_ascii=False,
    )
    task.resultJson = encode_video_plan_terminal_result(
        progress_json=progress_json,
        status="failed",
        event_id="fail-overflow",
        result={
            "code": "VIDEO_PLAN_FAILED",
            "message": (
                "VIDEO_SCENE_PLAN_INVALID：摄影灯光阶段：编译后的 Provider 中文提示词"
                "超出产品安全上限：2239/2000 字；禁止静默截断"
            ),
            "recoverable": True,
        },
    )

    inherited_json = _retry_plan_progress_json(
        task,
        source_payload=payload,
        target_payload=payload,
    )

    assert inherited_json is None


def test_initial_keyframe_failure_retry_downgrades_story_to_scene_assets() -> None:
    """旧故事错放初态时只继承可信素材，并从故事阶段重新生成。"""

    task, _scene, _project, _bible = _resources(status="failed")
    payload = VideoPlanJobPayload.model_validate_json(task.requestJson)
    story = _story_plan_with_misplaced_initial_state()
    progress_json = json.dumps(
        {
            "kind": "video_plan_progress_checkpoint",
            "schemaVersion": "2.0",
            "checkpointStage": "story",
            "sceneAssetsPlan": None,
            "storyPlan": story.model_dump(mode="json"),
            "attemptState": {
                "reservedCalls": 3,
                "inheritedCalls": 0,
                "pendingStage": "cinematography",
            },
            "inheritedFromTaskId": None,
            "inheritedInputFingerprint": None,
            "reservations": [
                {
                    "eventId": "reserve-assets",
                    "checkpointStage": "empty",
                    "stage": "scene_assets",
                    "reservedCallsBefore": 0,
                },
                {
                    "eventId": "reserve-story",
                    "checkpointStage": "scene_assets",
                    "stage": "story_beats",
                    "reservedCallsBefore": 1,
                },
                {
                    "eventId": "reserve-camera",
                    "checkpointStage": "story",
                    "stage": "cinematography",
                    "reservedCallsBefore": 2,
                },
            ],
        },
        ensure_ascii=False,
    )
    task.resultJson = encode_video_plan_terminal_result(
        progress_json=progress_json,
        status="failed",
        event_id="fail-initial-state",
        result={
            "code": "VIDEO_PLAN_FAILED",
            "message": (
                "VIDEO_SCENE_PLAN_INVALID：摄影灯光阶段："
                "VIDEO_PLAN_INITIAL_KEYFRAME_REQUIRED：首个机械拍缺少初态"
            ),
            "recoverable": True,
        },
    )

    inherited_json = _retry_plan_progress_json(
        task,
        source_payload=payload,
        target_payload=payload,
    )

    assert inherited_json is not None
    inherited = _load_active_plan_progress(inherited_json)
    assert inherited.checkpoint_stage == "scene_assets"
    assert inherited.scene_assets_plan is not None
    assert inherited.scene_assets_plan.assets == story.assets
    assert inherited.story_plan is None
    assert inherited.attempt_state.inheritedCalls == 1
    assert inherited.reservations == ()


def test_initial_keyframe_failure_without_initial_asset_restarts_from_empty() -> None:
    """故事本身没有初态素材时不能伪造降级检查点。"""

    task, _scene, _project, _bible = _resources(status="failed")
    payload = VideoPlanJobPayload.model_validate_json(task.requestJson)
    progress_json = json.dumps(
        {
            "kind": "video_plan_progress_checkpoint",
            "schemaVersion": "2.0",
            "checkpointStage": "story",
            "sceneAssetsPlan": None,
            "storyPlan": _story_plan().model_dump(mode="json"),
            "attemptState": {
                "reservedCalls": 2,
                "inheritedCalls": 0,
                "pendingStage": None,
            },
            "inheritedFromTaskId": None,
            "inheritedInputFingerprint": None,
            "reservations": [
                {
                    "eventId": "reserve-assets",
                    "checkpointStage": "empty",
                    "stage": "scene_assets",
                    "reservedCallsBefore": 0,
                },
                {
                    "eventId": "reserve-story",
                    "checkpointStage": "scene_assets",
                    "stage": "story_beats",
                    "reservedCallsBefore": 1,
                },
            ],
        },
        ensure_ascii=False,
    )
    task.resultJson = encode_video_plan_terminal_result(
        progress_json=progress_json,
        status="failed",
        event_id="fail-missing-initial-state",
        result={
            "code": "VIDEO_PLAN_FAILED",
            "message": "VIDEO_PLAN_INITIAL_KEYFRAME_REQUIRED：缺少初态",
            "recoverable": True,
        },
    )

    inherited_json = _retry_plan_progress_json(
        task,
        source_payload=payload,
        target_payload=payload,
    )

    assert inherited_json is None


@pytest.mark.asyncio
async def test_checkpoint_rejects_missing_pending_jump_and_changed_frozen_assets() -> None:
    task, scene, project, bible = _resources()
    repository = VideoRepository(  # type: ignore[arg-type]
        _CheckpointSessionFactory(task, scene, project, bible)
    )
    assets = _scene_assets_plan()

    with pytest.raises(ApiError) as no_pending:
        await repository.save_story_plan_checkpoint(
            _checkpoint(
                event_id="checkpoint-assets",
                checkpoint_stage="scene_assets",
                reserved_calls=1,
                scene_assets_plan=assets,
            )
        )
    assert no_pending.value.code == "VIDEO_PLAN_CHECKPOINT_ATTEMPT_CONFLICT"

    await repository.reserve_plan_call(
        _reserve(
            event_id="reserve-assets-1",
            checkpoint_stage="empty",
            stage="scene_assets",
            expected_calls=0,
        )
    )
    with pytest.raises(ApiError) as jump:
        await repository.save_story_plan_checkpoint(
            _checkpoint(
                event_id="checkpoint-story",
                checkpoint_stage="story",
                reserved_calls=2,
                story_plan=_story_plan(),
            )
        )
    assert jump.value.code in {
        "VIDEO_PLAN_CHECKPOINT_ATTEMPT_CONFLICT",
        "VIDEO_PLAN_CHECKPOINT_TRANSITION_INVALID",
    }

    await repository.save_story_plan_checkpoint(
        _checkpoint(
            event_id="checkpoint-assets",
            checkpoint_stage="scene_assets",
            reserved_calls=1,
            scene_assets_plan=assets,
        )
    )
    await repository.reserve_plan_call(
        _reserve(
            event_id="reserve-story-1",
            checkpoint_stage="scene_assets",
            stage="story_beats",
            expected_calls=1,
        )
    )
    with pytest.raises(ApiError) as changed_assets:
        await repository.save_story_plan_checkpoint(
            _checkpoint(
                event_id="checkpoint-story-changed",
                checkpoint_stage="story",
                reserved_calls=2,
                story_plan=_story_plan(title="改写后的标题"),
            )
        )
    assert changed_assets.value.code == "VIDEO_PLAN_STORY_CHANGED_SCENE_ASSETS"


@pytest.mark.asyncio
async def test_reservation_cas_and_global_five_call_limit() -> None:
    task, scene, project, bible = _resources()
    repository = VideoRepository(  # type: ignore[arg-type]
        _CheckpointSessionFactory(task, scene, project, bible)
    )

    await repository.reserve_plan_call(
        _reserve(
            event_id="assets-first",
            checkpoint_stage="empty",
            stage="scene_assets",
            expected_calls=0,
        )
    )
    with pytest.raises(ApiError) as stale_count:
        await repository.reserve_plan_call(
            _reserve(
                event_id="assets-stale",
                checkpoint_stage="empty",
                stage="scene_assets",
                expected_calls=0,
            )
        )
    assert stale_count.value.code == "VIDEO_PLAN_RESERVATION_COUNT_CONFLICT"

    await repository.reserve_plan_call(
        _reserve(
            event_id="assets-correction",
            checkpoint_stage="empty",
            stage="scene_assets",
            expected_calls=1,
        )
    )
    await repository.save_story_plan_checkpoint(
        _checkpoint(
            event_id="assets-done",
            checkpoint_stage="scene_assets",
            reserved_calls=2,
            scene_assets_plan=_scene_assets_plan(),
        )
    )
    await repository.reserve_plan_call(
        _reserve(
            event_id="story-first",
            checkpoint_stage="scene_assets",
            stage="story_beats",
            expected_calls=2,
        )
    )
    await repository.save_story_plan_checkpoint(
        _checkpoint(
            event_id="story-done",
            checkpoint_stage="story",
            reserved_calls=3,
            story_plan=_story_plan(),
        )
    )
    fourth = await repository.reserve_plan_call(
        _reserve(
            event_id="camera-first",
            checkpoint_stage="story",
            stage="cinematography",
            expected_calls=3,
        )
    )
    assert fourth.attemptState.reservedCalls == 4
    fifth = await repository.reserve_plan_call(
        _reserve(
            event_id="camera-correction",
            checkpoint_stage="story",
            stage="cinematography",
            expected_calls=4,
        )
    )
    assert fifth.attemptState.reservedCalls == 5
    assert len(_load_active_plan_progress(task.resultJson).reservations) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "failed"])
async def test_terminal_progress_hides_plans_and_pending(status: str) -> None:
    task, scene, project, bible = _resources()
    repository = VideoRepository(  # type: ignore[arg-type]
        _CheckpointSessionFactory(task, scene, project, bible)
    )
    await repository.reserve_plan_call(
        _reserve(
            event_id="assets-first",
            checkpoint_stage="empty",
            stage="scene_assets",
            expected_calls=0,
        )
    )
    task.status = status

    progress = await repository.get_plan_progress(
        VideoPlanProgressQuery.model_validate(_identity())
    )
    assert progress.status == status
    assert progress.checkpointStage == "terminal"
    assert progress.sceneAssetsPlan is None
    assert progress.storyPlan is None
    assert progress.attemptState.reservedCalls == 1
    assert progress.attemptState.pendingStage is None


@pytest.mark.asyncio
async def test_terminal_callbacks_preserve_ledger_and_require_exact_replay() -> None:
    task, scene, project, bible = _resources()
    factory = _CheckpointSessionFactory(task, scene, project, bible)
    repository = VideoRepository(factory)  # type: ignore[arg-type]
    await repository.reserve_plan_call(
        _reserve(
            event_id="assets-first",
            checkpoint_stage="empty",
            stage="scene_assets",
            expected_calls=0,
        )
    )
    saved_ledger = task.resultJson
    failure = VideoPlanFailureCallback(
        **_identity(),
        eventId="fail-1",
        code="VIDEO_PLAN_FAILED",
        message="素材阶段失败",
        recoverable=False,
    )
    await repository.fail_plan(failure)
    failed_terminal = decode_video_plan_terminal_result(task.resultJson)
    assert failed_terminal is not None
    assert failed_terminal.status == "failed"
    assert failed_terminal.event_id == failure.eventId
    assert failed_terminal.result == {
        "code": failure.code,
        "message": failure.message,
        "recoverable": False,
    }
    assert failed_terminal.progress == json.loads(saved_ledger or "null")

    await repository.fail_plan(failure)
    with pytest.raises(ApiError) as changed_failure:
        await repository.fail_plan(
            failure.model_copy(update={"message": "同一事件换成另一条错误"})
        )
    assert changed_failure.value.code == "VIDEO_PLAN_TERMINAL_CALLBACK_CONFLICT"

    # 用新的活动事实验证成功回调保留临时进度并创建正式候选。
    task.status = "submitted"
    task.resultJson = saved_ledger
    scene.status = "generating"
    scene.chapterId = "chapter-1"
    scene.title = "雨夜对峙"
    task.requestJson = VideoPlanJobPayload(
        projectId=project.id,
        sceneId=scene.id,
        chapterId=scene.chapterId,
        title=scene.title,
        sourceText="沈砚在雨夜听见门外异响。",
        durationSeconds=4,
        ratio="16:9",
        settingSnapshot=LongSerialSettingSnapshot.from_entries([]),
    ).model_dump_json()
    output = SeedanceOutputSpec(durationSeconds=4)
    scene_plan = ScenePromptSpec(
        sceneId=scene.id,
        title=scene.title,
        summary="沈砚确认门外威胁",
        visualStyle="冷峻现实主义",
        globalDirection="动作由异响触发",
        assets=[
            AssetBinding(
                assetId="asset01",
                modality="audio",
                duty="ambience",
                targetEntity="门外雨声",
                includeFeatures=["雨滴敲击铁皮"],
                excludeFeatures=[],
            )
        ],
        beats=[
            CameraBeatSpec(
                beatId="beat-01",
                startSecond=0,
                endSecond=4,
                shotSize="中景",
                cameraAngle="平视",
                cameraMovement="固定机位",
                action="沈砚侧耳判断门外异响",
                referencedAssetIds=["asset01"],
            )
        ],
        negativeConstraints=["禁止无动机移动"],
        output=output,
    )
    prompt = "雨夜门外传来异响"
    prompt_package = SeedancePromptPackage(
        sceneId=scene.id,
        prompt=prompt,
        promptCharacterCount=len(prompt),
        assetBindings=[
            CompiledAssetBinding(
                assetId="asset01",
                mediaAssetId=None,
                alias="@素材1",
                modality="audio",
                duty="ambience",
                bindingScope="scene_direct",
                settingReference=None,
                featureDomain="ambience",
                keyframeRole=None,
                targetEntity="门外雨声",
                isFixture=True,
            )
        ],
        output=output,
        previewOnly=True,
        assetReady=False,
        submissionReady=False,
        fixtureOnly=True,
    )
    completion = VideoPlanCompletionCallback(
        **_identity(),
        eventId="complete-1",
        scenePlan=scene_plan,
        promptPackage=prompt_package,
    )
    await repository.complete_plan(completion)
    assert task.status == "completed"
    completed_terminal = decode_video_plan_terminal_result(task.resultJson)
    assert completed_terminal is not None
    assert completed_terminal.status == "completed"
    assert completed_terminal.event_id == completion.eventId
    assert completed_terminal.result["applyTarget"] == {
        "type": "video_scene_plan",
        "sceneId": scene.id,
    }
    assert completed_terminal.progress == json.loads(saved_ledger or "null")
    assert any(isinstance(value, ReviewArtifact) for value in factory.sessions[-1].added)
    terminal_progress = await repository.get_plan_progress(
        VideoPlanProgressQuery.model_validate(_identity())
    )
    assert terminal_progress.status == "completed"
    assert terminal_progress.attemptState.reservedCalls == 1
    assert terminal_progress.attemptState.pendingStage is None

    await repository.complete_plan(completion)
    with pytest.raises(ApiError) as changed_completion:
        await repository.complete_plan(
            completion.model_copy(update={"eventId": "complete-2"})
        )
    assert changed_completion.value.code == "VIDEO_PLAN_TERMINAL_CALLBACK_CONFLICT"

    with pytest.raises(ApiError) as contradictory_failure:
        await repository.fail_plan(failure)
    assert contradictory_failure.value.code == "VIDEO_PLAN_TERMINAL_CALLBACK_CONFLICT"


def test_sixfold_binding_includes_deterministic_run_identity() -> None:
    task, scene, project, _bible = _resources()
    mismatched = VideoPlanProgressQuery.model_validate(
        {**_identity(), "runId": "run-from-other-task"}
    )
    with pytest.raises(ApiError) as caught:
        _validate_callback_binding(task, scene, project, mismatched)
    assert caught.value.code == "VIDEO_CALLBACK_RESOURCE_MISMATCH"


@pytest.mark.asyncio
async def test_reserve_rejects_stale_task_and_non_long_serial() -> None:
    task, scene, project, bible = _resources()
    request = _reserve(
        event_id="assets-first",
        checkpoint_stage="empty",
        stage="scene_assets",
        expected_calls=0,
    )
    stale_repository = VideoRepository(  # type: ignore[arg-type]
        _CheckpointSessionFactory(
            task,
            scene,
            project,
            bible,
            latest_task_id="task-newer",
        )
    )
    with pytest.raises(ApiError) as stale:
        await stale_repository.reserve_plan_call(request)
    assert stale.value.code == "VIDEO_CALLBACK_STALE_ATTEMPT"

    short_bible = WritingBible(
        id="bible-short",
        novelId="novel-1",
        storyLengthProfile="short_medium",
    )
    short_repository = VideoRepository(  # type: ignore[arg-type]
        _CheckpointSessionFactory(task, scene, project, short_bible)
    )
    with pytest.raises(ApiError) as short:
        await short_repository.reserve_plan_call(request)
    assert short.value.code == "VIDEO_LONG_SERIAL_REQUIRED"


class _Verifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def verify_request(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_progress_checkpoint_and_reservation_share_signed_video_write_scope() -> None:
    routes = {(route.path, frozenset(route.methods or set())) for route in internal_router.routes}
    for suffix in ("progress", "story-checkpoint", "call-reservations"):
        assert (
            f"/internal/v1/video/scenes/{{scene_id}}/{suffix}",
            frozenset({"POST"}),
        ) in routes

    body = b'{"protocolVersion":"1.0"}'

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/v1/video/scenes/scene-1/call-reservations",
            "query_string": b"",
            "headers": [
                (b"authorization", b"Bearer signed-token"),
                (b"idempotency-key", b"reserve-task-1"),
                (b"x-inkforge-timestamp", b"1720000000"),
                (b"x-inkforge-body-sha256", b"body-hash"),
            ],
            "client": ("127.0.0.1", 32000),
        },
        receive,
    )
    verifier = _Verifier()
    await _verify_callback(
        request,
        verifier,  # type: ignore[arg-type]
        task_id="task-1",
        run_id="task-1",
        novel_id="novel-1",
    )
    assert verifier.calls[0]["required_scope"] == ServiceScope.VIDEO_WRITE
