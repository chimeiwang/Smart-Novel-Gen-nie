# AI 创作聊天优先工作台 Implementation Plan

> **供 Agent 执行：** 必须逐任务使用 `subagent-driven-development`（推荐）或 `executing-plans`；所有步骤使用复选框追踪，严格执行 TDD、逐步验证和小提交。

**目标：** 把长篇 AI 创作页恢复为以可恢复聊天时间线为唯一主入口的工作台，并以 SSE 实时呈现任务、Agent、复审、Artifact 决定和正式写入结果。

**架构：** Core 在同一会话创建新任务时组装完整可见会话历史，并用现有 `WritingMessage.metadata` 保存稳定任务与 Artifact 关联，不修改数据库结构。Web 把消息、当前任务、SSE 运行态和 Artifact 投影成单一时间线；右栏仅展示当前选中项目的完整检查器。现有 CreativeOperation、ReviewArtifact 状态机、SSE 事件契约和 `run_outcome` 权威对账保持不变。

**技术栈：** Next.js 16、React 19、TypeScript 5.9、原生 CSS、FastAPI、SQLAlchemy Async、Pydantic、PostgreSQL、SSE、Node Test Runner、pytest、Ruff、Mypy。

---

## 文件结构

### 新建

- `apps/core-api/src/inkforge_core/writing/conversation_history.py`：从现有 `WritingMessage` 组装新任务的完整可见会话历史。
- `apps/core-api/tests/writing/test_conversation_history.py`：会话历史顺序、角色过滤和当前消息追加测试。
- `apps/web/src/features/writing/writing-conversation-types.ts`：集中定义会话消息、Artifact、章节上下文和运行展示类型，供容器、时间线与检查器共同引用。
- `apps/web/src/features/writing/writing-timeline.ts`：把持久消息、任务、实时状态和 Artifact 投影成稳定时间线项目。
- `apps/web/src/features/writing/writing-conversation-timeline.tsx`：只负责渲染时间线、运行卡和 Artifact 卡。
- `apps/web/src/features/writing/writing-context-inspector.tsx`：只负责当前选中任务或 Artifact 的右侧检查器。
- `apps/web/src/features/writing/__tests__/writing-timeline.test.ts`：时间线顺序、卡片替换和恢复测试。

### 修改

- `apps/core-api/src/inkforge_core/writing/commands.py`：自然语言启动和显式长篇启动读取同会话历史。
- `apps/core-api/src/inkforge_core/writing/message_metadata.py`：工作流消息 metadata 支持 artifactId、revision 和 kind。
- `apps/core-api/src/inkforge_core/writing/tasks.py`：进入 awaiting_user_review 时持久化 Artifact 时间线节点。
- `apps/core-api/tests/writing/test_commands.py`：自然语言启动继承会话历史。
- `apps/core-api/tests/writing/test_long_serial_runs.py`：显式长篇启动继承会话历史。
- `apps/core-api/tests/writing/test_callback_identity.py`：Artifact 等待消息幂等持久化。
- `apps/web/src/features/writing/writing-conversation.tsx`：接入时间线投影、选中态、恢复提示和检查器，移除顶部任务模块。
- `apps/web/src/features/writing/product-actions.ts`：保留推荐算法，但输出改作输入框附近的推荐说法。
- `apps/web/src/features/writing/run-stream-monitor.ts`：暴露 connecting、connected、reconnecting 状态。
- `apps/web/src/features/writing/writing-conversation.css`：落实聊天优先结构、内联卡片、恢复提示和检查器样式。
- `apps/web/src/features/workspace/workspace-shell.tsx`：右栏语义从审核栏收敛为上下文检查器。
- `apps/web/src/features/writing/__tests__/product-actions.test.ts`：推荐说法而非平级模块的契约。
- `apps/web/src/features/writing/__tests__/run-stream-monitor.test.ts`：SSE 连接状态和重连测试。
- `apps/web/src/features/workspace/__tests__/workspace-shell-source.test.ts`：聊天优先 DOM 与右侧检查器契约。
- `docs/requirements/03-ai-writing-and-agents.md`：补充 chat-first 与跨任务会话连续性。
- `docs/requirements/04-review-quality-and-workflow.md`：补充 Artifact 内联卡与 SSE 决定反馈。

## Task 1：Core 会话历史组装

