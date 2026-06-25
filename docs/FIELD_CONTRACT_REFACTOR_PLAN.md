# 字段契约一致性改造计划

> 创建日期：2026-06-09
>
> 依据：`docs/FIELD_CONTRACT_AUDIT.md`
>
> 目标：消除 Prisma、Server Actions、API、Agent、前端之间的字段契约漂移，让同一业务对象只有一个字段来源，避免“类型允许、解析丢弃、执行无效、前端不认”的问题。

## 一、改造原则

### 1. Contract 优先

所有跨层对象必须先定义 contract，再接入业务代码。

Contract 包含：

- Zod schema
- TypeScript type
- 默认配置/映射表
- DTO 转换函数
- 运行时 parser

### 2. 不在组件里手写后端 DTO

前端组件只导入共享 DTO 类型，不再手写 `QualityCheckData`、`QualityScores`、SSE event union 等跨层类型。

### 3. Zod schema 是运行时入口

API route、server action、Agent 输出解析都必须 `parse/safeParse`。TypeScript 类型只能做编译期约束，不能替代运行时校验。

### 4. schema、sanitizer、execute 必须同源

Agent updates 不能再出现：

- TypeScript 允许
- Zod 允许
- sanitizer 丢弃
- executeUpdates 不处理

### 5. 先不做 checkpoint 持久化

本计划不包含 LangGraph checkpoint 持久化改造。

## 二、目标目录结构

新增共享契约目录：

```text
src/shared/contracts/
├── agent-updates.ts
├── quality-check.ts
├── sse-events.ts
├── writing-task.ts
└── novel-context.ts
```

推荐职责：

| 文件 | 职责 |
| --- | --- |
| `quality-check.ts` | 质量检查 type/status/gate、默认检查项、负责 Agent、运行消息、DTO schema |
| `agent-updates.ts` | Agent updates 完整 schema、类型、sanitize、section/action 定义 |
| `sse-events.ts` | SSE 事件 schema/type，前端 `processStream` 使用 |
| `writing-task.ts` | WritingTask phase、selectedAgents 编解码 |
| `novel-context.ts` | `NovelData`/聚合上下文 DTO schema 与转换 |

## 三、阶段计划

## Phase 0：基线与防回归准备

目标：先建立可验证基线，避免后续改造过程中不知道是否修坏。

### 任务

1. 运行并记录当前状态：
   - `npm run typecheck`
   - `npm run lint`
2. 记录当前 lint 已知问题，避免和本计划混淆。
3. 新增最小测试目录：
   - `src/shared/contracts/__tests__/`
   - 或项目现有测试目录，如没有测试框架，则先创建可用的纯 TypeScript contract check 脚本。
4. 建立字段契约回归清单：
   - 质量检查四种 type 都能找到定义、Agent、运行消息。
   - AgentUpdates schema 允许的 section 不会被 sanitizer 丢弃。
   - AgentUpdates schema 允许的 action 在 executeUpdates 有处理分支。

### 验收

- `npm run typecheck` 通过。
- 本阶段不要求修复现有 lint，但必须记录现有 lint 失败位置。
- 有一份可重复执行的 contract 检查入口。

## Phase 1：质量检查契约统一

目标：先修最明显的前后端字段重复和状态分裂。

### 任务 1：新增 `quality-check.ts`

新增文件：

```text
src/shared/contracts/quality-check.ts
```

应导出：

```ts
export const QualityCheckTypeSchema = z.enum([
  "consistency",
  "lore_sync",
  "editorial",
  "craft",
]);
export type QualityCheckType = z.infer<typeof QualityCheckTypeSchema>;

export const QualityCheckStatusSchema = z.enum([
  "pending",
  "running",
  "completed",
  "skipped",
  "failed",
]);
export type QualityCheckStatus = z.infer<typeof QualityCheckStatusSchema>;

export const QualityGateSchema = z.enum(["pass", "revise", "rewrite"]);
export type QualityGate = z.infer<typeof QualityGateSchema>;
```

