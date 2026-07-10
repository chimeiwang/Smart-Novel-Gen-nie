> 状态：历史归档，不作为当前实现依据。当前事实以 `DOCS.md`、`AGENTS.md`、`src/agents/AGENTS.md`、代码和 schema 为准。

# 字段契约一致性审计

> 审计日期：2026-06-09
>
> 范围：Prisma schema、Server Actions、API route、Agent state/schema/parser、前端组件本地类型。
>
> 结论：当前不是单个字段写错，而是项目缺少统一的“字段契约层”。同一业务对象在数据库、Agent、API、前端之间被多次手写定义，导致字段名、枚举值、状态机和执行语义逐渐漂移。

## 一、为什么同一个项目会出现字段对不上

### 1. Prisma 字段用 `String + 注释` 表达枚举

例如 `Chapter.status`、`ChapterQualityCheck.type/status/qualityGate`、`WritingTask.phase` 都是 `String` 字段，只靠注释描述可选值。

结果是：

- 数据库不会阻止新状态写入。
- TypeScript 无法从 Prisma 自动得到严格联合类型。
- 前端、Action、Agent 服务可以各自发明不同的 union。

典型位置：

- `prisma/schema.prisma:60`：`Chapter.status String // drafting | review | completed`
- `prisma/schema.prisma:78-90`：质量检查类型、状态、门禁都是 `String`
- `prisma/schema.prisma:544`：`WritingTask.phase String`

### 2. DTO 和前端 Props 在多个文件重复手写

质量检查字段至少存在四套定义：

- `prisma/schema.prisma` 的 `ChapterQualityCheck`
- `src/app/workspace/[novelId]/page.tsx` 的 `qualityChecks` 映射类型
- `src/features/workspace/smart-writing-panel.tsx` 的 `qualityChecks` Props
- `src/features/writing/writing-conversation.tsx` 的 `QualityCheckData`

这些定义没有共享类型，也没有 schema 校验，只是字段名碰巧一样。

### 3. Agent 输出契约分成三层，各自维护

Agent 输出目前同时存在：

- TypeScript 接口：`src/agents/graph/state.ts` 的 `AgentOutput` / `AgentUpdates`
- Zod schema：`src/agents/graph/schemas.ts`
- 清洗器：`src/agents/graph/lore-update-schema.ts` 的 `sanitizeAgentUpdates()`
- 执行器：`src/agents/lib/db-operations.ts`

其中最危险的是：类型层允许的字段，不代表解析后能留下，也不代表执行层会处理。

### 4. 旧兼容层仍在承担新架构职责

`src/agents/types.ts` 说数据模型统一从 `state.ts` 导入，但仍保留 `AgentContext`、`NovelWithContext`、`AgentResult`、`OrchestrationEvent` 等旧类型；前端又自己扩展 `ExtendedEvent`。这让“到底谁是 SSE/Agent/上下文契约源头”不清楚。

### 5. API 没有显式请求/响应 schema

例如 `/api/writing/session`、`/api/quality-check/run`、`updateChapterQualityCheckStatusAction()` 都靠手写 body 解构和局部 TS 类型约束。运行时没有统一 Zod schema，前端也没有从同一 schema 推导类型。

## 二、已发现的字段契约不一致案例

### 1. `ChapterQualityCheck.status`：服务端写 `failed`，前端/Action 类型不认

现状：

- Prisma 注释只写：`pending | running | completed | skipped`
- `quality-check-service.ts` 的 `QualityCheckResult.status` 支持 `failed`
- `markCheckFailed()` 会把数据库状态写成 `failed`
- `updateChapterQualityCheckStatusAction()` 的入参不支持 `failed`
- `QualityCheckQueue.onMark()` 也不支持 `failed`

影响：

- 后端可以写出前端动作层不承认的状态。
- UI 很可能只能当普通字符串展示，无法提供一致的操作分支。
- 后续如果加筛选/统计，`failed` 容易漏算。

建议：

- 定义统一 `ChapterQualityCheckStatus = "pending" | "running" | "completed" | "skipped" | "failed"`。
- Prisma 改 enum，或至少在 `src/shared/contracts/quality-check.ts` 中用 Zod enum 作为唯一来源。
- 所有 action、service、frontend props 从该 contract 导入。

### 2. `ChapterQualityCheck.type` 默认项重复定义，顺序和文案不一致

现状：

- `src/app/actions.ts` 定义 `DEFAULT_CHAPTER_QUALITY_CHECKS`
- `src/agents/lib/quality-check-service.ts` 又定义一份 `DEFAULT_CHAPTER_QUALITY_CHECKS`
- `/api/quality-check/run` 又定义一份 `MESSAGE_BY_TYPE`
- 前端 `expectedAgentByType` 又定义一份 type 到 Agent 的映射