**Files:**
- Create: `apps/core-api/src/inkforge_core/writing/conversation_history.py`
- Create: `apps/core-api/tests/writing/test_conversation_history.py`
- Modify: `apps/core-api/src/inkforge_core/writing/commands.py`

- [ ] **Step 1：写失败测试，固定可见历史的顺序和角色**

```python
def test_build_new_task_history_preserves_visible_messages_and_appends_current() -> None:
    records = [
        SimpleNamespace(role="user", content="先讨论风险"),
        SimpleNamespace(role="system", content="内部调试记录"),
        SimpleNamespace(role="agent", content="风险来自内外压差"),
        SimpleNamespace(role="assistant", content="建议先规划本章"),
    ]

    assert build_new_task_history(records, "开始规划") == [
        {"role": "user", "content": "先讨论风险"},
        {"role": "agent", "content": "风险来自内外压差"},
        {"role": "assistant", "content": "建议先规划本章"},
        {"role": "user", "content": "开始规划"},
    ]
```

- [ ] **Step 2：运行测试并确认失败**

Run: `uv run pytest apps/core-api/tests/writing/test_conversation_history.py -q`

Expected: FAIL，提示 `conversation_history` 模块或 `build_new_task_history` 不存在。

- [ ] **Step 3：实现纯历史组装函数和数据库读取函数**

```python
from collections.abc import Iterable
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import WritingMessage


class VisibleMessage(Protocol):
    role: str
    content: str


def build_new_task_history(
    records: Iterable[VisibleMessage], current_user_message: str
) -> list[dict[str, str]]:
    history = [
        {"role": record.role, "content": record.content}
        for record in records
        if record.role in {"user", "agent", "assistant"}
    ]
    history.append({"role": "user", "content": current_user_message})
    return history


async def load_new_task_history(
    session: AsyncSession,
    writing_session_id: str | None,
    current_user_message: str,
) -> list[dict[str, str]]:
    if writing_session_id is None:
        return [{"role": "user", "content": current_user_message}]
    records = (
        await session.execute(
            select(WritingMessage)
            .where(WritingMessage.sessionId == writing_session_id)
            .order_by(WritingMessage.createdAt, WritingMessage.id)
        )
    ).scalars()
    return build_new_task_history(records, current_user_message)
```

- [ ] **Step 4：在两个长篇启动路径中使用完整历史**

在 `_create_natural_start()` 创建 `WritingTask` 前执行：

```python
conversation_history = await load_new_task_history(
    session,
    request.writingSessionId,
    request.userMessage,
)
```

在 `_create_long_serial_start()` 创建 `WritingTask` 前执行：

```python
conversation_history = await load_new_task_history(
    session,
    request.writingSessionId,
    request.userInstruction,
)
```

随后把 `WritingTask.conversationHistory` 和长篇 `graphStateJson.conversationHistory` 都改为同一个 `conversation_history`；本次用户消息仍只在事务内新增一条 `WritingMessage`。

- [ ] **Step 5：运行 Core 定向测试**

Run: `uv run pytest apps/core-api/tests/writing/test_conversation_history.py apps/core-api/tests/writing/test_commands.py apps/core-api/tests/writing/test_long_serial_runs.py -q`

Expected: PASS。

- [ ] **Step 6：提交**

```powershell
git add apps/core-api/src/inkforge_core/writing/conversation_history.py apps/core-api/src/inkforge_core/writing/commands.py apps/core-api/tests/writing/test_conversation_history.py apps/core-api/tests/writing/test_commands.py apps/core-api/tests/writing/test_long_serial_runs.py
git commit -m "功能：恢复跨任务会话上下文"
```

## Task 2：持久化 Artifact 时间线关联

**Files:**
- Modify: `apps/core-api/src/inkforge_core/writing/message_metadata.py`
- Modify: `apps/core-api/src/inkforge_core/writing/tasks.py`
- Test: `apps/core-api/tests/writing/test_callback_identity.py`

- [ ] **Step 1：写失败测试，要求 awaiting Artifact 产生一条幂等系统消息**

测试构造 awaiting_user_review checkpoint 和权威 `ReviewArtifact`，断言事务新增：

```python
message = next(item for item in session.added if isinstance(item, WritingMessage))
metadata = json.loads(message.metadata_)
assert message.role == "system"
assert metadata == {
    "source": "workflow",
    "taskId": "task-1",
    "eventType": "artifact_awaiting_user_approval",
    "agentId": "剧情",
    "artifactId": "artifact-1",
    "artifactRevision": 5,
    "artifactKind": "beat_plan",
    "contentHash": metadata["contentHash"],
}
```