并导出：

- `QualityScoresSchema`
- `QualityCheckDtoSchema`
- `QualityCheckDto`
- `QUALITY_CHECK_DEFINITIONS`
- `QUALITY_CHECK_AGENT_MAP`
- `QUALITY_CHECK_MESSAGE_MAP`
- `normalizeQualityScores()`
- `toQualityCheckDto()`

### 任务 2：替换重复定义

替换以下位置：

- `src/app/actions.ts` 中的 `DEFAULT_CHAPTER_QUALITY_CHECKS`
- `src/agents/lib/quality-check-service.ts` 中的 `DEFAULT_CHAPTER_QUALITY_CHECKS`、`CHECK_TYPE_TO_AGENT`
- `src/app/api/quality-check/run/route.ts` 中的 `MESSAGE_BY_TYPE`
- `src/features/writing/writing-conversation.tsx` 中的 `QualityCheckData`、`QualityScores`、`expectedAgentByType`
- `src/features/workspace/smart-writing-panel.tsx` 中手写的 `qualityChecks` Props
- `src/app/workspace/[novelId]/page.tsx` 中手写的 `qualityChecks` 映射类型

### 任务 3：前端运行检查改走统一 API

修改 `runQualityCheck()`：

- 不再直接发送 `@校验/@编辑/@设定` 到 `/api/writing/session`。
- 调用 `/api/quality-check/run`。
- 请求体只传：
  - `checkId`
  - 可选 `taskId`
  - 可选 `message`
- 前端只处理 SSE 和刷新，不再保存 Agent 结果。

### 任务 4：收窄 server action

调整 `updateChapterQualityCheckStatusAction()`：

- 入参使用共享 schema。
- 只允许人工状态变更：
  - `pending`
  - `skipped`
  - 可选 `completed`，但不带 result/scores。
- 不再负责保存 `result/scores/qualityGate/rewriteBrief`。
- 必须校验登录和 `chapter.novel.userId`。

### 验收

- `QUALITY_CHECK_DEFINITIONS` 是默认检查项唯一来源。
- 任意新增一个检查 type，只需要改 `quality-check.ts`。
- 前端没有本地手写 `QualityCheckData` / `QualityScores`。
- `/api/quality-check/run` 是质量检查运行的唯一入口。
- `failed` 状态能被前端识别和展示。

## Phase 2：AgentUpdates 契约统一

目标：解决“字段存在但解析阶段被静默丢弃”的核心问题。

### 任务 1：新增 `agent-updates.ts`

新增文件：

```text
src/shared/contracts/agent-updates.ts
```

应导出：

- `FieldChangeSchema`
- `CharacterAdjustmentSchema`
- `LocationAdjustmentSchema`
- `ItemAdjustmentSchema`
- `FactionAdjustmentSchema`
- `GlossaryAdjustmentSchema`
- `CharacterExperienceAdjustmentSchema`
- `OutlineUpdateSchema`
- `OutlineAdjustmentSchema`
- `ForeshadowingUpdateSchema`
- `ReferenceAdjustmentSchema`
- `AgentUpdatesSchema`
- `AgentUpdates`
- `sanitizeAgentUpdates(raw, options?)`
- `hasAgentUpdates(updates)`

### 任务 2：完整保留所有 section

`sanitizeAgentUpdates()` 必须支持并保留：

- `characters`
- `locations`
- `items`
- `factions`
- `glossaries`
- `characterExperiences`
- `outline`
- `outlineAdjustments`
- `foreshadowing`
- `references`
- `worldSetting`
- `storyBackground`

### 任务 3：替换旧 sanitizer

替换以下引用：

- `src/agents/graph/response-parser.ts`
- `src/agents/graph/graph-definition.ts`
- `src/agents/lib/db-operations.ts`
- `src/agents/types.ts`
- `src/agents/graph/state.ts`

