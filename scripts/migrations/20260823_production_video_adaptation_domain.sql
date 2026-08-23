\set ON_ERROR_STOP on

-- 正式库具名迁移：必须由受控运维显式确认，普通 psql 调用会在任何 DDL 前退出。
\if :{?confirm_production_video_adaptation}
\else
  \echo '缺少确认参数：-v confirm_production_video_adaptation=novelwriter:20260823:apply'
  \quit 3
\endif

SELECT :'confirm_production_video_adaptation' = 'novelwriter:20260823:apply' AS confirmation_ok \gset
\if :confirmation_ok
\else
  \echo '确认参数不匹配，拒绝执行正式库视频结构迁移'
  \quit 3
\endif

BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 这里只接受当前已核验的正式库基线，或者由本脚本前序事务留下的可重放阶段边界。
DO $preflight$
DECLARE
  existing_video_table_count INTEGER;
  required_table TEXT;
  required_column TEXT;
BEGIN
  IF current_database() <> 'novelwriter' THEN
    RAISE EXCEPTION '正式视频结构迁移只允许在 novelwriter 执行，当前数据库为 %', current_database();
  END IF;

  FOREACH required_table IN ARRAY ARRAY['Novel', 'Chapter', 'ReviewArtifact', 'TokenUsage']
  LOOP
    IF to_regclass(format('public.%I', required_table)) IS NULL THEN
      RAISE EXCEPTION '正式视频结构迁移缺少基线表 %', required_table;
    END IF;
  END LOOP;

  IF to_regtype('public."ReviewArtifactKind"') IS NULL THEN
    RAISE EXCEPTION '正式视频结构迁移缺少基线枚举 ReviewArtifactKind';
  END IF;

  FOREACH required_column IN ARRAY ARRAY['requestId', 'taskId', 'runId']
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'TokenUsage'
        AND column_name = required_column
    ) THEN
      RAISE EXCEPTION 'TokenUsage 尚未完成 20260821 迁移，缺少字段 %', required_column;
    END IF;
  END LOOP;

  SELECT count(*) INTO existing_video_table_count
  FROM pg_class AS relation
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  WHERE namespace.nspname = 'public'
    AND relation.relkind IN ('r', 'p')
    AND relation.relname = ANY (ARRAY[
      'VideoAdaptationDecisionCommand',
      'VideoAdaptationTask',
      'VideoAsset',
      'VideoAssetBinding',
      'VideoChapterAdaptation',
      'VideoChapterAdaptationHead',
      'VideoCinematicScene',
      'VideoDramaticBeat',
      'VideoDramaticBeatSourceAnchor',
      'VideoEpisodeBoundary',
      'VideoEpisodePlanVersion',
      'VideoGenerationTask',
      'VideoProject',
      'VideoReviewDecisionCommand',
      'VideoScene',
      'VideoShot',
      'VideoShotPlanVersion',
      'VideoShotPromptHead',
      'VideoShotPromptVersion',
      'VideoShotPromptVisualReference',
      'VideoShotSourceAnchor',
      'VideoShotVisualReferenceBinding',
      'VideoShotVisualReferenceSet',
      'VideoVisualCanon',
      'VideoVisualCanonVersion'
    ]);

  IF existing_video_table_count NOT IN (0, 5, 6, 25) THEN
    RAISE EXCEPTION
      '正式库视频表处于未知的部分迁移状态：已存在 %/25 张；请先人工审计',
      existing_video_table_count;
  END IF;
END
$preflight$;

COMMIT;

BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 本阶段仅获准在服务器端 novelwriter 正式库执行，脚本自身必须拒绝其他数据库。
DO $safety$
BEGIN
  IF current_database() <> 'novelwriter' THEN
    RAISE EXCEPTION '视频制作迁移只允许在 novelwriter 执行，当前数据库为 %', current_database();
  END IF;
END
$safety$;

-- 防止两个受控运维进程并发创建视频控制面对象。
SELECT pg_advisory_xact_lock(hashtext('inkforge:20260823:production-video-adaptation:control-plane'));

-- ReviewArtifact 需要能明确表达视频场景方案，而不是伪装成写作草案。
ALTER TYPE "ReviewArtifactKind" ADD VALUE IF NOT EXISTS 'video_scene_plan';