重复保存相同 checkpoint 时不得新增第二条消息。

- [ ] **Step 2：运行测试并确认失败**

Run: `uv run pytest apps/core-api/tests/writing/test_callback_identity.py -k artifact_timeline -q`

Expected: FAIL，当前 metadata 没有 Artifact 字段且 checkpoint 不持久化时间线消息。

- [ ] **Step 3：扩展 metadata 构造器**

```python
def workflow_message_metadata(
    task_id: str,
    *,
    event_type: str,
    content: str,
    agent_id: str | None = None,
    artifact_id: str | None = None,
    artifact_revision: int | None = None,
    artifact_kind: str | None = None,
) -> str:
    payload: dict[str, object] = {
        "source": "workflow",
        "taskId": task_id,
        "eventType": event_type,
        "agentId": agent_id,
        "contentHash": hashlib.sha256(content.strip().encode()).hexdigest()[:24],
    }
    if artifact_id is not None:
        payload.update(
            artifactId=artifact_id,
            artifactRevision=artifact_revision,
            artifactKind=artifact_kind,
        )
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
```

- [ ] **Step 4：在保存等待态 checkpoint 的同一事务中持久化卡片节点**

`save_checkpoint()` 锁定任务和命令后，读取同 task、同 artifactId 的权威 Artifact；仅在 phase 确认写成 awaiting_user_review 时调用：

```python
await _persist_workflow_message(
    session,
    target.task,
    role="system",
    content=f"{artifact.title or '待确认草案'}已生成，等待确认。",
    event_type="artifact_awaiting_user_approval",
    agent_id=artifact.updatedByAgent,
    artifact_id=artifact.id,
    artifact_revision=artifact.revision,
    artifact_kind=artifact.kind,
)
```

同步扩展 `_persist_workflow_message()` 的三个可选 Artifact 参数。来源、任务、章节或状态不匹配时拒绝持久化，不猜测产物。

- [ ] **Step 5：运行定向测试**

Run: `uv run pytest apps/core-api/tests/writing/test_callback_identity.py apps/core-api/tests/writing/test_recovery.py -q`

Expected: PASS。

- [ ] **Step 6：提交**

```powershell
git add apps/core-api/src/inkforge_core/writing/message_metadata.py apps/core-api/src/inkforge_core/writing/tasks.py apps/core-api/tests/writing/test_callback_identity.py
git commit -m "功能：持久化草案时间线关联"
```

## Task 3：建立前端时间线投影模型

**Files:**
- Create: `apps/web/src/features/writing/writing-conversation-types.ts`
- Create: `apps/web/src/features/writing/writing-timeline.ts`
- Create: `apps/web/src/features/writing/__tests__/writing-timeline.test.ts`
- Modify: `apps/web/src/features/writing/writing-conversation.tsx`

- [ ] **Step 1：写失败测试，固定消息、运行卡和 Artifact 卡的替换关系**

```typescript
const timeline = composeWritingTimeline({
  messages: [userMessage, artifactSystemMessage],
  task: { id: "task-1" },
  phase: "awaiting_user_review",
  activeArtifact: artifact,
  liveAgentRuns: [],
  connectionState: "connected",
});

assert.deepEqual(timeline.map((item) => item.kind), ["message", "artifact"]);
assert.equal(timeline[1].key, "artifact:artifact-1");
```

补充断言：运行中只有一个 `run:task-1`；Artifact 出现后替换该运行卡；同一 metadata Artifact 与活动 Artifact 去重；普通消息顺序不变。

- [ ] **Step 2：运行测试并确认失败**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/writing/__tests__/writing-timeline.test.ts`

Expected: FAIL，提示 `writing-timeline` 模块不存在。

- [ ] **Step 3：实现严格时间线联合类型**

先把 `writing-conversation.tsx` 中的 `Message`、`ReviewArtifactData`、`ReviewArtifactActionState` 和章节上下文类型移入 `writing-conversation-types.ts`，并补上服务端已返回但当前本地类型丢失的字段：

```typescript
import type { components } from "@inkforge/api-client";
import type { ReviewArtifactDecision } from "@/shared/contracts/review-artifact";