影响：

- 新增或改名检查类型时，需要同步改四处。
- 当前 `lore_sync` 曾出现“默认项存在，但 API 不支持/前端单独处理”的分裂。
- 检查类型和负责 Agent 的映射没有一个权威来源。

建议：

- 建一个 `src/shared/contracts/quality-check.ts`：
  - `QualityCheckTypeSchema`
  - `QUALITY_CHECK_DEFINITIONS`
  - `QUALITY_CHECK_AGENT_MAP`
  - `QUALITY_CHECK_MESSAGE_MAP`
- `actions.ts`、`quality-check-service.ts`、`quality-check/run/route.ts`、前端队列全部引用同一份定义。

### 3. 质量检查服务端化 API 没有接到前端

现状：

- 已有 `/api/quality-check/run`
- 前端 `runQualityCheck()` 仍直接调用 `updateChapterQualityCheckStatusAction()` 标记 running
- 随后仍走 `/api/writing/session` 或 `/api/writing/resume`
- 前端还通过 `saveActiveQualityCheckResult()` 基于 SSE 的 `agent_done` 保存检查结果

影响：

- 服务端保存路径和前端保存路径并存，字段归一化规则会分裂。
- 后端 `qualityGate` 推断、前端 `normalizeQualityScores()` 可能产生不同结果。
- 一个检查结果可能被服务端和前端先后覆盖。

建议：

- 前端运行检查统一调用 `/api/quality-check/run`。
- 前端不再直接写 `result/scores/qualityGate/rewriteBrief`，只负责刷新。
- `updateChapterQualityCheckStatusAction()` 只保留人工标记 `skipped/pending`，并加鉴权。

### 4. `AgentUpdates` 类型允许的字段会被 `sanitizeAgentUpdates()` 丢弃

现状：

`src/agents/graph/state.ts` 的 `AgentUpdates` 包含：

- `outline`
- `outlineAdjustments`
- `foreshadowing`
- `references`
- `worldSetting`
- `storyBackground`

`src/agents/graph/schemas.ts` 的 `AgentUpdatesSchema` 也定义了这些字段。

但 `src/agents/graph/lore-update-schema.ts` 的 `sanitizeAgentUpdates()` 只保留：

- `characters`
- `locations`
- `items`
- `factions`
- `glossaries`
- `characterExperiences`
- `worldSetting`
- `storyBackground`

它没有保留：

- `outline`
- `outlineAdjustments`
- `foreshadowing`
- `references`

而 `parseAgentResponse()`、`parseValidatorResponse()`、`parseEditorResponse()` 都调用这个 sanitizer。

影响：

- 剧情 Agent 或 proposal 工具生成的大纲/伏笔/参考资料 updates，会在解析阶段被静默丢弃。
- 用户看到的可能只是文字建议，保存链路不会触发对应变更。
- 这解释了“字段看似存在、实际前后端对不上”的核心体验。

建议：

- 把 `lore-update-schema.ts` 改名并拆分：
  - `agent-updates.contract.ts`：定义完整 `AgentUpdatesSchema`
  - `agent-updates-sanitizer.ts`：从 schema 推导清洗，不再手写字段白名单
- 如果某 Agent 只允许设定更新，应在 AgentDefinition 里声明 `allowedUpdateSections`，而不是用全局 sanitizer 丢字段。

### 5. 伏笔 updates：类型允许 `update`，执行层没有实现

现状：

- `ForeshadowingUpdate.action` 支持 `"create" | "update" | "payoff" | "abandon"`
- `AgentUpdatesSchema.foreshadowing.action` 也允许 `update`
- `executeUpdates()` 的伏笔分支只处理：
  - `create`
  - `payoff`
  - `abandon`

影响：

- Agent 输出 `{"action": "update"}` 会通过类型层，但执行层无效果。
- 用户确认保存后可能显示成功摘要不符合预期，或者没有任何保存。

建议：

- 要么实现 `update`，支持 `plantedContent/expectedPayoff/plantedAt/payoffAt/status`。
- 要么从 `ForeshadowingUpdate` 和 Zod schema 中移除 `update`。
- 文档和 prompt 也必须同步。

### 6. 伏笔回收字段：proposal 输出 `payoffNote`，数据库执行不接

现状：

- `propose_resolve_foreshadowing` 输出：
  - `payoffNote`
- Prisma `Foreshadowing` 没有 `payoffNote` 字段，只有：
  - `payoffAt`
  - `expectedPayoff`
  - `status`
- `executeUpdates()` 在 payoff 时写：
  - `status: "paid_off"`
  - `payoffAt: f.plantedAt ?? null`

影响：

