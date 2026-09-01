\set ON_ERROR_STOP on

BEGIN;

SET LOCAL search_path = pg_catalog, public;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- DDL 回滚仅用于尚无任何新引擎数据的空切换窗口；正式库还需要单独的精确令牌。
-- 生产调用示例：
-- PGOPTIONS='-c inkforge.durable_agent_execution_production=novelwriter:20260831:rollback-empty-v2' psql ... -f 本脚本
DO $safety$
DECLARE
  production_confirmation TEXT :=
    pg_catalog.current_setting('inkforge.durable_agent_execution_production', true);
BEGIN
  IF pg_catalog.current_database() = 'novelwriterdev' THEN
    NULL;
  ELSIF pg_catalog.current_database() = 'novelwriter'
      AND production_confirmation = 'novelwriter:20260831:rollback-empty-v2' THEN
    NULL;
  ELSIF pg_catalog.current_database() = 'novelwriter' THEN
    RAISE EXCEPTION '正式库耐久 Agent 执行 DDL 回滚缺少精确确认令牌';
  ELSE
    RAISE EXCEPTION
      '耐久 Agent 执行 DDL 回滚只允许在 novelwriterdev 或受确认的 novelwriter 执行，当前数据库为 %',
      pg_catalog.current_database();
  END IF;
END
$safety$;

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtext('inkforge:20260831:durable-agent-execution')
);

-- 任何 V2 Run 都意味着迁移已经承载业务事实，禁止通过 DDL 删除；其他新列/新表数据也拒绝静默丢弃。
DO $data_guard$
DECLARE
  has_data BOOLEAN;
  relation_name TEXT;