旧文件 `src/agents/graph/lore-update-schema.ts` 的处理：

- 保留 `LORE_UPDATE_SCHEMA_PROMPT` 可以先不动。
- `hasAgentUpdates()` 和 `sanitizeAgentUpdates()` 从新 contract re-export。
- 文件名后续再改，避免一次性影响过大。

### 任务 4：AgentDefinition 增加允许更新范围

在 `src/agents/runtime/agent-definition.ts` 增加：

```ts
allowedUpdateSections?: AgentUpdateSection[];
```

用途：

- 设定 Agent：允许 `characters/locations/items/factions/glossaries/characterExperiences/worldSetting/storyBackground`
- 剧情 Agent：允许 `outline/outlineAdjustments/foreshadowing`
- 编辑/校验 Agent：默认不允许写 updates，除非明确打开

解析时按 AgentDefinition 过滤，而不是全局丢字段。

### 验收

- 剧情 Agent 输出 `outlineAdjustments` 不再被 sanitizer 丢弃。
- 伏笔 proposal 输出 `foreshadowing` 不再被 sanitizer 丢弃。
- contract test 覆盖所有 update section。
- 所有旧 `sanitizeAgentUpdates()` 调用都来自共享 contract。

## Phase 3：修复 AgentUpdates 执行语义

目标：让 schema 允许的字段在执行层有明确结果。

### 任务 1：伏笔契约修复

统一 `ForeshadowingUpdate`。

建议字段：

```ts
{
  action: "create" | "update" | "payoff" | "abandon";
  id?: string;
  name: string;
  plantedAt?: string;
  plantedContent?: string;
  expectedPayoff?: string;
  payoffAt?: string;
  payoffNote?: string;
}
```

执行层必须：

- 实现 `update`
- `payoff` 使用 `payoffAt`，不要复用 `plantedAt`
- 如果保留 `payoffNote`，Prisma 需要新增字段；如果不新增，则 proposal 不得输出 `payoffNote`

推荐做法：

- 短期：移除 `payoffNote`，只保留 `payoffAt`
- 中期：如果产品确实要回收说明，再加 Prisma 字段

### 任务 2：大纲契约修复

统一 `OutlineAdjustment`。

建议字段：

```ts
{
  action: "create" | "update" | "delete";
  nodeId?: string;
  nodeTitle?: string;
  title?: string;
  content?: string;
  parentId?: string;
  status?: "planned" | "in_progress" | "completed" | "skipped";
  estimatedWordCount?: number;
  actualWordCount?: number;
}
```

执行层规则：

- 有 `nodeId`：按 `id + novelId` 定位。
- 无 `nodeId` 且有 `nodeTitle/title`：按 `novelId + title contains` 定位。
- `estimatedWordCount` 和 `actualWordCount` 都必须支持保存。

### 任务 3：proposal 工具修复

修改 `src/agents/tools/proposals/update-proposal-tools.ts`：

- `propose_update_outline` 不得把标题塞进 `nodeId`。
- 如果工具能查到大纲节点，返回真实 `nodeId`。
- 查不到时输出 `nodeTitle`，由执行层按标题定位。
- `propose_resolve_foreshadowing` 使用契约允许字段。

### 任务 4：执行层限域顺手补齐

虽然本计划重点是字段契约，但执行 updates 时必须按 `task.novelId` 限域，否则 contract 修好后仍可能跨小说误写。

`executeUpdates()` 中所有按 id 查询实体的位置，都改为：

- `findFirst({ where: { id, novelId: task.novelId } })`
- 子表通过关联对象校验归属

### 验收

- `ForeshadowingUpdateSchema` 允许的 action 在 `executeUpdates()` 都有分支。
- `OutlineAdjustmentSchema` 允许的字段都能被保存。
- proposal 工具输出的模板能被 schema parse，并能被执行层处理。
- 不再出现标题写入 `nodeId` 的情况。

