-- CreateTable
CREATE TABLE "ReviewArtifact" (
    "id" TEXT NOT NULL,
    "novelId" TEXT NOT NULL,
    "chapterId" TEXT,
    "taskId" TEXT,
    "workflowRunId" TEXT,
    "artifactKey" TEXT,
    "kind" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'draft',
    "title" TEXT,
    "summary" TEXT,
    "payloadJson" TEXT NOT NULL,
    "diffJson" TEXT,
    "createdByAgent" TEXT,
    "updatedByAgent" TEXT,
    "reviewerAgent" TEXT,
    "revision" INTEGER NOT NULL DEFAULT 1,
    "appliedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ReviewArtifact_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ReviewArtifactRevision" (
    "id" TEXT NOT NULL,
    "artifactId" TEXT NOT NULL,
    "revision" INTEGER NOT NULL,
    "summary" TEXT,
    "payloadJson" TEXT NOT NULL,
    "diffJson" TEXT,
    "createdByAgent" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ReviewArtifactRevision_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ReviewArtifactEvaluation" (
    "id" TEXT NOT NULL,
    "artifactId" TEXT NOT NULL,
    "revision" INTEGER NOT NULL,
    "evaluatorAgent" TEXT NOT NULL,
    "verdict" TEXT NOT NULL,
    "summary" TEXT NOT NULL,
    "requiredChanges" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ReviewArtifactEvaluation_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "ReviewArtifact_novelId_status_idx" ON "ReviewArtifact"("novelId", "status");

-- CreateIndex
CREATE INDEX "ReviewArtifact_chapterId_status_idx" ON "ReviewArtifact"("chapterId", "status");

-- CreateIndex
CREATE INDEX "ReviewArtifact_taskId_idx" ON "ReviewArtifact"("taskId");

-- CreateIndex
CREATE INDEX "ReviewArtifact_workflowRunId_idx" ON "ReviewArtifact"("workflowRunId");

-- CreateIndex
CREATE INDEX "ReviewArtifact_artifactKey_idx" ON "ReviewArtifact"("artifactKey");

-- CreateIndex
CREATE UNIQUE INDEX "ReviewArtifactRevision_artifactId_revision_key" ON "ReviewArtifactRevision"("artifactId", "revision");

-- CreateIndex
CREATE INDEX "ReviewArtifactRevision_artifactId_idx" ON "ReviewArtifactRevision"("artifactId");

-- CreateIndex
CREATE INDEX "ReviewArtifactEvaluation_artifactId_revision_idx" ON "ReviewArtifactEvaluation"("artifactId", "revision");

-- CreateIndex
CREATE INDEX "ReviewArtifactEvaluation_evaluatorAgent_idx" ON "ReviewArtifactEvaluation"("evaluatorAgent");

-- AddForeignKey
ALTER TABLE "ReviewArtifact" ADD CONSTRAINT "ReviewArtifact_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ReviewArtifact" ADD CONSTRAINT "ReviewArtifact_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES "Chapter"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ReviewArtifact" ADD CONSTRAINT "ReviewArtifact_taskId_fkey" FOREIGN KEY ("taskId") REFERENCES "WritingTask"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ReviewArtifact" ADD CONSTRAINT "ReviewArtifact_workflowRunId_fkey" FOREIGN KEY ("workflowRunId") REFERENCES "WorkflowRun"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ReviewArtifactRevision" ADD CONSTRAINT "ReviewArtifactRevision_artifactId_fkey" FOREIGN KEY ("artifactId") REFERENCES "ReviewArtifact"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ReviewArtifactEvaluation" ADD CONSTRAINT "ReviewArtifactEvaluation_artifactId_fkey" FOREIGN KEY ("artifactId") REFERENCES "ReviewArtifact"("id") ON DELETE CASCADE ON UPDATE CASCADE;
