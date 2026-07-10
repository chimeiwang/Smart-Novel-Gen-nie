> 状态：历史归档，不作为当前实现依据。当前事实以 `DOCS.md`、`AGENTS.md`、`src/agents/AGENTS.md`、代码和 schema 为准。

# LangGraph Native Agent Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strengthen the existing multi-Agent routing path so Agent handoff briefs, return requirements, and review/revision loops are carried by LangGraph state and control events instead of being implied by Markdown history.

**Architecture:** Implement this in three increments. Phase A fixes the current `nextAgent` chain by making handoff context explicit and visible to target Agents. Phase B moves routing decisions closer to a LangGraph-native command shape without replacing the runtime. Phase C introduces a reusable evaluator/reviser loop contract that can represent “revise then re-review until accepted” without adding one-off workflow state machines.

**Tech Stack:** Next.js 16, TypeScript strict mode, `@langchain/langgraph`, OpenAI-compatible tool calls, Node built-in `node:test`, `tsx`.

---

## File Structure

- Modify `src/agents/graph/state.ts`
  - Add structured handoff and loop state types to `WritingState`.
- Modify `src/agents/graph/graph-definition.ts`
  - Add state annotations, improve command alias parsing, and later consume routing decisions.
- Modify `src/agents/graph/control-event-processor.ts`
  - Preserve richer `pendingAgentCall`, return a routing decision object, and prepare for loop events.
- Modify `src/agents/graph/context-builder.ts`
  - Add active task context and include Agent-to-Agent call messages in history.
- Modify `src/agents/graph/nodes/*.ts`
  - Inject active task context into every Agent.
- Modify `src/shared/contracts/agent-control.ts`
  - Add general evaluation/revision control events in Phase C.
- Modify `src/agents/tools/registry.ts` or relevant control tool registration file
  - Register the new control tools from Phase C.
- Modify `src/agents/graph/__tests__/control-event-processor.test.ts`
  - Cover route handoff state, route decision, and loop events.
- Add `src/agents/graph/__tests__/context-builder.test.ts`
  - Cover active task context and call-message rendering.
- Add `src/agents/graph/__tests__/command-router.test.ts`
  - Cover routing decision mapping in a pure function before changing graph routing.
- Modify `src/agents/AGENTS.md`
  - Keep documentation aligned when Phase B/C land.

## Task 1: Phase A Test Coverage For Handoff Context

**Files:**
- Add: `src/agents/graph/__tests__/context-builder.test.ts`
- Modify: `src/agents/graph/__tests__/control-event-processor.test.ts`

- [ ] **Step 1: Write failing tests for active task context**

Create `src/agents/graph/__tests__/context-builder.test.ts`:

```ts
/**
 * Context builder tests
 *
 * 验证 Agent 间调用 brief 和用户根请求会进入目标 Agent 的当前任务上下文。
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { buildActiveTaskContext, buildConversationHistoryText } from "../context-builder";
import type { AgentMessage, WritingState } from "../state";

function createState(overrides: Partial<WritingState> = {}): WritingState {
  return {
    taskId: "task-1",
    userId: "user-1",
    novelId: "novel-1",
    chapterId: "chapter-1",
    targetWordCount: 2000,
    phase: "active",
    userMessage: "@编辑 先评审大纲，不行让剧情修改，改完你再审核，写入前让我确认",
    pendingUserResponse: false,
    conversationHistory: [],
    activeAgent: "剧情",
    loreAdvisorOutput: null,
    plotAdvisorOutput: null,
    writerOutput: null,
    validatorOutput: null,
    editorOutput: null,
    generatedContent: "",
    pendingUpdates: null,
    novelData: {
      novelId: "novel-1",
      chapterId: "chapter-1",
      novelName: "遗产猎人",
      chapterTitle: "第一章",
      chapterContent: "",
      outlineSummary: "",
      outlineNodes: [],
      plotProgress: { currentStage: "开篇" },
      storyBackground: "",
      worldSetting: "",
      writingBible: null,
      storyProgress: "",
      characters: [],
      items: [],
      locations: [],
      factions: [],
      glossaries: [],
      foreshadowings: [],
      references: [],
      styleProfile: "",
    },
    pendingAgentCall: null,
    errorMessage: null,
    streamCallbacks: {},
    controlEvents: undefined,
    ...overrides,
  };
}

describe("buildActiveTaskContext", () => {
  it("includes root user request and pending Agent call brief", () => {
    const state = createState({
      pendingAgentCall: {
        fromAgent: "编辑",
        toAgent: "剧情",
        reason: "前十章商业留存不足，需要重构节奏",
        specificQuestion: "请按编辑意见重构前十章大纲，完成后交回编辑复审。",
        contentToRewrite: "第一章到第十章大纲",
        timestamp: 123,
      },
    });

    const text = buildActiveTaskContext(state);

    assert.match(text, /当前任务上下文/);
    assert.match(text, /根用户请求/);
    assert.match(text, /改完你再审核/);
    assert.match(text, /本轮直接任务/);
    assert.match(text, /前十章商业留存不足/);
    assert.match(text, /交回编辑复审/);
    assert.match(text, /第一章到第十章大纲/);
  });

  it("returns an empty string when there is no useful task context", () => {
    const state = createState({ userMessage: "", pendingAgentCall: null });
    assert.equal(buildActiveTaskContext(state), "");
  });
});

describe("buildConversationHistoryText", () => {
  it("renders Agent call messages instead of dropping them", () => {
    const history: AgentMessage[] = [
      {
        id: "call-1",
        agentId: "编辑",
        agentName: "网文编辑",
        content: "剧情顾问：请重构前十章大纲。",
        timestamp: 1,
        isCallMessage: true,
        callTarget: "剧情",
      },
    ];

    const text = buildConversationHistoryText(history);

    assert.match(text, /网文编辑/);
    assert.match(text, /调用/);
    assert.match(text, /剧情/);
    assert.match(text, /请重构前十章大纲/);
  });
});
```

- [ ] **Step 2: Write failing test for richer pendingAgentCall**

Append to `src/agents/graph/__tests__/control-event-processor.test.ts` inside `describe("processControlEvents", ...)`:

```ts
  it("route_to_agent preserves a direct task brief for the target Agent", async () => {
    const event: AgentControlEvent = {
      type: "route_to_agent",
      toAgent: "剧情",
      reason: "编辑评审认为前十章只抑不扬",
      question: "请重构前十章，完成后必须交回编辑复审。",
      contentToRewrite: "前十章大纲",
    };

    const result = await processControlEvents(
      {
        events: [event],
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
          callChainDepth: 0,
        },
        activeAgent: "编辑",
        output: {
          agentId: "编辑",
          agentName: "网文编辑",
          content: "## 编辑意见\n\n需要返工。",
        },
        updatedHistory: [],
      },
      {
        emitEvent: () => {},
        now: () => 456,
      }
    );

    assert.equal(result.nextAgent, "剧情");
    assert.equal(result.pendingAgentCall?.fromAgent, "编辑");
    assert.equal(result.pendingAgentCall?.toAgent, "剧情");
    assert.equal(result.pendingAgentCall?.reason, "编辑评审认为前十章只抑不扬");
    assert.equal(result.pendingAgentCall?.specificQuestion, "请重构前十章，完成后必须交回编辑复审。");
    assert.equal(result.pendingAgentCall?.contentToRewrite, "前十章大纲");
    assert.equal(result.conversationHistory[0].isCallMessage, true);
  });
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
npx tsx --test src/agents/graph/__tests__/context-builder.test.ts src/agents/graph/__tests__/control-event-processor.test.ts
```

Expected:

- `context-builder.test.ts` fails because `buildActiveTaskContext` does not exist.
- If import errors stop execution first, that is the expected RED failure.

## Task 2: Phase A Implementation For Handoff Context

