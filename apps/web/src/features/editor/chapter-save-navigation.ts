type FlushChapterSave = () => Promise<void>;

let activeFlush: FlushChapterSave | null = null;

export function registerActiveChapterSave(
  flush: FlushChapterSave,
): () => void {
  activeFlush = flush;
  return () => {
    if (activeFlush === flush) activeFlush = null;
  };
}

export async function flushActiveChapterSave(): Promise<void> {
  await activeFlush?.();
}
