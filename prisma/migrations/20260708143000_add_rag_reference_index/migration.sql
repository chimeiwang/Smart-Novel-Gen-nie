CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE "RagSourceType" AS ENUM ('reference_material');
CREATE TYPE "RagDocumentStatus" AS ENUM ('disabled', 'ready', 'failed');

CREATE TABLE "RagDocument" (
    "id" TEXT NOT NULL,
    "novelId" TEXT NOT NULL,
    "sourceType" "RagSourceType" NOT NULL,
    "sourceId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "contentHash" TEXT NOT NULL,
    "status" "RagDocumentStatus" NOT NULL DEFAULT 'disabled',
    "errorMessage" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "RagDocument_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "RagChunk" (
    "id" TEXT NOT NULL,
    "documentId" TEXT NOT NULL,
    "novelId" TEXT NOT NULL,
    "chunkIndex" INTEGER NOT NULL,
    "text" TEXT NOT NULL,
    "charCount" INTEGER NOT NULL,
    "embeddingDimension" INTEGER NOT NULL,
    "embedding" vector NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "RagChunk_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "RagDocument_sourceType_sourceId_key" ON "RagDocument"("sourceType", "sourceId");
CREATE INDEX "RagDocument_novelId_sourceType_idx" ON "RagDocument"("novelId", "sourceType");
CREATE UNIQUE INDEX "RagChunk_documentId_chunkIndex_key" ON "RagChunk"("documentId", "chunkIndex");
CREATE INDEX "RagChunk_novelId_idx" ON "RagChunk"("novelId");

ALTER TABLE "RagDocument" ADD CONSTRAINT "RagDocument_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "RagChunk" ADD CONSTRAINT "RagChunk_documentId_fkey" FOREIGN KEY ("documentId") REFERENCES "RagDocument"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "RagChunk" ADD CONSTRAINT "RagChunk_novelId_fkey" FOREIGN KEY ("novelId") REFERENCES "Novel"("id") ON DELETE CASCADE ON UPDATE CASCADE;
