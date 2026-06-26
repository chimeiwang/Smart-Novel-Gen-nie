# Agent 架构重构执行计划

> 状态：历史执行计划，已被当前 v7.2 架构取代。后续 AI 不应按本文逐条执行。
>
> 当前准则：Agent 正文是 Markdown；控制信息走 OpenAI tool_calls control tools；服务端 legacy JSON 解析已删除；`MemorySaver` 仅用于当前进程内 interrupt/resume，短期不做持久化 checkpointer。

本文档用于把 InkForge（墨铸）当前 Agent 系统从“可运行但难维护”的形态，重构为可恢复、可审计、可扩展的服务端 Agent 工作流。执行者可以按阶段逐条实现；每个阶段完成后必须运行验收命令，并更新相关文档。

## 0. 执行原则

- 所有后续对话、提交说明、注释和文档使用简体中文。
- 修改 Agent 流程后必须同步更新 `src/agents/AGENTS.md`。
- 修改写作流程、质量评审、商业性评估、设定同步、伏笔管理前，必须阅读 `docs/AGENT_NOVEL_WRITING_ROADMAP.md`。
- 不要让 LLM 直接写数据库。任何设定、大纲、伏笔、进度变更都必须先生成 proposal 或 updates，再经用户确认后由服务端事务执行。
- 有成熟方案时不要手写：优先使用 LangGraph、OpenAI tool_calls、Zod 入参校验、Prisma transaction。当前不规划持久化 checkpoint。
- 每完成一个阶段，至少运行 `npm run typecheck`。若改动涉及 UI 或 lint 规则，再运行 `npm run lint`。

## 1. 当前核心问题

### 1.1 高危安全问题

- `/api/writing/resume` 只接收 `taskId` 和 `userMessage`，没有校验任务是否属于当前用户。
- `getWritingTaskAction`、`acceptGeneratedContentAction` 等 task 操作也需要统一任务归属校验。
- LLM 工具层存在直接写库操作，会绕过用户确认链路。

### 1.2 架构问题

- `src/agents/graph/executor.ts` 同时承担图定义、SSE、resume、checkpoint、状态持久化、人工确认、fallback 补发，文件过大且难测试。
- `src/agents/lib/tools.ts` 用一个巨大 switch 管理所有工具，缺少 Zod 入参校验和工具权限分层。
- `src/agents/graph/response-parser.ts` 手写 JSON 正则解析，已经变成维护负担。
- 五个 Agent node 重复实现构建消息、工具调用、流式抽取、响应解析、状态事件。
- `selectedAgents` 从前端传到后端后没有真正参与后端路由或建图。
- 质量检查结果依赖前端收到 SSE 后再落库，断流会丢报告。

## 2. 目标架构

```text
API 鉴权层
  -> WritingTaskService / QualityCheckService
  -> LangGraph Workflow Runtime
  -> AgentDefinition + AgentRunner
  -> Zod Structured Output + LangChain Tools
  -> Prisma 事务写入
```

目标状态：

- API 层负责鉴权和参数校验，不直接拼工作流细节。
- Agent runtime 负责 run/resume/stream/checkpoint。
- Agent 以配置形式声明：ID、名称、系统提示词、工具、输出 schema、消息构建器。
- 工具以 LangChain structured tool + Zod schema 定义。
- 读工具可并行，写入 proposal 必须人工确认，真正写库只发生在服务端事务里。
- checkpoint 持久化，服务重启后仍可恢复 interrupt。
- 质量检查在服务端落库，不依赖前端在线。

## 3. Phase 1：安全边界止血

优先级：P0。  
目标：先堵住权限和直接写库风险，不等待完整重构。

### 3.1 新增任务鉴权服务

新增文件：

- `src/agents/lib/task-auth.ts` 或 `src/shared/lib/task-auth.ts`

实现：

```ts
export async function authorizeWritingTask(taskId: string, userId: string) {
  const task = await prisma.writingTask.findUnique({
    where: { id: taskId },
    include: { novel: { select: { userId: true } } },
  });
  if (!task) throw new Error("任务不存在");
  if (task.novel.userId !== userId) throw new Error("无权访问该任务");
  return task;
}
```

需要处理 `novel.userId` 可能为空的历史数据。建议规则：