export type WritingMessage = {
  id: string;
  role: "user" | "agent" | "system";
  agentId?: string;
  agentName?: string;
  content: string;
  intent?: string;
  timestamp: number;
  metadata: components["schemas"]["JsonValue"] | null;
  pendingUpdates?: PendingUpdatesData | null;
  reviewArtifact?: ReviewArtifactData | null;
  fullVersion?: string;
  isNewProtocol?: boolean;
};

export type ReviewArtifactData = {
  id: string;
  taskId?: string | null;
  title?: string | null;
  artifactKey?: string | null;
  kind: string;
  status: string;
  summary?: string | null;
  revision: number;
  sourceBindingStatus?: string | null;
  diff?: UpdateDiffItem[] | null;
  payload?: ReviewArtifactPayload;
  evaluations?: ReviewArtifactEvaluation[];
  optimisticStatus?: "applying" | "discarding" | "revising";
};

export type ChapterContext = {
  title: string;
  status: string;
  wordCount: number;
  openConsistencyCheckCount: number;
  approvedBeatPlan: {
    id: string;
    chapterGoal: string;
    sceneCount: number;
    totalEstimatedWords: number;
  } | null;
};

export type ArtifactDecisionHandler = (
  artifact: ReviewArtifactData,
  decision: ReviewArtifactDecision,
  userMessage?: string,
  editedContent?: string,
) => Promise<void>;

export type ReviewArtifactActionStatus = "pending" | "succeeded" | "failed";

export type ReviewArtifactActionState = {
  artifactId: string;
  decision: ReviewArtifactDecision;
  status: ReviewArtifactActionStatus;
  message: string;
};
```

`PendingUpdatesData`、`UpdateDiffItem`、`ReviewArtifactPayload` 和 `ReviewArtifactEvaluation` 也从原文件原样搬入该类型模块，不能在三个组件中分别维护重复结构。

```typescript
import type { AgentLiveRun } from "./agent-live-state";
import type { StreamConnectionState } from "./run-stream-monitor";
import type { WritingConversationPhase } from "./session-workspace-state";
import type { ReviewArtifactData, WritingMessage } from "./writing-conversation-types";

export type WritingTimelineInput = {
  messages: readonly WritingMessage[];
  task: { id: string } | null;
  phase: WritingConversationPhase;
  activeArtifact: ReviewArtifactData | null;
  liveAgentRuns: readonly AgentLiveRun[];
  connectionState: StreamConnectionState;
};

export type WritingTimelineItem =
  | { kind: "message"; key: string; message: WritingMessage }
  | { kind: "live_agent"; key: string; run: AgentLiveRun }
  | { kind: "run"; key: string; taskId: string; phase: WritingConversationPhase; connectionState: StreamConnectionState }
  | { kind: "artifact"; key: string; artifact: ReviewArtifactData; sourceMessageId?: string };

export function composeWritingTimeline(input: WritingTimelineInput): WritingTimelineItem[] {
  const items = input.messages.flatMap(projectMessageItem);
  const artifactIds = new Set(items.flatMap((item) => item.kind === "artifact" ? [item.artifact.id] : []));
  if (input.activeArtifact && !artifactIds.has(input.activeArtifact.id)) {
    items.push({ kind: "artifact", key: `artifact:${input.activeArtifact.id}`, artifact: input.activeArtifact });
  } else if (input.task && !input.activeArtifact && isTaskVisible(input.phase)) {
    items.push({ kind: "run", key: `run:${input.task.id}`, taskId: input.task.id, phase: input.phase, connectionState: input.connectionState });
  }
  items.push(...input.liveAgentRuns.map((run) => ({ kind: "live_agent" as const, key: `agent:${run.agentId}`, run })));
  return items;
}
```

`projectMessageItem()` 解析 `WritingMessage.metadata`；只有 `source=workflow` 且 Artifact 字段类型完整时生成 Artifact 卡，否则按普通消息显示。

- [ ] **Step 4：让会话消息保留 metadata**

`loadSessionMessages()` 映射 `MessageResponse` 时增加：

```typescript
metadata: m.metadata ?? null,
```

同时在 `LoadedSessionResponse.messages` 的元素类型中增加：

```typescript
metadata: components["schemas"]["JsonValue"] | null;
```

并把本地 `WritingMessage` 类型的 metadata 定义为 `components["schemas"]["JsonValue"] | null`，禁止继续丢失服务端关联。

- [ ] **Step 5：运行测试**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/writing/__tests__/writing-timeline.test.ts src/features/writing/__tests__/session-initialization.test.ts`

