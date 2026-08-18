from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from inkforge_contracts.video import (
    AssetBinding,
    CameraActionUnit,
    CameraBeatSpec,
    CameraCompositionSpec,
    CameraFocusSpec,
    CameraMovementSpec,
    CameraPositionSpec,
    CameraShotProgression,
    CinematographyBase,
    LightingSetup,
    LightSourceSpec,
    LongSerialSettingSnapshot,
    ScenePromptSpec,
    SeedanceOutputSpec,
    SettingReference,
    ShotCameraSpec,
    ShotLightingCue,
    VideoPlanFailureCallback,
    VideoPlanJobPayload,
    calculate_setting_snapshot_fingerprint,
)
from inkforge_core.config import Settings
from inkforge_core.db.models import (
    Character,
    CharacterRelation,
    Item,
    Location,
    VideoAsset,
    VideoGenerationTask,
    VideoProject,
    VideoScene,
    WorldSetting,
    WritingBible,
)
from inkforge_core.errors import ApiError
from inkforge_core.video.repository import (
    VideoPromptPreviewContext,
    VideoRepository,
    _build_long_serial_setting_snapshot,
    _setting_entry_content_hash,
    _validate_callback_binding,
    _validate_retry_payload,
)
from inkforge_core.video.router import router
from inkforge_core.video.schemas import (
    CreateVideoProjectRequest,
    CreateVideoSceneRequest,
    PromptPreviewRequest,
    VideoAssetResponse,
)
from inkforge_core.video.service import VideoService
from inkforge_core.video.storage import VideoAssetStorage
from pydantic import ValidationError
from starlette.datastructures import Headers, UploadFile


class _Rows:
    """模拟 AsyncScalarResult 的最小只读结果。"""

    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return self._values


class _SnapshotSession:
    """按快照查询顺序返回五类长篇设定。"""

    def __init__(self, rows: list[list[object]], world_setting: WorldSetting | None) -> None:
        self._rows = iter(rows)
        self._world_setting = world_setting

    async def scalars(self, statement: object) -> _Rows:
        del statement
        return _Rows(next(self._rows))

    async def scalar(self, statement: object) -> WorldSetting | None:
        del statement
        return self._world_setting


class _PreviewSession:
    """为提示词预览提供正式场景、长篇资料和同项目素材。"""

    def __init__(
        self,
        scene: VideoScene,
        project: VideoProject,
        writing_bible: WritingBible,
        assets: list[VideoAsset],
    ) -> None:
        self._scalars = iter([scene, writing_bible])
        self._project = project
        self._assets = assets

    async def __aenter__(self) -> _PreviewSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    async def scalar(self, statement: object) -> object:
        del statement
        return next(self._scalars)

    async def get(self, model: object, object_id: str) -> VideoProject | None:
        del model
        return self._project if self._project.id == object_id else None

    async def scalars(self, statement: object) -> _Rows:
        del statement
        return _Rows(list(self._assets))


class _PreviewSessionFactory:
    """每次仓储调用返回同一个无写能力会话，以证明预览不会持久绑定。"""

    def __init__(self, session: _PreviewSession) -> None:
        self._session = session

    def __call__(self) -> _PreviewSession:
        return self._session


class _RecordingRepository:
    """记录服务层调用并返回可确定性编译的正式方案。"""

    def __init__(self, context: VideoPromptPreviewContext | None = None) -> None:
        self.context = context
        self.create_calls = 0
        self.list_calls = 0
        self.upload_calls = 0

    async def create_project(self, *args: object) -> Any:
        del args
        self.create_calls += 1
        raise AssertionError("关闭预览开关时不应进入仓储")

    async def list_projects(self, *args: object) -> list[object]:
        del args
        self.list_calls += 1
        return []

    async def prepare_prompt_preview(
        self,
        user_id: str,
        scene_id: str,
        request: PromptPreviewRequest,
    ) -> VideoPromptPreviewContext:
        del user_id, scene_id, request
        assert self.context is not None
        return self.context

    async def require_project(self, user_id: str, project_id: str) -> None:
        assert (user_id, project_id) == ("user-1", "project-1")

    async def create_asset(
        self,
        user_id: str,
        project_id: str,
        asset_id: str,
        *,
        name: str,
        modality: str,
        duty: str,
        source_kind: str,
        stored: Any,
    ) -> VideoAssetResponse:
        assert user_id == "user-1"
        self.upload_calls += 1
        now = datetime.now(UTC)
        return VideoAssetResponse(
            id=asset_id,
            projectId=project_id,
            name=name,
            modality=modality,
            duty=duty,
            mimeType=stored.mime_type,
            byteSize=stored.byte_size,
            durationMs=None,
            sha256=stored.sha256,
            sourceKind=source_kind,
            rightsStatus="unconfirmed",
            lockedAt=None,
            createdAt=now,
            updatedAt=now,
        )


