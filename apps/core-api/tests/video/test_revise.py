from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest
from inkforge_contracts.video import (
    AssetBinding,
    CameraBeatSpec,
    LongSerialSettingSnapshot,
    ScenePromptSpec,
    SeedanceOutputSpec,
    VideoPlanJobPayload,
)
from inkforge_core.db.models import (
    ReviewArtifact,
    ReviewArtifactRevision,
    VideoGenerationTask,
    VideoProject,
    VideoScene,
    WritingBible,
)
from inkforge_core.errors import ApiError
from inkforge_core.video.repository import (
    VideoRepository,
    _apply_revised_artifact,
    _artifact_revision_snapshot,
    _scene_response,
    _validate_artifact_matches_task,
    _validate_revise_replay_payload,
)
from inkforge_core.video.schemas import (
    ReviseVideoSceneRequest,
)
from pydantic import ValidationError


def _payload(*, instruction: str | None = "加强动作触发后的摄影机响应") -> VideoPlanJobPayload:
    """创建只包含冻结事实和可选返工意见的最小任务载荷。"""

    return VideoPlanJobPayload(
        projectId="project-1",
        sceneId="scene-1",
        chapterId="chapter-1",
        title="机关启动",
        sourceText="林默把铜扣插入木匣，机关开始转动。",
        durationSeconds=15,
        ratio="16:9",
        settingSnapshot=LongSerialSettingSnapshot.from_entries([]),
        revisionInstruction=instruction,
        planningRoute="responses_json_schema_v1",
        directorDraftVersion="1.1",
    )


def _scene_and_project() -> tuple[VideoScene, VideoProject]:
    payload = _payload()
    scene = VideoScene(
        id=payload.sceneId,
        projectId=payload.projectId,
        chapterId=payload.chapterId,
        title=payload.title,
        sourceText=payload.sourceText,
        sourceHash=hashlib.sha256(payload.sourceText.encode()).hexdigest(),
        durationSeconds=payload.durationSeconds,
    )
    project = VideoProject(
        id=payload.projectId,
        novelId="novel-1",
        title="项目",
        mode="highlight",
        targetAspectRatio="16:9",
    )
    return scene, project


def _candidate_json() -> str:
    """创建可由共享契约完整读取的旧候选，供返工基线测试复用。"""

    plan = ScenePromptSpec(
        sceneId="scene-1",
        title="机关启动",
        summary="林默插入铜扣后机关开始转动",
        visualStyle="冷峻写实",
        globalDirection="保持动作因果清楚",
        assets=[
            AssetBinding(
                assetId="asset01",
                modality="image",
                duty="prop",
                targetEntity="木匣",
                includeFeatures=["旧木与黄铜机关"],
                excludeFeatures=["现代电子元件"],
            )
        ],
        beats=[
            CameraBeatSpec(
                beatId="beat-01",
                startSecond=0,
                endSecond=15,
                shotSize="中景",
                cameraAngle="平视",
                cameraMovement="固定机位",
                action="林默把铜扣插入木匣，机关开始转动",
                referencedAssetIds=["asset01"],
            )
        ],
        negativeConstraints=["禁止现代电子元件"],
        output=SeedanceOutputSpec(durationSeconds=15),
    )
    return json.dumps(
        {
            "scenePlan": plan.model_dump(mode="json"),
            "promptPackage": {"prompt": "旧候选"},
        },
        ensure_ascii=False,
    )


def test_revise_request_strips_text_and_rejects_invalid_boundaries() -> None:
    request = ReviseVideoSceneRequest(
        clientRequestId=" 0123456789abcdef ",
        expectedArtifactRevision=2,
        userMessage="  镜头应由木匣启动后再推进  ",
    )

    assert request.clientRequestId == "0123456789abcdef"
    assert request.userMessage == "镜头应由木匣启动后再推进"

    invalid_values = [
        {
            "clientRequestId": "too-short",
            "expectedArtifactRevision": 2,
            "userMessage": "返工",
        },
        {
            "clientRequestId": "0123456789abcdef",
            "expectedArtifactRevision": 0,
            "userMessage": "返工",
        },
        {
            "clientRequestId": "0123456789abcdef",
            "expectedArtifactRevision": 2,
            "userMessage": "   ",
        },
        {
            "clientRequestId": "0123456789abcdef",
            "expectedArtifactRevision": 2,
            "userMessage": "甲" * 2_001,
        },
    ]
    for value in invalid_values:
        with pytest.raises(ValidationError):
            ReviseVideoSceneRequest.model_validate(value)


