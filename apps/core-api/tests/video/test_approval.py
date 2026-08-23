from __future__ import annotations

import hashlib
import json
from datetime import datetime

import pytest
from inkforge_contracts.video import (
    AssetBinding,
    CameraBeatSpec,
    CompiledAssetBinding,
    ScenePromptSpec,
    SeedanceOutputSpec,
    SeedancePromptPackage,
)
from inkforge_core.db.models import (
    ReviewArtifact,
    VideoGenerationTask,
    VideoProject,
    VideoReviewDecisionCommand,
    VideoScene,
    WritingBible,
)
from inkforge_core.errors import ApiError
from inkforge_core.video.repository import (
    VideoRepository,
    _video_review_decision_lock_key,
    _video_review_decision_request_hash,
)
from inkforge_core.video.schemas import ApproveVideoSceneRequest


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        del args


class _ScalarRows:
    def all(self) -> list[object]:
        return []


class _ApprovalSession:
    """按批准事务的查询顺序返回已锁定事实，并记录所有写入。"""

    def __init__(
        self,
        values: list[object | None],
        *,
        project: VideoProject | None = None,
    ) -> None:
        self._values = iter(values)
        self._project = project
        self.added: list[object] = []
        self.executed: list[tuple[str, object | None]] = []
        self.flush_count = 0

    async def __aenter__(self) -> _ApprovalSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    def begin(self) -> _Transaction:
        return _Transaction()

    async def execute(
        self,
        statement: object,
        parameters: object | None = None,
    ) -> None:
        self.executed.append((str(statement), parameters))

    async def scalar(self, statement: object) -> object | None:
        del statement
        return next(self._values)

    async def scalars(self, statement: object) -> _ScalarRows:
        del statement
        return _ScalarRows()

    async def get(
        self,
        model: object,
        identity: str,
        **kwargs: object,
    ) -> object | None:
        del model, kwargs
        if self._project is None or identity != self._project.id:
            return None
        return self._project

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1


class _ApprovalSessionFactory:
    def __init__(self, session: _ApprovalSession) -> None:
        self.session = session

    def __call__(self) -> _ApprovalSession:
        return self.session


def _approval_facts() -> tuple[
    VideoScene,
    VideoProject,
    WritingBible,
    ReviewArtifact,
    VideoGenerationTask,
]:
    now = datetime(2026, 8, 17, 8, 0, 0)
    project = VideoProject(
        id="project-1",
        novelId="novel-1",
        title="开发预览项目",
        mode="highlight",
        targetAspectRatio="16:9",
        createdAt=now,
        updatedAt=now,
    )
    source_text = "林默按下铜扣，木匣中的齿轮开始转动。"
    scene = VideoScene(
        id="scene-1",
        projectId=project.id,
        chapterId="chapter-1",
        ordinal=1,
        title="机关启动",
        sourceText=source_text,
        sourceHash=hashlib.sha256(source_text.encode()).hexdigest(),
        durationSeconds=4,
        status="awaiting_review",
        planJson=None,
        promptText=None,
        promptCharacterCount=None,
        lastErrorCode=None,
        lastErrorMessage=None,
        revision=1,
        createdAt=now,
        updatedAt=now,
    )
    output = SeedanceOutputSpec(durationSeconds=4)
    scene_plan = ScenePromptSpec(
        sceneId=scene.id,
        title=scene.title,
        summary="机关按动作因果启动",
        visualStyle="冷峻写实",
        globalDirection="先展示按下铜扣，再展示齿轮转动",
        assets=[
            AssetBinding(
                assetId="asset01",
                modality="audio",
                duty="ambience",
                targetEntity="木匣齿轮声",
                includeFeatures=["金属齿轮咬合声"],
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
                action="林默按下铜扣，木匣齿轮随即转动",
                referencedAssetIds=["asset01"],
            )
        ],
        negativeConstraints=["禁止齿轮在按键前自行启动"],
        output=output,
    )
    prompt = "木匣齿轮启动"
    package = SeedancePromptPackage(
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
                targetEntity="木匣齿轮声",
                isFixture=True,
            )
        ],
        output=output,
        previewOnly=True,
        assetReady=False,
        submissionReady=False,
        fixtureOnly=True,
    )
    candidate = {
        "applyTarget": {"type": "video_scene_plan", "sceneId": scene.id},
        "scenePlan": scene_plan.model_dump(mode="json"),
        "promptPackage": package.model_dump(mode="json"),
    }
    candidate_json = json.dumps(candidate, ensure_ascii=False)
    artifact = ReviewArtifact(
        id="artifact-1",
        novelId=project.novelId,
        videoSceneId=scene.id,
        kind="video_scene_plan",
        status="awaiting_user",
        title="视频场景方案：机关启动",
        summary="机关按动作因果启动",
        payloadJson=candidate_json,
        revision=2,
        createdByAgent="剧情",
        updatedByAgent="剧情",
        createdAt=now,
        updatedAt=now,
    )
    task = VideoGenerationTask(
        id="task-1",
        projectId=project.id,
        sceneId=scene.id,
        jobId="video-plan-task-1",
        kind="plan",
        provider="deepseek",
        status="completed",
        idempotencyKey="video-plan:scene-1:1",
        requestJson="{}",
        resultJson=candidate_json,
        lastErrorCode=None,
        lastErrorMessage=None,
        createdAt=now,
        updatedAt=now,
    )
    writing_bible = WritingBible(
        id="bible-1",
        novelId=project.novelId,
        storyLengthProfile="long_serial",
    )
    return scene, project, writing_bible, artifact, task