CREATE TABLE IF NOT EXISTS "VideoProject" (
  "id" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "mode" TEXT NOT NULL DEFAULT 'highlight'::text,
  "status" TEXT NOT NULL DEFAULT 'draft'::text,
  "targetAspectRatio" TEXT NOT NULL DEFAULT '16:9'::text,
  "targetLanguage" TEXT NOT NULL DEFAULT 'zh-CN'::text,
  "provider" TEXT NOT NULL DEFAULT 'seedance_2_5'::text,
  "revision" INTEGER NOT NULL DEFAULT 1,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  "deletedAt" TIMESTAMP(3),
  CONSTRAINT "VideoProject_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoProject_novelId_fkey"
    FOREIGN KEY ("novelId") REFERENCES "Novel"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoProject_mode_check"
    CHECK ("mode" IN ('concept', 'trailer', 'highlight', 'short_film', 'episode', 'series')),
  CONSTRAINT "VideoProject_status_check"
    CHECK ("status" IN ('draft', 'active', 'archived')),
  CONSTRAINT "VideoProject_aspect_ratio_check"
    CHECK ("targetAspectRatio" IN ('16:9', '4:3', '1:1', '3:4', '9:16', '21:9', 'adaptive')),
  CONSTRAINT "VideoProject_revision_check" CHECK ("revision" > 0),
  CONSTRAINT "VideoProject_title_check" CHECK (btrim("title") <> '')
);

DROP INDEX IF EXISTS "VideoProject_novelId_updatedAt_idx";
CREATE INDEX "VideoProject_novelId_updatedAt_idx"
ON "VideoProject"("novelId", "updatedAt")
WHERE "deletedAt" IS NULL;

CREATE TABLE IF NOT EXISTS "VideoScene" (
  "id" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "chapterId" TEXT,
  "ordinal" INTEGER NOT NULL,
  "title" TEXT NOT NULL,
  "sourceText" TEXT NOT NULL,
  "sourceHash" TEXT NOT NULL,
  "durationSeconds" INTEGER NOT NULL DEFAULT 15,
  "status" TEXT NOT NULL DEFAULT 'draft'::text,
  "planJson" TEXT,
  "promptText" TEXT,
  "promptCharacterCount" INTEGER,
  "lastErrorCode" TEXT,
  "lastErrorMessage" TEXT,
  "revision" INTEGER NOT NULL DEFAULT 1,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoScene_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoScene_projectId_fkey"
    FOREIGN KEY ("projectId") REFERENCES "VideoProject"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoScene_chapterId_fkey"
    FOREIGN KEY ("chapterId") REFERENCES "Chapter"("id")
    ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT "VideoScene_project_ordinal_key" UNIQUE ("projectId", "ordinal"),
  CONSTRAINT "VideoScene_duration_check" CHECK ("durationSeconds" BETWEEN 4 AND 30),
  CONSTRAINT "VideoScene_status_check"
    CHECK ("status" IN ('draft', 'generating', 'awaiting_review', 'approved', 'rendering', 'completed', 'failed')),
  CONSTRAINT "VideoScene_source_hash_check" CHECK ("sourceHash" ~ '^[0-9a-f]{64}$'),
  CONSTRAINT "VideoScene_source_text_check" CHECK (btrim("sourceText") <> ''),
  CONSTRAINT "VideoScene_prompt_count_check"
    CHECK ("promptCharacterCount" IS NULL OR "promptCharacterCount" BETWEEN 1 AND 2000),
  CONSTRAINT "VideoScene_plan_json_check"
    CHECK ("planJson" IS NULL OR COALESCE(jsonb_typeof("planJson"::jsonb) = 'object', FALSE)),
  CONSTRAINT "VideoScene_revision_check" CHECK ("revision" > 0)
);

-- 500 字是方舟中文建议值而非已确认硬限制；数据库保存产品 2000 字安全包络。
ALTER TABLE "VideoScene"
DROP CONSTRAINT IF EXISTS "VideoScene_prompt_count_check";
ALTER TABLE "VideoScene"
ADD CONSTRAINT "VideoScene_prompt_count_check"
CHECK ("promptCharacterCount" IS NULL OR "promptCharacterCount" BETWEEN 1 AND 2000);

CREATE INDEX IF NOT EXISTS "VideoScene_projectId_status_idx"
ON "VideoScene"("projectId", "status", "ordinal");

CREATE INDEX IF NOT EXISTS "VideoScene_chapterId_idx"
ON "VideoScene"("chapterId");

-- 视频方案仍走统一 ReviewArtifact 审核链，并通过外键绑定具体场景。
ALTER TABLE "ReviewArtifact"
ADD COLUMN IF NOT EXISTS "videoSceneId" TEXT;

DO $review_fk$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ReviewArtifact_videoSceneId_fkey'
      AND conrelid = 'public."ReviewArtifact"'::regclass
  ) THEN
    ALTER TABLE "ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_videoSceneId_fkey"
      FOREIGN KEY ("videoSceneId") REFERENCES "VideoScene"("id")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END
