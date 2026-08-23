import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { ShotVisualReference, VisualCanon } from "../types";
import {
  currentCanonVersion,
  recommendedVisualReferences,
  sameVisualReferences,
  visualReferenceWarnings,
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

describe("视觉设定与镜头参考推荐", () => {
  it("只推荐镜头上下文中出现且已经批准的视觉设定", () => {
    const identity = canon();
    const scene = canon({
      id: "canon-2",
      settingKind: "location",
      settingId: "location-1",
      settingName: "雾港钟楼",
      duty: "scene",
      currentVersionId: null,
      versions: [],
    });

    assert.deepEqual(recommendedVisualReferences([identity, scene], "林岚走进雾港钟楼"), [
      { canonVersionId: "version-1", strength: 72 },
    ]);
  });

  it("区分未批准与已批准但未绑定", () => {
    const identity = canon();
    const scene = canon({
      id: "canon-2",
      settingKind: "location",
      settingId: "location-1",
      settingName: "雾港钟楼",
      duty: "scene",
      currentVersionId: null,
      versions: [],
    });
    const references: ShotVisualReference[] = [];

    assert.deepEqual(
      visualReferenceWarnings(
        [identity, scene],
        "林岚走进雾港钟楼",
        references,
      ),
      [
        "林岚的身份图尚未绑定到本镜",
        "雾港钟楼的场景图还没有批准版本",
      ],
    );
  });

  it("当前版本必须按 Head 精确选择而不是取数组第一项", () => {
    const value = canon({
      currentVersionId: "version-1",
      versions: [
        { ...canon().versions[0], id: "version-2", versionNo: 2 },
        canon().versions[0],
      ],
    });

    assert.equal(currentCanonVersion(value)?.id, "version-1");
  });

  it("按版本、素材、强度和顺序识别提示词快照是否落后于当前绑定", () => {
    const reference: ShotVisualReference = {
      canonVersionId: "version-1",
      assetId: "asset-1",
      assetSha256: "a".repeat(64),
      settingKind: "character",
      settingId: "character-1",
      settingName: "林岚",
      duty: "identity",
      variantKey: "default",
      label: "标准身份",
      includeFeatures: [],
      excludeFeatures: [],
      strength: 70,
    };

    assert.equal(sameVisualReferences([reference], [{ ...reference }]), true);
    assert.equal(
      sameVisualReferences([reference], [{ ...reference, strength: 72 }]),
      false,
    );
    assert.equal(
      sameVisualReferences(
        [reference, { ...reference, canonVersionId: "version-2", assetId: "asset-2" }],
        [{ ...reference, canonVersionId: "version-2", assetId: "asset-2" }, reference],
      ),
      false,
    );
  });
});
