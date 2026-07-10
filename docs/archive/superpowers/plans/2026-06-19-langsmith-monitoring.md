> 状态：历史归档，不作为当前实现依据。当前事实以 `DOCS.md`、`AGENTS.md`、`src/agents/AGENTS.md`、代码和 schema 为准。

# LangSmith Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 LangGraph Studio 调试主路径的 LangSmith trace 覆盖，让 workflow、operation 阶段、Agent、LLM 和工具调用能形成可观察链路。

**Architecture:** 复用现有 `src/agents/lib/langsmith-tracer.ts`，不新增监控框架。Studio 入口显式初始化 LangSmith；operation graph 节点用 trace 包装关键阶段；AgentRuntime 工具执行用 `traceTool` 包装，保留现有本地日志。

**Tech Stack:** TypeScript, LangGraph, LangSmith SDK, Node test runner, Next.js App Router.

---

### Task 1: LangSmith 初始化与测试辅助

**Files:**
- Modify: `src/agents/lib/langsmith-tracer.ts`
- Create: `src/agents/lib/langsmith-studio-init.ts`
- Test: `src/agents/lib/__tests__/langsmith-tracer.test.ts`

- [ ] **Step 1: Write failing tests**

Create tests that verify `initLangSmithTracer()` enables tracing when `LANGSMITH_API_KEY` and `LANGSMITH_TRACING=true` exist, disables tracing otherwise, and exposes a reset helper for deterministic tests.

- [ ] **Step 2: Run tests to verify failure**

Run: `npx tsx --test src/agents/lib/__tests__/langsmith-tracer.test.ts`
Expected: FAIL because the test helper and Studio init module do not exist yet.

- [ ] **Step 3: Implement minimal code**

Add a test-only reset export and a small `initLangSmithForStudio()` helper that calls `initLangSmithTracer()` before exporting the graph.

- [ ] **Step 4: Run tests to verify pass**

Run: `npx tsx --test src/agents/lib/__tests__/langsmith-tracer.test.ts`
Expected: PASS.

### Task 2: Tool Trace Coverage

**Files:**
- Modify: `src/agents/runtime/agent-runtime.ts`
- Test: `src/agents/runtime/__tests__/agent-runtime.test.ts`

- [ ] **Step 1: Write failing test**

Add a runtime test that enables LangSmith, executes a read tool through `AgentRuntimeImpl`, and verifies trace wrapping is invoked without changing tool output.

- [ ] **Step 2: Run test to verify failure**

Run: `npx tsx --test src/agents/runtime/__tests__/agent-runtime.test.ts`
Expected: FAIL because non-control tool execution is not wrapped with `traceTool`.

- [ ] **Step 3: Implement minimal code**

Import `traceTool` in `agent-runtime.ts` and wrap `options.toolExecutor(toolName, args)` with metadata from `options.metadata`, including `toolName`, `toolKind`, `agentId`, `taskId`, `novelId`, and `userId`.

- [ ] **Step 4: Run test to verify pass**

Run: `npx tsx --test src/agents/runtime/__tests__/agent-runtime.test.ts`
Expected: PASS.

### Task 3: Operation Graph Trace Coverage

**Files:**
- Modify: `src/agents/operations/operation-graph.ts`
- Test: `src/agents/operations/__tests__/operation-tracing.test.ts`

- [ ] **Step 1: Write failing test**

Add a lightweight unit test for a helper that builds operation trace metadata, verifying it includes task, novel, chapter, operation kind, operation label, stage, active agent, and artifact id.

- [ ] **Step 2: Run test to verify failure**

Run: `npx tsx --test src/agents/operations/__tests__/operation-tracing.test.ts`
Expected: FAIL because the metadata helper does not exist.

- [ ] **Step 3: Implement minimal code**

Add exported `createOperationTraceMetadata()` and `traceOperationStage()` helpers in `operation-graph.ts`, then wrap `prepareOperationContextNode`, `executeOperationNode`, `reviewArtifactNode`, `reviseArtifactNode`, `awaitUserDecisionNode`, and `suggestNextActionNode`.

- [ ] **Step 4: Run test to verify pass**

Run: `npx tsx --test src/agents/operations/__tests__/operation-tracing.test.ts`
Expected: PASS.

### Task 4: Studio Entry And Documentation

**Files:**
- Modify: `src/agents/graph/studio-app.ts`
- Modify: `docs/LANGGRAPH_STUDIO.md`
- Modify: `src/agents/AGENTS.md`
- Modify: `.env.example`

- [ ] **Step 1: Implement Studio initialization**

Call `initLangSmithForStudio()` before exporting `graph` so Studio runs do not rely on Next server initialization.

- [ ] **Step 2: Update docs**

Document required variables and expected trace layers: workflow, operation stage, agent, llm, tool.

- [ ] **Step 3: Run verification**

Run: `npm run typecheck`
Expected: PASS.
