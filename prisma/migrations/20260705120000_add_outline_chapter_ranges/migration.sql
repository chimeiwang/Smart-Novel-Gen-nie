ALTER TABLE "OutlineNode"
  ADD COLUMN "chapterStartOrder" INTEGER,
  ADD COLUMN "chapterEndOrder" INTEGER;

ALTER TABLE "OutlineNode"
  ADD CONSTRAINT "OutlineNode_chapter_range_check"
  CHECK (
    ("chapterStartOrder" IS NULL AND "chapterEndOrder" IS NULL)
    OR (
      "chapterStartOrder" IS NOT NULL
      AND "chapterEndOrder" IS NOT NULL
      AND "chapterStartOrder" > 0
      AND "chapterEndOrder" >= "chapterStartOrder"
    )
  );

CREATE INDEX "OutlineNode_novelId_kind_chapterStartOrder_chapterEndOrder_idx"
  ON "OutlineNode"("novelId", "kind", "chapterStartOrder", "chapterEndOrder");
