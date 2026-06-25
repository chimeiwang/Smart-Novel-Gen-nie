/*
  Warnings:

  - You are about to drop the `StyleExtractionTask` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the column `extractedProfile` on the `WritingStyle` table. All the data in the column will be lost.
  - You are about to drop the column `sampleText` on the `WritingStyle` table. All the data in the column will be lost.

*/
-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "StyleExtractionTask";
PRAGMA foreign_keys=on;

-- CreateTable
CREATE TABLE "StyleReference" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "styleId" TEXT NOT NULL,
    "filename" TEXT NOT NULL,
    "filepath" TEXT NOT NULL,
    "charCount" INTEGER NOT NULL DEFAULT 0,
    "status" TEXT NOT NULL DEFAULT 'ready',
    "errorMessage" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "StyleReference_styleId_fkey" FOREIGN KEY ("styleId") REFERENCES "WritingStyle" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "StylePortraitTask" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "styleId" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "errorMessage" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "StylePortraitTask_styleId_fkey" FOREIGN KEY ("styleId") REFERENCES "WritingStyle" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_WritingStyle" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "sourceType" TEXT NOT NULL DEFAULT 'manual',
    "creativeMethodology" TEXT,
    "uniqueMarkers" TEXT,
    "generationStyle" TEXT,
    "expressionFeatures" TEXT,
    "styleTraits" TEXT,
    "portraitMarkdown" TEXT,
    "originalCharCount" INTEGER NOT NULL DEFAULT 0,
    "usedCharCount" INTEGER NOT NULL DEFAULT 0,
    "truncated" BOOLEAN NOT NULL DEFAULT false,
    "errorMessage" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);
INSERT INTO "new_WritingStyle" ("createdAt", "id", "name", "sourceType", "updatedAt") SELECT "createdAt", "id", "name", "sourceType", "updatedAt" FROM "WritingStyle";
DROP TABLE "WritingStyle";
ALTER TABLE "new_WritingStyle" RENAME TO "WritingStyle";
PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;

-- CreateIndex
CREATE INDEX "StyleReference_styleId_idx" ON "StyleReference"("styleId");

-- CreateIndex
CREATE INDEX "StylePortraitTask_styleId_idx" ON "StylePortraitTask"("styleId");
