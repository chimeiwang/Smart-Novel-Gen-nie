# Agent 架构重构 — 遗留问题追踪

本文档追踪《Agent 架构重构执行计划》各阶段完成后遗留的问题，
供后续阶段处理或未来版本修复。

## Phase 1: 安全边界止血

### 1.1 历史数据 `novel.userId = null`

- **严重程度**：中 → ✅ 已解决
- **解决**：创建 `scripts/backfill-novel-userid.ts` 回填脚本（`npx tsx scripts/backfill-novel-userid.ts`）

### 1.2 `resumeWriting` 内部未做二次鉴权

- **严重程度**：低 → ✅ 已解决
- **解决**：`resumeWriting()` 新增 `userId` 参数 + 内部 `task.novel.userId` 对比校验。API 路由传入 `session.userId`。形成纵深防御。

### 1.3 `getWriteTools()` 函数仍存在但未导出给 Agent

- **严重程度**：低 → ✅ 已解决
- **解决**：`src/agents/lib/tools.ts` 已瘦身为执行器和参数摘要辅助，旧 `getWriteTools()` / `withWriteTools()` 已删除。写入只能走 proposal/control event → 用户确认 → `executeUpdates()`。

## Phase 2: 结构化输出替换手写 JSON 解析

### 2.1 `createJsonFieldStreamer` 仍用手写流式解析

- **严重程度**：中 → ✅ 已解决
- **解决**：Agent 正文已迁移为 Markdown 直出，`createJsonFieldStreamer` 和 `response-parser.ts` 已删除。服务端不再从 Agent 正文 JSON 中抽取 `content`。

### 2.2 工具调用 + 结构化输出不能同时使用

- **严重程度**：低 → ✅ 已解决
- **解决**：不再要求 Agent 同时输出 JSON 信封和 tool calls。正文是 Markdown，控制信息通过 OpenAI tool_calls 的 control tools 提交。

### 2.3 `extractTextFieldFromJsonResponse` 保留简单正则回退

- **严重程度**：低 → ✅ 已解决
- **解决**：服务端 Agent JSON 响应解析已删除。前端只保留历史 DB 消息展示清洗，不参与控制流。

### 2.4 `callLLMStructured` 使用 `response_format: json_object` 而非 `json_schema`

- **严重程度**：低
- **现状**：DeepSeek API 不完全支持 OpenAI 的 `json_schema` 严格模式，使用 `json_object` 作为兼容方案。LLM 可能仍返回不符合 schema 的 JSON（由 Zod 校验 + 重试捕获）。
- **建议**：若后续切换到支持 `json_schema` 的 provider（如 OpenAI），可升级为严格模式
- **责任人**：待定

## Phase 3: 工具层重构

### 3.1 Agent 工具集函数仍手动维护

- **严重程度**：中 → ✅ 已解决
- **解决**：`AgentDefinition.getTools` 已删除，所有 Agent 通过 `toolCapabilities` 从 registry 获取工具。

### 3.2 写入工具的 proposal 模式未实现

- **严重程度**：中
- **现状**：`proposals/` 目录已创建但为空。写工具被 `isWriteTool` 标志拦截后返回 `WRITE_TOOL_DISABLED` 引导消息，但尚未实现"生成 proposal 结构 → 用户确认 → 服务端事务执行"的完整链路
- **建议**：Phase 4 实现 AgentRunner + processResult 中断逻辑时完成
- **责任人**：Phase 4-5

### 3.3 Agent node direct import 已解决

- **严重程度**：低 → ✅ Phase 4 已解决
- **解决**：AgentRunner 统一封装了整个执行管道，Agent node 不再直接 import `createToolExecutor`/`callLLMWithTools`/`createJsonFieldStreamer`。每个 node 只 import 其特有的构建函数和 AgentDefinition 类型。

### 3.4 Zod 校验错误消息未充分本地化

- **严重程度**：低
- **现状**：`executeTool()` 中的 Zod 校验失败消息为英文 technical message，LLM 看到后可能困惑
- **建议**：改进为中文错误消息或更引导性的提示
- **责任人**：Phase 4+

## Phase 4: AgentDefinition + AgentRunner

### 4.1 作家 Agent 后处理未完全融入 AgentRunner

- **严重程度**：中
- **现状**：作家 Agent 仍有 ~55 行自定义后处理代码（正文提取、自动入库、校验触发检测）。AgentRunner 返回后，authorNode 做二次处理。这些逻辑未能声明式配置。
- **建议**：Phase 5 可考虑在 AgentDefinition 中添加 `postProcess` 钩子，或创建 WriterAgentDefinition 子类型
- **责任人**：Phase 5

### 4.2 编辑/校验的 preGuard 逻辑简单但不够灵活

- **严重程度**：低
- **现状**：preGuard 只支持 skip/不 skip 二元判断。无法声明更复杂的条件。
- **建议**：后续可扩展为 `preProcess(state) => state` 钩子
- **责任人**：Phase 5+

### 4.3 AgentDefinition 中的 tools 列表仍手动维护

- **严重程度**：低 → ✅ 已解决
- **解决**：`getTools` 回调和 `getXxxTools()` 已删除。AgentDefinition 只保留 `toolCapabilities`。

## Phase 5: 拆分 LangGraph 执行器

### 5.1 MemorySaver 仍在使用，未替换为持久化 checkpoint

- **严重程度**：中 → 当前不处理
- **现状**：`MemorySaver` 仅用于当前进程内 LangGraph `interrupt/resume`，服务确认保存和确认路由。
- **决策**：当前产品短期不要求停机恢复或多实例恢复，不引入持久化 checkpointer。不要把“替换 MemorySaver”列为当前必须项。

## Phase 6: 质量检查服务端化

### 6.1 前端仍通过 SSE 触发检查，质量检查未完全异步

- **严重程度**：中
- **现状**：`trySaveQualityCheckResult()` 已服务端保存评分，但前端 `runQualityCheck()` 仍通过发送消息触发 Agent。断网时评分已落库但前端可能不知道。
- **建议**：创建独立的 API 端点（如 `/api/quality-check/run`），完全服务端驱动
- **责任人**：Phase 7

### 6.2 lore_sync 检查类型未接入 Agent 系统

- **严重程度**：低
- **现状**：`quality-check-service.ts` 定义了 4 种检查类型，但 `lore_sync` 仍由前端 `handleSyncRecentLore()` 处理
- **建议**：Phase 7 将 lore_sync 也接入 Agent 工作流
- **责任人**：Phase 7

## Phase 7: 写作闭环工作流 + Proposal + 质量检查 API

### 7.1 ✅ 3.2 proposal 模式 — 已解决
5 个 proposal 工具（角色/状态/大纲/伏笔），LLM 调用时返回结构化模板 → updates → interrupt → executeUpdates。

### 7.2 ✅ 4.1 作家后处理 — 已解决
AgentDefinition 新增 `postProcess` 钩子，authorNode 精简为 5 行。

### 7.3 ✅ 6.1 质量检查独立 API — 已解决
`/api/quality-check/run` 端点，POST checkId → 服务端调用 Agent → 自动落库。
