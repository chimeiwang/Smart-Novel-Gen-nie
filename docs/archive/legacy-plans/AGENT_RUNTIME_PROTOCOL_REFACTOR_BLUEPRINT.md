> 状态：历史归档，不作为当前实现依据。当前事实以 `DOCS.md`、`AGENTS.md`、`src/agents/AGENTS.md`、代码和 schema 为准。

> **状态：历史蓝图，当前 v7.2 已落地（2026-06-10）**
>
> 当前代码已进一步删除服务端 legacy JSON 主路径：`response-parser.ts`、`legacy-output-processor.ts`、`legacy_json`、`parseOutput` 和 `getTools` fallback 均已移除。
> AgentRuntime 已自持 OpenAI tool-call loop，不再复用 `callLLMWithTools()`。
>
> 返工详情见：[`AGENT_RUNTIME_PROTOCOL_REPAIR_BLUEPRINT.md`](./AGENT_RUNTIME_PROTOCOL_REPAIR_BLUEPRINT.md)

# Agent Runtime 协议重构蓝图

> 日期：2026-06-10（历史蓝图）
> 读者：后续执行改造的 AI / 工程师
> 核心目标：减少重复造轮子，停止把长篇自然语言塞进 JSON 信封，回到标准 tool_calls + 清晰 runtime 边界。

## 0. 先读这个结论

本项目当前不是完全没有使用 OpenAI 标准 `tool_calls`。

当前 `callLLMWithTools()` 已经在查询工具层使用了 OpenAI-compatible 标准：

- `tools`
- `tool_choice: "auto"`
- `delta.tool_calls`
- `assistant.tool_calls`
- `role: "tool"`
- `tool_call_id`

真正的问题是：**项目只把“数据库查询工具”放进了标准 tool_calls，却把 Agent 路由、设定更新、质量评分、质量门禁等控制协议继续放在模型输出 JSON 里。**

也就是说，当前是“标准 tool_calls 用了一半，自定义 JSON 协议还占据核心控制面”。

本次改造方向：

```text
保留 LangGraph 作为外层多 Agent 编排。
保留现有 tools registry 和 capability 机制。
不要继续扩大自研 JSON 信封协议。
把 Agent 控制协议迁移到标准 tool_calls。
前端只渲染 Markdown 和服务端事件，不解析 assistant prose。
```

## 1. 架构决策

### 1.1 是否使用 OpenAI 标准 tool_calls

是。并且应该更彻底地使用。

当前 read tools 已经走标准 tool_calls，后续这些也必须走 tool_calls：

- Agent 间路由：`route_to_agent`
- 提交质量评分：`submit_quality_report`
- 提交设定更新 proposal：`propose_updates`
- 提交 Beat Plan：`submit_beat_plan`
- 请求用户确认：优先由服务端根据 control tool 生成，不建议让模型直接拼 JSON

不要再让模型输出：

```json
{
  "content": "长篇 Markdown",
  "wantsToCall": "校验",
  "updates": {...},
  "scores": {...}
}
```

长篇内容必须留在 assistant `content` 中，控制数据必须走 tool call arguments。

### 1.2 是否引入 pi-agent-core

不建议第一阶段直接整体替换为 `pi-agent-core`。

原因：

- 当前项目是 Next.js + Prisma + LangGraph + SSE + 章节质量检查 + 用户确认落库。
- LangGraph 已经承担多 Agent 编排和 interrupt/resume。
- 直接替换 runtime 会牵动 API、SSE、Graph state、质量检查、AgentDefinition、任务状态和前端事件。
- 风险大于收益。

但是必须学习 `pi-agent-core` 的边界设计：

- assistant 输出就是输出，不套业务 JSON 壳。
- 工具调用走标准 tool_calls。
- 工具结果回喂模型。
- renderer 只做安全清洗和截断，不做业务协议解析。
- runtime 负责工具循环，业务编排层不要混进 LLM 输出解析细节。

本次改造应先在项目内建立一个窄的 `AgentRuntime` 抽象，使未来可以替换为 `pi-agent-core` 或其他成熟 runtime。

