BEGIN;

UPDATE "Novel"
SET "appliedStyleId" = NULL
WHERE "appliedStyleId" IS NOT NULL;

DELETE FROM "StylePortraitTask";
DELETE FROM "StyleReference";
DELETE FROM "WritingStyle";

ALTER TABLE "WritingStyle"
ADD COLUMN "userId" TEXT NOT NULL;

ALTER TABLE "WritingStyle"
ADD CONSTRAINT "WritingStyle_userId_fkey"
FOREIGN KEY ("userId") REFERENCES "User"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

CREATE INDEX "WritingStyle_userId_createdAt_idx"
ON "WritingStyle"("userId", "createdAt");

ALTER TABLE "StylePortraitTask"
ADD COLUMN "section" TEXT;

ALTER TABLE "StylePortraitTask"
ADD CONSTRAINT "StylePortraitTask_section_check"
CHECK (
  "section" IS NULL OR "section" IN (
    'creativeMethodology',
    'uniqueMarkers',
    'generationStyle',
    'expressionFeatures',
    'styleTraits'
  )
);

CREATE TABLE "WritingRunCommand" (
  "id" TEXT NOT NULL,
  "taskId" TEXT NOT NULL,
  "kind" TEXT NOT NULL,
  "artifactId" TEXT,
  "decision" TEXT,
  "payloadJson" TEXT NOT NULL,
  "resultJson" TEXT,
  "idempotencyKey" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "attemptCount" INTEGER NOT NULL DEFAULT 0,
  "nextAttemptAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "lastError" TEXT,
  "submittedAt" TIMESTAMP(3),
  "completedAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "WritingRunCommand_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "WritingRunCommand_taskId_fkey"
    FOREIGN KEY ("taskId") REFERENCES "WritingTask"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "WritingRunCommand_kind_check"
    CHECK ("kind" IN ('start', 'resume', 'artifact_decision')),
  CONSTRAINT "WritingRunCommand_decision_check"
    CHECK ("decision" IS NULL OR "decision" IN ('approve', 'discard', 'revise')),
  CONSTRAINT "WritingRunCommand_status_check"
    CHECK ("status" IN ('pending', 'submitted', 'processing', 'succeeded', 'failed'))
);

CREATE UNIQUE INDEX "WritingRunCommand_idempotencyKey_key"
ON "WritingRunCommand"("idempotencyKey");

CREATE INDEX "WritingRunCommand_due_idx"
ON "WritingRunCommand"("status", "nextAttemptAt");

CREATE UNIQUE INDEX "WritingRunCommand_active_task_key"
ON "WritingRunCommand"("taskId")
WHERE "status" IN ('pending', 'submitted', 'processing');

COMMIT;
