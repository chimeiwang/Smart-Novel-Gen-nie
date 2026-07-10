> 状态：历史归档，不作为当前实现依据。当前事实以 `DOCS.md`、`AGENTS.md`、`src/agents/AGENTS.md`、代码和 schema 为准。

# 架构改造计划：契约、工作流、工具、Beat Plan

> 范围：对应架构建议中的 2/3/4/5。
> 目标：先收敛系统边界，再扩展写作闭环能力，避免继续在旧状态、旧工具列表和临时 API 上叠功能。

## 一、改造目标

本次改造不以新增 Agent 数量为目标，而是把现有五 Agent 系统整理成更稳定的生产架构：

1. 字段契约统一：状态、类型、Agent ID、质量门禁、SSE 事件和 API 输入输出有唯一来源。
2. 聊天会话和生产工作流解耦：质量检查、设定同步、章节生成不再伪装成同一种写作任务。
3. 工具系统收口：Agent 通过能力域获取工具，不再手写维护工具列表。
4. Beat Plan 一等化：章节规划从临时 prompt 和 TS 类型升级为可保存、可确认、可验收的数据模型。

## 二、设计原则

- 先契约，后流程，再功能。
- 保留现有用户体验入口，但后端逐步切到新模型。
- 任何 LLM 产生的写入都必须走 proposal 或 updates 确认链路。
- 迁移阶段允许兼容层存在，但必须有明确删除点。
- 每一阶段都要能独立验收，避免一次性大爆炸式重构。

## 三、阶段计划

### Phase 0：基线审计与迁移边界

目标：确认当前字段、API、前端组件和 Agent 运行路径的真实依赖。

主要任务：

- 梳理 `Chapter.status`、`ChapterQualityCheck.type/status/qualityGate`、`WritingTask.phase`、`WritingSession.phase`、`WritingConfig.enabledAgents` 的读写点。
- 梳理 `/api/writing/session`、`/api/writing/resume`、`/api/quality-check/run` 的任务创建和恢复路径。
- 梳理 `src/agents/lib/tools.ts` 中手写工具列表与 `src/agents/tools/registry.ts` 的重叠关系。
- 梳理 Beat Plan 当前只存在于 `writing-workflow-service.ts` 的类型和 prompt 中，确认尚未持久化。

验收标准：

- 形成字段读写清单。
- 标出所有旧 Agent ID、字符串状态、重复映射、临时兼容层。
- 明确本次不处理的范围，例如 checkpoint 持久化可作为后续单独工程。

### Phase 1：字段契约统一

目标：让核心业务状态有唯一 contract，前端、API、Agent、服务层不再各自定义。

主要任务：

- 新增或补全共享契约：
  - `src/shared/contracts/agent.ts`：`CoreAgentIdSchema`、Agent 元信息、默认启用 Agent。
  - `src/shared/contracts/workflow.ts`：`WritingTaskPhaseSchema`、`WritingSessionPhaseSchema`、后续 `WorkflowRunStatusSchema`。
  - 扩展 `src/shared/contracts/quality-check.ts`：确保检查类型、状态、门禁、默认消息、Agent 映射都是唯一来源。
  - 收紧 `src/shared/contracts/sse-events.ts`：把 `agentId`、`qualityGate`、`phase` 从宽泛 `string` 改为共享 schema 派生类型。
- 改造调用方：
  - `actions.ts`、API route、Agent service、前端 Props 从 contract 导入类型和常量。
  - 清理 `host,writer,validator` 旧默认值，统一为中文 Agent ID。
  - 所有 API 入参用 Zod schema 做运行时校验。
- Prisma 处理策略：
  - 短期：先在 contract 层收口，降低迁移风险。
  - 中期：将稳定状态迁移为 Prisma enum，至少包括质量检查状态、质量门禁、章节状态。

验收标准：

- `rg "host,writer,validator" src prisma` 不再出现新的默认逻辑，只允许历史 migration 中存在。
- 质量检查默认定义只从 `QUALITY_CHECK_DEFINITIONS` 派生。
- 前端不再手写质量检查 type/status/gate union。
- `npm run typecheck` 通过。

### Phase 2：聊天会话与生产工作流解耦

目标：把“用户聊天”和“Agent 生产任务”拆成两种模型，质量检查不再通过创建普通 `WritingTask` 来复用写作流程。

建议数据模型：

- `WorkflowRun`
  - `id`
  - `novelId`
  - `chapterId`
  - `userId`
  - `kind`: `chat | chapter_generation | quality_check | lore_sync | beat_plan`
  - `status`: `pending | running | waiting_user | completed | failed | cancelled`
  - `sourceType`: `writing_session | writing_task | quality_check | manual`
  - `sourceId`
  - `currentAgentId`
  - `input`
  - `output`
  - `errorMessage`
  - timestamps
- `WorkflowStep`
  - `runId`
  - `agentId`
  - `stepType`: `agent | tool | user_confirmation | persistence`
  - `status`
  - `input`
  - `output`
  - `durationMs`
  - timestamps

主要任务：

- 新建 workflow service，作为 Agent 执行的统一入口。
- `/api/quality-check/run` 创建 `WorkflowRun(kind=quality_check)`，不再创建普通 `WritingTask`。
- `/api/writing/session` 仍可创建聊天会话，但底层 Agent 调用也绑定到 `WorkflowRun(kind=chat)`。
- `ChapterQualityCheck` 只保存检查项结果，执行过程放到 `WorkflowRun/WorkflowStep`。
- 保留 `WritingTask` 给章节生成和采纳正文使用，不再承担所有 Agent 运行语义。

迁移策略：

- 第一阶段保持 API 响应和 SSE 事件兼容。
- 新服务内部同时写旧字段和新 run 记录。
- 前端稳定后，移除质量检查对 `WritingTask` 的依赖。

