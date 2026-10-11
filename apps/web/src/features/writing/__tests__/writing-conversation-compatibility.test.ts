import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../writing-conversation.tsx", import.meta.url), "utf8");

test("旧图流程拒绝把 V2 运行响应当作 V1 继续", () => {
  assert.match(source, /run\.engineVersion !== 1/);
  assert.match(source, /terminal\.engineVersion !== 1/);
  assert.match(source, /accepted\.engineVersion !== 1/);
});

test("流程日志保留完整用户输入", () => {
  assert.match(source, /content: `用户: \$\{userMessage\}`/);
  assert.doesNotMatch(source, /用户: \$\{userMessage\.slice\(0, 50\)/);
});


test("前台展示现有 Agent 流程并屏蔽历史执行器内部状态", () => {
  assert.match(source, /liveAgentRuns\.map\(\(run\)\s*=>/);
  assert.match(source, /openWritingRunEvents/);
  assert.match(source, /case "run_outcome"/);
  assert.doesNotMatch(source, /workflowRun\.activeSteps|createWorkflowRunUiState/);
  assert.doesNotMatch(source, /deploymentFingerprint|deploymentProfileKey|endpointProfile/);
});