$review_fk$;

CREATE INDEX IF NOT EXISTS "ReviewArtifact_videoSceneId_status_idx"
ON "ReviewArtifact"("videoSceneId", "status");

CREATE TABLE IF NOT EXISTS "VideoAsset" (
  "id" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "modality" TEXT NOT NULL,
  "duty" TEXT NOT NULL,
  "storageKey" TEXT NOT NULL,
  "mimeType" TEXT NOT NULL,
  "byteSize" BIGINT NOT NULL,
  "durationMs" INTEGER,
  "sha256" TEXT NOT NULL,
  "sourceKind" TEXT NOT NULL DEFAULT 'user_upload'::text,
  "rightsStatus" TEXT NOT NULL DEFAULT 'unconfirmed'::text,
  "lockedAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoAsset_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoAsset_projectId_fkey"
    FOREIGN KEY ("projectId") REFERENCES "VideoProject"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoAsset_project_storage_key" UNIQUE ("projectId", "storageKey"),
  CONSTRAINT "VideoAsset_modality_check" CHECK ("modality" IN ('image', 'video', 'audio')),
  CONSTRAINT "VideoAsset_duty_check"
    CHECK ("duty" IN ('identity', 'costume', 'scene', 'prop', 'style', 'storyboard', 'keyframe', 'motion', 'camera', 'voice', 'ambience', 'music')),
  CONSTRAINT "VideoAsset_source_kind_check"
    CHECK ("sourceKind" IN ('user_upload', 'authorized_real', 'virtual', 'model_generated')),
  CONSTRAINT "VideoAsset_rights_status_check"
    CHECK ("rightsStatus" IN ('unconfirmed', 'confirmed', 'restricted', 'rejected')),
  CONSTRAINT "VideoAsset_byte_size_check" CHECK ("byteSize" > 0),
  CONSTRAINT "VideoAsset_duration_check" CHECK ("durationMs" IS NULL OR "durationMs" > 0),
  CONSTRAINT "VideoAsset_sha256_check" CHECK ("sha256" ~ '^[0-9a-f]{64}$')
);

DROP INDEX IF EXISTS "VideoAsset_projectId_modality_idx";
CREATE INDEX "VideoAsset_projectId_modality_idx"
ON "VideoAsset"("projectId", "modality", "createdAt");

CREATE TABLE IF NOT EXISTS "VideoAssetBinding" (
  "id" TEXT NOT NULL,
  "sceneId" TEXT NOT NULL,
  "assetId" TEXT NOT NULL,
  "targetEntity" TEXT NOT NULL,
  "includeFeaturesJson" TEXT NOT NULL,
  "excludeFeaturesJson" TEXT NOT NULL DEFAULT '[]'::text,
  "priority" INTEGER NOT NULL DEFAULT 50,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoAssetBinding_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoAssetBinding_sceneId_fkey"
    FOREIGN KEY ("sceneId") REFERENCES "VideoScene"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoAssetBinding_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "VideoAsset"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoAssetBinding_scene_asset_key" UNIQUE ("sceneId", "assetId"),
  CONSTRAINT "VideoAssetBinding_priority_check" CHECK ("priority" BETWEEN 0 AND 100),
  CONSTRAINT "VideoAssetBinding_include_json_check"
    CHECK (COALESCE(jsonb_typeof("includeFeaturesJson"::jsonb) = 'array', FALSE)),
  CONSTRAINT "VideoAssetBinding_exclude_json_check"
    CHECK (COALESCE(jsonb_typeof("excludeFeaturesJson"::jsonb) = 'array', FALSE))
);

DROP INDEX IF EXISTS "VideoAssetBinding_sceneId_priority_idx";
CREATE INDEX "VideoAssetBinding_sceneId_priority_idx"
ON "VideoAssetBinding"("sceneId", "priority", "createdAt");