def test_revise_idempotent_replay_requires_same_frozen_payload_and_message() -> None:
    scene, project = _scene_and_project()
    payload = _payload()
    task = VideoGenerationTask(
        id="task-1",
        projectId=project.id,
        sceneId=scene.id,
        kind="plan",
        requestJson=payload.model_dump_json(),
    )

    assert (
        _validate_revise_replay_payload(
            task,
            scene,
            project,
            "加强动作触发后的摄影机响应",
        )
        == payload
    )
    with pytest.raises(ApiError) as caught:
        _validate_revise_replay_payload(task, scene, project, "改成固定机位")
    assert caught.value.code == "VIDEO_REVISE_IDEMPOTENCY_CONFLICT"


def test_revise_snapshots_full_candidate_before_reusing_artifact() -> None:
    artifact = ReviewArtifact(
        id="artifact-1",
        novelId="novel-1",
        videoSceneId="scene-1",
        kind="video_scene_plan",
        status="awaiting_user",
        payloadJson='{"scenePlan":{"schemaVersion":"1.2"}}',
        diffJson='{"changed":["camera"]}',
        summary="旧候选摘要",
        createdByAgent="剧情",
        updatedByAgent="导演",
        revision=3,
    )

    snapshot = _artifact_revision_snapshot(artifact)
    assert snapshot.artifactId == artifact.id
    assert snapshot.revision == 3
    assert snapshot.payloadJson == artifact.payloadJson
    assert snapshot.diffJson == artifact.diffJson
    assert snapshot.summary == artifact.summary
    assert snapshot.createdByAgent == "导演"

    _apply_revised_artifact(
        artifact,
        scene_title="机关启动",
        summary="新候选摘要",
        payload_json='{"scenePlan":{"schemaVersion":"1.3"}}',
    )
    assert artifact.id == "artifact-1"
    assert artifact.status == "awaiting_user"
    assert artifact.revision == 4
    assert artifact.summary == "新候选摘要"
    assert artifact.diffJson is None
    assert json.loads(artifact.payloadJson)["scenePlan"]["schemaVersion"] == "1.3"


def test_revise_requires_artifact_to_match_latest_completed_task() -> None:
    payload_json = '{"scenePlan":{"schemaVersion":"1.2"}}'
    artifact = ReviewArtifact(
        id="artifact-1",
        novelId="novel-1",
        kind="video_scene_plan",
        payloadJson=payload_json,
    )
    task = VideoGenerationTask(id="task-1", resultJson=payload_json)

    _validate_artifact_matches_task(task, artifact)
    task.resultJson = '{"scenePlan":{"schemaVersion":"1.3"}}'
    with pytest.raises(ApiError) as caught:
        _validate_artifact_matches_task(task, artifact)
    assert caught.value.code == "VIDEO_REVISE_ARTIFACT_MISMATCH"


class _Transaction:
    """模拟 SQLAlchemy 事务上下文。"""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        del args


class _ReviseSession:
    """按返工事务查询顺序返回已锁定的数据库事实。"""

    def __init__(self, values: list[object | None]) -> None:
        self._values = iter(values)
        self.added: list[object] = []

    async def __aenter__(self) -> _ReviseSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    def begin(self) -> _Transaction:
        return _Transaction()

    async def scalar(self, statement: object) -> object | None:
        del statement
        return next(self._values)

    def add(self, value: object) -> None:
        self.added.append(value)


class _ReviseSessionFactory:
    """为一次仓储调用提供同一个事务会话。"""

    def __init__(self, session: _ReviseSession) -> None:
        self.session = session

    def __call__(self) -> _ReviseSession:
        return self.session


