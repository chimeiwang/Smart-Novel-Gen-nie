import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  nextVideoRefreshDelay,
  videoProjectRefreshSignature,
} from "../video-refresh-policy";

describe("视频状态刷新策略", () => {
  it("连续无变化时逐步退避且不超过八秒", () => {
    assert.deepEqual(
      [0, 1, 2, 3, 10].map(nextVideoRefreshDelay),
      [2_000, 3_000, 5_000, 8_000, 8_000],
    );
  });

  it("签名只跟随场景状态与更新时间", () => {
    const project = {
      scenes: [{ id: "scene-1", status: "generating", updatedAt: "v1" }],
    };
    assert.equal(
      videoProjectRefreshSignature(project),
      "scene-1:generating:v1",
    );
    assert.notEqual(
      videoProjectRefreshSignature({
        scenes: [{ ...project.scenes[0], status: "awaiting_review" }],
      }),
      videoProjectRefreshSignature(project),
    );
  });
});
