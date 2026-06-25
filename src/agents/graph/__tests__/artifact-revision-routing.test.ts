import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { buildArtifactRevisionResume } from "../artifact-revision-routing";

describe("artifact revision routing", () => {
  it("routes revise decisions back to the artifact producer with artifact context", () => {
    const result = buildArtifactRevisionResume({
      artifactId: "artifact-1",
      artifactKey: "outline-v1",
      revision: 2,
      createdByAgent: "剧情",
      updatedByAgent: "剧情",
      reviewerAgent: "编辑",
      userMessage: "继续修改待审核草案",
    });

    assert.equal(result?.targetAgent, "剧情");
    assert.match(result?.userMessage ?? "", /^@剧情 /);
    assert.match(result?.userMessage ?? "", /artifact-1/);
    assert.match(result?.userMessage ?? "", /outline-v1/);
    assert.match(result?.userMessage ?? "", /继续修改待审核草案/);
  });

  it("prefers the latest updating agent over the original creator", () => {
    const result = buildArtifactRevisionResume({
      artifactId: "artifact-2",
      artifactKey: null,
      revision: 1,
      createdByAgent: "剧情",
      updatedByAgent: "设定",
      reviewerAgent: "编辑",
    });

    assert.equal(result?.targetAgent, "设定");
    assert.match(result?.userMessage ?? "", /^@设定 /);
  });

  it("does not route to the reviewer when producer fields are missing", () => {
    const result = buildArtifactRevisionResume({
      artifactId: "artifact-3",
      artifactKey: null,
      revision: 1,
      createdByAgent: null,
      updatedByAgent: null,
      reviewerAgent: "编辑",
    });

    assert.equal(result, null);
  });
});
