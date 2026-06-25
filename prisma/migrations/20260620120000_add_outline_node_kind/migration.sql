CREATE TYPE "OutlineNodeKind" AS ENUM ('stage', 'plot_unit', 'chapter_group');

ALTER TABLE "OutlineNode"
  ADD COLUMN "kind" "OutlineNodeKind" NOT NULL DEFAULT 'stage';

UPDATE "OutlineNode" AS node
SET "kind" = CASE
  WHEN node."parentId" IS NULL THEN 'stage'::"OutlineNodeKind"
  WHEN parent."parentId" IS NULL THEN 'plot_unit'::"OutlineNodeKind"
  ELSE 'chapter_group'::"OutlineNodeKind"
END
FROM "OutlineNode" AS parent
WHERE node."parentId" = parent."id";

CREATE INDEX "OutlineNode_novelId_kind_idx" ON "OutlineNode"("novelId", "kind");
