BEGIN;
SET LOCAL search_path = public, pg_catalog;

-- 当前授权只允许具名隔离 PostgreSQL；不得据此连接服务器开发库或正式库。
DO $safety$
BEGIN
  IF current_database() NOT IN (
    'inkforge_video_episode_test',
    'inkforge_video_episode_codegen',
    'inkforge_video_production_test',
    'inkforge_video_production_codegen',
    'inkforge_video_production_post_codegen'
  ) THEN
    RAISE EXCEPTION '剧集分镜与制作基线迁移仅允许具名隔离数据库，当前为 %', current_database();
  END IF;
END
$safety$;
SELECT pg_advisory_xact_lock(hashtext('inkforge:20260910:video-production-baseline'));

ALTER TYPE "ReviewArtifactKind" ADD VALUE IF NOT EXISTS 'video_episode_storyboard';

ALTER TABLE "VideoEpisode"
  ADD COLUMN IF NOT EXISTS "currentStoryboardVersionId" TEXT,
  ADD COLUMN IF NOT EXISTS "currentProductionBaselineId" TEXT,
  ADD COLUMN IF NOT EXISTS "productionRevision" INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS "latestDeliveryVersionId" TEXT,
  ADD COLUMN IF NOT EXISTS "deliveryRevision" INTEGER NOT NULL DEFAULT 1;

DO $episode_revision_check$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoEpisode_production_revision_check'
      AND conrelid = 'public."VideoEpisode"'::regclass
  ) THEN
    ALTER TABLE "VideoEpisode" ADD CONSTRAINT "VideoEpisode_production_revision_check"
      CHECK ("productionRevision" > 0);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoEpisode_delivery_revision_check'
      AND conrelid = 'public."VideoEpisode"'::regclass
  ) THEN
    ALTER TABLE "VideoEpisode" ADD CONSTRAINT "VideoEpisode_delivery_revision_check"
      CHECK ("deliveryRevision" > 0);
  END IF;
END
$episode_revision_check$;

