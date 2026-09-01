\set ON_ERROR_STOP on

BEGIN;

SET LOCAL search_path = pg_catalog, public;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- 开发库可直接执行；正式库必须提供精确确认令牌，其他数据库一律拒绝。
-- 生产调用示例：
-- PGOPTIONS='-c inkforge.durable_agent_execution_production=novelwriter:20260831:apply' psql ... -f 本脚本
DO $safety$
DECLARE
  production_confirmation TEXT :=
    pg_catalog.current_setting('inkforge.durable_agent_execution_production', true);
BEGIN
  IF pg_catalog.current_database() = 'novelwriterdev' THEN
    NULL;
  ELSIF pg_catalog.current_database() = 'novelwriter'
      AND production_confirmation = 'novelwriter:20260831:apply' THEN
    NULL;
  ELSIF pg_catalog.current_database() = 'novelwriter' THEN
    RAISE EXCEPTION '正式库耐久 Agent 执行迁移缺少精确确认令牌';
  ELSE
    RAISE EXCEPTION
      '耐久 Agent 执行迁移只允许在 novelwriterdev 或受确认的 novelwriter 执行，当前数据库为 %',
      pg_catalog.current_database();
  END IF;
END
$safety$;

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtext('inkforge:20260831:durable-agent-execution')
);

DO $preflight$
BEGIN
  IF to_regclass('public."WorkflowRun"') IS NULL
      OR to_regclass('public."WorkflowStep"') IS NULL
      OR to_regclass('public."WritingSession"') IS NULL
      OR to_regclass('public."ReviewArtifact"') IS NULL
      OR to_regclass('public."ReviewArtifactRevision"') IS NULL THEN
    RAISE EXCEPTION '耐久 Agent 执行迁移所需的现有工作流或审核表不存在';
  END IF;
END
$preflight$;

ALTER TABLE public."WorkflowRun"
  ADD COLUMN IF NOT EXISTS "engineVersion" INTEGER,
  ADD COLUMN IF NOT EXISTS workflow TEXT,
  ADD COLUMN IF NOT EXISTS operation TEXT,
  ADD COLUMN IF NOT EXISTS "operationCatalogVersion" TEXT,
  ADD COLUMN IF NOT EXISTS "writingSessionId" TEXT,
  ADD COLUMN IF NOT EXISTS "parentRunId" TEXT,
  ADD COLUMN IF NOT EXISTS "idempotencyKey" TEXT,
  ADD COLUMN IF NOT EXISTS "requestHash" TEXT,
  ADD COLUMN IF NOT EXISTS "targetType" TEXT,
  ADD COLUMN IF NOT EXISTS "targetId" TEXT,
  ADD COLUMN IF NOT EXISTS "budgetJson" TEXT,
  ADD COLUMN IF NOT EXISTS "modelPolicyJson" TEXT,
  ADD COLUMN IF NOT EXISTS "currentEvidenceBundleId" TEXT,
  ADD COLUMN IF NOT EXISTS "lastEventSequence" BIGINT,
  ADD COLUMN IF NOT EXISTS revision INTEGER,
  ADD COLUMN IF NOT EXISTS "cancelRequestId" TEXT,
  ADD COLUMN IF NOT EXISTS "cancelRequestedAt" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "completedAt" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "errorCode" TEXT;

-- V1 的小说/章节范围保持必填；只让 V2 的用户级或非章节目标可以为空。
ALTER TABLE public."WorkflowRun"
  ALTER COLUMN "novelId" DROP NOT NULL,
  ALTER COLUMN "chapterId" DROP NOT NULL;

ALTER TABLE public."WorkflowStep"
  ADD COLUMN IF NOT EXISTS ordinal INTEGER,
  ADD COLUMN IF NOT EXISTS purpose TEXT,
  ADD COLUMN IF NOT EXISTS lane TEXT,
  ADD COLUMN IF NOT EXISTS "attemptCount" INTEGER,
  ADD COLUMN IF NOT EXISTS "nextAttemptAt" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "fencingToken" BIGINT,
  ADD COLUMN IF NOT EXISTS "leaseExpiresAt" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "heartbeatAt" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "activeJobId" TEXT,
  ADD COLUMN IF NOT EXISTS "idempotencyKey" TEXT,
  ADD COLUMN IF NOT EXISTS "requestHash" TEXT,
  ADD COLUMN IF NOT EXISTS "inputHash" TEXT,
  ADD COLUMN IF NOT EXISTS "resultHash" TEXT,
  ADD COLUMN IF NOT EXISTS "evidenceBundleId" TEXT,
  ADD COLUMN IF NOT EXISTS "artifactId" TEXT,
  ADD COLUMN IF NOT EXISTS "artifactRevision" INTEGER,
  ADD COLUMN IF NOT EXISTS "modelProfile" TEXT,
  ADD COLUMN IF NOT EXISTS "modelProfileVersion" TEXT,
  ADD COLUMN IF NOT EXISTS "outputSchema" TEXT,
  ADD COLUMN IF NOT EXISTS "outputSchemaVersion" TEXT,
  ADD COLUMN IF NOT EXISTS "budgetJson" TEXT,
  ADD COLUMN IF NOT EXISTS "resolvedModelJson" TEXT,
  ADD COLUMN IF NOT EXISTS "usageJson" TEXT,
  ADD COLUMN IF NOT EXISTS "lastProgressSequence" BIGINT,
  ADD COLUMN IF NOT EXISTS "cancelRequestId" TEXT,
  ADD COLUMN IF NOT EXISTS "submittedAt" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "updatedAt" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "completedAt" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "errorCode" TEXT;

-- 复合唯一键只扩展既有主键身份，用于让 FK 同时闭合租户、小说与会话范围。
CREATE UNIQUE INDEX IF NOT EXISTS "WritingSession_id_novel_chapter_key"
ON public."WritingSession"(id, "novelId", "chapterId");

CREATE UNIQUE INDEX IF NOT EXISTS "WorkflowRun_id_userId_key"
ON public."WorkflowRun"(id, "userId");

CREATE UNIQUE INDEX IF NOT EXISTS "WorkflowRun_id_novelId_key"
ON public."WorkflowRun"(id, "novelId");

CREATE UNIQUE INDEX IF NOT EXISTS "WorkflowRun_id_cancelRequestId_key"
ON public."WorkflowRun"(id, "cancelRequestId");

CREATE UNIQUE INDEX IF NOT EXISTS "ReviewArtifact_id_workflowRunId_key"
ON public."ReviewArtifact"(id, "workflowRunId");

CREATE UNIQUE INDEX IF NOT EXISTS "ReviewArtifact_id_workflowRunId_novelId_key"
ON public."ReviewArtifact"(id, "workflowRunId", "novelId");