## Phase 4：SSE 和前端事件契约统一

目标：让后端 SSE 事件和前端 `processStream` 使用同一 union。

### 任务 1：新增 `sse-events.ts`

新增文件：

```text
src/shared/contracts/sse-events.ts
```

至少定义：

- `StartEventSchema`
- `DoneEventSchema`
- `ErrorEventSchema`
- `ResumeEventSchema`
- `AgentStatusEventSchema`
- `AgentDoneEventSchema`
- `UserInputRequiredEventSchema`
- `UpdatesSavedEventSchema`
- `UpdatesDeclinedEventSchema`
- `StateUpdateEventSchema`
- `WritingSseEventSchema`
- `WritingSseEvent`

### 任务 2：后端事件发送使用 helper

在 `sse-adapter.ts` 中统一使用 builder：

```ts
sendWritingEvent(sendEvent, { type: "agent_done", ...payload });
```

builder 内部做 Zod 校验或开发环境校验。

### 任务 3：前端删除 `ExtendedEvent`

`writing-conversation.tsx` 导入：

```ts
import type { WritingSseEvent } from "@/shared/contracts/sse-events";
```

`processStream` 里对 JSON 先 parse：

```ts
const event = WritingSseEventSchema.safeParse(parsed);
```

### 验收

- 前端不再本地声明 `ExtendedEvent`。
- 后端新增 SSE 类型时，前端类型能同步感知。
- 未识别事件有明确日志，不会误当成有效事件。

## Phase 5：NovelData / 聚合上下文契约统一

目标：消除 `NovelWithContext` 和 `NovelData` 的可选字段差异。

### 任务 1：新增 `novel-context.ts`

定义：

- `NovelContextSchema`
- `NovelContext`
- `toNovelContext(prismaResult, chapter)`

### 任务 2：修改聚合函数返回类型

修改：

```text
src/shared/lib/context-aggregator.ts
```

要求：

- `aggregateNovelContext()`
- `aggregateNovelContextLightweight()`

都直接返回 `NovelData` 或新的 `NovelContext`。

不允许再返回 `NovelWithContext` 后强转成 `WritingState["novelData"]`。

### 任务 3：删除或收敛旧类型

处理：

- `src/agents/types.ts` 的 `NovelWithContext`
- `src/agents/types.ts` 的旧 `AgentContext`

如果仍需兼容，必须是 type alias：

```ts
export type NovelWithContext = NovelContext;
```

不能重新声明字段。

### 验收

- `aggregateNovelContextLightweight()` 不再需要 `as WritingState["novelData"]`。
- `NovelData.novelId/chapterId` 在聚合函数返回值中必填。
- `types.ts` 不再有一套字段不同的上下文类型。

## Phase 6：WritingTask 与 selectedAgents 契约统一

目标：解决前端传数组、DB 存字符串、Graph 不使用的问题。

### 决策点

二选一：

1. 保留 Agent 选择能力。
2. 删除 Agent 选择能力，只使用 `@Agent` 和智能路由。

### 方案 A：保留 Agent 选择

任务：

- 新增 `src/shared/contracts/writing-task.ts`
- 定义 `SelectedAgentsSchema = z.array(CoreAgentIdSchema)`
- DB 暂时仍存逗号字符串，但所有读写必须经过：
  - `encodeSelectedAgents()`
  - `decodeSelectedAgents()`
- `GraphState` 增加 `enabledAgents: CoreAgentId[]`
- `routeAfterInit()` 和 `routeAfterProcess()` 过滤未启用 Agent

验收：

- 用户取消某 Agent 后，系统不会路由或链式调用它。
- 状态报告只展示启用 Agent。

### 方案 B：删除 Agent 选择

任务：

- 移除前端 `selectedAgents` UI 状态。
- `/api/writing/session` 不再接收 `selectedAgents`。
- `WritingTask.selectedAgents` 固定写 `CORE_AGENT_IDS` 或保留历史字段但不展示。
- 删除 `validateAgentSelection()` 等旧逻辑。

