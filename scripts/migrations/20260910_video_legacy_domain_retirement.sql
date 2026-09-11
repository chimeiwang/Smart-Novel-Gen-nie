BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 本迁移只用于专用隔离库演练，不由应用启动或普通部署自动执行，也不代表服务器数据库获准晋升。
-- 只有旧公共/内部运行时与生成投影均已移除、文件清单已保全且零数据证明通过时，才可显式设置令牌。
DO $safety$
BEGIN
  IF current_database() NOT IN (
    'inkforge_video_legacy_retirement_test',
    'inkforge_video_legacy_retirement_codegen'
  ) THEN
    RAISE EXCEPTION '视频旧域退役迁移只允许在专用隔离数据库执行，当前为 %', current_database();
  END IF;

  IF current_setting('inkforge.video_legacy_retirement_confirm', TRUE)
      IS DISTINCT FROM
      'P4_WRITES_REMOVED_HISTORY_EMPTY_READ_RUNTIME_REMOVED_FILES_PRESERVED_SHARED_MEDIA_PRESERVED' THEN
    RAISE EXCEPTION
      '缺少视频旧域退役确认令牌；必须先证明旧写入口/后台调度/只读运行时均已移除、历史为空、文件和共享媒体表已保全';
  END IF;
END
$safety$;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260910:video-legacy-domain-retirement'));

-- 这里只物理删除真正以旧章节改编为根的 25 张专属表。Prompt/Keyframe/Render/Take/Extraction
-- 以及 Edit/Mix/Export 是新 Episode 链正在写入的双作用域表，必须原表保留，只退役其旧分支约束。
DO $shape_and_rows$
DECLARE
  legacy_only_tables CONSTANT TEXT[] := ARRAY[
    'VideoAdaptationDecisionCommand',
    'VideoAdaptationTask',
    'VideoAssetBinding',
    'VideoChapterAdaptation',
    'VideoChapterAdaptationHead',
    'VideoCinematicScene',
    'VideoDramaticBeat',
    'VideoDramaticBeatSourceAnchor',
    'VideoEpisodeBoundary',
    'VideoEpisodeEditHead',
    'VideoEpisodeMixHead',
    'VideoEpisodePlanVersion',
    'VideoGenerationTask',
    'VideoReviewDecisionCommand',
    'VideoScene',
    'VideoShot',
    'VideoShotKeyframeHead',
    'VideoShotPlanVersion',
    'VideoShotPromptHead',
    'VideoShotPromptVisualReference',
    'VideoShotSourceAnchor',
    'VideoShotTakeDecisionCommand',
    'VideoShotTakeHead',
    'VideoShotVisualReferenceBinding',
    'VideoShotVisualReferenceSet'
  ];
  shared_media_tables CONSTANT TEXT[] := ARRAY[
    'VideoShotPromptVersion',
    'VideoShotKeyframeVersion',
    'VideoShotRenderTask',
    'VideoShotTake',
    'VideoTakeFrameExtraction',
    'VideoEpisodeEditVersion',
    'VideoEpisodeEditClip',
    'VideoEpisodeMixVersion',
    'VideoEpisodeAudioClip',
    'VideoEpisodeSubtitleCue',
    'VideoEpisodeExportTask',
    'VideoEpisodeExport'
  ];
  replacement_tables CONSTANT TEXT[] := ARRAY[
    'VideoEpisode',
    'VideoEpisodeCommand',
    'VideoEpisodeSourceSetVersion',
    'VideoEpisodeSourceSnapshot',
    'VideoEpisodeScriptDraft',
    'VideoEpisodeScriptVersion',
    'VideoEpisodeDependency',
    'VideoStoryboardDraft',
    'VideoStoryboardVersion',
    'VideoEpisodeShot',
    'VideoShotVersion',
    'VideoShotLineage',
    'VideoTakeAdoption',
    'VideoProductionBaseline',
    'VideoProductionBaselineShot',
    'VideoProductionEditHead',
    'VideoProductionMixHead',
    'VideoImpactReview'
  ];
  evidence_tables CONSTANT TEXT[] := ARRAY[
    'ReviewArtifact',
    'ReviewArtifactRevision',
    'ReviewArtifactEvaluation',
    'WorkflowRun',
    'WorkflowStep',
    'WorkflowEvidenceBundle',
    'WorkflowEvidenceItem',
    'WorkflowEvent',
    'WorkflowEvaluation',
    'WorkflowBillingReservation',
    'TokenUsage'
  ];
  candidate_table TEXT;
  present_count INTEGER;
  row_count BIGINT;
  nonempty TEXT[] := ARRAY[]::TEXT[];
  missing TEXT[] := ARRAY[]::TEXT[];
  old_column_count INTEGER;
  scope RECORD;