def _revisable_rows() -> tuple[
    VideoScene,
    VideoProject,
    WritingBible,
    ReviewArtifact,
    VideoGenerationTask,
]:
    """创建一组状态与最新完成任务完全一致的返工事实。"""

    scene, project = _scene_and_project()
    scene.status = "awaiting_review"
    scene.planJson = None
    writing_bible = WritingBible(
        id="bible-1",
        novelId=project.novelId,
        storyLengthProfile="long_serial",
    )
    candidate_json = _candidate_json()
    artifact = ReviewArtifact(
        id="artifact-1",
        novelId=project.novelId,
        videoSceneId=scene.id,
        kind="video_scene_plan",
        status="awaiting_user",
        payloadJson=candidate_json,
        diffJson='{"camera":"changed"}',
        summary="旧候选",
        revision=2,
        createdByAgent="剧情",
        updatedByAgent="剧情",
    )
    latest_task = VideoGenerationTask(
        id="task-old",
        projectId=project.id,
        sceneId=scene.id,
        jobId="video-plan-task-old",
        kind="plan",
        status="completed",
        requestJson=_payload(instruction=None).model_dump_json(),
        resultJson=candidate_json,
    )
    return scene, project, writing_bible, artifact, latest_task


@pytest.mark.asyncio
async def test_repository_revise_atomically_snapshots_and_freezes_new_instruction() -> None:
    scene, project, writing_bible, artifact, latest_task = _revisable_rows()
    # 查询顺序：场景、项目、长篇事实、幂等任务、Artifact、最新任务。
    session = _ReviseSession([scene, project, writing_bible, None, artifact, latest_task])
    repository = VideoRepository(_ReviseSessionFactory(session))  # type: ignore[arg-type]
    request = ReviseVideoSceneRequest(
        clientRequestId="0123456789abcdef",
        expectedArtifactRevision=2,
        userMessage="让摄影机在机关启动后再推进",
    )

    acceptance = await repository.revise_scene_task("user-1", scene.id, request)

    assert acceptance.scene_id == scene.id
    assert artifact.status == "draft"
    assert scene.status == "generating"
    snapshots = [value for value in session.added if isinstance(value, ReviewArtifactRevision)]
    tasks = [value for value in session.added if isinstance(value, VideoGenerationTask)]
    assert len(snapshots) == 1
    assert snapshots[0].revision == 2
    assert snapshots[0].payloadJson == artifact.payloadJson
    assert snapshots[0].diffJson == artifact.diffJson
    assert len(tasks) == 1
    assert tasks[0].id == acceptance.task_id
    assert tasks[0].idempotencyKey == "video-revise:scene-1:0123456789abcdef"
    assert tasks[0].attemptCount == 0
    assert tasks[0].resultJson is None
    persisted_payload = VideoPlanJobPayload.model_validate_json(tasks[0].requestJson)
    assert persisted_payload.sourceText == scene.sourceText
    assert persisted_payload.settingSnapshot == _payload().settingSnapshot
    assert persisted_payload.revisionInstruction == request.userMessage
    assert persisted_payload.revisionBaseline is not None
    assert persisted_payload.revisionBaseline.sceneId == scene.id
    assert persisted_payload.revisionBaseline.summary == "林默插入铜扣后机关开始转动"
    assert persisted_payload.directorDraftVersion == "1.4"


@pytest.mark.asyncio
async def test_repository_revise_replay_returns_same_task_without_new_rows() -> None:
    scene, project, writing_bible, artifact, _ = _revisable_rows()
    request = ReviseVideoSceneRequest(
        clientRequestId="0123456789abcdef",
        expectedArtifactRevision=2,
        userMessage="让摄影机在机关启动后再推进",
    )
    replay_payload = VideoPlanJobPayload.model_validate(
        {
            **_payload(instruction=None).model_dump(mode="python"),
            "revisionInstruction": request.userMessage,
        }
    )
    existing_task = VideoGenerationTask(
        id="task-revise",
        projectId=project.id,
        sceneId=scene.id,
        jobId="video-plan-task-revise",
        kind="plan",
        status="submitted",
        idempotencyKey="video-revise:scene-1:0123456789abcdef",
        requestJson=replay_payload.model_dump_json(),
        createdAt=datetime.now(UTC),
        updatedAt=datetime.now(UTC),
    )
    scene.status = "generating"
    artifact.status = "draft"
    # 幂等命中发生在状态校验之前，不会再次读取 Artifact 或建立任务。
    session = _ReviseSession([scene, project, writing_bible, existing_task])
    repository = VideoRepository(_ReviseSessionFactory(session))  # type: ignore[arg-type]

    acceptance = await repository.revise_scene_task("user-1", scene.id, request)

    assert acceptance.scene_id == scene.id
    assert acceptance.task_id == existing_task.id
    assert acceptance.replay_task is not None
    assert acceptance.replay_task.id == existing_task.id
    assert session.added == []