BEGIN
  IF pg_catalog.to_regclass('public."WorkflowRun"') IS NULL
      OR pg_catalog.to_regclass('public."WorkflowStep"') IS NULL THEN
    RAISE EXCEPTION 'WorkflowRun 或 WorkflowStep 不存在，不能执行具名回滚';
  END IF;

  IF pg_catalog.to_regclass('public."ReviewArtifact"') IS NOT NULL THEN
    SELECT EXISTS (
      SELECT 1
      FROM public."ReviewArtifact" AS artifact
      WHERE artifact."workflowRunId" IS NOT NULL
        AND NOT EXISTS (
          SELECT 1
          FROM public."WorkflowRun" AS run
          WHERE run.id = artifact."workflowRunId"
        )
    ) INTO has_data;
    IF has_data THEN
      RAISE EXCEPTION '检测到失去 WorkflowRun 的孤儿 ReviewArtifact，拒绝耐久 Agent 执行 DDL 回滚';
    END IF;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'WorkflowRun'
      AND column_name = 'engineVersion'
  ) THEN
    EXECUTE 'SELECT EXISTS (
      SELECT 1 FROM public."WorkflowRun" WHERE "engineVersion" = 2
    )' INTO has_data;
    IF has_data THEN
      RAISE EXCEPTION '检测到 engineVersion=2 的 WorkflowRun，拒绝耐久 Agent 执行 DDL 回滚';
    END IF;
  END IF;

  FOREACH relation_name IN ARRAY ARRAY[
    'WorkflowBillingReservation',
    'WorkflowEvaluation',
    'WorkflowEvent',
    'WorkflowEvidenceItem',
    'WorkflowEvidenceBundle'
  ]
  LOOP
    IF pg_catalog.to_regclass(pg_catalog.format('public.%I', relation_name)) IS NOT NULL THEN
      EXECUTE pg_catalog.format('SELECT EXISTS (SELECT 1 FROM public.%I)', relation_name)
      INTO has_data;
      IF has_data THEN
        RAISE EXCEPTION '% 已有数据，拒绝耐久 Agent 执行 DDL 回滚', relation_name;
      END IF;
    END IF;
  END LOOP;

  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'WorkflowRun'
      AND column_name = 'engineVersion'
  ) THEN
    EXECUTE 'SELECT EXISTS (
      SELECT 1
      FROM public."WorkflowRun"
      WHERE "engineVersion" IS NOT NULL
        OR workflow IS NOT NULL
        OR operation IS NOT NULL
        OR "operationCatalogVersion" IS NOT NULL
        OR "writingSessionId" IS NOT NULL
        OR "parentRunId" IS NOT NULL
        OR "idempotencyKey" IS NOT NULL
        OR "requestHash" IS NOT NULL
        OR "targetType" IS NOT NULL
        OR "targetId" IS NOT NULL
        OR "budgetJson" IS NOT NULL
        OR "modelPolicyJson" IS NOT NULL
        OR "currentEvidenceBundleId" IS NOT NULL
        OR "lastEventSequence" IS NOT NULL
        OR revision IS NOT NULL
        OR "cancelRequestId" IS NOT NULL
        OR "cancelRequestedAt" IS NOT NULL
        OR "completedAt" IS NOT NULL
        OR "errorCode" IS NOT NULL
    )' INTO has_data;
    IF has_data THEN
      RAISE EXCEPTION 'WorkflowRun 新增字段已有数据，拒绝耐久 Agent 执行 DDL 回滚';
    END IF;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'WorkflowStep'
      AND column_name = 'ordinal'
  ) THEN
    EXECUTE 'SELECT EXISTS (
      SELECT 1
      FROM public."WorkflowStep"
      WHERE ordinal IS NOT NULL
        OR purpose IS NOT NULL
        OR lane IS NOT NULL
        OR "attemptCount" IS NOT NULL
        OR "nextAttemptAt" IS NOT NULL
        OR "fencingToken" IS NOT NULL
        OR "leaseExpiresAt" IS NOT NULL
        OR "heartbeatAt" IS NOT NULL
        OR "activeJobId" IS NOT NULL
        OR "idempotencyKey" IS NOT NULL
        OR "requestHash" IS NOT NULL
        OR "inputHash" IS NOT NULL
        OR "resultHash" IS NOT NULL
        OR "evidenceBundleId" IS NOT NULL
        OR "artifactId" IS NOT NULL
        OR "artifactRevision" IS NOT NULL
        OR "modelProfile" IS NOT NULL
        OR "modelProfileVersion" IS NOT NULL
        OR "outputSchema" IS NOT NULL
        OR "outputSchemaVersion" IS NOT NULL
        OR "budgetJson" IS NOT NULL
        OR "resolvedModelJson" IS NOT NULL
        OR "usageJson" IS NOT NULL
        OR "lastProgressSequence" IS NOT NULL
        OR "cancelRequestId" IS NOT NULL
        OR "submittedAt" IS NOT NULL
        OR "updatedAt" IS NOT NULL
        OR "completedAt" IS NOT NULL
        OR "errorCode" IS NOT NULL
    )' INTO has_data;
    IF has_data THEN
      RAISE EXCEPTION 'WorkflowStep 新增字段已有数据，拒绝耐久 Agent 执行 DDL 回滚';
    END IF;
  END IF;

  EXECUTE 'SELECT EXISTS (
    SELECT 1 FROM public."WorkflowRun"
    WHERE "novelId" IS NULL OR "chapterId" IS NULL
  )' INTO has_data;
  IF has_data THEN
    RAISE EXCEPTION 'WorkflowRun.novelId/chapterId 已有 NULL，无法恢复旧 NOT NULL 契约';
  END IF;
END
$data_guard$;

ALTER TABLE public."WorkflowRun"
  DROP CONSTRAINT IF EXISTS "WorkflowRun_currentEvidenceBundleId_fkey";

ALTER TABLE public."WorkflowStep"
  DROP CONSTRAINT IF EXISTS "WorkflowStep_evidence_run_fkey",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_artifact_revision_fkey",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_artifact_run_fkey",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_cancel_run_fkey";

