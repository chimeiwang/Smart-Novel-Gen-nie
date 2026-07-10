> 状态：历史归档，不作为当前实现依据。当前事实以 `DOCS.md`、`AGENTS.md`、`src/agents/AGENTS.md`、代码和 schema 为准。

# Phase 0 基线审计报告

## 字段读写清单

### Chapter.status
- 读写点: `actions.ts:123` (setChapterStatusAction), `author-node.ts:61` (自动入库→review)
- 当前值: `"drafting" | "review" | "completed"` (硬编码字符串)
- 问题: 无 Zod enum contract

### ChapterQualityCheck.type/status/qualityGate
- 已由 `quality-check.ts` contract 收口 ✅
- 但 `context-aggregator.ts:541` `upsertWritingConfig` 仍用旧默认值 `"host,writer,validator"` ❌

### WritingTask.phase
- 当前值: `"idle" | "active" | "waiting_call" | "completed" | "error"` (硬编码)
- 问题: 无 Zod enum contract

### 旧 Agent ID 残留
- `context-aggregator.ts:541`: `"host,writer,validator"` 仍为默认 ❌
- `AGENT_ID_TO_KEY` 映射用英文键名（内部使用，可接受）

### 工具系统重叠
- `tools.ts` 5 个手写 `getXxxTools()` 函数仍活跃
- `registry.ts` 已注册 22+5 个工具但 Agent 不使用

### Beat Plan
- Prisma schema 无相关模型
- 仅 `writing-workflow-service.ts` 有 TS 类型

## 本次不处理范围
- checkpoint 持久化
- Prisma enum 物理迁移

## Phase 1 完成标志
- `agent.ts` contract: CoreAgentIdSchema + 默认 Agent + 编解码
- `workflow.ts` contract: Chapter/WritingTask/WritingSession/WorkflowRun 状态枚举
- SSE 类型收紧: agentId/phase/activeAgent 使用派生 schema
- 旧默认值消灭: context-aggregator.ts "host,writer,validator" → "设定,剧情,写作,校验,编辑"

## Phase 4 完成标志
- Prisma 模型: ChapterWritingGoal + ChapterBeatPlan + SceneBeat
- Contract: `beat-plan.ts` (Zod schemas)
- Service: `beat-plan-service.ts` (saveGoal/createPlan/updateStatus/getLatest)
- 前端 UI 不在本次范围（按计划第一版最小化）