- Agent 给出的回收说明会被丢弃。
- `payoffAt` 还错误复用了 `plantedAt`，语义不清。

建议：

- 明确回收契约：
  - 如果只记录位置：使用 `payoffAt`
  - 如果要记录说明：Prisma 新增 `payoffNote String?`
- proposal、state type、Zod schema、executeUpdates 同步使用同一字段。

### 7. 大纲 proposal：`nodeId` 填标题，执行层按 ID 查找

现状：

- `propose_update_outline` 的入参是 `node_title`
- 输出模板把 `nodeId` 设置为 `args.node_title`
- `executeUpdates()` 对 `outlineAdjustments.update` 使用 `findUnique({ id: adj.nodeId })`

影响：

- 如果 Agent 按模板输出，`nodeId` 实际是标题，不是数据库 ID。
- 更新会找不到记录，或者静默无效果。

建议：

- proposal 工具必须先通过标题查找节点，返回真实 `nodeId`。
- 如果只知道标题，updates 应使用 `title` 定位，执行层走 `findFirst({ novelId, title contains ... })`。
- 字段名不要误导：标题就叫 `nodeTitle`，ID 才叫 `nodeId`。

### 8. 大纲字数字段：proposal 输出 `estimatedWordCount`，类型/执行层不接

现状：

- Prisma `OutlineNode` 有 `estimatedWordCount` 和 `actualWordCount`
- `propose_update_outline` 支持 `estimated_word_count`，输出 `estimatedWordCount`
- `OutlineAdjustment` 类型没有 `estimatedWordCount`
- `executeUpdates().outlineAdjustments` create/update 都没有写 `estimatedWordCount`

影响：

- Agent 生成的预估字数无法保存。

建议：

- 在 `OutlineAdjustment`、Zod schema、executeUpdates 中补齐 `estimatedWordCount`。
- 或从 proposal 工具移除这个字段。

### 9. `selectedAgents`：前端是数组，数据库是字符串，Graph 不使用

现状：

- 前端传 `selectedAgents: AgentId[]`
- `WritingTask.selectedAgents` 是逗号分隔字符串
- `createInitialState()` 会保存筛选后的字符串
- `GraphState` 没有 `selectedAgents`
- 路由和 `wantsToCall` 不读取 `selectedAgents`

影响：

- 用户选择/取消 Agent 只是被记录，不会真正限制执行。
- 前端选择控件和后端行为语义不一致。

建议：

- 如果要保留选择功能：
  - `GraphState` 增加 `enabledAgents: CoreAgentId[]`
  - `routeAfterInit()` 和 `routeAfterProcess()` 必须校验目标 Agent 是否启用
  - DB 存 JSON，不要用逗号字符串
- 如果暂时不做，就移除 UI/参数，避免假能力。

### 10. `QualityCheckData` 和 `qualityGate` 前端类型过宽

现状：

- 前端 `QualityCheckData.type/status/qualityGate` 都是 `string`
- Agent 和 service 中 `qualityGate` 是 `"pass" | "revise" | "rewrite"`
- 质量检查状态实际还出现 `failed`

影响：

- 前端无法在编译期发现新增状态未处理。
- CSS class 直接拼 `qualityGate`，未知值会进入 UI。

建议：

- 前端从共享 contract 导入：
  - `QualityCheckType`
  - `QualityCheckStatus`
  - `QualityGate`
- 所有外部数据进入组件前用 Zod parse。

### 11. `NovelWithContext` 与 `NovelData` 仍不是同一个类型

现状：

- `state.ts` 的 `NovelData.novelId/chapterId` 是必填
- `types.ts` 的 `NovelWithContext.novelId/chapterId` 是可选
- `aggregateNovelContextLightweight()` 返回 `Promise<NovelWithContext>`，后续又 cast 成 `WritingState["novelData"]`

影响：

- 聚合函数无法保证返回值满足 Graph state。
- 只能靠 `as WritingState["novelData"]` 绕过类型系统。

建议：

- `aggregateNovelContextLightweight()` 直接返回 `NovelData`。
- 删除或收敛 `NovelWithContext`，不要保留“别名但字段可选”的旧类型。

## 三、避免复发的工程规则

### 规则 1：为每个跨层对象建立唯一 contract 文件

建议目录：

```text
src/shared/contracts/
├── chapter.ts
├── quality-check.ts
├── writing-task.ts
├── agent-output.ts
├── agent-updates.ts
└── sse-events.ts
```

每个 contract 文件同时导出：

- Zod schema
- TypeScript type
- 默认值/映射表
- parser/normalizer

示例：

```ts
export const QualityGateSchema = z.enum(["pass", "revise", "rewrite"]);
export type QualityGate = z.infer<typeof QualityGateSchema>;

export const QualityCheckStatusSchema = z.enum([
  "pending",
  "running",
  "completed",
  "skipped",
  "failed",
]);
export type QualityCheckStatus = z.infer<typeof QualityCheckStatusSchema>;
```