@pytest.mark.asyncio
async def test_retry_creates_new_task_without_inheriting_failed_checkpoint() -> None:
    """显式重试复用冻结输入，但阶段检查点只能属于原失败任务。"""

    scene, project = _scene_and_project()
    scene.status = "failed"
    scene.planJson = None
    writing_bible = WritingBible(
        id="bible-1",
        novelId=project.novelId,
        storyLengthProfile="long_serial",
    )
    frozen_payload = VideoPlanJobPayload.model_validate(
        {
            **_payload(instruction=None).model_dump(mode="python"),
            "planningRoute": "legacy_strict_tool_v1",
            "directorDraftVersion": "1.0",
        }
    )
    failed_checkpoint = (
        '{"kind":"video_story_plan_checkpoint","schemaVersion":"1.0",'
        '"storyPlan":{"title":"旧阶段"},"correctionUsed":true}'
    )
    latest_task = VideoGenerationTask(
        id="task-failed",
        projectId=project.id,
        sceneId=scene.id,
        jobId="video-plan-task-failed",
        kind="plan",
        status="failed",
        requestJson=frozen_payload.model_dump_json(),
        resultJson=failed_checkpoint,
    )
    # 查询顺序：场景、项目、长篇事实、最新失败任务、任务总数。
    session = _ReviseSession([scene, project, writing_bible, latest_task, 1])
    repository = VideoRepository(_ReviseSessionFactory(session))  # type: ignore[arg-type]

    acceptance = await repository.retry_scene_task("user-1", scene.id)

    new_tasks = [value for value in session.added if isinstance(value, VideoGenerationTask)]
    assert len(new_tasks) == 1
    assert new_tasks[0].id == acceptance.task_id
    retried_payload = VideoPlanJobPayload.model_validate_json(new_tasks[0].requestJson)
    assert retried_payload.planningRoute == "responses_json_schema_v1"
    assert retried_payload.planningModel == "deepseek-v4-flash"
    assert retried_payload.directorDraftVersion == "1.4"
    assert retried_payload.sourceText == frozen_payload.sourceText
    assert retried_payload.settingSnapshot == frozen_payload.settingSnapshot
    assert new_tasks[0].attemptCount == 0
    assert new_tasks[0].resultJson is None
    assert latest_task.resultJson == failed_checkpoint


class _Rows:
    """模拟空素材绑定查询结果。"""

    def all(self) -> list[object]:
        return []


class _SceneReadSession:
    """按读模型查询顺序返回任务和 Artifact。"""

    def __init__(
        self,
        task: VideoGenerationTask | None,
        artifact: ReviewArtifact | None,
    ) -> None:
        self._values = iter([task, artifact])

    async def scalar(self, statement: object) -> object | None:
        del statement
        return next(self._values)

    async def scalars(self, statement: object) -> _Rows:
        del statement
        return _Rows()


@pytest.mark.asyncio
async def test_scene_read_model_hides_draft_candidate_during_revise() -> None:
    now = datetime.now(UTC)
    scene = VideoScene(
        id="scene-1",
        projectId="project-1",
        chapterId="chapter-1",
        ordinal=1,
        title="机关启动",
        sourceText="机关转动",
        sourceHash=hashlib.sha256("机关转动".encode()).hexdigest(),
        durationSeconds=15,
        status="generating",
        revision=1,
        createdAt=now,
        updatedAt=now,
    )
    artifact = ReviewArtifact(
        id="artifact-1",
        novelId="novel-1",
        videoSceneId=scene.id,
        kind="video_scene_plan",
        status="draft",
        payloadJson='{"scenePlan":{"old":true},"promptPackage":{"old":true}}',
        revision=1,
    )

    response = await _scene_response(  # type: ignore[arg-type]
        _SceneReadSession(None, artifact),
        scene,
    )

    assert response.candidatePlan is None
    assert response.candidatePackage is None
    assert response.reviewArtifact is not None
    assert response.reviewArtifact.status == "draft"