Expected: PASS。

- [ ] **Step 6：提交**

```powershell
git add apps/web/src/features/writing/writing-conversation-types.ts apps/web/src/features/writing/writing-timeline.ts apps/web/src/features/writing/writing-conversation.tsx apps/web/src/features/writing/__tests__/writing-timeline.test.ts
git commit -m "前端：建立写作会话时间线投影"
```

## Task 4：暴露 SSE 连接状态

**Files:**
- Modify: `apps/web/src/features/writing/run-stream-monitor.ts`
- Modify: `apps/web/src/features/writing/__tests__/run-stream-monitor.test.ts`
- Modify: `apps/web/src/features/writing/writing-conversation.tsx`

- [ ] **Step 1：写失败测试**

```typescript
const states: StreamConnectionState[] = [];
await monitorRunStream({
  open,
  consume,
  readOutcome,
  handleOutcome: () => undefined,
  shouldClose: (outcome) => outcome.streamShouldClose,
  onConnectionState: (state) => states.push(state),
  retryDelaysMs: [0],
});
assert.deepEqual(states, ["connecting", "reconnecting", "connected", "closed"]);
```

分别覆盖首次连接成功、首次失败后重连、收到事件后重置退避、权威 outcome 关闭。

- [ ] **Step 2：运行测试并确认失败**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/writing/__tests__/run-stream-monitor.test.ts`

Expected: FAIL，`onConnectionState` 尚不存在。

- [ ] **Step 3：实现连接状态回调**

```typescript
export type StreamConnectionState = "idle" | "connecting" | "connected" | "reconnecting" | "closed";

type MonitorRunStreamOptions<TOutcome> = {
  open: () => Promise<Response>;
  consume: (response: Response) => Promise<boolean>;
  readOutcome: () => Promise<TOutcome>;
  handleOutcome: (outcome: TOutcome) => void;
  shouldClose: (outcome: TOutcome) => boolean;
  signal?: AbortSignal;
  retryDelaysMs?: readonly number[];
  wait?: (delayMs: number, signal?: AbortSignal) => Promise<void>;
  onConnectionState?: (state: StreamConnectionState) => void;
};
```

首次 `open()` 前发 connecting；重试前发 reconnecting；成功取得 response 后发 connected；`shouldClose` 为真时发 closed。Abort 不转换为失败状态。

- [ ] **Step 4：WritingConversation 保存当前连接状态**

```typescript
const [streamConnectionState, setStreamConnectionState] = useState<StreamConnectionState>("idle");
```

在 `processStream()` 当前完整的 `monitorRunStream({...})` 参数对象中新增这一项，不改动已有 `open`、`consume`、`readOutcome`、`handleOutcome`、`shouldClose` 和 `signal`：

```typescript
onConnectionState: setStreamConnectionState,
```

连接状态只投影到当前 run 卡，不新增系统消息。

- [ ] **Step 5：运行测试并提交**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/writing/__tests__/run-stream-monitor.test.ts`

Expected: PASS。

```powershell
git add apps/web/src/features/writing/run-stream-monitor.ts apps/web/src/features/writing/writing-conversation.tsx apps/web/src/features/writing/__tests__/run-stream-monitor.test.ts
git commit -m "前端：展示写作事件流连接状态"
```

## Task 5：拆出时间线与上下文检查器组件

**Files:**
- Create: `apps/web/src/features/writing/writing-conversation-timeline.tsx`
- Create: `apps/web/src/features/writing/writing-context-inspector.tsx`
- Modify: `apps/web/src/features/writing/writing-conversation.tsx`
- Test: `apps/web/src/features/workspace/__tests__/workspace-shell-source.test.ts`

- [ ] **Step 1：先写 source contract 失败测试**

```typescript
assert.match(conversationSource, /<WritingConversationTimeline/);
assert.match(conversationSource, /<WritingContextInspector/);
assert.doesNotMatch(conversationSource, /next-action-panel writing-task-panel/);
assert.doesNotMatch(conversationSource, />创作任务</);
assert.match(conversationSource, /恢复了.*条消息/);
```

