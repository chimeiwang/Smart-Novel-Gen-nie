CREATE TYPE "StoryLengthProfile" AS ENUM ('short_medium', 'long_serial');

ALTER TABLE "WritingBible"
ADD COLUMN "storyLengthProfile" "StoryLengthProfile" NOT NULL DEFAULT 'long_serial',
ADD COLUMN "targetTotalWordCount" INTEGER;
