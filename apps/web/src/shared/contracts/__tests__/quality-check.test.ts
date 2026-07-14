import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import type { QualityCheckDto } from "../quality-check";

const generatedExample = {
  id: "check-1",
  chapterId: "chapter-1",
  type: "consistency",
  status: "pending",
  title: "一致性终检",
  summary: null,
  result: null,
  scoreHook: null,
  scoreTension: null,
  scorePayoff: null,
  scorePacing: null,
  scoreEndingHook: null,
  scoreReaderPromise: null,
  scoreOverall: null,
  qualityGate: null,
  rewriteBrief: null,
  createdAt: "2026-07-14T00:00:00Z",
  updatedAt: "2026-07-14T00:00:00Z",
} satisfies QualityCheckDto;

test("质量检查 DTO 直接派生自生成客户端", async () => {
  assert.equal(generatedExample.type, "consistency");
  const contractUrl = new URL("../quality-check.ts", import.meta.url);
  const source = await readFile(contractUrl, "utf8");

  assert.match(source, /import type \{ components \} from "@inkforge\/api-client"/);
  assert.match(
    source,
    /components\["schemas"\]\["QualityCheckDto"\]/,
  );
  assert.doesNotMatch(source, /QualityCheckDtoSchema/);
  assert.doesNotMatch(source, /toQualityCheckDto/);
});