- [ ] **Step 2：运行测试并确认失败**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/workspace/__tests__/workspace-shell-source.test.ts`

Expected: FAIL，组件尚未拆出，顶部任务模块仍存在。

- [ ] **Step 3：实现 `WritingConversationTimeline`**

组件只接收投影后的 `WritingTimelineItem[]` 和事件回调：

```typescript
type WritingConversationTimelineProps = {
  items: readonly WritingTimelineItem[];
  copiedMessageId: string | null;
  onCopyMessage: (message: WritingMessage) => void;
  onRetryMessage: (message: WritingMessage) => void;
  onInspectArtifact: (artifact: ReviewArtifactData) => void;
  onRequestRevision: (artifact: ReviewArtifactData) => void;
};
```

`run` 卡显示当前 Operation、Agent、阶段和连接状态；`artifact` 卡只显示摘要、revision、来源状态、Reviewer 结果和“查看完整内容”，不在卡片上直接批准。

- [ ] **Step 4：实现 `WritingContextInspector`**

```typescript
type WritingContextInspectorProps = {
  chapter: ChapterContext | undefined;
  selectedArtifact: ReviewArtifactData | null;
  action: ReviewArtifactActionState | null;
  onDecision: ArtifactDecisionHandler;
  onCloseArtifact: () => void;
};
```

未选中 Artifact 时展示章节正式摘要；选中时复用现有完整 Artifact 内容、Diff、来源绑定、评审和决定控件。Artifact 内容读取失败或来源未验证时禁用决定按钮。

- [ ] **Step 5：替换 WritingConversation 内联巨型渲染块**

保留数据获取和事件处理，但把消息循环、liveAgentRuns、operation card、review rail portal 改为两个新组件；现有审核弹窗可以暂时保留作长文本全屏查看，但右栏是默认检查器。

- [ ] **Step 6：运行测试并提交**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/workspace/__tests__/workspace-shell-source.test.ts src/features/writing/__tests__/review-artifact-state.test.ts`

Expected: PASS。

```powershell
git add apps/web/src/features/writing/writing-conversation-timeline.tsx apps/web/src/features/writing/writing-context-inspector.tsx apps/web/src/features/writing/writing-conversation.tsx apps/web/src/features/workspace/__tests__/workspace-shell-source.test.ts
git commit -m "前端：重构聊天时间线与上下文检查器"
```

## Task 6：把推荐操作退回输入区

**Files:**
- Modify: `apps/web/src/features/writing/product-actions.ts`
- Modify: `apps/web/src/features/writing/__tests__/product-actions.test.ts`
- Modify: `apps/web/src/features/writing/writing-conversation.tsx`

- [ ] **Step 1：写失败测试**

```typescript
const suggestions = composeWritingSuggestions(snapshot);
assert.equal(suggestions[0].prompt, WRITING_ACTION_PROMPTS.plan_beat);
assert.ok(suggestions.length <= 3);
assert.equal(suggestions.every((item) => item.kind !== "open_artifacts"), true);
```

待审核 Artifact 存在时，建议只返回“查看待确认变更”和与当前 Artifact 对话相关的说法，不生成新的写作任务建议。

- [ ] **Step 2：运行测试并确认失败**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/writing/__tests__/product-actions.test.ts`

Expected: FAIL，`composeWritingSuggestions` 不存在。

- [ ] **Step 3：实现最多三个推荐说法**

```typescript
export function composeWritingSuggestions(snapshot: WritingNextActionSnapshot): WritingProductAction[] {
  if (snapshot.awaitingArtifactCount > 0) {
    return [{ kind: "open_artifacts", label: "查看待确认变更", description: "打开当前草案" }];
  }
  return getWritingNextActions(snapshot).filter((action) => action.prompt).slice(0, 3);
}
```

- [ ] **Step 4：移动 UI**

删除 `next-action-panel writing-task-panel`，在输入框上方渲染 `writing-suggestion-chip`。点击带 prompt 的建议继续调用普通 `handleSendMessage(prompt)`；`open_artifacts` 只选中时间线中当前 Artifact。

- [ ] **Step 5：运行测试并提交**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/writing/__tests__/product-actions.test.ts src/features/workspace/__tests__/workspace-shell-source.test.ts`

Expected: PASS。

```powershell
git add apps/web/src/features/writing/product-actions.ts apps/web/src/features/writing/writing-conversation.tsx apps/web/src/features/writing/__tests__/product-actions.test.ts apps/web/src/features/workspace/__tests__/workspace-shell-source.test.ts
git commit -m "前端：将创作建议收敛到输入区"
```

