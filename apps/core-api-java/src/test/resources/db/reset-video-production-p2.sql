BEGIN;

ALTER TABLE "VideoEpisode" DROP CONSTRAINT IF EXISTS "VideoEpisode_current_storyboard_fkey";
ALTER TABLE "VideoEpisode" DROP CONSTRAINT IF EXISTS "VideoEpisode_current_baseline_fkey";
ALTER TABLE "VideoEpisode" DROP CONSTRAINT IF EXISTS "VideoEpisode_latest_delivery_fkey";
ALTER TABLE "VideoEpisodeExport" DROP CONSTRAINT IF EXISTS "VideoEpisodeExport_id_video_episode_key";
ALTER TABLE "VideoImpactReview" DROP CONSTRAINT IF EXISTS "VideoImpactReview_producer_baseline_fkey";
ALTER TABLE "VideoImpactReview" DROP CONSTRAINT IF EXISTS "VideoImpactReview_target_baseline_fkey";

ALTER TABLE "VideoShotPromptVersion" DROP CONSTRAINT IF EXISTS "VideoShotPromptVersion_based_on_episode_fkey";
ALTER TABLE "VideoShotPromptVersion" DROP CONSTRAINT IF EXISTS "VideoShotPromptVersion_baseline_input_fkey";
ALTER TABLE "VideoShotPromptVersion" DROP CONSTRAINT IF EXISTS "VideoShotPromptVersion_episode_scope_fkey";
ALTER TABLE "VideoShotPromptVersion" DROP CONSTRAINT IF EXISTS "VideoShotPromptVersion_baseline_scope_fkey";
ALTER TABLE "VideoShotKeyframeVersion" DROP CONSTRAINT IF EXISTS "VideoShotKeyframeVersion_based_on_episode_fkey";
ALTER TABLE "VideoShotKeyframeVersion" DROP CONSTRAINT IF EXISTS "VideoShotKeyframeVersion_baseline_input_fkey";
ALTER TABLE "VideoShotKeyframeVersion" DROP CONSTRAINT IF EXISTS "VideoShotKeyframeVersion_episode_scope_fkey";
ALTER TABLE "VideoShotKeyframeVersion" DROP CONSTRAINT IF EXISTS "VideoShotKeyframeVersion_baseline_scope_fkey";
ALTER TABLE "VideoShotRenderTask" DROP CONSTRAINT IF EXISTS "VideoShotRenderTask_retry_episode_fkey";
ALTER TABLE "VideoShotRenderTask" DROP CONSTRAINT IF EXISTS "VideoShotRenderTask_baseline_input_fkey";
ALTER TABLE "VideoShotRenderTask" DROP CONSTRAINT IF EXISTS "VideoShotRenderTask_prompt_new_scope_fkey";
ALTER TABLE "VideoShotRenderTask" DROP CONSTRAINT IF EXISTS "VideoShotRenderTask_episode_scope_fkey";
ALTER TABLE "VideoShotRenderTask" DROP CONSTRAINT IF EXISTS "VideoShotRenderTask_baseline_scope_fkey";
ALTER TABLE "VideoShotTake" DROP CONSTRAINT IF EXISTS "VideoShotTake_task_episode_scope_fkey";
ALTER TABLE "VideoShotTake" DROP CONSTRAINT IF EXISTS "VideoShotTake_episode_scope_fkey";
ALTER TABLE "VideoShotTake" DROP CONSTRAINT IF EXISTS "VideoShotTake_baseline_scope_fkey";
ALTER TABLE "VideoTakeFrameExtraction" DROP CONSTRAINT IF EXISTS "VideoTakeFrameExtraction_take_episode_scope_fkey";
ALTER TABLE "VideoTakeFrameExtraction" DROP CONSTRAINT IF EXISTS "VideoTakeFrameExtraction_episode_scope_fkey";
ALTER TABLE "VideoTakeFrameExtraction" DROP CONSTRAINT IF EXISTS "VideoTakeFrameExtraction_baseline_scope_fkey";
ALTER TABLE "VideoEpisodeEditVersion" DROP CONSTRAINT IF EXISTS "VideoEpisodeEditVersion_based_on_episode_fkey";
ALTER TABLE "VideoEpisodeEditVersion" DROP CONSTRAINT IF EXISTS "VideoEpisodeEditVersion_baseline_scope_fkey";
ALTER TABLE "VideoEpisodeEditClip" DROP CONSTRAINT IF EXISTS "VideoEpisodeEditClip_adoption_scope_fkey";
ALTER TABLE "VideoEpisodeEditClip" DROP CONSTRAINT IF EXISTS "VideoEpisodeEditClip_adoption_take_fkey";
ALTER TABLE "VideoEpisodeEditClip" DROP CONSTRAINT IF EXISTS "VideoEpisodeEditClip_baseline_input_fkey";
ALTER TABLE "VideoEpisodeEditClip" DROP CONSTRAINT IF EXISTS "VideoEpisodeEditClip_baseline_scope_fkey";
ALTER TABLE "VideoEpisodeEditClip" DROP CONSTRAINT IF EXISTS "VideoEpisodeEditClip_edit_new_scope_fkey";
ALTER TABLE "VideoEpisodeEditClip" DROP CONSTRAINT IF EXISTS "VideoEpisodeEditClip_episode_scope_fkey";
ALTER TABLE "VideoEpisodeEditClip" DROP CONSTRAINT IF EXISTS "VideoEpisodeEditClip_take_new_scope_fkey";
ALTER TABLE "VideoEpisodeMixVersion" DROP CONSTRAINT IF EXISTS "VideoEpisodeMixVersion_based_on_episode_fkey";
ALTER TABLE "VideoEpisodeMixVersion" DROP CONSTRAINT IF EXISTS "VideoEpisodeMixVersion_baseline_scope_fkey";
ALTER TABLE "VideoEpisodeMixVersion" DROP CONSTRAINT IF EXISTS "VideoEpisodeMixVersion_edit_new_scope_fkey";
ALTER TABLE "VideoEpisodeAudioClip" DROP CONSTRAINT IF EXISTS "VideoEpisodeAudioClip_baseline_input_fkey";
ALTER TABLE "VideoEpisodeAudioClip" DROP CONSTRAINT IF EXISTS "VideoEpisodeAudioClip_baseline_scope_fkey";
ALTER TABLE "VideoEpisodeAudioClip" DROP CONSTRAINT IF EXISTS "VideoEpisodeAudioClip_episode_scope_fkey";
ALTER TABLE "VideoEpisodeAudioClip" DROP CONSTRAINT IF EXISTS "VideoEpisodeAudioClip_mix_new_scope_fkey";
ALTER TABLE "VideoEpisodeSubtitleCue" DROP CONSTRAINT IF EXISTS "VideoEpisodeSubtitleCue_baseline_input_fkey";
ALTER TABLE "VideoEpisodeSubtitleCue" DROP CONSTRAINT IF EXISTS "VideoEpisodeSubtitleCue_baseline_scope_fkey";
ALTER TABLE "VideoEpisodeSubtitleCue" DROP CONSTRAINT IF EXISTS "VideoEpisodeSubtitleCue_episode_scope_fkey";
ALTER TABLE "VideoEpisodeSubtitleCue" DROP CONSTRAINT IF EXISTS "VideoEpisodeSubtitleCue_mix_new_scope_fkey";
ALTER TABLE "VideoEpisodeExportTask" DROP CONSTRAINT IF EXISTS "VideoEpisodeExportTask_baseline_scope_fkey";
ALTER TABLE "VideoEpisodeExportTask" DROP CONSTRAINT IF EXISTS "VideoEpisodeExportTask_edit_new_scope_fkey";
ALTER TABLE "VideoEpisodeExportTask" DROP CONSTRAINT IF EXISTS "VideoEpisodeExportTask_mix_new_scope_fkey";
ALTER TABLE "VideoEpisodeExportTask" DROP CONSTRAINT IF EXISTS "VideoEpisodeExportTask_retry_episode_fkey";
ALTER TABLE "VideoEpisodeExport" DROP CONSTRAINT IF EXISTS "VideoEpisodeExport_baseline_scope_fkey";
ALTER TABLE "VideoEpisodeExport" DROP CONSTRAINT IF EXISTS "VideoEpisodeExport_edit_new_scope_fkey";
ALTER TABLE "VideoEpisodeExport" DROP CONSTRAINT IF EXISTS "VideoEpisodeExport_mix_new_scope_fkey";
ALTER TABLE "VideoEpisodeExport" DROP CONSTRAINT IF EXISTS "VideoEpisodeExport_task_new_scope_fkey";

