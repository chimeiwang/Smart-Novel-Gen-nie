> 状态：历史归档，不作为当前实现依据。当前事实以 `DOCS.md`、`AGENTS.md`、`src/agents/AGENTS.md`、代码和 schema 为准。

# 待审核中间层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入一个持久化、可复审、可硬删除、覆盖小说创作产物的待审核中间层，让 Agent 可以围绕同一个草案自动评审和返工，最终只在用户确认后写入正式库。

**Architecture:** 新增通用 `ReviewArtifact` 层，作为 Agent 产物和正式数据库之间的唯一待审核对象。`propose_updates` 不再直接等价于“请求用户保存”，而是先生成或更新 Artifact；评审、返工、用户确认、正式落库都围绕 Artifact ID 和版本号进行。正式小说上下文和待审核草案上下文严格分层，Agent 只能在当前流程或显式工具中读取草案，并且必须标识为“待审核草案”。

**Tech Stack:** Next.js 16 App Router、TypeScript、Prisma、PostgreSQL、LangGraph StateGraph、OpenAI tool calls、SSE、Node test runner。

---

## 当前代码结论

1. 现有 `propose_updates` 语义过重：它同时代表“Agent 生成变更”和“立刻进入用户确认保存”。入口在 `src/shared/contracts/agent-control.ts`，处理在 `src/agents/graph/control-event-processor.ts`。
2. `control-event-router.ts` 把 `propose_updates`、`route_to_agent`、`request_revision` 都当成路由事件，只处理第一个。日志里剧情顾问先 `propose_updates` 再 `route_to_agent(编辑)`，后者被忽略，所以循环断掉。
3. `submit_evaluation` 当前只发 SSE 和日志，不写入任何可复审对象；`request_revision` 也只把 brief 塞进对话历史，没有版本化草案。
4. `WritingTask.pendingUpdates` 不存在持久字段，`WritingTask` 只保存任务状态和少量历史 JSON，不适合作为通用草案层。
5. `ChapterBeatPlan` 有 draft/reviewing/approved 状态，但只覆盖章节节拍，不能覆盖角色、设定、大纲、伏笔、参考资料、正文草稿等通用产物。
6. `WorkflowRun/WorkflowStep` 适合记录运行轨迹，不适合作为被审核和可应用的业务产物。
7. 前端 `src/features/writing/writing-conversation.tsx` 只认识 `pendingUpdates` 卡片和 `updates_saved/updates_declined`，没有持久 Artifact 的加载、版本、评审、硬删除和应用动作。
8. `aggregateNovelContextLightweight()` 和现有读工具只读取正式库；如果直接把草案混进去，会让 Agent 把待审核内容误当成已生效事实。

## 设计边界

- 第一期不实现通用工作流 DSL。循环由 LangGraph 状态、control tools 和 Artifact 服务承接，不再给每个场景补一个手写流程。
- 第一期优先迁移 `AgentUpdates` 覆盖的正式落库范围：角色、地点、物品、势力、术语、角色经历、大纲状态、大纲节点、伏笔、参考资料、世界设定、故事背景。
- 正文草稿和 Beat Plan 预留同一 Artifact 形态，但不在第一期替换 `acceptGeneratedContentAction()` 和 `ChapterBeatPlan` 的既有正式入口。
- 用户选择丢弃时对 Artifact、Revision、Evaluation 做硬删除；不保留“discarded”数据库终态，避免废弃草案长期污染查询。
- Artifact 未进入 `applied` 前，绝不写入正式小说表。
- Agent 读取草案时必须通过专门工具或当前 Graph state，不得默认进入正式上下文。

## 状态模型

只允许以下 Artifact 状态：

- `draft`: Agent 已创建或修改草案，尚未进入评审。
- `under_review`: 草案正在由指定 reviewer Agent 审核。
- `awaiting_user`: reviewer 已通过，等待用户确认应用或硬删除。
- `applying`: 用户已确认，服务端正在执行正式落库。这个状态只能短暂存在，用于幂等保护。
- `applied`: 已成功写入正式库。保留用于审计和展示“已应用来源”。

禁止新增 `cancelled`、`rejected`、`blocked`、`superseded` 等容易和硬删除、返工、版本覆盖混淆的状态。返工不是状态，而是新增 revision 和 evaluation。

## 文件结构

