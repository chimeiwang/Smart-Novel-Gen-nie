-- Add structured quality scores for chapter review gates.
ALTER TABLE "ChapterQualityCheck" ADD COLUMN "scoreHook" INTEGER;
ALTER TABLE "ChapterQualityCheck" ADD COLUMN "scoreTension" INTEGER;
ALTER TABLE "ChapterQualityCheck" ADD COLUMN "scorePayoff" INTEGER;
ALTER TABLE "ChapterQualityCheck" ADD COLUMN "scorePacing" INTEGER;
ALTER TABLE "ChapterQualityCheck" ADD COLUMN "scoreEndingHook" INTEGER;
ALTER TABLE "ChapterQualityCheck" ADD COLUMN "scoreReaderPromise" INTEGER;
ALTER TABLE "ChapterQualityCheck" ADD COLUMN "scoreOverall" INTEGER;
ALTER TABLE "ChapterQualityCheck" ADD COLUMN "qualityGate" TEXT;
ALTER TABLE "ChapterQualityCheck" ADD COLUMN "rewriteBrief" TEXT;
