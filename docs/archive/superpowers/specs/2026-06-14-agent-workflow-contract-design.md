> 状态：历史归档，不作为当前实现依据。当前事实以 `DOCS.md`、`AGENTS.md`、`src/agents/AGENTS.md`、代码和 schema 为准。

# Agent 工作流约束契约设计

## 背景

当前 Agent 编排已经从旧 JSON 信封协议迁移到 Markdown + tool_calls/control tools。这个方向是对的，但多 Agent 协作仍主要依赖对话历史和 Agent 自我遵守提示词。

这会导致一个实际问题：用户输入中的流程约束在多轮转交后被稀释。例如用户要求：

1. 网文编辑先评估大纲商业化。
2. 如果不符合，让设定顾问或相关 Agent 修改。
3. 修改后回到网文编辑复审。
4. 复审问题不大后，再提交给用户审核。
5. 用户确认前不得写入。

现有系统能让 Agent 在回复中“承诺”这个流程，但 Graph 没有状态字段或路由规则强制执行它。因此后续 Agent 可能只看见历史摘要和原始用户输入，而不是一个不可忽略的当前任务契约。

## 目标

本设计目标是把用户的流程约束从“提示词里的自然语言”提升为“Graph 层可执行状态”。

成功标准：

- 用户的原始流程要求被结构化保存，并注入后续每个 Agent。
- `route_to_agent` 的 brief 成为目标 Agent 的当前任务，而不是依赖对话历史间接传递。
- 涉及落库的修改支持“草案更新 -> 编辑复审 -> 用户确认 -> 执行写入”的硬流程。
- 复审通过、复审驳回、用户确认、用户拒绝都由 control event 驱动，不靠 Markdown 文本猜测。
- 不破坏现有普通单 Agent 问答、普通 `propose_updates` 用户确认流程。

## 非目标

- 不在第一版实现通用工作流 DSL。
- 不把所有 Agent 调度改成固定流水线。
- 不让设定顾问越权修改大纲；大纲结构仍归剧情顾问，设定类字段仍归设定顾问。
- 不从 assistant 正文中解析“已通过”“请修改”等自然语言作为流程信号。

## 方案概览

新增三层控制面能力：

1. `WorkflowContract`：保存用户本轮不可忽略的目标、约束、审批策略和阶段要求。
2. `ActiveTaskContext`：统一把 `workflowContract` 和 `pendingAgentCall` 注入目标 Agent prompt。
3. `Draft Updates Review`：新增草案更新 control flow，先提交草案给编辑复审，复审通过后才触发用户确认。

推荐数据流：

```text
用户请求
  -> initSession 解析 workflowContract
  -> 编辑评审
  -> route_to_agent 携带明确 brief
  -> 剧情/设定 Agent 生成 draft updates
  -> Graph 强制回到编辑复审
  -> 编辑 approve/reject draft
  -> approve 后触发 user_input_required
  -> 用户确认后 executeUpdates
```

## 1. WorkflowContract

### 文件位置

新增：

```text
src/agents/graph/workflow-contract.ts
```

职责：

- 定义工作流契约类型。
- 从用户输入和路由上下文中生成初始契约。
- 提供 prompt 注入格式化函数。
- 提供少量规则判断函数，供 Graph 路由使用。

### 类型设计

```ts
export type WorkflowStepType =
  | "review"
  | "draft_changes"
  | "editor_review"
  | "user_approval"
  | "persist";

export interface WorkflowStep {
  id: string;
  type: WorkflowStepType;
  ownerAgent?: CoreAgentId;
  description: string;
  required: boolean;
  status: "pending" | "active" | "completed" | "blocked";
}

export interface WorkflowContract {
  id: string;
  originalUserRequest: string;
  goal: string;
  constraints: string[];
  requiredSequence: WorkflowStep[];
  approvalPolicy: {
    requireUserBeforePersist: boolean;
    requireEditorReviewBeforeUserApproval: boolean;
  };
  createdAt: number;
}
```

