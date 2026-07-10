> 状态：历史归档，不作为当前实现依据。当前事实以 `DOCS.md`、`AGENTS.md`、`src/agents/AGENTS.md`、代码和 schema 为准。

# Agent Runtime 协议返工蓝图

> 本文是对 `docs/AGENT_RUNTIME_PROTOCOL_REFACTOR_BLUEPRINT.md` 执行结果的返工要求。
>
> **状态：历史返工蓝图，当前 v7.2 已落地（2026-06-10）**
>
> 当前代码已修复 `visibleContent` 聚合、`propose_updates` payload、前端新协议 JSON 解析隔离，并进一步删除服务端 legacy JSON 主路径。
> 本文保留为历史验收背景，不再作为下一步执行清单。
>
> 只有真实测试覆盖 Markdown + tool_calls 同轮输出、单轮长 Markdown 不重复、`propose_updates` 确认保存后，才能重新标记完成。

## 0. 严厉结论

当前实现方向没有错，但完成度被严重高估。

它已经有了这些正确外壳：

- `AgentDefinition.outputMode = "markdown_with_control_tools"`
- `AgentRuntimeImpl`
- `AgentTurnResult`
- `toolKind: "control"`
- `controlEvents`
- `route_to_agent`、`submit_quality_report`、`propose_updates` 等 control tools

但是，这些外壳并不等于协议闭环。

现在的问题不是“还差几个小优化”，而是：

1. 用户看见的 Markdown 正文，不一定进入 `AgentTurnResult.visibleContent`。
2. `propose_updates` 只传了“有更新”的摘要，没有传真正可执行的 `updates` 数据。
3. 旧 JSON `updates` 提示仍然混在新协议提示词里。
4. 前端仍在主链路解析 assistant prose。
5. `src/agents/AGENTS.md` 仍在教后续开发者使用旧 JSON 协议。

如果继续在这个状态上标记“完成”，后续 AI 会在错误地基上继续堆功能，最后得到的是一个更复杂、更难删除 legacy 的半迁移系统。

## 1. 返工原则

以下原则不允许被折中。

### 1.1 输出就是输出

Assistant 的 `content` 只能是用户可见 Markdown。

禁止再要求模型输出：

```json
{
  "content": "...",
  "updates": {},
  "wantsToCall": "..."
}
```

禁止新增任何替代 JSON 信封的文本协议，例如：

- `---META---`
- `<!-- control: ... -->`
- `【系统字段】`
- Markdown 表格承载控制字段
- 正文末尾附一段机器可解析 JSON

### 1.2 控制信息只能走 tool_calls

以下信息必须来自 OpenAI-compatible `tool_calls` arguments，而不是从 assistant content 解析：

- Agent 路由：`route_to_agent`
- 质量评分：`submit_quality_report`
- 校验结果：`submit_validation_report`
- Beat Plan：`submit_beat_plan`
- 设定更新：`propose_updates`

### 1.3 Runtime 必须成为真正边界

`AgentRuntime.runTurn()` 的结果必须满足：

```ts
interface AgentTurnResult {
  visibleContent: string;       // 所有用户可见 Markdown，完整、稳定、可落库
  controlEvents: AgentControlEvent[]; // 只来自 control tool_calls
  toolCalls: RuntimeToolCallRecord[];
  toolResults: RuntimeToolResultRecord[];
  usage?: TokenUsage;
  finishReason?: string | null;
}
```

`visibleContent` 和 `controlEvents` 必须来源分离。

前端、Graph、质量检查服务不得再从 `visibleContent` 里解析业务控制字段。

## 2. 当前失败点

### P0-1：`visibleContent` 没有聚合 tool-call 轮次中的 Markdown

问题位置：

- `src/agents/runtime/agent-runtime.ts`
- `src/agents/lib/llm-wrapper.ts`
- `src/agents/runtime/agent-runner.ts`
- `src/agents/graph/graph-definition.ts`

当前链路大致是：

```text
AgentRuntimeImpl.runTurn()
  -> callLLMWithTools()
       第 N 轮 assistant 输出 Markdown + tool_calls
       onChunk 把 Markdown 流给前端
       messages.push({ role: "assistant", content: fullTextContent, tool_calls })
       执行 tools
       进入下一轮
       最后一轮没有 tool_calls 时 return { content: fullTextContent }
  -> visibleContent = result.content
```

这意味着：

- 用户可能已经在前端看到了完整报告；
- 但服务端最终 `visibleContent` 只拿到最后一轮短回复；
- `conversationHistory` 保存的可能不是完整报告；
- `ChapterQualityCheck.result` 落库的可能不是完整评审；
- 作家自动入库可能拿到被工具确认污染后的内容。

这是协议重构的核心失败点，必须优先修。

#### 必须完成

