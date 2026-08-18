BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 本迁移只得到服务器端 novelwriterdev 开发库授权，必须拒绝测试库和生产库。
DO $safety$
BEGIN
  IF current_database() <> 'novelwriterdev' THEN
    RAISE EXCEPTION '视频域归属链迁移只允许在 novelwriterdev 执行，当前数据库为 %', current_database();
  END IF;
END
$safety$;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260817:video-domain-ownership-chain'));

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
