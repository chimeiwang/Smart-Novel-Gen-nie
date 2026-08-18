BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 本迁移得到的授权仅覆盖服务器端 novelwriterdev 开发库，脚本自身必须拒绝其他数据库。
DO $safety$
BEGIN
  IF current_database() <> 'novelwriterdev' THEN
    RAISE EXCEPTION '视频制作迁移只允许在 novelwriterdev 执行，当前数据库为 %', current_database();
  END IF;
END
$safety$;

-- 防止两个开发进程并发创建视频控制面对象。
SELECT pg_advisory_xact_lock(hashtext('inkforge:20260807:video-production-control-plane'));

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
