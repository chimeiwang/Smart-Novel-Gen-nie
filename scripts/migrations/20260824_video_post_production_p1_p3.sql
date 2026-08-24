BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 本迁移只获得服务器端 novelwriterdev 开发库授权；生产库和其他数据库必须主动拒绝。
DO $safety$
BEGIN
  IF current_database() <> 'novelwriterdev' THEN
    RAISE EXCEPTION '视频后期制作 P1-P3 迁移只允许在 novelwriterdev 执行，当前数据库为 %', current_database();
  END IF;
END
$safety$;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260824:video-post-production-p1-p3'));

-- P3 需要区分可独立替换的音效与最终整集成片，不能把它们冒充 ambience/motion。
ALTER TABLE "VideoAsset" DROP CONSTRAINT IF EXISTS "VideoAsset_duty_check";
ALTER TABLE "VideoAsset" ADD CONSTRAINT "VideoAsset_duty_check" CHECK (
  "duty" IN (
    'identity', 'costume', 'scene', 'prop', 'style', 'storyboard', 'keyframe',
    'motion', 'camera', 'voice', 'ambience', 'sfx', 'music', 'episode_export'
  )
);

CREATE TABLE IF NOT EXISTS "VideoTakeFrameExtraction" (
  "assetId" TEXT NOT NULL,
  "takeId" TEXT NOT NULL,
  "shotId" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "timestampMs" INTEGER NOT NULL,
  "clientRequestId" TEXT NOT NULL,
  "requestHash" TEXT NOT NULL,
  "requestedByUserId" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoTakeFrameExtraction_pkey" PRIMARY KEY ("assetId"),
  CONSTRAINT "VideoTakeFrameExtraction_asset_take_time_key"
    UNIQUE ("assetId", "takeId", "timestampMs"),
  CONSTRAINT "VideoTakeFrameExtraction_asset_project_fkey"
    FOREIGN KEY ("assetId", "projectId") REFERENCES "VideoAsset"("id", "projectId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoTakeFrameExtraction_take_scope_fkey"
    FOREIGN KEY ("takeId", "shotId", "adaptationId")
    REFERENCES "VideoShotTake"("id", "shotId", "adaptationId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoTakeFrameExtraction_adaptation_project_fkey"
    FOREIGN KEY ("adaptationId", "projectId")
    REFERENCES "VideoChapterAdaptation"("id", "projectId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoTakeFrameExtraction_adaptation_novel_fkey"
    FOREIGN KEY ("adaptationId", "novelId")
    REFERENCES "VideoChapterAdaptation"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoTakeFrameExtraction_novel_owner_fkey"
    FOREIGN KEY ("novelId", "requestedByUserId") REFERENCES "Novel"("id", "userId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoTakeFrameExtraction_user_fkey"
    FOREIGN KEY ("requestedByUserId") REFERENCES "User"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoTakeFrameExtraction_time_check" CHECK ("timestampMs" >= 0),
  CONSTRAINT "VideoTakeFrameExtraction_request_check" CHECK (btrim("clientRequestId") <> ''),
  CONSTRAINT "VideoTakeFrameExtraction_hash_check" CHECK ("requestHash" ~ '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoTakeFrameExtraction_asset_take_time_key"
ON "VideoTakeFrameExtraction"("assetId", "takeId", "timestampMs");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoTakeFrameExtraction_user_request_key"
ON "VideoTakeFrameExtraction"("requestedByUserId", "clientRequestId");
CREATE INDEX IF NOT EXISTS "VideoTakeFrameExtraction_take_created_idx"
ON "VideoTakeFrameExtraction"("takeId", "createdAt");

CREATE TABLE IF NOT EXISTS "VideoShotKeyframeVersion" (
  "id" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "shotId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "role" TEXT NOT NULL,
  "versionNo" INTEGER NOT NULL,
  "basedOnVersionId" TEXT,
  "assetId" TEXT,
  "sourceKind" TEXT NOT NULL,
  "sourceTakeId" TEXT,
  "sourceTimeMs" INTEGER,
  "clientRequestId" TEXT NOT NULL,
  "requestHash" TEXT NOT NULL,
  "contentHash" TEXT NOT NULL,
  "createdByUserId" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoShotKeyframeVersion_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoShotKeyframeVersion_id_shot_role_key"
    UNIQUE ("id", "shotId", "role"),
  CONSTRAINT "VideoShotKeyframeVersion_adaptation_project_fkey"
    FOREIGN KEY ("adaptationId", "projectId")
    REFERENCES "VideoChapterAdaptation"("id", "projectId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotKeyframeVersion_adaptation_novel_fkey"
    FOREIGN KEY ("adaptationId", "novelId")
    REFERENCES "VideoChapterAdaptation"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotKeyframeVersion_project_novel_fkey"
    FOREIGN KEY ("projectId", "novelId") REFERENCES "VideoProject"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotKeyframeVersion_plan_adaptation_fkey"
    FOREIGN KEY ("shotPlanVersionId", "adaptationId")
    REFERENCES "VideoShotPlanVersion"("id", "adaptationId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotKeyframeVersion_shot_plan_fkey"
    FOREIGN KEY ("shotId", "shotPlanVersionId") REFERENCES "VideoShot"("id", "planVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotKeyframeVersion_asset_project_fkey"
    FOREIGN KEY ("assetId", "projectId") REFERENCES "VideoAsset"("id", "projectId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotKeyframeVersion_source_take_fkey"
    FOREIGN KEY ("sourceTakeId", "shotId", "adaptationId")
    REFERENCES "VideoShotTake"("id", "shotId", "adaptationId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotKeyframeVersion_extraction_fkey"
    FOREIGN KEY ("assetId", "sourceTakeId", "sourceTimeMs")
    REFERENCES "VideoTakeFrameExtraction"("assetId", "takeId", "timestampMs")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotKeyframeVersion_based_on_fkey"
    FOREIGN KEY ("basedOnVersionId", "shotId", "role")
    REFERENCES "VideoShotKeyframeVersion"("id", "shotId", "role")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotKeyframeVersion_user_fkey"
    FOREIGN KEY ("createdByUserId") REFERENCES "User"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotKeyframeVersion_role_check"
    CHECK ("role" IN ('initial_state', 'transition_anchor', 'end_state')),
  CONSTRAINT "VideoShotKeyframeVersion_source_kind_check"
    CHECK ("sourceKind" IN ('asset', 'take_frame', 'cleared')),
  CONSTRAINT "VideoShotKeyframeVersion_version_check" CHECK ("versionNo" > 0),
  CONSTRAINT "VideoShotKeyframeVersion_hash_check" CHECK (
    "requestHash" ~ '^[0-9a-f]{64}$' AND "contentHash" ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT "VideoShotKeyframeVersion_request_check" CHECK (btrim("clientRequestId") <> ''),
  CONSTRAINT "VideoShotKeyframeVersion_source_check" CHECK (
    ("sourceKind" = 'cleared' AND "assetId" IS NULL AND "sourceTakeId" IS NULL AND "sourceTimeMs" IS NULL)
    OR ("sourceKind" = 'asset' AND "assetId" IS NOT NULL AND "sourceTakeId" IS NULL AND "sourceTimeMs" IS NULL)
    OR ("sourceKind" = 'take_frame' AND "assetId" IS NOT NULL AND "sourceTakeId" IS NOT NULL AND "sourceTimeMs" >= 0)
  )
);

-- 开发实施期间曾先落下无抽帧来源表的事务版本；最终脚本重放时必须补齐复合外键，
-- 不能因为 CREATE TABLE IF NOT EXISTS 而留下弱结构。
DO $keyframe_extraction_fk$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoShotKeyframeVersion_extraction_fkey'
      AND conrelid = '"VideoShotKeyframeVersion"'::regclass
  ) THEN
    ALTER TABLE "VideoShotKeyframeVersion"
      ADD CONSTRAINT "VideoShotKeyframeVersion_extraction_fkey"
      FOREIGN KEY ("assetId", "sourceTakeId", "sourceTimeMs")
      REFERENCES "VideoTakeFrameExtraction"("assetId", "takeId", "timestampMs")
      ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END
$keyframe_extraction_fk$;

CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotKeyframeVersion_id_shot_role_key"
ON "VideoShotKeyframeVersion"("id", "shotId", "role");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotKeyframeVersion_shot_role_version_key"
ON "VideoShotKeyframeVersion"("shotId", "role", "versionNo");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotKeyframeVersion_user_request_key"
ON "VideoShotKeyframeVersion"("createdByUserId", "clientRequestId");
CREATE INDEX IF NOT EXISTS "VideoShotKeyframeVersion_shot_created_idx"
ON "VideoShotKeyframeVersion"("shotId", "createdAt");

CREATE TABLE IF NOT EXISTS "VideoShotKeyframeHead" (
  "shotId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "role" TEXT NOT NULL,
  "currentVersionId" TEXT,
  "revision" INTEGER NOT NULL DEFAULT 1,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoShotKeyframeHead_pkey" PRIMARY KEY ("shotId", "role"),
  CONSTRAINT "VideoShotKeyframeHead_shot_plan_fkey"
    FOREIGN KEY ("shotId", "shotPlanVersionId") REFERENCES "VideoShot"("id", "planVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotKeyframeHead_current_version_fkey"
    FOREIGN KEY ("currentVersionId", "shotId", "role")
    REFERENCES "VideoShotKeyframeVersion"("id", "shotId", "role")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotKeyframeHead_role_check"
    CHECK ("role" IN ('initial_state', 'transition_anchor', 'end_state')),
  CONSTRAINT "VideoShotKeyframeHead_revision_check" CHECK ("revision" > 0)
);

CREATE TABLE IF NOT EXISTS "VideoEpisodeEditVersion" (
  "id" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "episodePlanVersionId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "episodeNo" INTEGER NOT NULL,
  "versionNo" INTEGER NOT NULL,
  "basedOnVersionId" TEXT,
  "totalDurationMs" INTEGER NOT NULL,
  "clientRequestId" TEXT NOT NULL,
  "requestHash" TEXT NOT NULL,
  "contentHash" TEXT NOT NULL,
  "createdByUserId" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoEpisodeEditVersion_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoEpisodeEditVersion_id_episode_key"
    UNIQUE ("id", "episodePlanVersionId", "episodeNo"),
  CONSTRAINT "VideoEpisodeEditVersion_adaptation_project_fkey"
    FOREIGN KEY ("adaptationId", "projectId")
    REFERENCES "VideoChapterAdaptation"("id", "projectId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeEditVersion_adaptation_novel_fkey"
    FOREIGN KEY ("adaptationId", "novelId")
    REFERENCES "VideoChapterAdaptation"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeEditVersion_project_novel_fkey"
    FOREIGN KEY ("projectId", "novelId") REFERENCES "VideoProject"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeEditVersion_episode_plan_fkey"
    FOREIGN KEY ("episodePlanVersionId", "shotPlanVersionId", "adaptationId")
    REFERENCES "VideoEpisodePlanVersion"("id", "shotPlanVersionId", "adaptationId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeEditVersion_based_on_fkey"
    FOREIGN KEY ("basedOnVersionId", "episodePlanVersionId", "episodeNo")
    REFERENCES "VideoEpisodeEditVersion"("id", "episodePlanVersionId", "episodeNo")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeEditVersion_user_fkey"
    FOREIGN KEY ("createdByUserId") REFERENCES "User"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeEditVersion_numbers_check"
    CHECK ("episodeNo" > 0 AND "versionNo" > 0 AND "totalDurationMs" > 0),
  CONSTRAINT "VideoEpisodeEditVersion_hash_check" CHECK (
    "requestHash" ~ '^[0-9a-f]{64}$' AND "contentHash" ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT "VideoEpisodeEditVersion_request_check" CHECK (btrim("clientRequestId") <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeEditVersion_id_episode_key"
ON "VideoEpisodeEditVersion"("id", "episodePlanVersionId", "episodeNo");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeEditVersion_id_plan_key"
ON "VideoEpisodeEditVersion"("id", "shotPlanVersionId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeEditVersion_episode_version_key"
ON "VideoEpisodeEditVersion"("episodePlanVersionId", "episodeNo", "versionNo");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeEditVersion_user_request_key"
ON "VideoEpisodeEditVersion"("createdByUserId", "clientRequestId");

CREATE TABLE IF NOT EXISTS "VideoEpisodeEditClip" (
  "editVersionId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "shotId" TEXT NOT NULL,
  "takeId" TEXT,
  "ordinal" INTEGER NOT NULL,
  "sourceInMs" INTEGER,
  "sourceOutMs" INTEGER,
  "timelineStartMs" INTEGER NOT NULL,
  "outputDurationMs" INTEGER NOT NULL,
  "transitionAfter" TEXT NOT NULL DEFAULT 'cut'::text,
  "transitionDurationMs" INTEGER NOT NULL DEFAULT 0,
  CONSTRAINT "VideoEpisodeEditClip_pkey" PRIMARY KEY ("editVersionId", "ordinal"),
  CONSTRAINT "VideoEpisodeEditClip_edit_plan_fkey"
    FOREIGN KEY ("editVersionId", "shotPlanVersionId")
    REFERENCES "VideoEpisodeEditVersion"("id", "shotPlanVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeEditClip_shot_plan_fkey"
    FOREIGN KEY ("shotId", "shotPlanVersionId") REFERENCES "VideoShot"("id", "planVersionId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeEditClip_take_scope_fkey"
    FOREIGN KEY ("takeId", "shotId", "shotPlanVersionId")
    REFERENCES "VideoShotTake"("id", "shotId", "shotPlanVersionId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeEditClip_ordinal_check" CHECK ("ordinal" > 0),
  CONSTRAINT "VideoEpisodeEditClip_timeline_check" CHECK (
    "timelineStartMs" >= 0 AND "outputDurationMs" >= 500
  ),
  CONSTRAINT "VideoEpisodeEditClip_transition_check" CHECK (
    ("transitionAfter" = 'cut' AND "transitionDurationMs" = 0)
    OR (
      "transitionAfter" = 'fade_black'
      AND "transitionDurationMs" > 0
      AND "transitionDurationMs" * 2 <= "outputDurationMs"
    )
  ),
  CONSTRAINT "VideoEpisodeEditClip_source_check" CHECK (
    ("takeId" IS NULL AND "sourceInMs" IS NULL AND "sourceOutMs" IS NULL)
    OR (
      "takeId" IS NOT NULL AND "sourceInMs" >= 0
      AND "sourceOutMs" > "sourceInMs"
      AND "outputDurationMs" = "sourceOutMs" - "sourceInMs"
    )
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeEditClip_version_shot_key"
ON "VideoEpisodeEditClip"("editVersionId", "shotId");

CREATE TABLE IF NOT EXISTS "VideoEpisodeEditHead" (
  "episodePlanVersionId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "episodeNo" INTEGER NOT NULL,
  "currentVersionId" TEXT,
  "revision" INTEGER NOT NULL DEFAULT 1,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoEpisodeEditHead_pkey" PRIMARY KEY ("episodePlanVersionId", "episodeNo"),
  CONSTRAINT "VideoEpisodeEditHead_episode_plan_fkey"
    FOREIGN KEY ("episodePlanVersionId", "shotPlanVersionId", "adaptationId")
    REFERENCES "VideoEpisodePlanVersion"("id", "shotPlanVersionId", "adaptationId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeEditHead_current_version_fkey"
    FOREIGN KEY ("currentVersionId", "episodePlanVersionId", "episodeNo")
    REFERENCES "VideoEpisodeEditVersion"("id", "episodePlanVersionId", "episodeNo")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeEditHead_numbers_check" CHECK ("episodeNo" > 0 AND "revision" > 0)
);

CREATE TABLE IF NOT EXISTS "VideoEpisodeMixVersion" (
  "id" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "episodePlanVersionId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "episodeNo" INTEGER NOT NULL,
  "editVersionId" TEXT NOT NULL,
  "versionNo" INTEGER NOT NULL,
  "basedOnVersionId" TEXT,
  "clientRequestId" TEXT NOT NULL,
  "requestHash" TEXT NOT NULL,
  "contentHash" TEXT NOT NULL,
  "createdByUserId" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoEpisodeMixVersion_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoEpisodeMixVersion_id_episode_key"
    UNIQUE ("id", "episodePlanVersionId", "episodeNo"),
  CONSTRAINT "VideoEpisodeMixVersion_adaptation_project_fkey"
    FOREIGN KEY ("adaptationId", "projectId")
    REFERENCES "VideoChapterAdaptation"("id", "projectId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeMixVersion_adaptation_novel_fkey"
    FOREIGN KEY ("adaptationId", "novelId")
    REFERENCES "VideoChapterAdaptation"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeMixVersion_project_novel_fkey"
    FOREIGN KEY ("projectId", "novelId") REFERENCES "VideoProject"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeMixVersion_episode_plan_fkey"
    FOREIGN KEY ("episodePlanVersionId", "shotPlanVersionId", "adaptationId")
    REFERENCES "VideoEpisodePlanVersion"("id", "shotPlanVersionId", "adaptationId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeMixVersion_edit_version_fkey"
    FOREIGN KEY ("editVersionId", "episodePlanVersionId", "episodeNo")
    REFERENCES "VideoEpisodeEditVersion"("id", "episodePlanVersionId", "episodeNo")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeMixVersion_based_on_fkey"
    FOREIGN KEY ("basedOnVersionId", "episodePlanVersionId", "episodeNo")
    REFERENCES "VideoEpisodeMixVersion"("id", "episodePlanVersionId", "episodeNo")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeMixVersion_user_fkey"
    FOREIGN KEY ("createdByUserId") REFERENCES "User"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeMixVersion_numbers_check" CHECK ("episodeNo" > 0 AND "versionNo" > 0),
  CONSTRAINT "VideoEpisodeMixVersion_hash_check" CHECK (
    "requestHash" ~ '^[0-9a-f]{64}$' AND "contentHash" ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT "VideoEpisodeMixVersion_request_check" CHECK (btrim("clientRequestId") <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeMixVersion_id_episode_key"
ON "VideoEpisodeMixVersion"("id", "episodePlanVersionId", "episodeNo");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeMixVersion_id_project_key"
ON "VideoEpisodeMixVersion"("id", "projectId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeMixVersion_id_project_plan_key"
ON "VideoEpisodeMixVersion"("id", "projectId", "shotPlanVersionId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeMixVersion_id_plan_key"
ON "VideoEpisodeMixVersion"("id", "shotPlanVersionId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeMixVersion_episode_version_key"
ON "VideoEpisodeMixVersion"("episodePlanVersionId", "episodeNo", "versionNo");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeMixVersion_user_request_key"
ON "VideoEpisodeMixVersion"("createdByUserId", "clientRequestId");

CREATE TABLE IF NOT EXISTS "VideoEpisodeAudioClip" (
  "mixVersionId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "ordinal" INTEGER NOT NULL,
  "trackKind" TEXT NOT NULL,
  "assetId" TEXT NOT NULL,
  "shotId" TEXT,
  "timelineStartMs" INTEGER NOT NULL,
  "sourceInMs" INTEGER NOT NULL,
  "sourceOutMs" INTEGER NOT NULL,
  "gainMillibels" INTEGER NOT NULL DEFAULT 0,
  "fadeInMs" INTEGER NOT NULL DEFAULT 0,
  "fadeOutMs" INTEGER NOT NULL DEFAULT 0,
  CONSTRAINT "VideoEpisodeAudioClip_pkey" PRIMARY KEY ("mixVersionId", "ordinal"),
  CONSTRAINT "VideoEpisodeAudioClip_mix_project_fkey"
    FOREIGN KEY ("mixVersionId", "projectId", "shotPlanVersionId")
    REFERENCES "VideoEpisodeMixVersion"("id", "projectId", "shotPlanVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeAudioClip_asset_project_fkey"
    FOREIGN KEY ("assetId", "projectId") REFERENCES "VideoAsset"("id", "projectId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeAudioClip_shot_plan_fkey"
    FOREIGN KEY ("shotId", "shotPlanVersionId") REFERENCES "VideoShot"("id", "planVersionId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeAudioClip_track_check"
    CHECK ("trackKind" IN ('dialogue', 'narration', 'ambience', 'sfx', 'music')),
  CONSTRAINT "VideoEpisodeAudioClip_range_check" CHECK (
    "ordinal" > 0 AND "timelineStartMs" >= 0 AND "sourceInMs" >= 0
    AND "sourceOutMs" > "sourceInMs"
  ),
  CONSTRAINT "VideoEpisodeAudioClip_gain_check"
    CHECK ("gainMillibels" BETWEEN -6000 AND 1200),
  CONSTRAINT "VideoEpisodeAudioClip_fade_check" CHECK (
    "fadeInMs" >= 0 AND "fadeOutMs" >= 0
    AND "fadeInMs" + "fadeOutMs" <= "sourceOutMs" - "sourceInMs"
  )
);

CREATE TABLE IF NOT EXISTS "VideoEpisodeSubtitleCue" (
  "mixVersionId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "ordinal" INTEGER NOT NULL,
  "shotId" TEXT,
  "startMs" INTEGER NOT NULL,
  "endMs" INTEGER NOT NULL,
  "speaker" TEXT,
  "text" TEXT NOT NULL,
  CONSTRAINT "VideoEpisodeSubtitleCue_pkey" PRIMARY KEY ("mixVersionId", "ordinal"),
  CONSTRAINT "VideoEpisodeSubtitleCue_mix_plan_fkey"
    FOREIGN KEY ("mixVersionId", "shotPlanVersionId")
    REFERENCES "VideoEpisodeMixVersion"("id", "shotPlanVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeSubtitleCue_shot_plan_fkey"
    FOREIGN KEY ("shotId", "shotPlanVersionId") REFERENCES "VideoShot"("id", "planVersionId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeSubtitleCue_range_check"
    CHECK ("ordinal" > 0 AND "startMs" >= 0 AND "endMs" > "startMs"),
  CONSTRAINT "VideoEpisodeSubtitleCue_text_check"
    CHECK (btrim("text") <> '' AND ("speaker" IS NULL OR char_length("speaker") <= 120))
);

CREATE TABLE IF NOT EXISTS "VideoEpisodeMixHead" (
  "episodePlanVersionId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "episodeNo" INTEGER NOT NULL,
  "currentVersionId" TEXT,
  "revision" INTEGER NOT NULL DEFAULT 1,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoEpisodeMixHead_pkey" PRIMARY KEY ("episodePlanVersionId", "episodeNo"),
  CONSTRAINT "VideoEpisodeMixHead_episode_plan_fkey"
    FOREIGN KEY ("episodePlanVersionId", "shotPlanVersionId", "adaptationId")
    REFERENCES "VideoEpisodePlanVersion"("id", "shotPlanVersionId", "adaptationId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeMixHead_current_version_fkey"
    FOREIGN KEY ("currentVersionId", "episodePlanVersionId", "episodeNo")
    REFERENCES "VideoEpisodeMixVersion"("id", "episodePlanVersionId", "episodeNo")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeMixHead_numbers_check" CHECK ("episodeNo" > 0 AND "revision" > 0)
);

CREATE TABLE IF NOT EXISTS "VideoEpisodeExportTask" (
  "id" TEXT NOT NULL,
  "requestedByUserId" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "episodePlanVersionId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "episodeNo" INTEGER NOT NULL,
  "editVersionId" TEXT NOT NULL,
  "mixVersionId" TEXT NOT NULL,
  "retryOfTaskId" TEXT,
  "clientRequestId" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'pending'::text,
  "inputHash" TEXT NOT NULL,
  "requestManifestJson" TEXT NOT NULL,
  "resolution" TEXT NOT NULL,
  "framesPerSecond" INTEGER NOT NULL,
  "burnSubtitles" BOOLEAN NOT NULL DEFAULT true,
  "attemptCount" INTEGER NOT NULL DEFAULT 0,
  "nextAttemptAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "lastErrorCode" TEXT,
  "lastErrorMessage" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  "startedAt" TIMESTAMP(3),
  "completedAt" TIMESTAMP(3),
  CONSTRAINT "VideoEpisodeExportTask_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoEpisodeExportTask_id_scope_key"
    UNIQUE ("id", "adaptationId", "episodeNo"),
  CONSTRAINT "VideoEpisodeExportTask_novel_owner_fkey"
    FOREIGN KEY ("novelId", "requestedByUserId") REFERENCES "Novel"("id", "userId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeExportTask_adaptation_project_fkey"
    FOREIGN KEY ("adaptationId", "projectId")
    REFERENCES "VideoChapterAdaptation"("id", "projectId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeExportTask_adaptation_novel_fkey"
    FOREIGN KEY ("adaptationId", "novelId")
    REFERENCES "VideoChapterAdaptation"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeExportTask_episode_plan_fkey"
    FOREIGN KEY ("episodePlanVersionId", "shotPlanVersionId", "adaptationId")
    REFERENCES "VideoEpisodePlanVersion"("id", "shotPlanVersionId", "adaptationId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeExportTask_edit_version_fkey"
    FOREIGN KEY ("editVersionId", "episodePlanVersionId", "episodeNo")
    REFERENCES "VideoEpisodeEditVersion"("id", "episodePlanVersionId", "episodeNo")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeExportTask_mix_version_fkey"
    FOREIGN KEY ("mixVersionId", "episodePlanVersionId", "episodeNo")
    REFERENCES "VideoEpisodeMixVersion"("id", "episodePlanVersionId", "episodeNo")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeExportTask_retry_scope_fkey"
    FOREIGN KEY ("retryOfTaskId", "adaptationId", "episodeNo")
    REFERENCES "VideoEpisodeExportTask"("id", "adaptationId", "episodeNo")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeExportTask_user_fkey"
    FOREIGN KEY ("requestedByUserId") REFERENCES "User"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeExportTask_status_check"
    CHECK ("status" IN ('pending', 'rendering', 'succeeded', 'failed')),
  CONSTRAINT "VideoEpisodeExportTask_output_check"
    CHECK ("resolution" IN ('720p', '1080p') AND "framesPerSecond" IN (24, 25, 30)),
  CONSTRAINT "VideoEpisodeExportTask_numbers_check"
    CHECK ("episodeNo" > 0 AND "attemptCount" >= 0),
  CONSTRAINT "VideoEpisodeExportTask_hash_check" CHECK ("inputHash" ~ '^[0-9a-f]{64}$'),
  CONSTRAINT "VideoEpisodeExportTask_manifest_check"
    CHECK (COALESCE(jsonb_typeof("requestManifestJson"::jsonb) = 'object', FALSE)),
  CONSTRAINT "VideoEpisodeExportTask_request_check" CHECK (btrim("clientRequestId") <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeExportTask_id_scope_key"
ON "VideoEpisodeExportTask"("id", "adaptationId", "episodeNo");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeExportTask_user_request_key"
ON "VideoEpisodeExportTask"("requestedByUserId", "clientRequestId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeExportTask_active_episode_key"
ON "VideoEpisodeExportTask"("episodePlanVersionId", "episodeNo")
WHERE "status" IN ('pending', 'rendering');
CREATE INDEX IF NOT EXISTS "VideoEpisodeExportTask_due_idx"
ON "VideoEpisodeExportTask"("nextAttemptAt", "createdAt")
WHERE "status" IN ('pending', 'rendering');

CREATE TABLE IF NOT EXISTS "VideoEpisodeExport" (
  "id" TEXT NOT NULL,
  "taskId" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "episodePlanVersionId" TEXT NOT NULL,
  "episodeNo" INTEGER NOT NULL,
  "editVersionId" TEXT NOT NULL,
  "mixVersionId" TEXT NOT NULL,
  "assetId" TEXT NOT NULL,
  "versionNo" INTEGER NOT NULL,
  "inputHash" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoEpisodeExport_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoEpisodeExport_task_scope_fkey"
    FOREIGN KEY ("taskId", "adaptationId", "episodeNo")
    REFERENCES "VideoEpisodeExportTask"("id", "adaptationId", "episodeNo")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeExport_asset_project_fkey"
    FOREIGN KEY ("assetId", "projectId") REFERENCES "VideoAsset"("id", "projectId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeExport_edit_version_fkey"
    FOREIGN KEY ("editVersionId", "episodePlanVersionId", "episodeNo")
    REFERENCES "VideoEpisodeEditVersion"("id", "episodePlanVersionId", "episodeNo")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeExport_mix_version_fkey"
    FOREIGN KEY ("mixVersionId", "episodePlanVersionId", "episodeNo")
    REFERENCES "VideoEpisodeMixVersion"("id", "episodePlanVersionId", "episodeNo")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeExport_numbers_check" CHECK ("episodeNo" > 0 AND "versionNo" > 0),
  CONSTRAINT "VideoEpisodeExport_hash_check" CHECK ("inputHash" ~ '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeExport_taskId_key"
ON "VideoEpisodeExport"("taskId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeExport_assetId_key"
ON "VideoEpisodeExport"("assetId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodeExport_episode_version_key"
ON "VideoEpisodeExport"("episodePlanVersionId", "episodeNo", "versionNo");
CREATE INDEX IF NOT EXISTS "VideoEpisodeExport_episode_created_idx"
ON "VideoEpisodeExport"("episodePlanVersionId", "episodeNo", "createdAt");

COMMIT;