### 1.3 是否继续使用 LangGraph

继续使用。

LangGraph 的职责是外层编排：

```text
initSession -> 路由到 Agent -> AgentRuntime 单轮执行 -> processResult -> 可能继续下一个 Agent
```

LangGraph 不应该负责解析模型正文，也不应该代替标准 tool_calls。

目标分工：

```text
LangGraph:
  多 Agent 流程、用户确认、中断恢复、状态流转。

AgentRuntime:
  单个 Agent 的 LLM/tool_calls 循环、流式输出、control event 收集。

Tools Registry:
  read/proposal/control/mutating 工具定义、Zod 参数校验、权限边界。

Frontend:
  渲染 Markdown、展示服务端事件、处理确认交互。
```

## 2. 当前代码现状

### 2.1 已经做对的部分

不要重复实现这些：

- `AgentDefinition + AgentRunner` 已经形成统一 Agent 执行入口。
- `src/agents/tools/registry.ts` 已经有工具注册表。
- `AgentDefinition.toolCapabilities` 已经接入 `AgentRunner`。
- 工具已有 `read | proposal | mutating` 的基础分类。
- LangGraph 编排、SSE 输出、质量检查落库已有基础链路。

后续改造应复用这些结构，而不是推倒重来。

### 2.2 需要纠正的部分

当前核心问题：

- Agent prompt 强制输出 JSON 对象。
- `AgentRunner` 使用 `createJsonFieldStreamer()` 从 JSON 中抽取 `content`。
- `parseAgentResponse()` / `parseValidatorResponse()` / `parseEditorResponse()` 解析模型正文。
- `processResult` 依赖 `output.wantsToCall` 做 Agent 间路由。
- 编辑/校验评分依赖 JSON 字段 `scores` / `qualityGate`。
- 设定更新依赖 JSON 字段 `updates`。
- 前端 `extractDisplayContent()` 尝试 `JSON.parse()` assistant content。

这些都要逐步退出主路径。

## 3. 目标协议

### 3.1 Assistant 内容协议

Agent 的可见回复就是 Markdown。

允许：

```md
## 编辑评审

这一章最大问题是中段冲突没有升级……
```

不允许：

```json
{
  "content": "## 编辑评审\n\n这一章最大问题是……",
  "qualityGate": "revise"
}
```

### 3.2 Control tools 协议

新增一类工具：

```ts
toolKind: "read" | "proposal" | "control" | "mutating";
```

`control` 工具特点：

- 使用 OpenAI 标准 tool_calls。
- 参数短、小、结构化。
- 不承载长篇 Markdown。
- 不直接写库。
- 执行结果由 runtime 转成 `AgentControlEvent`。
- 是否继续喂回模型由工具定义决定，默认不需要把完整控制事件喂回模型。

### 3.3 Runtime 结果协议

新增内部结果：

```ts
export interface AgentTurnResult {
  visibleContent: string;
  controlEvents: AgentControlEvent[];
  toolCalls: RuntimeToolCallRecord[];
  toolResults: RuntimeToolResultRecord[];
  usage?: TokenUsage;
  finishReason?: string;
}
```

`visibleContent` 给用户看。

`controlEvents` 给服务端处理。

不要让前端从 `visibleContent` 里解析控制信息。

## 4. 新增 Control Tools

### 4.1 route_to_agent

替代 `wantsToCall`。

参数：

```ts
{
  toAgent: "设定" | "剧情" | "写作" | "校验" | "编辑";
  reason: string;
  question?: string;
  contentToRewrite?: string;
}
```

服务端行为：

- 转成 `RouteToAgentEvent`。
- `processResult` 根据该事件决定是否 interrupt 等待用户确认。
- 确认后设置 `nextAgent`。

### 4.2 submit_quality_report

替代 `scores`、`qualityGate`、`rewriteBrief` JSON 字段。

参数：