### State 落点

修改：

```text
src/agents/graph/state.ts
```

给 `WritingState` 增加：

```ts
workflowContract?: WorkflowContract | null;
currentWorkflowStepId?: string | null;
draftUpdates?: AgentUpdates | null;
draftUpdatesSourceAgent?: CoreAgentId | null;
```

同时在 `WritingStateAnnotation` 增加同名字段：

```text
src/agents/graph/graph-definition.ts
```

### 生成策略

第一版不需要复杂 LLM 分类，先用规则覆盖高价值场景：

- 包含“你再审核”“再复审”“复审” -> `requireEditorReviewBeforeUserApproval = true`
- 包含“写入前让我审核”“保存前让我确认”“提交前让我看” -> `requireUserBeforePersist = true`
- 包含“让 X 根据你的意见修改” -> 添加 `draft_changes` 步骤
- 包含“如果不符合/不商业化/问题大就修改” -> 添加 `review -> draft_changes` 条件流程

如果没有命中这些规则，`workflowContract` 可以为空，保持现有行为。

## 2. ActiveTaskContext

### 问题

现在 `route_to_agent` 会写入一条 call message，但常规历史构建只输出用户消息和 Agent 输出。目标 Agent 容易看不到明确 brief，或者仍把原始 `userMessage` 当作当前任务。

### 文件位置

修改：

```text
src/agents/graph/context-builder.ts
```

新增：

```ts
export function buildActiveTaskContext(state: WritingState): string
```

职责：

- 输出当前用户原始目标。
- 输出 workflow contract 中的强约束。
- 如果存在 `pendingAgentCall`，将其格式化为“本轮你必须执行的任务”。
- 明确提示：原始用户消息是上层约束，`pendingAgentCall` 是本轮直接任务。

### 注入位置

修改各 Agent 的 `buildMessages`：

```text
src/agents/graph/nodes/editor-node.ts
src/agents/graph/nodes/plot-advisor-node.ts
src/agents/graph/nodes/lore-advisor-node.ts
src/agents/graph/nodes/author-node.ts
src/agents/graph/nodes/validator-node.ts
```

在对话历史之后、最终 user message 之前注入：

```ts
const activeTaskContext = buildActiveTaskContext(state);
if (activeTaskContext) {
  messages.push({ role: "system", content: activeTaskContext });
}
```

### route_to_agent 状态落点

修改：

```text
src/agents/graph/control-event-processor.ts
```

处理 `route_to_agent` 时，`pendingAgentCall` 必须保留：

- `fromAgent`
- `toAgent`
- `reason`
- `specificQuestion`
- `contentToRewrite`
- 当前 `workflowContract` 的关键摘要或引用

目标 Agent 不应该靠历史猜任务。

## 3. Draft Updates Review

### 问题

现有 `propose_updates` 的语义是“把变更提交给用户确认保存”。但用户要求“修改后先由网文编辑复审，问题不大后再给用户审核”。这需要一个比 `propose_updates` 更早的草案阶段。

### 新增 Control Tools

修改：

```text
src/shared/contracts/agent-control.ts
src/agents/tools/registry.ts
```

新增三个 control event：

```ts
submit_draft_updates({
  summary: string;
  updates: AgentUpdates;
  requestedReviewAgent?: CoreAgentId;
})

approve_draft_updates({
  summary: string;
  notes?: string;
})

reject_draft_updates({
  summary: string;
  requiredChanges: string;
  returnToAgent?: CoreAgentId;
})
```

### 处理逻辑

修改：

```text
src/agents/graph/control-event-processor.ts
```

`submit_draft_updates`：

1. 按当前 Agent 权限过滤 updates。
2. 存入 `draftUpdates`。
3. 设置 `currentWorkflowStepId` 为编辑复审步骤。
4. `nextAgent = "编辑"`。

`approve_draft_updates`：

