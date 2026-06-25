-- Add role invariants used for OOC validation and supervised lore maintenance.
ALTER TABLE "Character" ADD COLUMN "coreDesire" TEXT;
ALTER TABLE "Character" ADD COLUMN "behaviorBoundaries" TEXT;
ALTER TABLE "Character" ADD COLUMN "speechStyle" TEXT;
ALTER TABLE "Character" ADD COLUMN "relationshipPrinciples" TEXT;
ALTER TABLE "Character" ADD COLUMN "shortTermGoal" TEXT;
