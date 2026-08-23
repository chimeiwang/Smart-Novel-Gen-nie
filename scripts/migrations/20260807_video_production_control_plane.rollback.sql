BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 回滚同样只允许服务器端 novelwriterdev 开发库，避免误删任何生产数据。
DO $safety$
BEGIN
  IF current_database() <> 'novelwriterdev' THEN
    RAISE EXCEPTION '视频制作回滚只允许在 novelwriterdev 执行，当前数据库为 %', current_database();
  END IF;
END
$safety$;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260807:video-production-control-plane'));

DROP INDEX IF EXISTS "ReviewArtifact_videoSceneId_status_idx";
ALTER TABLE "ReviewArtifact" DROP COLUMN IF EXISTS "videoSceneId";
DROP TABLE IF EXISTS "VideoGenerationTask";
DROP TABLE IF EXISTS "VideoAssetBinding";
DROP TABLE IF EXISTS "VideoAsset";
DROP TABLE IF EXISTS "VideoScene";
DROP TABLE IF EXISTS "VideoProject";

-- PostgreSQL 枚举值无法安全原地删除；该标签无数据引用时保留，不影响旧代码。
COMMIT;