- 当前登录用户创建的新数据必须有 `userId`。
- 历史空 `userId` 数据只允许在明确兼容策略下访问，不要默认放开。

涉及文件：

- `src/app/api/writing/resume/route.ts`
- `src/app/api/writing/session/route.ts`
- `src/app/actions.ts`

验收标准：

- 未登录访问 resume 返回 401。
- 使用不属于当前用户的 `taskId` 返回 403。
- 当前用户自己的 task 可以正常 resume。

### 3.2 禁用 LLM 直接写库工具

修改文件：

- `src/agents/graph/nodes/lore-advisor-node.ts`
- `src/agents/graph/nodes/plot-advisor-node.ts`
- `src/agents/graph/nodes/author-node.ts`
- `src/agents/graph/nodes/validator-node.ts`
- `src/agents/graph/nodes/editor-node.ts`
- `src/agents/lib/tools.ts`

具体改动：

- 移除所有 `withWriteTools(...)` 调用。
- 各 Agent 只暴露只读工具。
- `getWriteTools()` 暂时保留但不导出给 Agent，后续 Phase 3 改为 proposal 工具。
- `createToolExecutor()` 中直接 `prisma.create/update/delete/upsert` 的分支先不删除，但必须加保护：默认拒绝执行写工具，返回“写入工具已禁用，请生成 updates/proposal 等待用户确认”。

验收标准：

- `rg -n "withWriteTools\\(" src/agents/graph/nodes` 无结果。
- LLM 无法通过 tool call 直接修改角色、伏笔、大纲、剧情进度。
- 设定更新仍可通过 `updates -> user_input_required -> executeUpdates()` 完成。

### 3.3 统一 Agent ID

当前注册表使用中文 ID，但部分前端仍检查旧 ID。

修改文件：

- `src/features/writing/writing-conversation.tsx`
- `src/features/writing/agent-selector.tsx`
- `src/features/workspace/smart-writing-panel.tsx`
- `src/features/workspace/inspector-tabs.tsx`
- `src/agents/registry.ts`
- `src/agents/graph/state.ts`

具体改动：

- 统一使用 `"设定" | "剧情" | "写作" | "校验" | "编辑"`。
- 删除 `"writer"`、`"host"` 等旧 ID 判断。
- 若 `selectedAgents` 仍保留，后端必须使用它；否则移除 UI 选择，改为 `@Agent` 显式路由。

验收标准：

- `rg -n '"writer"|"host"' src/features src/agents` 不再出现旧架构判断。
- 前端选择状态与后端保存的 `selectedAgents` 一致。

## 4. Phase 2：结构化输出替换手写 JSON 解析

优先级：P1。  
目标：不再维护正则解析 JSON。

### 4.1 新增输出 Schema

当前状态：

- `src/agents/graph/schemas.ts` 仅保留内部意图分类 schema。
- 不再新增或恢复 `AgentOutputSchema`、`ValidatorOutputSchema`、`EditorOutputSchema`。
- Agent 正文不走 JSON schema；可见正文为 Markdown，控制信息走 tool_calls。

要求：只对内部结构化任务和 tool arguments 使用 Zod。

### 4.2 改造 LLM 调用

修改文件：

- `src/agents/lib/llm-wrapper.ts`
- `src/agents/graph/response-parser.ts`
- 所有 Agent node

实现方向：

- 优先使用 OpenAI SDK `zodResponseFormat` 或 LangChain `.withStructuredOutput(...)`。
- 为不兼容的 OpenAI-compatible provider 保留一个兼容层，但只允许：
  1. 正常 structured output。
  2. 失败后带“只返回合法 JSON”重试一次。
  3. 仍失败则返回错误，不再从半截文本里正则猜字段。

验收标准：

- `response-parser.ts` 不再承担核心解析逻辑，只保留临时兼容函数或删除。
- Agent 输出 JSON 外壳不会显示到聊天窗口。
- `npm run typecheck` 通过。

### 4.3 意图分类结构化

修改文件：

- `src/agents/graph/executor.ts` 或拆分后的 `router.ts`

具体改动：

- `classifyUserIntent()` 使用 `IntentClassificationSchema`。
- 删除 `result.content.match(/\{[\s\S]*\}/)` 这类正则解析。