CREATE TABLE IF NOT EXISTS "VideoGenerationTask" (
  "id" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "sceneId" TEXT NOT NULL,
  "jobId" TEXT NOT NULL,
  "kind" TEXT NOT NULL,
  "provider" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'pending'::text,
  "idempotencyKey" TEXT NOT NULL,
  "providerTaskId" TEXT,
  "requestJson" TEXT NOT NULL,
  "resultJson" TEXT,
  "attemptCount" INTEGER NOT NULL DEFAULT 0,
  "nextAttemptAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "lastErrorCode" TEXT,
  "lastErrorMessage" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  "submittedAt" TIMESTAMP(3),
  "completedAt" TIMESTAMP(3),
  CONSTRAINT "VideoGenerationTask_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoGenerationTask_projectId_fkey"
    FOREIGN KEY ("projectId") REFERENCES "VideoProject"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoGenerationTask_sceneId_fkey"
    FOREIGN KEY ("sceneId") REFERENCES "VideoScene"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoGenerationTask_jobId_key" UNIQUE ("jobId"),
  CONSTRAINT "VideoGenerationTask_idempotencyKey_key" UNIQUE ("idempotencyKey"),
  CONSTRAINT "VideoGenerationTask_kind_check" CHECK ("kind" IN ('plan', 'render', 'poll', 'archive')),
  CONSTRAINT "VideoGenerationTask_status_check"
    CHECK ("status" IN ('pending', 'submitted', 'processing', 'awaiting_review', 'completed', 'failed', 'cancelled')),
  CONSTRAINT "VideoGenerationTask_attempt_count_check" CHECK ("attemptCount" >= 0),
  CONSTRAINT "VideoGenerationTask_request_json_check"
    CHECK (COALESCE(jsonb_typeof("requestJson"::jsonb) = 'object', FALSE)),
  CONSTRAINT "VideoGenerationTask_result_json_check"
    CHECK ("resultJson" IS NULL OR COALESCE(jsonb_typeof("resultJson"::jsonb) = 'object', FALSE))
);

CREATE INDEX IF NOT EXISTS "VideoGenerationTask_due_idx"
ON "VideoGenerationTask"("status", "nextAttemptAt", "createdAt")
WHERE "status" IN ('pending', 'submitted', 'processing');

DROP INDEX IF EXISTS "VideoGenerationTask_sceneId_createdAt_idx";
CREATE INDEX "VideoGenerationTask_sceneId_createdAt_idx"
ON "VideoGenerationTask"("sceneId", "createdAt");

COMMENT ON TABLE "VideoProject" IS '小说级视频制作项目';
COMMENT ON TABLE "VideoScene" IS '绑定不可变原文快照的可审核视频场景';
COMMENT ON TABLE "VideoAsset" IS '视频项目中具有哈希、权利状态和锁定状态的媒体素材';
COMMENT ON TABLE "VideoAssetBinding" IS '场景对真实素材及其参考职责的显式绑定';
COMMENT ON TABLE "VideoGenerationTask" IS '视频规划、渲染、轮询和归档的耐久任务事实';
COMMENT ON COLUMN "ReviewArtifact"."videoSceneId" IS '视频场景方案草案的审核目标';
COMMENT ON COLUMN "VideoScene"."sourceText" IS '用户选定原文的不可变快照，不随章节后续编辑改变';
COMMENT ON COLUMN "VideoScene"."planJson" IS '用户批准后应用的正式结构化场景方案';
COMMENT ON COLUMN "VideoAsset"."lockedAt" IS '素材权利已确认并由用户锁定的时间';

COMMIT;

BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 本阶段只得到服务器端 novelwriter 正式库授权，必须拒绝其他数据库。
DO $safety$
BEGIN
  IF current_database() <> 'novelwriter' THEN
    RAISE EXCEPTION '视频审核决定命令迁移只允许在 novelwriter 执行，当前数据库为 %', current_database();
  END IF;
END
$safety$;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260823:production-video-adaptation:review-command'));

-- 组合外键的目标必须有对应唯一约束。这些约束服务于视频批准命令的完整归属链。
DO $ownership_targets$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'Novel_id_userId_key'
      AND conrelid = 'public."Novel"'::regclass
  ) THEN
    ALTER TABLE "Novel"
    ADD CONSTRAINT "Novel_id_userId_key" UNIQUE ("id", "userId");
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoProject_id_novelId_key'
      AND conrelid = 'public."VideoProject"'::regclass
  ) THEN
    ALTER TABLE "VideoProject"
    ADD CONSTRAINT "VideoProject_id_novelId_key" UNIQUE ("id", "novelId");
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoScene_id_projectId_key'
      AND conrelid = 'public."VideoScene"'::regclass
  ) THEN
    ALTER TABLE "VideoScene"
    ADD CONSTRAINT "VideoScene_id_projectId_key" UNIQUE ("id", "projectId");
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ReviewArtifact_id_videoSceneId_key'
      AND conrelid = 'public."ReviewArtifact"'::regclass
  ) THEN
    ALTER TABLE "ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_id_videoSceneId_key" UNIQUE ("id", "videoSceneId");
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoGenerationTask_id_sceneId_projectId_key'
      AND conrelid = 'public."VideoGenerationTask"'::regclass
  ) THEN
    ALTER TABLE "VideoGenerationTask"
    ADD CONSTRAINT "VideoGenerationTask_id_sceneId_projectId_key"
      UNIQUE ("id", "sceneId", "projectId");
  END IF;
