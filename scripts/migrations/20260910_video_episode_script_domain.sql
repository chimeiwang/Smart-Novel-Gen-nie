BEGIN;
SET LOCAL search_path = public, pg_catalog;

-- 本次只执行隔离验证，不允许把本脚本直接用于服务器开发库或正式库。
DO $safety$
BEGIN
  IF current_database() NOT IN ('inkforge_video_episode_test', 'inkforge_video_episode_codegen') THEN
    RAISE EXCEPTION '剧集第一阶段迁移仅允许具名隔离数据库，当前为 %', current_database();
  END IF;
END
$safety$;
SELECT pg_advisory_xact_lock(hashtext('inkforge:20260910:video-episode-script'));

ALTER TYPE "ReviewArtifactKind" ADD VALUE IF NOT EXISTS 'video_episode_script';

CREATE TABLE IF NOT EXISTS "VideoEpisode" (
  id TEXT PRIMARY KEY,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  title TEXT NOT NULL CHECK (btrim(title) <> ''),
  ordinal INTEGER NOT NULL CHECK (ordinal > 0),
  "creativeIntent" TEXT NOT NULL DEFAULT '',
  "targetDurationSeconds" INTEGER CHECK ("targetDurationSeconds" > 0),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
  "currentSourceSetVersionId" TEXT,
  "currentScriptVersionId" TEXT,
  "archivedAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoEpisode_project_novel_fkey" FOREIGN KEY ("projectId", "novelId") REFERENCES "VideoProject"(id,"novelId") ON DELETE RESTRICT,
  CONSTRAINT "VideoEpisode_id_project_key" UNIQUE(id,"projectId"),
  CONSTRAINT "VideoEpisode_id_novel_key" UNIQUE(id,"novelId"),
  CONSTRAINT "VideoEpisode_project_ordinal_key" UNIQUE("projectId",ordinal) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS "VideoEpisodeSourceSetVersion" (
  id TEXT PRIMARY KEY,
  "episodeId" TEXT NOT NULL,
  "versionNo" INTEGER NOT NULL CHECK ("versionNo" > 0),
  "basedOnVersionId" TEXT,
  "contentHash" TEXT NOT NULL CHECK ("contentHash" ~ '^[0-9a-f]{64}$'),
  "createdByUserId" TEXT NOT NULL REFERENCES "User"(id) ON DELETE RESTRICT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoEpisodeSourceSetVersion_episode_fkey" FOREIGN KEY ("episodeId") REFERENCES "VideoEpisode"(id) ON DELETE RESTRICT,
  CONSTRAINT "VideoEpisodeSourceSetVersion_id_episode_key" UNIQUE(id,"episodeId"),
  CONSTRAINT "VideoEpisodeSourceSetVersion_episode_version_key" UNIQUE("episodeId","versionNo"),
  CONSTRAINT "VideoEpisodeSourceSetVersion_base_fkey" FOREIGN KEY ("basedOnVersionId","episodeId") REFERENCES "VideoEpisodeSourceSetVersion"(id,"episodeId") ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS "VideoEpisodeSourceSnapshot" (
  id TEXT PRIMARY KEY,
  "sourceSetVersionId" TEXT NOT NULL REFERENCES "VideoEpisodeSourceSetVersion"(id) ON DELETE RESTRICT,
  ordinal INTEGER NOT NULL CHECK (ordinal > 0),
  "chapterId" TEXT NOT NULL,
  "chapterTitle" TEXT NOT NULL,
  "chapterUpdatedAt" TIMESTAMP(3) NOT NULL,
  "sourceText" TEXT NOT NULL,
  "sourceHash" TEXT NOT NULL CHECK ("sourceHash" ~ '^[0-9a-f]{64}$'),
  "rangesJson" TEXT NOT NULL CHECK (jsonb_typeof("rangesJson"::jsonb) = 'array'),
  CONSTRAINT "VideoEpisodeSourceSnapshot_set_ordinal_key" UNIQUE("sourceSetVersionId",ordinal),
  CONSTRAINT "VideoEpisodeSourceSnapshot_id_set_key" UNIQUE(id,"sourceSetVersionId")
);
COMMENT ON COLUMN "VideoEpisodeSourceSnapshot"."chapterId" IS '不可变来源身份，不以实时章节外键使历史快照随删章丢失';

CREATE TABLE IF NOT EXISTS "VideoEpisodeScriptVersion" (
  id TEXT PRIMARY KEY,
  "episodeId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "versionNo" INTEGER NOT NULL CHECK ("versionNo" > 0),
  "basedOnVersionId" TEXT,
  "sourceSetVersionId" TEXT,
  "documentJson" TEXT NOT NULL CHECK (jsonb_typeof("documentJson"::jsonb) = 'object'),
  "contentHash" TEXT NOT NULL CHECK ("contentHash" ~ '^[0-9a-f]{64}$'),
  "reviewArtifactId" TEXT NOT NULL REFERENCES "ReviewArtifact"(id) ON DELETE RESTRICT,
  "approvedByUserId" TEXT NOT NULL REFERENCES "User"(id) ON DELETE RESTRICT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoEpisodeScriptVersion_episode_project_fkey" FOREIGN KEY ("episodeId","projectId") REFERENCES "VideoEpisode"(id,"projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoEpisodeScriptVersion_id_episode_key" UNIQUE(id,"episodeId"),
  CONSTRAINT "VideoEpisodeScriptVersion_id_scope_key" UNIQUE(id,"episodeId","projectId"),
  CONSTRAINT "VideoEpisodeScriptVersion_episode_version_key" UNIQUE("episodeId","versionNo"),
  CONSTRAINT "VideoEpisodeScriptVersion_artifact_key" UNIQUE("reviewArtifactId"),
  CONSTRAINT "VideoEpisodeScriptVersion_source_fkey" FOREIGN KEY ("sourceSetVersionId","episodeId") REFERENCES "VideoEpisodeSourceSetVersion"(id,"episodeId") ON DELETE RESTRICT,
  CONSTRAINT "VideoEpisodeScriptVersion_base_fkey" FOREIGN KEY ("basedOnVersionId","episodeId") REFERENCES "VideoEpisodeScriptVersion"(id,"episodeId") ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS "VideoEpisodeScriptDraft" (
  "episodeId" TEXT PRIMARY KEY REFERENCES "VideoEpisode"(id) ON DELETE RESTRICT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
  "basedOnScriptVersionId" TEXT,
  "sourceSetVersionId" TEXT,
  "documentJson" TEXT NOT NULL CHECK (jsonb_typeof("documentJson"::jsonb) = 'object'),
  "contentHash" TEXT NOT NULL CHECK ("contentHash" ~ '^[0-9a-f]{64}$'),
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoEpisodeScriptDraft_source_fkey" FOREIGN KEY ("sourceSetVersionId","episodeId") REFERENCES "VideoEpisodeSourceSetVersion"(id,"episodeId") ON DELETE RESTRICT,
  CONSTRAINT "VideoEpisodeScriptDraft_base_fkey" FOREIGN KEY ("basedOnScriptVersionId","episodeId") REFERENCES "VideoEpisodeScriptVersion"(id,"episodeId") ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS "VideoEpisodeDependency" (
  id TEXT PRIMARY KEY,
  "projectId" TEXT NOT NULL,
  "consumerEpisodeId" TEXT NOT NULL,
  "consumerScriptVersionId" TEXT NOT NULL,
  "consumerSceneId" TEXT NOT NULL,
  "consumerLineId" TEXT,
  "producerEpisodeId" TEXT NOT NULL,
  "producerScriptVersionId" TEXT NOT NULL,
  "producerStateKey" TEXT NOT NULL,
  "narrativeTime" TEXT NOT NULL,
  description TEXT NOT NULL,
  "sourceHash" TEXT NOT NULL CHECK ("sourceHash" ~ '^[0-9a-f]{64}$'),
  CONSTRAINT "VideoEpisodeDependency_consumer_fkey" FOREIGN KEY ("consumerScriptVersionId","consumerEpisodeId","projectId") REFERENCES "VideoEpisodeScriptVersion"(id,"episodeId","projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoEpisodeDependency_producer_fkey" FOREIGN KEY ("producerScriptVersionId","producerEpisodeId","projectId") REFERENCES "VideoEpisodeScriptVersion"(id,"episodeId","projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoEpisodeDependency_distinct_episode_check" CHECK ("consumerEpisodeId" <> "producerEpisodeId")
);
CREATE INDEX IF NOT EXISTS "VideoEpisodeDependency_producer_idx" ON "VideoEpisodeDependency"("producerScriptVersionId");

CREATE TABLE IF NOT EXISTS "VideoImpactReview" (
  id TEXT PRIMARY KEY,
  "projectId" TEXT NOT NULL,
  "producerEpisodeId" TEXT NOT NULL,
  "beforeScriptVersionId" TEXT,
  "afterScriptVersionId" TEXT NOT NULL,
  "targetEpisodeId" TEXT NOT NULL,
  "targetScriptVersionId" TEXT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','resolved')),
  "reportJson" TEXT NOT NULL CHECK (jsonb_typeof("reportJson"::jsonb) = 'object'),
  "decisionsJson" TEXT NOT NULL DEFAULT '[]' CHECK (jsonb_typeof("decisionsJson"::jsonb) = 'array'),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoImpactReview_before_fkey" FOREIGN KEY ("beforeScriptVersionId","producerEpisodeId","projectId") REFERENCES "VideoEpisodeScriptVersion"(id,"episodeId","projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoImpactReview_after_fkey" FOREIGN KEY ("afterScriptVersionId","producerEpisodeId","projectId") REFERENCES "VideoEpisodeScriptVersion"(id,"episodeId","projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoImpactReview_target_fkey" FOREIGN KEY ("targetEpisodeId","projectId") REFERENCES "VideoEpisode"(id,"projectId") ON DELETE RESTRICT,
  CONSTRAINT "VideoImpactReview_target_version_fkey" FOREIGN KEY ("targetScriptVersionId","targetEpisodeId","projectId") REFERENCES "VideoEpisodeScriptVersion"(id,"episodeId","projectId") ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS "VideoEpisodeCommand" (
  id TEXT PRIMARY KEY,
  "actorUserId" TEXT NOT NULL,
  "clientRequestId" TEXT NOT NULL CHECK (btrim("clientRequestId") <> ''),
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "episodeId" TEXT,
  operation TEXT NOT NULL CHECK (btrim(operation) <> ''),
  "requestHash" TEXT NOT NULL CHECK ("requestHash" ~ '^[0-9a-f]{64}$'),
  "resultJson" TEXT NOT NULL CHECK (jsonb_typeof("resultJson"::jsonb) = 'object'),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoEpisodeCommand_actor_client_key" UNIQUE("actorUserId","clientRequestId"),
  CONSTRAINT "VideoEpisodeCommand_novel_owner_fkey" FOREIGN KEY ("novelId","actorUserId") REFERENCES "Novel"(id,"userId") ON DELETE RESTRICT,
  CONSTRAINT "VideoEpisodeCommand_project_novel_fkey" FOREIGN KEY ("projectId","novelId") REFERENCES "VideoProject"(id,"novelId") ON DELETE RESTRICT,
  CONSTRAINT "VideoEpisodeCommand_episode_project_fkey" FOREIGN KEY ("episodeId","projectId") REFERENCES "VideoEpisode"(id,"projectId") ON DELETE RESTRICT
);

ALTER TABLE "ReviewArtifact" ADD COLUMN IF NOT EXISTS "videoEpisodeId" TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS "ReviewArtifact_id_videoEpisodeId_key" ON "ReviewArtifact"(id,"videoEpisodeId");
CREATE INDEX IF NOT EXISTS "ReviewArtifact_videoEpisodeId_status_idx" ON "ReviewArtifact"("videoEpisodeId",status);
DO $constraints$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ReviewArtifact_video_episode_novel_fkey') THEN
    ALTER TABLE "ReviewArtifact" ADD CONSTRAINT "ReviewArtifact_video_episode_novel_fkey" FOREIGN KEY ("videoEpisodeId","novelId") REFERENCES "VideoEpisode"(id,"novelId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ReviewArtifact_video_episode_target_check') THEN
    ALTER TABLE "ReviewArtifact" ADD CONSTRAINT "ReviewArtifact_video_episode_target_check" CHECK (
      ("videoEpisodeId" IS NULL AND kind::text <> 'video_episode_script') OR
      ("videoEpisodeId" IS NOT NULL AND kind::text = 'video_episode_script' AND "chapterId" IS NULL AND "taskId" IS NULL AND "videoSceneId" IS NULL AND "videoAdaptationId" IS NULL AND "videoAdaptationTaskId" IS NULL)
    );
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisodeScriptVersion_review_episode_fkey') THEN
    ALTER TABLE "VideoEpisodeScriptVersion" ADD CONSTRAINT "VideoEpisodeScriptVersion_review_episode_fkey" FOREIGN KEY ("reviewArtifactId","episodeId") REFERENCES "ReviewArtifact"(id,"videoEpisodeId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisode_current_source_fkey') THEN
    ALTER TABLE "VideoEpisode" ADD CONSTRAINT "VideoEpisode_current_source_fkey" FOREIGN KEY ("currentSourceSetVersionId",id) REFERENCES "VideoEpisodeSourceSetVersion"(id,"episodeId") ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='VideoEpisode_current_script_fkey') THEN
    ALTER TABLE "VideoEpisode" ADD CONSTRAINT "VideoEpisode_current_script_fkey" FOREIGN KEY ("currentScriptVersionId",id) REFERENCES "VideoEpisodeScriptVersion"(id,"episodeId") ON DELETE RESTRICT;
  END IF;
END
$constraints$;

-- 新表由与现有 User 相同的应用角色拥有，避免迁移执行者与应用用户不一致而失去写权限。
DO $ownership$
DECLARE owner_name TEXT; table_name TEXT;
BEGIN
  SELECT pg_get_userbyid(relowner) INTO owner_name FROM pg_class WHERE oid='public."User"'::regclass;
  FOREACH table_name IN ARRAY ARRAY['VideoEpisode','VideoEpisodeSourceSetVersion','VideoEpisodeSourceSnapshot','VideoEpisodeScriptDraft','VideoEpisodeScriptVersion','VideoEpisodeDependency','VideoImpactReview','VideoEpisodeCommand'] LOOP
    EXECUTE format('ALTER TABLE public.%I OWNER TO %I',table_name,owner_name);
  END LOOP;
END
$ownership$;
COMMIT;