ALTER TABLE public."ReviewArtifact"
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_workflow_owner_exclusive_check",
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_workflow_run_novel_fkey",
  DROP CONSTRAINT IF EXISTS "ReviewArtifact_workflowRunId_fkey";

DO $drop_immutable_triggers$
DECLARE
  relation_name TEXT;
  trigger_name TEXT;
BEGIN
  FOREACH relation_name IN ARRAY ARRAY[
    'WorkflowEvidenceBundle',
    'WorkflowEvidenceItem',
    'WorkflowEvent',
    'WorkflowEvaluation'
  ]
  LOOP
    IF pg_catalog.to_regclass(pg_catalog.format('public.%I', relation_name)) IS NOT NULL THEN
      trigger_name := relation_name || '_immutable_trigger';
      EXECUTE pg_catalog.format(
        'DROP TRIGGER IF EXISTS %I ON public.%I',
        trigger_name,
        relation_name
      );
    END IF;
  END LOOP;
END
$drop_immutable_triggers$;

DO $drop_billing_identity_trigger$
BEGIN
  IF pg_catalog.to_regclass('public."WorkflowBillingReservation"') IS NOT NULL THEN
    DROP TRIGGER IF EXISTS "WorkflowBillingReservation_identity_immutable_trigger"
    ON public."WorkflowBillingReservation";
  END IF;
END
$drop_billing_identity_trigger$;

DO $drop_v2_identity_triggers$
BEGIN
  DROP TRIGGER IF EXISTS "WorkflowRun_v2_identity_immutable_trigger"
  ON public."WorkflowRun";
  DROP TRIGGER IF EXISTS "WorkflowStep_v2_identity_immutable_trigger"
  ON public."WorkflowStep";
END
$drop_v2_identity_triggers$;

DROP FUNCTION IF EXISTS public."rejectWorkflowStepV2IdentityMutation"();
DROP FUNCTION IF EXISTS public."rejectWorkflowRunV2IdentityMutation"();

DROP FUNCTION IF EXISTS public."rejectWorkflowBillingIdentityMutation"();

DROP FUNCTION IF EXISTS public."rejectWorkflowAuditMutation"();

DROP TABLE IF EXISTS public."WorkflowBillingReservation";
DROP TABLE IF EXISTS public."WorkflowEvaluation";
DROP TABLE IF EXISTS public."WorkflowEvent";
DROP TABLE IF EXISTS public."WorkflowEvidenceItem";
DROP TABLE IF EXISTS public."WorkflowEvidenceBundle";

DROP INDEX IF EXISTS public."WorkflowRun_v2_user_idempotency_key";
DROP INDEX IF EXISTS public."WorkflowRun_v2_writingSession_foreground_key";
DROP INDEX IF EXISTS public."WorkflowRun_v2_novel_status_created_idx";
DROP INDEX IF EXISTS public."WorkflowRun_v2_parentRunId_idx";
DROP INDEX IF EXISTS public."WorkflowRun_v2_writingSessionId_idx";
DROP INDEX IF EXISTS public."WorkflowRun_v2_target_idx";

DROP INDEX IF EXISTS public."WorkflowStep_id_runId_key";
DROP INDEX IF EXISTS public."WorkflowStep_evaluation_binding_key";
DROP INDEX IF EXISTS public."WorkflowStep_evaluation_context_key";
DROP INDEX IF EXISTS public."WorkflowStep_run_ordinal_key";
DROP INDEX IF EXISTS public."WorkflowStep_run_idempotency_key";
DROP INDEX IF EXISTS public."WorkflowStep_activeJobId_key";
DROP INDEX IF EXISTS public."WorkflowStep_due_idx";
DROP INDEX IF EXISTS public."WorkflowStep_run_ordinal_idx";

