"""旧视频入口和物理退役必须保持同一条保全边界。"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "scripts/migrations/20260910_video_legacy_domain_retirement.sql"

RETIRED_CLI_COMMANDS = {
    "long.video.adaptation.create",
    "long.video.plan.start",
    "long.video.prompt.start",
    "long.video.adaptation.list",
    "long.video.adaptation.get",
    "long.video.adaptation.watch",
    "long.video.plan.confirm",
    "long.video.plan.discard",
    "long.video.episode.save",
    "long.video.prompt.save",
    "long.video.reference.save",
    "long.video.render.list",
    "long.video.render.start",
    "long.video.render.get",
    "long.video.render.retry",
    "long.video.render.watch",
    "long.video.take.confirm",
    "long.video.take.download",
    "long.video.post.show",
    "long.video.keyframe.set",
    "long.video.keyframe.clear",
    "long.video.keyframe.extract",
    "long.video.edit.save",
    "long.video.edit.get",
    "long.video.mix.save",
    "long.video.mix.get",
    "long.video.export.start",
    "long.video.export.get",
    "long.video.export.retry",
    "long.video.export.watch",
    "long.video.export.download",
}

LEGACY_ONLY_TABLES = {
    "VideoAdaptationDecisionCommand",
    "VideoAdaptationTask",
    "VideoAssetBinding",
    "VideoChapterAdaptation",
    "VideoChapterAdaptationHead",
    "VideoCinematicScene",
    "VideoDramaticBeat",
    "VideoDramaticBeatSourceAnchor",
    "VideoEpisodeBoundary",
    "VideoEpisodeEditHead",
    "VideoEpisodeMixHead",
    "VideoEpisodePlanVersion",
    "VideoGenerationTask",
    "VideoReviewDecisionCommand",
    "VideoScene",
    "VideoShot",
    "VideoShotKeyframeHead",
    "VideoShotPlanVersion",
    "VideoShotPromptHead",
    "VideoShotPromptVisualReference",
    "VideoShotSourceAnchor",
    "VideoShotTakeDecisionCommand",
    "VideoShotTakeHead",
    "VideoShotVisualReferenceBinding",
    "VideoShotVisualReferenceSet",
}

SHARED_MEDIA_TABLES = {
    "VideoShotPromptVersion",
    "VideoShotKeyframeVersion",
    "VideoShotRenderTask",
    "VideoShotTake",
    "VideoTakeFrameExtraction",
    "VideoEpisodeEditVersion",
    "VideoEpisodeEditClip",
    "VideoEpisodeMixVersion",
    "VideoEpisodeAudioClip",
    "VideoEpisodeSubtitleCue",
    "VideoEpisodeExportTask",
    "VideoEpisodeExport",
}

RETIRED_JAVA_METHODS = {
    "confirmShotPlanApiV1VideoChapterAdaptationsAdaptationIdShotPlanConfirmPost",
    "confirmShotTakeApiV1VideoChapterAdaptationsAdaptationIdShotsShotIdTakesTakeIdConfirmPost",
    "createAdaptationApiV1VideoProjectsProjectIdChapterAdaptationsPost",
    "createEpisodeExportTaskApiV1VideoChapterAdaptationsAdaptationIdEpisodesEpisodeNoExportTasksPost",
    "createRenderTaskApiV1VideoChapterAdaptationsAdaptationIdShotsShotIdRenderTasksPost",
    "discardCandidateApiV1VideoChapterAdaptationsAdaptationIdCandidateDiscardPost",
    "extractTakeFrameApiV1VideoTakesTakeIdFramesPost",
    "retryEpisodeExportTaskApiV1VideoExportTasksTaskIdRetryPost",
    "retryRenderTaskApiV1VideoRenderTasksTaskIdRetryPost",
    "saveEpisodeEditVersionApiV1VideoChapterAdaptationsAdaptationIdEpisodesEpisodeNoEditVersionsPost",
    "saveEpisodeMixVersionApiV1VideoChapterAdaptationsAdaptationIdEpisodesEpisodeNoMixVersionsPost",
    "saveEpisodePlanApiV1VideoChapterAdaptationsAdaptationIdEpisodePlanPut",
    "saveShotKeyframeVersionApiV1VideoChapterAdaptationsAdaptationIdShotsShotIdKeyframeVersionsPost",
    "saveShotPromptApiV1VideoChapterAdaptationsAdaptationIdShotsShotIdPromptPut",
    "saveShotVisualReferencesApiV1VideoChapterAdaptationsAdaptationIdShotsShotIdVisualReferencesPut",
    "startPromptRunApiV1VideoChapterAdaptationsAdaptationIdPromptRunsPost",
    "startShotPlanApiV1VideoChapterAdaptationsAdaptationIdShotPlanRunsPost",
    "completePlanInternalV1VideoAdaptationsAdaptationIdPlanCompletePost",
    "completePlanInternalV1VideoScenesSceneIdCompletePost",
    "completePromptsInternalV1VideoAdaptationsAdaptationIdPromptsCompletePost",
    "failPlanInternalV1VideoScenesSceneIdFailPost",
    "failTaskInternalV1VideoAdaptationsAdaptationIdFailPost",
    "getAdaptationApiV1VideoChapterAdaptationsAdaptationIdGet",
    "getEpisodeEditVersionApiV1VideoEditVersionsVersionIdGet",
    "getEpisodeExportContentApiV1VideoExportsExportIdContentGet",
    "getEpisodeExportTaskApiV1VideoExportTasksTaskIdGet",
    "getEpisodeMixVersionApiV1VideoMixVersionsVersionIdGet",
    "getPlanProgressInternalV1VideoScenesSceneIdProgressPost",
    "getPostProductionWorkspaceApiV1VideoChapterAdaptationsAdaptationIdPostProductionGet",
    "getProgressInternalV1VideoAdaptationsAdaptationIdProgressPost",
    "getRenderTaskApiV1VideoRenderTasksTaskIdGet",
    "getRenderWorkspaceApiV1VideoChapterAdaptationsAdaptationIdRendersGet",
    "getTakeContentApiV1VideoTakesTakeIdContentGet",
    "listAdaptationsApiV1VideoProjectsProjectIdChapterAdaptationsGet",
    "reservePlanCallInternalV1VideoScenesSceneIdCallReservationsPost",
    "saveCheckpointInternalV1VideoAdaptationsAdaptationIdCheckpointPost",
    "saveStoryPlanCheckpointInternalV1VideoScenesSceneIdStoryCheckpointPost",
}

RETIRED_JAVA_SOURCES = (
    "video/application/VideoAdaptationDecisionStore.java",
    "video/application/VideoAdaptationRepository.java",
    "video/application/VideoAdaptationService.java",
    "video/application/VideoAdaptationAgentStatus.java",
    "video/application/VideoAdaptationSnapshot.java",
    "video/application/VideoAdaptationSubmissionException.java",
    "video/application/VideoAdaptationTaskAcceptance.java",
    "video/application/VideoAdaptationTaskDispatch.java",
    "video/application/VideoAdaptationTaskStore.java",
    "video/application/VideoAdaptationTaskSubmitter.java",
    "video/application/VideoAdaptationTaskDispatcher.java",
    "video/application/LegacyVideoPlanProgress.java",
    "video/application/LegacyVideoPlanService.java",
    "video/application/LegacyVideoPlanStore.java",
    "video/application/LegacyVideoPlanDispatcher.java",
    "video/application/LegacyVideoPlanDispatchStore.java",
    "video/domain/VideoAdaptationPlans.java",
    "video/domain/SeedancePromptCompiler.java",
    "video/infrastructure/JooqVideoAdaptationDecisionStore.java",
    "video/infrastructure/JooqVideoAdaptationReadModel.java",
    "video/infrastructure/JooqVideoAdaptationRepository.java",
    "video/infrastructure/JooqVideoAdaptationTaskStore.java",
    "video/infrastructure/JooqVideoPlanMaterializer.java",
    "video/infrastructure/JooqLegacyVideoPlanStore.java",
    "video/infrastructure/JooqLegacyVideoPlanDispatchStore.java",
    "video/infrastructure/LegacyVideoPlanProgressCodec.java",
    "video/infrastructure/VideoAdaptationTaskPayload.java",
    "video/infrastructure/ProviderVideoAdaptationTaskSubmitter.java",
    "video/infrastructure/DurableVideoAdaptationRun.java",
    "video/infrastructure/JooqVideoModelRunStarter.java",
    "agentgateway/VideoAdaptationAgentSubmitter.java",
    "video/application/VideoRenderClaim.java",
    "video/application/VideoRenderReconciler.java",
    "video/application/VideoRenderRepository.java",
    "video/application/VideoRenderService.java",
    "video/infrastructure/JooqVideoRenderRepository.java",
    "video/infrastructure/VideoRenderManifestCodec.java",
    "video/application/VideoPostProductionReconciler.java",
    "video/application/VideoPostProductionRepository.java",
    "video/application/VideoPostProductionService.java",
    "video/infrastructure/JooqVideoPostProductionRepository.java",
    "video/infrastructure/JooqVideoPostProductionReadModel.java",
    "video/infrastructure/JooqVideoTimelineRepository.java",
    "video/infrastructure/JooqVideoExportRepository.java",
    "video/infrastructure/VideoPostProductionCommands.java",
    "video/infrastructure/VideoPostProductionContext.java",
    "video/infrastructure/VideoPostProductionDatabaseAccess.java",
    "video/application/ShotVisualReferenceSelection.java",
    "video/application/ShotVisualReferencesCommand.java",
)

# 这些共享实现仍由 Episode 视频链使用，故明确不纳入物理退役清单。
ACTIVE_SHARED_VIDEO_JAVA_SOURCES = (
    "video/application/VideoRenderSimulator.java",
    "video/infrastructure/FfmpegVideoRenderSimulator.java",
    "video/application/VideoVisualCanonService.java",
    "video/application/VideoVisualCanonRepository.java",
    "video/infrastructure/JooqVideoVisualCanonRepository.java",
)

REQUIRED_EPISODE_JAVA_SOURCES = (
    "video/application/VideoEpisodeRenderService.java",
    "video/application/VideoEpisodePostProductionService.java",
    "video/application/VideoEpisodeRenderRepository.java",
    "video/application/VideoEpisodeRenderReconciler.java",
)


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_all_legacy_public_writes_and_background_starts_are_closed() -> None:
    java_controller = _source(
        "apps/core-api-java/src/main/java/cn/inkforge/core/video/api/VideoController.java"
    )
    java_configuration = _source(
        "apps/core-api-java/src/main/java/cn/inkforge/core/video/infrastructure/"
        "VideoConfiguration.java"
    )

    for method in RETIRED_JAVA_METHODS:
        assert method not in java_controller

    for bean in (
        "videoAdaptationTaskDispatcher(",
        "legacyVideoPlanDispatcher(",
        "videoRenderReconciler(",
        "videoPostProductionReconciler(",
        "videoAdaptationRepository(",
        "videoAdaptationService(",
        "videoAdaptationTaskStore(",
        "legacyVideoPlanStore(",
        "legacyVideoPlanService(",
        "videoRenderRepository(",
        "videoRenderService(",
        "videoPostProductionRepository(",
        "videoPostProductionService(",
    ):
        assert bean not in java_configuration

    operations = ROOT / "apps/core-api-java/src/main/java/cn/inkforge/core/operations"
    for filename in (
        "LegacyVideoPlanBackgroundConfiguration.java",
        "VideoAdaptationBackgroundConfiguration.java",
        "VideoRenderBackgroundConfiguration.java",
        "VideoPostProductionBackgroundConfiguration.java",
    ):
        assert not (operations / filename).exists()

    # Java Core 已接管唯一公共运行时，旧入口必须彻底缺席，新 Episode worker 继续装配。
    assert "completePlanInternalV1VideoAdaptations" not in java_controller
    assert "videoEpisodePostProductionReconciler(" in java_configuration
    assert "VideoEpisodeRenderService" in java_controller


def test_retired_cli_and_web_entry_points_remain_absent() -> None:
    workspace = _source("apps/web/src/features/video/video-workspace.tsx")
    registry = json.loads(_source("contracts/cli/command-registry.json"))
    command_names = {item["name"] for item in registry["commands"]}

    assert RETIRED_CLI_COMMANDS.isdisjoint(command_names)
    assert 'from "./production/episode-workspace"' in workspace
    assert "ChapterAdaptationWorkspace" not in workspace


def test_retired_java_video_sources_are_physically_removed() -> None:
    java_root = ROOT / "apps/core-api-java/src/main/java/cn/inkforge/core"
    leftovers = [
        path for path in RETIRED_JAVA_SOURCES if (java_root / path).exists()
    ]
    assert leftovers == []


def test_active_episode_java_video_sources_are_preserved() -> None:
    java_root = ROOT / "apps/core-api-java/src/main/java/cn/inkforge/core"
    missing = [
        path for path in REQUIRED_EPISODE_JAVA_SOURCES if not (java_root / path).exists()
    ]
    assert missing == []
    assert set(RETIRED_JAVA_SOURCES).isdisjoint(ACTIVE_SHARED_VIDEO_JAVA_SOURCES)


def test_retirement_migration_preserves_shared_media_and_guards_old_branches() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    dropped = set(re.findall(r'DROP TABLE IF EXISTS "([^"]+)" RESTRICT', source))

    assert dropped == LEGACY_ONLY_TABLES
    assert dropped.isdisjoint(SHARED_MEDIA_TABLES)
    for table in SHARED_MEDIA_TABLES:
        assert table in source
        assert f'DROP TABLE IF EXISTS "{table}"' not in source

    assert "DROP CASCADE" not in source
    assert not re.search(r"DROP\s+(?:TABLE|COLUMN|CONSTRAINT)[^;]*\sCASCADE", source)
    assert "DELETE FROM" not in source
    assert "TRUNCATE" not in source
    assert (
        "P4_WRITES_REMOVED_HISTORY_EMPTY_READ_RUNTIME_REMOVED_FILES_PRESERVED_"
        "SHARED_MEDIA_PRESERVED"
    ) in source
    assert "SELECT count(*) FROM public.%I" in source
    assert "legacy_scope(table_name, predicate)" in source
    assert "[legacy]=%s" in source
    assert "发现需要保全的旧视频数据" in source
    assert 'FROM "ReviewArtifact"' in source
    assert 'FROM "WorkflowRun"' in source
    assert 'FROM "WorkflowEvidenceItem"' in source
    assert 'FROM "TokenUsage" AS usage' in source
    assert "video_adaptation_task_v2" in source
    assert "video_task_context" in source
    assert 'DROP TABLE IF EXISTS "VideoProject"' not in source
    assert 'DROP TABLE IF EXISTS "VideoAsset"' not in source
    assert 'DROP TABLE IF EXISTS "VideoVisualCanon"' not in source
    assert source.count('ADD CONSTRAINT "Video') >= len(SHARED_MEDIA_TABLES)


def test_retirement_migration_refuses_server_databases() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "inkforge_video_legacy_retirement_test" in source
    assert "inkforge_video_legacy_retirement_codegen" in source
    assert "novelwriterdev" not in source
    assert "current_database() NOT IN" in source