END
$ownership_targets$;

CREATE TABLE IF NOT EXISTS "VideoReviewDecisionCommand" (
  "id" TEXT NOT NULL,
  "requestedByUserId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "sceneId" TEXT NOT NULL,
  "artifactId" TEXT NOT NULL,
  "sourceTaskId" TEXT NOT NULL,
  "decision" TEXT NOT NULL DEFAULT 'approve'::text,
  "expectedArtifactRevision" INTEGER NOT NULL,
  "clientRequestId" TEXT NOT NULL,
  "requestHash" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'succeeded'::text,
  "resultJson" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  "completedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoReviewDecisionCommand_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoReviewDecisionCommand_requestedByUserId_fkey"
    FOREIGN KEY ("requestedByUserId") REFERENCES "User"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoReviewDecisionCommand_sceneId_fkey"
    FOREIGN KEY ("sceneId") REFERENCES "VideoScene"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoReviewDecisionCommand_artifactId_fkey"
    FOREIGN KEY ("artifactId") REFERENCES "ReviewArtifact"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoReviewDecisionCommand_sourceTaskId_fkey"
    FOREIGN KEY ("sourceTaskId") REFERENCES "VideoGenerationTask"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoReviewDecisionCommand_novel_owner_fkey"
    FOREIGN KEY ("novelId", "requestedByUserId") REFERENCES "Novel"("id", "userId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoReviewDecisionCommand_project_novel_fkey"
    FOREIGN KEY ("projectId", "novelId") REFERENCES "VideoProject"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoReviewDecisionCommand_scene_project_fkey"
    FOREIGN KEY ("sceneId", "projectId") REFERENCES "VideoScene"("id", "projectId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoReviewDecisionCommand_artifact_scene_fkey"
    FOREIGN KEY ("artifactId", "sceneId") REFERENCES "ReviewArtifact"("id", "videoSceneId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoReviewDecisionCommand_task_scene_project_fkey"
    FOREIGN KEY ("sourceTaskId", "sceneId", "projectId")
    REFERENCES "VideoGenerationTask"("id", "sceneId", "projectId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoReviewDecisionCommand_decision_check"
    CHECK ("decision" = 'approve'),
  CONSTRAINT "VideoReviewDecisionCommand_revision_check"
    CHECK ("expectedArtifactRevision" > 0),
  CONSTRAINT "VideoReviewDecisionCommand_client_request_check"
    CHECK (char_length("clientRequestId") BETWEEN 16 AND 128 AND btrim("clientRequestId") = "clientRequestId"),
  CONSTRAINT "VideoReviewDecisionCommand_request_hash_check"
    CHECK ("requestHash" ~ '^[0-9a-f]{64}$'),
  CONSTRAINT "VideoReviewDecisionCommand_status_check"
    CHECK ("status" = 'succeeded'),
  CONSTRAINT "VideoReviewDecisionCommand_result_json_check"
    CHECK (COALESCE(jsonb_typeof("resultJson"::jsonb) = 'object', FALSE))
);

-- 兼容由本脚本前序阶段留下的结构：先补列并由既有场景/项目事实回填。
ALTER TABLE "VideoReviewDecisionCommand"
ADD COLUMN IF NOT EXISTS "novelId" TEXT;

ALTER TABLE "VideoReviewDecisionCommand"
ADD COLUMN IF NOT EXISTS "projectId" TEXT;

UPDATE "VideoReviewDecisionCommand" AS command
SET
  "projectId" = scene."projectId",
  "novelId" = project."novelId"
FROM "VideoScene" AS scene
JOIN "VideoProject" AS project
  ON project."id" = scene."projectId"
WHERE command."sceneId" = scene."id"
  AND (command."projectId" IS NULL OR command."novelId" IS NULL);

ALTER TABLE "VideoReviewDecisionCommand"
ALTER COLUMN "novelId" SET NOT NULL;

ALTER TABLE "VideoReviewDecisionCommand"
ALTER COLUMN "projectId" SET NOT NULL;

DO $ownership_foreign_keys$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoReviewDecisionCommand_novel_owner_fkey'
      AND conrelid = 'public."VideoReviewDecisionCommand"'::regclass
  ) THEN
    ALTER TABLE "VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_novel_owner_fkey"
      FOREIGN KEY ("novelId", "requestedByUserId") REFERENCES "Novel"("id", "userId")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoReviewDecisionCommand_project_novel_fkey'
      AND conrelid = 'public."VideoReviewDecisionCommand"'::regclass
  ) THEN
    ALTER TABLE "VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_project_novel_fkey"
      FOREIGN KEY ("projectId", "novelId") REFERENCES "VideoProject"("id", "novelId")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoReviewDecisionCommand_scene_project_fkey'
      AND conrelid = 'public."VideoReviewDecisionCommand"'::regclass
  ) THEN
    ALTER TABLE "VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_scene_project_fkey"
      FOREIGN KEY ("sceneId", "projectId") REFERENCES "VideoScene"("id", "projectId")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoReviewDecisionCommand_artifact_scene_fkey'
      AND conrelid = 'public."VideoReviewDecisionCommand"'::regclass
  ) THEN
    ALTER TABLE "VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_artifact_scene_fkey"
      FOREIGN KEY ("artifactId", "sceneId") REFERENCES "ReviewArtifact"("id", "videoSceneId")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoReviewDecisionCommand_task_scene_project_fkey'
      AND conrelid = 'public."VideoReviewDecisionCommand"'::regclass
  ) THEN
    ALTER TABLE "VideoReviewDecisionCommand"
    ADD CONSTRAINT "VideoReviewDecisionCommand_task_scene_project_fkey"
      FOREIGN KEY ("sourceTaskId", "sceneId", "projectId")
      REFERENCES "VideoGenerationTask"("id", "sceneId", "projectId")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END