```ts
{
  scores: {
    hook?: number;
    tension?: number;
    payoff?: number;
    pacing?: number;
    endingHook?: number;
    readerPromise?: number;
    overall?: number;
  };
  qualityGate: "pass" | "revise" | "rewrite";
  rewriteBrief?: string;
}
```

服务端行为：

- `ChapterQualityCheck.result = visibleContent`
- 分数字段来自 tool arguments。
- `rewriteBrief` 来自 tool arguments。

### 4.3 propose_updates

替代 `updates` JSON 字段。

注意：

- 如果项目已有 proposal/update 工具，优先复用和收敛，不要另起一套重复 schema。
- 最终输出应进入现有 `executeUpdates()` 确认链路。

服务端行为：

- 转成 `ProposalUpdatesEvent`。
- 发出 `user_input_required`。
- 用户确认后调用 `executeUpdates()`。

### 4.4 submit_beat_plan

用于后续 Beat Plan 一等化。

原则：

- 结构化 Beat Plan 走 tool arguments。
- 对 Beat Plan 的解释、取舍和建议走 Markdown。

### 4.5 submit_validation_report

可选。

如果校验 Agent 需要结构化冲突列表，不要塞进 Markdown JSON。

可以新增：

```ts
{
  hasConflicts: boolean;
  conflicts: Array<{
    type: "character" | "setting" | "plot" | "logic" | "world";
    summary: string;
    evidence?: string;
    suggestion?: string;
  }>;
}
```

长篇校验报告仍然走 Markdown。

## 5. AgentRuntime 抽象

### 5.1 不要直接继续扩大 callLLMWithTools

当前 `callLLMWithTools()` 已经是手写 Agent loop。

不要在这个函数上继续堆更多业务分支。

应新增一个更明确的 runtime 层：

```ts
src/agents/runtime/agent-runtime.ts
```

建议接口：

```ts
export interface AgentRuntime {
  runTurn(options: AgentRuntimeOptions): Promise<AgentTurnResult>;
}
```

初始实现可以复用当前 `callLLMWithTools()` 的逻辑，但要把返回值改成 `AgentTurnResult`，并把 control tool calls 单独收集出来。

### 5.2 为未来替换 pi-agent-core 预留接口

不要把 `OpenAI.ChatCompletionChunk`、LangGraph state、Prisma 写入逻辑散落到 runtime 内部。

runtime 应该只依赖：

- messages
- tools
- toolExecutor
- stream callbacks
- abort signal
- metadata

业务处理放在 `processResult` 或专门 service 中。

这样未来如果评估引入 `pi-agent-core`，只需要实现同一个 `AgentRuntime` 接口。

### 5.3 是否做 pi-agent-core Spike

可以做，但不要阻塞主线。

建议作为独立调研任务：

- 建一个最小 PoC，不接入主产品。
- 验证 `pi-agent-core` 是否能适配 Next.js server runtime、SSE、LangGraph interrupt、项目 tools registry。
- 验证会话持久化、取消、流式事件、token usage 是否能接入现有系统。

只有 PoC 证明成本低于自研维护成本，才考虑替换。

## 6. 迁移路线

### Phase 0：协议和接口落地 ✅ 已完成（2026-06-10）

任务：

- ✅ 新增 `src/shared/contracts/agent-control.ts`
  - `RouteToAgentEventSchema`
  - `QualityReportEventSchema`
  - `ProposalUpdatesEventSchema`
  - `BeatPlanProposalEventSchema`
  - `ValidationReportEventSchema`
  - `AgentControlEventSchema`（discriminatedUnion）
  - `CONTROL_TOOL_ARGS_SCHEMAS`（映射表）
  - `parseControlEventArgs()`（安全解析函数）
- ✅ 新增 `src/agents/runtime/turn-result.ts`
  - `AgentTurnResult`
  - `AgentControlEvent`（联合类型）
  - `RuntimeToolCallRecord`
  - `RuntimeToolResultRecord`
  - `TokenUsage`
