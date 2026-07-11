import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { semanticSearchReferencesExecutor } from "../reference-tools";

function state(novelData: Record<string, unknown>, novelId?: string) {
  return { novelData, novelId };
}

describe("参考资料 RAG 只读工具", () => {
  it("缺少 novelId 时明确报错", async () => {
    const output = await semanticSearchReferencesExecutor({ query: "门派设定" }, state({}));
    const parsed = JSON.parse(output);

    assert.equal(parsed.error, "NOVEL_ID_REQUIRED");
  });

  it("未配置 embedding 时返回未启用状态", async () => {
    const oldKey = process.env.RAG_EMBEDDING_API_KEY;
    const oldBase = process.env.RAG_EMBEDDING_BASE_URL;
    const oldModel = process.env.RAG_EMBEDDING_MODEL;
    delete process.env.RAG_EMBEDDING_API_KEY;
    delete process.env.RAG_EMBEDDING_BASE_URL;
    delete process.env.RAG_EMBEDDING_MODEL;
    try {
      const output = await semanticSearchReferencesExecutor({ query: "门派设定" }, state({}, "novel-1"));
      const parsed = JSON.parse(output);

      assert.equal(parsed.enabled, false);
      assert.match(parsed.message, /未配置/);
    } finally {
      if (oldKey === undefined) delete process.env.RAG_EMBEDDING_API_KEY;
      else process.env.RAG_EMBEDDING_API_KEY = oldKey;
      if (oldBase === undefined) delete process.env.RAG_EMBEDDING_BASE_URL;
      else process.env.RAG_EMBEDDING_BASE_URL = oldBase;
      if (oldModel === undefined) delete process.env.RAG_EMBEDDING_MODEL;
      else process.env.RAG_EMBEDDING_MODEL = oldModel;
    }
  });
});