DROP TABLE IF EXISTS "VideoProductionEditHead", "VideoProductionMixHead";
DROP TABLE IF EXISTS "VideoProductionBaselineShot", "VideoTakeAdoption";
DROP TABLE IF EXISTS "VideoProductionBaseline", "VideoStoryboardDraft", "VideoShotVersion";
DROP TABLE IF EXISTS "VideoStoryboardVersion", "VideoShotLineage", "VideoEpisodeShot";

ALTER TABLE "VideoShotPromptVersion"
  DROP COLUMN IF EXISTS "videoEpisodeId",
  DROP COLUMN IF EXISTS "episodeShotId",
  DROP COLUMN IF EXISTS "episodeShotVersionId",
  DROP COLUMN IF EXISTS "productionBaselineId",
  ALTER COLUMN "shotId" SET NOT NULL,
  ALTER COLUMN "shotPlanVersionId" SET NOT NULL;
ALTER TABLE "VideoShotKeyframeVersion"
  DROP COLUMN IF EXISTS "videoEpisodeId",
  DROP COLUMN IF EXISTS "episodeShotId",
  DROP COLUMN IF EXISTS "episodeShotVersionId",
  DROP COLUMN IF EXISTS "productionBaselineId",
  ALTER COLUMN "adaptationId" SET NOT NULL,
  ALTER COLUMN "shotId" SET NOT NULL,
  ALTER COLUMN "shotPlanVersionId" SET NOT NULL;