1. 仅允许编辑 Agent 在存在 `draftUpdates` 时调用。
2. 触发 `user_input_required`，展示 diff。
3. 用户确认后执行 `executeUpdates`。
4. 用户取消后清空 `draftUpdates`。

`reject_draft_updates`：

1. 设置 `nextAgent` 为 `returnToAgent` 或草案来源 Agent。
2. 把 `requiredChanges` 写入 `pendingAgentCall.specificQuestion`。
3. 保留 `draftUpdates` 或清空，第一版建议清空，避免修改基于旧草案叠加。

### Graph 路由

修改：

```text
src/agents/graph/graph-definition.ts
```

在 `routeAfterProcess` 中加入硬规则：

```ts
if (
  state.workflowContract?.approvalPolicy.requireEditorReviewBeforeUserApproval &&
  state.draftUpdates &&
  state.currentWorkflowStepId === "editor_review"
) {
  return "editor";
}
```

如果编辑拒绝，Graph 路由回草案来源 Agent。

## Agent Prompt 调整

Prompt 只承担“告知能力和工具用法”，不承担流程保证。

需要补充：

- 剧情顾问、设定顾问：当存在 `workflowContract.approvalPolicy.requireEditorReviewBeforeUserApproval` 时，提交草案用 `submit_draft_updates`，不要直接 `propose_updates`。
- 网文编辑：复审草案时必须使用 `approve_draft_updates` 或 `reject_draft_updates`，不要只用 Markdown 表态。

这部分写在各 Agent system prompt 中，但流程仍由 Graph 校验。

## 权限边界

保持现有 section 过滤：

- 设定 Agent 允许：角色、地点、物品、势力、术语、角色经历、世界设定、故事背景。
- 剧情 Agent 允许：大纲、伏笔。

如果用户说“让设定顾问改大纲”，系统应保留用户意图，但实际大纲更新必须由剧情顾问提交。设定顾问可以补齐角色动机、物品、世界规则等配套设定。

## 错误处理

- 草案 updates 为空：不进入编辑复审，返回普通回复。
- 草案被过滤后为空：发出可见说明，不进入用户确认。
- 编辑调用 `approve_draft_updates` 但没有 `draftUpdates`：返回工具校验错误。
- 非编辑 Agent 调用 `approve_draft_updates`：返回权限错误。
- 用户取消保存：清空 `draftUpdates`，保留对话历史。
- 调用链超过上限：停止路由，输出当前状态和原因。

## 测试计划

新增或扩展测试：

```text
src/agents/graph/__tests__/control-event-processor.test.ts
src/agents/runtime/__tests__/agent-runtime.test.ts
```

覆盖：

- 规则生成 `workflowContract`。
- `route_to_agent` 后 `pendingAgentCall` 被注入当前任务。
- `submit_draft_updates` 路由到编辑。
- 编辑 `approve_draft_updates` 才触发 `user_input_required`。
- 编辑 `reject_draft_updates` 路由回来源 Agent。
- `propose_updates` 在无复审契约时保持原行为。
- 设定 Agent 提交大纲 section 会被过滤。

## 实施顺序

1. 增加 `WorkflowContract` 类型、解析和 state 字段。
2. 增加 `buildActiveTaskContext` 并注入所有 Agent。
3. 扩展 control event contract 和工具注册。
4. 在 `control-event-processor` 实现 draft review 状态转移。
5. 在 `routeAfterProcess` 增加强制复审路由。
6. 更新 Agent prompt。
7. 更新 `src/agents/AGENTS.md`，说明新增工作流约束和草案复审流程。
8. 补测试，运行 `npm run typecheck` 和相关测试。

## 设计结论

本方案把用户约束从“Agent 记忆”变成“Graph 状态”。Agent 可以继续灵活判断内容质量，但是否需要复审、是否能提交用户确认、是否允许写入，必须由 control event 和 Graph 路由决定。

这能直接解决当前问题：多轮 Agent 协作时，后续 Agent 不再靠长历史猜用户的真实要求，而是收到明确的当前任务和不可忽略的工作流契约。
