import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  buildAgentRunFinalLogRecord,
  buildLLMRequestLogRecord,
  buildLLMResponseLogRecord,
  buildLLMToolCallLogRecord,
} from "@/shared/lib/logger";
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

  it("keeps initial execution and resume runs in the same task log", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "inkforge-workflow-resume-"));
    tempDirs.push(root);
    process.env.WORKFLOW_EVENT_LOG_ENABLED = "true";
    process.env.WORKFLOW_EVENT_LOG_DIR = path.join(root, "events");
    process.env.WORKFLOW_LOG_WRITE_IN_TESTS = "true";

    const firstRun = createWorkflowEventFileLogger({
      taskId: "task-resume-123456789",
      runKind: "writing-workflow",
    });
    firstRun.recordWorkflowEvent("workflow_started");
    firstRun.recordGraphInitialState({ phase: "active", operationStep: "init" });
    firstRun.recordWorkflowEvent("workflow_completed");

    const resumedRun = createWorkflowEventFileLogger({
      taskId: "task-resume-123456789",
      runKind: "resume-writing-workflow",
    });
    resumedRun.recordWorkflowEvent("resume_started");
    resumedRun.recordGraphInitialState({ phase: "awaiting_user_review", operationStep: "await_user_decision" });
    resumedRun.recordWorkflowEvent("resume_completed", { phase: "awaiting_user_review" });

    const runDir = path.join(root, "events", "runs", new Date().toISOString().slice(0, 10));
    const files = fs.readdirSync(runDir);
    assert.equal(files.length, 1);
    const trace = fs.readFileSync(path.join(runDir, files[0]), "utf-8");
    assert.match(trace, /工作流运行 R01/);
    assert.match(trace, /工作流运行 R02/);
    assert.match(trace, /类型: resume-writing-workflow \| 状态: 等待用户输入/);
  });

  it("does not create an empty human log when no LLM or LangGraph state ran", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "inkforge-workflow-empty-"));
    tempDirs.push(root);
    process.env.WORKFLOW_EVENT_LOG_ENABLED = "true";
    process.env.WORKFLOW_EVENT_LOG_DIR = path.join(root, "events");
    process.env.WORKFLOW_LOG_WRITE_IN_TESTS = "true";

    const logger = createWorkflowEventFileLogger({
      taskId: "task-short-circuit-123456789",
      runKind: "resume-writing-workflow",
    });
    logger.recordWorkflowEvent("resume_started", { decision: "approve" });
    logger.recordPersistenceEvent("artifact_applied", { success: true });

    const runDir = path.join(root, "events", "runs", new Date().toISOString().slice(0, 10));
    assert.equal(fs.existsSync(runDir), true);
    assert.deepEqual(fs.readdirSync(runDir), []);
  });

  it("writes only complete LLM records and Chinese LangGraph state transitions", () => {
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
    logger.recordLangGraphEvent({
      event: "on_chain_stream",
      data: {
        chunk: [["operationWorkflow:subgraph-1"], "updates", {
          prepareOperationContext: {
            operationStep: "execute_operation",
            operationStage: "准备操作上下文",
          },
        }],
      },
    });
    const runtimeTrace = logger.createRuntimeTrace();
    const agentCallId = runtimeTrace.allocateAgentCallId("写作");
    const stateRef = runtimeTrace.captureState({
      phase: "active",
      operationStep: "execute_operation",
      activeAgent: "写作",
    }, `${agentCallId} 输入状态`);
    logger.recordSSEEvent("agent_start", { agentId: "写作", agentName: "作家", agentCallId, stateRef });
    const reviewerCallId = runtimeTrace.allocateAgentCallId("编辑");
    const reviewerStateRef = runtimeTrace.captureState({
      phase: "active",
      operationStep: "review_artifact",
      activeAgent: "编辑",
    }, `${reviewerCallId} 输入状态`);
    logger.recordSSEEvent("agent_start", {
      agentId: "编辑",
      agentName: "网文商业编辑",
      agentCallId: reviewerCallId,
      stateRef: reviewerStateRef,
    });
    runtimeTrace.recordLLM(buildLLMRequestLogRecord({
      requestId: "model-request-1",
      messages: [{ role: "user", content: "完整用户请求" }],
      tools: [{ type: "function", function: { name: "submit_evaluation" } }],
      context: { taskId: "task-123456789", agentId: "写作", agentRunId: agentCallId, modelTurn: 1, stateRef },
      mode: "full",
    }));
    runtimeTrace.recordLLM(buildLLMResponseLogRecord({
      requestId: "model-request-1",
      content: "完整模型输出",
      reasoningContent: "完整供应商推理",
      toolCalls: [{ type: "function", function: { name: "submit_evaluation", arguments: "{\"verdict\":\"pass\"}" } }],
      usage: { promptTokens: 100, completionTokens: 20, cachedTokens: 60, totalTokens: 120 },
      context: { taskId: "task-123456789", agentId: "写作", agentRunId: agentCallId, modelTurn: 1, stateRef },
      mode: "full",
    }));
    runtimeTrace.recordLLM(buildLLMToolCallLogRecord({
      requestId: agentCallId,
      toolName: "submit_evaluation",
      args: { verdict: "pass" },
      result: "完整工具返回",
      context: { taskId: "task-123456789", agentId: "写作", agentRunId: agentCallId, modelTurn: 1, stateRef, toolCallIndex: 1, toolCallTotal: 1 },
      mode: "full",
    }));
    runtimeTrace.recordLLM(buildAgentRunFinalLogRecord({
      agentRunId: agentCallId,
      content: "不应重复展示的 Agent 汇总",
      context: { taskId: "task-123456789", agentId: "写作", stateRef },
      mode: "full",
    }));
    logger.recordSSEEvent("agent_status", { agentId: "写作", message: "不进入人工日志" });
    logger.recordSSEEvent("agent_done", {
      agentId: "编辑",
      agentName: "网文商业编辑",
      agentCallId: reviewerCallId,
      stateRef: reviewerStateRef,
      durationMs: 80,
      hasOutput: true,
    });
    logger.recordSSEEvent("agent_done", { agentId: "写作", agentName: "作家", agentCallId, stateRef, durationMs: 120, hasOutput: true });
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

    assert.match(trace, /工作流运行 R01/);
    assert.match(trace, /操作: 生成章节正文/);
    assert.match(trace, /# 一、LLM 输入与输出原文/);
    assert.match(trace, /# 二、LangGraph 状态切换（中文）/);
    assert.match(trace, /## A01 写作｜调用前状态 S004/);
    assert.match(trace, /第 1 轮 LLM 输入 >>>/);
    assert.match(trace, /第 1 轮 LLM 输出 <<</);
    assert.match(trace, /完整用户请求/);
    assert.match(trace, /完整模型输出/);
    assert.doesNotMatch(trace, /第 1 轮 工具 1\/1：submit_evaluation/);
    assert.doesNotMatch(trace, /完整供应商推理/);
    assert.doesNotMatch(trace, /完整工具返回/);
    assert.doesNotMatch(trace, /【发送给模型的工具定义原文】/);
    assert.match(trace, /## S001 LangGraph 初始状态/);
    assert.match(trace, /## S002 初始化会话完成后的状态/);
    assert.match(trace, /当前步骤：初始化 → 准备操作上下文/);
    assert.match(trace, /当前 Agent：无 → 写作/);
    assert.match(trace, /创作操作：无 → 生成章节正文/);
    assert.match(trace, /## S003 准备操作上下文完成后的状态/);
    assert.match(trace, /## S004 A01 Agent 调用前状态/);
    assert.match(trace, /## S005 A02 Agent 调用前状态/);
    assert.doesNotMatch(trace, /# 三、/);
    assert.doesNotMatch(trace, /# 四、/);
    assert.doesNotMatch(trace, /Workflow \/ LangGraph \/ SSE/);
    assert.doesNotMatch(trace, /GraphState 与节点 patch 原文/);
    assert.doesNotMatch(trace, /operationWorkflow:subgraph-1/);
    assert.doesNotMatch(trace, /完整节点输出内容/);
    assert.doesNotMatch(trace, /完整历史内容/);
    assert.doesNotMatch(trace, /不应重复展示的 Agent 汇总/);
    assert.doesNotMatch(trace, /不进入人工日志/);
    assert.doesNotMatch(trace, /token-99/);
    assert.equal(fs.existsSync(path.join(root, "events", `workflow-events-${new Date().toISOString().slice(0, 10)}.jsonl`)), false);
  });
});