## Task 7：恢复 Artifact 卡与当前任务

**Files:**
- Modify: `apps/web/src/features/writing/writing-conversation.tsx`
- Modify: `apps/web/src/features/writing/review-artifact-state.ts`
- Modify: `apps/web/src/features/writing/__tests__/review-artifact-state.test.ts`
- Modify: `apps/web/src/features/writing/__tests__/session-initialization.test.ts`

- [ ] **Step 1：写失败测试，固定 metadata Artifact 恢复**

```typescript
const refs = collectArtifactMessageRefs(messages);
assert.deepEqual(refs, [
  { messageId: "message-2", taskId: "task-1", artifactId: "artifact-1", revision: 5 },
]);
```

补充测试：同一 artifactId 只请求一次；旧请求晚到不能覆盖当前会话；404 时保留“已不可用”卡片且不能批准。

- [ ] **Step 2：运行测试并确认失败**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/writing/__tests__/review-artifact-state.test.ts src/features/writing/__tests__/session-initialization.test.ts`

Expected: FAIL，当前加载消息时丢弃 metadata，也不会恢复历史 Artifact。

- [ ] **Step 3：实现引用收集与权威读取**

```typescript
export function collectArtifactMessageRefs(messages: readonly WritingMessage[]): ArtifactMessageRef[] {
  return messages.flatMap((message) => {
    const metadata = parseWorkflowArtifactMetadata(message.metadata);
    return metadata ? [{ messageId: message.id, ...metadata }] : [];
  });
}
```

选择会话后并行读取去重后的 `/api/v1/review-artifacts/{artifact_id}` 与仍在运行的 task status；用现有 request version/epoch 机制拒绝旧会话响应。读取完成后按 messageId 附着权威 Artifact，而不是追加到最后一条 Agent 消息。

- [ ] **Step 4：恢复提示与 SSE 续接**

`loadSessionMessages()` 完成后生成：

```typescript
setRecoveryNotice({
  sessionTitle: session.title,
  messageCount: session.messages.length,
  taskPhase: session.currentTask?.phase ?? null,
  awaitingArtifactCount: restoredArtifacts.filter(isAwaiting).length,
});
```

如果 currentTask 为 active/waiting_call，自动 `processStream(currentTask.id, sessionScope)`；awaiting_user_review 只恢复 Artifact 并等待用户，不重复启动命令。

- [ ] **Step 5：运行测试并提交**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/writing/__tests__/review-artifact-state.test.ts src/features/writing/__tests__/session-initialization.test.ts src/features/writing/__tests__/session-recovery-state.test.ts`

Expected: PASS。

```powershell
git add apps/web/src/features/writing/writing-conversation.tsx apps/web/src/features/writing/review-artifact-state.ts apps/web/src/features/writing/__tests__/review-artifact-state.test.ts apps/web/src/features/writing/__tests__/session-initialization.test.ts
git commit -m "前端：恢复会话中的草案与运行状态"
```

## Task 8：落实视觉层级与可访问性

**Files:**
- Modify: `apps/web/src/features/writing/writing-conversation.css`
- Modify: `apps/web/src/app/globals.css`
- Modify: `apps/web/src/features/workspace/workspace-shell.tsx`
- Test: `apps/web/src/features/workspace/__tests__/workspace-shell-source.test.ts`

- [ ] **Step 1：写失败 source/CSS contract**

```typescript
assert.match(cssSource, /\.writing-timeline/);
assert.match(cssSource, /\.writing-run-card/);
assert.match(cssSource, /\.writing-artifact-timeline-card/);
assert.match(cssSource, /\.writing-recovery-notice/);
assert.doesNotMatch(cssSource, /\.writing-chat \.next-action-panel/);
assert.match(shellSource, /id="workspace-context-inspector"/);
```

- [ ] **Step 2：运行测试并确认失败**

Run: `npm exec --workspace @inkforge/web -- tsx --test src/features/workspace/__tests__/workspace-shell-source.test.ts`

Expected: FAIL，旧审核栏和顶部 action 样式仍存在。

- [ ] **Step 3：按 DESIGN.md 落实样式**

