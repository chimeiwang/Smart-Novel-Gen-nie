import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  LEGACY_PROMPT_NOTICE,
  normalizeSeedancePromptPackage,
  readSeedancePackageStatus,
  type SeedancePromptPackage,
} from "../video-workspace-helpers";

function makePackage(
  overrides: Partial<SeedancePromptPackage> = {},
): SeedancePromptPackage {
  return {
    schemaVersion: "1.0",
    sceneId: "scene-1",
    prompt: "默认提示词",
    promptCharacterCount: 5,
    recommendedPromptCharacters: 500,
    maxPromptCharacters: 2_000,
    compileProfile: "seedance_director_v3",
    providerPrompt: "默认提示词",
    providerPromptCharacterCount: 5,
    manifestPrompt: "默认提示词",
    manifestPromptCharacterCount: 5,
    warnings: [],
    assetBindings: [],
    output: {
      model: "doubao-seedance-2-5-260628",
      resolution: "720p",
      ratio: "16:9",
      durationSeconds: 15,
      generateAudio: true,
      outputFormat: "mp4",
      watermark: false,
    },
    previewOnly: true,
    assetReady: true,
    submissionReady: false,
    fixtureOnly: true,
    ...overrides,
  };
}

describe("Seedance 双层提示词展示", () => {
  it("默认使用 Provider，并把超长 Manifest 作为独立制作清单", () => {
    const providerPrompt = "供".repeat(1_200);
    const manifestPrompt = "清".repeat(2_200);
    const presentation = normalizeSeedancePromptPackage(makePackage({
      prompt: providerPrompt,
      promptCharacterCount: 1_200,
      providerPrompt,
      providerPromptCharacterCount: 1_200,
      manifestPrompt,
      manifestPromptCharacterCount: 2_200,
    }));

    assert.equal(presentation.providerPrompt, providerPrompt);
    assert.equal(presentation.providerPromptCharacterCount, 1_200);
    assert.equal(presentation.manifestPrompt, manifestPrompt);
    assert.equal(presentation.manifestPromptCharacterCount, 2_200);
    assert.equal(presentation.hasDistinctManifest, true);
    assert.equal(presentation.providerLengthState, "warning");
  });

  it("旧版只有 prompt 时只展示一份并明确标记 legacy", () => {
    const presentation = normalizeSeedancePromptPackage(makePackage({
      prompt: "旧版合并",
      promptCharacterCount: 4,
      maxPromptCharacters: 2_000,
      compileProfile: "legacy_single_prompt_v1",
      providerPrompt: null,
      providerPromptCharacterCount: null,
      manifestPrompt: null,
      manifestPromptCharacterCount: null,
    }));

    assert.equal(presentation.providerPrompt, "旧版合并");
    assert.equal(presentation.manifestPrompt, "旧版合并");
    assert.equal(presentation.hasDistinctManifest, false);
    assert.equal(presentation.isLegacy, true);
    assert.match(LEGACY_PROMPT_NOTICE, /导演语言版本/);
  });

  it("旧双层包即使字段齐全也不能伪装成导演语言版本", () => {
    const presentation = normalizeSeedancePromptPackage(makePackage({
      compileProfile: "dual_layer_v1",
    }));

    assert.equal(presentation.isLegacy, true);
  });

  it("1.2 兼容投影可以展示，但仍要求重新规划后才能提交", () => {
    const presentation = normalizeSeedancePromptPackage(makePackage({
      compileProfile: "seedance_director_v3_compat",
    }));

    assert.equal(presentation.isLegacy, true);
  });

  it("缺少 Manifest 时回退 Provider，不制造重复折叠区", () => {
    const presentation = normalizeSeedancePromptPackage(makePackage({
      manifestPrompt: null,
      manifestPromptCharacterCount: null,
    }));

    assert.equal(presentation.manifestPrompt, presentation.providerPrompt);
    assert.equal(presentation.hasDistinctManifest, false);
  });
});

describe("Seedance 包状态展示", () => {
  it("分别列出开发预览和素材未齐两个阻断原因", () => {
    const status = readSeedancePackageStatus(makePackage({
      previewOnly: true,
      assetReady: false,
      submissionReady: false,
    }));

    assert.equal(status.previewLabel, "开发预览");
    assert.equal(status.assetLabel, "素材未齐");
    assert.equal(status.submissionLabel, "不可提交");
    assert.equal(status.blockers.length, 2);
    assert.match(status.blockers[0] ?? "", /开发预览边界/);
    assert.match(status.blockers[1] ?? "", /占位素材/);
  });

  it("正式包且素材齐备时独立显示可提交状态", () => {
    const status = readSeedancePackageStatus(makePackage({
      previewOnly: false,
      assetReady: true,
      submissionReady: true,
    }));

    assert.equal(status.previewLabel, "正式制作");
    assert.equal(status.assetLabel, "素材已齐");
    assert.equal(status.submissionLabel, "可提交");
    assert.deepEqual(status.blockers, []);
    assert.match(status.readyMessage ?? "", /受控提交流程/);
  });
});