def _scene_plan() -> ScenePromptSpec:
    """创建同时包含设定槽位和场次直接槽位的四秒正式方案。"""

    return ScenePromptSpec(
        schemaVersion="1.2",
        sceneId="scene-1",
        title="对峙",
        summary="两人在雨夜对峙",
        visualStyle="冷色电影质感",
        globalDirection="保持人物身份稳定",
        cinematographyBase=CinematographyBase(
            captureFormat="super_35",
            lensProjection="spherical",
            frameRateFps=24,
            shutterAngleDegrees=180,
            axisRule="maintain_180",
            screenDirection="left_to_right",
        ),
        lightingSetup=LightingSetup(
            exposureStyle="low_key",
            ambientSource="码头棚外雨夜冷光",
            ambientColorTemperatureK=6500,
            keyToFillStops=3,
            negativeFillSide="camera_right",
            atmosphere="雨雾在人物背后形成轻微空气透视",
        ),
        assets=[
            AssetBinding(
                assetId="slot-character",
                modality="image",
                duty="identity",
                bindingScope="canon_slot",
                settingReference=SettingReference(kind="character", id="character-1"),
                featureDomain="character_identity",
                targetEntity="沈砚",
                includeFeatures=["面部", "发型"],
                excludeFeatures=["服装"],
            ),
            AssetBinding(
                assetId="slot-relationship",
                modality="image",
                duty="relation_interaction",
                bindingScope="canon_slot",
                settingReference=SettingReference(kind="relationship", id="relation-1"),
                featureDomain="relationship_interaction",
                targetEntity="沈砚与陆遥的敌对关系",
                includeFeatures=["站位", "对抗感"],
                excludeFeatures=[],
            ),
            AssetBinding(
                assetId="slot-ambience",
                modality="audio",
                duty="ambience",
                bindingScope="scene_direct",
                settingReference=None,
                featureDomain="ambience",
                targetEntity="码头雨声",
                includeFeatures=["雨打铁皮", "远处船笛"],
                excludeFeatures=["背景音乐"],
            ),
        ],
        beats=[
            CameraBeatSpec(
                beatId="beat-1",
                startSecond=0,
                endSecond=4,
                shotSize="中景",
                cameraAngle="平视",
                cameraMovement="缓慢推进",
                action="沈砚与陆遥无声对峙，二人保持敌对站位",
                actionUnits=[
                    CameraActionUnit(
                        subject="沈砚与陆遥",
                        action="无声对峙",
                        visibleResult="二人保持敌对站位",
                    )
                ],
                actionComplexity="simple",
                shotProgression=CameraShotProgression(
                    startShotSize="中景",
                    endShotSize="中景",
                    changeMode="continuous",
                ),
                cameraSpec=ShotCameraSpec(
                    lensType="prime",
                    focalLengthMm=40,
                    endFocalLengthMm=40,
                    tStop=2.8,
                    position=CameraPositionSpec(
                        heightCm=125,
                        azimuthDegrees=-25,
                        elevationDegrees=0,
                        rollDegrees=0,
                        subjectDistanceMeters=3.2,
                        axisSide="screen_left",
                    ),
                    composition=CameraCompositionSpec(
                        rule="rule_of_thirds",
                        subjectPlacement="right_third",
                        subjectFramePercent=55,
                        headroom="standard",
                        foregroundLayer="雨帘和棚柱",
                        backgroundLayer="失焦船灯与铁皮棚",
                    ),
                    movement=CameraMovementSpec(
                        support="dolly",
                        movementType="dolly_in",
                        travelDistanceMeters=0.5,
                        rotationDegrees=0,
                        speed="slow",
                        easing="ease_in_out",
                    ),
                    focus=CameraFocusSpec(
                        depthOfField="shallow",
                        startTarget="沈砚与陆遥的眼神平面",
                        endTarget="沈砚与陆遥的眼神平面",
                        transition="locked",
                        rackDurationSeconds=0,
                    ),
                ),
                lightingCue=ShotLightingCue(
                    continuityMode="establish",
                    motivatedChange="建立码头棚外雨夜冷光",
                    keyLight=LightSourceSpec(
                        role="key",
                        motivatedBy="棚外雨夜天光",
                        direction="back_left",
                        azimuthDegrees=-135,
                        elevationDegrees=30,
                        quality="soft",
                        delivery="diffused",
                        colorTemperatureK=6500,
                        relativeExposureStops=0,
                        beamAngleDegrees=75,
                        falloff="slow",
                        spillControl="棚柱与黑旗限制正面溢光",
                        visibleResult="人物肩线与雨丝出现冷色分离光",
                    ),
                    fillStrategy="negative_fill",
                    fillDirection="front_right",
                    fillRelativeStops=-3,
                    edgeLight=None,
                    atmosphere="雨雾保持轻微体积层次",
                    visibleResult="两人面部压暗，轮廓和敌对站位清晰",
                ),
                sound="<雨打铁皮><远处船笛>，无对白",
                referencedAssetIds=[
                    "slot-character",
                    "slot-relationship",
                    "slot-ambience",
                ],
            )
        ],
        negativeConstraints=["禁止人物变脸"],
        output=SeedanceOutputSpec(durationSeconds=4),
    )