def _request(client_request_id: str = "approve-request-0001") -> ApproveVideoSceneRequest:
    return ApproveVideoSceneRequest(
        clientRequestId=client_request_id,
        expectedArtifactRevision=2,
    )


@pytest.mark.asyncio
async def test_approval_applies_once_and_persists_full_result_in_same_transaction() -> None:
    scene, project, bible, artifact, task = _approval_facts()
    # 查询顺序：请求命令、场景、长篇事实、Artifact、来源任务、响应任务、响应 Artifact。
    session = _ApprovalSession(
        [None, scene, bible, artifact, task, task, artifact],
        project=project,
    )
    repository = VideoRepository(_ApprovalSessionFactory(session))  # type: ignore[arg-type]

    response = await repository.approve_scene("user-1", scene.id, _request())

    assert response.scene.status == "approved"
    assert response.scene.plan is not None
    assert response.scene.plan["sceneId"] == scene.id
    assert response.scene.plan["summary"] == "机关按动作因果启动"
    assert scene.revision == 2
    assert artifact.status == "applied"
    assert artifact.appliedAt == scene.updatedAt
    commands = [
        value for value in session.added if isinstance(value, VideoReviewDecisionCommand)
    ]
    assert len(commands) == 1
    command = commands[0]
    assert command.requestedByUserId == "user-1"
    assert command.novelId == project.novelId
    assert command.projectId == project.id
    assert command.sceneId == scene.id
    assert command.artifactId == artifact.id
    assert command.sourceTaskId == task.id
    assert command.clientRequestId == "approve-request-0001"
    assert command.requestHash == _video_review_decision_request_hash(scene.id, 2)
    assert json.loads(command.resultJson) == json.loads(response.model_dump_json())
    assert command.completedAt == artifact.appliedAt
    assert session.flush_count == 2
    assert session.executed == [
        (
            "SELECT pg_advisory_xact_lock(:lock_key)",
            {
                "lock_key": _video_review_decision_lock_key(
                    "user-1", "approve-request-0001"
                )
            },
        )
    ]


@pytest.mark.asyncio
async def test_same_approval_request_replays_saved_result_without_reapplying() -> None:
    scene, project, bible, artifact, task = _approval_facts()
    first_session = _ApprovalSession(
        [None, scene, bible, artifact, task, task, artifact],
        project=project,
    )
    repository = VideoRepository(_ApprovalSessionFactory(first_session))  # type: ignore[arg-type]
    first = await repository.approve_scene("user-1", scene.id, _request())
    command = next(
        value
        for value in first_session.added
        if isinstance(value, VideoReviewDecisionCommand)
    )
    approved_revision = scene.revision

    replay_session = _ApprovalSession([command], project=project)
    replay_repository = VideoRepository(  # type: ignore[arg-type]
        _ApprovalSessionFactory(replay_session)
    )
    replay = await replay_repository.approve_scene("user-1", scene.id, _request())

    assert replay == first
    assert scene.revision == approved_revision
    assert replay_session.added == []
    assert replay_session.flush_count == 0


