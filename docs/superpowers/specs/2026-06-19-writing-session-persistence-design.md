# Writing Session Persistence Design

## 背景

当前写作界面有两套对话历史：

- `WritingSession` / `WritingMessage`：用户可见的会话列表和消息详情，前端侧栏读取这里。
- `WritingTask.conversationHistory`：Agent / LangGraph 内部上下文，用于多 Agent 协作、恢复和上下文注入。

实际数据库状态显示，最近的 `WritingSession` 大多只有会话记录，没有 `WritingMessage`；而部分 `WritingTask.conversationHistory` 中存在 Agent 输出。这说明 Agent 运行结果并非完全没有落库，而是写入了内部任务历史，用户可见会话消息没有被可靠持久化。

## 目标

建立 `WritingSession` 与一次 Agent `WritingTask` 的明确关联，并让服务端工作流负责把用户可见消息写入 `WritingMessage`。前端可以继续做乐观展示，但不能再作为 Agent 消息持久化的唯一权威来源。

## 非目标

- 不合并 `WritingSession/WritingMessage` 与 `WritingTask.conversationHistory`。
- 不让会话列表直接读取 `WritingTask.conversationHistory`。
- 不新增平行 Agent 编排或自定义工作流状态机。
- 不改变 `ReviewArtifact` 作为 Agent 产物正式落库前中间层的规则。
- 不承诺 LangGraph `MemorySaver` 之外的停机级 graph checkpoint 恢复。

## 推荐方案

采用“服务端会话持久化桥接层”方案：

1. 前端创建或选择 `WritingSession`。
2. 前端启动 `/api/writing/session` 时显式传入 `writingSessionId`。
3. 服务端校验该会话属于当前用户，并且 `novelId/chapterId` 与请求一致。
4. `createInitialState()` 创建 `WritingTask` 时记录可选 `writingSessionId`。
5. 工作流发送 SSE 的同时，服务端根据关键事件写入 `WritingMessage`。
6. 前端会话列表继续只读取 `WritingSession/WritingMessage`。

这样 `WritingTask.conversationHistory` 继续服务 Agent 内部上下文，`WritingMessage` 成为用户可见聊天记录的权威来源。

## 数据模型

在 `WritingTask` 上增加可选关系：

```prisma
model WritingTask {
  id               String @id @default(cuid())
  novelId          String
  chapterId        String
  writingSessionId String?

  writingSession   WritingSession? @relation(fields: [writingSessionId], references: [id], onDelete: SetNull)

  @@index([writingSessionId])
}

model WritingSession {
  id      String @id @default(cuid())
  tasks   WritingTask[]
}
```

字段保持可选，以兼容历史任务、质量检查任务和 Studio 调试任务。

## 服务端数据流

### 新会话运行

1. `WritingConversation` 调用 `POST /api/writing/sessions` 创建会话。
2. 前端使用返回的 `session.id` 设置当前会话，并传给 `POST /api/writing/session`。
3. `/api/writing/session` 校验：
   - 用户已登录。
   - `novelId` 属于当前用户。
   - `writingSessionId` 存在时，必须属于当前用户。
   - `WritingSession.novelId/chapterId` 必须与请求一致。
4. `createInitialState()` 创建 `WritingTask`，写入 `writingSessionId`。
5. 服务端先保存用户消息到 `WritingMessage(role="user")`，或确认前端已保存并采用幂等保护避免重复。
6. 工作流运行期间，`agent_done` 写入 `WritingMessage(role="agent")`。
7. `done.finalContent` 写入 `WritingMessage(role="system")`。
8. `WritingSession.updatedAt` 随消息写入更新。

### 继续会话

现有 `/api/writing/resume` 以 `taskId` 为入口。恢复时从 `WritingTask.writingSessionId` 找到可见会话：

1. `authorizeWritingTask()` 校验任务归属。
2. 查询 task 的 `writingSessionId`。
3. 如果存在，则把用户继续输入和后续 Agent 输出写入同一个 `WritingSession`。
4. 如果不存在，保留当前行为，只更新 `WritingTask.conversationHistory`，不强行创建可见会话。

### 选择历史会话并恢复可继续状态

用户点击历史会话时，只应先恢复可见聊天记录，不应立即唤醒 LangGraph 或推进任务。只有用户继续输入、处理待审核草案或点击明确操作时，才进入 `/api/writing/resume`。

`GET /api/writing/sessions/[id]` 返回会话详情时，应把可继续任务与只读历史任务分开：

```ts
type CurrentSessionTask = {
  id: string;
  phase: "active" | "waiting_call" | "awaiting_user_review";
  updatedAt: string;
  hasAwaitingReviewArtifact: boolean;
} | null;

type LastSessionTask = {
  id: string;
  phase: "completed" | "error";
  updatedAt: string;
} | null;
```

任务选择规则：

1. 优先选择同一 `writingSessionId` 下 `phase = "awaiting_user_review"` 的最近任务。
2. 其次选择 `phase = "active"` 或 `phase = "waiting_call"` 的最近任务。
3. 最近的 `completed` 或 `error` 任务只放入 `lastTask`，不得进入 `currentTask` 或成为默认 resume 句柄。
4. 如果没有显式 `writingSessionId` 关联的非终态任务，返回 `currentTask: null`；禁止按小说、章节或创建时间猜测未绑定任务。

前端 `selectSession()` 加载会话后：

