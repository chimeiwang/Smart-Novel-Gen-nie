import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { chunkRagText } from "@/shared/lib/rag-service";

describe("RAG reference chunking", () => {
  it("returns no chunks for empty content", () => {
    assert.deepEqual(chunkRagText(" \n\n "), []);
  });

  it("keeps a short document as one chunk", () => {
    assert.deepEqual(chunkRagText("第一段\n\n第二段", 100), ["第一段\n\n第二段"]);
  });

  it("splits long text without losing content", () => {
    const text = "开头" + "长".repeat(25) + "结尾";
    const chunks = chunkRagText(text, 10);

    assert.ok(chunks.length > 1);
    assert.equal(chunks.join(""), text);
  });
});