验收标准：

- 无 `JSON.parse(jsonMatch[0])` 风格意图解析。
- 低置信度仍回退 `statusReport`。

## 5. Phase 3：工具层重构

优先级：P1。  
目标：把巨大 switch 改成 structured tools + registry。

### 5.1 新目录结构

新增：

```text
src/agents/tools/
  index.ts
  registry.ts
  permissions.ts
  read/
    novel-tools.ts
    character-tools.ts
    lore-tools.ts
    plot-tools.ts
    chapter-tools.ts
  proposals/
    update-proposal-tools.ts
```

### 5.2 使用 LangChain structured tools

成熟方案：

- 使用 `@langchain/core/tools` 的 `tool()`。
- 工具入参使用 Zod schema。
- 工具返回结构化 JSON 字符串或明确的 `ToolResult`。

示例：

```ts
export const getCharacterDetailTool = tool(
  async ({ characterName }, runtime) => {
    // 只读查询
  },
  {
    name: "get_character_detail",
    description: "获取角色完整设定",
    schema: z.object({
      characterName: z.string().min(1),
    }),
  }
);
```

### 5.3 工具权限模型

每个工具必须声明元信息：

```ts
type ToolPermission = {
  readOnly: boolean;
  concurrencySafe: boolean;
  requiresConfirmation: boolean;
  capability: "lore" | "plot" | "writing" | "validation" | "editorial";
};
```

执行规则：

- `readOnly && concurrencySafe` 可并行执行。
- `!readOnly` 一律不允许 LLM 直接执行写库，只能生成 proposal。
- 需要用户确认的 proposal 交给 `processResult` interrupt。

验收标准：

- `src/agents/lib/tools.ts` 缩减为兼容导出或删除。
- 无工具执行分支直接调用 `prisma.character.update` 等写库操作。
- 所有工具入参都有 Zod schema。

## 6. Phase 4：AgentDefinition + AgentRunner

优先级：P1。  
目标：消除五个 Agent node 的重复代码。

### 6.1 新增 runtime

新增：

```text
src/agents/runtime/
  agent-definition.ts
  agent-runner.ts
  stream-events.ts
  build-agent-messages.ts
```

核心类型：

```ts
export interface AgentDefinition<TOutput> {
  id: CoreAgentId;
  name: string;
  outputField: keyof WritingState;
  tools: AgentToolName[];
  outputSchema: z.ZodType<TOutput>;
  maxIterations?: number;
  buildMessages(state: WritingState): OpenAI.Chat.ChatCompletionMessageParam[];
}
```

`runAgent(definition, state)` 统一负责：

- `agent_start`
- status callback
- 工具调用
- structured output
- `agent_done`
- 返回 `{ [outputField]: output, activeAgent: id }`

### 6.2 迁移五个 Agent

迁移顺序：

1. `编辑`：输出结构较清晰，适合作为样板。
2. `校验`：迁移 conflict schema。
3. `设定`：迁移 updates schema。
4. `剧情`：迁移剧情建议。
5. `写作`：最后迁移，因为涉及正文自动保存。

验收标准：

- 五个 node 文件只保留 AgentDefinition 或薄包装。
- 新增 Agent 不需要修改大量重复流式逻辑。
- `npm run typecheck` 通过。

## 7. Phase 5：拆分 LangGraph 执行器

优先级：P2。  
目标：让 graph、runtime、SSE、persistence 分层。

### 7.1 拆分文件

从 `src/agents/graph/executor.ts` 拆出：

```text
src/agents/graph/
  graph-definition.ts
  router.ts
  process-result-node.ts
  checkpoint.ts
  workflow-runner.ts
  sse-adapter.ts
  task-state.ts
```

职责：

- `graph-definition.ts`：只定义节点、边、条件路由。
- `router.ts`：`@Agent` 快速路由和 LLM 意图分类。
- `process-result-node.ts`：桥接 Graph 状态；control tool 业务由 `control-event-processor.ts` 处理。
- `checkpoint.ts`：当前不需要。`MemorySaver` 只服务当前进程内 interrupt/resume。
- `workflow-runner.ts`：封装 run/resume。
- `sse-adapter.ts`：LangGraph event 到前端 SSE event。
- `task-state.ts`：读写 `WritingTask` 状态。