### 规则 2：禁止在组件里重新声明后端 DTO

禁止：

```ts
type QualityCheckData = {
  id: string;
  type: string;
  status: string;
};
```

改为：

```ts
import type { QualityCheckDto } from "@/shared/contracts/quality-check";
```

页面从 Prisma 读出的数据先转换成 DTO，再传给 client component。

### 规则 3：所有 API route 和 server action 都必须有 input schema

请求体、server action 入参不要只靠 TS 类型。必须在入口处 parse：

```ts
const input = RunQualityCheckInputSchema.parse(await request.json());
```

server action 同理：

```ts
const input = UpdateQualityCheckInputSchema.parse(rawInput);
```

### 规则 4：Agent 输出 schema、sanitizer、executeUpdates 必须同源

不要再维护三份字段列表：

- `AgentUpdates` interface
- `AgentUpdatesSchema`
- `sanitizeAgentUpdates()`
- `executeUpdates()` 分支

建议以 Zod schema 为源头：

- `AgentUpdatesSchema` 定义允许字段
- `sanitizeAgentUpdates()` 只做 `AgentUpdatesSchema.safeParse()`
- `executeUpdates()` 的每个分支只接收 schema parse 后的数据
- 每个 update section 有一组 contract test 覆盖“schema 允许的 action 必须被执行层处理”

### 规则 5：字段命名必须表达真实语义

禁止把标题塞进 ID 字段：

- 错：`nodeId: args.node_title`
- 对：`nodeTitle: args.node_title`

如果执行层需要 ID，工具层必须先查出真实 ID。

### 规则 6：数据库枚举优先用 Prisma enum

建议改造：

- `Chapter.status` -> `ChapterStatus`
- `ChapterQualityCheck.type` -> `ChapterQualityCheckType`
- `ChapterQualityCheck.status` -> `ChapterQualityCheckStatus`
- `ChapterQualityCheck.qualityGate` -> `QualityGate?`
- `WritingTask.phase` -> `WritingTaskPhase`

如果短期不想迁移数据库，至少用 Zod enum 作为应用层唯一入口。

### 规则 7：禁止 `as unknown as` 穿透跨层对象

出现以下写法时，要视为 contract 缺失：

```ts
as unknown as WritingState
as WritingState["novelData"]
as Record<string, unknown>
```

合理例外只能出现在 adapter 层，并且 adapter 必须有 Zod parse 或明确转换函数。

### 规则 8：为 contract 增加类型级和运行时测试

最低测试集：

1. `AgentUpdatesSchema` 允许的所有 section，`sanitizeAgentUpdates()` 都不会丢。
2. `AgentUpdatesSchema` 允许的所有 action，`executeUpdates()` 都有分支处理。
3. `QUALITY_CHECK_DEFINITIONS` 的每个 type：
   - 有标题/摘要
   - 有负责 Agent
   - 有运行消息
   - 前端可渲染
4. SSE 事件 union 中每个事件都能被前端 `processStream` 处理，或明确忽略。

## 四、建议修复优先级

### P0：先修会导致功能静默失效的契约

1. `sanitizeAgentUpdates()` 不再丢 `outline/outlineAdjustments/foreshadowing/references`。
2. `ForeshadowingUpdate.update` 要么实现，要么从 schema/type 删除。
3. `propose_update_outline` 不再把标题塞进 `nodeId`。
4. 质量检查 status 统一补上 `failed`。

### P1：收敛重复定义

1. 建 `src/shared/contracts/quality-check.ts`。
2. 建 `src/shared/contracts/agent-updates.ts`。
3. 前端删除本地 `QualityCheckData` / `QualityScores` 重复定义。
4. `/api/quality-check/run`、前端队列、service 共用同一份 `QUALITY_CHECK_DEFINITIONS`。

### P2：数据库层类型化

1. 把 String 状态字段逐步迁移成 Prisma enum。
2. `WritingTask.selectedAgents` 从逗号字符串改 JSON，或删除该功能。
3. `aggregateNovelContextLightweight()` 返回 `NovelData`，移除 `NovelWithContext` 的可选差异。

## 五、验收标准

完成后应满足：

- 前端不再手写后端 DTO。
- 任意新增质量检查类型，只需要改一个 contract 文件。
- 任意新增 Agent update section，schema、sanitizer、executeUpdates、prompt 必须同 PR 同步。
- `npm run typecheck` 能在字段改名时暴露所有受影响位置。
- contract test 能发现“schema 允许但执行层不处理”的字段。
- 不再出现“保存成功但字段被静默丢弃”的路径。