$ownership_foreign_keys$;

CREATE UNIQUE INDEX IF NOT EXISTS "VideoReviewDecisionCommand_user_request_key"
ON "VideoReviewDecisionCommand"("requestedByUserId", "clientRequestId");

-- 命令按请求键唯一；同一候选的不同请求键可以各自记录为重放，但正式应用仍只执行一次。
DROP INDEX IF EXISTS "VideoReviewDecisionCommand_artifact_revision_key";
CREATE INDEX IF NOT EXISTS "VideoReviewDecisionCommand_artifact_revision_idx"
ON "VideoReviewDecisionCommand"("artifactId", "expectedArtifactRevision", "decision");

CREATE INDEX IF NOT EXISTS "VideoReviewDecisionCommand_scene_created_idx"
ON "VideoReviewDecisionCommand"("sceneId", "createdAt");

COMMENT ON TABLE "VideoReviewDecisionCommand" IS
  '视频候选同步批准的耐久幂等命令；不代表完整视频 production_v2 审核命令';
COMMENT ON COLUMN "VideoReviewDecisionCommand"."requestHash" IS
  '由动作、场景和预期候选 revision 计算的规范请求 SHA-256';
COMMENT ON COLUMN "VideoReviewDecisionCommand"."resultJson" IS
  '首次成功批准返回给浏览器的完整响应，用于网络结果不确定时原样重放';
COMMENT ON COLUMN "VideoReviewDecisionCommand"."novelId" IS
  '与请求用户、视频项目共同受组合外键保护的小说归属';
COMMENT ON COLUMN "VideoReviewDecisionCommand"."projectId" IS
  '与场景、来源任务共同受组合外键保护的视频项目归属';

COMMIT;

BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 本阶段只得到服务器端 novelwriter 正式库授权，必须拒绝其他数据库。
DO $safety$
BEGIN
  IF current_database() <> 'novelwriter' THEN
    RAISE EXCEPTION '视频域归属链迁移只允许在 novelwriter 执行，当前数据库为 %', current_database();
  END IF;
END
$safety$;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260823:production-video-adaptation:ownership'));

ALTER TABLE "VideoScene"
ADD COLUMN IF NOT EXISTS "novelId" TEXT;

ALTER TABLE "VideoAssetBinding"
ADD COLUMN IF NOT EXISTS "projectId" TEXT;

-- 冗余归属只从现有权威父记录回填，绝不猜测或静默修正非空冲突值。
UPDATE "VideoScene" AS scene
SET "novelId" = project."novelId"
FROM "VideoProject" AS project
WHERE scene."projectId" = project."id"
  AND scene."novelId" IS NULL;

UPDATE "VideoAssetBinding" AS binding
SET "projectId" = scene."projectId"
FROM "VideoScene" AS scene
WHERE binding."sceneId" = scene."id"
  AND binding."projectId" IS NULL;

-- 在加约束前给出明确失败原因；任一计数非零都会回滚整笔迁移。
DO $ownership_audit$
DECLARE
  invalid_count BIGINT;