### 7.2 持久化 checkpoint

当前不作为执行项。

- `MemorySaver` 只用于当前进程内 LangGraph interrupt/resume。
- 当前产品短期不要求停机恢复或多实例恢复。
- 不要为了满足旧计划引入 SQLite/Postgres checkpointer。

## 8. Phase 6：质量检查服务端化

优先级：P2。  
目标：质量报告不依赖前端 SSE 落库。

### 8.1 新增质量检查服务

新增：

```text
src/agents/lib/quality-check-service.ts
```

职责：

- 标记检查项 `running`。
- 根据检查类型生成对应 Agent 请求。
- 调用 graph/runtime。
- Agent 完成后服务端直接写入：
  - `result`
  - `scoreHook`
  - `scoreTension`
  - `scorePayoff`
  - `scorePacing`
  - `scoreEndingHook`
  - `scoreReaderPromise`
  - `scoreOverall`
  - `qualityGate`
  - `rewriteBrief`

### 8.2 前端改为状态展示

修改：

- `src/features/writing/writing-conversation.tsx`
- `src/features/workspace/smart-writing-panel.tsx`

删除或弱化：

- 前端在 `agent_done` 中保存质量检查结果的逻辑。

验收标准：

- 断开前端页面，服务端检查完成后结果仍落库。
- 前端刷新后可看到质量报告。

## 9. Phase 7：写作闭环工作流

优先级：P3。  
目标：从聊天式协作升级为受控生产流水线。

建议流程：

```text
作者输入本章目标
  -> 剧情生成 beat plan
  -> 作者确认
  -> 作家生成正文
  -> 校验员一致性检查
  -> 编辑商业性评审
  -> 技法评审
  -> 不通过则生成 rewrite brief
  -> 作者采纳
  -> 同步设定/伏笔/进度
```

需要新增或扩展：

- 本章写作目标。
- 本章验收标准。
- Beat plan 数据结构。
- 技法评审 Agent 或编辑 Agent 的 craft 模式独立 schema。
- 质量门禁阈值。

验收标准：

- 每个阶段可查看状态。
- 每个阶段可跳过、重试、确认。
- 不通过时生成可执行返工 brief，而不是只给抽象评价。

## 10. 禁止事项

- 禁止让 LLM tool call 直接执行 Prisma 写库。
- 禁止恢复 `response-parser.ts` 或任何 Agent 正文 JSON 信封解析。
- 禁止在多个 Agent node 复制同一套流式事件和工具调用逻辑。
- 禁止新增 Agent 后只改代码不更新 `src/agents/AGENTS.md`。
- 禁止用前端 SSE 是否收到作为服务端质量报告落库依据。
- 禁止引入新的全局状态库解决 Agent runtime 问题。

## 11. 推荐执行顺序清单

1. 修复 `/api/writing/resume` 鉴权。
2. 禁用直接写库工具，移除 node 中的 `withWriteTools`。
3. 统一 Agent ID，修复 `selectedAgents` 行为。
4. 保持 Agent 正文 Markdown 直出，控制信息只走 tool_calls control tools。
5. 继续补真实端到端验证，重点是 `propose_updates`、`submit_quality_report`、`route_to_agent`。
6. 质量检查服务端落库链路继续完善异步状态展示。
7. 增加写作闭环工作流。
8. 更新 `src/agents/AGENTS.md` 和 `docs/AGENT_NOVEL_WRITING_ROADMAP.md`。

## 12. 每阶段通用验收命令

```bash
npm run typecheck
npm run lint
```

若涉及 Prisma schema：

```bash
npm run db:generate
```

若涉及 Agent 文档：

```bash
rg -n "AgentRuntime|tool_calls|control tool|质量检查" src/agents/AGENTS.md docs/AGENT_NOVEL_WRITING_ROADMAP.md
```

## 13. 最小可交付版本

如果时间有限，至少完成以下内容：

1. `/resume` 鉴权。
2. 禁用直接写库工具。
3. 统一 Agent ID。
4. 编辑 Agent 使用 Zod structured output。
5. `src/agents/AGENTS.md` 更新当前真实架构。

完成这五项后，系统仍未完全优雅，但已经明显降低安全风险和维护压力。
