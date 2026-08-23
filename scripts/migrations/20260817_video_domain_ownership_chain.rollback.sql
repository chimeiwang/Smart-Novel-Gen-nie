BEGIN;

SET LOCAL search_path = public, pg_catalog;

DO $safety$
BEGIN
  IF current_database() <> 'novelwriterdev' THEN
    RAISE EXCEPTION '视频域归属链回滚只允许在 novelwriterdev 执行，当前数据库为 %', current_database();
  END IF;
END
$safety$;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260817:video-domain-ownership-chain'));

ALTER TABLE "VideoAssetBinding"
DROP CONSTRAINT IF EXISTS "VideoAssetBinding_asset_project_fkey";
ALTER TABLE "VideoAssetBinding"
DROP CONSTRAINT IF EXISTS "VideoAssetBinding_scene_project_fkey";
ALTER TABLE "VideoGenerationTask"
DROP CONSTRAINT IF EXISTS "VideoGenerationTask_scene_project_fkey";
ALTER TABLE "ReviewArtifact"
DROP CONSTRAINT IF EXISTS "ReviewArtifact_video_scene_novel_fkey";
ALTER TABLE "VideoScene"
DROP CONSTRAINT IF EXISTS "VideoScene_chapter_novel_fkey";
ALTER TABLE "VideoScene"
DROP CONSTRAINT IF EXISTS "VideoScene_project_novel_fkey";

ALTER TABLE "VideoAssetBinding"
DROP COLUMN IF EXISTS "projectId";
ALTER TABLE "VideoScene"
DROP COLUMN IF EXISTS "novelId";

ALTER TABLE "VideoAsset"
DROP CONSTRAINT IF EXISTS "VideoAsset_id_projectId_key";
ALTER TABLE "VideoScene"
DROP CONSTRAINT IF EXISTS "VideoScene_id_novelId_key";
ALTER TABLE "Chapter"
DROP CONSTRAINT IF EXISTS "Chapter_id_novelId_key";

COMMIT;