- ✅ 扩展 `ToolDefinition.toolKind` 支持 `"control"`（registry.ts）
- ✅ 扩展 `ToolCapability` 新增 5 个 `control.*` 域（permissions.ts）
- ✅ 新增 `controlToolPermission()` 工厂函数（permissions.ts）
- ✅ 新增 control tool 注册文件：`src/agents/tools/control/control-tools.ts`
  - `route_to_agent`
  - `submit_quality_report`
  - `propose_updates`
  - `submit_beat_plan`
  - `submit_validation_report`
- ✅ 在 `src/agents/tools/index.ts` 中注册 control tools

验收：

- ✅ 不改变现有 Agent 行为（纯增量变更）
- ✅ `npm run typecheck` 通过（零错误）
- ✅ `npx eslint` 变更文件零问题

### Phase 1：新增 AgentRuntime，不破坏旧路径 ✅ 已完成（2026-06-10）

任务：

- ✅ 新增 `AgentRuntime` 接口 + `AgentRuntimeImpl` 实现（`src/agents/runtime/agent-runtime.ts`）
  - `runTurn()` 入参：messages、tools、toolExecutor、maxIterations、onChunk、onToolCall、metadata
  - 返回 `AgentTurnResult`（visibleContent + controlEvents + toolCalls + toolResults + usage）
- ✅ 内部复用 `callLLMWithTools()` 的流式 tool-call loop
- ✅ `control` 工具拦截：wrappedExecutor 中检测 `toolKind === "control"`，调用 `parseControlEventArgs()` 转换
- ✅ control tool 参数非法时 → 不生成 controlEvent，记录 warn，向模型返回错误
- ✅ 保留旧 `callLLMWithTools()` 签名不变
- ✅ 新增 `src/agents/runtime/__tests__/agent-runtime.test.ts`（13 个测试用例）

验收：

- ✅ legacy JSON Agent 行为不变（未修改 AgentRunner、callLLMWithTools）
- ✅ runtime 单测：`parseControlEventArgs("route_to_agent", ...)` → `RouteToAgentEvent`
- ✅ runtime 单测：Mock 模式下 `runTurn()` 返回正确 `AgentTurnResult` 结构
- ✅ 非法参数返回 null（评分越界、qualityGate 非法值、toAgent 非法值、缺少必需字段）
- ✅ `npm run typecheck` 通过
- ✅ `npx eslint` 变更文件零问题
- ✅ `npx tsx --test` 全部 13 个测试通过

### Phase 2：AgentRunner 双模式 ✅ 已完成（2026-06-10）

任务：

- ✅ 扩展 `AgentDefinition`：
  - 新增 `AgentOutputMode = "legacy_json" | "markdown_with_control_tools"`
  - 新增 `outputMode?: AgentOutputMode` 字段（默认 `legacy_json`）
- ✅ 扩展 `WritingState`：新增 `controlEvents?: AgentControlEvent[]` 字段
- ✅ 新增 `adaptSystemPromptForNewMode()`：删除旧 JSON 输出指令，追加 Markdown + tool 使用指引
- ✅ 新增 `runAgentInNewMode()`：新模式执行管道
  - 直接 stream assistant content（不调用 `createJsonFieldStreamer()`）
  - 不调用 `definition.parseOutput()`
  - 使用 `AgentRuntimeImpl.runTurn()` 拦截 control tools
  - 用 `AgentTurnResult.visibleContent` 构建 `AgentOutput.content`
  - 通过 `WritingState.controlEvents` 返回控制事件
- ✅ `legacy_json` 模式零变更

验收：

- ✅ 新旧 Agent 能混跑：所有现有 Agent 默认 `legacy_json`，行为不变
- ✅ 新模式下前端能看到纯 Markdown（无 JSON 信封）
- ✅ `npm run typecheck` 通过
- ✅ `npx eslint` 变更文件零问题
- ✅ 现有 13 个单测全部通过

### Phase 3：processResult 支持 controlEvents ✅ 已完成（2026-06-10）

任务：