ALTER TABLE public."WorkflowRun"
  DROP CONSTRAINT IF EXISTS "WorkflowRun_engineVersion_check",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_v1_scope_check",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_v2_shape_check",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_requestHash_check",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_budgetJson_check",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_modelPolicyJson_check",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_sequence_revision_check",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_terminal_time_check",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_time_order_check",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_cancel_binding_check",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_parent_not_self_check",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_writingSessionId_fkey",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_parentRunId_fkey",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_userId_fkey",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_novel_user_fkey",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_writingSession_scope_fkey",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_parent_user_fkey",
  DROP CONSTRAINT IF EXISTS "WorkflowRun_parent_novel_fkey";

ALTER TABLE public."WorkflowStep"
  DROP CONSTRAINT IF EXISTS "WorkflowStep_v2_shape_check",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_lane_check",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_counter_check",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_hashes_check",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_lease_check",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_artifact_binding_check",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_model_binding_check",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_budgetJson_check",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_resolvedModelJson_check",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_usageJson_check",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_progress_sequence_check",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_resolved_model_binding_check",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_cancel_binding_check",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_terminal_time_check",
  DROP CONSTRAINT IF EXISTS "WorkflowStep_time_order_check";

ALTER TABLE public."WorkflowStep"
  DROP COLUMN IF EXISTS ordinal,
  DROP COLUMN IF EXISTS purpose,
  DROP COLUMN IF EXISTS lane,
  DROP COLUMN IF EXISTS "attemptCount",
  DROP COLUMN IF EXISTS "nextAttemptAt",
  DROP COLUMN IF EXISTS "fencingToken",
  DROP COLUMN IF EXISTS "leaseExpiresAt",
  DROP COLUMN IF EXISTS "heartbeatAt",
  DROP COLUMN IF EXISTS "activeJobId",
  DROP COLUMN IF EXISTS "idempotencyKey",
  DROP COLUMN IF EXISTS "requestHash",
  DROP COLUMN IF EXISTS "inputHash",
  DROP COLUMN IF EXISTS "resultHash",
  DROP COLUMN IF EXISTS "evidenceBundleId",
  DROP COLUMN IF EXISTS "artifactId",
  DROP COLUMN IF EXISTS "artifactRevision",
  DROP COLUMN IF EXISTS "modelProfile",
  DROP COLUMN IF EXISTS "modelProfileVersion",
  DROP COLUMN IF EXISTS "outputSchema",
  DROP COLUMN IF EXISTS "outputSchemaVersion",
  DROP COLUMN IF EXISTS "budgetJson",
  DROP COLUMN IF EXISTS "resolvedModelJson",
  DROP COLUMN IF EXISTS "usageJson",
  DROP COLUMN IF EXISTS "lastProgressSequence",
  DROP COLUMN IF EXISTS "cancelRequestId",
  DROP COLUMN IF EXISTS "submittedAt",
  DROP COLUMN IF EXISTS "updatedAt",
  DROP COLUMN IF EXISTS "completedAt",
  DROP COLUMN IF EXISTS "errorCode";

ALTER TABLE public."WorkflowRun"
  DROP COLUMN IF EXISTS "engineVersion",
  DROP COLUMN IF EXISTS workflow,
  DROP COLUMN IF EXISTS operation,
  DROP COLUMN IF EXISTS "operationCatalogVersion",
  DROP COLUMN IF EXISTS "writingSessionId",
  DROP COLUMN IF EXISTS "parentRunId",
  DROP COLUMN IF EXISTS "idempotencyKey",
  DROP COLUMN IF EXISTS "requestHash",
  DROP COLUMN IF EXISTS "targetType",
  DROP COLUMN IF EXISTS "targetId",
  DROP COLUMN IF EXISTS "budgetJson",
  DROP COLUMN IF EXISTS "modelPolicyJson",
  DROP COLUMN IF EXISTS "currentEvidenceBundleId",
  DROP COLUMN IF EXISTS "lastEventSequence",
  DROP COLUMN IF EXISTS revision,
  DROP COLUMN IF EXISTS "cancelRequestId",
  DROP COLUMN IF EXISTS "cancelRequestedAt",
  DROP COLUMN IF EXISTS "completedAt",
  DROP COLUMN IF EXISTS "errorCode";