DO $run_constraints$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::regclass
      AND conname = 'WorkflowRun_engineVersion_check'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_engineVersion_check"
      CHECK ("engineVersion" IS NULL OR "engineVersion" IN (1, 2));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::pg_catalog.regclass
      AND conname = 'WorkflowRun_v1_scope_check'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_v1_scope_check"
      CHECK (
        "engineVersion" IS NOT DISTINCT FROM 2
        OR ("novelId" IS NOT NULL AND "chapterId" IS NOT NULL)
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::regclass
      AND conname = 'WorkflowRun_v2_shape_check'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_v2_shape_check"
      CHECK (
        "engineVersion" IS DISTINCT FROM 2
        OR (
          "userId" IS NOT NULL
          AND btrim("userId") <> ''
          AND workflow IS NOT NULL
          AND btrim(workflow) <> ''
          AND (operation IS NULL OR btrim(operation) <> '')
          AND "operationCatalogVersion" IS NOT NULL
          AND btrim("operationCatalogVersion") <> ''
          AND "idempotencyKey" IS NOT NULL
          AND btrim("idempotencyKey") <> ''
          AND "requestHash" IS NOT NULL
          AND "budgetJson" IS NOT NULL
          AND "modelPolicyJson" IS NOT NULL
          AND "lastEventSequence" IS NOT NULL
          AND revision IS NOT NULL
          AND ("writingSessionId" IS NULL OR (
            "novelId" IS NOT NULL AND "chapterId" IS NOT NULL
          ))
          AND (
            ("targetType" IS NULL AND "targetId" IS NULL)
            OR (
              "targetType" IS NOT NULL
              AND btrim("targetType") <> ''
              AND "targetId" IS NOT NULL
              AND btrim("targetId") <> ''
            )
          )
        )
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::regclass
      AND conname = 'WorkflowRun_requestHash_check'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_requestHash_check"
      CHECK ("requestHash" IS NULL OR "requestHash" ~ '^[0-9A-Fa-f]{64}$');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::regclass
      AND conname = 'WorkflowRun_budgetJson_check'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_budgetJson_check"
      CHECK (
        "budgetJson" IS NULL
        OR COALESCE(jsonb_typeof("budgetJson"::jsonb) = 'object', FALSE)
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::regclass
      AND conname = 'WorkflowRun_modelPolicyJson_check'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_modelPolicyJson_check"
      CHECK (
        "modelPolicyJson" IS NULL
        OR COALESCE(jsonb_typeof("modelPolicyJson"::jsonb) = 'object', FALSE)
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::regclass
      AND conname = 'WorkflowRun_sequence_revision_check'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_sequence_revision_check"
      CHECK (
        ("lastEventSequence" IS NULL OR "lastEventSequence" >= 0)
        AND (revision IS NULL OR revision > 0)
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::regclass
      AND conname = 'WorkflowRun_terminal_time_check'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_terminal_time_check"
      CHECK (
        "engineVersion" IS DISTINCT FROM 2
        OR (
          (
            status::text IN ('completed', 'failed', 'cancelled')
            AND "completedAt" IS NOT NULL
          )
          OR (
            status::text NOT IN ('completed', 'failed', 'cancelled')
            AND "completedAt" IS NULL
          )
        )
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::regclass
      AND conname = 'WorkflowRun_time_order_check'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_time_order_check"
      CHECK (
        ("cancelRequestedAt" IS NULL OR "cancelRequestedAt" >= "createdAt")
        AND ("completedAt" IS NULL OR "completedAt" >= "createdAt")
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::regclass
      AND conname = 'WorkflowRun_parent_not_self_check'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_parent_not_self_check"
      CHECK ("parentRunId" IS NULL OR "parentRunId" <> id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::pg_catalog.regclass
      AND conname = 'WorkflowRun_cancel_binding_check'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_cancel_binding_check"
      CHECK (
        (
          "cancelRequestId" IS NULL
          AND "cancelRequestedAt" IS NULL
          AND (
            "engineVersion" IS DISTINCT FROM 2
            OR status::text <> 'cancelled'
          )
        )
        OR (
          "cancelRequestId" IS NOT NULL
          AND btrim("cancelRequestId") <> ''
          AND "cancelRequestedAt" IS NOT NULL
        )
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::regclass
      AND conname = 'WorkflowRun_writingSessionId_fkey'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_writingSessionId_fkey"
      FOREIGN KEY ("writingSessionId") REFERENCES public."WritingSession"(id)
      ON UPDATE CASCADE ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::regclass
      AND conname = 'WorkflowRun_parentRunId_fkey'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_parentRunId_fkey"
      FOREIGN KEY ("parentRunId") REFERENCES public."WorkflowRun"(id)
      ON UPDATE CASCADE ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::pg_catalog.regclass
      AND conname = 'WorkflowRun_userId_fkey'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_userId_fkey"
      FOREIGN KEY ("userId") REFERENCES public."User"(id)
      ON UPDATE CASCADE ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::pg_catalog.regclass
      AND conname = 'WorkflowRun_novel_user_fkey'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_novel_user_fkey"
      FOREIGN KEY ("novelId", "userId") REFERENCES public."Novel"(id, "userId")
      ON UPDATE CASCADE ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::pg_catalog.regclass
      AND conname = 'WorkflowRun_writingSession_scope_fkey'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_writingSession_scope_fkey"
      FOREIGN KEY ("writingSessionId", "novelId", "chapterId")
      REFERENCES public."WritingSession"(id, "novelId", "chapterId")
      ON UPDATE CASCADE ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::pg_catalog.regclass
      AND conname = 'WorkflowRun_parent_user_fkey'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_parent_user_fkey"
      FOREIGN KEY ("parentRunId", "userId")
      REFERENCES public."WorkflowRun"(id, "userId")
      ON UPDATE CASCADE ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::pg_catalog.regclass
      AND conname = 'WorkflowRun_parent_novel_fkey'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_parent_novel_fkey"
      FOREIGN KEY ("parentRunId", "novelId")
      REFERENCES public."WorkflowRun"(id, "novelId")
      ON UPDATE CASCADE ON DELETE RESTRICT;
  END IF;
END
$run_constraints$;

DO $step_constraints$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::regclass
      AND conname = 'WorkflowStep_v2_shape_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_v2_shape_check"
      CHECK (
        ordinal IS NULL
        OR (
          ordinal > 0
          AND purpose IS NOT NULL
          AND btrim(purpose) <> ''
          AND lane IS NOT NULL
          AND "attemptCount" IS NOT NULL
          AND "attemptCount" >= 0
          AND "fencingToken" IS NOT NULL
          AND "fencingToken" >= 0
          AND "idempotencyKey" IS NOT NULL
          AND btrim("idempotencyKey") <> ''
          AND "requestHash" IS NOT NULL
          AND "inputHash" IS NOT NULL
          AND "submittedAt" IS NOT NULL
          AND "updatedAt" IS NOT NULL
          AND (status::text <> 'pending' OR "nextAttemptAt" IS NOT NULL)
        )
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::regclass
      AND conname = 'WorkflowStep_lane_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_lane_check"
      CHECK (
        lane IS NULL
        OR lane IN ('control', 'interactive', 'creative', 'batch_media')
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::regclass
      AND conname = 'WorkflowStep_counter_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_counter_check"
      CHECK (
        ("attemptCount" IS NULL OR "attemptCount" >= 0)
        AND ("fencingToken" IS NULL OR "fencingToken" >= 0)
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::regclass
      AND conname = 'WorkflowStep_hashes_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_hashes_check"
      CHECK (
        ("requestHash" IS NULL OR "requestHash" ~ '^[0-9A-Fa-f]{64}$')
        AND ("inputHash" IS NULL OR "inputHash" ~ '^[0-9A-Fa-f]{64}$')
        AND ("resultHash" IS NULL OR "resultHash" ~ '^[0-9A-Fa-f]{64}$')
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::regclass
      AND conname = 'WorkflowStep_lease_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_lease_check"
      CHECK (
        ("activeJobId" IS NULL AND "leaseExpiresAt" IS NULL)
        OR (
          "activeJobId" IS NOT NULL
          AND btrim("activeJobId") <> ''
          AND "leaseExpiresAt" IS NOT NULL
        )
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::regclass
      AND conname = 'WorkflowStep_artifact_binding_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_artifact_binding_check"
      CHECK (
        ("artifactId" IS NULL AND "artifactRevision" IS NULL)
        OR (
          "artifactId" IS NOT NULL
          AND "artifactRevision" IS NOT NULL
          AND "artifactRevision" > 0
        )
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::regclass
      AND conname = 'WorkflowStep_model_binding_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_model_binding_check"
      CHECK (
        (
          "modelProfile" IS NULL
          AND "modelProfileVersion" IS NULL
          AND "outputSchema" IS NULL
          AND "outputSchemaVersion" IS NULL
        )
        OR (
          "modelProfile" IS NOT NULL
          AND btrim("modelProfile") <> ''
          AND "modelProfileVersion" IS NOT NULL
          AND btrim("modelProfileVersion") <> ''
          AND "outputSchema" IS NOT NULL
          AND btrim("outputSchema") <> ''
          AND "outputSchemaVersion" IS NOT NULL
          AND btrim("outputSchemaVersion") <> ''
        )
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::regclass
      AND conname = 'WorkflowStep_budgetJson_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_budgetJson_check"
      CHECK (
        "budgetJson" IS NULL
        OR COALESCE(jsonb_typeof("budgetJson"::jsonb) = 'object', FALSE)
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::regclass
      AND conname = 'WorkflowStep_terminal_time_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_terminal_time_check"
      CHECK (
        ordinal IS NULL
        OR (
          (
            status::text IN ('completed', 'failed', 'skipped')
            AND "completedAt" IS NOT NULL
          )
          OR (
            status::text NOT IN ('completed', 'failed', 'skipped')
            AND "completedAt" IS NULL
          )
        )
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::pg_catalog.regclass
      AND conname = 'WorkflowStep_resolvedModelJson_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_resolvedModelJson_check"
      CHECK (
        "resolvedModelJson" IS NULL
        OR COALESCE(jsonb_typeof("resolvedModelJson"::jsonb) = 'object', FALSE)
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::pg_catalog.regclass
      AND conname = 'WorkflowStep_usageJson_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_usageJson_check"
      CHECK (
        "usageJson" IS NULL
        OR COALESCE(jsonb_typeof("usageJson"::jsonb) = 'object', FALSE)
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::pg_catalog.regclass
      AND conname = 'WorkflowStep_progress_sequence_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_progress_sequence_check"
      CHECK (
        "lastProgressSequence" IS NULL
        OR (
          "lastProgressSequence" >= 0
          AND "usageJson" IS NOT NULL
        )
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::pg_catalog.regclass
      AND conname = 'WorkflowStep_resolved_model_binding_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_resolved_model_binding_check"
      CHECK (
        "resolvedModelJson" IS NULL
        OR (
          "modelProfile" IS NOT NULL
          AND btrim("modelProfile") <> ''
          AND "modelProfileVersion" IS NOT NULL
          AND btrim("modelProfileVersion") <> ''
        )
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::pg_catalog.regclass
      AND conname = 'WorkflowStep_cancel_binding_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_cancel_binding_check"
      CHECK (
        "cancelRequestId" IS NULL
        OR (
          ordinal IS NOT NULL
          AND btrim("cancelRequestId") <> ''
        )
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::pg_catalog.regclass
      AND conname = 'WorkflowStep_cancel_run_fkey'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_cancel_run_fkey"
      FOREIGN KEY ("runId", "cancelRequestId")
      REFERENCES public."WorkflowRun"(id, "cancelRequestId")
      ON UPDATE CASCADE ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::regclass
      AND conname = 'WorkflowStep_time_order_check'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_time_order_check"
      CHECK (
        ("submittedAt" IS NULL OR "submittedAt" >= "createdAt")
        AND ("nextAttemptAt" IS NULL OR "nextAttemptAt" >= "createdAt")
        AND ("updatedAt" IS NULL OR "updatedAt" >= "createdAt")
        AND ("heartbeatAt" IS NULL OR "heartbeatAt" >= "createdAt")
        AND ("completedAt" IS NULL OR "completedAt" >= "createdAt")
      );
  END IF;
END
$step_constraints$;

-- V2 Artifact 是审计事实：discard 只收敛 Run，不删除候选，Run 也不能先于候选被删除。
DO $artifact_owner_constraints$
DECLARE
  workflow_fk_delete_action "char";
BEGIN
  SELECT confdeltype
  INTO workflow_fk_delete_action
  FROM pg_catalog.pg_constraint
  WHERE conrelid = 'public."ReviewArtifact"'::pg_catalog.regclass
    AND conname = 'ReviewArtifact_workflowRunId_fkey';

  IF workflow_fk_delete_action IS NOT NULL AND workflow_fk_delete_action <> 'r' THEN
    ALTER TABLE public."ReviewArtifact"
      DROP CONSTRAINT "ReviewArtifact_workflowRunId_fkey";
    workflow_fk_delete_action := NULL;
  END IF;

  IF workflow_fk_delete_action IS NULL THEN
    ALTER TABLE public."ReviewArtifact"
      ADD CONSTRAINT "ReviewArtifact_workflowRunId_fkey"
      FOREIGN KEY ("workflowRunId") REFERENCES public."WorkflowRun"(id)
      ON UPDATE CASCADE ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."ReviewArtifact"'::pg_catalog.regclass
      AND conname = 'ReviewArtifact_workflow_owner_exclusive_check'
  ) THEN
    ALTER TABLE public."ReviewArtifact"
      ADD CONSTRAINT "ReviewArtifact_workflow_owner_exclusive_check"
      CHECK (NOT ("taskId" IS NOT NULL AND "workflowRunId" IS NOT NULL));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."ReviewArtifact"'::pg_catalog.regclass
      AND conname = 'ReviewArtifact_workflow_run_novel_fkey'
  ) THEN
    ALTER TABLE public."ReviewArtifact"
      ADD CONSTRAINT "ReviewArtifact_workflow_run_novel_fkey"
      FOREIGN KEY ("workflowRunId", "novelId")
      REFERENCES public."WorkflowRun"(id, "novelId")
      ON UPDATE CASCADE ON DELETE RESTRICT;
  END IF;
END
$artifact_owner_constraints$;

CREATE TABLE IF NOT EXISTS public."WorkflowEvidenceBundle" (
  id TEXT NOT NULL,
  "runId" TEXT NOT NULL,
  version INTEGER NOT NULL,
  "policyVersion" TEXT NOT NULL,
  "manifestJson" TEXT NOT NULL,
  "manifestSha256" TEXT NOT NULL,
  "totalBytes" BIGINT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "WorkflowEvidenceBundle_pkey" PRIMARY KEY (id),
  CONSTRAINT "WorkflowEvidenceBundle_run_version_key" UNIQUE ("runId", version),
  CONSTRAINT "WorkflowEvidenceBundle_id_runId_key" UNIQUE (id, "runId"),
  CONSTRAINT "WorkflowEvidenceBundle_runId_fkey"
    FOREIGN KEY ("runId") REFERENCES public."WorkflowRun"(id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT "WorkflowEvidenceBundle_version_check" CHECK (version > 0),
  CONSTRAINT "WorkflowEvidenceBundle_policyVersion_check"
    CHECK (btrim("policyVersion") <> ''),
  CONSTRAINT "WorkflowEvidenceBundle_manifestJson_check"
    CHECK (COALESCE(jsonb_typeof("manifestJson"::jsonb) = 'object', FALSE)),
  CONSTRAINT "WorkflowEvidenceBundle_manifestSha256_check"
    CHECK ("manifestSha256" ~ '^[0-9A-Fa-f]{64}$'),
  CONSTRAINT "WorkflowEvidenceBundle_totalBytes_check" CHECK ("totalBytes" >= 0)
);

CREATE TABLE IF NOT EXISTS public."WorkflowEvidenceItem" (
  id TEXT NOT NULL,
  "bundleId" TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  "resourceType" TEXT NOT NULL,
  "resourceId" TEXT NOT NULL,
  exists BOOLEAN NOT NULL,
  "resourceRevision" INTEGER,
  "resourceUpdatedAt" TIMESTAMP(3),
  "contentType" TEXT,
  "contentText" TEXT,
  "contentJson" TEXT,
  "contentSha256" TEXT,
  "byteCount" BIGINT NOT NULL,
  "rangeJson" TEXT,
  "metadataJson" TEXT NOT NULL DEFAULT '{}',
  CONSTRAINT "WorkflowEvidenceItem_pkey" PRIMARY KEY (id),
  CONSTRAINT "WorkflowEvidenceItem_bundle_ordinal_key" UNIQUE ("bundleId", ordinal),
  CONSTRAINT "WorkflowEvidenceItem_bundleId_fkey"
    FOREIGN KEY ("bundleId") REFERENCES public."WorkflowEvidenceBundle"(id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT "WorkflowEvidenceItem_ordinal_check" CHECK (ordinal > 0),
  CONSTRAINT "WorkflowEvidenceItem_resource_check" CHECK (
    btrim("resourceType") <> '' AND btrim("resourceId") <> ''
  ),
  CONSTRAINT "WorkflowEvidenceItem_resourceRevision_check" CHECK (
    "resourceRevision" IS NULL OR "resourceRevision" > 0
  ),
  CONSTRAINT "WorkflowEvidenceItem_contentType_check" CHECK (
    "contentType" IS NULL OR "contentType" IN ('text', 'json')
  ),
  CONSTRAINT "WorkflowEvidenceItem_content_exclusive_check" CHECK (
    (NOT exists AND "contentText" IS NULL AND "contentJson" IS NULL)
    OR (
      exists
      AND (
        ("contentType" = 'text' AND "contentText" IS NOT NULL AND "contentJson" IS NULL)
        OR ("contentType" = 'json' AND "contentText" IS NULL AND "contentJson" IS NOT NULL)
      )
    )
  ),
  CONSTRAINT "WorkflowEvidenceItem_existence_shape_check" CHECK (
    (
      NOT exists
      AND "resourceRevision" IS NULL
      AND "resourceUpdatedAt" IS NULL
      AND "contentType" IS NULL
      AND "contentText" IS NULL
      AND "contentJson" IS NULL
      AND "contentSha256" IS NULL
      AND "rangeJson" IS NULL
      AND "byteCount" = 0
    )
    OR (
      exists
      AND "contentType" IS NOT NULL
      AND "contentSha256" IS NOT NULL
      AND (
        ("contentText" IS NOT NULL AND "contentJson" IS NULL)
        OR ("contentText" IS NULL AND "contentJson" IS NOT NULL)
      )
    )
  ),
  CONSTRAINT "WorkflowEvidenceItem_contentJson_check" CHECK (
    "contentJson" IS NULL OR ("contentJson"::jsonb IS NOT NULL)
  ),
  CONSTRAINT "WorkflowEvidenceItem_contentSha256_check"
    CHECK ("contentSha256" IS NULL OR "contentSha256" ~ '^[0-9A-Fa-f]{64}$'),
  CONSTRAINT "WorkflowEvidenceItem_byteCount_check" CHECK ("byteCount" >= 0),
  CONSTRAINT "WorkflowEvidenceItem_rangeJson_check" CHECK (
    "rangeJson" IS NULL
    OR COALESCE(jsonb_typeof("rangeJson"::jsonb) = 'object', FALSE)
  ),
  CONSTRAINT "WorkflowEvidenceItem_metadataJson_check" CHECK (
    COALESCE(jsonb_typeof("metadataJson"::jsonb) = 'object', FALSE)
  )
);

CREATE TABLE IF NOT EXISTS public."WorkflowEvent" (
  id TEXT NOT NULL,
  "runId" TEXT NOT NULL,
  sequence BIGINT NOT NULL,
  "eventType" TEXT NOT NULL,
  "payloadJson" TEXT NOT NULL,
  "dedupeKey" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "WorkflowEvent_pkey" PRIMARY KEY (id),
  CONSTRAINT "WorkflowEvent_run_sequence_key" UNIQUE ("runId", sequence),
  CONSTRAINT "WorkflowEvent_run_dedupe_key" UNIQUE ("runId", "dedupeKey"),
  CONSTRAINT "WorkflowEvent_runId_fkey"
    FOREIGN KEY ("runId") REFERENCES public."WorkflowRun"(id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT "WorkflowEvent_sequence_check" CHECK (sequence > 0),
  CONSTRAINT "WorkflowEvent_eventType_check" CHECK (
    "eventType" IN (
      'run_accepted',
      'intent_resolved',
      'clarification_required',
      'evidence_ready',
      'step_queued',
      'step_started',
      'step_progress',
      'step_finished',
      'candidate_ready',
      'review_started',
      'review_completed',
      'awaiting_user',
      'applying',
      'completed',
      'failed',
      'cancelled'
    )
  ),
  CONSTRAINT "WorkflowEvent_payloadJson_check"
    CHECK (COALESCE(jsonb_typeof("payloadJson"::jsonb) = 'object', FALSE)),
  CONSTRAINT "WorkflowEvent_dedupeKey_check" CHECK (btrim("dedupeKey") <> '')
);

-- 该具名迁移在正式执行前曾有本地预发布草案；事件集合只允许向当前冻结协议精确收敛。
-- 重建同名 CHECK 既让全新安装与草案重跑一致，也不会改写任何既有事件行。
ALTER TABLE public."WorkflowEvent"
  DROP CONSTRAINT IF EXISTS "WorkflowEvent_eventType_check";
ALTER TABLE public."WorkflowEvent"
  ADD CONSTRAINT "WorkflowEvent_eventType_check" CHECK (
    "eventType" IN (
      'run_accepted',
      'intent_resolved',
      'clarification_required',
      'evidence_ready',
      'step_queued',
      'step_started',
      'step_progress',
      'step_finished',
      'candidate_ready',
      'review_started',
      'review_completed',
      'awaiting_user',
      'applying',
      'completed',
      'failed',
      'cancelled'
    )
  );

-- 复合外键用于阻止 Step/Evaluation 绑定其他 Run 的证据或 Step。
CREATE UNIQUE INDEX IF NOT EXISTS "WorkflowStep_id_runId_key"
ON public."WorkflowStep"(id, "runId");

CREATE UNIQUE INDEX IF NOT EXISTS "WorkflowStep_evaluation_binding_key"
ON public."WorkflowStep"(
  id,
  "runId",
  "evidenceBundleId",
  "artifactId",
  "artifactRevision"
);

CREATE UNIQUE INDEX IF NOT EXISTS "WorkflowStep_evaluation_context_key"
ON public."WorkflowStep"(id, "runId", "evidenceBundleId");

CREATE TABLE IF NOT EXISTS public."WorkflowEvaluation" (
  id TEXT NOT NULL,
  "runId" TEXT NOT NULL,
  "stepId" TEXT NOT NULL,
  "evidenceBundleId" TEXT NOT NULL,
  "artifactId" TEXT,
  "artifactRevision" INTEGER,
  "evaluatorProfile" TEXT NOT NULL,
  "rubricVersion" TEXT NOT NULL,
  "executionStatus" TEXT NOT NULL,
  "contentVerdict" TEXT NOT NULL,
  "findingsJson" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "WorkflowEvaluation_pkey" PRIMARY KEY (id),
  CONSTRAINT "WorkflowEvaluation_stepId_key" UNIQUE ("stepId"),
  CONSTRAINT "WorkflowEvaluation_runId_fkey"
    FOREIGN KEY ("runId") REFERENCES public."WorkflowRun"(id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT "WorkflowEvaluation_step_run_fkey"
    FOREIGN KEY ("stepId", "runId") REFERENCES public."WorkflowStep"(id, "runId")
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT "WorkflowEvaluation_evidence_run_fkey"
    FOREIGN KEY ("evidenceBundleId", "runId")
    REFERENCES public."WorkflowEvidenceBundle"(id, "runId")
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT "WorkflowEvaluation_artifact_revision_fkey"
    FOREIGN KEY ("artifactId", "artifactRevision")
    REFERENCES public."ReviewArtifactRevision"("artifactId", revision)
    MATCH SIMPLE
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT "WorkflowEvaluation_profile_check" CHECK (
    btrim("evaluatorProfile") <> '' AND btrim("rubricVersion") <> ''
  ),
  CONSTRAINT "WorkflowEvaluation_executionStatus_check" CHECK (
    "executionStatus" IN ('completed', 'incomplete', 'failed')
  ),
  CONSTRAINT "WorkflowEvaluation_contentVerdict_check" CHECK (
    "contentVerdict" IN ('pass', 'issues_found', 'cannot_assess')
  ),
  CONSTRAINT "WorkflowEvaluation_execution_content_check" CHECK (
    "executionStatus" = 'completed' OR "contentVerdict" = 'cannot_assess'
  ),
  CONSTRAINT "WorkflowEvaluation_findingsJson_check" CHECK (
    COALESCE(jsonb_typeof("findingsJson"::jsonb) = 'array', FALSE)
  ),
  CONSTRAINT "WorkflowEvaluation_artifact_binding_check" CHECK (
    ("artifactId" IS NULL AND "artifactRevision" IS NULL)
    OR (
      "artifactId" IS NOT NULL
      AND "artifactRevision" IS NOT NULL
      AND "artifactRevision" > 0
    )
  )
);

-- 兼容同名迁移早期草案：非 Artifact 质量评估允许一对 NULL，但禁止单边 NULL。
ALTER TABLE public."WorkflowEvaluation"
  ALTER COLUMN "artifactId" DROP NOT NULL,
  ALTER COLUMN "artifactRevision" DROP NOT NULL,
  DROP CONSTRAINT IF EXISTS "WorkflowEvaluation_artifactRevision_check";

DO $evaluation_artifact_shape$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowEvaluation"'::pg_catalog.regclass
      AND conname = 'WorkflowEvaluation_artifact_binding_check'
  ) THEN
    ALTER TABLE public."WorkflowEvaluation"
      ADD CONSTRAINT "WorkflowEvaluation_artifact_binding_check"
      CHECK (
        ("artifactId" IS NULL AND "artifactRevision" IS NULL)
        OR (
          "artifactId" IS NOT NULL
          AND "artifactRevision" IS NOT NULL
          AND "artifactRevision" > 0
        )
      );
  END IF;
END
$evaluation_artifact_shape$;

DO $evaluation_scope_constraints$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowEvaluation"'::pg_catalog.regclass
      AND conname = 'WorkflowEvaluation_step_evidence_fkey'
  ) THEN
    ALTER TABLE public."WorkflowEvaluation"
      ADD CONSTRAINT "WorkflowEvaluation_step_evidence_fkey"
      FOREIGN KEY ("stepId", "runId", "evidenceBundleId")
      REFERENCES public."WorkflowStep"(id, "runId", "evidenceBundleId")
      ON UPDATE CASCADE ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowEvaluation"'::pg_catalog.regclass
      AND conname = 'WorkflowEvaluation_step_exact_fkey'
  ) THEN
    ALTER TABLE public."WorkflowEvaluation"
      ADD CONSTRAINT "WorkflowEvaluation_step_exact_fkey"
      FOREIGN KEY (
        "stepId",
        "runId",
        "evidenceBundleId",
        "artifactId",
        "artifactRevision"
      ) REFERENCES public."WorkflowStep"(
        id,
        "runId",
        "evidenceBundleId",
        "artifactId",
        "artifactRevision"
      )
      MATCH SIMPLE
      ON UPDATE CASCADE ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowEvaluation"'::pg_catalog.regclass
      AND conname = 'WorkflowEvaluation_artifact_run_fkey'
  ) THEN
    ALTER TABLE public."WorkflowEvaluation"
      ADD CONSTRAINT "WorkflowEvaluation_artifact_run_fkey"
      FOREIGN KEY ("artifactId", "runId")
      REFERENCES public."ReviewArtifact"(id, "workflowRunId")
      MATCH SIMPLE
      ON UPDATE CASCADE ON DELETE RESTRICT;
  END IF;
END
$evaluation_scope_constraints$;

-- 每个逻辑模型 Step 只允许一个 Core 权威积分预留。余额本身仍是已结算事实；
-- reserved/reconciliation_required 行在 User 行锁内参与可用余额计算，不能充当第二份工作流状态。
CREATE TABLE IF NOT EXISTS public."WorkflowBillingReservation" (
  id TEXT NOT NULL,
  "runId" TEXT NOT NULL,
  "stepId" TEXT NOT NULL,
  "userId" TEXT NOT NULL,
  "requestId" TEXT NOT NULL,
  "pricingVersion" TEXT NOT NULL,
  "pricingJson" TEXT NOT NULL,
  "reservedMicros" BIGINT NOT NULL,
  "chargedMicros" BIGINT NOT NULL DEFAULT 0,
  "usageJson" TEXT,
  status TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  "settledAt" TIMESTAMP(3),
  CONSTRAINT "WorkflowBillingReservation_pkey" PRIMARY KEY (id),
  CONSTRAINT "WorkflowBillingReservation_stepId_key" UNIQUE ("stepId"),
  CONSTRAINT "WorkflowBillingReservation_requestId_key" UNIQUE ("requestId"),
  CONSTRAINT "WorkflowBillingReservation_run_step_key" UNIQUE ("runId", "stepId"),
  CONSTRAINT "WorkflowBillingReservation_run_user_fkey"
    FOREIGN KEY ("runId", "userId") REFERENCES public."WorkflowRun"(id, "userId")
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT "WorkflowBillingReservation_step_run_fkey"
    FOREIGN KEY ("stepId", "runId") REFERENCES public."WorkflowStep"(id, "runId")
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT "WorkflowBillingReservation_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES public."User"(id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT "WorkflowBillingReservation_requestId_check"
    CHECK (btrim("requestId") <> ''),
  CONSTRAINT "WorkflowBillingReservation_pricing_check" CHECK (
    btrim("pricingVersion") <> ''
    AND COALESCE(jsonb_typeof("pricingJson"::jsonb) = 'object', FALSE)
  ),
  CONSTRAINT "WorkflowBillingReservation_amount_check" CHECK (
    "reservedMicros" >= 0
    AND "chargedMicros" >= 0
    AND "chargedMicros" <= "reservedMicros"
  ),
  CONSTRAINT "WorkflowBillingReservation_usageJson_check" CHECK (
    "usageJson" IS NULL
    OR COALESCE(jsonb_typeof("usageJson"::jsonb) = 'object', FALSE)
  ),
  CONSTRAINT "WorkflowBillingReservation_status_check" CHECK (
    status IN ('reserved', 'settled', 'released', 'reconciliation_required')
  ),
  CONSTRAINT "WorkflowBillingReservation_status_shape_check" CHECK (
    (
      status = 'reserved'
      AND "chargedMicros" = 0
      AND "usageJson" IS NULL
      AND "settledAt" IS NULL
    )
    OR (
      status = 'settled'
      AND "usageJson" IS NOT NULL
      AND "settledAt" IS NOT NULL
    )
    OR (
      status = 'released'
      AND "chargedMicros" = 0
      AND "settledAt" IS NOT NULL
    )
    OR (
      status = 'reconciliation_required'
      AND "chargedMicros" = 0
      AND "usageJson" IS NOT NULL
      AND "settledAt" IS NULL
    )
  ),
  CONSTRAINT "WorkflowBillingReservation_time_order_check" CHECK (
    "updatedAt" >= "createdAt"
    AND ("settledAt" IS NULL OR "settledAt" >= "createdAt")
  )
);

DO $relationship_constraints$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowRun"'::regclass
      AND conname = 'WorkflowRun_currentEvidenceBundleId_fkey'
  ) THEN
    ALTER TABLE public."WorkflowRun"
      ADD CONSTRAINT "WorkflowRun_currentEvidenceBundleId_fkey"
      FOREIGN KEY ("currentEvidenceBundleId", id)
      REFERENCES public."WorkflowEvidenceBundle"(id, "runId")
      ON UPDATE NO ACTION
      ON DELETE NO ACTION
      DEFERRABLE INITIALLY DEFERRED;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::regclass
      AND conname = 'WorkflowStep_evidence_run_fkey'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_evidence_run_fkey"
      FOREIGN KEY ("evidenceBundleId", "runId")
      REFERENCES public."WorkflowEvidenceBundle"(id, "runId")
      ON UPDATE CASCADE
      ON DELETE NO ACTION
      DEFERRABLE INITIALLY DEFERRED;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::regclass
      AND conname = 'WorkflowStep_artifact_revision_fkey'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_artifact_revision_fkey"
      FOREIGN KEY ("artifactId", "artifactRevision")
      REFERENCES public."ReviewArtifactRevision"("artifactId", revision)
      ON UPDATE CASCADE ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public."WorkflowStep"'::pg_catalog.regclass
      AND conname = 'WorkflowStep_artifact_run_fkey'
  ) THEN
    ALTER TABLE public."WorkflowStep"
      ADD CONSTRAINT "WorkflowStep_artifact_run_fkey"
      FOREIGN KEY ("artifactId", "runId")
      REFERENCES public."ReviewArtifact"(id, "workflowRunId")
      ON UPDATE CASCADE ON DELETE RESTRICT;
  END IF;
END
$relationship_constraints$;

CREATE OR REPLACE FUNCTION public."rejectWorkflowAuditMutation"()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $immutable$
BEGIN
  RAISE EXCEPTION USING
    ERRCODE = '55000',
    MESSAGE = pg_catalog.format(
      '%s 是不可变工作流审计事实，禁止 %s',
      TG_TABLE_NAME,
      TG_OP
    );
END
$immutable$;

-- BillingReservation 需要从 reserved 结算到终态，但身份、价格和预留上限一经创建不得漂移。
CREATE OR REPLACE FUNCTION public."rejectWorkflowBillingIdentityMutation"()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $billing_identity$
BEGIN
  IF NEW.id IS DISTINCT FROM OLD.id
      OR NEW."runId" IS DISTINCT FROM OLD."runId"
      OR NEW."stepId" IS DISTINCT FROM OLD."stepId"
      OR NEW."userId" IS DISTINCT FROM OLD."userId"
      OR NEW."requestId" IS DISTINCT FROM OLD."requestId"
      OR NEW."pricingVersion" IS DISTINCT FROM OLD."pricingVersion"
      OR NEW."pricingJson" IS DISTINCT FROM OLD."pricingJson"
      OR NEW."reservedMicros" IS DISTINCT FROM OLD."reservedMicros"
      OR NEW."createdAt" IS DISTINCT FROM OLD."createdAt" THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'WorkflowBillingReservation 身份、价格与预留上限不可修改';
  END IF;
  RETURN NEW;
END
$billing_identity$;

DO $billing_identity_trigger$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_trigger AS trigger_row
    WHERE trigger_row.tgrelid = 'public."WorkflowBillingReservation"'::pg_catalog.regclass
      AND trigger_row.tgname = 'WorkflowBillingReservation_identity_immutable_trigger'
      AND NOT trigger_row.tgisinternal
  ) THEN
    CREATE TRIGGER "WorkflowBillingReservation_identity_immutable_trigger"
    BEFORE UPDATE ON public."WorkflowBillingReservation"
    FOR EACH ROW EXECUTE FUNCTION public."rejectWorkflowBillingIdentityMutation"();
  END IF;
END
$billing_identity_trigger$;

-- V2 Run 的请求、归属、目标、预算与完整执行计划是一份不可重解释的身份快照。
CREATE OR REPLACE FUNCTION public."rejectWorkflowRunV2IdentityMutation"()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $run_identity$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD."engineVersion" = 2 THEN
      RAISE EXCEPTION USING
        ERRCODE = '55000',
        MESSAGE = 'V2 WorkflowRun 是不可删除的耐久执行审计事实';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD."engineVersion" IS DISTINCT FROM 2
      AND NEW."engineVersion" IS DISTINCT FROM 2 THEN
    RETURN NEW;
  END IF;
  IF NEW.id IS DISTINCT FROM OLD.id
      OR NEW."novelId" IS DISTINCT FROM OLD."novelId"
      OR NEW."chapterId" IS DISTINCT FROM OLD."chapterId"
      OR NEW."userId" IS DISTINCT FROM OLD."userId"
      OR NEW.kind IS DISTINCT FROM OLD.kind
      OR NEW.input IS DISTINCT FROM OLD.input
      OR NEW."sourceType" IS DISTINCT FROM OLD."sourceType"
      OR NEW."sourceId" IS DISTINCT FROM OLD."sourceId"
      OR NEW."createdAt" IS DISTINCT FROM OLD."createdAt"
      OR NEW."engineVersion" IS DISTINCT FROM OLD."engineVersion"
      OR NEW.workflow IS DISTINCT FROM OLD.workflow
      OR NEW.operation IS DISTINCT FROM OLD.operation
      OR NEW."operationCatalogVersion" IS DISTINCT FROM OLD."operationCatalogVersion"
      OR NEW."writingSessionId" IS DISTINCT FROM OLD."writingSessionId"
      OR NEW."parentRunId" IS DISTINCT FROM OLD."parentRunId"
      OR NEW."idempotencyKey" IS DISTINCT FROM OLD."idempotencyKey"
      OR NEW."requestHash" IS DISTINCT FROM OLD."requestHash"
      OR NEW."targetType" IS DISTINCT FROM OLD."targetType"
      OR NEW."targetId" IS DISTINCT FROM OLD."targetId"
      OR NEW."budgetJson" IS DISTINCT FROM OLD."budgetJson"
      OR NEW."modelPolicyJson" IS DISTINCT FROM OLD."modelPolicyJson" THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'V2 WorkflowRun 的归属、目标、请求、预算与执行计划身份不可修改';
  END IF;
  IF (OLD."cancelRequestId" IS NOT NULL
        AND NEW."cancelRequestId" IS DISTINCT FROM OLD."cancelRequestId")
      OR (OLD."cancelRequestedAt" IS NOT NULL
        AND NEW."cancelRequestedAt" IS DISTINCT FROM OLD."cancelRequestedAt") THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'V2 WorkflowRun 的取消身份只能从 NULL 冻结一次';
  END IF;
  IF OLD.status::text IN ('completed', 'failed', 'cancelled')
      AND NEW.status IS DISTINCT FROM OLD.status THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'V2 WorkflowRun 的终态不可反转';
  END IF;
  IF (OLD."completedAt" IS NOT NULL
        AND NEW."completedAt" IS DISTINCT FROM OLD."completedAt")
      OR (OLD."errorCode" IS NOT NULL
        AND NEW."errorCode" IS DISTINCT FROM OLD."errorCode") THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'V2 WorkflowRun 的完成时间与错误码只能从 NULL 冻结一次';
  END IF;
  RETURN NEW;
END
$run_identity$;

-- V2 Step 的逻辑调用身份不可变；执行结果绑定只允许从 NULL 一次冻结。
CREATE OR REPLACE FUNCTION public."rejectWorkflowStepV2IdentityMutation"()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $step_identity$
DECLARE
  belongs_to_v2 BOOLEAN;
BEGIN
  IF TG_OP = 'DELETE' THEN
    SELECT EXISTS (
      SELECT 1
      FROM public."WorkflowRun" AS run
      WHERE run.id = OLD."runId"
        AND run."engineVersion" = 2
    )
    INTO belongs_to_v2;
    IF belongs_to_v2 THEN
      RAISE EXCEPTION USING
        ERRCODE = '55000',
        MESSAGE = 'V2 WorkflowStep 是不可删除的耐久执行审计事实';
    END IF;
    RETURN OLD;
  END IF;
  SELECT EXISTS (
    SELECT 1
    FROM public."WorkflowRun" AS run
    WHERE run.id IN (OLD."runId", NEW."runId")
      AND run."engineVersion" = 2
  )
  INTO belongs_to_v2;
  IF NOT belongs_to_v2 THEN
    RETURN NEW;
  END IF;
  IF NEW.id IS DISTINCT FROM OLD.id
      OR NEW."runId" IS DISTINCT FROM OLD."runId"
      OR NEW."agentId" IS DISTINCT FROM OLD."agentId"
      OR NEW."stepType" IS DISTINCT FROM OLD."stepType"
      OR NEW.input IS DISTINCT FROM OLD.input
      OR NEW."createdAt" IS DISTINCT FROM OLD."createdAt"
      OR NEW.ordinal IS DISTINCT FROM OLD.ordinal
      OR NEW.purpose IS DISTINCT FROM OLD.purpose
      OR NEW.lane IS DISTINCT FROM OLD.lane
      OR NEW."idempotencyKey" IS DISTINCT FROM OLD."idempotencyKey"
      OR NEW."requestHash" IS DISTINCT FROM OLD."requestHash"
      OR NEW."inputHash" IS DISTINCT FROM OLD."inputHash"
      OR NEW."evidenceBundleId" IS DISTINCT FROM OLD."evidenceBundleId"
      OR NEW."modelProfile" IS DISTINCT FROM OLD."modelProfile"
      OR NEW."modelProfileVersion" IS DISTINCT FROM OLD."modelProfileVersion"
      OR NEW."outputSchema" IS DISTINCT FROM OLD."outputSchema"
      OR NEW."outputSchemaVersion" IS DISTINCT FROM OLD."outputSchemaVersion"
      OR NEW."budgetJson" IS DISTINCT FROM OLD."budgetJson"
      OR NEW."submittedAt" IS DISTINCT FROM OLD."submittedAt" THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'V2 WorkflowStep 的调用身份不可修改';
  END IF;
  IF (OLD."artifactId" IS NOT NULL OR OLD."artifactRevision" IS NOT NULL)
      AND (
        NEW."artifactId" IS DISTINCT FROM OLD."artifactId"
        OR NEW."artifactRevision" IS DISTINCT FROM OLD."artifactRevision"
      ) THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'V2 WorkflowStep 的 Artifact 绑定只能从 NULL 冻结一次';
  END IF;
  IF OLD."resolvedModelJson" IS NOT NULL
      AND NEW."resolvedModelJson" IS DISTINCT FROM OLD."resolvedModelJson" THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'V2 WorkflowStep 的 resolved model 只能从 NULL 冻结一次';
  END IF;
  IF OLD."resultHash" IS NOT NULL
      AND NEW."resultHash" IS DISTINCT FROM OLD."resultHash" THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'V2 WorkflowStep 的 result hash 只能从 NULL 冻结一次';
  END IF;
  IF OLD."cancelRequestId" IS NOT NULL
      AND NEW."cancelRequestId" IS DISTINCT FROM OLD."cancelRequestId" THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'V2 WorkflowStep 的取消身份只能从 NULL 冻结一次';
  END IF;
  IF OLD.status::text IN ('completed', 'failed', 'skipped')
      AND NEW.status IS DISTINCT FROM OLD.status THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'V2 WorkflowStep 的终态不可反转';
  END IF;
  IF (OLD."completedAt" IS NOT NULL
        AND NEW."completedAt" IS DISTINCT FROM OLD."completedAt")
      OR (OLD."errorCode" IS NOT NULL
        AND NEW."errorCode" IS DISTINCT FROM OLD."errorCode") THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'V2 WorkflowStep 的完成时间与错误码只能从 NULL 冻结一次';
  END IF;
  RETURN NEW;
END
$step_identity$;

DO $v2_identity_triggers$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_trigger AS trigger_row
    WHERE trigger_row.tgrelid = 'public."WorkflowRun"'::pg_catalog.regclass
      AND trigger_row.tgname = 'WorkflowRun_v2_identity_immutable_trigger'
      AND NOT trigger_row.tgisinternal
  ) THEN
    CREATE TRIGGER "WorkflowRun_v2_identity_immutable_trigger"
    BEFORE UPDATE OR DELETE ON public."WorkflowRun"
    FOR EACH ROW EXECUTE FUNCTION public."rejectWorkflowRunV2IdentityMutation"();
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_trigger AS trigger_row
    WHERE trigger_row.tgrelid = 'public."WorkflowStep"'::pg_catalog.regclass
      AND trigger_row.tgname = 'WorkflowStep_v2_identity_immutable_trigger'
      AND NOT trigger_row.tgisinternal
  ) THEN
    CREATE TRIGGER "WorkflowStep_v2_identity_immutable_trigger"
    BEFORE UPDATE OR DELETE ON public."WorkflowStep"
    FOR EACH ROW EXECUTE FUNCTION public."rejectWorkflowStepV2IdentityMutation"();
  END IF;
END
$v2_identity_triggers$;

DO $immutable_triggers$
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
    trigger_name := relation_name || '_immutable_trigger';
    IF NOT EXISTS (
      SELECT 1
      FROM pg_catalog.pg_trigger AS trigger_row
      WHERE trigger_row.tgrelid = pg_catalog.to_regclass(
          pg_catalog.format('public.%I', relation_name)
        )
        AND trigger_row.tgname = trigger_name
        AND NOT trigger_row.tgisinternal
    ) THEN
      EXECUTE pg_catalog.format(
        'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON public.%I '
        'FOR EACH ROW EXECUTE FUNCTION public.%I()',
        trigger_name,
        relation_name,
        'rejectWorkflowAuditMutation'
      );
    END IF;
  END LOOP;
END
$immutable_triggers$;

CREATE UNIQUE INDEX IF NOT EXISTS "WorkflowRun_v2_user_idempotency_key"
ON public."WorkflowRun"("userId", "idempotencyKey")
WHERE "engineVersion" = 2;

CREATE UNIQUE INDEX IF NOT EXISTS "WorkflowRun_v2_writingSession_foreground_key"
ON public."WorkflowRun"("writingSessionId")
WHERE "engineVersion" = 2
  AND "writingSessionId" IS NOT NULL
  AND status IN (
    'pending'::"WorkflowRunStatus",
    'running'::"WorkflowRunStatus",
    'waiting_user'::"WorkflowRunStatus"
  );

CREATE INDEX IF NOT EXISTS "WorkflowRun_v2_novel_status_created_idx"
ON public."WorkflowRun"("novelId", status, "createdAt")
WHERE "engineVersion" = 2;

CREATE INDEX IF NOT EXISTS "WorkflowRun_v2_parentRunId_idx"
ON public."WorkflowRun"("parentRunId")
WHERE "parentRunId" IS NOT NULL;

CREATE INDEX IF NOT EXISTS "WorkflowRun_v2_writingSessionId_idx"
ON public."WorkflowRun"("writingSessionId")
WHERE "writingSessionId" IS NOT NULL;

CREATE INDEX IF NOT EXISTS "WorkflowRun_v2_target_idx"
ON public."WorkflowRun"("novelId", "targetType", "targetId")
WHERE "engineVersion" = 2 AND "targetType" IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS "WorkflowStep_run_ordinal_key"
ON public."WorkflowStep"("runId", ordinal)
WHERE ordinal IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS "WorkflowStep_run_idempotency_key"
ON public."WorkflowStep"("runId", "idempotencyKey")
WHERE "idempotencyKey" IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS "WorkflowStep_activeJobId_key"
ON public."WorkflowStep"("activeJobId")
WHERE "activeJobId" IS NOT NULL;

CREATE INDEX IF NOT EXISTS "WorkflowStep_due_idx"
ON public."WorkflowStep"(lane, status, "nextAttemptAt", "createdAt")
WHERE ordinal IS NOT NULL
  AND status IN (
    'pending'::"WorkflowStepStatus",
    'running'::"WorkflowStepStatus"
  );

CREATE INDEX IF NOT EXISTS "WorkflowStep_run_ordinal_idx"
ON public."WorkflowStep"("runId", ordinal)
WHERE ordinal IS NOT NULL;

CREATE INDEX IF NOT EXISTS "WorkflowEvidenceItem_bundle_ordinal_idx"
ON public."WorkflowEvidenceItem"("bundleId", ordinal);

CREATE INDEX IF NOT EXISTS "WorkflowEvent_run_sequence_idx"
ON public."WorkflowEvent"("runId", sequence);

CREATE INDEX IF NOT EXISTS "WorkflowEvaluation_run_created_idx"
ON public."WorkflowEvaluation"("runId", "createdAt");

CREATE INDEX IF NOT EXISTS "WorkflowEvaluation_artifact_revision_idx"
ON public."WorkflowEvaluation"("artifactId", "artifactRevision");

CREATE INDEX IF NOT EXISTS "WorkflowBillingReservation_run_created_idx"
ON public."WorkflowBillingReservation"("runId", "createdAt");

CREATE INDEX IF NOT EXISTS "WorkflowBillingReservation_user_status_idx"
ON public."WorkflowBillingReservation"("userId", status, "createdAt")
WHERE status IN ('reserved', 'reconciliation_required');

COMMENT ON TABLE public."WorkflowEvidenceBundle" IS 'V2 WorkflowRun 的不可变证据清单';
COMMENT ON TABLE public."WorkflowEvidenceItem" IS '证据清单中的完整文本或 JSON 内容';
COMMENT ON TABLE public."WorkflowEvent" IS '与权威工作流状态同事务提交、供 SSE 回放的持久事件';
COMMENT ON TABLE public."WorkflowEvaluation" IS '绑定证据与候选 revision 的结构化 Reviewer 结果';
COMMENT ON TABLE public."WorkflowBillingReservation" IS '逐逻辑模型 Step 的积分预留、幂等结算与未知用量对账边界';
COMMENT ON COLUMN public."WorkflowRun"."engineVersion" IS 'NULL/1 为旧引擎兼容记录，2 为 Core 拥有的耐久执行';
COMMENT ON COLUMN public."WorkflowRun"."lastEventSequence" IS '该 Run 已提交的最后一个 WorkflowEvent 序号';
COMMENT ON COLUMN public."WorkflowStep"."fencingToken" IS '执行租约代次；迟到结果必须以此做 CAS 拒绝';

-- 新表由 Core 所有；迁移账户可能是管理员，因此显式对齐现有 WorkflowRun 表所有者。
DO $ownership$
DECLARE
  expected_owner OID;
  expected_owner_name TEXT;
  relation_name TEXT;
  function_name TEXT;
  actual_owner OID;
BEGIN
  SELECT relation.relowner
  INTO expected_owner
  FROM pg_class AS relation
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  WHERE namespace.nspname = 'public'
    AND relation.relname = 'WorkflowRun'
    AND relation.relkind IN ('r', 'p');

  expected_owner_name := pg_get_userbyid(expected_owner);
  IF expected_owner IS NULL OR expected_owner_name IS NULL THEN
    RAISE EXCEPTION 'WorkflowRun 表所有者无法解析';
  END IF;

  FOREACH relation_name IN ARRAY ARRAY[
    'WorkflowEvidenceBundle',
    'WorkflowEvidenceItem',
    'WorkflowEvent',
    'WorkflowEvaluation',
    'WorkflowBillingReservation'
  ]
  LOOP
    SELECT relation.relowner
    INTO actual_owner
    FROM pg_class AS relation
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'public'
      AND relation.relname = relation_name
      AND relation.relkind IN ('r', 'p');

    IF actual_owner IS NULL THEN
      RAISE EXCEPTION '% 表所有者无法解析', relation_name;
    END IF;
    IF actual_owner <> expected_owner THEN
      EXECUTE format('ALTER TABLE public.%I OWNER TO %I', relation_name, expected_owner_name);
    END IF;
  END LOOP;

  FOREACH function_name IN ARRAY ARRAY[
    'rejectWorkflowAuditMutation',
    'rejectWorkflowBillingIdentityMutation',
    'rejectWorkflowRunV2IdentityMutation',
    'rejectWorkflowStepV2IdentityMutation'
  ]
  LOOP
    SELECT procedure_row.proowner
    INTO actual_owner
    FROM pg_catalog.pg_proc AS procedure_row
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = procedure_row.pronamespace
    WHERE namespace.nspname = 'public'
      AND procedure_row.proname = function_name
      AND procedure_row.pronargs = 0;
    IF actual_owner IS NULL THEN
      RAISE EXCEPTION '% trigger function 所有者无法解析', function_name;
    END IF;
    IF actual_owner <> expected_owner THEN
      EXECUTE format(
        'ALTER FUNCTION public.%I() OWNER TO %I',
        function_name,
        expected_owner_name
      );
    END IF;
  END LOOP;
END
$ownership$;

-- IF NOT EXISTS 不校验同名漂移；重跑结束前核对列、约束、索引、触发器与所有者的真实定义。
DO $postcondition$
DECLARE
  required RECORD;
  missing_items TEXT[] := ARRAY[]::TEXT[];
  expected_owner OID;
  actual_owner OID;
  actual_type TEXT;
  actual_not_null BOOLEAN;
  actual_definition TEXT;
  actual_columns TEXT[];
  actual_unique BOOLEAN;
  actual_predicate TEXT;
BEGIN
  FOR required IN
    SELECT * FROM (VALUES
      ('WorkflowRun', 'novelId', 'text', FALSE),
      ('WorkflowRun', 'chapterId', 'text', FALSE),
      ('WorkflowRun', 'engineVersion', 'integer', FALSE),
      ('WorkflowRun', 'workflow', 'text', FALSE),
      ('WorkflowRun', 'operation', 'text', FALSE),
      ('WorkflowRun', 'operationCatalogVersion', 'text', FALSE),
      ('WorkflowRun', 'writingSessionId', 'text', FALSE),
      ('WorkflowRun', 'parentRunId', 'text', FALSE),
      ('WorkflowRun', 'idempotencyKey', 'text', FALSE),
      ('WorkflowRun', 'requestHash', 'text', FALSE),
      ('WorkflowRun', 'targetType', 'text', FALSE),
      ('WorkflowRun', 'targetId', 'text', FALSE),
      ('WorkflowRun', 'budgetJson', 'text', FALSE),
      ('WorkflowRun', 'modelPolicyJson', 'text', FALSE),
      ('WorkflowRun', 'currentEvidenceBundleId', 'text', FALSE),
      ('WorkflowRun', 'lastEventSequence', 'bigint', FALSE),
      ('WorkflowRun', 'revision', 'integer', FALSE),
      ('WorkflowRun', 'cancelRequestId', 'text', FALSE),
      ('WorkflowRun', 'cancelRequestedAt', 'timestamp(3) without time zone', FALSE),
      ('WorkflowRun', 'completedAt', 'timestamp(3) without time zone', FALSE),
      ('WorkflowRun', 'errorCode', 'text', FALSE),
      ('WorkflowStep', 'ordinal', 'integer', FALSE),
      ('WorkflowStep', 'purpose', 'text', FALSE),
      ('WorkflowStep', 'lane', 'text', FALSE),
      ('WorkflowStep', 'attemptCount', 'integer', FALSE),
      ('WorkflowStep', 'nextAttemptAt', 'timestamp(3) without time zone', FALSE),
      ('WorkflowStep', 'fencingToken', 'bigint', FALSE),
      ('WorkflowStep', 'leaseExpiresAt', 'timestamp(3) without time zone', FALSE),
      ('WorkflowStep', 'heartbeatAt', 'timestamp(3) without time zone', FALSE),
      ('WorkflowStep', 'activeJobId', 'text', FALSE),
      ('WorkflowStep', 'idempotencyKey', 'text', FALSE),
      ('WorkflowStep', 'requestHash', 'text', FALSE),
      ('WorkflowStep', 'inputHash', 'text', FALSE),
      ('WorkflowStep', 'resultHash', 'text', FALSE),
      ('WorkflowStep', 'evidenceBundleId', 'text', FALSE),
      ('WorkflowStep', 'artifactId', 'text', FALSE),
      ('WorkflowStep', 'artifactRevision', 'integer', FALSE),
      ('WorkflowStep', 'modelProfile', 'text', FALSE),
      ('WorkflowStep', 'modelProfileVersion', 'text', FALSE),
      ('WorkflowStep', 'outputSchema', 'text', FALSE),
      ('WorkflowStep', 'outputSchemaVersion', 'text', FALSE),
      ('WorkflowStep', 'budgetJson', 'text', FALSE),
      ('WorkflowStep', 'resolvedModelJson', 'text', FALSE),
      ('WorkflowStep', 'usageJson', 'text', FALSE),
      ('WorkflowStep', 'lastProgressSequence', 'bigint', FALSE),
      ('WorkflowStep', 'cancelRequestId', 'text', FALSE),
      ('WorkflowStep', 'submittedAt', 'timestamp(3) without time zone', FALSE),
      ('WorkflowStep', 'updatedAt', 'timestamp(3) without time zone', FALSE),
      ('WorkflowStep', 'completedAt', 'timestamp(3) without time zone', FALSE),
      ('WorkflowStep', 'errorCode', 'text', FALSE),
      ('WorkflowEvidenceBundle', 'id', 'text', TRUE),
      ('WorkflowEvidenceBundle', 'runId', 'text', TRUE),
      ('WorkflowEvidenceBundle', 'version', 'integer', TRUE),
      ('WorkflowEvidenceBundle', 'manifestJson', 'text', TRUE),
      ('WorkflowEvidenceBundle', 'manifestSha256', 'text', TRUE),
      ('WorkflowEvidenceBundle', 'totalBytes', 'bigint', TRUE),
      ('WorkflowEvidenceItem', 'id', 'text', TRUE),
      ('WorkflowEvidenceItem', 'bundleId', 'text', TRUE),
      ('WorkflowEvidenceItem', 'ordinal', 'integer', TRUE),
      ('WorkflowEvidenceItem', 'exists', 'boolean', TRUE),
      ('WorkflowEvidenceItem', 'resourceRevision', 'integer', FALSE),
      ('WorkflowEvidenceItem', 'contentType', 'text', FALSE),
      ('WorkflowEvidenceItem', 'contentSha256', 'text', FALSE),
      ('WorkflowEvidenceItem', 'byteCount', 'bigint', TRUE),
      ('WorkflowEvidenceItem', 'metadataJson', 'text', TRUE),
      ('WorkflowEvent', 'sequence', 'bigint', TRUE),
      ('WorkflowEvent', 'payloadJson', 'text', TRUE),
      ('WorkflowEvaluation', 'artifactId', 'text', FALSE),
      ('WorkflowEvaluation', 'artifactRevision', 'integer', FALSE),
      ('WorkflowEvaluation', 'executionStatus', 'text', TRUE),
      ('WorkflowEvaluation', 'contentVerdict', 'text', TRUE),
      ('WorkflowEvaluation', 'findingsJson', 'text', TRUE),
      ('WorkflowBillingReservation', 'id', 'text', TRUE),
      ('WorkflowBillingReservation', 'runId', 'text', TRUE),
      ('WorkflowBillingReservation', 'stepId', 'text', TRUE),
      ('WorkflowBillingReservation', 'userId', 'text', TRUE),
      ('WorkflowBillingReservation', 'requestId', 'text', TRUE),
      ('WorkflowBillingReservation', 'pricingVersion', 'text', TRUE),
      ('WorkflowBillingReservation', 'pricingJson', 'text', TRUE),
      ('WorkflowBillingReservation', 'reservedMicros', 'bigint', TRUE),
      ('WorkflowBillingReservation', 'chargedMicros', 'bigint', TRUE),
      ('WorkflowBillingReservation', 'usageJson', 'text', FALSE),
      ('WorkflowBillingReservation', 'status', 'text', TRUE),
      ('WorkflowBillingReservation', 'createdAt', 'timestamp(3) without time zone', TRUE),
      ('WorkflowBillingReservation', 'updatedAt', 'timestamp(3) without time zone', TRUE),
      ('WorkflowBillingReservation', 'settledAt', 'timestamp(3) without time zone', FALSE)
    ) AS expected(table_name, column_name, type_name, not_null)
  LOOP
    SELECT
      pg_catalog.format_type(attribute.atttypid, attribute.atttypmod),
      attribute.attnotnull
    INTO actual_type, actual_not_null
    FROM pg_catalog.pg_attribute AS attribute
    WHERE attribute.attrelid = pg_catalog.to_regclass(
        pg_catalog.format('public.%I', required.table_name)
      )
      AND attribute.attname = required.column_name
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped;

    IF actual_type IS DISTINCT FROM required.type_name
        OR actual_not_null IS DISTINCT FROM required.not_null THEN
      missing_items := pg_catalog.array_append(
        missing_items,
        required.table_name || '.' || required.column_name || ':type_or_nullability'
      );
    END IF;
  END LOOP;

  FOR required IN
    SELECT * FROM (VALUES
      ('WorkflowRun', 'WorkflowRun_engineVersion_check'),
      ('WorkflowRun', 'WorkflowRun_v1_scope_check'),
      ('WorkflowRun', 'WorkflowRun_v2_shape_check'),
      ('WorkflowRun', 'WorkflowRun_cancel_binding_check'),
      ('WorkflowRun', 'WorkflowRun_userId_fkey'),
      ('WorkflowRun', 'WorkflowRun_novel_user_fkey'),
      ('WorkflowRun', 'WorkflowRun_writingSessionId_fkey'),
      ('WorkflowRun', 'WorkflowRun_writingSession_scope_fkey'),
      ('WorkflowRun', 'WorkflowRun_parentRunId_fkey'),
      ('WorkflowRun', 'WorkflowRun_parent_user_fkey'),
      ('WorkflowRun', 'WorkflowRun_parent_novel_fkey'),
      ('WorkflowRun', 'WorkflowRun_currentEvidenceBundleId_fkey'),
      ('WorkflowStep', 'WorkflowStep_v2_shape_check'),
      ('WorkflowStep', 'WorkflowStep_lease_check'),
      ('WorkflowStep', 'WorkflowStep_artifact_binding_check'),
      ('WorkflowStep', 'WorkflowStep_resolvedModelJson_check'),
      ('WorkflowStep', 'WorkflowStep_usageJson_check'),
      ('WorkflowStep', 'WorkflowStep_progress_sequence_check'),
      ('WorkflowStep', 'WorkflowStep_resolved_model_binding_check'),
      ('WorkflowStep', 'WorkflowStep_cancel_binding_check'),
      ('WorkflowStep', 'WorkflowStep_cancel_run_fkey'),
      ('WorkflowStep', 'WorkflowStep_evidence_run_fkey'),
      ('WorkflowStep', 'WorkflowStep_artifact_revision_fkey'),
      ('WorkflowStep', 'WorkflowStep_artifact_run_fkey'),
      ('ReviewArtifact', 'ReviewArtifact_workflowRunId_fkey'),
      ('ReviewArtifact', 'ReviewArtifact_workflow_owner_exclusive_check'),
      ('ReviewArtifact', 'ReviewArtifact_workflow_run_novel_fkey'),
      ('WorkflowEvidenceBundle', 'WorkflowEvidenceBundle_run_version_key'),
      ('WorkflowEvidenceItem', 'WorkflowEvidenceItem_content_exclusive_check'),
      ('WorkflowEvidenceItem', 'WorkflowEvidenceItem_existence_shape_check'),
      ('WorkflowEvent', 'WorkflowEvent_run_sequence_key'),
      ('WorkflowEvent', 'WorkflowEvent_run_dedupe_key'),
      ('WorkflowEvaluation', 'WorkflowEvaluation_runId_fkey'),
      ('WorkflowEvaluation', 'WorkflowEvaluation_step_run_fkey'),
      ('WorkflowEvaluation', 'WorkflowEvaluation_step_evidence_fkey'),
      ('WorkflowEvaluation', 'WorkflowEvaluation_step_exact_fkey'),
      ('WorkflowEvaluation', 'WorkflowEvaluation_evidence_run_fkey'),
      ('WorkflowEvaluation', 'WorkflowEvaluation_artifact_revision_fkey'),
      ('WorkflowEvaluation', 'WorkflowEvaluation_artifact_run_fkey'),
      ('WorkflowEvaluation', 'WorkflowEvaluation_artifact_binding_check'),
      ('WorkflowEvaluation', 'WorkflowEvaluation_execution_content_check'),
      ('WorkflowBillingReservation', 'WorkflowBillingReservation_stepId_key'),
      ('WorkflowBillingReservation', 'WorkflowBillingReservation_requestId_key'),
      ('WorkflowBillingReservation', 'WorkflowBillingReservation_run_user_fkey'),
      ('WorkflowBillingReservation', 'WorkflowBillingReservation_step_run_fkey'),
      ('WorkflowBillingReservation', 'WorkflowBillingReservation_userId_fkey'),
      ('WorkflowBillingReservation', 'WorkflowBillingReservation_pricing_check'),
      ('WorkflowBillingReservation', 'WorkflowBillingReservation_amount_check'),
      ('WorkflowBillingReservation', 'WorkflowBillingReservation_status_shape_check'),
      ('WorkflowBillingReservation', 'WorkflowBillingReservation_time_order_check')
    ) AS expected(table_name, constraint_name)
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_catalog.pg_constraint AS constraint_row
      WHERE constraint_row.conrelid = pg_catalog.to_regclass(
          pg_catalog.format('public.%I', required.table_name)
        )
        AND constraint_row.conname = required.constraint_name
        AND constraint_row.convalidated
    ) THEN
      missing_items := pg_catalog.array_append(
        missing_items,
        required.table_name || '.' || required.constraint_name
      );
    END IF;
  END LOOP;

  FOR required IN
    SELECT * FROM (VALUES
      ('WorkflowRun', 'WorkflowRun_v1_scope_check', ARRAY[
        '"engineversion"',
        '"novelid" is not null',
        '"chapterid" is not null'
      ]::TEXT[]),
      ('WorkflowRun', 'WorkflowRun_novel_user_fkey', ARRAY[
        'foreign key ("novelid", "userid")',
        'references "novel"(id, "userid")'
      ]::TEXT[]),
      ('WorkflowRun', 'WorkflowRun_writingSession_scope_fkey', ARRAY[
        'foreign key ("writingsessionid", "novelid", "chapterid")',
        'references "writingsession"(id, "novelid", "chapterid")'
      ]::TEXT[]),
      ('WorkflowRun', 'WorkflowRun_parent_user_fkey', ARRAY[
        'foreign key ("parentrunid", "userid")',
        'references "workflowrun"(id, "userid")'
      ]::TEXT[]),
      ('WorkflowRun', 'WorkflowRun_cancel_binding_check', ARRAY[
        '"cancelrequestid" is null',
        '"cancelrequestedat" is null',
        '"cancelrequestid" is not null',
        '"cancelrequestedat" is not null',
        'cancelled'
      ]::TEXT[]),
      ('WorkflowStep', 'WorkflowStep_v2_shape_check', ARRAY[
        'status', 'pending', '"nextattemptat" is not null'
      ]::TEXT[]),
      ('WorkflowStep', 'WorkflowStep_resolvedModelJson_check', ARRAY[
        '"resolvedmodeljson" is null', 'jsonb_typeof'
      ]::TEXT[]),
      ('WorkflowStep', 'WorkflowStep_usageJson_check', ARRAY[
        '"usagejson" is null', 'jsonb_typeof'
      ]::TEXT[]),
      ('WorkflowStep', 'WorkflowStep_progress_sequence_check', ARRAY[
        '"lastprogresssequence" is null', '"lastprogresssequence" >= 0',
        '"usagejson" is not null'
      ]::TEXT[]),
      ('WorkflowStep', 'WorkflowStep_artifact_binding_check', ARRAY[
        '"artifactid" is null', '"artifactrevision" is null',
        '"artifactid" is not null', '"artifactrevision" is not null',
        '"artifactrevision" > 0'
      ]::TEXT[]),
      ('WorkflowStep', 'WorkflowStep_cancel_run_fkey', ARRAY[
        'foreign key ("runid", "cancelrequestid")',
        'references "workflowrun"(id, "cancelrequestid")'
      ]::TEXT[]),
      ('WorkflowStep', 'WorkflowStep_artifact_run_fkey', ARRAY[
        'foreign key ("artifactid", "runid")',
        'references "reviewartifact"(id, "workflowrunid")'
      ]::TEXT[]),
      ('ReviewArtifact', 'ReviewArtifact_workflowRunId_fkey', ARRAY[
        'foreign key ("workflowrunid")',
        'references "workflowrun"(id)',
        'on delete restrict'
      ]::TEXT[]),
      ('ReviewArtifact', 'ReviewArtifact_workflow_run_novel_fkey', ARRAY[
        'foreign key ("workflowrunid", "novelid")',
        'references "workflowrun"(id, "novelid")'
      ]::TEXT[]),
      ('WorkflowEvidenceItem', 'WorkflowEvidenceItem_existence_shape_check', ARRAY[
        'not "exists"', '"bytecount" = 0', '"contentsha256" is null'
      ]::TEXT[]),
      ('WorkflowEvaluation', 'WorkflowEvaluation_step_exact_fkey', ARRAY[
        '"stepid", "runid", "evidencebundleid", "artifactid", "artifactrevision"',
        'references "workflowstep"'
      ]::TEXT[]),
      ('WorkflowEvaluation', 'WorkflowEvaluation_step_evidence_fkey', ARRAY[
        'foreign key ("stepid", "runid", "evidencebundleid")',
        'references "workflowstep"(id, "runid", "evidencebundleid")'
      ]::TEXT[]),
      ('WorkflowEvaluation', 'WorkflowEvaluation_artifact_binding_check', ARRAY[
        '"artifactid" is null', '"artifactrevision" is null',
        '"artifactid" is not null', '"artifactrevision" is not null',
        '"artifactrevision" > 0'
      ]::TEXT[]),
      ('WorkflowEvaluation', 'WorkflowEvaluation_artifact_run_fkey', ARRAY[
        'foreign key ("artifactid", "runid")',
        'references "reviewartifact"(id, "workflowrunid")'
      ]::TEXT[]),
      ('WorkflowBillingReservation', 'WorkflowBillingReservation_run_user_fkey', ARRAY[
        'foreign key ("runid", "userid")',
        'references "workflowrun"(id, "userid")',
        'on delete restrict'
      ]::TEXT[]),
      ('WorkflowBillingReservation', 'WorkflowBillingReservation_step_run_fkey', ARRAY[
        'foreign key ("stepid", "runid")',
        'references "workflowstep"(id, "runid")',
        'on delete restrict'
      ]::TEXT[]),
      ('WorkflowBillingReservation', 'WorkflowBillingReservation_status_shape_check', ARRAY[
        'reserved', 'settled', 'released', 'reconciliation_required',
        '"usagejson" is null', '"usagejson" is not null', '"settledat" is not null'
      ]::TEXT[])
    ) AS expected(table_name, constraint_name, required_tokens)
  LOOP
    SELECT pg_catalog.lower(
      pg_catalog.regexp_replace(
        pg_catalog.pg_get_constraintdef(constraint_row.oid),
        '[[:space:]]+',
        ' ',
        'g'
      )
    )
    INTO actual_definition
    FROM pg_catalog.pg_constraint AS constraint_row
    WHERE constraint_row.conrelid = pg_catalog.to_regclass(
        pg_catalog.format('public.%I', required.table_name)
      )
      AND constraint_row.conname = required.constraint_name;

    IF actual_definition IS NULL OR EXISTS (
      SELECT 1
      FROM pg_catalog.unnest(required.required_tokens) AS required_token
      WHERE pg_catalog.strpos(actual_definition, required_token) = 0
    ) THEN
      missing_items := pg_catalog.array_append(
        missing_items,
        required.table_name || '.' || required.constraint_name || ':definition'
      );
    END IF;
  END LOOP;

  FOR required IN
    SELECT * FROM (VALUES
      ('WritingSession_id_novel_chapter_key', TRUE, ARRAY['id', '"novelId"', '"chapterId"']::TEXT[], ARRAY[]::TEXT[]),
      ('WorkflowRun_id_userId_key', TRUE, ARRAY['id', '"userId"']::TEXT[], ARRAY[]::TEXT[]),
      ('WorkflowRun_id_novelId_key', TRUE, ARRAY['id', '"novelId"']::TEXT[], ARRAY[]::TEXT[]),
      ('WorkflowRun_id_cancelRequestId_key', TRUE, ARRAY['id', '"cancelRequestId"']::TEXT[], ARRAY[]::TEXT[]),
      ('ReviewArtifact_id_workflowRunId_key', TRUE, ARRAY['id', '"workflowRunId"']::TEXT[], ARRAY[]::TEXT[]),
      ('WorkflowStep_id_runId_key', TRUE, ARRAY['id', '"runId"']::TEXT[], ARRAY[]::TEXT[]),
      ('WorkflowStep_evaluation_binding_key', TRUE, ARRAY[
        'id', '"runId"', '"evidenceBundleId"', '"artifactId"', '"artifactRevision"'
      ]::TEXT[], ARRAY[]::TEXT[]),
      ('WorkflowStep_evaluation_context_key', TRUE, ARRAY[
        'id', '"runId"', '"evidenceBundleId"'
      ]::TEXT[], ARRAY[]::TEXT[]),
      ('WorkflowRun_v2_user_idempotency_key', TRUE, ARRAY['"userId"', '"idempotencyKey"']::TEXT[], ARRAY['"engineversion" = 2']::TEXT[]),
      ('WorkflowRun_v2_writingSession_foreground_key', TRUE, ARRAY['"writingSessionId"']::TEXT[], ARRAY[
        '"engineversion" = 2', '"writingsessionid" is not null',
        'pending', 'running', 'waiting_user'
      ]::TEXT[]),
      ('WorkflowRun_v2_novel_status_created_idx', FALSE, ARRAY['"novelId"', 'status', '"createdAt"']::TEXT[], ARRAY['"engineversion" = 2']::TEXT[]),
      ('WorkflowStep_run_ordinal_key', TRUE, ARRAY['"runId"', 'ordinal']::TEXT[], ARRAY['ordinal is not null']::TEXT[]),
      ('WorkflowStep_run_idempotency_key', TRUE, ARRAY['"runId"', '"idempotencyKey"']::TEXT[], ARRAY['"idempotencykey" is not null']::TEXT[]),
      ('WorkflowStep_due_idx', FALSE, ARRAY['lane', 'status', '"nextAttemptAt"', '"createdAt"']::TEXT[], ARRAY[
        'ordinal is not null', 'pending', 'running'
      ]::TEXT[]),
      ('WorkflowEvent_run_sequence_idx', FALSE, ARRAY['"runId"', 'sequence']::TEXT[], ARRAY[]::TEXT[]),
      ('WorkflowEvaluation_run_created_idx', FALSE, ARRAY['"runId"', '"createdAt"']::TEXT[], ARRAY[]::TEXT[]),
      ('WorkflowBillingReservation_run_created_idx', FALSE, ARRAY['"runId"', '"createdAt"']::TEXT[], ARRAY[]::TEXT[]),
      ('WorkflowBillingReservation_user_status_idx', FALSE, ARRAY['"userId"', 'status', '"createdAt"']::TEXT[], ARRAY[
        'reserved', 'reconciliation_required'
      ]::TEXT[])
    ) AS expected(index_name, is_unique, columns, predicate_tokens)
  LOOP
    SELECT
      index_row.indisunique,
      ARRAY(
        SELECT pg_catalog.pg_get_indexdef(
          index_row.indexrelid,
          ordinal.value,
          TRUE
        )
        FROM pg_catalog.generate_series(1, index_row.indnkeyatts) AS ordinal(value)
        ORDER BY ordinal.value
      ),
      pg_catalog.lower(COALESCE(
        pg_catalog.pg_get_expr(index_row.indpred, index_row.indrelid),
        ''
      ))
    INTO actual_unique, actual_columns, actual_predicate
    FROM pg_catalog.pg_index AS index_row
    WHERE index_row.indexrelid = pg_catalog.to_regclass(
      pg_catalog.format('public.%I', required.index_name)
    );

    IF actual_unique IS DISTINCT FROM required.is_unique
        OR actual_columns IS DISTINCT FROM required.columns
        OR EXISTS (
          SELECT 1
          FROM pg_catalog.unnest(required.predicate_tokens) AS predicate_token
          WHERE pg_catalog.strpos(actual_predicate, predicate_token) = 0
        ) THEN
      missing_items := pg_catalog.array_append(
        missing_items,
        required.index_name || ':definition'
      );
    END IF;
  END LOOP;

  SELECT pg_catalog.lower(pg_catalog.pg_get_triggerdef(trigger_row.oid))
  INTO actual_definition
  FROM pg_catalog.pg_trigger AS trigger_row
  WHERE trigger_row.tgrelid = 'public."WorkflowBillingReservation"'::pg_catalog.regclass
    AND trigger_row.tgname = 'WorkflowBillingReservation_identity_immutable_trigger'
    AND trigger_row.tgenabled = 'O'
    AND NOT trigger_row.tgisinternal;

  IF actual_definition IS NULL
      OR pg_catalog.strpos(actual_definition, 'before update') = 0
      OR pg_catalog.strpos(actual_definition, 'rejectworkflowbillingidentitymutation') = 0 THEN
    missing_items := pg_catalog.array_append(
      missing_items,
      'WorkflowBillingReservation.WorkflowBillingReservation_identity_immutable_trigger:definition'
    );
  END IF;

  FOR required IN
    SELECT * FROM (VALUES
      (
        'WorkflowRun',
        'WorkflowRun_v2_identity_immutable_trigger',
        'rejectworkflowrunv2identitymutation'
      ),
      (
        'WorkflowStep',
        'WorkflowStep_v2_identity_immutable_trigger',
        'rejectworkflowstepv2identitymutation'
      )
    ) AS expected(table_name, trigger_name, function_token)
  LOOP
    SELECT pg_catalog.lower(pg_catalog.pg_get_triggerdef(trigger_row.oid))
    INTO actual_definition
    FROM pg_catalog.pg_trigger AS trigger_row
    WHERE trigger_row.tgrelid = pg_catalog.to_regclass(
        pg_catalog.format('public.%I', required.table_name)
      )
      AND trigger_row.tgname = required.trigger_name
      AND trigger_row.tgenabled = 'O'
      AND NOT trigger_row.tgisinternal;

    IF actual_definition IS NULL
        OR pg_catalog.strpos(actual_definition, 'before') = 0
        OR pg_catalog.strpos(actual_definition, 'update') = 0
        OR pg_catalog.strpos(actual_definition, 'delete') = 0
        OR pg_catalog.strpos(actual_definition, required.function_token) = 0 THEN
      missing_items := pg_catalog.array_append(
        missing_items,
        required.table_name || '.' || required.trigger_name || ':definition'
      );
    END IF;
  END LOOP;

  FOR required IN
    SELECT * FROM (VALUES
      ('WorkflowEvidenceBundle', 'WorkflowEvidenceBundle_immutable_trigger'),
      ('WorkflowEvidenceItem', 'WorkflowEvidenceItem_immutable_trigger'),
      ('WorkflowEvent', 'WorkflowEvent_immutable_trigger'),
      ('WorkflowEvaluation', 'WorkflowEvaluation_immutable_trigger')
    ) AS expected(table_name, trigger_name)
  LOOP
    SELECT pg_catalog.lower(pg_catalog.pg_get_triggerdef(trigger_row.oid))
    INTO actual_definition
    FROM pg_catalog.pg_trigger AS trigger_row
    WHERE trigger_row.tgrelid = pg_catalog.to_regclass(
        pg_catalog.format('public.%I', required.table_name)
      )
      AND trigger_row.tgname = required.trigger_name
      AND trigger_row.tgenabled = 'O'
      AND NOT trigger_row.tgisinternal;

    IF actual_definition IS NULL
        OR pg_catalog.strpos(actual_definition, 'before delete or update') = 0
        OR pg_catalog.strpos(actual_definition, 'rejectworkflowauditmutation') = 0 THEN
      missing_items := pg_catalog.array_append(
        missing_items,
        required.table_name || '.' || required.trigger_name || ':definition'
      );
    END IF;
  END LOOP;

  SELECT relation.relowner
  INTO expected_owner
  FROM pg_catalog.pg_class AS relation
  WHERE relation.oid = 'public."WorkflowRun"'::pg_catalog.regclass;

  FOR required IN
    SELECT * FROM (VALUES
      ('WorkflowEvidenceBundle'),
      ('WorkflowEvidenceItem'),
      ('WorkflowEvent'),
      ('WorkflowEvaluation'),
      ('WorkflowBillingReservation')
    ) AS expected(table_name)
  LOOP
    SELECT relation.relowner
    INTO actual_owner
    FROM pg_catalog.pg_class AS relation
    WHERE relation.oid = pg_catalog.to_regclass(
      pg_catalog.format('public.%I', required.table_name)
    );
    IF actual_owner IS DISTINCT FROM expected_owner THEN
      missing_items := pg_catalog.array_append(
        missing_items,
        required.table_name || ':owner'
      );
    END IF;
  END LOOP;

  FOR required IN
    SELECT * FROM (VALUES
      ('rejectWorkflowAuditMutation'),
      ('rejectWorkflowBillingIdentityMutation'),
      ('rejectWorkflowRunV2IdentityMutation'),
      ('rejectWorkflowStepV2IdentityMutation')
    ) AS expected(function_name)
  LOOP
    SELECT procedure_row.proowner
    INTO actual_owner
    FROM pg_catalog.pg_proc AS procedure_row
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = procedure_row.pronamespace
    WHERE namespace.nspname = 'public'
      AND procedure_row.proname = required.function_name
      AND procedure_row.pronargs = 0;
    IF actual_owner IS DISTINCT FROM expected_owner THEN
      missing_items := pg_catalog.array_append(
        missing_items,
        required.function_name || '():owner'
      );
    END IF;
  END LOOP;

  IF pg_catalog.cardinality(missing_items) > 0 THEN
    RAISE EXCEPTION '耐久 Agent 执行迁移后结构不完整或发生漂移：%', missing_items;
  END IF;
END
$postcondition$;

COMMIT;