- Create `src/shared/contracts/review-artifact.ts`: Artifact kind、status、payload、SSE payload、服务端动作 schema 的唯一类型来源。
- Create `src/agents/artifacts/artifact-service.ts`: create/update/list/get/submitEvaluation/markReviewing/awaitUser/apply/deleteHard 的业务服务。
- Create `src/agents/artifacts/artifact-diff.ts`: 从 `control-event-processor.ts` 抽出 `buildUpdateDiffs()`、字段标签和实体比对。
- Create `src/agents/artifacts/artifact-apply.ts`: 根据 artifact kind 执行正式落库。第一期实现 `agent_updates` 调 `executeUpdates()`。
- Create `src/agents/tools/read/artifact-tools.ts`: Agent 读取当前草案和历史 revision/evaluation 的 read tools。
- Modify `prisma/schema.prisma`: 增加 `ReviewArtifact`、`ReviewArtifactRevision`、`ReviewArtifactEvaluation`，并补 Novel/Chapter/WritingTask/WorkflowRun 关系。
- Modify `src/shared/contracts/agent-control.ts`: 增加 `submit_artifact` 或扩展 `propose_updates` 的 artifact 字段；增加 evaluation 和 revision 对 artifactId 的强绑定。
- Modify `src/agents/tools/control/control-tools.ts`: 注册新 control tool，更新工具描述，明确多 Agent 复审必须使用 Artifact。
- Modify `src/agents/graph/state.ts`: 增加 `activeArtifactId`、`artifactMode`、`reviewerAgent`、`reviserAgent`、`artifactIteration`、`maxArtifactIterations`。
- Modify `src/agents/graph/graph-definition.ts`: 在 `processResultNode` 中让 Artifact control events 先生成/更新 Artifact，再按评审结果路由。
- Modify `src/agents/graph/control-event-router.ts`: `propose_updates/submit_artifact` 不再作为互斥 route event；同轮可以先提交 Artifact，再路由 reviewer。
- Modify `src/agents/graph/control-event-processor.ts`: 删除直接 interrupt 保存逻辑，改为 Artifact 服务驱动。
- Modify `src/agents/graph/workflow-runner.ts`: resume payload 从 `{ confirmed, userMessage }` 扩展为结构化 decision。
- Modify `src/shared/contracts/sse-events.ts`: 增加 Artifact SSE 事件。
- Modify `src/features/writing/writing-conversation.tsx`: 用 ArtifactReviewCard 替代只支持 `pendingUpdates` 的 UpdatesPreviewCard。
- Modify `src/app/api/writing/resume/route.ts`: 支持 artifact decision 请求体，仍保留普通 userMessage。
- Create `src/app/api/review-artifacts/[id]/route.ts`: 查询单个 Artifact。
- Create `src/app/api/review-artifacts/[id]/apply/route.ts`: 用户确认应用。
- Create `src/app/api/review-artifacts/[id]/route.ts` DELETE: 用户硬删除草案。
- Modify `src/shared/lib/context-aggregator.ts`: 不默认混入草案；只在 state 指定 activeArtifactId 时提供单独 `draftArtifacts` 字段。
- Modify `src/agents/graph/context-builder.ts`: 增加“待审核草案”上下文段，和正式设定分区展示。
- Modify `src/agents/graph/nodes/plot-advisor-node.ts`、`editor-node.ts`、`lore-advisor-node.ts`、`validator-node.ts`: 提示词要求修改/复审围绕 Artifact ID 和 revision。
- Modify `src/agents/AGENTS.md`: 更新流程图、control tools、Artifact 中间层、上下文隔离规则。

## Task 1: 数据模型和契约

**Files:**
- Modify: `prisma/schema.prisma`
- Create: `src/shared/contracts/review-artifact.ts`
- Test: `src/shared/contracts/__tests__/review-artifact.test.ts`

- [ ] Step 1: 写契约测试，覆盖状态、kind、decision 和 payload 校验。

