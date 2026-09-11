import assert from "node:assert/strict";
import test from "node:test";

import {
  productionCapabilityProblems,
  productionKeyframeInputs,
  productionKeyframeProblems,
  restoreProductionKeyframeSelection,
} from "../production/production-baseline-state";
import { impactDecisionNotesComplete, rebaseImpactDecisions } from "../production/impact-review-state";
import { storyboardReviewPresentation } from "../production/storyboard-review-presentation";
import { editDraftProblems, mixDraftProblems } from "../production/post-production-state";
import {
  baselineAdoptionInputs,
  takeCandidateMatchesSource,
  takeDirectInputDifferences,
  takeReferenceHashesForReview,
} from "../production/take-adoption-state";
import {
  appendStoryboardShot,
  duplicateStoryboardShot,
  moveStoryboardShot,
  reconcileStoryboardShotIds,
  storyboardShotIdentity,
  updateStoryboardShot,
} from "../production/storyboard-document-state";
import type { EpisodeEditVersion, EpisodePostAsset, ProductionBaseline, ProductionCapability, ScriptVersion, StoryboardDocument, StoryboardVersion, TakeCandidate } from "../production/types";

const capability: ProductionCapability = {
  provider: "seedance",
  model: "服务端模型",
  generationMode: "reference",
  executionMode: "simulated",
  feeConfirmationRequired: false,
  videoPreviewEnabled: true,
  providerConfigured: false,
  providerEnabled: false,
  allowedDurationSeconds: [4, 6, 8],
  allowedResolution: "720p",
  allowedOutputFormat: "mp4",
  maxImageReferences: 20,
};

function document(): StoryboardDocument {
  return {
    schemaVersion: "video-episode-storyboard/1.0",
    shots: [
      {
        id: "shot-a",
        tempKey: null,
        lineage: [],
        scriptSceneId: "scene-1",
        scriptLineIds: ["line-1"],
        title: "交信",
        action: "林岚递出信",
        framing: "medium",
        cameraMovement: "static",
        durationMs: 4_000,
        productionIntent: {
          provider: "seedance",
          model: "服务端模型",
          generationMode: "reference",
          executionMode: "simulated",
          feeConfirmed: false,
          prompt: "雨夜门廊，林岚递出信",
          ratio: "9:16",
          durationSeconds: 4,
          resolution: "720p",
          generateAudio: true,
          watermark: false,
          outputFormat: "mp4",
          references: [{ canonVersionId: "canon-v1", strength: 70 }],
        },
      },
      {
        id: "shot-b",
        tempKey: null,
        lineage: [],
        scriptSceneId: "scene-1",
        scriptLineIds: [],
        title: "顾舟反应",
        action: "顾舟抬眼",
        framing: "close_up",
        cameraMovement: "static",
        durationMs: 4_000,
        productionIntent: {
          provider: "seedance",
          model: "服务端模型",
          generationMode: "reference",
          executionMode: "simulated",
          feeConfirmed: false,
          prompt: "顾舟抬眼",
          ratio: "9:16",
          durationSeconds: 4,
          resolution: "720p",
          generateAudio: true,
          watermark: false,
          outputFormat: "mp4",
          references: [{ canonVersionId: "canon-v2", strength: 65 }],
        },
      },
    ],
  };
}

test("新增镜头使用服务端能力而不是浏览器自造模型与执行模式", () => {
  const next = appendStoryboardShot({ schemaVersion: "video-episode-storyboard/1.0", shots: [] }, {
    tempKey: "temp-1",
    scriptSceneId: "scene-1",
    title: "收回信",
    action: "林岚收回手",
    prompt: "林岚因迟疑收回信",
    references: [{ canonVersionId: "canon-v1", strength: 72 }],
    ratio: "9:16",
    capability,
    durationSeconds: 6,
    feeConfirmed: false,
  });
  const shot = next.shots?.[0];
  assert.equal(shot?.tempKey, "temp-1");
  assert.equal(shot?.productionIntent.model, "服务端模型");
  assert.equal(shot?.productionIntent.executionMode, "simulated");
  assert.equal(shot?.productionIntent.durationSeconds, 6);
  assert.equal(shot?.durationMs, 6_000);
});