ALTER TABLE "VideoShotRenderTask"
  DROP COLUMN IF EXISTS "videoEpisodeId",
  DROP COLUMN IF EXISTS "episodeShotId",
  DROP COLUMN IF EXISTS "episodeShotVersionId",
  DROP COLUMN IF EXISTS "productionBaselineId",
  ALTER COLUMN "adaptationId" SET NOT NULL,
  ALTER COLUMN "shotId" SET NOT NULL,
  ALTER COLUMN "shotPlanVersionId" SET NOT NULL,
  ALTER COLUMN "promptVersionId" SET NOT NULL;
ALTER TABLE "VideoShotTake"
  DROP COLUMN IF EXISTS "videoEpisodeId",
  DROP COLUMN IF EXISTS "episodeShotId",
  DROP COLUMN IF EXISTS "episodeShotVersionId",
  DROP COLUMN IF EXISTS "productionBaselineId",
  DROP COLUMN IF EXISTS "lastFrameAssetId",
  ALTER COLUMN "adaptationId" SET NOT NULL,
  ALTER COLUMN "shotId" SET NOT NULL,
  ALTER COLUMN "shotPlanVersionId" SET NOT NULL,
  ALTER COLUMN "promptVersionId" SET NOT NULL;
ALTER TABLE "VideoTakeFrameExtraction"
  DROP COLUMN IF EXISTS "videoEpisodeId",
  DROP COLUMN IF EXISTS "episodeShotId",
  DROP COLUMN IF EXISTS "episodeShotVersionId",
  DROP COLUMN IF EXISTS "productionBaselineId",
  ALTER COLUMN "adaptationId" SET NOT NULL,
  ALTER COLUMN "shotId" SET NOT NULL;
ALTER TABLE "VideoEpisodeEditVersion"
  DROP COLUMN IF EXISTS "videoEpisodeId",
  DROP COLUMN IF EXISTS "productionBaselineId",
  DROP COLUMN IF EXISTS "omissionsJson",
  ALTER COLUMN "adaptationId" SET NOT NULL,
  ALTER COLUMN "episodePlanVersionId" SET NOT NULL,
  ALTER COLUMN "shotPlanVersionId" SET NOT NULL,
  ALTER COLUMN "episodeNo" SET NOT NULL;
ALTER TABLE "VideoEpisodeEditClip"
  DROP COLUMN IF EXISTS "videoEpisodeId",
  DROP COLUMN IF EXISTS "productionBaselineId",
  DROP COLUMN IF EXISTS "episodeShotId",
  DROP COLUMN IF EXISTS "episodeShotVersionId",
  DROP COLUMN IF EXISTS "adoptionId",
  DROP COLUMN IF EXISTS "clipId",
  DROP COLUMN IF EXISTS "sourceAudioMode",
  ALTER COLUMN "shotId" SET NOT NULL,
  ALTER COLUMN "shotPlanVersionId" SET NOT NULL;