```ts
import test from "node:test";
import assert from "node:assert/strict";
import {
  ReviewArtifactStatusSchema,
  ReviewArtifactKindSchema,
  ReviewArtifactDecisionSchema,
} from "../review-artifact";

test("review artifact status set is intentionally small", () => {
  assert.deepEqual(ReviewArtifactStatusSchema.options, [
    "draft",
    "under_review",
    "awaiting_user",
    "applying",
    "applied",
  ]);
});

test("discard is a user decision, not a persisted status", () => {
  assert.equal(ReviewArtifactDecisionSchema.safeParse("discard").success, true);
  assert.equal(ReviewArtifactStatusSchema.safeParse("discarded").success, false);
});

test("first phase supports agent_updates artifact", () => {
  assert.equal(ReviewArtifactKindSchema.safeParse("agent_updates").success, true);
});
```

- [ ] Step 2: 新增 `review-artifact.ts`，定义状态、kind、DTO 和动作 schema。

```ts
import { z } from "zod";
import { CoreAgentIdSchema } from "./agent";
import { AgentUpdatesSchema } from "./agent-updates";

export const ReviewArtifactStatusSchema = z.enum([
  "draft",
  "under_review",
  "awaiting_user",
  "applying",
  "applied",
]);
export type ReviewArtifactStatus = z.infer<typeof ReviewArtifactStatusSchema>;

export const ReviewArtifactKindSchema = z.enum([
  "agent_updates",
  "chapter_content",
  "beat_plan",
  "freeform_markdown",
]);
export type ReviewArtifactKind = z.infer<typeof ReviewArtifactKindSchema>;

export const ReviewArtifactDecisionSchema = z.enum(["approve", "discard", "revise"]);
export type ReviewArtifactDecision = z.infer<typeof ReviewArtifactDecisionSchema>;

export const ReviewArtifactPayloadSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("agent_updates"), updates: AgentUpdatesSchema }),
  z.object({ kind: z.literal("chapter_content"), content: z.string().min(1) }),
  z.object({ kind: z.literal("beat_plan"), beatPlan: z.unknown() }),
  z.object({ kind: z.literal("freeform_markdown"), markdown: z.string().min(1) }),
]);

export const ReviewArtifactDtoSchema = z.object({
  id: z.string(),
  novelId: z.string(),
  chapterId: z.string().nullable(),
  taskId: z.string().nullable(),
  workflowRunId: z.string().nullable(),
  artifactKey: z.string().nullable(),
  kind: ReviewArtifactKindSchema,
  status: ReviewArtifactStatusSchema,
  title: z.string().nullable(),
  summary: z.string().nullable(),
  payload: ReviewArtifactPayloadSchema,
  diff: z.unknown().nullable(),
  createdByAgent: CoreAgentIdSchema.nullable(),
  updatedByAgent: CoreAgentIdSchema.nullable(),
  reviewerAgent: CoreAgentIdSchema.nullable(),
  revision: z.number().int().min(1),
  createdAt: z.string(),
  updatedAt: z.string(),
});
```

- [ ] Step 3: 修改 Prisma schema，增加三张表和索引。

```prisma
model ReviewArtifact {
  id             String   @id @default(cuid())
  novelId        String
  chapterId      String?
  taskId         String?
  workflowRunId  String?
  artifactKey    String?
  kind           String
  status         String   @default("draft")
  title          String?
  summary        String?
  payloadJson    String
  diffJson       String?
  createdByAgent String?
  updatedByAgent String?
  reviewerAgent  String?
  revision       Int      @default(1)
  appliedAt      DateTime?
  createdAt      DateTime @default(now())
  updatedAt      DateTime @updatedAt

  novel          Novel    @relation(fields: [novelId], references: [id], onDelete: Cascade)
  chapter        Chapter? @relation(fields: [chapterId], references: [id], onDelete: Cascade)
  task           WritingTask? @relation(fields: [taskId], references: [id], onDelete: SetNull)
  workflowRun    WorkflowRun? @relation(fields: [workflowRunId], references: [id], onDelete: SetNull)
  revisions      ReviewArtifactRevision[]
  evaluations    ReviewArtifactEvaluation[]

  @@index([novelId, status])
  @@index([chapterId, status])
  @@index([taskId])
  @@index([workflowRunId])
  @@index([artifactKey])
}

model ReviewArtifactRevision {
  id          String   @id @default(cuid())
  artifactId  String
  revision    Int
  summary     String?
  payloadJson String
  diffJson    String?
  createdByAgent String?
  createdAt   DateTime @default(now())

  artifact    ReviewArtifact @relation(fields: [artifactId], references: [id], onDelete: Cascade)

  @@unique([artifactId, revision])
  @@index([artifactId])
}

model ReviewArtifactEvaluation {
  id              String   @id @default(cuid())
  artifactId      String
  revision        Int
  evaluatorAgent  String
  verdict         String   // pass | revise | block
  summary         String
  requiredChanges String?
  createdAt       DateTime @default(now())

  artifact        ReviewArtifact @relation(fields: [artifactId], references: [id], onDelete: Cascade)

  @@index([artifactId, revision])
  @@index([evaluatorAgent])
}
```

