-- Add chapter lifecycle state.
ALTER TABLE "Chapter" ADD COLUMN "status" TEXT NOT NULL DEFAULT 'drafting';
ALTER TABLE "Chapter" ADD COLUMN "completedAt" DATETIME;

-- Persist the per-chapter review/check queue.
CREATE TABLE "ChapterQualityCheck" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "chapterId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "title" TEXT NOT NULL,
    "summary" TEXT,
    "result" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "ChapterQualityCheck_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES "Chapter" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "ChapterQualityCheck_chapterId_type_key" ON "ChapterQualityCheck"("chapterId", "type");
CREATE INDEX "ChapterQualityCheck_chapterId_idx" ON "ChapterQualityCheck"("chapterId");
CREATE INDEX "ChapterQualityCheck_status_idx" ON "ChapterQualityCheck"("status");
CREATE INDEX "Chapter_status_idx" ON "Chapter"("status");