BEGIN
  SELECT count(*)
  INTO present_count
  FROM unnest(legacy_only_tables) AS item(name)
  WHERE to_regclass(format('public.%I', item.name)) IS NOT NULL;

  -- 成功重放只能看到 25 张全在或全无；部分结构代表人工 DDL 或失败脚本留下了不可证明状态。
  IF present_count NOT IN (0, cardinality(legacy_only_tables)) THEN
    RAISE EXCEPTION '25 张旧专属视频表只存在 % 张，拒绝在部分结构上继续退役', present_count;
  END IF;

  FOREACH candidate_table IN ARRAY (replacement_tables || shared_media_tables || evidence_tables) LOOP
    IF to_regclass(format('public.%I', candidate_table)) IS NULL THEN
      missing := array_append(missing, candidate_table);
    END IF;
  END LOOP;
  IF cardinality(missing) <> 0 THEN
    RAISE EXCEPTION '新制作链、共享媒体或耐久证据链尚未完整，缺少表：%', array_to_string(missing, ', ');
  END IF;

  SELECT count(*)
  INTO old_column_count
  FROM information_schema.columns
  WHERE table_schema = 'public'
    AND table_name = 'ReviewArtifact'
    AND column_name IN ('videoSceneId', 'videoAdaptationId', 'videoAdaptationTaskId');
  IF (present_count = cardinality(legacy_only_tables) AND old_column_count <> 3)
      OR (present_count = 0 AND old_column_count <> 0) THEN
    RAISE EXCEPTION
      '旧专属表与 ReviewArtifact 旧归属列状态不一致：tables=%, columns=%',
      present_count,
      old_column_count;
  END IF;

  -- 不迁移、不清空、不猜测。任一旧专属表有一行都表示仍有来源、命令、任务或文件事实。
  IF present_count = cardinality(legacy_only_tables) THEN
    FOREACH candidate_table IN ARRAY legacy_only_tables LOOP
      EXECUTE format('SELECT count(*) FROM public.%I', candidate_table) INTO row_count;
      IF row_count <> 0 THEN
        nonempty := array_append(nonempty, format('%s=%s', candidate_table, row_count));
      END IF;
    END LOOP;
  END IF;

  -- 双作用域表只能证明旧分支为空，绝不能把新 Episode 行计入“旧数据”后删除整表。
  FOR scope IN
    SELECT * FROM (VALUES
      ('VideoShotPromptVersion', '"shotId" IS NOT NULL OR "shotPlanVersionId" IS NOT NULL OR "sourceTaskId" IS NOT NULL'),
      ('VideoShotKeyframeVersion', '"adaptationId" IS NOT NULL OR "shotId" IS NOT NULL OR "shotPlanVersionId" IS NOT NULL'),
      ('VideoShotRenderTask', '"adaptationId" IS NOT NULL OR "shotId" IS NOT NULL OR "shotPlanVersionId" IS NOT NULL'),
      ('VideoShotTake', '"adaptationId" IS NOT NULL OR "shotId" IS NOT NULL OR "shotPlanVersionId" IS NOT NULL'),
      ('VideoTakeFrameExtraction', '"adaptationId" IS NOT NULL OR "shotId" IS NOT NULL'),
      ('VideoEpisodeEditVersion', '"adaptationId" IS NOT NULL OR "episodePlanVersionId" IS NOT NULL OR "shotPlanVersionId" IS NOT NULL OR "episodeNo" IS NOT NULL'),
      ('VideoEpisodeEditClip', '"shotId" IS NOT NULL OR "shotPlanVersionId" IS NOT NULL'),
      ('VideoEpisodeMixVersion', '"adaptationId" IS NOT NULL OR "episodePlanVersionId" IS NOT NULL OR "shotPlanVersionId" IS NOT NULL OR "episodeNo" IS NOT NULL'),
      ('VideoEpisodeAudioClip', '"shotId" IS NOT NULL OR "shotPlanVersionId" IS NOT NULL'),
      ('VideoEpisodeSubtitleCue', '"shotId" IS NOT NULL OR "shotPlanVersionId" IS NOT NULL'),
      ('VideoEpisodeExportTask', '"adaptationId" IS NOT NULL OR "episodePlanVersionId" IS NOT NULL OR "shotPlanVersionId" IS NOT NULL OR "episodeNo" IS NOT NULL'),
      ('VideoEpisodeExport', '"adaptationId" IS NOT NULL OR "episodePlanVersionId" IS NOT NULL OR "episodeNo" IS NOT NULL')
    ) AS legacy_scope(table_name, predicate)
  LOOP
    EXECUTE format(
      'SELECT count(*) FROM public.%I WHERE %s',
      scope.table_name,
      scope.predicate
    ) INTO row_count;
    IF row_count <> 0 THEN
      nonempty := array_append(nonempty, format('%s[legacy]=%s', scope.table_name, row_count));
    END IF;
  END LOOP;

  IF cardinality(nonempty) <> 0 THEN
    RAISE EXCEPTION '发现需要保全的旧视频数据，停止物理退役：%', array_to_string(nonempty, ', ');
  END IF;
