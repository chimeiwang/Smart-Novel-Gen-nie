export const STORY_LENGTH_PROFILES = ["short_medium", "long_serial"] as const;

export type StoryLengthProfile = typeof STORY_LENGTH_PROFILES[number];

export type StoryLengthProfileConfig = {
  label: string;
  targetWords: [number, number];
  chapterCount: [number, number];
  plotUnits: [number, number];
  chapterWords: [number, number];
  planningFocus: string;
};

export const DEFAULT_STORY_LENGTH_PROFILE: StoryLengthProfile = "long_serial";

export const STORY_LENGTH_PROFILE_CONFIG: Record<StoryLengthProfile, StoryLengthProfileConfig> = {
  short_medium: {
    label: "中短篇",
    targetWords: [30_000, 100_000],
    chapterCount: [8, 25],
    plotUnits: [3, 5],
    chapterWords: [3_000, 5_000],
    planningFocus: "先从一句灵感孵化故事核心，再收束为单主线、少量关键设定和完整结局承诺。",
  },
  long_serial: {
    label: "长篇连载",
    targetWords: [300_000, 1_000_000],
    chapterCount: [80, 300],
    plotUnits: [10, 40],
    chapterWords: [3_000, 6_000],
    planningFocus: "先验证长期连载能力，再展开多阶段主线、可持续冲突源、伏笔池和角色长期状态。",
  },
};

export function normalizeStoryLengthProfile(value: unknown): StoryLengthProfile {
  return STORY_LENGTH_PROFILES.includes(value as StoryLengthProfile)
    ? value as StoryLengthProfile
    : DEFAULT_STORY_LENGTH_PROFILE;
}

export function getStoryLengthProfileConfig(profile: unknown): StoryLengthProfileConfig {
  return STORY_LENGTH_PROFILE_CONFIG[normalizeStoryLengthProfile(profile)];
}

export function formatStoryLengthProfile(profile: unknown, targetTotalWordCount?: number | null): string {
  const normalized = normalizeStoryLengthProfile(profile);
  const config = STORY_LENGTH_PROFILE_CONFIG[normalized];
  const [minWords, maxWords] = config.targetWords;
  const target = targetTotalWordCount ? `目标约 ${targetTotalWordCount} 字` : `默认 ${minWords}-${maxWords} 字`;
  return `${config.label}（${target}，${config.chapterCount[0]}-${config.chapterCount[1]} 章）`;
}