def _video_service(
    tmp_path: Path,
    repository: object,
    *,
    enabled: bool,
) -> VideoService:
    return VideoService(
        repository,  # type: ignore[arg-type]
        storage=VideoAssetStorage(tmp_path),
        video_preview_enabled=enabled,
    )


def test_preview_switch_defaults_closed_and_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VIDEO_PREVIEW_ENABLED", raising=False)
    assert Settings(environment="dev").video_preview_enabled is False

    monkeypatch.setenv("VIDEO_PREVIEW_ENABLED", "true")
    monkeypatch.setenv("VIDEO_DISPATCH_NAMESPACE", "preview-test")
    assert Settings(environment="dev").video_preview_enabled is True


def test_preview_requests_narrow_mode_duration_source_and_duplicate_slots() -> None:
    with pytest.raises(ValidationError):
        CreateVideoProjectRequest(title="旧模式", mode="short_film")
    with pytest.raises(ValidationError):
        CreateVideoSceneRequest(
            clientRequestId="0123456789abcdef",
            chapterId="chapter-1",
            title="过长场景",
            expectedChapterUpdatedAt="2026-08-10T00:00:00Z",
            selectionStartUtf16=0,
            selectionEndUtf16=4,
            selectedText="具体事件",
            durationSeconds=16,
        )
    with pytest.raises(ValidationError):
        CreateVideoSceneRequest(
            clientRequestId="0123456789abcdef",
            chapterId="chapter-1",
            title="缺少事件选区",
        )
    with pytest.raises(ValidationError):
        CreateVideoSceneRequest(
            clientRequestId="0123456789abcdef",
            chapterId="chapter-1",
            title="过长原文",
            expectedChapterUpdatedAt="2026-08-10T00:00:00Z",
            selectionStartUtf16=0,
            selectionEndUtf16=2_001,
            selectedText="甲" * 2_001,
        )
    required = CreateVideoSceneRequest.model_json_schema()["required"]
    assert "selectedText" in required
    assert "expectedChapterUpdatedAt" in required
    with pytest.raises(ValidationError, match="slotId"):
        PromptPreviewRequest.model_validate(
            {
                "previewBindings": [
                    {"slotId": "slot-1", "assetId": "asset-1"},
                    {"slotId": "slot-1", "assetId": "asset-2"},
                ]
            }
        )


@pytest.mark.asyncio
async def test_switch_blocks_writes_but_keeps_legacy_reads(tmp_path: Path) -> None:
    repository = _RecordingRepository()
    service = _video_service(tmp_path, repository, enabled=False)

    with pytest.raises(ApiError) as caught:
        await service.create_project(
            "user-1",
            "novel-1",
            CreateVideoProjectRequest(title="预览项目"),
        )
    assert caught.value.status_code == 503
    assert caught.value.code == "VIDEO_PREVIEW_DISABLED"
    assert repository.create_calls == 0

    project_list = await service.list_projects("user-1", "novel-1")
    assert project_list.projects == []
    assert project_list.previewEnabled is False
    assert project_list.seedanceConfigured is False
    assert project_list.seedanceEnabled is False
    assert repository.list_calls == 1