END
$shape_and_rows$;

-- ReviewArtifact、Revision/Evaluation 以及 V2 Run/Evidence/Event/Billing 都是共享证据。
-- 数据库没有覆盖全部逻辑来源的外键，因此在任何 DDL 前逐类证明旧引用为零。
DO $shared_evidence$
DECLARE
  preserved_count BIGINT;
  old_column_count INTEGER;
BEGIN
  SELECT count(*)
  INTO old_column_count
  FROM information_schema.columns
  WHERE table_schema = 'public'
    AND table_name = 'ReviewArtifact'
    AND column_name IN ('videoSceneId', 'videoAdaptationId', 'videoAdaptationTaskId');

  IF old_column_count = 3 THEN
    EXECUTE $query$
      SELECT count(*)
      FROM "ReviewArtifact"
      WHERE "videoSceneId" IS NOT NULL
         OR "videoAdaptationId" IS NOT NULL
         OR "videoAdaptationTaskId" IS NOT NULL
         OR kind::text IN ('video_scene_plan', 'video_adaptation_plan')
    $query$
    INTO preserved_count;
  ELSE
    SELECT count(*)
    INTO preserved_count
    FROM "ReviewArtifact"
    WHERE kind::text IN ('video_scene_plan', 'video_adaptation_plan');
  END IF;
  IF preserved_count <> 0 THEN
    RAISE EXCEPTION 'ReviewArtifact 中有 % 条旧视频审核或来源，停止物理退役', preserved_count;
  END IF;

  SELECT count(*)
  INTO preserved_count
  FROM "WorkflowRun"
  WHERE "sourceType" = 'video_adaptation_task_v2'
     OR "targetType" IN ('video_adaptation', 'video_shot_prompt')
     OR operation IN ('chapter_cinematic_adaptation_v2', 'chapter_shot_prompt_v2');
  IF preserved_count <> 0 THEN
    RAISE EXCEPTION 'WorkflowRun 中有 % 条旧章节视频 Run，停止物理退役并保留全部下游证据', preserved_count;
  END IF;

  SELECT count(*)
  INTO preserved_count
  FROM "WorkflowEvidenceItem"
  WHERE "resourceType" = 'video_task_context';
  IF preserved_count <> 0 THEN
    RAISE EXCEPTION 'WorkflowEvidenceItem 中有 % 条旧视频冻结上下文，停止物理退役', preserved_count;
  END IF;

  IF to_regclass('public."VideoAdaptationTask"') IS NOT NULL THEN
    SELECT count(*)
    INTO preserved_count
    FROM "TokenUsage" AS usage
    JOIN "VideoAdaptationTask" AS task
      ON usage."taskId" = task.id OR usage."runId" IN (
        SELECT run.id
        FROM "WorkflowRun" AS run
        WHERE run."sourceType" = 'video_adaptation_task_v2'
          AND run."sourceId" = task.id
      );
    IF preserved_count <> 0 THEN
      RAISE EXCEPTION 'TokenUsage 中有 % 条旧视频任务用量来源，停止物理退役', preserved_count;
    END IF;
  END IF;