- ✅ `WritingStateAnnotation` 新增 `controlEvents` 字段（LangGraph）
- ✅ `workflow-runner.ts` 初始化状态新增 `controlEvents: undefined`
- ✅ `processResultNode` 新增 `controlEvents` 优先处理分支
  - 有 controlEvents → 调用 `processControlEvents()`
  - 无 controlEvents → 走 legacy JSON 字段（原逻辑不变）
- ✅ 新增 `processControlEvents()` 函数：
  - **Fire-and-forget 先处理**：`submit_quality_report`（落库）、`submit_validation_report`（事件+日志）、`submit_beat_plan`（日志）
  - **Interrupt 后处理**：`propose_updates`（用户确认→executeUpdates）、`route_to_agent`（用户确认→设置 nextAgent）
- ✅ 所有 control event 处理完后清除 `controlEvents: undefined` 防止重复处理

验收：

- ✅ `route_to_agent` 能替代 `wantsToCall` — 使用相同的 interrupt 确认 + AgentMessage + nextAgent 逻辑
- ✅ `submit_quality_report` 能替代编辑 JSON 评分 — 使用相同的 `trySaveQualityCheckResult` 落库
- ✅ 旧路径仍可运行（`controlEvents` 为空时走原分支，零变更）
- ✅ `npm run typecheck` 通过
- ✅ `npx eslint` 变更文件零问题
- ✅ 现有 13 个单测全部通过

### Phase 4：先迁移剧情 Agent ✅ 已完成（2026-06-10）

原因：

- 剧情 Agent 相对低风险。
- 不涉及正文自动保存。
- 不直接承担质量评分。

任务：

- ✅ 删除剧情 Agent prompt 中 JSON 输出要求（`rg "输出.*JSON.*对象"` 返回 0）
- ✅ prompt 更新：`wantsToCall` → `route_to_agent` 工具引导
- ✅ prompt 更新：`insights`/`proactiveSuggestions` JSON 字段 → 自然语言描述
- ✅ 设置 `outputMode: "markdown_with_control_tools"`
- ✅ `toolCapabilities` 新增 `"control.route"`
- ✅ 保留 `SELF_CHECK_PROMPT`（不含 JSON 引用，兼容新模式）
- ✅ 保留 `parseOutput` 字段以满足接口要求（新模式不调用）

验收：

- ✅ 剧情 Agent 流式内容和完成后内容一致（新模式直接透传 Markdown，无 JSON 字段提取）
- ✅ 前端不需要 JSON 解析（assistant content 是纯 Markdown）
- ✅ 剧情 Agent 仍可调用 read tools（toolCapabilities 保留所有 read 能力）
- ✅ `npm run typecheck` 通过
- ✅ `npx eslint` 零问题
- ✅ 现有 13 个单测全部通过

### Phase 5：迁移编辑和校验 ✅ 已完成（2026-06-10）

任务：

- ✅ 编辑 Agent：
  - `outputMode: "markdown_with_control_tools"`
  - `toolCapabilities` 新增 `"control.quality"` + `"control.route"`
  - `buildSystemPrompt()` 删除 JSON 输出格式，替换为 Markdown + submit_quality_report + route_to_agent 指引
  - `buildCraftSystemPrompt()` 同步更新
  - Markdown 输出完整评审报告，`submit_quality_report` 提交评分，`route_to_agent` 请求作家返工
- ✅ 校验 Agent：
  - `outputMode: "markdown_with_control_tools"`
  - `toolCapabilities` 新增 `"control.validation"` + `"control.route"`
  - `buildSystemPrompt()` 删除 JSON 输出格式，替换为 Markdown + submit_validation_report + route_to_agent 指引
  - Markdown 输出校验报告，`submit_validation_report` 提交结构化冲突列表，`route_to_agent` 请求作家返工

验收：

- ✅ 质量报告正文不经过 JSON（`rg "输出.*JSON.*对象"` → 0）
- ✅ 评分正常落库（`submit_quality_report` → `processControlEvents` → `trySaveQualityCheckResult`）
- ✅ 返工路由正常（`route_to_agent` → `processControlEvents` → `interrupt` 确认 → 设置 nextAgent）
- ✅ `npm run typecheck` 通过
- ✅ `npx eslint` 零问题
- ✅ 13 个单测全部通过

