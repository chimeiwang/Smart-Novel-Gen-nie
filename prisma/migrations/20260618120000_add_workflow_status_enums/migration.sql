-- 写作闭环关键状态改为 PostgreSQL enum，防止应用层之外写入无效状态。

CREATE TYPE "ChapterStatus" AS ENUM ('drafting', 'review', 'completed');
CREATE TYPE "QualityCheckType" AS ENUM ('consistency', 'lore_sync', 'editorial', 'craft');
CREATE TYPE "QualityCheckStatus" AS ENUM ('pending', 'running', 'completed', 'skipped', 'failed');
CREATE TYPE "WritingTaskPhase" AS ENUM ('idle', 'active', 'waiting_call', 'awaiting_user_review', 'completed', 'error');
CREATE TYPE "WorkflowRunKind" AS ENUM ('chat', 'chapter_generation', 'quality_check', 'lore_sync', 'beat_plan');
CREATE TYPE "WorkflowRunStatus" AS ENUM ('pending', 'running', 'waiting_user', 'completed', 'failed', 'cancelled');
CREATE TYPE "WorkflowStepType" AS ENUM ('agent', 'tool', 'user_confirmation', 'persistence');
CREATE TYPE "WorkflowStepStatus" AS ENUM ('pending', 'running', 'completed', 'failed', 'skipped');
CREATE TYPE "ReviewArtifactKind" AS ENUM ('agent_updates', 'outline_draft', 'chapter_draft', 'lore_draft', 'revision_brief', 'beat_plan_draft', 'chapter_content', 'beat_plan', 'freeform_markdown');
CREATE TYPE "ReviewArtifactStatus" AS ENUM ('draft', 'under_review', 'awaiting_user', 'applying', 'applied');
CREATE TYPE "ReviewArtifactEvaluationVerdict" AS ENUM ('pass', 'revise', 'block');
CREATE TYPE "BeatPlanStatus" AS ENUM ('draft', 'reviewing', 'approved', 'rejected', 'superseded');

UPDATE "Chapter"
SET "status" = 'drafting'
WHERE "status" NOT IN ('drafting', 'review', 'completed');

UPDATE "ChapterQualityCheck"
SET "type" = 'consistency'
WHERE "type" NOT IN ('consistency', 'lore_sync', 'editorial', 'craft');

UPDATE "ChapterQualityCheck"
SET "status" = 'pending'
WHERE "status" NOT IN ('pending', 'running', 'completed', 'skipped', 'failed');

UPDATE "WritingTask"
SET "phase" = 'idle'
WHERE "phase" NOT IN ('idle', 'active', 'waiting_call', 'awaiting_user_review', 'completed', 'error');

UPDATE "WorkflowRun"
SET "kind" = 'chat'
WHERE "kind" NOT IN ('chat', 'chapter_generation', 'quality_check', 'lore_sync', 'beat_plan');

UPDATE "WorkflowRun"
SET "status" = 'pending'
WHERE "status" NOT IN ('pending', 'running', 'waiting_user', 'completed', 'failed', 'cancelled');

UPDATE "WorkflowStep"
SET "stepType" = 'tool'
WHERE "stepType" NOT IN ('agent', 'tool', 'user_confirmation', 'persistence');

UPDATE "WorkflowStep"
SET "status" = 'pending'
WHERE "status" NOT IN ('pending', 'running', 'completed', 'failed', 'skipped');

UPDATE "ReviewArtifact"
SET "kind" = 'freeform_markdown'
WHERE "kind" NOT IN ('agent_updates', 'outline_draft', 'chapter_draft', 'lore_draft', 'revision_brief', 'beat_plan_draft', 'chapter_content', 'beat_plan', 'freeform_markdown');

UPDATE "ReviewArtifact"
SET "status" = 'draft'
WHERE "status" NOT IN ('draft', 'under_review', 'awaiting_user', 'applying', 'applied');

UPDATE "ReviewArtifactEvaluation"
SET "verdict" = 'block'
WHERE "verdict" NOT IN ('pass', 'revise', 'block');

UPDATE "ChapterBeatPlan"
SET "status" = 'draft'
WHERE "status" NOT IN ('draft', 'reviewing', 'approved', 'rejected', 'superseded');

ALTER TABLE "Chapter"
  ALTER COLUMN "status" DROP DEFAULT,
  ALTER COLUMN "status" TYPE "ChapterStatus" USING ("status"::"ChapterStatus"),
  ALTER COLUMN "status" SET DEFAULT 'drafting';

ALTER TABLE "ChapterQualityCheck"
  ALTER COLUMN "type" TYPE "QualityCheckType" USING ("type"::"QualityCheckType"),
  ALTER COLUMN "status" DROP DEFAULT,
  ALTER COLUMN "status" TYPE "QualityCheckStatus" USING ("status"::"QualityCheckStatus"),
  ALTER COLUMN "status" SET DEFAULT 'pending';

ALTER TABLE "WritingTask"
  ALTER COLUMN "phase" DROP DEFAULT,
  ALTER COLUMN "phase" TYPE "WritingTaskPhase" USING ("phase"::"WritingTaskPhase"),
  ALTER COLUMN "phase" SET DEFAULT 'idle';

ALTER TABLE "WorkflowRun"
  ALTER COLUMN "kind" TYPE "WorkflowRunKind" USING ("kind"::"WorkflowRunKind"),
  ALTER COLUMN "status" DROP DEFAULT,
  ALTER COLUMN "status" TYPE "WorkflowRunStatus" USING ("status"::"WorkflowRunStatus"),
  ALTER COLUMN "status" SET DEFAULT 'pending';

ALTER TABLE "WorkflowStep"
  ALTER COLUMN "stepType" TYPE "WorkflowStepType" USING ("stepType"::"WorkflowStepType"),
  ALTER COLUMN "status" DROP DEFAULT,
  ALTER COLUMN "status" TYPE "WorkflowStepStatus" USING ("status"::"WorkflowStepStatus"),
  ALTER COLUMN "status" SET DEFAULT 'pending';

ALTER TABLE "ReviewArtifact"
  ALTER COLUMN "kind" TYPE "ReviewArtifactKind" USING ("kind"::"ReviewArtifactKind"),
  ALTER COLUMN "status" DROP DEFAULT,
  ALTER COLUMN "status" TYPE "ReviewArtifactStatus" USING ("status"::"ReviewArtifactStatus"),
  ALTER COLUMN "status" SET DEFAULT 'draft';

ALTER TABLE "ReviewArtifactEvaluation"
  ALTER COLUMN "verdict" TYPE "ReviewArtifactEvaluationVerdict" USING ("verdict"::"ReviewArtifactEvaluationVerdict");

ALTER TABLE "ChapterBeatPlan"
  ALTER COLUMN "status" DROP DEFAULT,
  ALTER COLUMN "status" TYPE "BeatPlanStatus" USING ("status"::"BeatPlanStatus"),
  ALTER COLUMN "status" SET DEFAULT 'draft';