END
$shared_evidence$;

-- 先具名解除共享表指向旧专属父表的外键；所有新 Episode/Baseline/Asset 外键原样保留。
ALTER TABLE "ReviewArtifact"
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_videoSceneId_fkey",
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_video_scene_novel_fkey",
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_videoAdaptationId_fkey",
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_video_adaptation_novel_fkey",
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_video_adaptation_task_fkey",
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_video_target_exclusive_check",
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_video_adaptation_kind_check",
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_video_episode_target_check";

ALTER TABLE "VideoShotPromptVersion"
  DROP CONSTRAINT IF EXISTS "VideoShotPromptVersion_shot_plan_fkey",
  DROP CONSTRAINT IF EXISTS "VideoShotPromptVersion_sourceTaskId_fkey",
  DROP CONSTRAINT IF EXISTS "VideoShotPromptVersion_source_task_plan_fkey";
ALTER TABLE "VideoShotKeyframeVersion"
  DROP CONSTRAINT IF EXISTS "VideoShotKeyframeVersion_adaptation_novel_fkey",
  DROP CONSTRAINT IF EXISTS "VideoShotKeyframeVersion_adaptation_project_fkey",
  DROP CONSTRAINT IF EXISTS "VideoShotKeyframeVersion_plan_adaptation_fkey",
  DROP CONSTRAINT IF EXISTS "VideoShotKeyframeVersion_shot_plan_fkey";
ALTER TABLE "VideoShotRenderTask"
  DROP CONSTRAINT IF EXISTS "VideoShotRenderTask_adaptation_novel_fkey",
  DROP CONSTRAINT IF EXISTS "VideoShotRenderTask_adaptation_project_fkey",
  DROP CONSTRAINT IF EXISTS "VideoShotRenderTask_plan_adaptation_fkey",
  DROP CONSTRAINT IF EXISTS "VideoShotRenderTask_shot_plan_fkey";
ALTER TABLE "VideoTakeFrameExtraction"
  DROP CONSTRAINT IF EXISTS "VideoTakeFrameExtraction_adaptation_novel_fkey",
  DROP CONSTRAINT IF EXISTS "VideoTakeFrameExtraction_adaptation_project_fkey";
ALTER TABLE "VideoEpisodeEditVersion"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeEditVersion_adaptation_novel_fkey",
  DROP CONSTRAINT IF EXISTS "VideoEpisodeEditVersion_adaptation_project_fkey",
  DROP CONSTRAINT IF EXISTS "VideoEpisodeEditVersion_episode_plan_fkey";
ALTER TABLE "VideoEpisodeEditClip"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeEditClip_shot_plan_fkey";
ALTER TABLE "VideoEpisodeMixVersion"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeMixVersion_adaptation_novel_fkey",
  DROP CONSTRAINT IF EXISTS "VideoEpisodeMixVersion_adaptation_project_fkey",
  DROP CONSTRAINT IF EXISTS "VideoEpisodeMixVersion_episode_plan_fkey";
ALTER TABLE "VideoEpisodeAudioClip"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeAudioClip_shot_plan_fkey";
ALTER TABLE "VideoEpisodeSubtitleCue"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeSubtitleCue_shot_plan_fkey";
ALTER TABLE "VideoEpisodeExportTask"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeExportTask_adaptation_novel_fkey",
  DROP CONSTRAINT IF EXISTS "VideoEpisodeExportTask_adaptation_project_fkey",
  DROP CONSTRAINT IF EXISTS "VideoEpisodeExportTask_episode_plan_fkey";

