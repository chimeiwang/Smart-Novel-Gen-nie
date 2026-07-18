import type { components } from "@inkforge/api-client";

type WritingBible = components["schemas"]["WritingBibleDto"];
type WritingBibleRequest = components["schemas"]["WritingBibleRequest"];

export function buildWritingBibleTargetUpdate(
  writingBible: WritingBible,
  targetTotalWordCount: number,
): WritingBibleRequest {
  return {
    targetTotalWordCount,
    genre: writingBible.genre,
    targetReaders: writingBible.targetReaders,
    coreSellingPoint: writingBible.coreSellingPoint,
    readerPromise: writingBible.readerPromise,
    appealModel: writingBible.appealModel,
    taboo: writingBible.taboo,
    comparableTitles: writingBible.comparableTitles,
    notes: writingBible.notes,
  };
}

