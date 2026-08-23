\set ON_ERROR_STOP on

-- 仅供功能尚未启用、视频域完全为空时使用；任何视频数据都会让事务在 DDL 前失败。
\if :{?confirm_production_video_adaptation}
\else
  \echo '缺少确认参数：-v confirm_production_video_adaptation=novelwriter:20260823:rollback-empty-only'
  \quit 3
\endif

SELECT :'confirm_production_video_adaptation' =
  'novelwriter:20260823:rollback-empty-only' AS confirmation_ok \gset
\if :confirmation_ok
\else
  \echo '确认参数不匹配，拒绝执行正式库视频结构反向迁移'
  \quit 3
\endif

BEGIN;

SET LOCAL search_path = public, pg_catalog;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260823:production-video-adaptation:rollback'));

DO $safety$
DECLARE
  target_table TEXT;
  target_column TEXT;
  row_count BIGINT;
BEGIN
  IF current_database() <> 'novelwriter' THEN
    RAISE EXCEPTION '正式视频结构反向迁移只允许在 novelwriter 执行，当前数据库为 %', current_database();
  END IF;

  FOREACH target_table IN ARRAY ARRAY[
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
    IF to_regclass(format('public.%I', target_table)) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM public.%I', target_table) INTO row_count;
      IF row_count <> 0 THEN
        RAISE EXCEPTION '视频表 % 存在 % 行，拒绝 destructive rollback', target_table, row_count;
      END IF;
    END IF;
  END LOOP;

  FOREACH target_column IN ARRAY ARRAY['videoSceneId', 'videoAdaptationId', 'videoAdaptationTaskId']
  LOOP
    IF EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'ReviewArtifact'
        AND column_name = target_column
    ) THEN
      EXECUTE format(
        'SELECT count(*) FROM public.%I WHERE %I IS NOT NULL',
        'ReviewArtifact',
        target_column
      ) INTO row_count;
      IF row_count <> 0 THEN
        RAISE EXCEPTION
          'ReviewArtifact.% 存在 % 个视频关联，拒绝 destructive rollback',
          target_column,
          row_count;
      END IF;
    END IF;
  END LOOP;
END
$safety$;

-- 先解除共同表对视频表的反向外键；其他仅依赖关联列的对象在后续删列时自动移除。
ALTER TABLE "ReviewArtifact"
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_videoSceneId_fkey";
ALTER TABLE "ReviewArtifact"
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_video_scene_novel_fkey";
ALTER TABLE "ReviewArtifact"
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_videoAdaptationId_fkey";
ALTER TABLE "ReviewArtifact"
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_video_adaptation_novel_fkey";
ALTER TABLE "ReviewArtifact"
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_video_adaptation_task_fkey";

-- 同一 DROP 语句列出全部视频表，可以解析它们之间的外键，同时会拒绝未列出的外部依赖。
DROP TABLE IF EXISTS
  "VideoShotPromptVisualReference",
  "VideoShotVisualReferenceBinding",
  "VideoShotVisualReferenceSet",
  "VideoVisualCanonVersion",
  "VideoVisualCanon",
  "VideoAdaptationDecisionCommand",
  "VideoShotPromptHead",
  "VideoShotPromptVersion",
  "VideoShotSourceAnchor",
  "VideoShot",
  "VideoDramaticBeatSourceAnchor",
  "VideoDramaticBeat",
  "VideoCinematicScene",
  "VideoEpisodeBoundary",
  "VideoEpisodePlanVersion",
  "VideoChapterAdaptationHead",
  "VideoShotPlanVersion",
  "VideoAdaptationTask",
  "VideoChapterAdaptation",
  "VideoReviewDecisionCommand",
  "VideoGenerationTask",
  "VideoAssetBinding",
  "VideoAsset",
  "VideoScene",
  "VideoProject";

-- 视频表的反向外键已经移除；删除关联列会一并移除该表内的索引、检查约束和唯一约束。
ALTER TABLE "ReviewArtifact" DROP COLUMN IF EXISTS "videoAdaptationTaskId";
ALTER TABLE "ReviewArtifact" DROP COLUMN IF EXISTS "videoAdaptationId";
ALTER TABLE "ReviewArtifact" DROP COLUMN IF EXISTS "videoSceneId";