@pytest.mark.asyncio
async def test_snapshot_freezes_typed_closed_entries_without_truncation() -> None:
    characters = [
        Character(
            id="character-1",
            novelId="novel-1",
            name="沈砚",
            aliases="阿砚，沈先生",
            appearance="黑发灰眸",
            identity="调查员",
        ),
        Character(
            id="character-2",
            novelId="novel-1",
            name="陆遥",
            aliases=None,
            appearance="短发",
            identity="记者",
        ),
    ]
    relations = [
        CharacterRelation(
            id="relation-1",
            characterId="character-1",
            targetId="character-2",
            relationType="enemy",
            description="表面对立，目标暂时一致",
        )
    ]
    locations = [
        Location(
            id="location-1",
            novelId="novel-1",
            name="旧码头",
            aliases="七码头",
            type="室外",
            parentId=None,
            climate="暴雨",
            culture=None,
            description="锈蚀吊机与积水",
        )
    ]
    items = [
        Item(
            id="item-1",
            novelId="novel-1",
            name="铜钥匙",
            aliases=None,
            type="线索",
            ownerId="character-1",
            description="边缘刻有潮汐纹",
        )
    ]
    long_world_content = "世界规则" * 1_000
    world_setting = WorldSetting(
        id="world-1",
        novelId="novel-1",
        content=long_world_content,
    )
    session = _SnapshotSession(
        [characters, relations, locations, items],
        world_setting,
    )

    snapshot = await _build_long_serial_setting_snapshot(session, "novel-1")  # type: ignore[arg-type]

    assert {entry.kind for entry in snapshot.entries} == {
        "character",
        "relationship",
        "location",
        "item",
        "world_setting",
    }
    relationship = next(entry for entry in snapshot.entries if entry.kind == "relationship")
    assert relationship.sourceCharacterId == "character-1"
    assert relationship.targetCharacterId == "character-2"
    world = next(entry for entry in snapshot.entries if entry.kind == "world_setting")
    assert world.content == long_world_content
    for entry in snapshot.entries:
        content = entry.model_dump(mode="json", exclude={"contentHash"})
        assert entry.contentHash == _setting_entry_content_hash(content)
    assert snapshot.fingerprint == calculate_setting_snapshot_fingerprint(snapshot.entries)


@pytest.mark.asyncio
async def test_repository_preview_accepts_locked_keyframe_for_relationship_slot() -> None:
    now = datetime.now(UTC)
    scene_plan = _scene_plan()
    scene = VideoScene(
        id="scene-1",
        projectId="project-1",
        status="approved",
        planJson=scene_plan.model_dump_json(),
    )
    project = VideoProject(
        id="project-1",
        novelId="novel-1",
        title="项目",
        mode="highlight",
    )
    writing_bible = WritingBible(
        id="bible-1",
        novelId="novel-1",
        storyLengthProfile="long_serial",
    )
    assets = [
        VideoAsset(
            id="asset-character",
            projectId="project-1",
            modality="image",
            duty="identity",
            rightsStatus="confirmed",
            lockedAt=now,
        ),
        VideoAsset(
            id="asset-ambience",
            projectId="project-1",
            modality="audio",
            duty="ambience",
            rightsStatus="confirmed",
            lockedAt=now,
        ),
        VideoAsset(
            id="asset-relation",
            projectId="project-1",
            modality="image",
            duty="keyframe",
            rightsStatus="confirmed",
            lockedAt=now,
        ),
    ]
    session = _PreviewSession(scene, project, writing_bible, assets)
    repository = VideoRepository(_PreviewSessionFactory(session))  # type: ignore[arg-type]
    request = PromptPreviewRequest.model_validate(
        {
            "previewBindings": [
                {"slotId": "slot-character", "assetId": "asset-character"},
                {"slotId": "slot-relationship", "assetId": "asset-relation"},
                {"slotId": "slot-ambience", "assetId": "asset-ambience"},
            ]
        }
    )

    context = await repository.prepare_prompt_preview("user-1", "scene-1", request)

    assert context.selections == {
        "slot-character": "asset-character",
        "slot-relationship": "asset-relation",
        "slot-ambience": "asset-ambience",
    }
    assert context.resolved_slot_ids == (
        "slot-character",
        "slot-relationship",
        "slot-ambience",
    )
    assert context.missing_slot_ids == ()


