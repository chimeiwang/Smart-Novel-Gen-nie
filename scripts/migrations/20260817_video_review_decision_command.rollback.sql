BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 回滚同样只允许服务器端 novelwriterdev 开发库，避免误删生产审核事实。
DO $safety$
BEGIN
  IF current_database() <> 'novelwriterdev' THEN
    RAISE EXCEPTION '视频审核决定命令回滚只允许在 novelwriterdev 执行，当前数据库为 %', current_database();
  END IF;
END
$safety$;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260817:video-review-decision-command'));

DROP TABLE IF EXISTS "VideoReviewDecisionCommand";

ALTER TABLE "VideoGenerationTask"
DROP CONSTRAINT IF EXISTS "VideoGenerationTask_id_sceneId_projectId_key";

ALTER TABLE "ReviewArtifact"
DROP CONSTRAINT IF EXISTS "ReviewArtifact_id_videoSceneId_key";

ALTER TABLE "VideoScene"
DROP CONSTRAINT IF EXISTS "VideoScene_id_projectId_key";

ALTER TABLE "VideoProject"
DROP CONSTRAINT IF EXISTS "VideoProject_id_novelId_key";

ALTER TABLE "Novel"
DROP CONSTRAINT IF EXISTS "Novel_id_userId_key";

COMMIT;
