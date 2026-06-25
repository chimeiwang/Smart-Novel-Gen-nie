-- CreateTable
CREATE TABLE "Novel" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "summary" TEXT,
    "appliedStyleId" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "Novel_appliedStyleId_fkey" FOREIGN KEY ("appliedStyleId") REFERENCES "WritingStyle" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "Chapter" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "content" TEXT NOT NULL DEFAULT '',
    "order" INTEGER NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "Chapter_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "LoreEntry" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "aliases" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "LoreEntry_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "Outline" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "summary" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "Outline_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "OutlineNode" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "outlineId" TEXT NOT NULL,
    "parentId" TEXT,
    "title" TEXT NOT NULL,
    "summary" TEXT NOT NULL,
    "linkedChapterId" TEXT,
    "order" INTEGER NOT NULL,
    CONSTRAINT "OutlineNode_outlineId_fkey" FOREIGN KEY ("outlineId") REFERENCES "Outline" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "OutlineNode_parentId_fkey" FOREIGN KEY ("parentId") REFERENCES "OutlineNode" ("id") ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT "OutlineNode_linkedChapterId_fkey" FOREIGN KEY ("linkedChapterId") REFERENCES "Chapter" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "PlotProgress" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "currentStage" TEXT NOT NULL,
    "currentGoal" TEXT,
    "currentConflict" TEXT,
    "nextMilestone" TEXT,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "PlotProgress_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "ReferenceMaterial" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "sourceUrl" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "ReferenceMaterial_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "WritingStyle" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "sampleText" TEXT NOT NULL,
    "extractedProfile" TEXT NOT NULL,
    "sourceType" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);

-- CreateTable
CREATE TABLE "StyleExtractionTask" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "styleId" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "sourceText" TEXT NOT NULL,
    "result" TEXT,
    "errorMessage" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "StyleExtractionTask_styleId_fkey" FOREIGN KEY ("styleId") REFERENCES "WritingStyle" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateIndex
CREATE INDEX "Chapter_novelId_order_idx" ON "Chapter"("novelId", "order");

-- CreateIndex
CREATE INDEX "LoreEntry_novelId_type_idx" ON "LoreEntry"("novelId", "type");

-- CreateIndex
CREATE UNIQUE INDEX "Outline_novelId_key" ON "Outline"("novelId");

-- CreateIndex
CREATE INDEX "OutlineNode_outlineId_order_idx" ON "OutlineNode"("outlineId", "order");

-- CreateIndex
CREATE UNIQUE INDEX "PlotProgress_novelId_key" ON "PlotProgress"("novelId");

-- CreateIndex
CREATE INDEX "ReferenceMaterial_novelId_type_idx" ON "ReferenceMaterial"("novelId", "type");