@pytest.mark.asyncio
async def test_different_request_key_for_applied_revision_copies_first_exact_result() -> None:
    scene, project, bible, artifact, task = _approval_facts()
    first_session = _ApprovalSession(
        [None, scene, bible, artifact, task, task, artifact],
        project=project,
    )
    repository = VideoRepository(_ApprovalSessionFactory(first_session))  # type: ignore[arg-type]
    first = await repository.approve_scene("user-1", scene.id, _request())
    first_command = next(
        value
        for value in first_session.added
        if isinstance(value, VideoReviewDecisionCommand)
    )
    approved_revision = scene.revision

    second_session = _ApprovalSession(
        [None, scene, bible, artifact, task, first_command],
        project=project,
    )
    second_repository = VideoRepository(  # type: ignore[arg-type]
        _ApprovalSessionFactory(second_session)
    )
    second = await second_repository.approve_scene(
        "user-1",
        scene.id,
        _request("approve-request-0002"),
    )

    assert second == first
    assert scene.revision == approved_revision
    second_command = next(
        value
        for value in second_session.added
        if isinstance(value, VideoReviewDecisionCommand)
    )
    assert second_command.clientRequestId == "approve-request-0002"
    assert second_command.resultJson == first_command.resultJson
    assert second_command.sourceTaskId == first_command.sourceTaskId


@pytest.mark.asyncio
async def test_same_request_key_with_different_revision_is_a_stable_conflict() -> None:
    scene, project, bible, artifact, task = _approval_facts()
    first_session = _ApprovalSession(
        [None, scene, bible, artifact, task, task, artifact],
        project=project,
    )
    repository = VideoRepository(_ApprovalSessionFactory(first_session))  # type: ignore[arg-type]
    await repository.approve_scene("user-1", scene.id, _request())
    command = next(
        value
        for value in first_session.added
        if isinstance(value, VideoReviewDecisionCommand)
    )
    conflicting_request = ApproveVideoSceneRequest(
        clientRequestId=command.clientRequestId,
        expectedArtifactRevision=3,
    )
    conflict_session = _ApprovalSession([command], project=project)
    conflict_repository = VideoRepository(  # type: ignore[arg-type]
        _ApprovalSessionFactory(conflict_session)
    )

    with pytest.raises(ApiError) as caught:
        await conflict_repository.approve_scene(
            "user-1",
            scene.id,
            conflicting_request,
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "VIDEO_REVIEW_DECISION_IDEMPOTENCY_CONFLICT"
    assert conflict_session.added == []


@pytest.mark.asyncio
async def test_applied_legacy_candidate_without_command_gains_a_durable_replay_record() -> None:
    scene, project, bible, artifact, task = _approval_facts()
    payload = json.loads(artifact.payloadJson)
    scene.planJson = json.dumps(payload["scenePlan"], ensure_ascii=False)
    scene.promptText = payload["promptPackage"]["prompt"]
    scene.promptCharacterCount = payload["promptPackage"]["promptCharacterCount"]
    scene.status = "approved"
    scene.revision = 2
    artifact.status = "applied"
    artifact.appliedAt = scene.updatedAt
    # 查询顺序在来源任务后先查历史命令；查不到时再聚合当前正式响应。
    session = _ApprovalSession(
        [None, scene, bible, artifact, task, None, task, artifact],
        project=project,
    )
    repository = VideoRepository(_ApprovalSessionFactory(session))  # type: ignore[arg-type]

    response = await repository.approve_scene("user-1", scene.id, _request())

    assert response.scene.status == "approved"
    assert scene.revision == 2
    command = next(
        value for value in session.added if isinstance(value, VideoReviewDecisionCommand)
    )
    assert command.resultJson == response.model_dump_json()
    assert command.sourceTaskId == task.id


@pytest.mark.asyncio
async def test_approval_rejects_candidate_that_does_not_match_source_task() -> None:
    scene, project, bible, artifact, task = _approval_facts()
    task.resultJson = '{"scenePlan":{"sceneId":"other-scene"}}'
    session = _ApprovalSession(
        [None, scene, bible, artifact, task],
        project=project,
    )
    repository = VideoRepository(_ApprovalSessionFactory(session))  # type: ignore[arg-type]

    with pytest.raises(ApiError) as caught:
        await repository.approve_scene("user-1", scene.id, _request())

    assert caught.value.code == "VIDEO_APPROVAL_ARTIFACT_MISMATCH"
    assert scene.status == "awaiting_review"
    assert scene.planJson is None
    assert artifact.status == "awaiting_user"
    assert session.added == []


def test_approval_hash_and_lock_key_bind_all_replay_boundaries() -> None:
    request_hash = _video_review_decision_request_hash("scene-1", 2)

    assert len(request_hash) == 64
    assert request_hash == _video_review_decision_request_hash("scene-1", 2)
    assert request_hash != _video_review_decision_request_hash("scene-2", 2)
    assert request_hash != _video_review_decision_request_hash("scene-1", 3)
    assert _video_review_decision_lock_key("user-1", "request-00000001") != (
        _video_review_decision_lock_key("user-2", "request-00000001")
    )
