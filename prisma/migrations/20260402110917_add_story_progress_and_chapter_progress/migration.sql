-- AlterTable
ALTER TABLE "Novel" ADD COLUMN "storyProgress" TEXT;

-- CreateTable
CREATE TABLE "ChapterProgress" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "chapterId" TEXT NOT NULL,
    "content" TEXT NOT NULL DEFAULT '',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "ChapterProgress_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES "Chapter" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateIndex
CREATE UNIQUE INDEX "ChapterProgress_chapterId_key" ON "ChapterProgress"("chapterId");