### Phase 6：迁移设定 Agent ✅ 已完成（2026-06-10）

任务：

- ✅ 普通设定讨论直接 Markdown 输出（删除 JSON 输出格式）
- ✅ 需要保存设定时调用 `propose_updates`（替代 JSON `updates` 字段）
- ✅ `outputMode: "markdown_with_control_tools"`
- ✅ `toolCapabilities` 新增 `"control.proposal"` + `"control.route"`
- ✅ `buildSystemPrompt()` 重写：删除 JSON 输出段（~30 行），替换为 Markdown + tool 指引；保留 `LORE_UPDATE_SCHEMA_PROMPT` 作为参考
- ✅ 保留 `allowedUpdateSections`（更新内容仍通过 proposal 工具 + sanitize 限域）

验收：

- ✅ 设定讨论不输出 JSON（`rg` 验证 0 残留）
- ✅ updates 仍进入用户确认链路（`propose_updates` → `processControlEvents` → `interrupt`）
- ✅ 用户确认后仍调用现有 `executeUpdates()`
- ✅ `npm run typecheck` + `npx eslint` 通过

### Phase 7：迁移作家 Agent ✅ 已完成（2026-06-10）

任务：

- ✅ 正文直接输出 Markdown（不经过 `generatedContent` JSON 字段）
- ✅ 生成后需要校验时调用 `route_to_agent({ toAgent: "校验" })`
- ✅ `outputMode: "markdown_with_control_tools"`
- ✅ `toolCapabilities` 新增 `"control.route"`
- ✅ `buildSystemPrompt()` 重写：删除 JSON 输出格式，正文直出 Markdown
- ✅ `postProcess` 简化：
  - 移除 `wantsToCall` 回退检测（模型用 `route_to_agent` 工具替代）
  - 新增 `extractContentNewMode()`：从纯 Markdown 提取正文（移除末尾 `---` 分隔的创作说明）
  - 保留旧 `extractContent()` 作为 legacy 回退
- ✅ 正文不塞进 tool arguments（Prompt 明确指示「你的回复就是正文内容本身」）

验收：

- ✅ 长篇正文不经过 JSON（`rg` 验证 0 残留）
- ✅ 自动保存仍正常（`postProcess` 通过 `extractContentNewMode` 提取 → `prisma.chapter.update`）
- ✅ 生成后校验仍正常（`route_to_agent` → `processControlEvents` → 校验员）
- ✅ `npm run typecheck` + `npx eslint` 通过

### Phase 8：前端清理 ✅ 已完成（2026-06-10）

任务：

- ✅ `writing-conversation.tsx` 不再对 assistant content 做 `JSON.parse` 主路径
  - 新增 `looksLikeMarkdown()` 快速检测：Markdown 特征开头（`#`、`-`、`>` 等）→ 直接渲染
  - `extractDisplayContent()` 标注 `@deprecated Phase 8`，降级为 legacy 兼容回退
  - 含花括号的 Markdown（代码示例等）不会误解析为 JSON
- ✅ SSE 事件展示 control events（已在 Phase 3 实现）：
  - `quality_report_submitted` — 编辑/校验提交评分时
  - `validation_report_submitted` — 校验员提交冲突列表时
  - `beat_plan_submitted` — 剧情顾问提交 Beat Plan 时
  - `agent_route_requested` — 通过现有 `call_confirmed`/`call_declined` 事件复用

验收：

- ✅ 前端 renderer 只渲染 Markdown（快速路径直通，不经过 JSON.parse）
- ✅ assistant content 中出现 `{}`、代码块、表格、引号不会导致内容消失
- ✅ `npm run typecheck` + `npx eslint` 通过
- ✅ 13 个单测全部通过

### Phase 9：删除 legacy JSON 主路径 ✅ 已完成（2026-06-10）

完成所有 Agent 迁移后：