test("改名和场内调序保持稳定 shotId，复制显式创建 copy 沿袭", () => {
  const renamed = updateStoryboardShot(document(), "shot-a", (shot) => ({ ...shot, title: "林岚收信" }));
  const moved = moveStoryboardShot(renamed, "shot-b", -1);
  assert.deepEqual(moved.shots?.map(storyboardShotIdentity), ["shot-b", "shot-a"]);
  assert.equal(moved.shots?.[1]?.title, "林岚收信");
  const duplicated = duplicateStoryboardShot(moved, "shot-a", "temp-copy");
  assert.ok(duplicated);
  const copy = duplicated.shots?.find((shot) => shot.tempKey === "temp-copy");
  assert.equal(copy?.id, null);
  assert.deepEqual(copy?.lineage, [{ sourceShotId: "shot-a", relation: "copy" }]);
  assert.equal(document().shots?.[0]?.title, "交信");
});

test("Core 身份映射只回填 tempKey，不覆盖保存期间继续编辑的内容", () => {
  const local = appendStoryboardShot({ schemaVersion: "video-episode-storyboard/1.0", shots: [] }, {
    tempKey: "temp-late",
    scriptSceneId: "scene-1",
    title: "作者继续改过的标题",
    action: "继续输入的动作",
    prompt: "继续输入的提示词",
    references: [{ canonVersionId: "canon-v1" }],
    ratio: "9:16",
    capability,
    durationSeconds: 4,
    feeConfirmed: false,
  });
  const reconciled = reconcileStoryboardShotIds(local, { "temp-late": "stable-shot" });
  assert.equal(reconciled.shots?.[0]?.id, "stable-shot");
  assert.equal(reconciled.shots?.[0]?.tempKey, null);
  assert.equal(reconciled.shots?.[0]?.title, "作者继续改过的标题");
});

test("旧正式分镜与当前服务端能力不一致时阻止创建新基线", () => {
  const version = { document: document() } as StoryboardVersion;
  assert.deepEqual(productionCapabilityProblems(version, capability), []);
  assert.deepEqual(productionCapabilityProblems(version, { ...capability, model: "新模型" }), [
    "镜头 1 的冻结能力与服务端当前允许值不同",
    "镜头 2 的冻结能力与服务端当前允许值不同",
  ]);
});

test("制作基线按正式镜头顺序冻结关键帧并恢复合法本地选择", () => {
  const storyboard = {
    document: document(),
    shots: [
      { id: "shot-version-a", content: document().shots![0]! },
      { id: "shot-version-b", content: document().shots![1]! },
    ],
  } as StoryboardVersion;
  const restored = restoreProductionKeyframeSelection({
    "shot-version-a": { end_state: "asset-end", initial_state: "asset-start", unknown: "ignored" },
    "shot-version-b": { transition_anchor: "asset-turn" },
    broken: null,
  });

  assert.deepEqual(productionKeyframeInputs(storyboard, restored), [
    { shotVersionId: "shot-version-a", role: "initial_state", assetId: "asset-start" },
    { shotVersionId: "shot-version-a", role: "end_state", assetId: "asset-end" },
    { shotVersionId: "shot-version-b", role: "transition_anchor", assetId: "asset-turn" },
  ]);
});

test("视觉参考与关键帧逐镜合计超过服务端上限时阻止确认", () => {
  const crowdedShot = {
    ...document().shots![0]!,
    productionIntent: {
      ...document().shots![0]!.productionIntent,
      references: Array.from({ length: 19 }, (_, index) => ({ canonVersionId: `canon-${index}`, strength: 70 })),
    },
  };
  const storyboard = { document: document(), shots: [{ id: "shot-version-a", content: crowdedShot }] } as StoryboardVersion;
  const selection = { "shot-version-a": { initial_state: "asset-start", end_state: "asset-end" } } as const;

  assert.deepEqual(productionKeyframeProblems(storyboard, selection, new Set(["asset-start", "asset-end"]), 20), [
    "镜头 1 的视觉参考与关键帧合计超过 20 张",
  ]);
  assert.deepEqual(productionKeyframeProblems(storyboard, { "shot-version-a": { initial_state: "missing" } }, new Set(), 20), [
    "镜头 1 选择了已不在批准定妆版本中的关键帧素材",
  ]);
});