**Files:**
- Modify: `src/agents/graph/state.ts`
- Modify: `src/agents/graph/context-builder.ts`
- Modify: `src/agents/graph/control-event-processor.ts`
- Modify: `src/agents/graph/graph-definition.ts`
- Modify: `src/agents/graph/nodes/editor-node.ts`
- Modify: `src/agents/graph/nodes/plot-advisor-node.ts`
- Modify: `src/agents/graph/nodes/lore-advisor-node.ts`
- Modify: `src/agents/graph/nodes/author-node.ts`
- Modify: `src/agents/graph/nodes/validator-node.ts`

- [ ] **Step 1: Add explicit PendingAgentCall shape to state**

In `src/agents/graph/state.ts`, keep the existing `PendingAgentCall` interface and ensure `WritingState.pendingAgentCall` continues to use it. No new production code is required if the interface already includes:

```ts
export interface PendingAgentCall {
  fromAgent: CoreAgentId;
  toAgent: CoreAgentId;
  reason: string;
  specificQuestion?: string;
  contentToRewrite?: string;
  timestamp: number;
}
```

If `pendingAgentCall` is typed too loosely elsewhere, use this interface instead of `Record<string, unknown>`.

- [ ] **Step 2: Add `buildActiveTaskContext`**

In `src/agents/graph/context-builder.ts`, add:

```ts
export function buildActiveTaskContext(state: WritingState): string {
  const lines: string[] = [];
  const rootRequest = state.userMessage?.trim();
  const call = state.pendingAgentCall;

  if (!rootRequest && !call) return "";

  lines.push("## 当前任务上下文");
  lines.push("");

  if (rootRequest) {
    lines.push("### 根用户请求");
    lines.push(rootRequest);
    lines.push("");
  }

  if (call) {
    lines.push("### 本轮直接任务");
    lines.push(`- 调用来源：${call.fromAgent}`);
    lines.push(`- 目标 Agent：${call.toAgent}`);
    lines.push(`- 调用原因：${call.reason}`);
    if (call.specificQuestion) {
      lines.push(`- 具体要求：${call.specificQuestion}`);
    }
    if (call.contentToRewrite) {
      lines.push("");
      lines.push("### 待处理材料");
      lines.push(call.contentToRewrite);
    }
    lines.push("");
    lines.push("执行要求：优先完成“本轮直接任务”，同时不得违反“根用户请求”中的流程约束。");
  }

  return lines.join("\n");
}
```

- [ ] **Step 3: Render call messages in conversation history**

In `buildConversationHistoryText`, replace the Agent-output-only branch with logic that handles `isCallMessage` first:

```ts
    if (msg.userMessage) {
      lines.push("**用户**：" + msg.userMessage);
    } else if (msg.isCallMessage) {
      const target = msg.callTarget ? ` → ${msg.callTarget}` : "";
      lines.push("**" + msg.agentName + " 调用" + target + "**：" + msg.content);
    } else if (msg.agentOutput?.content) {
      lines.push("**" + msg.agentName + "**：" + msg.agentOutput.content);
    }
```

- [ ] **Step 4: Keep route_to_agent pendingAgentCall intact**

In `src/agents/graph/control-event-processor.ts`, ensure the `route_to_agent` return includes:

```ts
pendingAgentCall: {
  fromAgent: activeAgent,
  toAgent: targetAgent,
  reason: event.reason,
  specificQuestion: event.question,
  contentToRewrite: event.contentToRewrite,
  timestamp: now(),
}
```

This currently exists; keep it stable while changing types.

- [ ] **Step 5: Type `pendingAgentCall` annotation correctly**

In `src/agents/graph/graph-definition.ts`, change:

```ts
pendingAgentCall: Annotation<Record<string, unknown> | null>,
```

to:

```ts
pendingAgentCall: Annotation<WritingState["pendingAgentCall"]>,
```

- [ ] **Step 6: Add command aliases for common Agent names**

In `parseUserCommand`, replace the regex-only logic with alias normalization:

```ts
const AGENT_COMMAND_ALIASES: Record<string, CoreAgentId> = {
  "设定": "设定",
  "设定顾问": "设定",
  "剧情": "剧情",
  "剧情顾问": "剧情",
  "写作": "写作",
  "作家": "写作",
  "校验": "校验",
  "校验员": "校验",
  "编辑": "编辑",
  "网文编辑": "编辑",
  "编辑顾问": "编辑",
};

function parseUserCommand(message: string): { targetAgent: CoreAgentId | null } {
  const match = message.match(/@([\u4e00-\u9fa5A-Za-z0-9_-]+)/);
  if (!match) return { targetAgent: null };
  return { targetAgent: AGENT_COMMAND_ALIASES[match[1]] ?? null };
}
```

- [ ] **Step 7: Inject active task context into every Agent**

In each Agent node file, import `buildActiveTaskContext` from `../context-builder`.

After conversation history and before the final user message, add:

```ts
    const activeTaskContext = buildActiveTaskContext(state);
    if (activeTaskContext) {
      messages.push({ role: "system", content: activeTaskContext });
    }
```

Apply to:

- `src/agents/graph/nodes/editor-node.ts`
- `src/agents/graph/nodes/plot-advisor-node.ts`
- `src/agents/graph/nodes/lore-advisor-node.ts`
- `src/agents/graph/nodes/author-node.ts`
- `src/agents/graph/nodes/validator-node.ts`

- [ ] **Step 8: Run Phase A tests and verify pass**

Run:

```bash
npx tsx --test src/agents/graph/__tests__/context-builder.test.ts src/agents/graph/__tests__/control-event-processor.test.ts
```

Expected: PASS.

- [ ] **Step 9: Commit Phase A**

Run:

```bash
git add src/agents/graph/state.ts src/agents/graph/context-builder.ts src/agents/graph/control-event-processor.ts src/agents/graph/graph-definition.ts src/agents/graph/nodes/editor-node.ts src/agents/graph/nodes/plot-advisor-node.ts src/agents/graph/nodes/lore-advisor-node.ts src/agents/graph/nodes/author-node.ts src/agents/graph/nodes/validator-node.ts src/agents/graph/__tests__/context-builder.test.ts src/agents/graph/__tests__/control-event-processor.test.ts
git commit -m "feat: preserve agent handoff context"
```

Expected: commit only Phase A files. Do not stage unrelated working tree changes.

## Task 3: Phase B Tests For LangGraph-Native Routing Decisions

**Files:**
- Add: `src/agents/graph/__tests__/command-router.test.ts`
- Add: `src/agents/graph/command-router.ts`

- [ ] **Step 1: Write failing tests for routing decision helper**

Create `src/agents/graph/__tests__/command-router.test.ts`:

```ts
/**
 * Command router tests
 *
 * 验证 control event 处理结果可以被转换为单一 Graph 路由决策。
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { mapAgentToNode, toGraphRoute } from "../command-router";

describe("mapAgentToNode", () => {
  it("maps CoreAgentId to graph node names", () => {
    assert.equal(mapAgentToNode("设定"), "loreAdvisor");
    assert.equal(mapAgentToNode("剧情"), "plotAdvisor");
    assert.equal(mapAgentToNode("写作"), "author");
    assert.equal(mapAgentToNode("校验"), "validator");
    assert.equal(mapAgentToNode("编辑"), "editor");
  });
});

describe("toGraphRoute", () => {
  it("routes to target node when nextAgent exists", () => {
    assert.equal(toGraphRoute({ nextAgent: "编辑" }), "editor");
  });

  it("routes to end when there is no nextAgent", () => {
    assert.equal(toGraphRoute({ nextAgent: null }), "end");
  });
});
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
npx tsx --test src/agents/graph/__tests__/command-router.test.ts
```

Expected: FAIL because `command-router.ts` does not exist.

## Task 4: Phase B Implementation For Routing Helper

**Files:**
- Create: `src/agents/graph/command-router.ts`
- Modify: `src/agents/graph/graph-definition.ts`

- [ ] **Step 1: Add routing helper**

Create `src/agents/graph/command-router.ts`:

```ts
import type { CoreAgentId } from "./state";

export type GraphRoute =
  | "loreAdvisor"
  | "plotAdvisor"
  | "author"
  | "validator"
  | "editor"
  | "statusReport"
  | "end";

const AGENT_NODE_MAP: Record<CoreAgentId, GraphRoute> = {
  "设定": "loreAdvisor",
  "剧情": "plotAdvisor",
  "写作": "author",
  "校验": "validator",
  "编辑": "editor",
};

export function mapAgentToNode(agentId: CoreAgentId | null | undefined): GraphRoute {
  if (!agentId) return "end";
  return AGENT_NODE_MAP[agentId] ?? "end";
}

export function toGraphRoute(result: { nextAgent?: CoreAgentId | null }): GraphRoute {
  return mapAgentToNode(result.nextAgent);
}
```

- [ ] **Step 2: Use routing helper in graph-definition**

In `src/agents/graph/graph-definition.ts`, import:

```ts
import { mapAgentToNode } from "./command-router";
```

Replace duplicated maps in `routeAfterInit` and `routeAfterProcess`:

```ts
function routeAfterInit(state: GraphState): string {
  return state.activeAgent ? mapAgentToNode(state.activeAgent) : "statusReport";
}

function routeAfterProcess(state: GraphState): string {
  const next = (state as Record<string, unknown>).nextAgent as CoreAgentId | null;
  return next ? mapAgentToNode(next) : "end";
}
```

- [ ] **Step 3: Run Phase B tests**

Run:

```bash
npx tsx --test src/agents/graph/__tests__/command-router.test.ts src/agents/graph/__tests__/control-event-processor.test.ts
```

Expected: PASS.

- [ ] **Step 4: Commit Phase B**

Run:

```bash
git add src/agents/graph/command-router.ts src/agents/graph/graph-definition.ts src/agents/graph/__tests__/command-router.test.ts
git commit -m "refactor: centralize graph routing decisions"
```

Expected: commit only Phase B files.

## Task 5: Phase C Tests For Generic Evaluation Loop Events

**Files:**
- Modify: `src/shared/contracts/agent-control.ts`
- Modify: `src/agents/runtime/__tests__/agent-runtime.test.ts`
- Modify: `src/agents/graph/__tests__/control-event-processor.test.ts`

- [ ] **Step 1: Write failing parser tests for evaluation loop control tools**

Append to `src/agents/runtime/__tests__/agent-runtime.test.ts` under `describe("parseControlEventArgs", ...)`:

```ts
  it("解析 submit_evaluation → EvaluationEvent", () => {
    const event = parseControlEventArgs("submit_evaluation", {
      artifactKey: "outline-revision-1",
      verdict: "revise",
      summary: "前3章仍缺少小赢节点",
      requiredChanges: "第2章需要补一个明确获得线索的小胜利",
    });
    assert.ok(event);
    assert.equal(event!.type, "submit_evaluation");
    if (event!.type === "submit_evaluation") {
      assert.equal(event.verdict, "revise");
      assert.equal(event.artifactKey, "outline-revision-1");
    }
  });

  it("解析 request_revision → RevisionRequestEvent", () => {
    const event = parseControlEventArgs("request_revision", {
      toAgent: "剧情",
      artifactKey: "outline-revision-1",
      reason: "编辑复审未通过",
      instructions: "保留主线，但提高第1-3章爽点密度。",
    });
    assert.ok(event);
    assert.equal(event!.type, "request_revision");
    if (event!.type === "request_revision") {
      assert.equal(event.toAgent, "剧情");
      assert.equal(event.instructions, "保留主线，但提高第1-3章爽点密度。");
    }
  });
```

- [ ] **Step 2: Write failing processor test for request_revision routing**

Append to `src/agents/graph/__tests__/control-event-processor.test.ts`:

```ts
  it("request_revision routes back to requested Agent with revision brief", async () => {
    const event: AgentControlEvent = {
      type: "request_revision",
      toAgent: "剧情",
      artifactKey: "outline-revision-1",
      reason: "编辑复审未通过",
      instructions: "第2章需要补一个明确小赢节点。",
    };

    const result = await processControlEvents(
      {
        events: [event],
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
          callChainDepth: 1,
        },
        activeAgent: "编辑",
        output: {
          agentId: "编辑",
          agentName: "网文编辑",
          content: "## 复审\n\n仍需修改。",
        },
        updatedHistory: [],
      },
      {
        emitEvent: () => {},
        now: () => 789,
      }
    );

    assert.equal(result.nextAgent, "剧情");
    assert.equal(result.pendingAgentCall?.fromAgent, "编辑");
    assert.equal(result.pendingAgentCall?.toAgent, "剧情");
    assert.match(result.pendingAgentCall?.specificQuestion ?? "", /小赢节点/);
    assert.equal(result.callChainDepth, 2);
  });
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
npx tsx --test src/agents/runtime/__tests__/agent-runtime.test.ts src/agents/graph/__tests__/control-event-processor.test.ts
```

Expected:

- FAIL because `submit_evaluation` and `request_revision` are not known control event types.

## Task 6: Phase C Implementation For Generic Evaluation Loop Events

**Files:**
- Modify: `src/shared/contracts/agent-control.ts`
- Modify: control tool registration file under `src/agents/tools/`
- Modify: `src/agents/graph/control-event-processor.ts`
- Modify: relevant Agent prompts in `src/agents/graph/nodes/editor-node.ts` and `src/agents/graph/nodes/validator-node.ts`
- Modify: `src/agents/AGENTS.md`

- [ ] **Step 1: Add control event schemas**

In `src/shared/contracts/agent-control.ts`, add Zod schemas and union members for:

```ts
submit_evaluation({
  artifactKey: string;
  verdict: "pass" | "revise" | "block";
  summary: string;
  requiredChanges?: string;
})

request_revision({
  toAgent: CoreAgentId;
  artifactKey?: string;
  reason: string;
  instructions: string;
})
```

Ensure `parseControlEventArgs("submit_evaluation", args)` and `parseControlEventArgs("request_revision", args)` return typed events.

- [ ] **Step 2: Register control tools**

In the control tool registration file under `src/agents/tools/`, register both tools with:

```ts
toolKind: "control"
```

and capabilities that are available to evaluator Agents:

- `submit_evaluation`: at least editor and validator.
- `request_revision`: editor and validator.

Use the same Zod schemas from `agent-control.ts` or schema-compatible definitions.

- [ ] **Step 3: Process request_revision**

In `src/agents/graph/control-event-processor.ts`, add a case for `request_revision` similar to `route_to_agent`:

```ts
case "request_revision": {
  const targetAgent = event.toAgent as CoreAgentId;
  if (!isValidAgentId(targetAgent) || state.callChainDepth >= maxCallChainDepth) {
    logger.warn("CONTROL_EVENTS", "request_revision 目标无效或调用链过深", {
      targetAgent,
      depth: state.callChainDepth,
    });
    break;
  }

  const nextDepth = state.callChainDepth + 1;
  const brief = `${event.reason}\n${event.instructions}`;
  const callMessage: AgentMessage = {
    id: `revision_${now()}`,
    agentId: activeAgent,
    agentName: AGENT_NAMES[activeAgent],
    content: `${AGENT_NAMES[targetAgent]}：${brief}`,
    timestamp: now(),
    isCallMessage: true,
    callTarget: targetAgent,
  };

  return {
    conversationHistory: [...updatedHistory, callMessage],
    nextAgent: targetAgent,
    callChainDepth: nextDepth,
    controlEvents: undefined,
    pendingAgentCall: {
      fromAgent: activeAgent,
      toAgent: targetAgent,
      reason: event.reason,
      specificQuestion: event.instructions,
      timestamp: now(),
    },
  };
}
```

- [ ] **Step 4: Process submit_evaluation**

In `processControlEvents`, add a case that emits an event but does not route by itself:

