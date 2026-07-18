import type { components } from "@inkforge/api-client";

export type StoryLengthProfile = components["schemas"]["StoryLengthProfile"];

export const STORY_LENGTH_PROFILES = ["short_medium", "long_serial"] as const satisfies readonly StoryLengthProfile[];

export type StoryLengthProfileConfig = {
  label: string;
  targetWords: [number, number];
  planningFocus: string;
};

export const STORY_LENGTH_PROFILE_CONFIG: Record<StoryLengthProfile, StoryLengthProfileConfig> = {
  short_medium: {
    label: "中短篇",
    targetWords: [6_000, 80_000],
    planningFocus: "先从一句灵感孵化故事核心，再收束为单主线、少量关键设定和完整结局承诺。",
  },
  long_serial: {
    label: "长篇连载",
    targetWords: [300_000, 1_000_000],
    planningFocus: "先验证长期连载能力，再展开多阶段主线、可持续冲突源、伏笔池和角色长期状态。",
  },
};

export function normalizeStoryLengthProfile(value: unknown): StoryLengthProfile | null {
  return STORY_LENGTH_PROFILES.includes(value as StoryLengthProfile)
    ? value as StoryLengthProfile
    : null;
}

export function getStoryLengthProfileConfig(profile: StoryLengthProfile): StoryLengthProfileConfig {
  return STORY_LENGTH_PROFILE_CONFIG[profile];
}

export function formatStoryLengthProfile(profile: StoryLengthProfile, targetTotalWordCount?: number | null): string {
  const config = STORY_LENGTH_PROFILE_CONFIG[profile];
  const [minWords, maxWords] = config.targetWords;
  const target = targetTotalWordCount ? `目标约 ${targetTotalWordCount} 字` : `默认 ${minWords}-${maxWords} 字`;
  return `${config.label}（${target}）`;
}
