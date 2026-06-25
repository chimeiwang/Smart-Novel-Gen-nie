ALTER TABLE "WritingTask"
  ADD COLUMN "writingSessionId" TEXT,
  ADD COLUMN "graphStateJson" TEXT;

ALTER TABLE "WritingTask"
  ADD CONSTRAINT "WritingTask_writingSessionId_fkey"
  FOREIGN KEY ("writingSessionId") REFERENCES "WritingSession"("id")
  ON DELETE SET NULL ON UPDATE CASCADE;

CREATE INDEX "WritingTask_writingSessionId_idx" ON "WritingTask"("writingSessionId");