@pytest.mark.asyncio
async def test_service_compiles_preview_only_package_even_when_all_assets_resolved(
    tmp_path: Path,
) -> None:
    context = VideoPromptPreviewContext(
        scene_plan=_scene_plan(),
        selections={
            "slot-character": "asset-character",
            "slot-relationship": "asset-relation",
            "slot-ambience": "asset-ambience",
        },
        resolved_slot_ids=(
            "slot-character",
            "slot-relationship",
            "slot-ambience",
        ),
        missing_slot_ids=(),
    )
    service = _video_service(
        tmp_path,
        _RecordingRepository(context),
        enabled=True,
    )

    response = await service.preview_prompt(
        "user-1",
        "scene-1",
        PromptPreviewRequest.model_validate(
            {
                "previewBindings": [
                    {"slotId": "slot-character", "assetId": "asset-character"},
                    {"slotId": "slot-relationship", "assetId": "asset-relation"},
                    {"slotId": "slot-ambience", "assetId": "asset-ambience"},
                ]
            }
        ),
    )

    assert response.resolvedSlotIds == [
        "slot-character",
        "slot-relationship",
        "slot-ambience",
    ]
    assert response.missingSlotIds == []
    assert response.promptPackage.assetReady is True
    assert response.promptPackage.previewOnly is True
    assert response.promptPackage.submissionReady is False
    assert response.promptPackage.compileProfile == "seedance_director_v3_compat"
    assert response.promptPackage.providerPrompt == response.promptPackage.prompt
    assert (
        response.promptPackage.manifestPromptCharacterCount
        > response.promptPackage.providerPromptCharacterCount
    )
    assert [binding.assetId for binding in response.promptPackage.assetBindings] == [
        "slot-character",
        "slot-relationship",
        "slot-ambience",
    ]
    assert [binding.mediaAssetId for binding in response.promptPackage.assetBindings] == [
        "asset-character",
        "asset-relation",
        "asset-ambience",
    ]


@pytest.mark.asyncio
async def test_upload_uses_planned_asset_validation_without_fake_materialization(
    tmp_path: Path,
) -> None:
    repository = _RecordingRepository()
    service = _video_service(tmp_path, repository, enabled=True)
    upload = UploadFile(
        BytesIO(b"\x89PNG\r\n\x1a\npreview-image"),
        filename="identity.png",
        headers=Headers({"content-type": "image/png"}),
    )

    response = await service.upload_asset(
        "user-1",
        "project-1",
        upload=upload,
        name="人物定妆照",
        modality="image",
        duty="identity",
        source_kind="user_upload",
    )

    assert response.modality == "image"
    assert response.duty == "identity"
    assert repository.upload_calls == 1


def test_callback_novel_id_must_match_task_project() -> None:
    task = VideoGenerationTask(
        id="task-1",
        jobId="job-1",
        projectId="project-1",
        sceneId="scene-1",
    )
    scene = VideoScene(id="scene-1", projectId="project-1")
    project = VideoProject(
        id="project-1",
        novelId="novel-1",
        title="项目",
        mode="highlight",
    )
    callback = VideoPlanFailureCallback(
        protocolVersion="1.0",
        eventId="event-1",
        jobId="job-1",
        runId="run-1",
        taskId="task-1",
        novelId="novel-other",
        projectId="project-1",
        sceneId="scene-1",
        code="VIDEO_PLAN_FAILED",
        message="失败",
        recoverable=True,
    )

    with pytest.raises(ApiError) as caught:
        _validate_callback_binding(task, scene, project, callback)

    assert caught.value.status_code == 403
    assert caught.value.code == "VIDEO_CALLBACK_RESOURCE_MISMATCH"


def test_retry_payload_reuses_exact_frozen_scene_input() -> None:
    source_text = "林默把铜扣插入木匣，机关开始转动。"
    scene = VideoScene(
        id="scene-1",
        projectId="project-1",
        chapterId="chapter-1",
        title="机关启动",
        sourceText=source_text,
        sourceHash=hashlib.sha256(source_text.encode()).hexdigest(),
        durationSeconds=15,
    )
    project = VideoProject(
        id="project-1",
        novelId="novel-1",
        title="项目",
        mode="highlight",
    )
    payload = VideoPlanJobPayload(
        projectId=project.id,
        sceneId=scene.id,
        chapterId=scene.chapterId,
        title=scene.title,
        sourceText=source_text,
        durationSeconds=scene.durationSeconds,
        ratio="16:9",
        settingSnapshot=LongSerialSettingSnapshot.from_entries([]),
    )
    task = VideoGenerationTask(
        id="task-1",
        projectId=project.id,
        sceneId=scene.id,
        requestJson=payload.model_dump_json(),
    )

    assert _validate_retry_payload(task, scene, project) == payload

    scene.sourceText = "被修改的场景正文"
    with pytest.raises(ApiError) as caught:
        _validate_retry_payload(task, scene, project)
    assert caught.value.code == "VIDEO_RETRY_INPUT_MISMATCH"


def test_public_router_exposes_preview_and_removes_legacy_free_text_binding() -> None:
    paths = {route.path for route in router.routes}

    assert "/video/scenes/{scene_id}/prompt-preview" in paths
    assert "/video/scenes/{scene_id}/retry" in paths
    assert "/video/scenes/{scene_id}/revise" in paths
    assert "/video/scenes/{scene_id}/asset-bindings" not in paths
