-- CreateTable
CREATE TABLE "Foreshadowing" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "plantedAt" TEXT,
    "plantedContent" TEXT,
    "expectedPayoff" TEXT,
    "payoffAt" TEXT,
    "status" TEXT NOT NULL DEFAULT 'active',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "Foreshadowing_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "OutlineNode" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "parentId" TEXT,
    "title" TEXT NOT NULL,
    "content" TEXT,
    "order" INTEGER NOT NULL DEFAULT 0,
    "status" TEXT NOT NULL DEFAULT 'planned',
    "estimatedWordCount" INTEGER,
    "actualWordCount" INTEGER,
    "linkedChapterId" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "OutlineNode_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "OutlineNode_parentId_fkey" FOREIGN KEY ("parentId") REFERENCES "OutlineNode" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "CharacterStateChange" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "characterId" TEXT NOT NULL,
    "chapterId" TEXT,
    "changeType" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "beforeState" TEXT,
    "afterState" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "CharacterStateChange_characterId_fkey" FOREIGN KEY ("characterId") REFERENCES "Character" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "WritingConfig" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "defaultWordCount" INTEGER NOT NULL DEFAULT 4000,
    "enabledAgents" TEXT NOT NULL DEFAULT 'host,writer,validator',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "WritingConfig_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "WritingTask" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "chapterId" TEXT NOT NULL,
    "targetWordCount" INTEGER NOT NULL,
    "selectedAgents" TEXT NOT NULL,
    "phase" TEXT NOT NULL DEFAULT 'idle',
    "agentOutputs" TEXT,
    "generatedContent" TEXT,
    "finalContent" TEXT,
    "foreshadowingUpdates" TEXT,
    "outlineUpdates" TEXT,
    "characterChanges" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "WritingTask_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "WritingTask_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES "Chapter" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateIndex
CREATE INDEX "Foreshadowing_novelId_idx" ON "Foreshadowing"("novelId");

-- CreateIndex
CREATE INDEX "Foreshadowing_status_idx" ON "Foreshadowing"("status");

-- CreateIndex
CREATE INDEX "OutlineNode_novelId_idx" ON "OutlineNode"("novelId");

-- CreateIndex
CREATE INDEX "OutlineNode_parentId_idx" ON "OutlineNode"("parentId");

-- CreateIndex
CREATE INDEX "OutlineNode_status_idx" ON "OutlineNode"("status");

-- CreateIndex
CREATE INDEX "CharacterStateChange_characterId_idx" ON "CharacterStateChange"("characterId");

-- CreateIndex
CREATE INDEX "CharacterStateChange_chapterId_idx" ON "CharacterStateChange"("chapterId");

-- CreateIndex
CREATE UNIQUE INDEX "WritingConfig_novelId_key" ON "WritingConfig"("novelId");

-- CreateIndex
CREATE INDEX "WritingTask_novelId_idx" ON "WritingTask"("novelId");

-- CreateIndex
CREATE INDEX "WritingTask_chapterId_idx" ON "WritingTask"("chapterId");