-- 子表先于父表；每个 DROP 都是 RESTRICT。漏盘的依赖会使整个事务失败并回滚。
DROP TABLE IF EXISTS "VideoAdaptationDecisionCommand" RESTRICT;
DROP TABLE IF EXISTS "VideoAssetBinding" RESTRICT;
DROP TABLE IF EXISTS "VideoChapterAdaptationHead" RESTRICT;
DROP TABLE IF EXISTS "VideoDramaticBeatSourceAnchor" RESTRICT;
DROP TABLE IF EXISTS "VideoEpisodeBoundary" RESTRICT;
DROP TABLE IF EXISTS "VideoEpisodeEditHead" RESTRICT;
DROP TABLE IF EXISTS "VideoEpisodeMixHead" RESTRICT;
DROP TABLE IF EXISTS "VideoReviewDecisionCommand" RESTRICT;
DROP TABLE IF EXISTS "VideoGenerationTask" RESTRICT;
DROP TABLE IF EXISTS "VideoScene" RESTRICT;
DROP TABLE IF EXISTS "VideoShotKeyframeHead" RESTRICT;
DROP TABLE IF EXISTS "VideoShotPromptHead" RESTRICT;
DROP TABLE IF EXISTS "VideoShotPromptVisualReference" RESTRICT;
DROP TABLE IF EXISTS "VideoShotSourceAnchor" RESTRICT;
DROP TABLE IF EXISTS "VideoShotTakeDecisionCommand" RESTRICT;
DROP TABLE IF EXISTS "VideoShotTakeHead" RESTRICT;
DROP TABLE IF EXISTS "VideoShotVisualReferenceBinding" RESTRICT;
DROP TABLE IF EXISTS "VideoShotVisualReferenceSet" RESTRICT;
DROP TABLE IF EXISTS "VideoEpisodePlanVersion" RESTRICT;
DROP TABLE IF EXISTS "VideoShot" RESTRICT;
DROP TABLE IF EXISTS "VideoDramaticBeat" RESTRICT;
DROP TABLE IF EXISTS "VideoCinematicScene" RESTRICT;

-- Task 与旧 ShotPlan 互相冻结来源，必须具名拆环，禁止用 CASCADE 隐式删除。
DO $cycle_constraints$
BEGIN
  IF to_regclass('public."VideoAdaptationTask"') IS NOT NULL THEN
    ALTER TABLE "VideoAdaptationTask"
      DROP CONSTRAINT IF EXISTS "VideoAdaptationTask_base_plan_fkey";
  END IF;
  IF to_regclass('public."VideoShotPlanVersion"') IS NOT NULL THEN
    ALTER TABLE "VideoShotPlanVersion"
      DROP CONSTRAINT IF EXISTS "VideoShotPlanVersion_source_task_fkey";
  END IF;
END
$cycle_constraints$;
DROP TABLE IF EXISTS "VideoAdaptationTask" RESTRICT;
DROP TABLE IF EXISTS "VideoShotPlanVersion" RESTRICT;
DROP TABLE IF EXISTS "VideoChapterAdaptation" RESTRICT;

-- 旧专属表已不存在后，解除双作用域表内部仅服务旧分支的自引用/复合引用和唯一约束。
ALTER TABLE "VideoShotPromptVersion"
  DROP CONSTRAINT IF EXISTS "VideoShotPromptVersion_based_on_fkey",
  DROP CONSTRAINT IF EXISTS "VideoShotPromptVersion_shot_version_key";
ALTER TABLE "VideoShotKeyframeVersion"
  DROP CONSTRAINT IF EXISTS "VideoShotKeyframeVersion_based_on_fkey",
  DROP CONSTRAINT IF EXISTS "VideoShotKeyframeVersion_source_take_fkey",
  DROP CONSTRAINT IF EXISTS "VideoShotKeyframeVersion_id_shot_role_key";
ALTER TABLE "VideoShotRenderTask"
  DROP CONSTRAINT IF EXISTS "VideoShotRenderTask_prompt_scope_fkey",
  DROP CONSTRAINT IF EXISTS "VideoShotRenderTask_retry_shot_fkey",
  DROP CONSTRAINT IF EXISTS "VideoShotRenderTask_id_shot_key";
ALTER TABLE "VideoShotTake"
  DROP CONSTRAINT IF EXISTS "VideoShotTake_task_scope_fkey";
