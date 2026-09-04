/** 仅判断全文编辑能力；具体资源身份、来源与版本仍由 Core 复验。 */
export function isChapterWritingReviewArtifact(kind: string, payload: unknown): boolean {
  if (kind !== "chapter_draft" || !payload || typeof payload !== "object") return false;
  const data = payload as Record<string, unknown>;
  const target = data.target;
  return data.operation === "write_chapter"
    && Boolean(target && typeof target === "object"
      && (target as Record<string, unknown>).mode === "existing_chapter");
}