验收标准：

- 运行质量检查不会新建普通 `WritingTask`。
- 一个质量检查能在数据库里看到完整 `WorkflowRun` 和至少一个 `WorkflowStep`。
- 失败、重试、用户确认都能挂在同一个 run 下。
- 现有写作面板和检查队列功能不回退。

### Phase 3：工具系统收口

目标：让工具注册表成为唯一工具来源，Agent 不再维护手写工具数组。

目标形态：

```ts
const loreAdvisorDefinition: AgentDefinition = {
  id: "设定",
  toolCapabilities: ["novel.read", "character.read", "lore.read", "plot.recentChapters", "proposal.lore"],
  ...
};
```

主要任务：

- 扩展 `ToolPermission.capability`，形成稳定能力域命名：
  - `novel.read`
  - `character.read`
  - `lore.read`
  - `plot.read`
  - `chapter.read`
  - `style.read`
  - `proposal.lore`
  - `proposal.plot`
- `AgentDefinition` 新增 `toolCapabilities?: string[]` 或 `toolSelector?: (state) => ToolDefinition[]`。
- `AgentRunner` 根据 capability 从 registry 派生 OpenAI tools。
- 将 `getLoreAdvisorTools()`、`getPlotAdvisorTools()`、`getValidatorTools()`、`getWriterTools()`、`getEditorTools()` 标记为废弃，逐个替换调用方。
- 清理 `src/agents/lib/tools.ts`，最后只保留：
  - `createToolExecutor`
  - `summarizeToolArgs`
  - OpenAI 工具转换兼容函数，或直接迁移到 registry。

验收标准：

- 新增工具只需要在 registry 注册一次，不需要同步改多个 `getXxxTools()`。
- `AgentDefinition` 中能一眼看到该 Agent 的能力边界。
- 直接写库工具继续被拦截，proposal 工具可正常生成待确认更新。
- `npm run typecheck` 通过。

### Phase 4：Beat Plan 一等化

目标：把章节写前规划变成可保存、可确认、可验收的数据，而不是一次性的提示词文本。

建议数据模型：

- `ChapterWritingGoal`
  - `id`
  - `novelId`
  - `chapterId`
  - `narrativeGoal`
  - `desiredEmotion`
  - `requiredForeshadowing`
  - `requiredCharacters`
  - `wordCountMin`
  - `wordCountMax`
  - `specialNotes`
  - timestamps
- `ChapterBeatPlan`
  - `id`
  - `chapterId`
  - `goalId`
  - `status`: `draft | reviewing | approved | rejected | superseded`
  - `chapterGoal`
  - `mainPlotConnection`
  - `chapterAcceptanceCriteria`
  - `totalEstimatedWords`
  - timestamps
- `SceneBeat`
  - `id`
  - `beatPlanId`
  - `order`
  - `goal`
  - `conflict`
  - `characters`
  - `foreshadowingRefs`
  - `estimatedWords`
  - `acceptanceCriteria`

主要任务：

- 新增 Beat Plan contract：
  - `ChapterWritingGoalSchema`
  - `ChapterBeatPlanSchema`
  - `SceneBeatSchema`
  - `BeatPlanStatusSchema`
- 新增服务端操作或 API：
  - 保存章节目标。
  - 请求剧情 Agent 生成 Beat Plan。
  - 作者确认或驳回 Beat Plan。
  - 作家按已确认 Beat Plan 生成正文。
- 改造 Agent prompt：
  - 剧情 Agent 输出结构化 Beat Plan proposal。
  - 作家 Agent 优先使用已确认 Beat Plan。
  - 编辑/技法评审引用 Beat Plan 的验收标准，判断是否偏离本章目标。
- 前端工作台新增轻量入口：
  - 当前章节目标。
  - Beat Plan 列表。
  - 确认后进入写作。

验收标准：

- 一个章节可以保存写作目标。
- 剧情 Agent 能生成结构化 Beat Plan，并等待用户确认。
- 作家生成正文时能引用已确认 Beat Plan。
- 技法评审能指出正文相对 Beat Plan 的偏离。

## 四、推荐执行顺序

推荐顺序：

1. Phase 1 字段契约统一。
2. Phase 3 工具系统收口。
3. Phase 2 聊天和生产工作流解耦。
4. Phase 4 Beat Plan 一等化。

原因：

- 契约统一是所有后续改造的地基。
- 工具系统收口相对独立，收益明确，能降低后续 Agent 改造成本。
- 工作流解耦涉及数据模型和 API，需要在契约稳定后做。
- Beat Plan 最像产品功能，应该建立在稳定工作流之上。

## 五、风险与控制

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| 一次性迁移 Prisma enum 影响历史数据 | 中 | 先 contract 收口，再做数据库 enum 迁移 |
| 前端依赖旧 SSE 字段 | 中 | 保持事件 payload 兼容，新增字段不删除旧字段 |
| WorkflowRun 引入后路径重复 | 中 | 设定明确删除点，质量检查先切，写作任务后切 |
| 工具 capability 命名不稳定 | 低 | 先定义能力域表，再迁移 Agent |
| Beat Plan UI 过重 | 中 | 第一版只做章节目标、节拍列表、确认按钮 |

## 六、完成定义

本轮 2/3/4/5 改造完成时，应满足：

- 核心状态和映射有共享 contract。
- 质量检查不再依赖普通 `WritingTask` 表达执行过程。
- Agent 工具来自 registry capability，而不是手写工具数组。
- Beat Plan 可保存、可确认、可被写作和评审引用。
- 现有五 Agent 功能保持可用。
- `npm run typecheck` 通过，必要时补充契约层单元测试。

