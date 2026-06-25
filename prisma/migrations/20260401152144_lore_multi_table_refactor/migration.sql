/*
  Warnings:

  - You are about to drop the `LoreEntry` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the `OutlineNode` table. If the table is not empty, all the data it contains will be lost.
  - You are about to drop the column `summary` on the `Outline` table. All the data in the column will be lost.
  - You are about to drop the column `title` on the `Outline` table. All the data in the column will be lost.

*/
-- DropIndex
DROP INDEX "LoreEntry_novelId_category_idx";

-- DropIndex
DROP INDEX "OutlineNode_outlineId_order_idx";

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "LoreEntry";
PRAGMA foreign_keys=on;

-- DropTable
PRAGMA foreign_keys=off;
DROP TABLE "OutlineNode";
PRAGMA foreign_keys=on;

-- CreateTable
CREATE TABLE "Character" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "aliases" TEXT,
    "gender" TEXT,
    "age" TEXT,
    "appearance" TEXT,
    "personality" TEXT,
    "identity" TEXT,
    "background" TEXT,
    "factionId" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "Character_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "Character_factionId_fkey" FOREIGN KEY ("factionId") REFERENCES "Faction" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "CharacterRelation" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "characterId" TEXT NOT NULL,
    "targetId" TEXT NOT NULL,
    "relationType" TEXT NOT NULL,
    "description" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "CharacterRelation_characterId_fkey" FOREIGN KEY ("characterId") REFERENCES "Character" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "CharacterRelation_targetId_fkey" FOREIGN KEY ("targetId") REFERENCES "Character" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "Item" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "aliases" TEXT,
    "type" TEXT,
    "rarity" TEXT,
    "effect" TEXT,
    "origin" TEXT,
    "description" TEXT,
    "ownerId" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "Item_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "Item_ownerId_fkey" FOREIGN KEY ("ownerId") REFERENCES "Character" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "Location" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "aliases" TEXT,
    "type" TEXT,
    "parentId" TEXT,
    "climate" TEXT,
    "culture" TEXT,
    "description" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "Location_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "Location_parentId_fkey" FOREIGN KEY ("parentId") REFERENCES "Location" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "Faction" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "aliases" TEXT,
    "type" TEXT,
    "ideology" TEXT,
    "baseId" TEXT,
    "description" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "Faction_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "Faction_baseId_fkey" FOREIGN KEY ("baseId") REFERENCES "Location" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "Glossary" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "term" TEXT NOT NULL,
    "definition" TEXT NOT NULL,
    "category" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "Glossary_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "_FactionTerritories" (
    "A" TEXT NOT NULL,
    "B" TEXT NOT NULL,
    CONSTRAINT "_FactionTerritories_A_fkey" FOREIGN KEY ("A") REFERENCES "Faction" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "_FactionTerritories_B_fkey" FOREIGN KEY ("B") REFERENCES "Location" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_Outline" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "content" TEXT NOT NULL DEFAULT '',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "Outline_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
INSERT INTO "new_Outline" ("createdAt", "id", "novelId", "updatedAt") SELECT "createdAt", "id", "novelId", "updatedAt" FROM "Outline";
DROP TABLE "Outline";
ALTER TABLE "new_Outline" RENAME TO "Outline";
CREATE UNIQUE INDEX "Outline_novelId_key" ON "Outline"("novelId");
PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;

-- CreateIndex
CREATE INDEX "Character_novelId_idx" ON "Character"("novelId");

-- CreateIndex
CREATE INDEX "Character_factionId_idx" ON "Character"("factionId");

-- CreateIndex
CREATE INDEX "CharacterRelation_characterId_idx" ON "CharacterRelation"("characterId");

-- CreateIndex
CREATE INDEX "CharacterRelation_targetId_idx" ON "CharacterRelation"("targetId");

-- CreateIndex
CREATE INDEX "Item_novelId_idx" ON "Item"("novelId");

-- CreateIndex
CREATE INDEX "Item_ownerId_idx" ON "Item"("ownerId");

-- CreateIndex
CREATE INDEX "Location_novelId_idx" ON "Location"("novelId");

-- CreateIndex
CREATE INDEX "Location_parentId_idx" ON "Location"("parentId");

-- CreateIndex
CREATE INDEX "Faction_novelId_idx" ON "Faction"("novelId");

-- CreateIndex
CREATE INDEX "Faction_baseId_idx" ON "Faction"("baseId");

-- CreateIndex
CREATE INDEX "Glossary_novelId_idx" ON "Glossary"("novelId");

-- CreateIndex
CREATE UNIQUE INDEX "_FactionTerritories_AB_unique" ON "_FactionTerritories"("A", "B");

-- CreateIndex
CREATE INDEX "_FactionTerritories_B_index" ON "_FactionTerritories"("B");
