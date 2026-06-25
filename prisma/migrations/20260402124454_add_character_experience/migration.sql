-- CreateTable
CREATE TABLE "CharacterExperience" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "characterId" TEXT NOT NULL,
    "chapterId" TEXT,
    "content" TEXT NOT NULL,
    "order" INTEGER NOT NULL DEFAULT 0,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "CharacterExperience_characterId_fkey" FOREIGN KEY ("characterId") REFERENCES "Character" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateIndex
CREATE INDEX "CharacterExperience_characterId_idx" ON "CharacterExperience"("characterId");

-- CreateIndex
CREATE INDEX "CharacterExperience_chapterId_idx" ON "CharacterExperience"("chapterId");
