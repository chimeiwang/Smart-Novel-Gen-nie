/*
  Warnings:

  - You are about to drop the column `type` on the `LoreEntry` table. All the data in the column will be lost.
  - Added the required column `category` to the `LoreEntry` table without a default value. This is not possible if the table is not empty.

*/
-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_LoreEntry" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "category" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "aliases" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "LoreEntry_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
INSERT INTO "new_LoreEntry" ("aliases", "createdAt", "description", "id", "name", "novelId", "updatedAt") SELECT "aliases", "createdAt", "description", "id", "name", "novelId", "updatedAt" FROM "LoreEntry";
DROP TABLE "LoreEntry";
ALTER TABLE "new_LoreEntry" RENAME TO "LoreEntry";
CREATE INDEX "LoreEntry_novelId_category_idx" ON "LoreEntry"("novelId", "category");
PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;
