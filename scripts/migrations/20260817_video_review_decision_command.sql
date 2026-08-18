BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 本迁移只得到服务器端 novelwriterdev 开发库授权，必须拒绝测试库和生产库。
DO $safety$
BEGIN
  IF current_database() <> 'novelwriterdev' THEN
    RAISE EXCEPTION '视频审核决定命令迁移只允许在 novelwriterdev 执行，当前数据库为 %', current_database();
  END IF;
END
$safety$;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260817:video-review-decision-command'));

-- 组合外键的目标必须有对应唯一约束。这些约束只服务于 dev 视频批准命令的完整归属链。
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

-- 兼容已执行过上一版具名迁移的 dev 库：先补列并由既有场景/项目事实回填。
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
  '服务器 dev 库中视频候选同步批准的开发预览耐久幂等命令；不代表完整视频 v2 审核命令';
COMMENT ON COLUMN "VideoReviewDecisionCommand"."requestHash" IS
  '由动作、场景和预期候选 revision 计算的规范请求 SHA-256';
COMMENT ON COLUMN "VideoReviewDecisionCommand"."resultJson" IS
  '首次成功批准返回给浏览器的完整响应，用于网络结果不确定时原样重放';
COMMENT ON COLUMN "VideoReviewDecisionCommand"."novelId" IS
  '与请求用户、视频项目共同受组合外键保护的小说归属';
COMMENT ON COLUMN "VideoReviewDecisionCommand"."projectId" IS
  '与场景、来源任务共同受组合外键保护的视频项目归属';

COMMIT;