验收：

- 前端不再呈现“可以选择 Agent”的假能力。
- Graph 行为和 UI 语义一致。

## Phase 7：Prisma enum 与迁移

目标：从数据库层阻止非法状态。

### 任务

把以下 String 状态迁移成 Prisma enum：

- `Chapter.status`
- `ChapterQualityCheck.type`
- `ChapterQualityCheck.status`
- `ChapterQualityCheck.qualityGate`
- `WritingTask.phase`

示例：

```prisma
enum ChapterQualityCheckStatus {
  pending
  running
  completed
  skipped
  failed
}
```

### 注意

- 本项目同时有 `schema.prisma` 和 `schema.postgres.prisma`，两个文件必须同步。
- 迁移前先确认现有数据是否存在未知字符串。
- 如果当前阶段不想动数据库，至少保留应用层 Zod enum，Prisma enum 可放到后续。

### 验收

- 两份 Prisma schema 同步。
- `npm run db:generate` 成功。
- `npm run typecheck` 成功。
- 现有数据迁移脚本能处理旧字符串。

## Phase 8：Contract 测试与 CI 门禁

目标：防止字段契约再次漂移。

### 测试 1：质量检查定义完整性

检查：

- 每个 `QualityCheckType` 都有 definition。
- 每个 type 都有负责 Agent。
- 每个 type 都有运行 message。
- 前端 DTO schema 能 parse 页面传入数据。

### 测试 2：AgentUpdates section 不丢失

构造包含所有 section 的 updates，经过 `sanitizeAgentUpdates()` 后仍保留。

### 测试 3：AgentUpdates action 覆盖

对每个 section/action 建覆盖表。

最低要求：

```text
schema 允许的 action 必须在 executeUpdates 有处理分支。
```

### 测试 4：proposal 模板可执行

对每个 proposal 工具：

1. 调用 executor 得到模板。
2. 取出 `updatesTemplate`。
3. 用 `AgentUpdatesSchema` parse。
4. 确认执行层支持对应 section/action。

### 测试 5：SSE event parse

后端常见事件样例必须能被 `WritingSseEventSchema` parse。

### 验收

- CI 至少运行：
  - `npm run typecheck`
  - contract test
- 字段新增但未同步 contract/test 时，CI 失败。

## 四、推荐执行顺序

按以下顺序给其他 AI 执行：

1. Phase 1：质量检查契约统一
2. Phase 2：AgentUpdates 契约统一
3. Phase 3：AgentUpdates 执行语义修复
4. Phase 4：SSE 事件契约统一
5. Phase 5：NovelData 聚合上下文统一
6. Phase 6：selectedAgents 决策与处理
7. Phase 7：Prisma enum 迁移
8. Phase 8：Contract 测试与 CI

其中 Phase 1-3 是最优先，因为它们已经导致功能行为不一致或静默丢字段。

## 五、每阶段交付格式

每个阶段完成后，执行者必须提交：

```text
完成阶段：
修改文件：
删除/废弃的重复类型：
新增 contract：
新增测试：
验证命令：
遗留问题：
```

## 六、最终验收标准

完成全部改造后应满足：

- `QualityCheckData`、`QualityScores` 不再在前端组件内重复声明。
- `AgentUpdates` 只有一个 Zod schema 来源。
- `sanitizeAgentUpdates()` 不会丢 schema 允许的字段。
- `executeUpdates()` 覆盖 schema 允许的所有 action。
- proposal 工具输出的 updates 模板能被 schema parse 并被执行层处理。
- SSE 事件类型由共享 contract 驱动。
- 聚合上下文不再通过 `as WritingState["novelData"]` 强转。
- `selectedAgents` 要么真实生效，要么从 UI/API 中移除。
- `npm run typecheck` 通过。
- contract tests 通过。
