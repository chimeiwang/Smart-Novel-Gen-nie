-- Add work-level commercial positioning and writing constraints.
CREATE TABLE "WritingBible" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "novelId" TEXT NOT NULL,
    "genre" TEXT,
    "targetReaders" TEXT,
    "coreSellingPoint" TEXT,
    "readerPromise" TEXT,
    "appealModel" TEXT,
    "taboo" TEXT,
    "comparableTitles" TEXT,
    "notes" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "WritingBible_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "WritingBible_novelId_key" ON "WritingBible"("novelId");