底层 tool-call loop 必须把所有 assistant 可见正文聚合成一个稳定的 `visibleContent`。

可接受方案二选一：

方案 A：改造 `callLLMWithTools()` 返回聚合内容。

```ts
let visibleContentParts: string[] = [];

// 每一轮 stream 完成后
if (fullTextContent.trim()) {
  visibleContentParts.push(fullTextContent);
}

// 最终返回
return {
  content: visibleContentParts.join("\n\n").trim(),
  ...
};
```

方案 B：新增 runtime 专用 tool-call loop，不再复用旧 `callLLMWithTools()` 的返回语义。

如果选择方案 B，必须保证新 loop 仍支持：

- streaming chunks
- OpenAI `tool_calls` accumulation
- role `tool` result append
- usage 记录
- maxIterations
- tool execution error handling

#### 不允许

- 不允许只比较 `event.content` 和前端 stream 长度来“凑”最终内容。
- 不允许让前端负责保存完整报告。
- 不允许把工具确认文本拼进正文。
- 不允许依赖模型“最后再复述一次完整报告”。

#### 验收测试

必须新增单测，模拟以下响应序列：

1. 第一轮 assistant 输出 `## 评审报告\n...长篇内容...`，同时调用 `submit_quality_report`。
2. runtime 拦截 control tool，返回 ack。
3. 第二轮 assistant 只输出 `已提交评分。`
4. `AgentTurnResult.visibleContent` 必须包含第一轮长篇报告。
5. `visibleContent` 不应只剩 `已提交评分。`
6. `controlEvents` 必须包含 `submit_quality_report`。

建议测试文件：

- `src/agents/runtime/__tests__/agent-runtime-visible-content.test.ts`

## 3. 当前失败点：设定更新 payload 没有闭环

### P0-2：`propose_updates` 只有摘要，没有可执行 updates

问题位置：

- `src/shared/contracts/agent-control.ts`
- `src/agents/tools/control/control-tools.ts`
- `src/agents/graph/graph-definition.ts`
- `src/agents/tools/proposals/update-proposal-tools.ts`
- `src/agents/graph/nodes/lore-advisor-node.ts`
- `src/agents/graph/lore-update-schema.ts`

当前 `propose_updates` schema 只有：

```ts
{
  summary: string;
  sectionCount: number;
}
```

但 `processControlEvents()` 又从 `output.updates` 读取实际变更：

```ts
const pendingUpdates = output.updates;
```

新模式下 `AgentOutput` 是用 Markdown `visibleContent` 构造的，不再解析 JSON，因此 `output.updates` 基本不会存在。

更糟的是，旧 proposal 工具仍然告诉模型：

```text
将上述模板放入你的 JSON 输出的 updates 字段
```

这和新协议直接冲突。

#### 必须完成

`propose_updates` 的 tool arguments 必须携带实际 `updates` payload。

推荐 schema：

```ts
export const ProposalUpdatesEventSchema = z.object({
  type: z.literal("propose_updates"),
  summary: z.string().min(1).max(1000),
  updates: AgentUpdatesSchema,
});
```

如果 `AgentUpdatesSchema` 过大，不要退回 JSON 正文。可以拆分 control tools：

- `propose_character_updates`
- `propose_location_updates`
- `propose_item_updates`
- `propose_faction_updates`
- `propose_glossary_updates`
- `propose_outline_updates`
- `propose_foreshadowing_updates`
- `propose_world_setting_update`

但无论拆不拆，实际可执行 payload 必须来自 tool arguments。

#### 必须修改

1. `src/shared/contracts/agent-control.ts`
   - 给 `propose_updates` 增加 `updates`。
   - 复用 `AgentUpdatesSchema` 或明确拆分后的 schema。
   - 保持 `parseControlEventArgs()` 是唯一控制事件解析入口。

2. `src/agents/tools/control/control-tools.ts`
   - 更新 `propose_updates` 描述。
   - 明确要求模型把实际变更放入 tool arguments。
   - 删除“具体更新内容请在 Markdown 正文中详细说明，或使用 propose_* 工具”的旧说法。

3. `src/agents/graph/graph-definition.ts`
   - `processControlEvents()` 不再读取 `output.updates`。
   - 改为读取 `event.updates`。
   - `interrupt({ pendingUpdates })` 必须使用 `event.updates`。
   - `executeUpdates()` 必须使用 `event.updates`。

4. `src/agents/tools/proposals/update-proposal-tools.ts`
   - 删除所有“放入 JSON 输出 updates 字段”的指令。
   - 如果这些工具继续保留，它们只能返回“如何构造 tool args”的帮助信息。
   - 更好的做法：把这些 proposal 工具合并或替换为真正的 control update tools。