ALTER TABLE "VideoTakeFrameExtraction"
  DROP CONSTRAINT IF EXISTS "VideoTakeFrameExtraction_take_scope_fkey";
ALTER TABLE "VideoEpisodeEditClip"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeEditClip_edit_plan_fkey",
  DROP CONSTRAINT IF EXISTS "VideoEpisodeEditClip_take_scope_fkey";
ALTER TABLE "VideoEpisodeMixVersion"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeMixVersion_based_on_fkey",
  DROP CONSTRAINT IF EXISTS "VideoEpisodeMixVersion_edit_version_fkey";
ALTER TABLE "VideoEpisodeAudioClip"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeAudioClip_mix_project_fkey";
ALTER TABLE "VideoEpisodeSubtitleCue"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeSubtitleCue_mix_plan_fkey";
ALTER TABLE "VideoEpisodeExportTask"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeExportTask_edit_version_fkey",
  DROP CONSTRAINT IF EXISTS "VideoEpisodeExportTask_mix_version_fkey",
  DROP CONSTRAINT IF EXISTS "VideoEpisodeExportTask_retry_scope_fkey";
ALTER TABLE "VideoEpisodeExport"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeExport_edit_version_fkey",
  DROP CONSTRAINT IF EXISTS "VideoEpisodeExport_mix_version_fkey",
  DROP CONSTRAINT IF EXISTS "VideoEpisodeExport_task_scope_fkey";
ALTER TABLE "VideoEpisodeExportTask"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeExportTask_id_scope_key";
ALTER TABLE "VideoEpisodeEditVersion"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeEditVersion_based_on_fkey",
  DROP CONSTRAINT IF EXISTS "VideoEpisodeEditVersion_id_episode_key";
ALTER TABLE "VideoEpisodeMixVersion"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeMixVersion_id_episode_key";

DROP INDEX IF EXISTS "VideoShotPromptVersion_id_shotId_key" RESTRICT;
DROP INDEX IF EXISTS "VideoShotPromptVersion_id_shot_plan_key" RESTRICT;
DROP INDEX IF EXISTS "VideoShotKeyframeVersion_shot_created_idx" RESTRICT;
DROP INDEX IF EXISTS "VideoShotKeyframeVersion_shot_role_version_key" RESTRICT;
DROP INDEX IF EXISTS "VideoShotRenderTask_active_shot_key" RESTRICT;
DROP INDEX IF EXISTS "VideoShotRenderTask_id_scope_key" RESTRICT;
DROP INDEX IF EXISTS "VideoShotRenderTask_shot_client_request_key" RESTRICT;
DROP INDEX IF EXISTS "VideoShotRenderTask_shot_created_idx" RESTRICT;
DROP INDEX IF EXISTS "VideoShotTake_id_shot_adaptation_key" RESTRICT;
DROP INDEX IF EXISTS "VideoShotTake_id_shot_plan_key" RESTRICT;
DROP INDEX IF EXISTS "VideoShotTake_shot_created_idx" RESTRICT;
DROP INDEX IF EXISTS "VideoShotTake_shot_take_no_key" RESTRICT;
DROP INDEX IF EXISTS "VideoEpisodeEditVersion_episode_version_key" RESTRICT;
DROP INDEX IF EXISTS "VideoEpisodeEditVersion_id_plan_key" RESTRICT;
DROP INDEX IF EXISTS "VideoEpisodeEditClip_version_shot_key" RESTRICT;
DROP INDEX IF EXISTS "VideoEpisodeMixVersion_episode_version_key" RESTRICT;
DROP INDEX IF EXISTS "VideoEpisodeMixVersion_id_plan_key" RESTRICT;
DROP INDEX IF EXISTS "VideoEpisodeMixVersion_id_project_key" RESTRICT;
DROP INDEX IF EXISTS "VideoEpisodeMixVersion_id_project_plan_key" RESTRICT;
DROP INDEX IF EXISTS "VideoEpisodeExportTask_active_episode_key" RESTRICT;
DROP INDEX IF EXISTS "VideoEpisodeExport_episode_created_idx" RESTRICT;
DROP INDEX IF EXISTS "VideoEpisodeExport_episode_version_key" RESTRICT;