- [ ] Step 4: 在 `Novel`、`Chapter`、`WritingTask`、`WorkflowRun` 增加 `reviewArtifacts ReviewArtifact[]` relation。

- [ ] Step 5: 运行迁移和测试。

Run:
```bash
npm run db:migrate
npm test -- src/shared/contracts/__tests__/review-artifact.test.ts
```

Expected:
```text
tests pass
Prisma Client generated without schema relation errors
```

## Task 2: Artifact 服务、diff 和正式应用

**Files:**
- Create: `src/agents/artifacts/artifact-diff.ts`
- Create: `src/agents/artifacts/artifact-service.ts`
- Create: `src/agents/artifacts/artifact-apply.ts`
- Modify: `src/agents/graph/control-event-processor.ts`
- Test: `src/agents/artifacts/__tests__/artifact-service.test.ts`

- [ ] Step 1: 把 `control-event-processor.ts` 里的 `FIELD_LABELS`、`SECTION_LABELS`、`DIFF_FIELDS`、`buildUpdateDiffs()` 迁移到 `artifact-diff.ts` 并导出。

- [ ] Step 2: 写服务测试，覆盖创建、同 key 更新生成新 revision、评审通过、硬删除、重复 apply 拒绝。

```ts
test("createOrUpdateAgentUpdatesArtifact creates draft revision 1", async () => {
  const artifact = await createOrUpdateAgentUpdatesArtifact({
    novelId,
    chapterId,
    taskId,
    artifactKey: "outline-main",
    summary: "调整前三章大纲",
    updates: { outlineAdjustments: [{ action: "update", nodeTitle: "第一章", content: "强化钩子" }] },
    agentId: "剧情",
    novelData,
  });

  assert.equal(artifact.status, "draft");
  assert.equal(artifact.revision, 1);
});

test("discardArtifactHard removes artifact graph", async () => {
  await discardArtifactHard({ artifactId, userId });
  const found = await prisma.reviewArtifact.findUnique({ where: { id: artifactId } });
  assert.equal(found, null);
});
```

- [ ] Step 3: 实现 `artifact-service.ts`。

Required exported functions:
```ts
export async function createOrUpdateAgentUpdatesArtifact(input: {
  novelId: string;
  chapterId?: string | null;
  taskId?: string | null;
  workflowRunId?: string | null;
  artifactKey?: string | null;
  summary: string;
  updates: AgentUpdates;
  agentId: CoreAgentId;
  reviewerAgent?: CoreAgentId | null;
  novelData?: NovelData;
}): Promise<ReviewArtifactDto>;

export async function submitArtifactEvaluation(input: {
  artifactId: string;
  evaluatorAgent: CoreAgentId;
  verdict: "pass" | "revise" | "block";
  summary: string;
  requiredChanges?: string;
}): Promise<ReviewArtifactDto>;

export async function markArtifactUnderReview(input: {
  artifactId: string;
  reviewerAgent: CoreAgentId;
}): Promise<ReviewArtifactDto>;

export async function markArtifactAwaitingUser(input: {
  artifactId: string;
}): Promise<ReviewArtifactDto>;

export async function discardArtifactHard(input: {
  artifactId: string;
  userId: string;
}): Promise<void>;
```

- [ ] Step 4: 实现 `artifact-apply.ts`，第一期只允许 `kind === "agent_updates"` 调用 `executeUpdates(taskId, updates)`。

Rules:
- `status` 必须是 `awaiting_user` 才能 apply。
- apply 前用事务把状态从 `awaiting_user` 更新为 `applying`，防止重复点击。
- apply 成功后写 `applied` 和 `appliedAt`。
- apply 失败后回到 `awaiting_user` 并返回错误，不写正式库部分成功状态。

- [ ] Step 5: 运行测试。

Run:
```bash
npm test -- src/agents/artifacts/__tests__/artifact-service.test.ts
```

