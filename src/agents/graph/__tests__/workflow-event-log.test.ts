import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  createWorkflowEventFileLogger,
  diffWorkflowState,
  projectWorkflowState,
} from "../workflow-event-log";

const ORIGINAL_ENV = {
  WORKFLOW_EVENT_LOG_ENABLED: process.env.WORKFLOW_EVENT_LOG_ENABLED,
  WORKFLOW_EVENT_LOG_DIR: process.env.WORKFLOW_EVENT_LOG_DIR,
  WORKFLOW_TRACE_LOG_DIR: process.env.WORKFLOW_TRACE_LOG_DIR,
  WORKFLOW_LOG_WRITE_IN_TESTS: process.env.WORKFLOW_LOG_WRITE_IN_TESTS,
};

const tempDirs: string[] = [];

function restoreEnv() {
  for (const [key, value] of Object.entries(ORIGINAL_ENV)) {
    if (value === undefined) delete process.env[key as keyof NodeJS.ProcessEnv];
    else process.env[key as keyof NodeJS.ProcessEnv] = value;
  }
}

describe("WorkflowEventFileLogger", () => {
  afterEach(() => {
    restoreEnv();
    for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
  });

  it("is disabled by default unless enabled from .env", () => {
    delete process.env.WORKFLOW_EVENT_LOG_ENABLED;

    const logger = createWorkflowEventFileLogger({
      taskId: "task-1",
      runKind: "writing-workflow",
    });

    assert.equal(logger.isEnabledForTests(), false);
  });

  it("can be enabled from .env", () => {
    process.env.WORKFLOW_EVENT_LOG_ENABLED = "true";

    const logger = createWorkflowEventFileLogger({
      taskId: "task-1",
      runKind: "writing-workflow",
    });

    assert.equal(logger.isEnabledForTests(), true);
  });

  it("projects and diffs only workflow-relevant GraphState fields", () => {
    const before = projectWorkflowState({
      phase: "active",
      operationStep: "prepare_context",
      activeAgent: "写作",
      novelData: { huge: "正文".repeat(1000) },
      artifactReview: { status: "draft", activeArtifactId: "artifact-123456789", iteration: 1 },
    });
    const after = { ...before, ...projectWorkflowState({
      operationStep: "execute_operation",
      activeAgent: "编辑",
      artifactReview: { status: "reviewing", activeArtifactId: "artifact-123456789", iteration: 2 },
    }) };
    const changes = diffWorkflowState(before, after);

    assert.equal("novelData" in before, false);
    assert.deepEqual(changes.operationStep, { before: "prepare_context", after: "execute_operation" });
    assert.deepEqual(changes.activeAgent, { before: "写作", after: "编辑" });
    assert.deepEqual(changes.artifactStatus, { before: "draft", after: "reviewing" });
  });

  it("writes a readable node/state/agent timeline into an isolated workflow trace", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "inkforge-workflow-trace-"));
    tempDirs.push(root);
    process.env.WORKFLOW_EVENT_LOG_ENABLED = "true";
    process.env.WORKFLOW_EVENT_LOG_DIR = path.join(root, "events");
    process.env.WORKFLOW_TRACE_LOG_DIR = path.join(root, "trace");
    process.env.WORKFLOW_LOG_WRITE_IN_TESTS = "true";

    const logger = createWorkflowEventFileLogger({
      taskId: "task-123456789",
      runKind: "writing-workflow",
    });
    logger.recordWorkflowEvent("workflow_started");
    logger.recordGraphInitialState({
      phase: "active",
      operationStep: "init",
      activeAgent: null,
      conversationHistory: [{ role: "user", content: "完整历史内容" }],
      novelData: { worldSetting: "不应进入可恢复状态审计" },
      streamCallbacks: { "写作": () => {} },
      artifactReview: { status: "idle", activeArtifactId: null, iteration: 0 },
    });
    logger.recordLangGraphEvent({
      event: "updates",
      data: {
        initSession: {
          operationStep: "prepare_context",
          activeAgent: "写作",
          currentOperation: {
            kind: "write_chapter",
            primaryAgent: "写作",
            reviewers: ["校验", "编辑"],
          },
          generatedContent: "完整节点输出内容",
        },
      },
    });
    logger.recordSSEEvent("agent_start", { agentId: "写作", agentName: "作家" });
    logger.recordSSEEvent("agent_status", { agentId: "写作", message: "不进入人工日志" });
    logger.recordSSEEvent("agent_done", { agentId: "写作", agentName: "作家", durationMs: 120, hasOutput: true });
    for (let index = 0; index < 100; index += 1) {
      logger.recordLangGraphEvent({
        event: "on_chat_model_stream",
        name: "ChatOpenAI",
        data: { chunk: { content: `token-${index}` } },
        metadata: { langgraph_checkpoint_ns: "很长且无人工阅读价值的底层元数据" },
      });
    }

    const runDir = path.join(root, "events", "runs", new Date().toISOString().slice(0, 10));
    const traceFile = fs.readdirSync(runDir).map((name) => path.join(runDir, name))[0];
    const trace = fs.readFileSync(traceFile, "utf-8");

    assert.match(trace, /工作流运行/);
    assert.match(trace, /LANGGRAPH 初始状态/);
    assert.match(trace, /LANGGRAPH 节点 #1 完成：initSession/);
    assert.match(trace, /operationStep: init → prepare_context/);
    assert.match(trace, /activeAgent: null → 写作/);
    assert.match(trace, /AGENT 调用 #1 开始：写作/);
    assert.match(trace, /AGENT 调用 #1 完成：写作/);
    assert.match(trace, /后续 LLM 输入、输出和工具调用将直接接在本文件中/);
    assert.match(trace, /【完整 GraphState】/);
    assert.match(trace, /完整历史内容/);
    assert.match(trace, /untracked novel data omitted/);
    assert.match(trace, /runtime-only omitted/);
    assert.match(trace, /【节点返回的完整 state patch】/);
    assert.match(trace, /完整节点输出内容/);
    assert.doesNotMatch(trace, /不进入人工日志/);
    assert.doesNotMatch(trace, /token-99/);
    assert.equal(fs.existsSync(path.join(root, "events", `workflow-events-${new Date().toISOString().slice(0, 10)}.jsonl`)), false);
  });
});