-- 保留双作用域表及旧列墓碑，但 CHECK 收紧为新 Episode 分支；当前新仓储显式写 NULL 的旧列仍兼容。
ALTER TABLE "VideoShotPromptVersion"
  DROP CONSTRAINT IF EXISTS "VideoShotPromptVersion_scope_branch_check",
  ADD CONSTRAINT "VideoShotPromptVersion_scope_branch_check" CHECK (
    "shotId" IS NULL AND "shotPlanVersionId" IS NULL AND "sourceTaskId" IS NULL
    AND "videoEpisodeId" IS NOT NULL AND "episodeShotId" IS NOT NULL
    AND "episodeShotVersionId" IS NOT NULL AND "productionBaselineId" IS NOT NULL
  );
ALTER TABLE "VideoShotKeyframeVersion"
  DROP CONSTRAINT IF EXISTS "VideoShotKeyframeVersion_scope_branch_check",
  ADD CONSTRAINT "VideoShotKeyframeVersion_scope_branch_check" CHECK (
    "adaptationId" IS NULL AND "shotId" IS NULL AND "shotPlanVersionId" IS NULL
    AND "videoEpisodeId" IS NOT NULL AND "episodeShotId" IS NOT NULL
    AND "episodeShotVersionId" IS NOT NULL AND "productionBaselineId" IS NOT NULL
  );
ALTER TABLE "VideoShotRenderTask"
  DROP CONSTRAINT IF EXISTS "VideoShotRenderTask_scope_branch_check",
  ADD CONSTRAINT "VideoShotRenderTask_scope_branch_check" CHECK (
    "adaptationId" IS NULL AND "shotId" IS NULL AND "shotPlanVersionId" IS NULL
    AND "promptVersionId" IS NOT NULL AND "videoEpisodeId" IS NOT NULL
    AND "episodeShotId" IS NOT NULL AND "episodeShotVersionId" IS NOT NULL
    AND "productionBaselineId" IS NOT NULL
  );
ALTER TABLE "VideoShotTake"
  DROP CONSTRAINT IF EXISTS "VideoShotTake_scope_branch_check",
  ADD CONSTRAINT "VideoShotTake_scope_branch_check" CHECK (
    "adaptationId" IS NULL AND "shotId" IS NULL AND "shotPlanVersionId" IS NULL
    AND "promptVersionId" IS NOT NULL AND "videoEpisodeId" IS NOT NULL
    AND "episodeShotId" IS NOT NULL AND "episodeShotVersionId" IS NOT NULL
    AND "productionBaselineId" IS NOT NULL
  );
ALTER TABLE "VideoTakeFrameExtraction"
  DROP CONSTRAINT IF EXISTS "VideoTakeFrameExtraction_scope_branch_check",
  ADD CONSTRAINT "VideoTakeFrameExtraction_scope_branch_check" CHECK (
    "adaptationId" IS NULL AND "shotId" IS NULL
    AND "videoEpisodeId" IS NOT NULL AND "episodeShotId" IS NOT NULL
    AND "episodeShotVersionId" IS NOT NULL AND "productionBaselineId" IS NOT NULL
  );
ALTER TABLE "VideoEpisodeEditVersion"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeEditVersion_scope_branch_check",
  ADD CONSTRAINT "VideoEpisodeEditVersion_scope_branch_check" CHECK (
    "adaptationId" IS NULL AND "episodePlanVersionId" IS NULL
    AND "shotPlanVersionId" IS NULL AND "episodeNo" IS NULL
    AND "videoEpisodeId" IS NOT NULL AND "productionBaselineId" IS NOT NULL
  );
ALTER TABLE "VideoEpisodeEditClip"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeEditClip_scope_branch_check",
  ADD CONSTRAINT "VideoEpisodeEditClip_scope_branch_check" CHECK (
    "shotId" IS NULL AND "shotPlanVersionId" IS NULL AND "clipId" IS NOT NULL
    AND "videoEpisodeId" IS NOT NULL AND "productionBaselineId" IS NOT NULL
    AND "episodeShotId" IS NOT NULL AND "episodeShotVersionId" IS NOT NULL
    AND "takeId" IS NOT NULL AND "adoptionId" IS NOT NULL
  );