Expected:
```text
all artifact service tests pass
```

## Task 3: Control tools 和 LangGraph 控制流

**Files:**
- Modify: `src/shared/contracts/agent-control.ts`
- Modify: `src/agents/tools/control/control-tools.ts`
- Modify: `src/agents/graph/control-event-router.ts`
- Modify: `src/agents/graph/control-event-processor.ts`
- Modify: `src/agents/graph/state.ts`
- Modify: `src/agents/graph/graph-definition.ts`
- Test: `src/agents/graph/__tests__/control-event-router.test.ts`
- Test: `src/agents/graph/__tests__/control-event-processor.test.ts`

- [ ] Step 1: 修改 control contract，让 evaluation/revision 强绑定 Artifact。

Rules:
- `submit_evaluation` 入参新增 `artifactId`，保留 `artifactKey` 仅作兼容和展示。
- `request_revision` 入参新增 `artifactId`。
- `propose_updates` 入参新增可选 `artifactKey`、`reviewerAgent`、`submitForReview`。
- 新增 `submit_artifact` 可作为长期推荐工具，但第一期 `propose_updates` 必须兼容。

- [ ] Step 2: 改 router 测试，确认 submit/propose 是 side effect，不吞掉 route。

```ts
test("propose_updates and route_to_agent can happen in one turn", () => {
  const result = splitControlEvents([
    { type: "propose_updates", summary: "大纲修改", updates: { outlineAdjustments: [] } },
    { type: "route_to_agent", toAgent: "编辑", reason: "请复审大纲草案" },
  ] as AgentControlEvent[]);

  assert.equal(result.sideEffectEvents[0].type, "propose_updates");
  assert.equal(result.routeEvent?.type, "route_to_agent");
  assert.equal(result.ignoredRouteEvents.length, 0);
});
```

- [ ] Step 3: 修改 `control-event-router.ts`。

New classification:
- Route events: `route_to_agent`、`request_revision`
- Side effect events: `propose_updates`、`submit_artifact`、`submit_evaluation`、`submit_quality_report`、`submit_validation_report`、`submit_beat_plan`

- [ ] Step 4: 修改 `processControlEvents()`。

Required behavior:
- `propose_updates`: sanitize 后创建或更新 Artifact，发 `artifact_submitted`，不 interrupt 用户。
- 如果 event 带 `reviewerAgent` 或同轮 route 到 reviewer，则设置 `activeArtifactId` 并允许继续路由。
- `submit_evaluation(pass)`: 写 evaluation，把 artifact 标记 `awaiting_user`，发 `artifact_awaiting_user`，interrupt 用户确认。
- `submit_evaluation(revise|block)`: 写 evaluation，不改成用户待确认；如果同轮有 `request_revision`，路由返工 Agent。
- `request_revision`: 必须带 `artifactId` 或能从 `state.activeArtifactId` 推断，否则返回 errorMessage，不路由。
- 到达 `maxArtifactIterations` 后不再自动返工，转 `awaiting_user` 并说明需要用户裁决。

- [ ] Step 5: 扩展 Graph state。

Add:
```ts
activeArtifactId?: string | null;
artifactMode?: "none" | "review_loop";
reviewerAgent?: CoreAgentId | null;
reviserAgent?: CoreAgentId | null;
artifactIteration?: number;
maxArtifactIterations?: number;
```

- [ ] Step 6: 在 `graph-definition.ts` Annotation、`createInitialState()` 和 resume fresh input 中同步这些字段。

- [ ] Step 7: 运行图控制测试。

Run:
```bash
npm test -- src/agents/graph/__tests__/control-event-router.test.ts src/agents/graph/__tests__/control-event-processor.test.ts
```

Expected:
```text
propose + route same turn passes
evaluation pass interrupts for user approval
revision routes to reviser with activeArtifactId
```

## Task 4: Agent 草案读取工具和上下文隔离

**Files:**
- Create: `src/agents/tools/read/artifact-tools.ts`
- Modify: `src/agents/tools/index.ts`
- Modify: `src/agents/lib/tools.ts`
- Modify: `src/shared/lib/context-aggregator.ts`
- Modify: `src/agents/graph/context-builder.ts`
- Test: `src/agents/graph/__tests__/context-builder.test.ts`

- [ ] Step 1: 新增 read tools。

