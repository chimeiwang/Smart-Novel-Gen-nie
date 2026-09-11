import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { VideoProject, VisualCanon } from "../types";
import {
  currentCanonVersion,
  parseVisualFeatures,
  selectSeriesProject,
  visualDuties,
  visualVariantKey,
  createVisualCandidateDraft,
  rebaseVisualCandidateDraft,
} from "../visual-canon-state";

function canon(overrides: Partial<VisualCanon> = {}): VisualCanon {
  return {
    id: "canon-1",
    projectId: "project-1",
    novelId: "novel-1",
    settingKind: "character",
    settingId: "character-1",
    settingName: "林岚",
    duty: "identity",
    variantKey: "default",
    label: "标准身份",
    candidateAsset: null,
    candidateIncludeFeatures: [],
    candidateExcludeFeatures: [],
    candidateDefaultStrength: null,
    currentVersionId: "version-1",
    versions: [{
      id: "version-1",
      canonId: "canon-1",
      versionNo: 1,
      asset: {
        id: "asset-1",
        projectId: "project-1",
        name: "林岚身份图",
        modality: "image",
        duty: "identity",
        mimeType: "image/png",
        byteSize: 10,
        durationMs: null,
        sha256: "a".repeat(64),
        sourceKind: "user_upload",
        rightsStatus: "confirmed",
        lockedAt: "2026-08-22T00:00:00",
        createdAt: "2026-08-22T00:00:00",
        updatedAt: "2026-08-22T00:00:00",
      },
      settingName: "林岚",
      label: "标准身份",
      includeFeatures: [],
      excludeFeatures: [],
      defaultStrength: 72,
      contentHash: "b".repeat(64),
      createdAt: "2026-08-22T00:00:00",
    }],
    revision: 2,
    createdAt: "2026-08-22T00:00:00",
    updatedAt: "2026-08-22T00:00:00",
    ...overrides,
  };
}

describe("设定定妆的项目与表单边界", () => {
  const project = (id: string, mode: string): VideoProject => ({ id, novelId: "novel", title: id, mode, status: "draft", targetAspectRatio: "9:16", targetLanguage: "zh-CN", provider: "seedance_2_5", revision: 1, createdAt: "2026-09-09T00:00:00Z", updatedAt: "2026-09-09T00:00:00Z" });

  it("当前定妆版本严格按 Head 选择", () => {
    const value = canon({
      currentVersionId: "version-1",
      versions: [
        { ...canon().versions[0], id: "version-2", versionNo: 2 },
        canon().versions[0],
      ],
    });

    assert.equal(currentCanonVersion(value)?.id, "version-1");
  });

  it("首次选择只接受 series，不把已有预告片项目误用为章节影视化", () => {
    assert.equal(selectSeriesProject([project("trailer", "trailer")]), null);
    assert.equal(selectSeriesProject([project("trailer", "trailer"), project("series", "series")])?.id, "series");
    assert.equal(selectSeriesProject([project("a", "series"), project("b", "series")], "b")?.id, "b");
    assert.equal(selectSeriesProject([project("a", "series"), project("trailer", "trailer")], "trailer")?.id, "a");
  });

  it("职责由文字设定种类决定，人物服装不混进地点或道具", () => {
    assert.deepEqual(visualDuties("character"), ["identity", "costume"]);
    assert.deepEqual(visualDuties("location"), ["scene"]);
    assert.deepEqual(visualDuties("item"), ["prop"]);
  });

  it("候选编辑冻结最初revision，远端更新只有明确继续编辑才推进且保留本地描述", () => {
    const saved = canon();
    const draft = createVisualCandidateDraft("identity", "first-request", saved);
    const edited = { ...draft, includeFeatures: "用户刚改的黑发和眉骨", label: "我保留的名称" };
    const remote = { ...saved, revision: saved.revision + 2, label: "另一页面名称" };
    assert.equal(edited.expectedRevision, saved.revision);
    const rebased = rebaseVisualCandidateDraft(edited, remote, "next-request");
    assert.equal(rebased.expectedRevision, remote.revision);
    assert.equal(rebased.includeFeatures, edited.includeFeatures);
    assert.equal(rebased.label, edited.label);
    assert.equal(rebased.variantKey, edited.variantKey);
    assert.equal(rebased.clientRequestId, "next-request");
    assert.throws(() => rebaseVisualCandidateDraft(edited, { ...remote, variantKey: "other" }, "bad"), /另一个定妆变体/);
    assert.equal(createVisualCandidateDraft("identity", "new-request").expectedRevision, 0);
  });

  it("新变体按独立请求标识生成，重复中文名称不会覆盖已有槽", () => {
    const first = visualVariantKey("850c1ca4-984f-45de-abc9-de0238b9b250");
    const second = visualVariantKey("850c1ca4-984f-45de-abc9-de0238b9b251");
    assert.match(first, /^[a-z0-9][a-z0-9_-]{0,63}$/);
    assert.notEqual(first, second);
    assert.equal(first, visualVariantKey("850c1ca4-984f-45de-abc9-de0238b9b250"));
  });

  it("视觉特征保留完整文字并拒绝超限，不静默截断", () => {
    assert.deepEqual(parseVisualFeatures("黑发， 左眉疤痕\n黑发,中性表情"), ["黑发", "左眉疤痕", "中性表情"]);
    assert.throws(() => parseVisualFeatures(Array.from({ length: 21 }, (_, index) => `特征${index}`).join("，")), /20 项/);
    assert.throws(() => parseVisualFeatures("字".repeat(121)), /120 字/);
    assert.deepEqual(parseVisualFeatures("𠮷".repeat(120)), ["𠮷".repeat(120)]);
  });
});