BEGIN
  SELECT count(*) INTO invalid_count
  FROM "VideoScene" AS scene
  JOIN "VideoProject" AS project ON project."id" = scene."projectId"
  WHERE scene."novelId" IS DISTINCT FROM project."novelId";
  IF invalid_count <> 0 THEN
    RAISE EXCEPTION 'VideoScene 项目与小说归属不一致：% 条', invalid_count;
  END IF;

  SELECT count(*) INTO invalid_count
  FROM "VideoScene" AS scene
  JOIN "Chapter" AS chapter ON chapter."id" = scene."chapterId"
  WHERE scene."chapterId" IS NOT NULL
    AND chapter."novelId" <> scene."novelId";
  IF invalid_count <> 0 THEN
    RAISE EXCEPTION 'VideoScene 章节与小说归属不一致：% 条', invalid_count;
  END IF;

  SELECT count(*) INTO invalid_count
  FROM "ReviewArtifact" AS artifact
  JOIN "VideoScene" AS scene ON scene."id" = artifact."videoSceneId"
  WHERE artifact."videoSceneId" IS NOT NULL
    AND artifact."novelId" <> scene."novelId";
  IF invalid_count <> 0 THEN
    RAISE EXCEPTION 'ReviewArtifact 场景与小说归属不一致：% 条', invalid_count;
  END IF;

  SELECT count(*) INTO invalid_count
  FROM "VideoGenerationTask" AS task
  JOIN "VideoScene" AS scene ON scene."id" = task."sceneId"
  WHERE task."projectId" <> scene."projectId";
  IF invalid_count <> 0 THEN
    RAISE EXCEPTION 'VideoGenerationTask 场景与项目归属不一致：% 条', invalid_count;
  END IF;

  SELECT count(*) INTO invalid_count
  FROM "VideoAssetBinding" AS binding
  JOIN "VideoScene" AS scene ON scene."id" = binding."sceneId"
  JOIN "VideoAsset" AS asset ON asset."id" = binding."assetId"
  WHERE binding."projectId" IS DISTINCT FROM scene."projectId"
     OR binding."projectId" IS DISTINCT FROM asset."projectId";
  IF invalid_count <> 0 THEN
    RAISE EXCEPTION 'VideoAssetBinding 场景、素材与项目归属不一致：% 条', invalid_count;
  END IF;
END
$ownership_audit$;

ALTER TABLE "VideoScene"
ALTER COLUMN "novelId" SET NOT NULL;

ALTER TABLE "VideoAssetBinding"
ALTER COLUMN "projectId" SET NOT NULL;

DO $ownership_targets$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'Chapter_id_novelId_key'
      AND conrelid = 'public."Chapter"'::regclass
  ) THEN
    ALTER TABLE "Chapter"
    ADD CONSTRAINT "Chapter_id_novelId_key" UNIQUE ("id", "novelId");
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoScene_id_novelId_key'
      AND conrelid = 'public."VideoScene"'::regclass
  ) THEN
    ALTER TABLE "VideoScene"
    ADD CONSTRAINT "VideoScene_id_novelId_key" UNIQUE ("id", "novelId");
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoAsset_id_projectId_key'
      AND conrelid = 'public."VideoAsset"'::regclass
  ) THEN
    ALTER TABLE "VideoAsset"
    ADD CONSTRAINT "VideoAsset_id_projectId_key" UNIQUE ("id", "projectId");
  END IF;
END
$ownership_targets$;

DO $ownership_foreign_keys$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoScene_project_novel_fkey'
      AND conrelid = 'public."VideoScene"'::regclass
  ) THEN
    ALTER TABLE "VideoScene"
    ADD CONSTRAINT "VideoScene_project_novel_fkey"
      FOREIGN KEY ("projectId", "novelId") REFERENCES "VideoProject"("id", "novelId")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoScene_chapter_novel_fkey'
      AND conrelid = 'public."VideoScene"'::regclass
  ) THEN
    ALTER TABLE "VideoScene"
    ADD CONSTRAINT "VideoScene_chapter_novel_fkey"
      FOREIGN KEY ("chapterId", "novelId") REFERENCES "Chapter"("id", "novelId")
      ON DELETE NO ACTION ON UPDATE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ReviewArtifact_video_scene_novel_fkey'
      AND conrelid = 'public."ReviewArtifact"'::regclass
  ) THEN
    ALTER TABLE "ReviewArtifact"
    ADD CONSTRAINT "ReviewArtifact_video_scene_novel_fkey"
      FOREIGN KEY ("videoSceneId", "novelId") REFERENCES "VideoScene"("id", "novelId")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoGenerationTask_scene_project_fkey'
      AND conrelid = 'public."VideoGenerationTask"'::regclass
  ) THEN
    ALTER TABLE "VideoGenerationTask"
    ADD CONSTRAINT "VideoGenerationTask_scene_project_fkey"
      FOREIGN KEY ("sceneId", "projectId") REFERENCES "VideoScene"("id", "projectId")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoAssetBinding_scene_project_fkey'
      AND conrelid = 'public."VideoAssetBinding"'::regclass
  ) THEN
    ALTER TABLE "VideoAssetBinding"
    ADD CONSTRAINT "VideoAssetBinding_scene_project_fkey"
      FOREIGN KEY ("sceneId", "projectId") REFERENCES "VideoScene"("id", "projectId")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'VideoAssetBinding_asset_project_fkey'
      AND conrelid = 'public."VideoAssetBinding"'::regclass
  ) THEN
    ALTER TABLE "VideoAssetBinding"
    ADD CONSTRAINT "VideoAssetBinding_asset_project_fkey"
      FOREIGN KEY ("assetId", "projectId") REFERENCES "VideoAsset"("id", "projectId")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END
