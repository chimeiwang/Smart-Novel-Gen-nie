BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 本迁移只获得服务器端 novelwriterdev 开发库授权；生产库和其他数据库必须主动拒绝。
DO $safety$
BEGIN
  IF current_database() <> 'novelwriterdev' THEN
    RAISE EXCEPTION '逐镜视频生成 P0 迁移只允许在 novelwriterdev 执行，当前数据库为 %', current_database();
  END IF;
END
$safety$;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260824:video-shot-render-p0'));

CREATE TABLE IF NOT EXISTS "VideoShotRenderTask" (
  "id" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "shotId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "promptVersionId" TEXT NOT NULL,
  "retryOfTaskId" TEXT,
  "provider" TEXT NOT NULL DEFAULT 'seedance'::text,
  "model" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'pending'::text,
  "clientRequestId" TEXT NOT NULL,
  "inputHash" TEXT NOT NULL,
  "requestManifestJson" TEXT NOT NULL,
  "providerTaskId" TEXT,
  "pollCount" INTEGER NOT NULL DEFAULT 0,
  "attemptCount" INTEGER NOT NULL DEFAULT 0,
  "nextAttemptAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "lastErrorCode" TEXT,
  "lastErrorMessage" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  "submittedAt" TIMESTAMP(3),
  "completedAt" TIMESTAMP(3),
  CONSTRAINT "VideoShotRenderTask_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoShotRenderTask_adaptation_project_fkey"
    FOREIGN KEY ("adaptationId", "projectId")
    REFERENCES "VideoChapterAdaptation"("id", "projectId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotRenderTask_adaptation_novel_fkey"
    FOREIGN KEY ("adaptationId", "novelId")
    REFERENCES "VideoChapterAdaptation"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotRenderTask_project_novel_fkey"
    FOREIGN KEY ("projectId", "novelId")
    REFERENCES "VideoProject"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotRenderTask_plan_adaptation_fkey"
    FOREIGN KEY ("shotPlanVersionId", "adaptationId")
    REFERENCES "VideoShotPlanVersion"("id", "adaptationId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotRenderTask_shot_plan_fkey"
    FOREIGN KEY ("shotId", "shotPlanVersionId")
    REFERENCES "VideoShot"("id", "planVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotRenderTask_prompt_scope_fkey"
    FOREIGN KEY ("promptVersionId", "shotId", "shotPlanVersionId")
    REFERENCES "VideoShotPromptVersion"("id", "shotId", "shotPlanVersionId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotRenderTask_retry_shot_fkey"
    FOREIGN KEY ("retryOfTaskId", "shotId")
    REFERENCES "VideoShotRenderTask"("id", "shotId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotRenderTask_provider_check" CHECK ("provider" = 'seedance'),
  CONSTRAINT "VideoShotRenderTask_status_check" CHECK (
    "status" IN (
      'pending', 'submitting', 'submission_unknown', 'queued', 'running',
      'archiving', 'succeeded', 'failed', 'expired', 'cancelled'
    )
  ),
  CONSTRAINT "VideoShotRenderTask_text_check" CHECK (
    btrim("model") <> '' AND btrim("clientRequestId") <> ''
  ),
  CONSTRAINT "VideoShotRenderTask_input_hash_check" CHECK ("inputHash" ~ '^[0-9a-f]{64}$'),
  CONSTRAINT "VideoShotRenderTask_manifest_check" CHECK (
    COALESCE(jsonb_typeof("requestManifestJson"::jsonb) = 'object', FALSE)
  ),
  CONSTRAINT "VideoShotRenderTask_counts_check" CHECK (
    "pollCount" >= 0 AND "attemptCount" >= 0
  ),
  CONSTRAINT "VideoShotRenderTask_provider_task_check" CHECK (
    ("status" IN ('queued', 'running', 'archiving', 'succeeded') AND "providerTaskId" IS NOT NULL)
    OR ("status" NOT IN ('queued', 'running', 'archiving', 'succeeded'))
  ),
  CONSTRAINT "VideoShotRenderTask_id_shot_key" UNIQUE ("id", "shotId")
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotRenderTask_id_scope_key"
ON "VideoShotRenderTask"(
  "id", "adaptationId", "projectId", "novelId", "shotId", "shotPlanVersionId", "promptVersionId"
);
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotRenderTask_shot_client_request_key"
ON "VideoShotRenderTask"("shotId", "clientRequestId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotRenderTask_active_shot_key"
ON "VideoShotRenderTask"("shotId")
WHERE "status" IN ('pending', 'submitting', 'queued', 'running', 'archiving');
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotRenderTask_provider_task_key"
ON "VideoShotRenderTask"("provider", "providerTaskId")
WHERE "providerTaskId" IS NOT NULL;
CREATE INDEX IF NOT EXISTS "VideoShotRenderTask_due_idx"
ON "VideoShotRenderTask"("nextAttemptAt", "createdAt")
WHERE "status" IN ('pending', 'queued', 'running', 'archiving');
CREATE INDEX IF NOT EXISTS "VideoShotRenderTask_shot_created_idx"
ON "VideoShotRenderTask"("shotId", "createdAt");

CREATE TABLE IF NOT EXISTS "VideoShotTake" (
  "id" TEXT NOT NULL,
  "taskId" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "shotId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "promptVersionId" TEXT NOT NULL,
  "assetId" TEXT NOT NULL,
  "takeNo" INTEGER NOT NULL,
  "provider" TEXT NOT NULL,
  "model" TEXT NOT NULL,
  "providerTaskId" TEXT NOT NULL,
  "inputHash" TEXT NOT NULL,
  "providerMetadataJson" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoShotTake_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoShotTake_task_scope_fkey"
    FOREIGN KEY (
      "taskId", "adaptationId", "projectId", "novelId", "shotId",
      "shotPlanVersionId", "promptVersionId"
    ) REFERENCES "VideoShotRenderTask"(
      "id", "adaptationId", "projectId", "novelId", "shotId",
      "shotPlanVersionId", "promptVersionId"
    ) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotTake_asset_project_fkey"
    FOREIGN KEY ("assetId", "projectId") REFERENCES "VideoAsset"("id", "projectId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotTake_take_no_check" CHECK ("takeNo" > 0),
  CONSTRAINT "VideoShotTake_provider_check" CHECK ("provider" = 'seedance'),
  CONSTRAINT "VideoShotTake_text_check" CHECK (
    btrim("model") <> '' AND btrim("providerTaskId") <> ''
  ),
  CONSTRAINT "VideoShotTake_input_hash_check" CHECK ("inputHash" ~ '^[0-9a-f]{64}$'),
  CONSTRAINT "VideoShotTake_metadata_check" CHECK (
    COALESCE(jsonb_typeof("providerMetadataJson"::jsonb) = 'object', FALSE)
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotTake_taskId_key"
ON "VideoShotTake"("taskId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotTake_assetId_key"
ON "VideoShotTake"("assetId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotTake_shot_take_no_key"
ON "VideoShotTake"("shotId", "takeNo");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotTake_id_shot_plan_key"
ON "VideoShotTake"("id", "shotId", "shotPlanVersionId");
CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotTake_id_shot_adaptation_key"
ON "VideoShotTake"("id", "shotId", "adaptationId");
CREATE INDEX IF NOT EXISTS "VideoShotTake_shot_created_idx"
ON "VideoShotTake"("shotId", "createdAt");

CREATE TABLE IF NOT EXISTS "VideoShotTakeHead" (
  "shotId" TEXT NOT NULL,
  "shotPlanVersionId" TEXT NOT NULL,
  "currentTakeId" TEXT,
  "revision" INTEGER NOT NULL DEFAULT 1,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "VideoShotTakeHead_pkey" PRIMARY KEY ("shotId"),
  CONSTRAINT "VideoShotTakeHead_shot_plan_fkey"
    FOREIGN KEY ("shotId", "shotPlanVersionId")
    REFERENCES "VideoShot"("id", "planVersionId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotTakeHead_current_take_fkey"
    FOREIGN KEY ("currentTakeId", "shotId", "shotPlanVersionId")
    REFERENCES "VideoShotTake"("id", "shotId", "shotPlanVersionId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotTakeHead_revision_check" CHECK ("revision" > 0)
);

CREATE TABLE IF NOT EXISTS "VideoShotTakeDecisionCommand" (
  "id" TEXT NOT NULL,
  "requestedByUserId" TEXT NOT NULL,
  "novelId" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "adaptationId" TEXT NOT NULL,
  "shotId" TEXT NOT NULL,
  "takeId" TEXT NOT NULL,
  "clientRequestId" TEXT NOT NULL,
  "expectedRevision" INTEGER NOT NULL,
  "requestHash" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "observedCurrentTakeId" TEXT,
  "resultingRevision" INTEGER,
  "errorCode" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "VideoShotTakeDecisionCommand_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "VideoShotTakeDecisionCommand_user_fkey"
    FOREIGN KEY ("requestedByUserId") REFERENCES "User"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotTakeDecisionCommand_novel_owner_fkey"
    FOREIGN KEY ("novelId", "requestedByUserId") REFERENCES "Novel"("id", "userId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotTakeDecisionCommand_adaptation_project_fkey"
    FOREIGN KEY ("adaptationId", "projectId")
    REFERENCES "VideoChapterAdaptation"("id", "projectId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotTakeDecisionCommand_adaptation_novel_fkey"
    FOREIGN KEY ("adaptationId", "novelId")
    REFERENCES "VideoChapterAdaptation"("id", "novelId")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "VideoShotTakeDecisionCommand_take_scope_fkey"
    FOREIGN KEY ("takeId", "shotId", "adaptationId")
    REFERENCES "VideoShotTake"("id", "shotId", "adaptationId")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "VideoShotTakeDecisionCommand_text_check" CHECK (btrim("clientRequestId") <> ''),
  CONSTRAINT "VideoShotTakeDecisionCommand_revision_check" CHECK (
    "expectedRevision" > 0 AND ("resultingRevision" IS NULL OR "resultingRevision" > 0)
  ),
  CONSTRAINT "VideoShotTakeDecisionCommand_request_hash_check" CHECK (
    "requestHash" ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT "VideoShotTakeDecisionCommand_status_check" CHECK (
    "status" IN ('succeeded', 'conflict', 'rejected')
  ),
  CONSTRAINT "VideoShotTakeDecisionCommand_result_check" CHECK (
    (
      "status" = 'succeeded'
      AND "observedCurrentTakeId" = "takeId"
      AND "resultingRevision" IS NOT NULL
      AND "errorCode" IS NULL
    )
    OR ("status" <> 'succeeded' AND "resultingRevision" IS NULL AND "errorCode" IS NOT NULL)
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS "VideoShotTakeDecisionCommand_user_request_key"
ON "VideoShotTakeDecisionCommand"("requestedByUserId", "clientRequestId");
CREATE INDEX IF NOT EXISTS "VideoShotTakeDecisionCommand_shot_created_idx"
ON "VideoShotTakeDecisionCommand"("shotId", "createdAt");

COMMIT;