ALTER TABLE "VideoEpisodeMixVersion"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeMixVersion_scope_branch_check",
  ADD CONSTRAINT "VideoEpisodeMixVersion_scope_branch_check" CHECK (
    "adaptationId" IS NULL AND "episodePlanVersionId" IS NULL
    AND "shotPlanVersionId" IS NULL AND "episodeNo" IS NULL
    AND "videoEpisodeId" IS NOT NULL AND "productionBaselineId" IS NOT NULL
  );
ALTER TABLE "VideoEpisodeAudioClip"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeAudioClip_scope_branch_check",
  ADD CONSTRAINT "VideoEpisodeAudioClip_scope_branch_check" CHECK (
    "shotId" IS NULL AND "shotPlanVersionId" IS NULL
    AND "videoEpisodeId" IS NOT NULL AND "productionBaselineId" IS NOT NULL
    AND (("episodeShotId" IS NULL AND "episodeShotVersionId" IS NULL)
      OR ("episodeShotId" IS NOT NULL AND "episodeShotVersionId" IS NOT NULL))
  );
ALTER TABLE "VideoEpisodeSubtitleCue"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeSubtitleCue_scope_branch_check",
  ADD CONSTRAINT "VideoEpisodeSubtitleCue_scope_branch_check" CHECK (
    "shotId" IS NULL AND "shotPlanVersionId" IS NULL
    AND "videoEpisodeId" IS NOT NULL AND "productionBaselineId" IS NOT NULL
    AND "episodeShotId" IS NOT NULL AND "episodeShotVersionId" IS NOT NULL
    AND "scriptLineId" IS NOT NULL
  );
ALTER TABLE "VideoEpisodeExportTask"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeExportTask_scope_branch_check",
  ADD CONSTRAINT "VideoEpisodeExportTask_scope_branch_check" CHECK (
    "adaptationId" IS NULL AND "episodePlanVersionId" IS NULL
    AND "shotPlanVersionId" IS NULL AND "episodeNo" IS NULL
    AND "videoEpisodeId" IS NOT NULL AND "productionBaselineId" IS NOT NULL
  );
ALTER TABLE "VideoEpisodeExport"
  DROP CONSTRAINT IF EXISTS "VideoEpisodeExport_scope_branch_check",
  ADD CONSTRAINT "VideoEpisodeExport_scope_branch_check" CHECK (
    "adaptationId" IS NULL AND "episodePlanVersionId" IS NULL AND "episodeNo" IS NULL
    AND "videoEpisodeId" IS NOT NULL AND "productionBaselineId" IS NOT NULL
  );

ALTER TABLE "ReviewArtifact"
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_id_videoSceneId_key";
DROP INDEX IF EXISTS "ReviewArtifact_id_videoAdaptationId_key" RESTRICT;
DROP INDEX IF EXISTS "ReviewArtifact_videoSceneId_status_idx" RESTRICT;
DROP INDEX IF EXISTS "ReviewArtifact_videoAdaptationId_status_idx" RESTRICT;

ALTER TABLE "ReviewArtifact"
  DROP COLUMN IF EXISTS "videoSceneId" RESTRICT,
  DROP COLUMN IF EXISTS "videoAdaptationTaskId" RESTRICT,
  DROP COLUMN IF EXISTS "videoAdaptationId" RESTRICT;

-- 旧 enum 标签保留为不可再写的墓碑值，避免重建共享 enum；新 Episode 审核归属继续排他。
ALTER TABLE "ReviewArtifact"
  ADD CONSTRAINT "ReviewArtifact_video_episode_target_check" CHECK (
    ("videoEpisodeId" IS NULL
      AND kind::text NOT IN (
        'video_scene_plan', 'video_adaptation_plan',
        'video_episode_script', 'video_episode_storyboard'
      ))
    OR
    ("videoEpisodeId" IS NOT NULL
      AND kind::text IN ('video_episode_script', 'video_episode_storyboard')
      AND "chapterId" IS NULL
      AND "taskId" IS NULL)
  );

COMMIT;