CREATE TABLE IF NOT EXISTS "VideoEpisodeShot" (
  id TEXT PRIMARY KEY,
  "episodeId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "createdByUserId" TEXT NOT NULL REFERENCES "User"(id) ON DELETE RESTRICT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoEpisodeShot_episode_project_fkey"
    FOREIGN KEY ("episodeId","projectId") REFERENCES "VideoEpisode"(id,"projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoEpisodeShot_id_episode_key" UNIQUE(id,"episodeId"),
  CONSTRAINT "VideoEpisodeShot_id_scope_key" UNIQUE(id,"episodeId","projectId")
);
CREATE INDEX IF NOT EXISTS "VideoEpisodeShot_episode_created_idx"
ON "VideoEpisodeShot"("episodeId","createdAt",id);

CREATE TABLE IF NOT EXISTS "VideoShotLineage" (
  "childShotId" TEXT NOT NULL,
  "sourceShotId" TEXT NOT NULL,
  "episodeId" TEXT NOT NULL,
  ordinal INTEGER NOT NULL CHECK (ordinal > 0),
  relation TEXT NOT NULL CHECK (relation IN ('replacement','copy','split','merge')),
  CONSTRAINT "VideoShotLineage_pkey" PRIMARY KEY ("childShotId",ordinal),
  CONSTRAINT "VideoShotLineage_child_fkey"
    FOREIGN KEY ("childShotId","episodeId") REFERENCES "VideoEpisodeShot"(id,"episodeId") ON DELETE RESTRICT,
  CONSTRAINT "VideoShotLineage_source_fkey"
    FOREIGN KEY ("sourceShotId","episodeId") REFERENCES "VideoEpisodeShot"(id,"episodeId") ON DELETE RESTRICT,
  CONSTRAINT "VideoShotLineage_child_source_key" UNIQUE("childShotId","sourceShotId"),
  CONSTRAINT "VideoShotLineage_distinct_check" CHECK ("childShotId" <> "sourceShotId")
);
CREATE INDEX IF NOT EXISTS "VideoShotLineage_source_idx"
ON "VideoShotLineage"("sourceShotId","childShotId");

CREATE TABLE IF NOT EXISTS "VideoStoryboardVersion" (
  id TEXT PRIMARY KEY,
  "episodeId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "versionNo" INTEGER NOT NULL CHECK ("versionNo" > 0),
  "basedOnVersionId" TEXT,
  "scriptVersionId" TEXT NOT NULL,
  "documentJson" TEXT NOT NULL CHECK (jsonb_typeof("documentJson"::jsonb) = 'object'),
  "contentHash" TEXT NOT NULL CHECK ("contentHash" ~ '^[0-9a-f]{64}$'),
  "reviewArtifactId" TEXT NOT NULL REFERENCES "ReviewArtifact"(id) ON DELETE RESTRICT,
  "approvedByUserId" TEXT NOT NULL REFERENCES "User"(id) ON DELETE RESTRICT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoStoryboardVersion_episode_project_fkey"
    FOREIGN KEY ("episodeId","projectId") REFERENCES "VideoEpisode"(id,"projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoStoryboardVersion_script_fkey"
    FOREIGN KEY ("scriptVersionId","episodeId","projectId")
    REFERENCES "VideoEpisodeScriptVersion"(id,"episodeId","projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoStoryboardVersion_base_fkey"
    FOREIGN KEY ("basedOnVersionId","episodeId") REFERENCES "VideoStoryboardVersion"(id,"episodeId") ON DELETE RESTRICT,
  CONSTRAINT "VideoStoryboardVersion_review_episode_fkey"
    FOREIGN KEY ("reviewArtifactId","episodeId") REFERENCES "ReviewArtifact"(id,"videoEpisodeId") ON DELETE RESTRICT,
  CONSTRAINT "VideoStoryboardVersion_id_episode_key" UNIQUE(id,"episodeId"),
  CONSTRAINT "VideoStoryboardVersion_id_scope_key" UNIQUE(id,"episodeId","projectId"),
  CONSTRAINT "VideoStoryboardVersion_id_script_scope_key" UNIQUE(id,"scriptVersionId","episodeId","projectId"),
  CONSTRAINT "VideoStoryboardVersion_episode_version_key" UNIQUE("episodeId","versionNo"),
  CONSTRAINT "VideoStoryboardVersion_artifact_key" UNIQUE("reviewArtifactId")
);

CREATE TABLE IF NOT EXISTS "VideoShotVersion" (
  id TEXT PRIMARY KEY,
  "shotId" TEXT NOT NULL,
  "episodeId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "storyboardVersionId" TEXT NOT NULL,
  ordinal INTEGER NOT NULL CHECK (ordinal > 0),
  "versionNo" INTEGER NOT NULL CHECK ("versionNo" > 0),
  "scriptSceneId" TEXT NOT NULL CHECK (btrim("scriptSceneId") <> ''),
  "scriptLineIdsJson" TEXT NOT NULL CHECK (jsonb_typeof("scriptLineIdsJson"::jsonb) = 'array'),
  "contentJson" TEXT NOT NULL CHECK (jsonb_typeof("contentJson"::jsonb) = 'object'),
  "contentHash" TEXT NOT NULL CHECK ("contentHash" ~ '^[0-9a-f]{64}$'),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoShotVersion_shot_scope_fkey"
    FOREIGN KEY ("shotId","episodeId","projectId")
    REFERENCES "VideoEpisodeShot"(id,"episodeId","projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoShotVersion_storyboard_scope_fkey"
    FOREIGN KEY ("storyboardVersionId","episodeId","projectId")
    REFERENCES "VideoStoryboardVersion"(id,"episodeId","projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoShotVersion_id_shot_episode_key" UNIQUE(id,"shotId","episodeId"),
  CONSTRAINT "VideoShotVersion_id_scope_key" UNIQUE(id,"shotId","episodeId","projectId"),
  CONSTRAINT "VideoShotVersion_storyboard_ordinal_key" UNIQUE("storyboardVersionId",ordinal),
  CONSTRAINT "VideoShotVersion_storyboard_shot_key" UNIQUE("storyboardVersionId","shotId"),
  CONSTRAINT "VideoShotVersion_shot_version_key" UNIQUE("shotId","versionNo")
);
CREATE INDEX IF NOT EXISTS "VideoShotVersion_episode_created_idx"
ON "VideoShotVersion"("episodeId","createdAt",id);

CREATE TABLE IF NOT EXISTS "VideoStoryboardDraft" (
  "episodeId" TEXT PRIMARY KEY REFERENCES "VideoEpisode"(id) ON DELETE RESTRICT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
  "basedOnStoryboardVersionId" TEXT,
  "scriptVersionId" TEXT,
  "documentJson" TEXT NOT NULL CHECK (jsonb_typeof("documentJson"::jsonb) = 'object'),
  "contentHash" TEXT NOT NULL CHECK ("contentHash" ~ '^[0-9a-f]{64}$'),
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoStoryboardDraft_base_fkey"
    FOREIGN KEY ("basedOnStoryboardVersionId","episodeId")
    REFERENCES "VideoStoryboardVersion"(id,"episodeId") ON DELETE RESTRICT,
  CONSTRAINT "VideoStoryboardDraft_script_fkey"
    FOREIGN KEY ("scriptVersionId","episodeId")
    REFERENCES "VideoEpisodeScriptVersion"(id,"episodeId") ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS "VideoProductionBaseline" (
  id TEXT PRIMARY KEY,
  "episodeId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "versionNo" INTEGER NOT NULL CHECK ("versionNo" > 0),
  "basedOnBaselineId" TEXT,
  "scriptVersionId" TEXT NOT NULL,
  "storyboardVersionId" TEXT NOT NULL,
  "manifestJson" TEXT NOT NULL CHECK (jsonb_typeof("manifestJson"::jsonb) = 'object'),
  "contentHash" TEXT NOT NULL CHECK ("contentHash" ~ '^[0-9a-f]{64}$'),
  "createdByUserId" TEXT NOT NULL REFERENCES "User"(id) ON DELETE RESTRICT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoProductionBaseline_episode_project_fkey"
    FOREIGN KEY ("episodeId","projectId") REFERENCES "VideoEpisode"(id,"projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoProductionBaseline_storyboard_script_fkey"
    FOREIGN KEY ("storyboardVersionId","scriptVersionId","episodeId","projectId")
    REFERENCES "VideoStoryboardVersion"(id,"scriptVersionId","episodeId","projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoProductionBaseline_base_fkey"
    FOREIGN KEY ("basedOnBaselineId","episodeId") REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT,
  CONSTRAINT "VideoProductionBaseline_id_episode_key" UNIQUE(id,"episodeId"),
  CONSTRAINT "VideoProductionBaseline_id_scope_key" UNIQUE(id,"episodeId","projectId"),
  CONSTRAINT "VideoProductionBaseline_episode_version_key" UNIQUE("episodeId","versionNo")
);

CREATE TABLE IF NOT EXISTS "VideoTakeAdoption" (
  id TEXT PRIMARY KEY,
  "episodeId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "targetShotId" TEXT NOT NULL,
  "targetShotVersionId" TEXT NOT NULL,
  "sourceTakeId" TEXT NOT NULL REFERENCES "VideoShotTake"(id) ON DELETE RESTRICT,
  "sourceBaselineId" TEXT,
  "comparisonJson" TEXT NOT NULL CHECK (jsonb_typeof("comparisonJson"::jsonb) = 'object'),
  "decisionHash" TEXT NOT NULL CHECK ("decisionHash" ~ '^[0-9a-f]{64}$'),
  "createdByUserId" TEXT NOT NULL REFERENCES "User"(id) ON DELETE RESTRICT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoTakeAdoption_target_scope_fkey"
    FOREIGN KEY ("targetShotVersionId","targetShotId","episodeId","projectId")
    REFERENCES "VideoShotVersion"(id,"shotId","episodeId","projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoTakeAdoption_source_baseline_fkey"
    FOREIGN KEY ("sourceBaselineId","episodeId")
    REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT,
  CONSTRAINT "VideoTakeAdoption_id_target_scope_key"
    UNIQUE(id,"episodeId","targetShotId","targetShotVersionId"),
  CONSTRAINT "VideoTakeAdoption_id_take_target_scope_key"
    UNIQUE(id,"sourceTakeId","episodeId","targetShotId","targetShotVersionId")
);
CREATE INDEX IF NOT EXISTS "VideoTakeAdoption_source_take_idx"
ON "VideoTakeAdoption"("sourceTakeId","createdAt");

CREATE TABLE IF NOT EXISTS "VideoProductionBaselineShot" (
  "baselineId" TEXT NOT NULL,
  "episodeId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  ordinal INTEGER NOT NULL CHECK (ordinal > 0),
  "shotId" TEXT NOT NULL,
  "shotVersionId" TEXT NOT NULL,
  "adoptionId" TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','adopted')),
  "inputSnapshotJson" TEXT NOT NULL CHECK (jsonb_typeof("inputSnapshotJson"::jsonb) = 'object'),
  "inputHash" TEXT NOT NULL CHECK ("inputHash" ~ '^[0-9a-f]{64}$'),
  CONSTRAINT "VideoProductionBaselineShot_pkey" PRIMARY KEY ("baselineId",ordinal),
  CONSTRAINT "VideoProductionBaselineShot_baseline_scope_fkey"
    FOREIGN KEY ("baselineId","episodeId","projectId")
    REFERENCES "VideoProductionBaseline"(id,"episodeId","projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoProductionBaselineShot_version_scope_fkey"
    FOREIGN KEY ("shotVersionId","shotId","episodeId","projectId")
    REFERENCES "VideoShotVersion"(id,"shotId","episodeId","projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoProductionBaselineShot_adoption_scope_fkey"
    FOREIGN KEY ("adoptionId","episodeId","shotId","shotVersionId")
    REFERENCES "VideoTakeAdoption"(id,"episodeId","targetShotId","targetShotVersionId") ON DELETE RESTRICT,
  CONSTRAINT "VideoProductionBaselineShot_status_adoption_check" CHECK (
    (status = 'adopted' AND "adoptionId" IS NOT NULL)
    OR (status = 'pending' AND "adoptionId" IS NULL)
  ),
  CONSTRAINT "VideoProductionBaselineShot_baseline_shot_key" UNIQUE("baselineId","shotId")
  ,CONSTRAINT "VideoProductionBaselineShot_input_scope_key"
    UNIQUE("baselineId","shotVersionId","episodeId","shotId")
);
CREATE INDEX IF NOT EXISTS "VideoProductionBaselineShot_version_idx"
ON "VideoProductionBaselineShot"("shotVersionId");

ALTER TABLE "VideoImpactReview"
  ADD COLUMN IF NOT EXISTS "producerProductionRevision" INTEGER,
  ADD COLUMN IF NOT EXISTS "targetProductionRevision" INTEGER,
  ADD COLUMN IF NOT EXISTS "producerBaselineId" TEXT,
  ADD COLUMN IF NOT EXISTS "targetBaselineId" TEXT;

DO $impact_scope_constraints$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoImpactReview_producer_baseline_fkey') THEN
    ALTER TABLE "VideoImpactReview" ADD CONSTRAINT "VideoImpactReview_producer_baseline_fkey"
      FOREIGN KEY ("producerBaselineId","producerEpisodeId")
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
    ALTER TABLE "VideoImpactReview" ADD CONSTRAINT "VideoImpactReview_target_baseline_fkey"
      FOREIGN KEY ("targetBaselineId","targetEpisodeId")
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
    ALTER TABLE "VideoImpactReview" ADD CONSTRAINT "VideoImpactReview_production_revision_check"
      CHECK (
        ("producerProductionRevision" IS NULL OR "producerProductionRevision" > 0)
        AND ("targetProductionRevision" IS NULL OR "targetProductionRevision" > 0)
      );
  END IF;
END
$impact_scope_constraints$;

-- P2 同批给既有媒体消费者增加明确的新域归属；旧字段保留只读兼容，P3 接通新写行为前不伪造桥接数据。
ALTER TABLE "VideoShotPromptVersion"
  ADD COLUMN IF NOT EXISTS "videoEpisodeId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotVersionId" TEXT,
  ADD COLUMN IF NOT EXISTS "productionBaselineId" TEXT;
ALTER TABLE "VideoShotKeyframeVersion"
  ADD COLUMN IF NOT EXISTS "videoEpisodeId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotVersionId" TEXT,
  ADD COLUMN IF NOT EXISTS "productionBaselineId" TEXT;
ALTER TABLE "VideoShotRenderTask"
  ADD COLUMN IF NOT EXISTS "videoEpisodeId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotVersionId" TEXT,
  ADD COLUMN IF NOT EXISTS "productionBaselineId" TEXT;
ALTER TABLE "VideoShotTake"
  ADD COLUMN IF NOT EXISTS "videoEpisodeId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotVersionId" TEXT,
  ADD COLUMN IF NOT EXISTS "productionBaselineId" TEXT,
  ADD COLUMN IF NOT EXISTS "lastFrameAssetId" TEXT;
ALTER TABLE "VideoTakeFrameExtraction"
  ADD COLUMN IF NOT EXISTS "videoEpisodeId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotVersionId" TEXT,
  ADD COLUMN IF NOT EXISTS "productionBaselineId" TEXT;
ALTER TABLE "VideoEpisodeEditVersion"
  ADD COLUMN IF NOT EXISTS "videoEpisodeId" TEXT,
  ADD COLUMN IF NOT EXISTS "productionBaselineId" TEXT,
  ADD COLUMN IF NOT EXISTS "omissionsJson" TEXT NOT NULL DEFAULT '[]';
ALTER TABLE "VideoEpisodeEditClip"
  ADD COLUMN IF NOT EXISTS "videoEpisodeId" TEXT,
  ADD COLUMN IF NOT EXISTS "productionBaselineId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotVersionId" TEXT,
  ADD COLUMN IF NOT EXISTS "adoptionId" TEXT,
  ADD COLUMN IF NOT EXISTS "sourceAudioMode" TEXT NOT NULL DEFAULT 'keep';
ALTER TABLE "VideoEpisodeMixVersion"
  ADD COLUMN IF NOT EXISTS "videoEpisodeId" TEXT,
  ADD COLUMN IF NOT EXISTS "productionBaselineId" TEXT;
ALTER TABLE "VideoEpisodeAudioClip"
  ADD COLUMN IF NOT EXISTS "videoEpisodeId" TEXT,
  ADD COLUMN IF NOT EXISTS "productionBaselineId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotVersionId" TEXT;
ALTER TABLE "VideoEpisodeSubtitleCue"
  ADD COLUMN IF NOT EXISTS "videoEpisodeId" TEXT,
  ADD COLUMN IF NOT EXISTS "productionBaselineId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotId" TEXT,
  ADD COLUMN IF NOT EXISTS "episodeShotVersionId" TEXT,
  ADD COLUMN IF NOT EXISTS "scriptLineId" TEXT;
ALTER TABLE "VideoEpisodeExportTask"
  ADD COLUMN IF NOT EXISTS "videoEpisodeId" TEXT,
  ADD COLUMN IF NOT EXISTS "productionBaselineId" TEXT;
ALTER TABLE "VideoEpisodeExport"
  ADD COLUMN IF NOT EXISTS "videoEpisodeId" TEXT,
  ADD COLUMN IF NOT EXISTS "productionBaselineId" TEXT;

-- 旧分支继续使用 adaptation/plan 身份；新分支只使用 episode/baseline/shotVersion，禁止占位旧 ID。
ALTER TABLE "VideoShotPromptVersion"
  ALTER COLUMN "shotId" DROP NOT NULL,
  ALTER COLUMN "shotPlanVersionId" DROP NOT NULL;
ALTER TABLE "VideoShotKeyframeVersion"
  ALTER COLUMN "adaptationId" DROP NOT NULL,
  ALTER COLUMN "shotId" DROP NOT NULL,
  ALTER COLUMN "shotPlanVersionId" DROP NOT NULL;
ALTER TABLE "VideoShotRenderTask"
  ALTER COLUMN "adaptationId" DROP NOT NULL,
  ALTER COLUMN "shotId" DROP NOT NULL,
  ALTER COLUMN "shotPlanVersionId" DROP NOT NULL,
  ALTER COLUMN "promptVersionId" DROP NOT NULL;
ALTER TABLE "VideoShotTake"
  ALTER COLUMN "adaptationId" DROP NOT NULL,
  ALTER COLUMN "shotId" DROP NOT NULL,
  ALTER COLUMN "shotPlanVersionId" DROP NOT NULL,
  ALTER COLUMN "promptVersionId" DROP NOT NULL;
ALTER TABLE "VideoTakeFrameExtraction"
  ALTER COLUMN "adaptationId" DROP NOT NULL,
  ALTER COLUMN "shotId" DROP NOT NULL;
ALTER TABLE "VideoEpisodeEditVersion"
  ALTER COLUMN "adaptationId" DROP NOT NULL,
  ALTER COLUMN "episodePlanVersionId" DROP NOT NULL,
  ALTER COLUMN "shotPlanVersionId" DROP NOT NULL,
  ALTER COLUMN "episodeNo" DROP NOT NULL;
ALTER TABLE "VideoEpisodeEditClip"
  ADD COLUMN IF NOT EXISTS "clipId" TEXT;
UPDATE "VideoEpisodeEditClip"
SET "clipId" = 'legacy_clip_' || md5("editVersionId" || ':' || ordinal::text)
WHERE "clipId" IS NULL;
ALTER TABLE "VideoEpisodeEditClip"
  ALTER COLUMN "shotId" DROP NOT NULL,
  ALTER COLUMN "shotPlanVersionId" DROP NOT NULL;
ALTER TABLE "VideoEpisodeMixVersion"
  ALTER COLUMN "adaptationId" DROP NOT NULL,
  ALTER COLUMN "episodePlanVersionId" DROP NOT NULL,
  ALTER COLUMN "shotPlanVersionId" DROP NOT NULL,
  ALTER COLUMN "episodeNo" DROP NOT NULL;
ALTER TABLE "VideoEpisodeAudioClip"
  ALTER COLUMN "shotPlanVersionId" DROP NOT NULL;
ALTER TABLE "VideoEpisodeSubtitleCue"
  ALTER COLUMN "shotPlanVersionId" DROP NOT NULL;
ALTER TABLE "VideoEpisodeExportTask"
  ALTER COLUMN "adaptationId" DROP NOT NULL,
  ALTER COLUMN "episodePlanVersionId" DROP NOT NULL,
  ALTER COLUMN "shotPlanVersionId" DROP NOT NULL,
  ALTER COLUMN "episodeNo" DROP NOT NULL;
ALTER TABLE "VideoEpisodeExport"
  ALTER COLUMN "adaptationId" DROP NOT NULL,
  ALTER COLUMN "episodePlanVersionId" DROP NOT NULL,
  ALTER COLUMN "episodeNo" DROP NOT NULL;

-- 粗剪保存 Adoption 的目标镜头／目标基线，而 Take 保留原始生成镜头／源基线。
-- adoption_take 已同时冻结 sourceTakeId 与目标 scope；继续把 clip 的目标 scope
-- 强制等于 Take 源 scope 会错误拒绝 B0 Take 被 B1 显式采用的合法关系。
ALTER TABLE "VideoEpisodeEditClip"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeEditClip_take_new_scope_fkey";

DO $consumer_branch_constraints$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoShotPromptVersion_scope_branch_check') THEN
    ALTER TABLE "VideoShotPromptVersion" ADD CONSTRAINT "VideoShotPromptVersion_scope_branch_check" CHECK (
      ("shotId" IS NOT NULL AND "shotPlanVersionId" IS NOT NULL AND "videoEpisodeId" IS NULL
        AND "episodeShotId" IS NULL AND "episodeShotVersionId" IS NULL AND "productionBaselineId" IS NULL)
      OR
      ("shotId" IS NULL AND "shotPlanVersionId" IS NULL AND "sourceTaskId" IS NULL
        AND "videoEpisodeId" IS NOT NULL AND "episodeShotId" IS NOT NULL
        AND "episodeShotVersionId" IS NOT NULL AND "productionBaselineId" IS NOT NULL)
    );
    ALTER TABLE "VideoShotPromptVersion" ADD CONSTRAINT "VideoShotPromptVersion_id_episode_shot_key"
      UNIQUE(id,"episodeShotId");
    ALTER TABLE "VideoShotPromptVersion" ADD CONSTRAINT "VideoShotPromptVersion_id_new_scope_key"
      UNIQUE(id,"videoEpisodeId","episodeShotId","episodeShotVersionId","productionBaselineId");
    ALTER TABLE "VideoShotPromptVersion" ADD CONSTRAINT "VideoShotPromptVersion_based_on_episode_fkey"
      FOREIGN KEY ("basedOnVersionId","episodeShotId")
      REFERENCES "VideoShotPromptVersion"(id,"episodeShotId") ON DELETE RESTRICT;
    ALTER TABLE "VideoShotPromptVersion" ADD CONSTRAINT "VideoShotPromptVersion_baseline_input_fkey"
      FOREIGN KEY ("productionBaselineId","episodeShotVersionId","videoEpisodeId","episodeShotId")
      REFERENCES "VideoProductionBaselineShot"("baselineId","shotVersionId","episodeId","shotId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoShotKeyframeVersion_scope_branch_check') THEN
    ALTER TABLE "VideoShotKeyframeVersion" ADD CONSTRAINT "VideoShotKeyframeVersion_scope_branch_check" CHECK (
      ("adaptationId" IS NOT NULL AND "shotId" IS NOT NULL AND "shotPlanVersionId" IS NOT NULL
        AND "videoEpisodeId" IS NULL AND "episodeShotId" IS NULL
        AND "episodeShotVersionId" IS NULL AND "productionBaselineId" IS NULL)
      OR
      ("adaptationId" IS NULL AND "shotId" IS NULL AND "shotPlanVersionId" IS NULL
        AND "videoEpisodeId" IS NOT NULL AND "episodeShotId" IS NOT NULL
        AND "episodeShotVersionId" IS NOT NULL AND "productionBaselineId" IS NOT NULL)
    );
    ALTER TABLE "VideoShotKeyframeVersion" ADD CONSTRAINT "VideoShotKeyframeVersion_id_episode_role_key"
      UNIQUE(id,"episodeShotId",role);
    ALTER TABLE "VideoShotKeyframeVersion" ADD CONSTRAINT "VideoShotKeyframeVersion_based_on_episode_fkey"
      FOREIGN KEY ("basedOnVersionId","episodeShotId",role)
      REFERENCES "VideoShotKeyframeVersion"(id,"episodeShotId",role) ON DELETE RESTRICT;
    ALTER TABLE "VideoShotKeyframeVersion" ADD CONSTRAINT "VideoShotKeyframeVersion_baseline_input_fkey"
      FOREIGN KEY ("productionBaselineId","episodeShotVersionId","videoEpisodeId","episodeShotId")
      REFERENCES "VideoProductionBaselineShot"("baselineId","shotVersionId","episodeId","shotId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoShotRenderTask_scope_branch_check') THEN
    ALTER TABLE "VideoShotRenderTask" ADD CONSTRAINT "VideoShotRenderTask_scope_branch_check" CHECK (
      ("adaptationId" IS NOT NULL AND "shotId" IS NOT NULL AND "shotPlanVersionId" IS NOT NULL
        AND "promptVersionId" IS NOT NULL AND "videoEpisodeId" IS NULL AND "episodeShotId" IS NULL
        AND "episodeShotVersionId" IS NULL AND "productionBaselineId" IS NULL)
      OR
      ("adaptationId" IS NULL AND "shotId" IS NULL AND "shotPlanVersionId" IS NULL
        AND "promptVersionId" IS NOT NULL AND "videoEpisodeId" IS NOT NULL AND "episodeShotId" IS NOT NULL
        AND "episodeShotVersionId" IS NOT NULL AND "productionBaselineId" IS NOT NULL)
    );
    ALTER TABLE "VideoShotRenderTask" ADD CONSTRAINT "VideoShotRenderTask_id_episode_scope_key"
      UNIQUE(
        id,"videoEpisodeId","projectId","novelId","episodeShotId",
        "episodeShotVersionId","productionBaselineId","promptVersionId"
      );
    ALTER TABLE "VideoShotRenderTask" ADD CONSTRAINT "VideoShotRenderTask_id_episode_shot_key"
      UNIQUE(id,"episodeShotId");
    ALTER TABLE "VideoShotRenderTask" ADD CONSTRAINT "VideoShotRenderTask_retry_episode_fkey"
      FOREIGN KEY ("retryOfTaskId","episodeShotId")
      REFERENCES "VideoShotRenderTask"(id,"episodeShotId") ON DELETE RESTRICT;
    ALTER TABLE "VideoShotRenderTask" ADD CONSTRAINT "VideoShotRenderTask_baseline_input_fkey"
      FOREIGN KEY ("productionBaselineId","episodeShotVersionId","videoEpisodeId","episodeShotId")
      REFERENCES "VideoProductionBaselineShot"("baselineId","shotVersionId","episodeId","shotId") ON DELETE RESTRICT;
    ALTER TABLE "VideoShotRenderTask" ADD CONSTRAINT "VideoShotRenderTask_prompt_new_scope_fkey"
      FOREIGN KEY ("promptVersionId","videoEpisodeId","episodeShotId","episodeShotVersionId","productionBaselineId")
      REFERENCES "VideoShotPromptVersion"(id,"videoEpisodeId","episodeShotId","episodeShotVersionId","productionBaselineId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoShotTake_scope_branch_check') THEN
    ALTER TABLE "VideoShotTake" ADD CONSTRAINT "VideoShotTake_scope_branch_check" CHECK (
      ("adaptationId" IS NOT NULL AND "shotId" IS NOT NULL AND "shotPlanVersionId" IS NOT NULL
        AND "promptVersionId" IS NOT NULL AND "videoEpisodeId" IS NULL AND "episodeShotId" IS NULL
        AND "episodeShotVersionId" IS NULL AND "productionBaselineId" IS NULL)
      OR
      ("adaptationId" IS NULL AND "shotId" IS NULL AND "shotPlanVersionId" IS NULL
        AND "promptVersionId" IS NOT NULL AND "videoEpisodeId" IS NOT NULL AND "episodeShotId" IS NOT NULL
        AND "episodeShotVersionId" IS NOT NULL AND "productionBaselineId" IS NOT NULL)
    );
    ALTER TABLE "VideoShotTake" ADD CONSTRAINT "VideoShotTake_task_episode_scope_fkey"
      FOREIGN KEY (
        "taskId","videoEpisodeId","projectId","novelId","episodeShotId",
        "episodeShotVersionId","productionBaselineId","promptVersionId"
      )
      REFERENCES "VideoShotRenderTask"(
        id,"videoEpisodeId","projectId","novelId","episodeShotId",
        "episodeShotVersionId","productionBaselineId","promptVersionId"
      ) ON DELETE RESTRICT;
    ALTER TABLE "VideoShotTake" ADD CONSTRAINT "VideoShotTake_id_episode_shot_version_baseline_key"
      UNIQUE(id,"videoEpisodeId","episodeShotId","episodeShotVersionId","productionBaselineId");
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoTakeFrameExtraction_scope_branch_check') THEN
    ALTER TABLE "VideoTakeFrameExtraction" ADD CONSTRAINT "VideoTakeFrameExtraction_scope_branch_check" CHECK (
      ("adaptationId" IS NOT NULL AND "shotId" IS NOT NULL AND "videoEpisodeId" IS NULL
        AND "episodeShotId" IS NULL AND "episodeShotVersionId" IS NULL AND "productionBaselineId" IS NULL)
      OR
      ("adaptationId" IS NULL AND "shotId" IS NULL AND "videoEpisodeId" IS NOT NULL
        AND "episodeShotId" IS NOT NULL AND "episodeShotVersionId" IS NOT NULL
        AND "productionBaselineId" IS NOT NULL)
    );
    ALTER TABLE "VideoTakeFrameExtraction" ADD CONSTRAINT "VideoTakeFrameExtraction_take_episode_scope_fkey"
      FOREIGN KEY ("takeId","videoEpisodeId","episodeShotId","episodeShotVersionId","productionBaselineId")
      REFERENCES "VideoShotTake"(id,"videoEpisodeId","episodeShotId","episodeShotVersionId","productionBaselineId") ON DELETE RESTRICT;
  END IF;
END
$consumer_branch_constraints$;

DO $post_branch_constraints$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeEditVersion_scope_branch_check') THEN
    ALTER TABLE "VideoEpisodeEditVersion" ADD CONSTRAINT "VideoEpisodeEditVersion_scope_branch_check" CHECK (
      ("adaptationId" IS NOT NULL AND "episodePlanVersionId" IS NOT NULL
        AND "shotPlanVersionId" IS NOT NULL AND "episodeNo" IS NOT NULL
        AND "videoEpisodeId" IS NULL AND "productionBaselineId" IS NULL)
      OR
      ("adaptationId" IS NULL AND "episodePlanVersionId" IS NULL
        AND "shotPlanVersionId" IS NULL AND "episodeNo" IS NULL
        AND "videoEpisodeId" IS NOT NULL AND "productionBaselineId" IS NOT NULL)
    );
    ALTER TABLE "VideoEpisodeEditVersion" ADD CONSTRAINT "VideoEpisodeEditVersion_id_new_scope_key"
      UNIQUE(id,"videoEpisodeId","productionBaselineId");
    ALTER TABLE "VideoEpisodeEditVersion" ADD CONSTRAINT "VideoEpisodeEditVersion_id_video_episode_key"
      UNIQUE(id,"videoEpisodeId");
    ALTER TABLE "VideoEpisodeEditVersion" ADD CONSTRAINT "VideoEpisodeEditVersion_based_on_episode_fkey"
      FOREIGN KEY ("basedOnVersionId","videoEpisodeId")
      REFERENCES "VideoEpisodeEditVersion"(id,"videoEpisodeId") ON DELETE RESTRICT;
    ALTER TABLE "VideoEpisodeEditVersion" ADD CONSTRAINT "VideoEpisodeEditVersion_omissions_json_check"
      CHECK (COALESCE(jsonb_typeof("omissionsJson"::jsonb) = 'array', FALSE));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeEditClip_scope_branch_check') THEN
    ALTER TABLE "VideoEpisodeEditClip" ADD CONSTRAINT "VideoEpisodeEditClip_scope_branch_check" CHECK (
      ("shotId" IS NOT NULL AND "shotPlanVersionId" IS NOT NULL
        AND "videoEpisodeId" IS NULL AND "productionBaselineId" IS NULL
        AND "episodeShotId" IS NULL AND "episodeShotVersionId" IS NULL AND "adoptionId" IS NULL)
      OR
      ("shotId" IS NULL AND "shotPlanVersionId" IS NULL
        AND "clipId" IS NOT NULL
        AND "videoEpisodeId" IS NOT NULL AND "productionBaselineId" IS NOT NULL
        AND "episodeShotId" IS NOT NULL AND "episodeShotVersionId" IS NOT NULL
        AND "takeId" IS NOT NULL AND "adoptionId" IS NOT NULL)
    );
    ALTER TABLE "VideoEpisodeEditClip" ADD CONSTRAINT "VideoEpisodeEditClip_clipId_key" UNIQUE("clipId");
    ALTER TABLE "VideoEpisodeEditClip" ADD CONSTRAINT "VideoEpisodeEditClip_source_audio_mode_check"
      CHECK ("sourceAudioMode" IN ('keep','mute'));
    ALTER TABLE "VideoEpisodeEditClip" ADD CONSTRAINT "VideoEpisodeEditClip_edit_new_scope_fkey"
      FOREIGN KEY ("editVersionId","videoEpisodeId","productionBaselineId")
      REFERENCES "VideoEpisodeEditVersion"(id,"videoEpisodeId","productionBaselineId") ON DELETE RESTRICT;
    ALTER TABLE "VideoEpisodeEditClip" ADD CONSTRAINT "VideoEpisodeEditClip_adoption_take_fkey"
      FOREIGN KEY ("adoptionId","takeId","videoEpisodeId","episodeShotId","episodeShotVersionId")
      REFERENCES "VideoTakeAdoption"(id,"sourceTakeId","episodeId","targetShotId","targetShotVersionId") ON DELETE RESTRICT;
    ALTER TABLE "VideoEpisodeEditClip" ADD CONSTRAINT "VideoEpisodeEditClip_baseline_input_fkey"
      FOREIGN KEY ("productionBaselineId","episodeShotVersionId","videoEpisodeId","episodeShotId")
      REFERENCES "VideoProductionBaselineShot"("baselineId","shotVersionId","episodeId","shotId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeMixVersion_scope_branch_check') THEN
    ALTER TABLE "VideoEpisodeMixVersion" ADD CONSTRAINT "VideoEpisodeMixVersion_scope_branch_check" CHECK (
      ("adaptationId" IS NOT NULL AND "episodePlanVersionId" IS NOT NULL
        AND "shotPlanVersionId" IS NOT NULL AND "episodeNo" IS NOT NULL
        AND "videoEpisodeId" IS NULL AND "productionBaselineId" IS NULL)
      OR
      ("adaptationId" IS NULL AND "episodePlanVersionId" IS NULL
        AND "shotPlanVersionId" IS NULL AND "episodeNo" IS NULL
        AND "videoEpisodeId" IS NOT NULL AND "productionBaselineId" IS NOT NULL)
    );
    ALTER TABLE "VideoEpisodeMixVersion" ADD CONSTRAINT "VideoEpisodeMixVersion_id_new_scope_key"
      UNIQUE(id,"videoEpisodeId","productionBaselineId");
    ALTER TABLE "VideoEpisodeMixVersion" ADD CONSTRAINT "VideoEpisodeMixVersion_id_video_episode_key"
      UNIQUE(id,"videoEpisodeId");
    ALTER TABLE "VideoEpisodeMixVersion" ADD CONSTRAINT "VideoEpisodeMixVersion_edit_new_scope_fkey"
      FOREIGN KEY ("editVersionId","videoEpisodeId","productionBaselineId")
      REFERENCES "VideoEpisodeEditVersion"(id,"videoEpisodeId","productionBaselineId") ON DELETE RESTRICT;
    ALTER TABLE "VideoEpisodeMixVersion" ADD CONSTRAINT "VideoEpisodeMixVersion_based_on_episode_fkey"
      FOREIGN KEY ("basedOnVersionId","videoEpisodeId")
      REFERENCES "VideoEpisodeMixVersion"(id,"videoEpisodeId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeAudioClip_scope_branch_check') THEN
    ALTER TABLE "VideoEpisodeAudioClip" ADD CONSTRAINT "VideoEpisodeAudioClip_scope_branch_check" CHECK (
      ("shotPlanVersionId" IS NOT NULL AND "videoEpisodeId" IS NULL
        AND "productionBaselineId" IS NULL AND "episodeShotId" IS NULL
        AND "episodeShotVersionId" IS NULL)
      OR
      ("shotPlanVersionId" IS NULL AND "videoEpisodeId" IS NOT NULL
        AND "productionBaselineId" IS NOT NULL
        AND (("episodeShotId" IS NULL AND "episodeShotVersionId" IS NULL)
          OR ("episodeShotId" IS NOT NULL AND "episodeShotVersionId" IS NOT NULL)))
    );
    ALTER TABLE "VideoEpisodeAudioClip" ADD CONSTRAINT "VideoEpisodeAudioClip_mix_new_scope_fkey"
      FOREIGN KEY ("mixVersionId","videoEpisodeId","productionBaselineId")
      REFERENCES "VideoEpisodeMixVersion"(id,"videoEpisodeId","productionBaselineId") ON DELETE RESTRICT;
    ALTER TABLE "VideoEpisodeAudioClip" ADD CONSTRAINT "VideoEpisodeAudioClip_baseline_input_fkey"
      FOREIGN KEY ("productionBaselineId","episodeShotVersionId","videoEpisodeId","episodeShotId")
      REFERENCES "VideoProductionBaselineShot"("baselineId","shotVersionId","episodeId","shotId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeSubtitleCue_scope_branch_check') THEN
    ALTER TABLE "VideoEpisodeSubtitleCue" ADD CONSTRAINT "VideoEpisodeSubtitleCue_scope_branch_check" CHECK (
      ("shotPlanVersionId" IS NOT NULL AND "videoEpisodeId" IS NULL
        AND "productionBaselineId" IS NULL AND "episodeShotId" IS NULL
        AND "episodeShotVersionId" IS NULL AND "scriptLineId" IS NULL)
      OR
      ("shotPlanVersionId" IS NULL AND "videoEpisodeId" IS NOT NULL
        AND "productionBaselineId" IS NOT NULL AND "episodeShotId" IS NOT NULL
        AND "episodeShotVersionId" IS NOT NULL AND "scriptLineId" IS NOT NULL)
    );
    ALTER TABLE "VideoEpisodeSubtitleCue" ADD CONSTRAINT "VideoEpisodeSubtitleCue_mix_new_scope_fkey"
      FOREIGN KEY ("mixVersionId","videoEpisodeId","productionBaselineId")
      REFERENCES "VideoEpisodeMixVersion"(id,"videoEpisodeId","productionBaselineId") ON DELETE RESTRICT;
    ALTER TABLE "VideoEpisodeSubtitleCue" ADD CONSTRAINT "VideoEpisodeSubtitleCue_baseline_input_fkey"
      FOREIGN KEY ("productionBaselineId","episodeShotVersionId","videoEpisodeId","episodeShotId")
      REFERENCES "VideoProductionBaselineShot"("baselineId","shotVersionId","episodeId","shotId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeExportTask_scope_branch_check') THEN
    ALTER TABLE "VideoEpisodeExportTask" ADD CONSTRAINT "VideoEpisodeExportTask_scope_branch_check" CHECK (
      ("adaptationId" IS NOT NULL AND "episodePlanVersionId" IS NOT NULL
        AND "shotPlanVersionId" IS NOT NULL AND "episodeNo" IS NOT NULL
        AND "videoEpisodeId" IS NULL AND "productionBaselineId" IS NULL)
      OR
      ("adaptationId" IS NULL AND "episodePlanVersionId" IS NULL
        AND "shotPlanVersionId" IS NULL AND "episodeNo" IS NULL
        AND "videoEpisodeId" IS NOT NULL AND "productionBaselineId" IS NOT NULL)
    );
    ALTER TABLE "VideoEpisodeExportTask" ADD CONSTRAINT "VideoEpisodeExportTask_id_video_episode_key"
      UNIQUE(id,"videoEpisodeId");
    ALTER TABLE "VideoEpisodeExportTask" ADD CONSTRAINT "VideoEpisodeExportTask_edit_new_scope_fkey"
      FOREIGN KEY ("editVersionId","videoEpisodeId","productionBaselineId")
      REFERENCES "VideoEpisodeEditVersion"(id,"videoEpisodeId","productionBaselineId") ON DELETE RESTRICT;
    ALTER TABLE "VideoEpisodeExportTask" ADD CONSTRAINT "VideoEpisodeExportTask_mix_new_scope_fkey"
      FOREIGN KEY ("mixVersionId","videoEpisodeId","productionBaselineId")
      REFERENCES "VideoEpisodeMixVersion"(id,"videoEpisodeId","productionBaselineId") ON DELETE RESTRICT;
    ALTER TABLE "VideoEpisodeExportTask" ADD CONSTRAINT "VideoEpisodeExportTask_retry_episode_fkey"
      FOREIGN KEY ("retryOfTaskId","videoEpisodeId")
      REFERENCES "VideoEpisodeExportTask"(id,"videoEpisodeId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeExport_scope_branch_check') THEN
    ALTER TABLE "VideoEpisodeExport" ADD CONSTRAINT "VideoEpisodeExport_scope_branch_check" CHECK (
      ("adaptationId" IS NOT NULL AND "episodePlanVersionId" IS NOT NULL
        AND "episodeNo" IS NOT NULL AND "videoEpisodeId" IS NULL
        AND "productionBaselineId" IS NULL)
      OR
      ("adaptationId" IS NULL AND "episodePlanVersionId" IS NULL
        AND "episodeNo" IS NULL AND "videoEpisodeId" IS NOT NULL
        AND "productionBaselineId" IS NOT NULL)
    );
    ALTER TABLE "VideoEpisodeExport" ADD CONSTRAINT "VideoEpisodeExport_task_new_scope_fkey"
      FOREIGN KEY ("taskId","videoEpisodeId")
      REFERENCES "VideoEpisodeExportTask"(id,"videoEpisodeId") ON DELETE RESTRICT;
    ALTER TABLE "VideoEpisodeExport" ADD CONSTRAINT "VideoEpisodeExport_edit_new_scope_fkey"
      FOREIGN KEY ("editVersionId","videoEpisodeId","productionBaselineId")
      REFERENCES "VideoEpisodeEditVersion"(id,"videoEpisodeId","productionBaselineId") ON DELETE RESTRICT;
    ALTER TABLE "VideoEpisodeExport" ADD CONSTRAINT "VideoEpisodeExport_mix_new_scope_fkey"
      FOREIGN KEY ("mixVersionId","videoEpisodeId","productionBaselineId")
      REFERENCES "VideoEpisodeMixVersion"(id,"videoEpisodeId","productionBaselineId") ON DELETE RESTRICT;
  END IF;
END
$post_branch_constraints$;

-- 最新交付是剧集聚合 head；复合身份禁止把其他剧集的成片挂到当前剧集。
DO $delivery_head_constraints$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoEpisodeExport_id_video_episode_key'
      AND conrelid = 'public."VideoEpisodeExport"'::regclass
  ) THEN
    ALTER TABLE "VideoEpisodeExport"
      ADD CONSTRAINT "VideoEpisodeExport_id_video_episode_key"
      UNIQUE(id,"videoEpisodeId");
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoEpisode_latest_delivery_fkey'
      AND conrelid = 'public."VideoEpisode"'::regclass
  ) THEN
    ALTER TABLE "VideoEpisode"
      ADD CONSTRAINT "VideoEpisode_latest_delivery_fkey"
      FOREIGN KEY ("latestDeliveryVersionId",id)
      REFERENCES "VideoEpisodeExport"(id,"videoEpisodeId") ON DELETE RESTRICT;
  END IF;
END
$delivery_head_constraints$;

CREATE TABLE IF NOT EXISTS "VideoProductionEditHead" (
  "episodeId" TEXT NOT NULL,
  "productionBaselineId" TEXT NOT NULL,
  "currentVersionId" TEXT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoProductionEditHead_pkey" PRIMARY KEY ("episodeId","productionBaselineId"),
  CONSTRAINT "VideoProductionEditHead_baseline_fkey"
    FOREIGN KEY ("productionBaselineId","episodeId")
    REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT,
  CONSTRAINT "VideoProductionEditHead_current_fkey"
    FOREIGN KEY ("currentVersionId","episodeId","productionBaselineId")
    REFERENCES "VideoEpisodeEditVersion"(id,"videoEpisodeId","productionBaselineId") ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS "VideoProductionMixHead" (
  "episodeId" TEXT NOT NULL,
  "productionBaselineId" TEXT NOT NULL,
  "currentVersionId" TEXT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoProductionMixHead_pkey" PRIMARY KEY ("episodeId","productionBaselineId"),
  CONSTRAINT "VideoProductionMixHead_baseline_fkey"
    FOREIGN KEY ("productionBaselineId","episodeId")
    REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT,
  CONSTRAINT "VideoProductionMixHead_current_fkey"
    FOREIGN KEY ("currentVersionId","episodeId","productionBaselineId")
    REFERENCES "VideoEpisodeMixVersion"(id,"videoEpisodeId","productionBaselineId") ON DELETE RESTRICT
);

DO $consumer_scope_constraints$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoShotPromptVersion_episode_scope_fkey') THEN
    ALTER TABLE "VideoShotPromptVersion" ADD CONSTRAINT "VideoShotPromptVersion_episode_scope_fkey"
      FOREIGN KEY ("episodeShotVersionId","episodeShotId","videoEpisodeId")
      REFERENCES "VideoShotVersion"(id,"shotId","episodeId") ON DELETE RESTRICT;
    ALTER TABLE "VideoShotPromptVersion" ADD CONSTRAINT "VideoShotPromptVersion_baseline_scope_fkey"
      FOREIGN KEY ("productionBaselineId","videoEpisodeId")
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoShotKeyframeVersion_episode_scope_fkey') THEN
    ALTER TABLE "VideoShotKeyframeVersion" ADD CONSTRAINT "VideoShotKeyframeVersion_episode_scope_fkey"
      FOREIGN KEY ("episodeShotVersionId","episodeShotId","videoEpisodeId")
      REFERENCES "VideoShotVersion"(id,"shotId","episodeId") ON DELETE RESTRICT;
    ALTER TABLE "VideoShotKeyframeVersion" ADD CONSTRAINT "VideoShotKeyframeVersion_baseline_scope_fkey"
      FOREIGN KEY ("productionBaselineId","videoEpisodeId")
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoShotRenderTask_episode_scope_fkey') THEN
    ALTER TABLE "VideoShotRenderTask" ADD CONSTRAINT "VideoShotRenderTask_episode_scope_fkey"
      FOREIGN KEY ("episodeShotVersionId","episodeShotId","videoEpisodeId")
      REFERENCES "VideoShotVersion"(id,"shotId","episodeId") ON DELETE RESTRICT;
    ALTER TABLE "VideoShotRenderTask" ADD CONSTRAINT "VideoShotRenderTask_baseline_scope_fkey"
      FOREIGN KEY ("productionBaselineId","videoEpisodeId")
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoShotTake_episode_scope_fkey') THEN
    ALTER TABLE "VideoShotTake" ADD CONSTRAINT "VideoShotTake_episode_scope_fkey"
      FOREIGN KEY ("episodeShotVersionId","episodeShotId","videoEpisodeId")
      REFERENCES "VideoShotVersion"(id,"shotId","episodeId") ON DELETE RESTRICT;
    ALTER TABLE "VideoShotTake" ADD CONSTRAINT "VideoShotTake_baseline_scope_fkey"
      FOREIGN KEY ("productionBaselineId","videoEpisodeId")
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
    ALTER TABLE "VideoShotTake" ADD CONSTRAINT "VideoShotTake_id_episode_project_key"
      UNIQUE(id,"videoEpisodeId","projectId");
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoShotTake_last_frame_asset_fkey') THEN
    ALTER TABLE "VideoShotTake" ADD CONSTRAINT "VideoShotTake_last_frame_asset_fkey"
      FOREIGN KEY ("lastFrameAssetId","projectId")
      REFERENCES "VideoAsset"(id,"projectId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoTakeAdoption_source_scope_fkey') THEN
    ALTER TABLE "VideoTakeAdoption" ADD CONSTRAINT "VideoTakeAdoption_source_scope_fkey"
      FOREIGN KEY ("sourceTakeId","episodeId","projectId")
      REFERENCES "VideoShotTake"(id,"videoEpisodeId","projectId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoTakeFrameExtraction_episode_scope_fkey') THEN
    ALTER TABLE "VideoTakeFrameExtraction" ADD CONSTRAINT "VideoTakeFrameExtraction_episode_scope_fkey"
      FOREIGN KEY ("episodeShotVersionId","episodeShotId","videoEpisodeId")
      REFERENCES "VideoShotVersion"(id,"shotId","episodeId") ON DELETE RESTRICT;
    ALTER TABLE "VideoTakeFrameExtraction" ADD CONSTRAINT "VideoTakeFrameExtraction_baseline_scope_fkey"
      FOREIGN KEY ("productionBaselineId","videoEpisodeId")
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeEditVersion_baseline_scope_fkey') THEN
    ALTER TABLE "VideoEpisodeEditVersion" ADD CONSTRAINT "VideoEpisodeEditVersion_baseline_scope_fkey"
      FOREIGN KEY ("productionBaselineId","videoEpisodeId")
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeEditClip_episode_scope_fkey') THEN
    ALTER TABLE "VideoEpisodeEditClip" ADD CONSTRAINT "VideoEpisodeEditClip_episode_scope_fkey"
      FOREIGN KEY ("episodeShotVersionId","episodeShotId","videoEpisodeId")
      REFERENCES "VideoShotVersion"(id,"shotId","episodeId") ON DELETE RESTRICT;
    ALTER TABLE "VideoEpisodeEditClip" ADD CONSTRAINT "VideoEpisodeEditClip_baseline_scope_fkey"
      FOREIGN KEY ("productionBaselineId","videoEpisodeId")
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
    ALTER TABLE "VideoEpisodeEditClip" ADD CONSTRAINT "VideoEpisodeEditClip_adoption_scope_fkey"
      FOREIGN KEY ("adoptionId","videoEpisodeId","episodeShotId","episodeShotVersionId")
      REFERENCES "VideoTakeAdoption"(id,"episodeId","targetShotId","targetShotVersionId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeMixVersion_baseline_scope_fkey') THEN
    ALTER TABLE "VideoEpisodeMixVersion" ADD CONSTRAINT "VideoEpisodeMixVersion_baseline_scope_fkey"
      FOREIGN KEY ("productionBaselineId","videoEpisodeId")
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeAudioClip_episode_scope_fkey') THEN
    ALTER TABLE "VideoEpisodeAudioClip" ADD CONSTRAINT "VideoEpisodeAudioClip_episode_scope_fkey"
      FOREIGN KEY ("episodeShotVersionId","episodeShotId","videoEpisodeId")
      REFERENCES "VideoShotVersion"(id,"shotId","episodeId") ON DELETE RESTRICT;
    ALTER TABLE "VideoEpisodeAudioClip" ADD CONSTRAINT "VideoEpisodeAudioClip_baseline_scope_fkey"
      FOREIGN KEY ("productionBaselineId","videoEpisodeId")
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeSubtitleCue_episode_scope_fkey') THEN
    ALTER TABLE "VideoEpisodeSubtitleCue" ADD CONSTRAINT "VideoEpisodeSubtitleCue_episode_scope_fkey"
      FOREIGN KEY ("episodeShotVersionId","episodeShotId","videoEpisodeId")
      REFERENCES "VideoShotVersion"(id,"shotId","episodeId") ON DELETE RESTRICT;
    ALTER TABLE "VideoEpisodeSubtitleCue" ADD CONSTRAINT "VideoEpisodeSubtitleCue_baseline_scope_fkey"
      FOREIGN KEY ("productionBaselineId","videoEpisodeId")
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeExportTask_baseline_scope_fkey') THEN
    ALTER TABLE "VideoEpisodeExportTask" ADD CONSTRAINT "VideoEpisodeExportTask_baseline_scope_fkey"
      FOREIGN KEY ("productionBaselineId","videoEpisodeId")
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeExport_baseline_scope_fkey') THEN
    ALTER TABLE "VideoEpisodeExport" ADD CONSTRAINT "VideoEpisodeExport_baseline_scope_fkey"
      FOREIGN KEY ("productionBaselineId","videoEpisodeId")
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
  END IF;
END
$consumer_scope_constraints$;

CREATE INDEX IF NOT EXISTS "VideoShotPromptVersion_episode_version_idx"
ON "VideoShotPromptVersion"("videoEpisodeId","episodeShotVersionId");
CREATE INDEX IF NOT EXISTS "VideoShotKeyframeVersion_episode_version_idx"
ON "VideoShotKeyframeVersion"("videoEpisodeId","episodeShotVersionId");
CREATE INDEX IF NOT EXISTS "VideoShotRenderTask_episode_baseline_idx"
ON "VideoShotRenderTask"("videoEpisodeId","productionBaselineId","createdAt");
CREATE INDEX IF NOT EXISTS "VideoShotTake_episode_baseline_idx"
ON "VideoShotTake"("videoEpisodeId","productionBaselineId","createdAt");
CREATE INDEX IF NOT EXISTS "VideoEpisodeEditVersion_new_episode_idx"
ON "VideoEpisodeEditVersion"("videoEpisodeId","productionBaselineId","versionNo");
CREATE INDEX IF NOT EXISTS "VideoEpisodeMixVersion_new_episode_idx"
ON "VideoEpisodeMixVersion"("videoEpisodeId","productionBaselineId","versionNo");
CREATE INDEX IF NOT EXISTS "VideoEpisodeExportTask_new_episode_idx"
ON "VideoEpisodeExportTask"("videoEpisodeId","productionBaselineId","createdAt");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotPromptVersion_new_shot_version_key"
ON "VideoShotPromptVersion"("episodeShotId","versionNo")
WHERE "videoEpisodeId" IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotKeyframeVersion_new_shot_role_version_key"
ON "VideoShotKeyframeVersion"("episodeShotId",role,"versionNo")
WHERE "videoEpisodeId" IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotRenderTask_new_shot_client_request_key"
ON "VideoShotRenderTask"("episodeShotId","clientRequestId")
WHERE "videoEpisodeId" IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotRenderTask_new_active_shot_key"
ON "VideoShotRenderTask"("videoEpisodeId","episodeShotId")
WHERE "videoEpisodeId" IS NOT NULL
  AND status IN ('pending','submitting','queued','running','archiving');
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotTake_new_shot_take_no_key"
ON "VideoShotTake"("episodeShotId","takeNo")
WHERE "videoEpisodeId" IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeEditVersion_new_episode_version_key"
ON "VideoEpisodeEditVersion"("videoEpisodeId","versionNo")
WHERE "videoEpisodeId" IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeMixVersion_new_episode_version_key"
ON "VideoEpisodeMixVersion"("videoEpisodeId","versionNo")
WHERE "videoEpisodeId" IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeExportTask_new_active_episode_key"
ON "VideoEpisodeExportTask"("videoEpisodeId")
WHERE "videoEpisodeId" IS NOT NULL AND status IN ('pending','rendering');
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeExport_new_episode_version_key"
ON "VideoEpisodeExport"("videoEpisodeId","versionNo")
WHERE "videoEpisodeId" IS NOT NULL;

INSERT INTO "VideoStoryboardDraft"(
  "episodeId",revision,"basedOnStoryboardVersionId","scriptVersionId","documentJson","contentHash","updatedAt"
)
SELECT
  e.id,
  1,
  NULL,
  e."currentScriptVersionId",
  '{"schemaVersion":"video-episode-storyboard/1.0","shots":[]}',
  'cfbdce6be5c120100e0183e213dca1d830bf93261debc289583312a66887bd3b',
  e."updatedAt"
FROM "VideoEpisode" e
ON CONFLICT ("episodeId") DO NOTHING;

DROP INDEX IF EXISTS "ReviewArtifact_videoEpisodeId_status_idx";
CREATE INDEX "ReviewArtifact_videoEpisodeId_status_idx"
ON "ReviewArtifact"("videoEpisodeId",status);

DO $constraints$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ReviewArtifact_video_episode_target_check'
      AND conrelid = 'public."ReviewArtifact"'::regclass
  ) THEN
    ALTER TABLE "ReviewArtifact" DROP CONSTRAINT "ReviewArtifact_video_episode_target_check";
  END IF;
  ALTER TABLE "ReviewArtifact" ADD CONSTRAINT "ReviewArtifact_video_episode_target_check" CHECK (
    ("videoEpisodeId" IS NULL AND kind::text NOT IN ('video_episode_script','video_episode_storyboard')) OR
    ("videoEpisodeId" IS NOT NULL AND kind::text IN ('video_episode_script','video_episode_storyboard')
      AND "chapterId" IS NULL AND "taskId" IS NULL AND "videoSceneId" IS NULL
      AND "videoAdaptationId" IS NULL AND "videoAdaptationTaskId" IS NULL)
  );

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisode_current_storyboard_fkey') THEN
    ALTER TABLE "VideoEpisode" ADD CONSTRAINT "VideoEpisode_current_storyboard_fkey"
      FOREIGN KEY ("currentStoryboardVersionId",id)
      REFERENCES "VideoStoryboardVersion"(id,"episodeId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisode_current_baseline_fkey') THEN
    ALTER TABLE "VideoEpisode" ADD CONSTRAINT "VideoEpisode_current_baseline_fkey"
      FOREIGN KEY ("currentProductionBaselineId",id)
      REFERENCES "VideoProductionBaseline"(id,"episodeId") ON DELETE RESTRICT;
  END IF;
END
$constraints$;

-- 新表与既有应用表使用同一所有者，避免隔离验证因迁移执行角色不同而掩盖权限问题。
DO $ownership$
DECLARE owner_name TEXT; table_name TEXT;
BEGIN
  SELECT pg_get_userbyid(relowner) INTO owner_name FROM pg_class WHERE oid='public."User"'::regclass;
  FOREACH table_name IN ARRAY ARRAY[
    'VideoEpisodeShot','VideoShotLineage','VideoStoryboardVersion','VideoShotVersion',
    'VideoStoryboardDraft','VideoProductionBaseline','VideoTakeAdoption',
    'VideoProductionBaselineShot','VideoProductionEditHead','VideoProductionMixHead'
  ] LOOP
    EXECUTE format('ALTER TABLE public.%I OWNER TO %I',table_name,owner_name);
  END LOOP;
END
$ownership$;

COMMENT ON TABLE "VideoEpisodeShot" IS '独立分集中不随标题、镜号或顺序变化的稳定镜头身份';
COMMENT ON TABLE "VideoShotLineage" IS '替换、复制、拆分和合并产生新镜头身份时冻结的多源沿袭关系';
COMMENT ON TABLE "VideoShotVersion" IS '一次正式分镜中某稳定镜头的不可变内容版本';
COMMENT ON TABLE "VideoStoryboardDraft" IS '分镜自动保存工作稿，CAS 更新且不等同正式版本';
COMMENT ON TABLE "VideoStoryboardVersion" IS '作者确认后的不可变整集分镜版本';
COMMENT ON TABLE "VideoProductionBaseline" IS '作者确认的整集不可变制作输入版本';
COMMENT ON TABLE "VideoTakeAdoption" IS '原始 Take 到目标镜头版本的人工采用事实，不修改原生成依据';
COMMENT ON TABLE "VideoProductionBaselineShot" IS '制作基线逐镜冻结的确切镜头版本及输入快照';
COMMENT ON TABLE "VideoProductionEditHead" IS '独立剧集粗剪当前版本的 CAS head';
COMMENT ON TABLE "VideoProductionMixHead" IS '独立剧集声音字幕当前版本的 CAS head';

COMMIT;