5. `src/agents/graph/nodes/lore-advisor-node.ts`
   - 移除 `LORE_UPDATE_SCHEMA_PROMPT` 的旧 JSON 版本。
   - 改成 “调用 `propose_updates` tool，并在 tool arguments.updates 中提交结构化变更”。

6. `src/agents/graph/lore-update-schema.ts`
   - 不得再向新协议 Agent 注入“JSON 的 updates 字段”说明。
   - 可以保留字段白名单和更新规则，但必须改写为 tool args schema 说明。

#### 不允许

- 不允许让模型在 Markdown 正文里写“待保存设定”再由前端/服务端解析。
- 不允许 `propose_updates` 只发 summary。
- 不允许继续从 `AgentOutput.updates` 补救新协议。
- 不允许为了省事恢复 `parseAgentResponse()` 主路径。

#### 验收测试

必须新增测试，覆盖：

1. 模型调用 `propose_updates`，arguments 中含 `updates.characters`。
2. runtime 产出 `controlEvents[0].type === "propose_updates"`。
3. event 中包含可执行 `updates`。
4. `processControlEvents()` 使用 `event.updates` 触发 `user_input_required`。
5. 用户确认后调用 `executeUpdates(taskId, event.updates)`。
6. 不依赖 `output.updates`。

建议测试文件：

- `src/agents/graph/__tests__/process-control-events.test.ts`
- 或把 `processControlEvents()` 提取为可测模块：`src/agents/graph/control-event-processor.ts`

## 4. 前端主路径必须停止解析 assistant prose

### P1-1：`extractDisplayContent()` 仍在主渲染路径

问题位置：

- `src/features/writing/writing-conversation.tsx`

当前 `extractDisplayContent()` 虽然加了 Markdown fast path，但仍然会尝试：

```ts
JSON.parse(candidate)
```

这不符合“renderer 只做安全清洗，不做业务协议解析”的目标。

#### 必须完成

把消息协议显式化：

```ts
type MessageProtocol = "markdown_control_tools" | "legacy_json";
```

新消息：

- 直接渲染 `content`。
- 不调用 `extractDisplayContent()`。

旧消息：

- 只有明确标记为 `legacy_json` 或历史迁移路径时，才调用 `extractDisplayContent()`。

#### 最小可接受实现

如果暂时不改数据库字段，也必须做到：

- SSE 新事件进来的内容不调用 JSON 解析。
- 当前会话中的新 agent 消息不调用 JSON 解析。
- 历史消息加载时可以保留 legacy fallback，但必须有注释说明这是历史兼容，不是新协议主路径。

#### 不允许

- 不允许用“Markdown fast path”宣称完成。
- 不允许在新协议 `agent_done` 里继续对 content 做 JSON field extraction。
- 不允许前端保存质量报告时解析 scores/qualityGate，这些必须来自 SSE/control event 或服务端落库结果。

## 5. 文档必须纠偏

### P1-2：`src/agents/AGENTS.md` 仍然是旧协议

问题位置：

- `src/agents/AGENTS.md`
- 根 `AGENTS.md` 中 Agent 模块说明也可能需要同步
- `docs/AGENT_RUNTIME_PROTOCOL_REFACTOR_BLUEPRINT.md`

当前 `src/agents/AGENTS.md` 仍然写着：

- JSON 结构化输出
- `updates`
- `wantsToCall`
- `parseAgentResponse()`
- 前端展示层清洗 JSON 外壳

这是严重问题。后续 AI 会优先读 `AGENTS.md`，然后继续按旧协议写代码。

#### 必须完成

更新 `src/agents/AGENTS.md`：

- 明确当前协议是 Markdown assistant content + OpenAI-compatible tool_calls。
- 明确 `route_to_agent` 替代 `wantsToCall`。
- 明确 `propose_updates` tool arguments 承载实际 updates。
- 明确 `submit_quality_report` 替代 scores/qualityGate JSON 字段。
- 明确 `submit_validation_report` 替代 conflicts JSON 字段。
- 明确 `parseAgentResponse()` 只允许 legacy fallback。
- 更新流程图中的 `processResult` 分支。

更新 `docs/AGENT_RUNTIME_PROTOCOL_REFACTOR_BLUEPRINT.md`：

- 删除或修正“全部完成”的结论。
- 标注当前存在 P0 缺口。
- 链接本文。

#### 不允许

- 不允许原文继续宣称“全部 10 个 Phase 完成”。
- 不允许新旧协议并列但不说明主次。
- 不允许把 legacy fallback 写成推荐路径。

## 6. 测试要求

这次返工必须补的是协议测试，不是普通类型测试。

### 6.1 必须通过的命令

```bash
npm run typecheck
npx tsx --test src/agents/runtime/__tests__/agent-runtime.test.ts
npx tsx --test src/agents/runtime/__tests__/agent-runtime-visible-content.test.ts
```

