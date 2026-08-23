BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 本迁移只获得服务器端 novelwriterdev 开发库授权；生产库和其他数据库必须主动拒绝。
DO $safety$
BEGIN
  IF current_database() <> 'novelwriterdev' THEN
    RAISE EXCEPTION '章节影视化领域迁移只允许在 novelwriterdev 执行，当前数据库为 %', current_database();
  END IF;
END
$safety$;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260818:video-chapter-adaptation-domain'));

ALTER TYPE "ReviewArtifactKind" ADD VALUE IF NOT EXISTS 'video_adaptation_plan';

CREATE TABLE IF NOT EXISTS "VideoChapterAdaptation" (
  "id" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "chapterId" TEXT,
  "chapterTitle" TEXT NOT NULL,
  "chapterUpdatedAt" TIMESTAMP(3) NOT NULL,
  "sourceText" TEXT NOT NULL,
  "sourceHash" TEXT NOT NULL,
  "lifecycleStatus" TEXT NOT NULL DEFAULT 'active'::text,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoChapterAdaptation_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoChapterAdaptation_project_novel_fkey"
    FOREIGN KEY ("projectId", "novelId") REFERENCES "VideoProject"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoChapterAdaptation_chapterId_fkey"
    FOREIGN KEY ("chapterId") REFERENCES "Chapter"("id")
    ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT "VideoChapterAdaptation_chapter_novel_fkey"
    FOREIGN KEY ("chapterId", "novelId") REFERENCES "Chapter"("id", "novelId")
    ON DELETE NO ACTION ON UPDATE CASCADE,
  CONSTRAINT "VideoChapterAdaptation_title_check" CHECK (btrim("chapterTitle") <> ''),
  CONSTRAINT "VideoChapterAdaptation_source_check" CHECK (btrim("sourceText") <> ''),
  CONSTRAINT "VideoChapterAdaptation_source_hash_check" CHECK ("sourceHash" ~ '^[0-9a-f]{64}$'),
  CONSTRAINT "VideoChapterAdaptation_lifecycle_check"
    CHECK ("lifecycleStatus" IN ('active', 'archived'))
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoChapterAdaptation_id_projectId_key"
ON "VideoChapterAdaptation"("id", "projectId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoChapterAdaptation_id_novelId_key"
ON "VideoChapterAdaptation"("id", "novelId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoChapterAdaptation_project_chapter_source_key"
ON "VideoChapterAdaptation"("projectId", "chapterId", "sourceHash")
WHERE "chapterId" IS NOT NULL AND "lifecycleStatus" = 'active';
CREATE INDEX IF NOT EXISTS "VideoChapterAdaptation_project_created_idx"
ON "VideoChapterAdaptation"("projectId", "createdAt");

CREATE TABLE IF NOT EXISTS "VideoAdaptationTask" (
  "id" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "baseShotPlanVersionId" TEXT,
  "jobId" TEXT NOT NULL,
  "kind" TEXT NOT NULL,
  "workflow" TEXT NOT NULL,
  "provider" TEXT NOT NULL DEFAULT 'deepseek'::text,
  "status" TEXT NOT NULL DEFAULT 'pending'::text,
  "idempotencyKey" TEXT NOT NULL,
  "requestJson" TEXT NOT NULL,
  "resultJson" TEXT,
  "checkpointStage" TEXT NOT NULL DEFAULT 'none'::text,
  "checkpointJson" TEXT,
  "attemptCount" INTEGER NOT NULL DEFAULT 0,
  "nextAttemptAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "lastErrorCode" TEXT,
  "lastErrorMessage" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  "submittedAt" TIMESTAMP(3),
  "completedAt" TIMESTAMP(3),
  CONSTRAINT "VideoAdaptationTask_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoAdaptationTask_adaptation_project_fkey"
    FOREIGN KEY ("adaptationId", "projectId")
    REFERENCES "VideoChapterAdaptation"("id", "projectId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoAdaptationTask_adaptation_novel_fkey"
    FOREIGN KEY ("adaptationId", "novelId")
    REFERENCES "VideoChapterAdaptation"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoAdaptationTask_project_novel_fkey"
    FOREIGN KEY ("projectId", "novelId") REFERENCES "VideoProject"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoAdaptationTask_kind_workflow_check" CHECK (
    ("kind" = 'shot_plan' AND "workflow" = 'chapter_cinematic_adaptation_v2')
    OR
    ("kind" = 'shot_prompt' AND "workflow" = 'chapter_shot_prompt_v2' AND "baseShotPlanVersionId" IS NOT NULL)
  ),
  CONSTRAINT "VideoAdaptationTask_status_check"
    CHECK ("status" IN ('pending', 'submitted', 'processing', 'completed', 'failed', 'cancelled')),
  CONSTRAINT "VideoAdaptationTask_checkpoint_check" CHECK (
    ("checkpointStage" = 'none' AND "checkpointJson" IS NULL)
    OR
    ("checkpointStage" = 'dramatic_structure'
      AND COALESCE(jsonb_typeof("checkpointJson"::jsonb) = 'object', FALSE))
  ),
  CONSTRAINT "VideoAdaptationTask_request_json_check"
    CHECK (COALESCE(jsonb_typeof("requestJson"::jsonb) = 'object', FALSE)),
  CONSTRAINT "VideoAdaptationTask_result_json_check"
    CHECK ("resultJson" IS NULL OR COALESCE(jsonb_typeof("resultJson"::jsonb) = 'object', FALSE)),
  CONSTRAINT "VideoAdaptationTask_attempt_check" CHECK ("attemptCount" >= 0)
);

-- shot_plan 允许可空正式方案基线；旧约束来自本迁移已执行版本，需显式替换。
ALTER TABLE "VideoAdaptationTask"
DROP CONSTRAINT IF EXISTS "VideoAdaptationTask_kind_workflow_check";
ALTER TABLE "VideoAdaptationTask"
ADD CONSTRAINT "VideoAdaptationTask_kind_workflow_check" CHECK (
  ("kind" = 'shot_plan' AND "workflow" = 'chapter_cinematic_adaptation_v2')
  OR
  ("kind" = 'shot_prompt' AND "workflow" = 'chapter_shot_prompt_v2' AND "baseShotPlanVersionId" IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoAdaptationTask_id_adaptationId_key"
ON "VideoAdaptationTask"("id", "adaptationId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoAdaptationTask_jobId_key"
ON "VideoAdaptationTask"("jobId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoAdaptationTask_idempotencyKey_key"
ON "VideoAdaptationTask"("idempotencyKey");
CREATE INDEX IF NOT EXISTS "VideoAdaptationTask_due_idx"
ON "VideoAdaptationTask"("status", "nextAttemptAt", "createdAt")
WHERE "status" IN ('pending', 'submitted', 'processing');
CREATE INDEX IF NOT EXISTS "VideoAdaptationTask_adaptation_created_idx"
ON "VideoAdaptationTask"("adaptationId", "createdAt");

ALTER TABLE "ReviewArtifact"
ADD COLUMN IF NOT EXISTS "videoAdaptationId" TEXT;
ALTER TABLE "ReviewArtifact"
ADD COLUMN IF NOT EXISTS "videoAdaptationTaskId" TEXT;

DO $review_artifact_constraints$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ReviewArtifact_videoAdaptationId_fkey'
      AND conrelid = 'public."ReviewArtifact"'::regclass
  ) THEN
    ALTER TABLE "ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_videoAdaptationId_fkey"
      FOREIGN KEY ("videoAdaptationId") REFERENCES "VideoChapterAdaptation"("id")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ReviewArtifact_video_adaptation_novel_fkey'
      AND conrelid = 'public."ReviewArtifact"'::regclass
  ) THEN
    ALTER TABLE "ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_video_adaptation_novel_fkey"
      FOREIGN KEY ("videoAdaptationId", "novelId")
      REFERENCES "VideoChapterAdaptation"("id", "novelId")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ReviewArtifact_video_adaptation_task_fkey'
      AND conrelid = 'public."ReviewArtifact"'::regclass
  ) THEN
    ALTER TABLE "ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_video_adaptation_task_fkey"
      FOREIGN KEY ("videoAdaptationTaskId", "videoAdaptationId")
      REFERENCES "VideoAdaptationTask"("id", "adaptationId")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ReviewArtifact_video_target_exclusive_check'
      AND conrelid = 'public."ReviewArtifact"'::regclass
  ) THEN
    ALTER TABLE "ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_video_target_exclusive_check"
      CHECK (NOT ("videoSceneId" IS NOT NULL AND "videoAdaptationId" IS NOT NULL));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ReviewArtifact_video_adaptation_kind_check'
      AND conrelid = 'public."ReviewArtifact"'::regclass
  ) THEN
    ALTER TABLE "ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_video_adaptation_kind_check" CHECK (
      "kind"::text <> 'video_adaptation_plan'
      OR (
        "videoAdaptationId" IS NOT NULL
        AND "videoAdaptationTaskId" IS NOT NULL
        AND "videoSceneId" IS NULL
        AND "taskId" IS NULL
      )
    );
  END IF;
END
$review_artifact_constraints$;

CREATE UNIQUE INDEX IF NOT EXISTS "ReviewArtifact_id_videoAdaptationId_key"
ON "ReviewArtifact"("id", "videoAdaptationId");
CREATE INDEX IF NOT EXISTS "ReviewArtifact_videoAdaptationId_status_idx"
ON "ReviewArtifact"("videoAdaptationId", "status");

CREATE TABLE IF NOT EXISTS "VideoShotPlanVersion" (
  "id" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "versionNo" INTEGER NOT NULL,
  "basedOnVersionId" TEXT,
  "sourceTaskId" TEXT NOT NULL,
  "reviewArtifactId" TEXT NOT NULL,
  "createdByUserId" TEXT NOT NULL,
  "contentHash" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoShotPlanVersion_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoShotPlanVersion_adaptationId_fkey"
    FOREIGN KEY ("adaptationId") REFERENCES "VideoChapterAdaptation"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPlanVersion_source_task_fkey"
    FOREIGN KEY ("sourceTaskId", "adaptationId")
    REFERENCES "VideoAdaptationTask"("id", "adaptationId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPlanVersion_review_artifact_fkey"
    FOREIGN KEY ("reviewArtifactId", "adaptationId")
    REFERENCES "ReviewArtifact"("id", "videoAdaptationId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPlanVersion_createdByUserId_fkey"
    FOREIGN KEY ("createdByUserId") REFERENCES "User"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPlanVersion_version_check" CHECK ("versionNo" > 0),
  CONSTRAINT "VideoShotPlanVersion_content_hash_check" CHECK ("contentHash" ~ '^[0-9a-f]{64}$'),
  CONSTRAINT "VideoShotPlanVersion_adaptation_version_key" UNIQUE ("adaptationId", "versionNo"),
  CONSTRAINT "VideoShotPlanVersion_sourceTaskId_key" UNIQUE ("sourceTaskId"),
  CONSTRAINT "VideoShotPlanVersion_reviewArtifactId_key" UNIQUE ("reviewArtifactId")
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotPlanVersion_id_adaptationId_key"
ON "VideoShotPlanVersion"("id", "adaptationId");

DO $shot_plan_self_fk$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoShotPlanVersion_based_on_fkey'
      AND conrelid = 'public."VideoShotPlanVersion"'::regclass
  ) THEN
    ALTER TABLE "VideoShotPlanVersion"
    ADD CONSTRAINT "VideoShotPlanVersion_based_on_fkey"
      FOREIGN KEY ("basedOnVersionId", "adaptationId")
      REFERENCES "VideoShotPlanVersion"("id", "adaptationId")
      ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END
$shot_plan_self_fk$;

DO $task_plan_fk$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoAdaptationTask_base_plan_fkey'
      AND conrelid = 'public."VideoAdaptationTask"'::regclass
  ) THEN
    ALTER TABLE "VideoAdaptationTask"
    ADD CONSTRAINT "VideoAdaptationTask_base_plan_fkey"
      FOREIGN KEY ("baseShotPlanVersionId", "adaptationId")
      REFERENCES "VideoShotPlanVersion"("id", "adaptationId")
      ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END
$task_plan_fk$;

CREATE UNIQUE INDEX IF NOT EXISTS "VideoAdaptationTask_id_baseShotPlanVersionId_key"
ON "VideoAdaptationTask"("id", "baseShotPlanVersionId");

CREATE TABLE IF NOT EXISTS "VideoChapterAdaptationHead" (
  "adaptationId" TEXT NOT NULL,
  "currentShotPlanVersionId" TEXT,
  "currentEpisodePlanVersionId" TEXT,
  "revision" INTEGER NOT NULL DEFAULT 1,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoChapterAdaptationHead_pkey" PRIMARY KEY ("adaptationId"),
  CONSTRAINT "VideoChapterAdaptationHead_adaptationId_fkey"
    FOREIGN KEY ("adaptationId") REFERENCES "VideoChapterAdaptation"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoChapterAdaptationHead_current_plan_fkey"
    FOREIGN KEY ("currentShotPlanVersionId", "adaptationId")
    REFERENCES "VideoShotPlanVersion"("id", "adaptationId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoChapterAdaptationHead_revision_check" CHECK ("revision" > 0)
);

CREATE TABLE IF NOT EXISTS "VideoCinematicScene" (
  "id" TEXT NOT NULL,
  "planVersionId" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "sceneKey" TEXT NOT NULL,
  "ordinal" INTEGER NOT NULL,
  "title" TEXT NOT NULL,
  "locationLabel" TEXT NOT NULL,
  "timeLabel" TEXT NOT NULL,
  "objective" TEXT NOT NULL,
  "changeSummary" TEXT NOT NULL,
  CONSTRAINT "VideoCinematicScene_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoCinematicScene_plan_adaptation_fkey"
    FOREIGN KEY ("planVersionId", "adaptationId")
    REFERENCES "VideoShotPlanVersion"("id", "adaptationId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoCinematicScene_key_check" CHECK ("sceneKey" ~ '^SC[0-9]{2,3}$'),
  CONSTRAINT "VideoCinematicScene_ordinal_check" CHECK ("ordinal" > 0),
  CONSTRAINT "VideoCinematicScene_text_check" CHECK (
    btrim("title") <> '' AND btrim("locationLabel") <> '' AND btrim("timeLabel") <> ''
    AND btrim("objective") <> '' AND btrim("changeSummary") <> ''
  ),
  CONSTRAINT "VideoCinematicScene_plan_key_key" UNIQUE ("planVersionId", "sceneKey"),
  CONSTRAINT "VideoCinematicScene_plan_ordinal_key" UNIQUE ("planVersionId", "ordinal")
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoCinematicScene_id_planVersionId_key"
ON "VideoCinematicScene"("id", "planVersionId");

CREATE TABLE IF NOT EXISTS "VideoDramaticBeat" (
  "id" TEXT NOT NULL,
  "planVersionId" TEXT NOT NULL,
  "sceneId" TEXT NOT NULL,
  "beatKey" TEXT NOT NULL,
  "ordinal" INTEGER NOT NULL,
  "title" TEXT NOT NULL,
  "dramaticTurn" TEXT NOT NULL,
  "visualStrategy" TEXT NOT NULL,
  "coverageGoalsJson" TEXT,
  CONSTRAINT "VideoDramaticBeat_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoDramaticBeat_scene_plan_fkey"
    FOREIGN KEY ("sceneId", "planVersionId")
    REFERENCES "VideoCinematicScene"("id", "planVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoDramaticBeat_key_check" CHECK ("beatKey" ~ '^B[0-9]{2,3}$'),
  CONSTRAINT "VideoDramaticBeat_ordinal_check" CHECK ("ordinal" > 0),
  CONSTRAINT "VideoDramaticBeat_text_check" CHECK (
    btrim("title") <> '' AND btrim("dramaticTurn") <> '' AND btrim("visualStrategy") <> ''
  ),
  CONSTRAINT "VideoDramaticBeat_plan_key_key" UNIQUE ("planVersionId", "beatKey"),
  CONSTRAINT "VideoDramaticBeat_plan_ordinal_key" UNIQUE ("planVersionId", "ordinal")
);

ALTER TABLE "VideoDramaticBeat"
ADD COLUMN IF NOT EXISTS "coverageGoalsJson" TEXT;
ALTER TABLE "VideoDramaticBeat"
DROP CONSTRAINT IF EXISTS "VideoDramaticBeat_coverage_goals_check";
ALTER TABLE "VideoDramaticBeat"
ADD CONSTRAINT "VideoDramaticBeat_coverage_goals_check" CHECK (
  "coverageGoalsJson" IS NULL
  OR (
    COALESCE(jsonb_typeof("coverageGoalsJson"::jsonb) = 'array', FALSE)
    AND jsonb_array_length("coverageGoalsJson"::jsonb) > 0
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoDramaticBeat_id_planVersionId_key"
ON "VideoDramaticBeat"("id", "planVersionId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoDramaticBeat_id_sceneId_planVersionId_key"
ON "VideoDramaticBeat"("id", "sceneId", "planVersionId");

CREATE TABLE IF NOT EXISTS "VideoDramaticBeatSourceAnchor" (
  "beatId" TEXT NOT NULL,
  "planVersionId" TEXT NOT NULL,
  "ordinal" INTEGER NOT NULL,
  "startCodePoint" INTEGER NOT NULL,
  "endCodePoint" INTEGER NOT NULL,
  CONSTRAINT "VideoDramaticBeatSourceAnchor_pkey" PRIMARY KEY ("beatId", "ordinal"),
  CONSTRAINT "VideoDramaticBeatSourceAnchor_beat_plan_fkey"
    FOREIGN KEY ("beatId", "planVersionId")
    REFERENCES "VideoDramaticBeat"("id", "planVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoDramaticBeatSourceAnchor_ordinal_check" CHECK ("ordinal" > 0),
  CONSTRAINT "VideoDramaticBeatSourceAnchor_range_check"
    CHECK ("startCodePoint" >= 0 AND "endCodePoint" > "startCodePoint")
);

CREATE TABLE IF NOT EXISTS "VideoShot" (
  "id" TEXT NOT NULL,
  "planVersionId" TEXT NOT NULL,
  "sceneId" TEXT NOT NULL,
  "beatId" TEXT NOT NULL,
  "shotKey" TEXT NOT NULL,
  "ordinal" INTEGER NOT NULL,
  "title" TEXT NOT NULL,
  "narrativePurpose" TEXT NOT NULL,
  "adaptationType" TEXT NOT NULL,
  "sourceRelation" TEXT,
  "storyFunction" TEXT,
  "audienceGain" TEXT,
  "coveredGoalKeysJson" TEXT,
  "shotScale" TEXT NOT NULL,
  "cameraAngle" TEXT NOT NULL,
  "cameraMovement" TEXT NOT NULL,
  "visualIntent" TEXT NOT NULL,
  "audioMode" TEXT NOT NULL,
  "audioIntent" TEXT NOT NULL,
  "speechMode" TEXT,
  "spokenText" TEXT,
  "cutReason" TEXT NOT NULL,
  "timelineDurationMs" INTEGER NOT NULL,
  CONSTRAINT "VideoShot_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoShot_scene_plan_fkey"
    FOREIGN KEY ("sceneId", "planVersionId")
    REFERENCES "VideoCinematicScene"("id", "planVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShot_beat_plan_fkey"
    FOREIGN KEY ("beatId", "planVersionId")
    REFERENCES "VideoDramaticBeat"("id", "planVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShot_beat_scene_plan_fkey"
    FOREIGN KEY ("beatId", "sceneId", "planVersionId")
    REFERENCES "VideoDramaticBeat"("id", "sceneId", "planVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShot_key_check" CHECK ("shotKey" ~ '^S[0-9]{2,3}$'),
  CONSTRAINT "VideoShot_ordinal_check" CHECK ("ordinal" > 0),
  CONSTRAINT "VideoShot_purpose_check" CHECK (
    "narrativePurpose" IN ('establishing', 'action', 'dialogue', 'reaction', 'reveal', 'insert', 'transition', 'atmosphere')
  ),
  CONSTRAINT "VideoShot_adaptation_type_check"
    CHECK ("adaptationType" IN ('direct', 'visualized', 'voiceover', 'supplemental')),
  CONSTRAINT "VideoShot_scale_check" CHECK (
    "shotScale" IN ('extreme_long', 'long', 'medium', 'medium_close', 'close', 'extreme_close', 'over_shoulder', 'two_shot', 'pov')
  ),
  CONSTRAINT "VideoShot_angle_check"
    CHECK ("cameraAngle" IN ('eye_level', 'high_angle', 'low_angle', 'overhead', 'dutch_angle')),
  CONSTRAINT "VideoShot_movement_check" CHECK (
    "cameraMovement" IN ('locked', 'pan', 'tilt', 'push_in', 'pull_out', 'tracking', 'arc', 'handheld', 'focus_shift')
  ),
  CONSTRAINT "VideoShot_audio_mode_check"
    CHECK ("audioMode" IN ('sync_dialogue', 'offscreen_dialogue', 'voiceover', 'ambient', 'music', 'silence')),
  CONSTRAINT "VideoShot_duration_check"
    CHECK ("timelineDurationMs" BETWEEN 500 AND 15000 AND mod("timelineDurationMs", 500) = 0),
  CONSTRAINT "VideoShot_text_check" CHECK (
    btrim("title") <> '' AND btrim("visualIntent") <> '' AND btrim("audioIntent") <> '' AND btrim("cutReason") <> ''
  ),
  CONSTRAINT "VideoShot_plan_key_key" UNIQUE ("planVersionId", "shotKey"),
  CONSTRAINT "VideoShot_plan_ordinal_key" UNIQUE ("planVersionId", "ordinal")
);

ALTER TABLE "VideoShot" ADD COLUMN IF NOT EXISTS "sourceRelation" TEXT;
ALTER TABLE "VideoShot" ADD COLUMN IF NOT EXISTS "storyFunction" TEXT;
ALTER TABLE "VideoShot" ADD COLUMN IF NOT EXISTS "audienceGain" TEXT;
ALTER TABLE "VideoShot" ADD COLUMN IF NOT EXISTS "coveredGoalKeysJson" TEXT;
ALTER TABLE "VideoShot" ADD COLUMN IF NOT EXISTS "speechMode" TEXT;
ALTER TABLE "VideoShot" ADD COLUMN IF NOT EXISTS "spokenText" TEXT;
ALTER TABLE "VideoShot"
DROP CONSTRAINT IF EXISTS "VideoShot_goal_driven_fields_check";
ALTER TABLE "VideoShot"
ADD CONSTRAINT "VideoShot_goal_driven_fields_check" CHECK (
  (
    "sourceRelation" IS NULL AND "storyFunction" IS NULL AND "audienceGain" IS NULL
    AND "coveredGoalKeysJson" IS NULL AND "speechMode" IS NULL AND "spokenText" IS NULL
  )
  OR (
    "sourceRelation" IN ('direct', 'derived', 'supplemental')
    AND COALESCE(btrim("storyFunction") <> '', FALSE)
    AND COALESCE(btrim("audienceGain") <> '', FALSE)
    AND COALESCE(jsonb_typeof("coveredGoalKeysJson"::jsonb) = 'array', FALSE)
    AND "speechMode" IN ('none', 'sync', 'offscreen', 'voiceover')
    AND (
      ("speechMode" = 'none' AND "spokenText" IS NULL)
      OR ("speechMode" <> 'none' AND COALESCE(btrim("spokenText") <> '', FALSE))
    )
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoShot_id_planVersionId_key"
ON "VideoShot"("id", "planVersionId");

DO $shot_beat_scene_fk$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoShot_beat_scene_plan_fkey'
      AND conrelid = 'public."VideoShot"'::regclass
  ) THEN
    ALTER TABLE "VideoShot"
    ADD CONSTRAINT "VideoShot_beat_scene_plan_fkey"
      FOREIGN KEY ("beatId", "sceneId", "planVersionId")
      REFERENCES "VideoDramaticBeat"("id", "sceneId", "planVersionId")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END
$shot_beat_scene_fk$;

CREATE TABLE IF NOT EXISTS "VideoShotSourceAnchor" (
  "shotId" TEXT NOT NULL,
  "planVersionId" TEXT NOT NULL,
  "ordinal" INTEGER NOT NULL,
  "startCodePoint" INTEGER NOT NULL,
  "endCodePoint" INTEGER NOT NULL,
  CONSTRAINT "VideoShotSourceAnchor_pkey" PRIMARY KEY ("shotId", "ordinal"),
  CONSTRAINT "VideoShotSourceAnchor_shot_plan_fkey"
    FOREIGN KEY ("shotId", "planVersionId") REFERENCES "VideoShot"("id", "planVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotSourceAnchor_ordinal_check" CHECK ("ordinal" > 0),
  CONSTRAINT "VideoShotSourceAnchor_range_check"
    CHECK ("startCodePoint" >= 0 AND "endCodePoint" > "startCodePoint")
);

CREATE TABLE IF NOT EXISTS "VideoEpisodePlanVersion" (
  "id" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "versionNo" INTEGER NOT NULL,
  "basedOnVersionId" TEXT,
  "createdByUserId" TEXT NOT NULL,
  "contentHash" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoEpisodePlanVersion_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoEpisodePlanVersion_shot_plan_fkey"
    FOREIGN KEY ("shotPlanVersionId", "adaptationId")
    REFERENCES "VideoShotPlanVersion"("id", "adaptationId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodePlanVersion_createdByUserId_fkey"
    FOREIGN KEY ("createdByUserId") REFERENCES "User"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodePlanVersion_version_check" CHECK ("versionNo" > 0),
  CONSTRAINT "VideoEpisodePlanVersion_content_hash_check" CHECK ("contentHash" ~ '^[0-9a-f]{64}$'),
  CONSTRAINT "VideoEpisodePlanVersion_adaptation_version_key" UNIQUE ("adaptationId", "versionNo")
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodePlanVersion_id_adaptationId_key"
ON "VideoEpisodePlanVersion"("id", "adaptationId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodePlanVersion_id_shotPlanVersionId_key"
ON "VideoEpisodePlanVersion"("id", "shotPlanVersionId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoEpisodePlanVersion_id_shotPlanVersionId_adaptationId_key"
ON "VideoEpisodePlanVersion"("id", "shotPlanVersionId", "adaptationId");

DO $episode_plan_self_fk$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoEpisodePlanVersion_based_on_fkey'
      AND conrelid = 'public."VideoEpisodePlanVersion"'::regclass
  ) THEN
    ALTER TABLE "VideoEpisodePlanVersion"
    ADD CONSTRAINT "VideoEpisodePlanVersion_based_on_fkey"
      FOREIGN KEY ("basedOnVersionId", "adaptationId")
      REFERENCES "VideoEpisodePlanVersion"("id", "adaptationId")
      ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END
$episode_plan_self_fk$;

CREATE TABLE IF NOT EXISTS "VideoEpisodeBoundary" (
  "episodePlanVersionId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "afterShotId" TEXT NOT NULL,
  "ordinal" INTEGER NOT NULL,
  CONSTRAINT "VideoEpisodeBoundary_pkey" PRIMARY KEY ("episodePlanVersionId", "ordinal"),
  CONSTRAINT "VideoEpisodeBoundary_episode_shot_plan_fkey"
    FOREIGN KEY ("episodePlanVersionId", "shotPlanVersionId")
    REFERENCES "VideoEpisodePlanVersion"("id", "shotPlanVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeBoundary_shot_plan_fkey"
    FOREIGN KEY ("afterShotId", "shotPlanVersionId")
    REFERENCES "VideoShot"("id", "planVersionId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoEpisodeBoundary_ordinal_check" CHECK ("ordinal" > 0),
  CONSTRAINT "VideoEpisodeBoundary_version_shot_key" UNIQUE ("episodePlanVersionId", "afterShotId")
);

DO $adaptation_head_episode_fk$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoChapterAdaptationHead_current_episode_fkey'
      AND conrelid = 'public."VideoChapterAdaptationHead"'::regclass
  ) THEN
    ALTER TABLE "VideoChapterAdaptationHead"
    ADD CONSTRAINT "VideoChapterAdaptationHead_current_episode_fkey"
      FOREIGN KEY ("currentEpisodePlanVersionId", "adaptationId")
      REFERENCES "VideoEpisodePlanVersion"("id", "adaptationId")
      ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END
$adaptation_head_episode_fk$;

DO $adaptation_head_episode_plan_fk$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoChapterAdaptationHead_current_episode_plan_fkey'
      AND conrelid = 'public."VideoChapterAdaptationHead"'::regclass
  ) THEN
    ALTER TABLE "VideoChapterAdaptationHead"
    ADD CONSTRAINT "VideoChapterAdaptationHead_current_episode_plan_fkey"
      FOREIGN KEY ("currentEpisodePlanVersionId", "currentShotPlanVersionId", "adaptationId")
      REFERENCES "VideoEpisodePlanVersion"("id", "shotPlanVersionId", "adaptationId")
      ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END
$adaptation_head_episode_plan_fk$;

CREATE TABLE IF NOT EXISTS "VideoShotPromptVersion" (
  "id" TEXT NOT NULL,
  "shotId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "versionNo" INTEGER NOT NULL,
  "basedOnVersionId" TEXT,
  "generatedText" TEXT,
  "currentText" TEXT NOT NULL,
  "sourceTaskId" TEXT,
  "createdByUserId" TEXT NOT NULL,
  "contentHash" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoShotPromptVersion_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoShotPromptVersion_shot_plan_fkey"
    FOREIGN KEY ("shotId", "shotPlanVersionId")
    REFERENCES "VideoShot"("id", "planVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPromptVersion_sourceTaskId_fkey"
    FOREIGN KEY ("sourceTaskId") REFERENCES "VideoAdaptationTask"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPromptVersion_source_task_plan_fkey"
    FOREIGN KEY ("sourceTaskId", "shotPlanVersionId")
    REFERENCES "VideoAdaptationTask"("id", "baseShotPlanVersionId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPromptVersion_createdByUserId_fkey"
    FOREIGN KEY ("createdByUserId") REFERENCES "User"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPromptVersion_version_check" CHECK ("versionNo" > 0),
  CONSTRAINT "VideoShotPromptVersion_text_check" CHECK (
    char_length("currentText") BETWEEN 1 AND 2000
    AND ("generatedText" IS NULL OR char_length("generatedText") BETWEEN 1 AND 2000)
  ),
  CONSTRAINT "VideoShotPromptVersion_content_hash_check" CHECK ("contentHash" ~ '^[0-9a-f]{64}$'),
  CONSTRAINT "VideoShotPromptVersion_shot_version_key" UNIQUE ("shotId", "versionNo")
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotPromptVersion_id_shotId_key"
ON "VideoShotPromptVersion"("id", "shotId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotPromptVersion_id_shot_plan_key"
ON "VideoShotPromptVersion"("id", "shotId", "shotPlanVersionId");

DO $prompt_source_task_plan_fk$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoShotPromptVersion_source_task_plan_fkey'
      AND conrelid = 'public."VideoShotPromptVersion"'::regclass
  ) THEN
    ALTER TABLE "VideoShotPromptVersion"
    ADD CONSTRAINT "VideoShotPromptVersion_source_task_plan_fkey"
      FOREIGN KEY ("sourceTaskId", "shotPlanVersionId")
      REFERENCES "VideoAdaptationTask"("id", "baseShotPlanVersionId")
      ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END
$prompt_source_task_plan_fk$;

DO $prompt_version_self_fk$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoShotPromptVersion_based_on_fkey'
      AND conrelid = 'public."VideoShotPromptVersion"'::regclass
  ) THEN
    ALTER TABLE "VideoShotPromptVersion"
    ADD CONSTRAINT "VideoShotPromptVersion_based_on_fkey"
      FOREIGN KEY ("basedOnVersionId", "shotId")
      REFERENCES "VideoShotPromptVersion"("id", "shotId")
      ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END
$prompt_version_self_fk$;

CREATE TABLE IF NOT EXISTS "VideoShotPromptHead" (
  "shotId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "currentVersionId" TEXT,
  "revision" INTEGER NOT NULL DEFAULT 1,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoShotPromptHead_pkey" PRIMARY KEY ("shotId"),
  CONSTRAINT "VideoShotPromptHead_shot_plan_fkey"
    FOREIGN KEY ("shotId", "shotPlanVersionId")
    REFERENCES "VideoShot"("id", "planVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPromptHead_current_version_fkey"
    FOREIGN KEY ("currentVersionId", "shotId")
    REFERENCES "VideoShotPromptVersion"("id", "shotId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPromptHead_revision_check" CHECK ("revision" > 0)
);

-- VideoAsset 只保存媒体文件；视觉设定槽负责候选、批准版本和当前 Head。
CREATE TABLE IF NOT EXISTS "VideoVisualCanon" (
  "id" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "settingKind" TEXT NOT NULL,
  "settingId" TEXT NOT NULL,
  "settingName" TEXT NOT NULL,
  "duty" TEXT NOT NULL,
  "variantKey" TEXT NOT NULL,
  "label" TEXT NOT NULL,
  "candidateAssetId" TEXT,
  "candidateIncludeFeaturesJson" TEXT,
  "candidateExcludeFeaturesJson" TEXT,
  "candidateDefaultStrength" INTEGER,
  "currentVersionId" TEXT,
  "revision" INTEGER NOT NULL DEFAULT 1,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoVisualCanon_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoVisualCanon_project_novel_fkey"
    FOREIGN KEY ("projectId", "novelId") REFERENCES "VideoProject"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoVisualCanon_candidate_asset_fkey"
    FOREIGN KEY ("candidateAssetId", "projectId") REFERENCES "VideoAsset"("id", "projectId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoVisualCanon_kind_duty_check" CHECK (
    ("settingKind" = 'character' AND "duty" IN ('identity', 'costume'))
    OR ("settingKind" = 'location' AND "duty" = 'scene')
    OR ("settingKind" = 'item' AND "duty" = 'prop')
  ),
  CONSTRAINT "VideoVisualCanon_text_check" CHECK (
    btrim("settingId") <> '' AND btrim("settingName") <> '' AND btrim("label") <> ''
    AND "variantKey" ~ '^[a-z0-9][a-z0-9_-]{0,63}$'
  ),
  CONSTRAINT "VideoVisualCanon_candidate_check" CHECK (
    (
      "candidateAssetId" IS NULL
      AND "candidateIncludeFeaturesJson" IS NULL
      AND "candidateExcludeFeaturesJson" IS NULL
      AND "candidateDefaultStrength" IS NULL
    )
    OR (
      "candidateAssetId" IS NOT NULL
      AND COALESCE(jsonb_typeof("candidateIncludeFeaturesJson"::jsonb) = 'array', FALSE)
      AND COALESCE(jsonb_typeof("candidateExcludeFeaturesJson"::jsonb) = 'array', FALSE)
      AND "candidateDefaultStrength" BETWEEN 1 AND 100
    )
  ),
  CONSTRAINT "VideoVisualCanon_revision_check" CHECK ("revision" > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoVisualCanon_id_project_novel_key"
ON "VideoVisualCanon"("id", "projectId", "novelId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoVisualCanon_slot_key"
ON "VideoVisualCanon"("projectId", "settingKind", "settingId", "duty", "variantKey");
CREATE INDEX IF NOT EXISTS "VideoVisualCanon_project_setting_idx"
ON "VideoVisualCanon"("projectId", "settingKind", "settingId");

CREATE TABLE IF NOT EXISTS "VideoVisualCanonVersion" (
  "id" TEXT NOT NULL,
  "canonId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "versionNo" INTEGER NOT NULL,
  "assetId" TEXT NOT NULL,
  "settingName" TEXT NOT NULL,
  "label" TEXT NOT NULL,
  "includeFeaturesJson" TEXT NOT NULL,
  "excludeFeaturesJson" TEXT NOT NULL,
  "defaultStrength" INTEGER NOT NULL,
  "approvedByUserId" TEXT NOT NULL,
  "contentHash" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoVisualCanonVersion_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoVisualCanonVersion_canon_scope_fkey"
    FOREIGN KEY ("canonId", "projectId", "novelId")
    REFERENCES "VideoVisualCanon"("id", "projectId", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoVisualCanonVersion_asset_project_fkey"
    FOREIGN KEY ("assetId", "projectId") REFERENCES "VideoAsset"("id", "projectId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoVisualCanonVersion_user_fkey"
    FOREIGN KEY ("approvedByUserId") REFERENCES "User"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoVisualCanonVersion_version_check" CHECK ("versionNo" > 0),
  CONSTRAINT "VideoVisualCanonVersion_features_check" CHECK (
    COALESCE(jsonb_typeof("includeFeaturesJson"::jsonb) = 'array', FALSE)
    AND COALESCE(jsonb_typeof("excludeFeaturesJson"::jsonb) = 'array', FALSE)
  ),
  CONSTRAINT "VideoVisualCanonVersion_strength_check" CHECK ("defaultStrength" BETWEEN 1 AND 100),
  CONSTRAINT "VideoVisualCanonVersion_text_check" CHECK (
    btrim("settingName") <> '' AND btrim("label") <> ''
  ),
  CONSTRAINT "VideoVisualCanonVersion_hash_check" CHECK ("contentHash" ~ '^[0-9a-f]{64}$'),
  CONSTRAINT "VideoVisualCanonVersion_canon_version_key" UNIQUE ("canonId", "versionNo")
);

-- 已执行过早期开发版本时，把显示快照从 Canon Head 固定到不可变版本。
ALTER TABLE "VideoVisualCanonVersion" ADD COLUMN IF NOT EXISTS "settingName" TEXT;
ALTER TABLE "VideoVisualCanonVersion" ADD COLUMN IF NOT EXISTS "label" TEXT;
UPDATE "VideoVisualCanonVersion" AS version
SET
  "settingName" = canon."settingName",
  "label" = canon."label"
FROM "VideoVisualCanon" AS canon
WHERE version."canonId" = canon."id"
  AND (version."settingName" IS NULL OR version."label" IS NULL);
ALTER TABLE "VideoVisualCanonVersion" ALTER COLUMN "settingName" SET NOT NULL;
ALTER TABLE "VideoVisualCanonVersion" ALTER COLUMN "label" SET NOT NULL;
ALTER TABLE "VideoVisualCanonVersion"
DROP CONSTRAINT IF EXISTS "VideoVisualCanonVersion_text_check";
ALTER TABLE "VideoVisualCanonVersion"
ADD CONSTRAINT "VideoVisualCanonVersion_text_check" CHECK (
  btrim("settingName") <> '' AND btrim("label") <> ''
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoVisualCanonVersion_id_canonId_key"
ON "VideoVisualCanonVersion"("id", "canonId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoVisualCanonVersion_id_project_novel_key"
ON "VideoVisualCanonVersion"("id", "projectId", "novelId");

DO $visual_canon_current_version_fk$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoVisualCanon_current_version_fkey'
      AND conrelid = 'public."VideoVisualCanon"'::regclass
  ) THEN
    ALTER TABLE "VideoVisualCanon"
    ADD CONSTRAINT "VideoVisualCanon_current_version_fkey"
      FOREIGN KEY ("currentVersionId", "id")
      REFERENCES "VideoVisualCanonVersion"("id", "canonId")
      ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END
$visual_canon_current_version_fk$;

CREATE TABLE IF NOT EXISTS "VideoShotVisualReferenceSet" (
  "shotId" TEXT NOT NULL,
  "planVersionId" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "revision" INTEGER NOT NULL DEFAULT 1,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoShotVisualReferenceSet_pkey" PRIMARY KEY ("shotId"),
  CONSTRAINT "VideoShotVisualReferenceSet_shot_plan_fkey"
    FOREIGN KEY ("shotId", "planVersionId") REFERENCES "VideoShot"("id", "planVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotVisualReferenceSet_plan_adaptation_fkey"
    FOREIGN KEY ("planVersionId", "adaptationId")
    REFERENCES "VideoShotPlanVersion"("id", "adaptationId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotVisualReferenceSet_adaptation_project_fkey"
    FOREIGN KEY ("adaptationId", "projectId")
    REFERENCES "VideoChapterAdaptation"("id", "projectId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotVisualReferenceSet_adaptation_novel_fkey"
    FOREIGN KEY ("adaptationId", "novelId")
    REFERENCES "VideoChapterAdaptation"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotVisualReferenceSet_project_novel_fkey"
    FOREIGN KEY ("projectId", "novelId") REFERENCES "VideoProject"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotVisualReferenceSet_revision_check" CHECK ("revision" > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotVisualReferenceSet_scope_key"
ON "VideoShotVisualReferenceSet"("shotId", "planVersionId", "adaptationId", "projectId", "novelId");

CREATE TABLE IF NOT EXISTS "VideoShotVisualReferenceBinding" (
  "shotId" TEXT NOT NULL,
  "ordinal" INTEGER NOT NULL,
  "planVersionId" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "canonVersionId" TEXT NOT NULL,
  "strength" INTEGER NOT NULL,
  CONSTRAINT "VideoShotVisualReferenceBinding_pkey" PRIMARY KEY ("shotId", "ordinal"),
  CONSTRAINT "VideoShotVisualReferenceBinding_set_scope_fkey"
    FOREIGN KEY ("shotId", "planVersionId", "adaptationId", "projectId", "novelId")
    REFERENCES "VideoShotVisualReferenceSet"(
      "shotId", "planVersionId", "adaptationId", "projectId", "novelId"
    ) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotVisualReferenceBinding_canon_scope_fkey"
    FOREIGN KEY ("canonVersionId", "projectId", "novelId")
    REFERENCES "VideoVisualCanonVersion"("id", "projectId", "novelId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotVisualReferenceBinding_ordinal_check" CHECK ("ordinal" > 0),
  CONSTRAINT "VideoShotVisualReferenceBinding_strength_check" CHECK ("strength" BETWEEN 1 AND 100),
  CONSTRAINT "VideoShotVisualReferenceBinding_shot_canon_key" UNIQUE ("shotId", "canonVersionId")
);

CREATE TABLE IF NOT EXISTS "VideoShotPromptVisualReference" (
  "promptVersionId" TEXT NOT NULL,
  "shotId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "ordinal" INTEGER NOT NULL,
  "canonVersionId" TEXT NOT NULL,
  "strength" INTEGER NOT NULL,
  CONSTRAINT "VideoShotPromptVisualReference_pkey" PRIMARY KEY ("promptVersionId", "ordinal"),
  CONSTRAINT "VideoShotPromptVisualReference_prompt_scope_fkey"
    FOREIGN KEY ("promptVersionId", "shotId", "shotPlanVersionId")
    REFERENCES "VideoShotPromptVersion"("id", "shotId", "shotPlanVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPromptVisualReference_plan_adaptation_fkey"
    FOREIGN KEY ("shotPlanVersionId", "adaptationId")
    REFERENCES "VideoShotPlanVersion"("id", "adaptationId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPromptVisualReference_adaptation_project_fkey"
    FOREIGN KEY ("adaptationId", "projectId")
    REFERENCES "VideoChapterAdaptation"("id", "projectId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPromptVisualReference_adaptation_novel_fkey"
    FOREIGN KEY ("adaptationId", "novelId")
    REFERENCES "VideoChapterAdaptation"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPromptVisualReference_canon_scope_fkey"
    FOREIGN KEY ("canonVersionId", "projectId", "novelId")
    REFERENCES "VideoVisualCanonVersion"("id", "projectId", "novelId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotPromptVisualReference_ordinal_check" CHECK ("ordinal" > 0),
  CONSTRAINT "VideoShotPromptVisualReference_strength_check" CHECK ("strength" BETWEEN 1 AND 100),
  CONSTRAINT "VideoShotPromptVisualReference_prompt_canon_key"
    UNIQUE ("promptVersionId", "canonVersionId")
);

CREATE TABLE IF NOT EXISTS "VideoAdaptationDecisionCommand" (
  "id" TEXT NOT NULL,
  "requestedByUserId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "artifactId" TEXT NOT NULL,
  "sourceTaskId" TEXT NOT NULL,
  "clientRequestId" TEXT NOT NULL,
  "expectedArtifactRevision" INTEGER NOT NULL,
  "expectedAdaptationRevision" INTEGER NOT NULL,
  "requestHash" TEXT NOT NULL,
  "decision" TEXT NOT NULL DEFAULT 'approve'::text,
  "status" TEXT NOT NULL DEFAULT 'succeeded'::text,
  "resultJson" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  "completedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoAdaptationDecisionCommand_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoAdaptationDecisionCommand_user_fkey"
    FOREIGN KEY ("requestedByUserId") REFERENCES "User"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoAdaptationDecisionCommand_novel_owner_fkey"
    FOREIGN KEY ("novelId", "requestedByUserId") REFERENCES "Novel"("id", "userId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoAdaptationDecisionCommand_project_novel_fkey"
    FOREIGN KEY ("projectId", "novelId") REFERENCES "VideoProject"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoAdaptationDecisionCommand_adaptation_project_fkey"
    FOREIGN KEY ("adaptationId", "projectId")
    REFERENCES "VideoChapterAdaptation"("id", "projectId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoAdaptationDecisionCommand_artifact_adaptation_fkey"
    FOREIGN KEY ("artifactId", "adaptationId")
    REFERENCES "ReviewArtifact"("id", "videoAdaptationId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoAdaptationDecisionCommand_task_adaptation_fkey"
    FOREIGN KEY ("sourceTaskId", "adaptationId")
    REFERENCES "VideoAdaptationTask"("id", "adaptationId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoAdaptationDecisionCommand_client_request_check" CHECK (btrim("clientRequestId") <> ''),
  CONSTRAINT "VideoAdaptationDecisionCommand_revision_check"
    CHECK ("expectedArtifactRevision" > 0 AND "expectedAdaptationRevision" > 0),
  CONSTRAINT "VideoAdaptationDecisionCommand_request_hash_check" CHECK ("requestHash" ~ '^[0-9a-f]{64}$'),
  CONSTRAINT "VideoAdaptationDecisionCommand_decision_check" CHECK ("decision" = 'approve'),
  CONSTRAINT "VideoAdaptationDecisionCommand_status_check" CHECK ("status" = 'succeeded'),
  CONSTRAINT "VideoAdaptationDecisionCommand_result_json_check"
    CHECK (COALESCE(jsonb_typeof("resultJson"::jsonb) = 'object', FALSE))
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoAdaptationDecisionCommand_user_request_key"
ON "VideoAdaptationDecisionCommand"("requestedByUserId", "clientRequestId");
CREATE INDEX IF NOT EXISTS "VideoAdaptationDecisionCommand_adaptation_created_idx"
ON "VideoAdaptationDecisionCommand"("adaptationId", "createdAt");

COMMENT ON TABLE "VideoChapterAdaptation" IS '长篇章节不可变来源快照及影视化工作台根对象';
COMMENT ON TABLE "VideoAdaptationTask" IS '章节拆镜与逐镜提示词的 PostgreSQL 耐久任务事实';
COMMENT ON TABLE "VideoShotPlanVersion" IS '用户批准后的不可变章节电影化镜头方案版本';
COMMENT ON TABLE "VideoCinematicScene" IS '正式镜头方案中的真实时间地点连续场景';
COMMENT ON TABLE "VideoDramaticBeat" IS '正式场景中由目标、信息、情绪或行动变化定义的戏剧节拍';
COMMENT ON TABLE "VideoShot" IS '正式戏剧节拍中的最终剪辑镜头，不等同于供应商生成片段';
COMMENT ON TABLE "VideoEpisodePlanVersion" IS '固定引用一个镜头方案版本的不可变分集边界版本';
COMMENT ON TABLE "VideoShotPromptVersion" IS '用户明确保存的逐镜即梦提示词不可变版本';
COMMENT ON TABLE "VideoVisualCanon" IS '项目内文字设定对应的候选和当前视觉设定槽';
COMMENT ON TABLE "VideoVisualCanonVersion" IS '用户批准后引用已锁定图片的不可变视觉设定版本';
COMMENT ON TABLE "VideoShotVisualReferenceSet" IS '正式镜头当前视觉参考集合的 CAS Head';
COMMENT ON TABLE "VideoShotVisualReferenceBinding" IS '镜头参考集合中的有序视觉版本与参考强度';
COMMENT ON TABLE "VideoShotPromptVisualReference" IS '正式提示词版本冻结的视觉参考版本';
COMMENT ON COLUMN "ReviewArtifact"."videoAdaptationId" IS '章节影视化镜头方案候选的明确审核目标';
COMMENT ON COLUMN "ReviewArtifact"."videoAdaptationTaskId" IS '产生章节影视化候选的耐久来源任务';

COMMIT;