1. 设置 `currentSessionId`。
2. 渲染 `WritingMessage` 历史。
3. 如果 `currentTask` 存在，设置 `taskId = currentTask.id` 和 `taskIdRef.current`。
4. 如果 `currentTask.phase === "awaiting_user_review"`，调用现有 task 级 `/api/writing/tasks/[taskId]/review-artifact` 兜底接口恢复待审核草案卡片。
5. 用户继续输入时，如果存在 `taskId`，走 `/api/writing/resume`；否则走 `/api/writing/session` 创建新任务。

恢复 LangGraph 状态的方向必须是：

```text
WritingSession -> WritingTask -> /api/writing/resume -> checkpoint resume 或 fresh graph input
```

禁止从 `WritingMessage` 反向拼装 `WritingTask.conversationHistory` 或 LangGraph state。`WritingMessage` 是用户可见记录，不包含完整 control events、AgentOutput、调用消息和 ReviewArtifact 路由语义；反向拼装会造成路由、返工和审核状态不可靠。

## 消息落库策略

扩展 `src/agents/lib/message-service.ts`，让服务端工作流复用统一入口保存消息：

- `saveMessage()`：保存单条消息并更新 `WritingSession.updatedAt`。
- `saveMessagesBatch()`：保存批量消息。
- 新增幂等能力，推荐通过 `metadata` 存储稳定事件键：
  - 用户消息：`workflow:user:<taskId>:<messageHash>`
  - Agent 消息：`workflow:agent_done:<taskId>:<agentId>:<contentLength>:<contentHash>`
  - 系统消息：`workflow:done:<taskId>:<contentHash>`

当前 schema 没有 `dedupeKey` 字段，因此第一阶段可在 `metadata` 内写入 `dedupeKey`，保存前按 `sessionId + metadata contains key` 查询；如果后续性能需要，再考虑独立字段和唯一索引。

## SSE 契约

`src/shared/contracts/sse-events.ts` 可给以下事件增加可选 `writingSessionId`：

- `start`
- `agent_done`
- `done`
- `completed`
- `resume`

这不是前端持久化的必要条件，但有利于调试和状态追踪。新增字段必须同步前端类型解析。

## 前端职责

`writing-conversation.tsx` 做三类调整：

1. `createSession()` 返回创建出的 session，而不只调用 `setCurrentSessionId()`。
2. `startDiscussionInternal()` 使用局部 `sessionId` 变量，避免 React state 异步更新导致首条消息无法保存。
3. 启动 `/api/writing/session` 时传入 `writingSessionId`。

前端仍可保留 `addMessage()` 的即时展示能力；但 Agent 回复的长期持久化应以后端写入为准。为避免重复写入，可以选择：

- 用户消息仍由前端通过 `/api/writing/messages` 保存，后端只保存 Agent/system 消息。
- 或把用户消息也交给 `/api/writing/session` 统一保存，前端只做乐观展示。

推荐后者，因为它让一次工作流的可见消息全部由同一个后端入口负责。

## 错误处理

- `writingSessionId` 不存在：返回 404。
- 会话不属于当前用户：返回 403。
- 会话的 `novelId/chapterId` 与请求不一致：返回 400。
- 消息持久化失败但 SSE 仍可继续时：
  - 记录错误日志，包含 `taskId`、`writingSessionId`、事件类型。
  - 不中断 Agent 工作流。
  - 在 `done` 后可通过日志定位持久化失败。
- `WritingTask` 没有关联 `writingSessionId`：兼容历史任务，不写可见会话消息。

## 测试范围

### 后端单元/集成测试

- `/api/writing/session` 接收合法 `writingSessionId` 时创建的 `WritingTask` 带有关联。
- `writingSessionId` 属于其他小说或章节时返回错误。
- `writingSessionId` 属于其他用户时返回 403。
- `agent_done` 事件触发后写入 `WritingMessage(role="agent")`。
- 重复 `agent_done` fallback 不会重复写入同一条消息。
- `/api/writing/resume` 能使用 task 上的 `writingSessionId` 继续写入同一会话。
- `GET /api/writing/sessions/[id]` 返回最适合继续的 `currentTask`。
- 当存在 `awaiting_user_review` task 时，前端选择会话后能恢复审核草案卡片。
- 选择历史会话只加载消息和 task 摘要，不会立即推进 LangGraph。

### 前端测试

- 新建会话后立即发送第一条消息，使用返回的 session id，而不是依赖尚未刷新的 React state。
- 收到 `agent_done` 后 UI 仍即时展示。
- 刷新后从 `/api/writing/sessions/[id]` 能恢复用户消息和 Agent 消息。
- 选择带有关联 active task 的历史会话后，继续输入走 `/api/writing/resume`。
- 选择没有关联 task 的历史会话后，继续输入会创建新的 `WritingTask` 并绑定当前 `WritingSession`。

### 手动验证

1. 新建会话，发送一条 `@编辑` 请求。
2. 等 Agent 回复完成。
3. 刷新页面。
4. 打开同一个会话，确认用户消息和 Agent 回复都存在。
5. 检查数据库：
   - `WritingSession._count.messages > 0`
   - 对应 `WritingTask.writingSessionId = WritingSession.id`
   - `WritingTask.conversationHistory` 仍正常保存 Agent 内部历史。

## 文档更新

因为该变更影响 Agent 写作流程的持久化边界，需要同步更新 `src/agents/AGENTS.md`：

- 说明 `WritingTask.conversationHistory` 是 Agent 内部上下文。
- 说明 `WritingSession/WritingMessage` 是用户可见聊天记录。
- 说明工作流入口通过 `writingSessionId` 桥接两者，但不合并职责。

如果最终修改到仓库级开发准则，再同步更新根级 `AGENTS.md`。