如果新增 graph/control processor 测试：

```bash
npx tsx --test src/agents/graph/__tests__/process-control-events.test.ts
```

### 6.2 必须覆盖的场景

| 场景 | 必须证明 |
| --- | --- |
| Markdown + control tool 同轮输出 | `visibleContent` 不丢正文 |
| 质量报告落库 | `ChapterQualityCheck.result` 使用完整 Markdown |
| `propose_updates` | event 中携带实际 updates |
| 用户确认保存 | `executeUpdates()` 使用 event payload |
| 前端新消息渲染 | 不调用 JSON.parse 解析 assistant prose |
| legacy 历史消息 | 仍可兼容，但隔离在 legacy path |

## 7. 推荐执行顺序

### Phase A：冻结错误完成状态

目标：先停止误导。

任务：

1. 修改 `docs/AGENT_RUNTIME_PROTOCOL_REFACTOR_BLUEPRINT.md`，取消“全部完成”表述。
2. 在该文顶部链接本文。
3. 在 `progress.md` 记录返工原因。

验收：

- 文档不再把半迁移状态描述为完成。

### Phase B：修复 `visibleContent` 聚合

目标：用户看到的内容、服务端保存的内容、质量报告落库内容一致。

任务：

1. 改造 `callLLMWithTools()` 或新增 runtime loop。
2. 聚合每个 assistant message 的可见 `content`。
3. 过滤工具 ack，不把 tool result 拼入 `visibleContent`。
4. 更新 `AgentRuntimeImpl.runTurn()`。
5. 新增 runtime visible content 单测。

验收：

- Markdown + tool_calls 同轮输出不会丢报告。
- `AgentOutput.content` 是完整 Markdown。
- `trySaveQualityCheckResult()` 拿到完整报告。

### Phase C：重做 `propose_updates`

目标：设定更新真正走 tool_calls，且可确认、可落库。

任务：

1. 更新 `ProposalUpdatesEventSchema`。
2. 更新 control tool 描述。
3. 更新 `processControlEvents()` 使用 `event.updates`。
4. 删除新协议中的 `output.updates` 依赖。
5. 移除/改写旧 proposal tools 的 JSON 指令。
6. 移除 `lore-advisor-node` 注入的旧 JSON schema prompt。
7. 新增 event payload 测试。

验收：

- 不再需要模型正文输出 JSON updates。
- 用户确认链路仍可展示变更预览。
- 确认后仍调用 `executeUpdates()`。

### Phase D：隔离前端 legacy 解析

目标：前端不再承担协议解析职责。

任务：

1. 新消息直接渲染 Markdown。
2. `extractDisplayContent()` 仅用于 legacy 历史消息。
3. 当前 SSE `agent_chunk` 和 `agent_done` 不再走 JSON.parse。
4. 如果缺少协议字段，至少用函数命名和注释隔离新旧路径。

验收：

- 新协议消息中出现 `{}`、代码块、JSON 示例时不会被前端误解析。
- `extractDisplayContent()` 不在新消息主路径调用。

### Phase E：更新 Agent 文档

目标：后续 AI 不会继续按旧协议开发。

任务：

1. 重写 `src/agents/AGENTS.md` 的协议章节。
2. 更新流程图。
3. 更新 Agent 开发规范。
4. 标明 legacy parser 的删除条件。

验收：

- 文档读者能清楚知道：Markdown 是正文，tool_calls 是控制面。
- 文档中不再推荐 `wantsToCall` 和 JSON `updates`。

## 8. 完成定义

只有同时满足以下条件，才能重新标记“Agent Runtime 协议重构完成”：

1. 所有新协议 Agent 的 assistant content 都是 Markdown。
2. Agent 路由不依赖 `wantsToCall`。
3. 质量评分不依赖 JSON `scores`。
4. 校验冲突不依赖 JSON `conflicts`。
5. 设定更新不依赖 JSON `updates`。
6. `visibleContent` 能完整聚合 tool-call 轮次正文。
7. `ChapterQualityCheck.result` 保存完整 Markdown 报告。
8. 前端新消息渲染不解析 assistant prose。
9. `src/agents/AGENTS.md` 与真实代码一致。
10. 协议测试覆盖 Markdown + tool_calls 同轮输出、设定更新确认保存。

少一条，都不能叫完成。

## 9. 给执行 AI 的直接要求

不要再提交“看起来完成”的外壳改动。

这次返工只看链路闭环：

- 内容是否完整进入 `visibleContent`？
- 控制事件是否全部来自 tool_calls？
- 设定更新 payload 是否可执行？
- 前端是否停止解析业务协议？
- 文档是否阻止后续 AI 走回旧路？

如果某个改动不能回答这些问题，就不要把它列为完成项。