- 时间线使用安静近白背景、hairline 边框和 14px 正文；
- 用户消息靠右，Agent 消息靠左；运行卡和 Artifact 卡使用小面积状态边线，不使用大色块；
- 输入区固定在中央底部，推荐 chip 不抢主操作；
- 检查器宽度沿用 340–400px，完整长文本纵向滚动；
- connecting/reconnecting、awaiting、failed 同时使用文字和颜色；
- 所有图标按钮提供 `aria-label`，任务状态区域使用 `aria-live="polite"`；
- 不引入 Tailwind，不使用 ReactMarkdown，不新增移动端设计。

- [ ] **Step 4：运行 Web 定向测试和类型检查**

Run: `npm test --workspace @inkforge/web -- --test-name-pattern="创作台|审核|会话|事件流"`

Run: `npm run typecheck --workspace @inkforge/web`

Expected: PASS。

- [ ] **Step 5：提交**

```powershell
git add apps/web/src/features/writing/writing-conversation.css apps/web/src/app/globals.css apps/web/src/features/workspace/workspace-shell.tsx apps/web/src/features/workspace/__tests__/workspace-shell-source.test.ts
git commit -m "前端：完成聊天优先创作台视觉层级"
```

## Task 9：同步权威需求并完成全量验证

**Files:**
- Modify: `docs/requirements/03-ai-writing-and-agents.md`
- Modify: `docs/requirements/04-review-quality-and-workflow.md`

- [ ] **Step 1：更新当前需求事实**

在 03 号需求中写明：聊天是长篇创作唯一主入口；同一 session 的新 task 必须继承可见历史；运行过程通过 SSE 投影到时间线。

在 04 号需求中写明：Artifact 是稳定消息卡；右栏仅为完整检查器；Artifact 决定 202 后继续监听同一任务并由 outcome 收口。

- [ ] **Step 2：运行 Python 定向验证**

Run: `uv run pytest apps/core-api/tests/writing/test_conversation_history.py apps/core-api/tests/writing/test_commands.py apps/core-api/tests/writing/test_long_serial_runs.py apps/core-api/tests/writing/test_callback_identity.py apps/core-api/tests/writing/test_recovery.py -q`

Expected: PASS。

Run: `uv run ruff check apps/core-api/src/inkforge_core/writing apps/core-api/tests/writing`

Expected: PASS。

Run: `uv run mypy apps/core-api/src`

Expected: PASS。

- [ ] **Step 3：运行 Web 全量验证**

Run: `npm run test:web`

Expected: PASS。

Run: `npm run typecheck`

Expected: PASS。

Run: `npm run lint`

Expected: PASS。

- [ ] **Step 4：核对数据库结构与文档**

Run: `git diff --check`

Expected: 无输出。

确认 `apps/core-api/src/inkforge_core/db/schema-contract.json` 未修改，未创建迁移文件，未新增数据库表或字段。

- [ ] **Step 5：手工验收完整浏览器流程**

1. 打开已有长篇章节和历史会话；
2. 确认消息、当前任务和待确认 Artifact 恢复；
3. 发送普通讨论消息，立即看到用户消息与运行卡；
4. 观察 Agent 状态和正文通过 SSE 更新；
5. 生成 Beat Plan，确认 Artifact 卡出现在正确对话位置；
6. 打开右侧检查器，查看完整计划、来源和评审；
7. 提交 revise，确认卡片进入返工中并继续 SSE；
8. 刷新页面，确认消息、Artifact revision 和当前状态恢复；
9. approve 后确认卡片显示正式应用结果；
10. 在同一会话发送新消息，确认 Agent 能引用此前对话事实。

- [ ] **Step 6：提交文档和最终收口**

```powershell
git add docs/requirements/03-ai-writing-and-agents.md docs/requirements/04-review-quality-and-workflow.md
git commit -m "文档：同步聊天优先创作工作流"
```

## 计划自审结果

- spec 中的页面结构、聊天主入口、Artifact 内联、右侧检查器、SSE 实时反馈、断流重连、跨任务上下文恢复、错误状态、数据库边界和测试要求均有对应任务。
- 不新增公共业务入口，不修改 PostgreSQL schema，不重复实现 SSE 监听器。
- 新增文件按“Core 历史组装、前端时间线投影、时间线渲染、检查器渲染”拆分，避免继续扩大 `writing-conversation.tsx`。
- 中短篇专用工作台不进入本次 UI 和历史继承改造。