ALTER TABLE "VideoEpisodeMixVersion"
  DROP COLUMN IF EXISTS "videoEpisodeId",
  DROP COLUMN IF EXISTS "productionBaselineId",
  ALTER COLUMN "adaptationId" SET NOT NULL,
  ALTER COLUMN "episodePlanVersionId" SET NOT NULL,
  ALTER COLUMN "shotPlanVersionId" SET NOT NULL,
  ALTER COLUMN "episodeNo" SET NOT NULL;
ALTER TABLE "VideoEpisodeAudioClip"
  DROP COLUMN IF EXISTS "videoEpisodeId",
  DROP COLUMN IF EXISTS "productionBaselineId",
  DROP COLUMN IF EXISTS "episodeShotId",
  DROP COLUMN IF EXISTS "episodeShotVersionId",
  ALTER COLUMN "shotPlanVersionId" SET NOT NULL;
ALTER TABLE "VideoEpisodeSubtitleCue"
  DROP COLUMN IF EXISTS "videoEpisodeId",
  DROP COLUMN IF EXISTS "productionBaselineId",
  DROP COLUMN IF EXISTS "episodeShotId",
  DROP COLUMN IF EXISTS "episodeShotVersionId",
  DROP COLUMN IF EXISTS "scriptLineId",
  ALTER COLUMN "shotPlanVersionId" SET NOT NULL;
ALTER TABLE "VideoEpisodeExportTask"
  DROP COLUMN IF EXISTS "videoEpisodeId",
  DROP COLUMN IF EXISTS "productionBaselineId",
  ALTER COLUMN "adaptationId" SET NOT NULL,
  ALTER COLUMN "episodePlanVersionId" SET NOT NULL,
  ALTER COLUMN "shotPlanVersionId" SET NOT NULL,
  ALTER COLUMN "episodeNo" SET NOT NULL;
ALTER TABLE "VideoEpisodeExport"
  DROP COLUMN IF EXISTS "videoEpisodeId",
  DROP COLUMN IF EXISTS "productionBaselineId",
  ALTER COLUMN "adaptationId" SET NOT NULL,
  ALTER COLUMN "episodePlanVersionId" SET NOT NULL,
  ALTER COLUMN "episodeNo" SET NOT NULL;

ALTER TABLE "VideoImpactReview"
  DROP CONSTRAINT IF EXISTS "VideoImpactReview_production_revision_check",
  DROP COLUMN IF EXISTS "producerProductionRevision",
  DROP COLUMN IF EXISTS "targetProductionRevision",
  DROP COLUMN IF EXISTS "producerBaselineId",
  DROP COLUMN IF EXISTS "targetBaselineId";
ALTER TABLE "VideoEpisode"
  DROP CONSTRAINT IF EXISTS "VideoEpisode_production_revision_check",
  DROP CONSTRAINT IF EXISTS "VideoEpisode_delivery_revision_check",
  DROP COLUMN IF EXISTS "currentStoryboardVersionId",
  DROP COLUMN IF EXISTS "currentProductionBaselineId",
  DROP COLUMN IF EXISTS "productionRevision",
  DROP COLUMN IF EXISTS "latestDeliveryVersionId",
  DROP COLUMN IF EXISTS "deliveryRevision";

ALTER TABLE "ReviewArtifact" DROP CONSTRAINT IF EXISTS "ReviewArtifact_video_episode_target_check";
ALTER TYPE "ReviewArtifactKind" RENAME TO "ReviewArtifactKind_with_storyboard";
CREATE TYPE "ReviewArtifactKind" AS ENUM (
  'agent_updates','outline_draft','chapter_draft','lore_draft','revision_brief',
  'beat_plan_draft','chapter_content','beat_plan','freeform_markdown','video_scene_plan',
  'video_adaptation_plan','video_episode_script'
);
ALTER TABLE "ReviewArtifact" ALTER COLUMN kind TYPE "ReviewArtifactKind"
USING kind::text::"ReviewArtifactKind";
DROP TYPE "ReviewArtifactKind_with_storyboard";
ALTER TABLE "ReviewArtifact" ADD CONSTRAINT "ReviewArtifact_video_episode_target_check" CHECK (
  ("videoEpisodeId" IS NULL AND kind::text <> 'video_episode_script') OR
  ("videoEpisodeId" IS NOT NULL AND kind::text = 'video_episode_script'
    AND "chapterId" IS NULL AND "taskId" IS NULL AND "videoSceneId" IS NULL
    AND "videoAdaptationId" IS NULL AND "videoAdaptationTaskId" IS NULL)
);

COMMIT;