Tools:
- `list_review_artifacts(status?: string, kind?: string)`
- `get_review_artifact(artifact_id: string)`
- `get_active_review_artifact()`

Tool output must include:
```json
{
  "warning": "以下内容是待审核草案，不是正式设定。",
  "artifactId": "...",
  "status": "under_review",
  "revision": 2,
  "payload": {}
}
```

- [ ] Step 2: 修改 `createToolExecutor()`，给 tools state 传入 `activeArtifactId`、`novelId`、`chapterId`、`taskId`，但不把所有 Artifact 默认塞进 `novelData`。

- [ ] Step 3: 修改 `context-builder.ts`，只在 `state.activeArtifactId` 存在时追加 `## 当前待审核草案`。

Required wording:
```text
以下是待审核草案，不是正式设定。评审和返工必须引用 artifactId 与 revision；除非用户确认应用，否则不得把它当成已落库事实。
```

- [ ] Step 4: 写测试确认正式上下文和草案上下文隔离。

```ts
test("draft artifact is labeled as draft and not merged into official outline", () => {
  const text = buildActiveTaskContext(stateWithArtifact);
  assert.match(text, /待审核草案/);
  assert.match(text, /不是正式设定/);
});
```

## Task 5: 用户确认、SSE 和前端卡片

**Files:**
- Modify: `src/shared/contracts/sse-events.ts`
- Modify: `src/app/api/writing/resume/route.ts`
- Create: `src/app/api/review-artifacts/[id]/apply/route.ts`
- Create/Modify: `src/app/api/review-artifacts/[id]/route.ts`
- Modify: `src/features/writing/writing-conversation.tsx`
- Modify: `src/features/writing/writing-conversation.css`

- [ ] Step 1: 增加 SSE 事件契约。

Events:
- `artifact_submitted`
- `artifact_updated`
- `artifact_evaluation_submitted`
- `artifact_awaiting_user_approval`
- `artifact_applied`
- `artifact_deleted`

- [ ] Step 2: `user_input_required` 增加 `artifact` 字段，保留 `pendingUpdates` 兼容旧 UI。

- [ ] Step 3: `/api/writing/resume` 请求体支持：

```ts
{
  taskId: string;
  userMessage?: string;
  decision?: "approve" | "discard" | "revise";
  artifactId?: string;
}
```

- [ ] Step 4: `resumeWriting()` interrupt resume 不再永远 `{ confirmed: true, userMessage }`。

Mapping:
- `decision=approve`: 调用 `applyReviewArtifact()`，发 `artifact_applied`。
- `decision=discard`: 调用 `discardArtifactHard()`，发 `artifact_deleted`。
- `decision=revise`: 作为普通 userMessage 继续流程，并保留 activeArtifactId。

- [ ] Step 5: 前端新增 `ArtifactReviewCard`。

Display:
- 标题、状态、revision、创建/更新 Agent、reviewer、summary。
- diff 仍复用现有 `UpdatesPreviewCard` 的字段差异展示。
- evaluations 列表显示最近一次编辑/校验结论。
- actions: `应用到正式库`、`丢弃草案`、`继续修改`。

- [ ] Step 6: 保留旧 `updates_saved/updates_declined` 处理，避免老事件或测试瞬间崩。

- [ ] Step 7: 手动验证场景。

Scenario:
```text
@编辑 你觉得大纲怎么样，如果不好让剧情顾问改，然后你再审核，满意后让我确认再写入
```

Expected:
```text
编辑审阅 -> request_revision 剧情
剧情 submit/propose artifact -> route 编辑
编辑 submit_evaluation revise/pass
pass 后前端出现 ArtifactReviewCard
用户点应用后才 executeUpdates
用户点丢弃后 DB 中 artifact 硬删除
```

## Task 6: Agent 提示词和文档

**Files:**
- Modify: `src/agents/graph/nodes/plot-advisor-node.ts`
- Modify: `src/agents/graph/nodes/lore-advisor-node.ts`
- Modify: `src/agents/graph/nodes/editor-node.ts`
- Modify: `src/agents/graph/nodes/validator-node.ts`
- Modify: `src/agents/AGENTS.md`
- Modify: `docs/AGENT_NOVEL_WRITING_ROADMAP.md`

- [ ] Step 1: 更新剧情/设定 Agent。

