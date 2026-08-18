import type { components } from "@inkforge/api-client";

import { parseVideoStage, type VideoPlanAssetView, type VideoStage } from "./video-workspace-state";
import {
  VIDEO_ASSET_DUTIES,
  type AssetDuty,
  type VideoAsset,
} from "./video-workspace-types";

export type SeedancePromptPackage = components["schemas"]["SeedancePromptPackage"];

export type SeedancePromptPresentation = {
  providerPrompt: string;
  providerPromptCharacterCount: number;
  manifestPrompt: string;
  manifestPromptCharacterCount: number;
  hasDistinctManifest: boolean;
  isLegacy: boolean;
  providerLengthState: "ok" | "warning" | "blocked";
};

export type SeedancePackageStatusPresentation = {
  previewLabel: "开发预览" | "正式制作";
  assetLabel: "素材已齐" | "素材未齐";
  submissionLabel: "可提交" | "不可提交";
  blockers: string[];
  readyMessage: string | null;
};

export const LEGACY_PROMPT_NOTICE = "旧版或兼容提示词包：需从正式场景重新规划、审核并编译为导演语言版本。";

export type VideoInitialLocation = {
  projectId: string | null;
  sceneId: string | null;
  stage: VideoStage;
};

// 服务端渲染时没有浏览器地址，因此用第一阶段作为稳定回退值。
export function readInitialVideoLocation(): VideoInitialLocation {
  if (typeof window === "undefined") {
    return { projectId: null, sceneId: null, stage: "source" };
  }
  const params = new URLSearchParams(window.location.search);
  return {
    projectId: params.get("videoProjectId"),
    sceneId: params.get("videoSceneId"),
    stage: parseVideoStage(params.get("videoStage")),
  };
}

export function textFromRecord(value: unknown, key: string): string {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return "";
  const selected = (value as Record<string, unknown>)[key];
  return typeof selected === "string" ? selected : "";
}

export function videoSceneStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    draft: "草稿",
    generating: "生成中",
    awaiting_review: "待批准",
    approved: "已批准",
    failed: "失败",
  };
  return labels[status] ?? status;
}

export function videoAssetDutyLabel(duty: AssetDuty | string): string {
  if (duty === "relation_interaction") return "人物关系互动";
  return VIDEO_ASSET_DUTIES.find((item) => item.value === duty)?.label ?? duty;
}

export function isCompatiblePreviewAsset(
  asset: VideoAsset,
  slot: VideoPlanAssetView,
): boolean {
  if (!asset.lockedAt || asset.modality !== slot.modality) return false;
  // 旧 dev 表没有 relation_interaction 枚举，预览期使用 keyframe 文件表达关系同框参考。
  const expectedDuty = slot.duty === "relation_interaction" ? "keyframe" : slot.duty;
  return asset.duty === expectedDuty;
}

export function formatVideoAssetBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function videoErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

/**
 * 把新旧 Seedance 包统一成双层展示模型。
 * 旧包保持可读，但不能伪装成已经通过专业摄影编译器重新生成。
 */
export function normalizeSeedancePromptPackage(
  packageValue: SeedancePromptPackage,
): SeedancePromptPresentation {
  const providerPrompt = packageValue.providerPrompt ?? packageValue.prompt;
  const providerPromptCharacterCount = packageValue.providerPromptCharacterCount
    ?? packageValue.promptCharacterCount
    ?? countUnicodeCodePoints(providerPrompt);
  const manifestPrompt = packageValue.manifestPrompt ?? providerPrompt;
  const manifestPromptCharacterCount = packageValue.manifestPromptCharacterCount
    ?? (manifestPrompt === providerPrompt
      ? providerPromptCharacterCount
      : countUnicodeCodePoints(manifestPrompt));
  const isLegacy = packageValue.compileProfile !== "seedance_director_v3"
    || packageValue.providerPrompt === null
    || packageValue.providerPrompt === undefined;
  const providerLengthState = providerPromptCharacterCount > packageValue.maxPromptCharacters
    ? "blocked"
    : providerPromptCharacterCount > packageValue.recommendedPromptCharacters
      ? "warning"
      : "ok";

  return {
    providerPrompt,
    providerPromptCharacterCount,
    manifestPrompt,
    manifestPromptCharacterCount,
    hasDistinctManifest: manifestPrompt !== providerPrompt,
    isLegacy,
    providerLengthState,
  };
}

/**
 * 预览边界、素材事实和最终提交状态必须分开表达，避免把所有不可提交都归因于密钥。
 */
export function readSeedancePackageStatus(
  packageValue: SeedancePromptPackage,
): SeedancePackageStatusPresentation {
  const blockers: string[] = [];
  if (packageValue.previewOnly) {
    blockers.push("开发预览边界：当前包不会发送至火山供应商。");
  }
  if (!packageValue.assetReady) {
    blockers.push("素材状态：仍有占位素材，当前包不能提交。");
  }
  if (!packageValue.submissionReady && !packageValue.previewOnly && packageValue.assetReady) {
    blockers.push("提交状态：素材已齐，但服务端尚未把当前包标记为可提交，请重新编译。");
  }

  return {
    previewLabel: packageValue.previewOnly ? "开发预览" : "正式制作",
    assetLabel: packageValue.assetReady ? "素材已齐" : "素材未齐",
    submissionLabel: packageValue.submissionReady ? "可提交" : "不可提交",
    blockers,
    readyMessage: packageValue.submissionReady
      ? "提交状态：Provider 提示词与素材均已就绪，可进入受控提交流程。"
      : null,
  };
}

// 仅在过渡 payload 缺失计数字段时兜底；正常数据始终信任 Core 返回的字符数。
function countUnicodeCodePoints(value: string): number {
  return Array.from(value).length;
}
