type ChapterBeatPlanSummary = {
  sceneCount: number;
  totalEstimatedWords: number;
};

export function formatChapterBeatPlanMeta(
  plan: ChapterBeatPlanSummary | null,
  options: { isCurrentChapter: boolean },
): string | null {
  if (plan) {
    return `章节计划 ${plan.sceneCount} 场 · ${plan.totalEstimatedWords} 字`;
  }

  return options.isCurrentChapter ? "未确认章节计划" : null;
}