Required prompt rule:
```text
当用户要求“先审核、写入前审核、让某 Agent 改完再由另一个 Agent 复审”时，你提交的是待审核 Artifact，不是直接请求用户保存。提交后必须把 artifactId 或 artifactKey 交给 reviewer。
```

- [ ] Step 2: 更新编辑/校验 Agent。

Required prompt rule:
```text
复审其他 Agent 产物时，必须读取 active review artifact。通过时 submit_evaluation(pass)，需要返工时 submit_evaluation(revise/block) 后 request_revision，并且两者必须引用同一个 artifactId。
```

- [ ] Step 3: 更新 `src/agents/AGENTS.md`。

Must document:
- ReviewArtifact 数据流。
- 正式库和待审核草案隔离。
- `propose_updates -> ReviewArtifact -> evaluation/revision loop -> awaiting_user -> apply`。
- 用户硬删除语义。
- 不再把 `propose_updates` 当路由互斥事件。

- [ ] Step 4: 更新路线图，说明中间层是“作者监督下的高质量网文生产闭环”的基础设施。

## Task 7: 回归测试和验收

**Files:**
- Modify/Add tests under `src/agents/graph/__tests__`
- Modify/Add tests under `src/shared/contracts/__tests__`
- Modify/Add tests under `src/agents/artifacts/__tests__`

- [ ] Step 1: 跑类型检查。

Run:
```bash
npm run typecheck
```

Expected:
```text
TypeScript reports no errors from review artifact changes
```

- [ ] Step 2: 跑相关单测。

Run:
```bash
npm test -- src/shared/contracts/__tests__/review-artifact.test.ts src/agents/graph/__tests__/control-event-router.test.ts src/agents/graph/__tests__/control-event-processor.test.ts src/agents/graph/__tests__/context-builder.test.ts
```

Expected:
```text
all selected tests pass
```

- [ ] Step 3: 跑 lint。

Run:
```bash
npm run lint
```

Expected:
```text
No new lint errors from changed files. Existing unrelated lint failures must be listed separately if present.
```

- [ ] Step 4: 启动开发服务器手动验收。

Run:
```bash
npm run dev
```

Manual checks:
- 普通 `@剧情 修改大纲` 不应立刻写库。
- `@剧情 修改大纲后让编辑复审` 应自动进入编辑。
- 编辑 pass 后前端出现等待用户应用的 Artifact。
- 用户应用后正式大纲节点变化。
- 用户丢弃后 Artifact 表无记录，正式库无变化。
- Agent 读取草案时 UI/日志/工具输出都明确显示“待审核草案”。

## 异常状态防线

1. Artifact 是待审核产物唯一来源，`pendingUpdates` 只作为旧 UI 兼容展示，不再作为业务状态源。
2. 正式落库只有 `applyReviewArtifact()` 一个入口，第一期内部只调用 `executeUpdates()`。
3. `apply`、`discard` 必须校验小说归属，复用 `authorizeWritingTask()` 和 `authorizeNovel()`。
4. `apply` 必须检查 `revision` 和 `status`，避免旧卡片覆盖新草案。
5. `discard` 是硬删除，不保留 discarded 状态。
6. `under_review` 不代表正式通过，只代表 reviewer 正在处理。
7. `awaiting_user` 只由 `submit_evaluation(pass)` 进入，不允许 producer Agent 自己把草案送到用户确认。
8. 自动返工有 `maxArtifactIterations`，超过后交给用户裁决，避免无限循环。
9. 同一轮多个 control events 按顺序处理 side effect，再处理 route；不再因为先提交草案而吞掉后续路由。
10. 草案上下文永远与正式上下文分区展示，读工具返回 warning，避免污染 Agent 判断。

## 推荐实施顺序

1. 先做 Task 1-2：没有持久 Artifact 服务，后面的 Graph/UI 都没有稳定对象。
2. 再做 Task 3-4：让 LangGraph 真正围绕 Artifact 循环，且保证上下文隔离。
3. 再做 Task 5：前端接入用户确认、应用、硬删除。
4. 最后做 Task 6-7：提示词、文档和回归验收。

第一期完成后，用户原始需求应能闭环：编辑提出问题，剧情顾问修改 Artifact，编辑复审同一个 Artifact，反复返工直到 pass，然后等待用户审核；用户确认后才写入正式库，用户拒绝则硬删除草案。