DROP INDEX IF EXISTS public."WritingSession_id_novel_chapter_key";
DROP INDEX IF EXISTS public."WorkflowRun_id_userId_key";
DROP INDEX IF EXISTS public."WorkflowRun_id_novelId_key";
DROP INDEX IF EXISTS public."WorkflowRun_id_cancelRequestId_key";
DROP INDEX IF EXISTS public."ReviewArtifact_id_workflowRunId_key";
DROP INDEX IF EXISTS public."ReviewArtifact_id_workflowRunId_novelId_key";

ALTER TABLE public."WorkflowRun"
  ALTER COLUMN "novelId" SET NOT NULL,
  ALTER COLUMN "chapterId" SET NOT NULL;

ALTER TABLE public."ReviewArtifact"
  ADD CONSTRAINT "ReviewArtifact_workflowRunId_fkey"
  FOREIGN KEY ("workflowRunId") REFERENCES public."WorkflowRun"(id)
  ON UPDATE CASCADE ON DELETE SET NULL;

DO $postcondition$
DECLARE
  forbidden RECORD;
BEGIN
  FOR forbidden IN
    SELECT * FROM (VALUES
      ('WorkflowBillingReservation'),
      ('WorkflowEvidenceBundle'),
      ('WorkflowEvidenceItem'),
      ('WorkflowEvent'),
      ('WorkflowEvaluation')
    ) AS expected(table_name)
  LOOP
    IF pg_catalog.to_regclass(pg_catalog.format('public.%I', forbidden.table_name)) IS NOT NULL THEN
      RAISE EXCEPTION '回滚后 % 仍然存在', forbidden.table_name;
    END IF;
  END LOOP;

  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND (
        (
          table_name = 'WorkflowRun'
          AND column_name IN ('engineVersion', 'cancelRequestId')
        )
        OR (
          table_name = 'WorkflowStep'
          AND column_name IN (
            'ordinal', 'resolvedModelJson', 'usageJson',
            'lastProgressSequence', 'cancelRequestId'
          )
        )
      )
  ) THEN
    RAISE EXCEPTION '回滚后 WorkflowRun/WorkflowStep 的 V2 列仍然存在';
  END IF;

  IF pg_catalog.to_regclass('public."WorkflowRun_v2_writingSession_foreground_key"')
      IS NOT NULL
      OR pg_catalog.to_regclass('public."WorkflowRun_id_cancelRequestId_key"')
      IS NOT NULL
      OR pg_catalog.to_regclass('public."WorkflowStep_evaluation_context_key"')
      IS NOT NULL THEN
    RAISE EXCEPTION '回滚后新增 V2 唯一索引仍然存在';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'WorkflowRun'
      AND column_name IN ('novelId', 'chapterId')
      AND is_nullable <> 'NO'
  ) THEN
    RAISE EXCEPTION '回滚后 WorkflowRun.novelId/chapterId 未恢复 NOT NULL';
  END IF;

  IF pg_catalog.to_regprocedure('public."rejectWorkflowAuditMutation"()') IS NOT NULL THEN
    RAISE EXCEPTION '回滚后不可变审计触发器函数仍然存在';
  END IF;

  IF pg_catalog.to_regprocedure('public."rejectWorkflowBillingIdentityMutation"()') IS NOT NULL THEN
    RAISE EXCEPTION '回滚后 BillingReservation 身份保护函数仍然存在';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_constraint AS constraint_row
    WHERE constraint_row.conrelid = 'public."ReviewArtifact"'::pg_catalog.regclass
      AND constraint_row.conname = 'ReviewArtifact_workflowRunId_fkey'
      AND constraint_row.confdeltype = 'n'
  ) THEN
    RAISE EXCEPTION '回滚后 ReviewArtifact workflowRunId FK 未恢复 SET NULL 语义';
  END IF;
END
$postcondition$;

COMMIT;