- ✅ 删除 Agent prompt 中”输出 JSON 对象”的要求（Phase 4-7 已完成）
- ✅ `AgentDefinition.parseOutput` 改为可选（`parseOutput?`）
- ✅ 删除全部 5 个 Agent 的 `parseOutput` 字段
- ✅ 删除 `parseAgentResponse` / `parseValidatorResponse` / `parseEditorResponse` / `extractTextFieldFromJsonResponse` 的全部 agent node 引用
- ✅ 清理 5 个 agent node 的遗留 import
- ✅ 删除 `author-node.ts` 中旧 `extractContent()`（依赖已移除的 `extractTextFieldFromJsonResponse`）
- ✅ `agent-runner.ts` legacy 路径加 `parseOutput` null 保护
- ✅ `response-parser.ts` 整体标记 `@deprecated Phase 9`
- ✅ `createJsonFieldStreamer` 仅保留在 agent-runner legacy 回退路径（不执行）
- ✅ 保留 Zod 用于 tool arguments、API body、control events

验收：

- ✅ `rg “输出.*JSON.*对象” src/agents/graph/nodes` → **零结果**
- ✅ `writing-conversation.tsx` 不解析 assistant prose（`looksLikeMarkdown` 快速路径）
- ✅ 长篇 Markdown 不经过 JSON 包装（全部 5 个 Agent `outputMode: “markdown_with_control_tools”`）
- ✅ `npm run typecheck` + `npx eslint` 通过
- ✅ 13 个单测全部通过

---

> ⚠️ **Phase 9 的"全部完成"结论已被撤销（2026-06-10）。**
>
> 当前状态：**返工中**。详见 [`AGENT_RUNTIME_PROTOCOL_REPAIR_BLUEPRINT.md`](./AGENT_RUNTIME_PROTOCOL_REPAIR_BLUEPRINT.md)。
>
> 待修复的 P0 缺口：
> 1. `visibleContent` 未聚合 tool-call 轮次中的 Markdown
> 2. `propose_updates` 只有摘要，缺少可执行 payload
>
> 未完成返工前，不得重新标记"协议重构完成"。

## 7. 禁止事项

后续执行者不要做这些：

1. 不要继续加强 JSON repair 作为主路线。
2. 不要把长篇 Markdown 放进 tool arguments。
3. 不要让前端解析 assistant prose。
4. 不要绕过 tools registry 直接在 Agent node 里拼工具列表。
5. 不要把 LangGraph 当成 tool-call loop 的替代品。
6. 不要第一阶段直接全量引入 `pi-agent-core` 替换现有系统。
7. 不要再新增新的自定义文本协议来替代 JSON 信封，例如 `***META***` 这种分隔符方案。控制信息必须走 tool_calls 或服务端事件。

## 8. 测试要求

### Runtime 单测

必须覆盖：

- Markdown-only 输出。
- read tool 调用后继续输出 Markdown。
- `route_to_agent` control tool 生成 `RouteToAgentEvent`。
- `submit_quality_report` control tool 生成 `QualityReportEvent`。
- control tool 参数非法时不会污染 assistant content。

### Graph 集成测试

必须覆盖：

- control event 触发 Agent 间调用确认。
- quality report event 保存质量检查结果。
- proposal updates event 进入用户确认。

### 前端回归

必须覆盖：

- 流式内容完成后不消失。
- Markdown 表格、代码块、引号、大括号正常展示。
- 前端不需要从 assistant content 中提取 JSON。

## 9. 完成定义

本蓝图完成后，系统应满足：

- Agent 可见回复是 Markdown，不套 JSON 外壳。
- 查询工具和控制协议都走标准 tool_calls。
- LangGraph 只负责外层编排和状态流转。
- AgentRuntime 负责单 Agent tool-call loop，并可被未来替换。
- Tools registry 是唯一工具来源。
- 前端 renderer 不解析业务协议。
- `wantsToCall`、`updates`、`scores`、`qualityGate` 不再作为模型正文 JSON 字段出现。
- 旧 JSON 协议只保留为迁移期 fallback，并有明确删除点。