test("影响决定冲突时只覆盖本窗口改过的项目，保留远端其他决定", () => {
  const remote = [
    { itemId: "letter", action: "revise_target" as const, note: "另一窗口决定返工" },
    { itemId: "memory", action: "not_applicable" as const, note: "回忆发生在三日前" },
  ];
  const local = [
    { itemId: "letter", action: "keep_existing" as const, note: "本窗口原始值" },
    { itemId: "memory", action: "defer" as const, note: "本窗口只改了这项" },
  ];
  assert.deepEqual(rebaseImpactDecisions(remote, local, new Set(["memory"])), [remote[0], local[1]]);
});

test("非暂缓影响决定必须写明可审计依据", () => {
  assert.equal(impactDecisionNotesComplete([{ itemId: "a", action: "defer", note: "" }]), true);
  assert.equal(impactDecisionNotesComplete([{ itemId: "a", action: "keep_existing", note: "   " }]), false);
  assert.equal(impactDecisionNotesComplete([{ itemId: "a", action: "revise_target", note: "承接状态已经改变" }]), true);
});

test("分镜候选只有完整 pass 结论才能显示 AI 审阅通过", () => {
  assert.equal(storyboardReviewPresentation({ review: null, reviewFindings: [] }).label, "尚无审阅结果");
  assert.equal(storyboardReviewPresentation({ review: { decision: "revise", summary: "需要修订", requiredChanges: ["补足反应镜头"], findings: [] }, reviewFindings: [] }).label, "仍有待核对项");
  assert.equal(storyboardReviewPresentation({ review: { decision: "pass", summary: "镜头范围已核对", requiredChanges: [], findings: [] }, reviewFindings: [] }).label, "已通过 AI 审阅");
});

test("Take 采用只接受与源基线冻结输入精确关联的候选", () => {
  const sha256 = "a".repeat(64);
  const source = {
    ordinal: 1,
    shotId: "stable-a",
    shotVersionId: "shot-version-a",
    adoptionId: null,
    status: "pending",
    inputHash: "b".repeat(64),
    inputSnapshot: {
      schemaVersion: "video-production-shot-input/1.0",
      shotId: "stable-a",
      shotVersionId: "shot-version-a",
      shotVersionNo: 1,
      shotContentHash: "c".repeat(64),
      scriptSceneId: "scene-1",
      scriptLineIds: ["line-1"],
      provider: "seedance",
      model: "服务端模型",
      generationMode: "reference",
      executionMode: "simulated",
      feeConfirmed: false,
      promptVersionId: "prompt-v1",
      prompt: "雨夜门廊，林岚递出信",
      ratio: "9:16",
      durationSeconds: 4,
      resolution: "720p",
      generateAudio: true,
      watermark: false,
      outputFormat: "mp4",
      references: [{ canonVersionId: "canon-v1", sha256 }],
    },
  } satisfies ProductionBaseline["shots"][number];
  const baseline = { id: "baseline-a", shots: [source] } as ProductionBaseline;
  const target = { id: "target-v2", scriptSceneId: "scene-1", scriptLineIds: ["line-1"], content: document().shots![0]! } as StoryboardVersion["shots"][number];
  const candidate = { sourceBaselineId: baseline.id, sourceShotId: source.shotId, sourceShotVersionId: source.shotVersionId, inputHash: source.inputHash } as TakeCandidate;
  assert.equal(takeCandidateMatchesSource(candidate, baseline, source), true);
  assert.deepEqual(takeDirectInputDifferences(source, target), []);
  assert.deepEqual(takeReferenceHashesForReview(source), [sha256]);
  assert.equal(takeCandidateMatchesSource({ ...candidate, inputHash: "d".repeat(64) }, baseline, source), false);
});