```ts
case "submit_evaluation": {
  emitEvent("workflow_evaluation_submitted", {
    agentId: activeAgent,
    artifactKey: event.artifactKey,
    verdict: event.verdict,
    summary: event.summary,
    requiredChanges: event.requiredChanges,
  });
  logger.info("CONTROL_EVENTS", "工作流评估已提交", {
    agentId: activeAgent,
    artifactKey: event.artifactKey,
    verdict: event.verdict,
  });
  break;
}
```

This is intentionally small. The actual loop route is `request_revision`; pass/block end normally unless future Graph state needs stronger behavior.

- [ ] **Step 5: Update evaluator Agent prompts**

In `src/agents/graph/nodes/editor-node.ts` and `src/agents/graph/nodes/validator-node.ts`, add concise instructions:

```ts
"\n- 当你在复审其他 Agent 产物时，必须用 submit_evaluation 提交 pass/revise/block 结论。"
+"\n- 如果需要返工，使用 request_revision 指定目标 Agent 和明确修改指令；不要只在 Markdown 中说“请修改”。"
```

- [ ] **Step 6: Update AGENTS.md**

In `src/agents/AGENTS.md`, update the control tool table to include:

```markdown
| 工作流评估 | — | `submit_evaluation(artifactKey, verdict, summary, requiredChanges?)` |
| 请求返工 | — | `request_revision(toAgent, reason, instructions, artifactKey?)` |
```

Add one sentence that generic evaluator/reviser loops use these tools rather than bespoke workflow state machines.

- [ ] **Step 7: Run Phase C tests**

Run:

```bash
npx tsx --test src/agents/runtime/__tests__/agent-runtime.test.ts src/agents/graph/__tests__/control-event-processor.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit Phase C**

Run:

```bash
git add src/shared/contracts/agent-control.ts src/agents/tools src/agents/graph/control-event-processor.ts src/agents/graph/nodes/editor-node.ts src/agents/graph/nodes/validator-node.ts src/agents/AGENTS.md src/agents/runtime/__tests__/agent-runtime.test.ts src/agents/graph/__tests__/control-event-processor.test.ts
git commit -m "feat: add generic agent revision loop controls"
```

Expected: commit only Phase C files.

## Task 7: Full Verification

**Files:**
- No new files unless verification exposes a defect.

- [ ] **Step 1: Run focused Agent tests**

Run:

```bash
npx tsx --test src/agents/graph/__tests__/context-builder.test.ts src/agents/graph/__tests__/command-router.test.ts src/agents/graph/__tests__/control-event-processor.test.ts src/agents/runtime/__tests__/agent-runtime.test.ts src/agents/runtime/__tests__/agent-runtime-visible-content.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 3: Run lint**

Run:

```bash
npm run lint
```

Expected: PASS or only pre-existing warnings unrelated to touched files. If lint fails on touched files, fix before finalizing.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git diff --stat
git diff -- src/agents/graph src/agents/runtime src/shared/contracts src/agents/tools src/agents/AGENTS.md docs/superpowers/plans/2026-06-14-langgraph-native-agent-routing.md
```

Expected:

- Changes are limited to the planned files and tests.
- No unrelated UI files are staged or modified by this work.

- [ ] **Step 5: Final commit for plan document if not already committed**

If the plan file has not been committed with Task 1, run:

```bash
git add docs/superpowers/plans/2026-06-14-langgraph-native-agent-routing.md
git commit -m "docs: plan langgraph native agent routing"
```

Expected: plan document committed.

## Self-Review

- Spec coverage:
  - Phase A covers reliable brief and constraint propagation.
  - Phase B covers the first migration away from duplicated hand-written route maps toward a Graph routing helper and later `Command` compatibility.
  - Phase C covers the general evaluator/reviser loop primitive without building a bespoke workflow DSL.
- Placeholder scan:
  - No `TBD`, `TODO`, or undefined “do appropriate thing” steps are present.
- Type consistency:
  - `PendingAgentCall`, `AgentControlEvent`, `CoreAgentId`, and `WritingState` names match existing project types.
  - New control event names are consistently `submit_evaluation` and `request_revision`.
