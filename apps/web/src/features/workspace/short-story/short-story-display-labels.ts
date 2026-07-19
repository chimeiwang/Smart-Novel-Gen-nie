import type { components } from "@inkforge/api-client";

type ShortStoryOperation = components["schemas"]["ShortStoryTaskStatus"]["operation"];
type ShortStoryVerdict = components["schemas"]["ArtifactEvaluationResponse"]["verdict"];

const OPERATION_LABELS = {
  develop_short_outline: "生成完整大纲",
  write_short_story: "生成完整初稿",
} satisfies Record<ShortStoryOperation, string>;

const PHASE_LABELS: Readonly<Record<string, string>> = {
  idle: "待开始",
  discussing: "沟通中",
  generating: "生成中",
  recording: "整理中",
  active: "处理中",
  pending: "等待处理",
  submitted: "已提交",
  processing: "处理中",
  waiting_call: "等待模型响应",
  waiting_user: "等待用户确认",
  awaiting_user_review: "等待用户确认",
  succeeded: "已完成",
  completed: "已完成",
  failed: "运行失败",
  error: "运行失败",
  cancelled: "已取消",
};

const VERDICT_LABELS = {
  pass: "通过",
  revise: "需修改",
  block: "未通过",
} satisfies Record<ShortStoryVerdict, string>;

export function formatShortStoryOperation(operation: string): string {
  return (OPERATION_LABELS as Readonly<Record<string, string>>)[operation] ?? "未知操作";
}

export function formatShortStoryPhase(phase: string): string {
  return PHASE_LABELS[phase] ?? "状态未知";
}

export function formatShortStoryVerdict(verdict: string): string {
  return (VERDICT_LABELS as Readonly<Record<string, string>>)[verdict] ?? "结论未知";
}

export function formatShortStoryVersion(revision: number): string {
  return `版本 ${revision}`;
}