ALTER TABLE "Chapter" DROP CONSTRAINT IF EXISTS "Chapter_id_novelId_key";
ALTER TABLE "Novel" DROP CONSTRAINT IF EXISTS "Novel_id_userId_key";

-- PostgreSQL 14 不能原地删除枚举值。只在依赖仍与迁移前基线一致时替换整个枚举类型。
DO $enum_safety$
DECLARE
  enum_column_count INTEGER;
  unexpected_value_count INTEGER;
BEGIN
  IF to_regtype('public."ReviewArtifactKind_20260823_rollback"') IS NOT NULL THEN
    RAISE EXCEPTION '临时枚举 ReviewArtifactKind_20260823_rollback 已存在，拒绝覆盖';
  END IF;

  SELECT count(*) INTO enum_column_count
  FROM pg_attribute AS attribute
  JOIN pg_class AS relation ON relation.oid = attribute.attrelid
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  WHERE attribute.atttypid = 'public."ReviewArtifactKind"'::regtype
    AND attribute.attnum > 0
    AND NOT attribute.attisdropped;

  IF enum_column_count <> 1 OR NOT EXISTS (
    SELECT 1
    FROM pg_attribute AS attribute
    JOIN pg_class AS relation ON relation.oid = attribute.attrelid
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE attribute.atttypid = 'public."ReviewArtifactKind"'::regtype
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped
      AND namespace.nspname = 'public'
      AND relation.relname = 'ReviewArtifact'
      AND attribute.attname = 'kind'
  ) THEN
    RAISE EXCEPTION 'ReviewArtifactKind 依赖范围已变化，拒绝自动重建枚举';
  END IF;

  SELECT count(*) INTO unexpected_value_count
  FROM unnest(enum_range(NULL::"ReviewArtifactKind")) AS enum_value
  WHERE enum_value::text NOT IN (
    'agent_updates',
    'outline_draft',
    'chapter_draft',
    'lore_draft',
    'revision_brief',
    'beat_plan_draft',
    'chapter_content',
    'beat_plan',
    'freeform_markdown',
    'video_scene_plan',
    'video_adaptation_plan'
  );

  IF unexpected_value_count <> 0 THEN
    RAISE EXCEPTION 'ReviewArtifactKind 出现迁移范围外的枚举值，拒绝自动重建枚举';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM "ReviewArtifact"
    WHERE "kind" IN ('video_scene_plan', 'video_adaptation_plan')
  ) THEN
    RAISE EXCEPTION 'ReviewArtifact 仍在使用视频枚举值，拒绝 destructive rollback';
  END IF;
END
$enum_safety$;

CREATE TYPE "ReviewArtifactKind_20260823_rollback" AS ENUM (
  'agent_updates',
  'outline_draft',
  'chapter_draft',
  'lore_draft',
  'revision_brief',
  'beat_plan_draft',
  'chapter_content',
  'beat_plan',
  'freeform_markdown'
);

ALTER TABLE "ReviewArtifact"
ALTER COLUMN "kind" TYPE "ReviewArtifactKind_20260823_rollback"
USING ("kind"::text::"ReviewArtifactKind_20260823_rollback");

DROP TYPE "ReviewArtifactKind";
ALTER TYPE "ReviewArtifactKind_20260823_rollback" RENAME TO "ReviewArtifactKind";

DO $verification$
DECLARE
  target_table TEXT;
  target_column TEXT;
BEGIN
  FOREACH target_table IN ARRAY ARRAY[
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
    IF to_regclass(format('public.%I', target_table)) IS NOT NULL THEN
      RAISE EXCEPTION '正式视频结构反向迁移终检仍存在表 %', target_table;
    END IF;
  END LOOP;

  FOREACH target_column IN ARRAY ARRAY['videoSceneId', 'videoAdaptationId', 'videoAdaptationTaskId']
  LOOP
    IF EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'ReviewArtifact'
        AND column_name = target_column
    ) THEN
      RAISE EXCEPTION '正式视频结构反向迁移终检仍存在 ReviewArtifact.%', target_column;
    END IF;
  END LOOP;
END
$verification$;

COMMIT;