test("新制作基线只按正式分镜顺序带入目标匹配的采用记录", () => {
  const storyboard = {
    shots: [{ id: "shot-v1" }, { id: "shot-v2" }],
  } as StoryboardVersion;
  const adoptions = { "shot-v2": "adoption-2", outsider: "adoption-x" };
  assert.deepEqual(baselineAdoptionInputs(storyboard, adoptions), [
    { shotVersionId: "shot-v2", adoptionId: "adoption-2" },
  ]);
});

test("粗剪允许重复同一采用素材，但每个基线镜头必须成片或明确省略", () => {
  const baseline = { shots: [
    { ordinal: 1, shotId: "shot-1", shotVersionId: "shot-v1", adoptionId: "adopt-1" },
    { ordinal: 2, shotId: "shot-2", shotVersionId: "shot-v2", adoptionId: null },
  ] } as ProductionBaseline;
  const take = { id: "take-1", adoptionId: "adopt-1", durationMs: 2_000 } as TakeCandidate;
  const draft = {
    basedOnVersionId: null,
    expectedHeadRevision: 1,
    clips: [
      { tempKey: "clip-a", adoptionId: "adopt-1", takeId: "take-1", sourceInMs: 0, sourceOutMs: 1_000, sourceAudioMode: "keep" as const, transitionAfter: "cut" as const, transitionDurationMs: 0 },
      { tempKey: "clip-b", adoptionId: "adopt-1", takeId: "take-1", sourceInMs: 1_000, sourceOutMs: 2_000, sourceAudioMode: "mute" as const, transitionAfter: "cut" as const, transitionDurationMs: 0 },
    ],
    omissions: [{ shotVersionId: "shot-v2", reason: "本镜改由对白字幕承接" }],
  };
  const adoptionTakes = { "adopt-1": "take-1" };
  assert.deepEqual(editDraftProblems(baseline, draft, { "take-1": take }, adoptionTakes), []);
  assert.match(editDraftProblems(baseline, { ...draft, omissions: [] }, { "take-1": take }, adoptionTakes).join("；"), /镜头 2/);
  assert.match(editDraftProblems(baseline, { ...draft, clips: [{ ...draft.clips[0]!, sourceOutMs: 2_500 }] }, { "take-1": take }, adoptionTakes).join("；"), /实测素材时长/);
});

test("声音字幕只能落在确切粗剪时长和镜头绑定的正式台词上", () => {
  const edit = { id: "edit-1", totalDurationMs: 4_000 } as EpisodeEditVersion;
  const storyboard = { shots: [{ id: "shot-v1", scriptLineIds: ["line-1"] }] } as StoryboardVersion;
  const script = { document: { scenes: [{ lines: [{ id: "line-1", kind: "dialogue", text: "别回头" }] }] } } as ScriptVersion;
  const asset = { id: "audio-1", modality: "audio", durationMs: 2_000 } as EpisodePostAsset;
  const draft = {
    basedOnVersionId: null,
    expectedHeadRevision: 1,
    editVersionId: "edit-1",
    audioClips: [{ trackKind: "music" as const, assetId: "audio-1", shotVersionId: null, timelineStartMs: 0, sourceInMs: 0, sourceOutMs: 2_000, gainMillibels: -1200, fadeInMs: 0, fadeOutMs: 0 }],
    subtitleCues: [{ shotVersionId: "shot-v1", scriptLineId: "line-1", startMs: 0, endMs: 1_500, speaker: null, text: "别回头" }],
  };
  assert.deepEqual(mixDraftProblems(edit, draft, [asset], storyboard, script), []);
  assert.match(mixDraftProblems(edit, { ...draft, subtitleCues: [{ ...draft.subtitleCues[0]!, scriptLineId: "line-x" }] }, [asset], storyboard, script).join("；"), /正式剧本节点/);
});