$ownership_foreign_keys$;

COMMENT ON COLUMN "VideoScene"."novelId" IS
  '由 VideoProject 冗余并受组合外键保护的小说归属，用于约束章节和审核候选';
COMMENT ON COLUMN "VideoAssetBinding"."projectId" IS
  '由 VideoScene 冗余并同时约束场景与素材的项目归属';

COMMIT;

BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 本阶段只获得服务器端 novelwriter 正式库授权；其他数据库必须主动拒绝。
DO $safety$
BEGIN
  IF current_database() <> 'novelwriter' THEN
    RAISE EXCEPTION '章节影视化领域迁移只允许在 novelwriter 执行，当前数据库为 %', current_database();
  END IF;
END
$safety$;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260823:production-video-adaptation:chapter-domain'));

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

-- 已执行过早期阶段时，把显示快照从 Canon Head 固定到不可变版本。
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

BEGIN;

SET LOCAL search_path = public, pg_catalog;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260823:production-video-adaptation:verify'));

DO $verification$
DECLARE
  required_table TEXT;
  required_column TEXT;
BEGIN
  IF current_database() <> 'novelwriter' THEN
    RAISE EXCEPTION '正式视频结构迁移终检只允许在 novelwriter 执行，当前数据库为 %', current_database();
  END IF;

  FOREACH required_table IN ARRAY ARRAY[
    'VideoAdaptationDecisionCommand',
    'VideoAdaptationTask',
    'VideoAsset',
    'VideoAssetBinding',
    'VideoChapterAdaptation',
    'VideoChapterAdaptationHead',
    'VideoCinematicScene',
    'VideoDramaticBeat',
    'VideoDramaticBeatSourceAnchor',
    'VideoEpisodeBoundary',
    'VideoEpisodePlanVersion',
    'VideoGenerationTask',
    'VideoProject',
    'VideoReviewDecisionCommand',
    'VideoScene',
    'VideoShot',
    'VideoShotPlanVersion',
    'VideoShotPromptHead',
    'VideoShotPromptVersion',
    'VideoShotPromptVisualReference',
    'VideoShotSourceAnchor',
    'VideoShotVisualReferenceBinding',
    'VideoShotVisualReferenceSet',
    'VideoVisualCanon',
    'VideoVisualCanonVersion'
  ]
  LOOP
    IF to_regclass(format('public.%I', required_table)) IS NULL THEN
      RAISE EXCEPTION '正式视频结构迁移终检缺少表 %', required_table;
    END IF;
  END LOOP;

  FOREACH required_column IN ARRAY ARRAY['videoSceneId', 'videoAdaptationId', 'videoAdaptationTaskId']
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'ReviewArtifact'
        AND column_name = required_column
    ) THEN
      RAISE EXCEPTION '正式视频结构迁移终检缺少 ReviewArtifact.%', required_column;
    END IF;
  END LOOP;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_enum AS enum_value
    JOIN pg_type AS enum_type ON enum_type.oid = enum_value.enumtypid
    JOIN pg_namespace AS namespace ON namespace.oid = enum_type.typnamespace
    WHERE namespace.nspname = 'public'
      AND enum_type.typname = 'ReviewArtifactKind'
      AND enum_value.enumlabel = 'video_scene_plan'
  ) OR NOT EXISTS (
    SELECT 1
    FROM pg_enum AS enum_value
    JOIN pg_type AS enum_type ON enum_type.oid = enum_value.enumtypid
    JOIN pg_namespace AS namespace ON namespace.oid = enum_type.typnamespace
    WHERE namespace.nspname = 'public'
      AND enum_type.typname = 'ReviewArtifactKind'
      AND enum_value.enumlabel = 'video_adaptation_plan'
  ) THEN
    RAISE EXCEPTION '正式视频结构迁移终检缺少 ReviewArtifactKind 视频枚举值';
  END IF;
END
$verification$;

COMMIT;
