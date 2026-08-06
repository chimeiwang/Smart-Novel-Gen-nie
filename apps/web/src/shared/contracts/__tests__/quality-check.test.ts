import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  RunQualityCheckSchema,
  UpdateQualityCheckStatusSchema,
  type QualityCheckDto,
} from "../quality-check";

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

test("质量运行请求必须携带调用方生成的幂等请求号", () => {
  assert.equal(RunQualityCheckSchema.safeParse({ checkId: "check-1" }).success, false);
  assert.equal(
    RunQualityCheckSchema.safeParse({
      checkId: "check-1",
      clientRequestId: "quality-run-1",
    }).success,
    true,
  );
});

test("质量状态更新必须携带当前服务端版本", () => {
  assert.equal(
    UpdateQualityCheckStatusSchema.safeParse({
      id: "check-1",
      status: "skipped",
    }).success,
    false,
  );
  assert.equal(
    UpdateQualityCheckStatusSchema.safeParse({
      id: "check-1",
      status: "skipped",
      expectedUpdatedAt: "2026-08-06T00:00:00Z",
    }).success,
    true,
  );
});
