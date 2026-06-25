# Writing Session Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make writing chat sessions reliably recoverable by bridging `WritingSession` to `WritingTask` and persisting user-visible workflow messages from the server.

**Architecture:** Keep `WritingSession/WritingMessage` as the user-visible chat record and `WritingTask.conversationHistory` as the Agent/LangGraph internal context. Add an optional `writingSessionId` relation on `WritingTask`, pass it through `/api/writing/session`, persist visible messages through a service-layer bridge during workflow streaming, and let session selection recover the associated task for `/api/writing/resume`.

**Tech Stack:** Next.js App Router route handlers, React 19, TypeScript strict, Prisma 6/PostgreSQL, LangGraph, node:test.

---

## File Structure

- Modify `prisma/schema.prisma`: add optional `WritingTask.writingSessionId` relation and index.
- Create `prisma/migrations/20260619170000_add_writing_task_session_link/migration.sql`: PostgreSQL migration for the new nullable FK and index.
- Modify `src/agents/graph/workflow-runner.ts`: thread `writingSessionId` through `WorkflowInitialState`, `createInitialState()`, SSE events, and resume message persistence.
- Modify `src/agents/lib/message-service.ts`: add server-side helpers for workflow-visible message persistence with metadata dedupe.
- Create `src/agents/lib/__tests__/message-service.test.ts`: unit tests for dedupe key behavior.
- Modify `src/app/api/writing/session/route.ts`: accept and authorize `writingSessionId`, save user message through the workflow bridge, and pass the session id into `createInitialState()`.
- Modify `src/app/api/writing/resume/route.ts`: rely on task-associated `writingSessionId` for continued visible message persistence.
- Modify `src/app/api/writing/sessions/[id]/route.ts`: include `currentTask` summary in the session detail payload.
- Modify `src/shared/contracts/sse-events.ts`: add optional `writingSessionId` to relevant SSE schemas.
- Modify `src/features/writing/writing-conversation.tsx`: use returned session id synchronously, pass `writingSessionId`, restore `taskId` from `currentTask`, and recover review artifact cards for `awaiting_user_review`.
- Create `src/features/writing/session-task-state.ts`: small pure helper for selecting the UI phase after loading a session task.
- Create `src/features/writing/__tests__/session-task-state.test.ts`: tests for session task restoration decisions.
- Modify `src/agents/AGENTS.md`: document the persistence boundary and resume direction.
- Run `npx prisma generate` or `npm run db:generate` after schema changes.

## Task 1: Add WritingTask to WritingSession Relation

**Files:**
- Modify: `prisma/schema.prisma`
- Create: `prisma/migrations/20260619170000_add_writing_task_session_link/migration.sql`

- [ ] **Step 1: Update Prisma schema**

In `prisma/schema.prisma`, update `WritingTask` and `WritingSession`:

```prisma
model WritingTask {
  id        String @id @default(cuid())
  novelId   String
  chapterId String
  writingSessionId String?

  targetWordCount Int
  selectedAgents  String
  phase           WritingTaskPhase @default(idle)

  agentOutputs     String?
  generatedContent String?
  finalContent     String?

  conversationHistory String?

  foreshadowingUpdates String?
  outlineUpdates       String?
  characterChanges     String?

  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt

  novel           Novel            @relation(fields: [novelId], references: [id], onDelete: Cascade)
  chapter         Chapter          @relation(fields: [chapterId], references: [id], onDelete: Cascade)
  writingSession  WritingSession?  @relation(fields: [writingSessionId], references: [id], onDelete: SetNull)
  reviewArtifacts ReviewArtifact[]

  @@index([novelId])
  @@index([chapterId])
  @@index([writingSessionId])
}

model WritingSession {
  id        String   @id @default(cuid())
  novelId   String
  chapterId String
  title     String?
  phase     String   @default("idle")
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt

  novel    Novel            @relation(fields: [novelId], references: [id], onDelete: Cascade)
  chapter  Chapter          @relation(fields: [chapterId], references: [id], onDelete: Cascade)
  messages WritingMessage[]
  tasks    WritingTask[]

  @@index([novelId])
  @@index([chapterId])
}
```

- [ ] **Step 2: Add PostgreSQL migration**

Create `prisma/migrations/20260619170000_add_writing_task_session_link/migration.sql`:

```sql
ALTER TABLE "WritingTask"
  ADD COLUMN "writingSessionId" TEXT;

CREATE INDEX "WritingTask_writingSessionId_idx"
  ON "WritingTask"("writingSessionId");

ALTER TABLE "WritingTask"
  ADD CONSTRAINT "WritingTask_writingSessionId_fkey"
  FOREIGN KEY ("writingSessionId")
  REFERENCES "WritingSession"("id")
  ON DELETE SET NULL
  ON UPDATE CASCADE;
```

- [ ] **Step 3: Generate Prisma client**

Run:

```bash
npx prisma generate
```

Expected: Prisma Client generation succeeds without schema validation errors.

- [ ] **Step 4: Typecheck schema consumers**

Run:

```bash
npm run typecheck
```

Expected: TypeScript may fail in files that still need `writingSessionId` support. Record those failures for the next tasks; no unrelated failures should be introduced by the schema itself.

- [ ] **Step 5: Commit**

```bash
git add prisma/schema.prisma prisma/migrations/20260619170000_add_writing_task_session_link/migration.sql package-lock.json
git commit -m "feat: link writing tasks to chat sessions"
```

If `package-lock.json` is unchanged, omit it from `git add`.

## Task 2: Add Workflow Message Persistence Helpers

**Files:**
- Modify: `src/agents/lib/message-service.ts`
- Create: `src/agents/lib/__tests__/message-service.test.ts`

- [ ] **Step 1: Add tests for dedupe helper**

Create `src/agents/lib/__tests__/message-service.test.ts`:

```ts
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  buildWorkflowMessageDedupeKey,
  hashWorkflowMessageContent,
} from "../message-service";

describe("workflow message persistence helpers", () => {
  it("builds stable user message dedupe keys", () => {
    const key = buildWorkflowMessageDedupeKey({
      kind: "user",
      taskId: "task-1",
      content: "继续修改大纲",
    });

    assert.match(key, /^workflow:user:task-1:/);
    assert.equal(
      key,
      buildWorkflowMessageDedupeKey({
        kind: "user",
        taskId: "task-1",
        content: "继续修改大纲",
      })
    );
  });

  it("builds distinct agent dedupe keys by agent and content", () => {
    const first = buildWorkflowMessageDedupeKey({
      kind: "agent_done",
      taskId: "task-1",
      agentId: "编辑",
      content: "第一版评审",
    });
    const second = buildWorkflowMessageDedupeKey({
      kind: "agent_done",
      taskId: "task-1",
      agentId: "设定",
      content: "第一版评审",
    });

    assert.notEqual(first, second);
    assert.match(first, /^workflow:agent_done:task-1:编辑:5:/);
  });

  it("hashes content deterministically", () => {
    assert.equal(
      hashWorkflowMessageContent("同一段内容"),
      hashWorkflowMessageContent("同一段内容")
    );
    assert.notEqual(
      hashWorkflowMessageContent("同一段内容"),
      hashWorkflowMessageContent("另一段内容")
    );
  });
});
```

- [ ] **Step 2: Run failing test**

Run:

```bash
npx tsx --test src/agents/lib/__tests__/message-service.test.ts
```

Expected: FAIL because `buildWorkflowMessageDedupeKey` and `hashWorkflowMessageContent` do not exist.

- [ ] **Step 3: Implement helpers and idempotent save**

In `src/agents/lib/message-service.ts`, add imports:

```ts
import { createHash } from "node:crypto";
```

Add exports after `SaveMessageParams`:

```ts
export type WorkflowMessageDedupeInput =
  | { kind: "user"; taskId: string; content: string }
  | { kind: "agent_done"; taskId: string; agentId: string; content: string }
  | { kind: "done"; taskId: string; content: string };

export function hashWorkflowMessageContent(content: string): string {
  return createHash("sha256").update(content).digest("hex").slice(0, 16);
}

export function buildWorkflowMessageDedupeKey(input: WorkflowMessageDedupeInput): string {
  const hash = hashWorkflowMessageContent(input.content);
  if (input.kind === "agent_done") {
    return `workflow:agent_done:${input.taskId}:${input.agentId}:${input.content.length}:${hash}`;
  }
  return `workflow:${input.kind}:${input.taskId}:${hash}`;
}

export async function saveWorkflowVisibleMessage(params: SaveMessageParams & {
  taskId: string;
  dedupe: WorkflowMessageDedupeInput;
}) {
  const dedupeKey = buildWorkflowMessageDedupeKey(params.dedupe);
  const metadata = {
    ...(params.metadata ?? {}),
    dedupeKey,
    taskId: params.taskId,
    source: "workflow",
  };

  const existing = await prisma.writingMessage.findFirst({
    where: {
      sessionId: params.sessionId,
      metadata: {
        contains: `"dedupeKey":"${dedupeKey}"`,
      },
    },
  });

  if (existing) return existing;

  return saveMessage({
    ...params,
    metadata,
  });
}
```

- [ ] **Step 4: Run helper test**

Run:

```bash
npx tsx --test src/agents/lib/__tests__/message-service.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agents/lib/message-service.ts src/agents/lib/__tests__/message-service.test.ts
git commit -m "feat: add workflow visible message persistence helpers"
```

## Task 3: Authorize and Pass writingSessionId into New Workflow Runs

**Files:**
- Modify: `src/app/api/writing/session/route.ts`
- Modify: `src/agents/graph/workflow-runner.ts`

- [ ] **Step 1: Extend workflow input type**

In `src/agents/graph/workflow-runner.ts`, add `writingSessionId` to `WorkflowInitialState`:

```ts
export interface WorkflowInitialState {
  novelId: string;
  chapterId: string;
  targetWordCount: number;
  userMessage: string;
  userId: string;
  writingSessionId?: string | null;
  qualityCheckId?: string | null;
  selectedAgents?: string[];
}
```

- [ ] **Step 2: Persist relation when creating WritingTask**

In `createInitialState()`, destructure `writingSessionId` and add it to `prisma.writingTask.create()`:

```ts
const { novelId, chapterId, targetWordCount, userMessage, userId, writingSessionId, qualityCheckId, selectedAgents } = params;
```

```ts
const task = await prisma.writingTask.create({
  data: {
    novelId,
    chapterId,
    writingSessionId: writingSessionId ?? null,
    targetWordCount,
    selectedAgents: effectiveAgents.join(","),
    phase: "active",
    conversationHistory: "[]",
  },
});
```

- [ ] **Step 3: Authorize writingSessionId in route**

In `src/app/api/writing/session/route.ts`, import:

```ts
import { authorizeWritingSession, authErrorResponse } from "@/agents/lib/task-auth";
```

Read `writingSessionId` from the body:

```ts
const {
  novelId,
  chapterId,
  targetWordCount,
  selectedAgents,
  userMessage,
  writingSessionId,
} = body;
```

After novel ownership validation, add:

```ts
let authorizedWritingSessionId: string | null = null;
if (typeof writingSessionId === "string" && writingSessionId.trim()) {
  const sessionAuth = await authorizeWritingSession(writingSessionId, session.userId);
  if (!sessionAuth.authorized) {
    return authErrorResponse(sessionAuth.reason ?? "无权访问该会话", 403);
  }
  if (
    sessionAuth.session?.novelId !== novelId ||
    sessionAuth.session?.chapterId !== chapterId
  ) {
    return new Response(
      JSON.stringify({ error: "会话与当前小说或章节不匹配" }),
      { status: 400 }
    );
  }
  authorizedWritingSessionId = writingSessionId;
}
```

Pass it to `createInitialState()`:

```ts
const initialState = await createInitialState({
  novelId,
  chapterId,
  targetWordCount: targetWordCount ?? 4000,
  userMessage: userMessage ?? "",
  userId: session.userId,
  writingSessionId: authorizedWritingSessionId,
  selectedAgents: selectedAgents ?? undefined,
});
```

- [ ] **Step 4: Typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS or only failures from tasks not yet implemented if this is run before all tasks. Do not ignore new errors in touched files.

- [ ] **Step 5: Commit**

```bash
git add src/app/api/writing/session/route.ts src/agents/graph/workflow-runner.ts
git commit -m "feat: bind new workflow runs to writing sessions"
```

## Task 4: Persist Workflow SSE Messages Server-Side

**Files:**
- Modify: `src/agents/graph/workflow-runner.ts`
- Modify: `src/shared/contracts/sse-events.ts`

- [ ] **Step 1: Add optional writingSessionId to SSE contracts**

In `src/shared/contracts/sse-events.ts`, add `writingSessionId: z.string().optional()` to:

```ts
StartEventSchema
DoneEventSchema
CompletedEventSchema
ResumeEventSchema
AgentDoneEventSchema
```

Example:

```ts
export const StartEventSchema = z.object({
  type: z.literal("start"),
  taskId: z.string(),
  writingSessionId: z.string().optional(),
});
```

- [ ] **Step 2: Import message persistence helper**

In `src/agents/graph/workflow-runner.ts`, import:

```ts
import { saveWorkflowVisibleMessage } from "@/agents/lib/message-service";
```

- [ ] **Step 3: Extend createSSEStream with a visible session ref**

Add a small type above `createSSEStream()`:

```ts
type VisibleSessionRef = { writingSessionId: string | null };
```

Change `createSSEStream()` signature to accept the ref:

```ts
function createSSEStream(
  taskId: string,
  logPrefix: string,
  auditContext: Omit<WorkflowEventLogContext, "taskId">,
  visibleSession: VisibleSessionRef,
  runner: (
    sendEvent: SendEventFn,
    sentKeys: Set<string>,
    config: { configurable: { thread_id: string } },
    close: () => void,
    auditLog: WorkflowEventFileLogger
  ) => Promise<void>
): Response {
```

For new workflow runs, pass the known session id at construction:

```ts
return createSSEStream(
  taskId,
  "",
  {
    runKind: "writing-workflow",
    userId: initialState.userId,
    novelId: initialState.novelId,
    chapterId: initialState.chapterId,
    qualityCheckId: initialState.qualityCheckId,
  },
  { writingSessionId: initialState.writingSessionId ?? null },
  async (sendEvent, sentKeys, config, close, auditLog) => {
    // existing runner body
  }
);
```

For resume runs, create the ref before calling `createSSEStream()`:

```ts
const visibleSession: VisibleSessionRef = { writingSessionId: null };
```

Pass `visibleSession`, then set it immediately after loading the task:

```ts
visibleSession.writingSessionId = task.writingSessionId ?? null;
```

- [ ] **Step 4: Persist agent_done and done messages**

Inside `sendEvent`, after `auditLog.recordSSEEvent(type, data)` and before enqueue, add:

```ts
void persistVisibleWorkflowEvent({
  taskId,
  writingSessionId: visibleSession.writingSessionId,
  type,
  data,
});
```

Add helper in `workflow-runner.ts`:

```ts
async function persistVisibleWorkflowEvent(input: {
  taskId: string;
  writingSessionId: string | null;
  type: string;
  data: Record<string, unknown>;
}): Promise<void> {
  if (!input.writingSessionId) return;

  try {
    if (input.type === "agent_done") {
      const content = typeof input.data.content === "string" ? input.data.content : "";
      const agentId = typeof input.data.agentId === "string" ? input.data.agentId : undefined;
      if (!content || !agentId) return;
      await saveWorkflowVisibleMessage({
        sessionId: input.writingSessionId,
        taskId: input.taskId,
        role: "agent",
        agentId,
        content,
        dedupe: {
          kind: "agent_done",
          taskId: input.taskId,
          agentId,
          content,
        },
      });
      return;
    }

    if (input.type === "done" || input.type === "completed") {
      const content = typeof input.data.finalContent === "string" ? input.data.finalContent : "";
      if (!content) return;
      await saveWorkflowVisibleMessage({
        sessionId: input.writingSessionId,
        taskId: input.taskId,
        role: "system",
        content,
        dedupe: {
          kind: "done",
          taskId: input.taskId,
          content,
        },
      });
    }
  } catch (error) {
    logger.error("WORKFLOW", "保存可见会话消息失败", {
      taskId: input.taskId,
      writingSessionId: input.writingSessionId,
      type: input.type,
      error,
    });
  }
}
```

- [ ] **Step 5: Include writingSessionId in start/resume/done events**

In new workflow:

```ts
sendEvent("start", { taskId, writingSessionId: visibleSession.writingSessionId ?? undefined });
```

In done:

```ts
sendEvent("done", {
  taskId,
  writingSessionId: visibleSession.writingSessionId ?? undefined,
  conversationSummary: buildContextSummary(fs as unknown as WritingState),
  activeAgent: fs.activeAgent,
});
```

In resume, include the task-associated session id once loaded.

- [ ] **Step 6: Run tests**

Run:

```bash
npx tsx --test src/agents/lib/__tests__/message-service.test.ts src/agents/graph/__tests__/sse-adapter.test.ts
npm run typecheck
```

Expected: tests pass and typecheck passes.

- [ ] **Step 7: Commit**

```bash
git add src/agents/graph/workflow-runner.ts src/shared/contracts/sse-events.ts
git commit -m "feat: persist workflow messages to writing sessions"
```

## Task 5: Return currentTask from Session Detail API

**Files:**
- Modify: `src/app/api/writing/sessions/[id]/route.ts`

- [ ] **Step 1: Query task candidates**

In `GET`, after loading the authorized session, include related tasks with minimal fields:

```ts
const session = await prisma.writingSession.findUnique({
  where: { id },
  include: {
    messages: {
      orderBy: { createdAt: "asc" },
    },
    tasks: {
      orderBy: { updatedAt: "desc" },
      select: {
        id: true,
        phase: true,
        updatedAt: true,
        generatedContent: true,
        reviewArtifacts: {
          where: { status: "awaiting_user" },
          select: { id: true },
          take: 1,
        },
      },
    },
  },
});
```

- [ ] **Step 2: Select currentTask**

Add helper in the route file:

```ts
function selectCurrentSessionTask(
  tasks: Array<{
    id: string;
    phase: string;
    updatedAt: Date;
    reviewArtifacts: Array<{ id: string }>;
  }>
) {
  const priority = ["awaiting_user_review", "active", "waiting_call", "completed", "error"];
  for (const phase of priority) {
    const match = tasks.find((task) => task.phase === phase);
    if (match) {
      return {
        id: match.id,
        phase: match.phase,
        updatedAt: match.updatedAt,
        hasAwaitingReviewArtifact: match.reviewArtifacts.length > 0,
      };
    }
  }
  return null;
}
```

Return:

```ts
return Response.json({
  ...session,
  currentTask: selectCurrentSessionTask(session.tasks),
  tasks: undefined,
});
```

Use object destructuring instead of returning `tasks: undefined` if lint complains:

```ts
const { tasks, ...payload } = session;
return Response.json({
  ...payload,
  currentTask: selectCurrentSessionTask(tasks),
});
```

- [ ] **Step 3: Typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/app/api/writing/sessions/[id]/route.ts
git commit -m "feat: expose current task for writing sessions"
```

## Task 6: Update Frontend Session Selection and New Run Flow

**Files:**
- Modify: `src/features/writing/writing-conversation.tsx`
- Create: `src/features/writing/session-task-state.ts`
- Create: `src/features/writing/__tests__/session-task-state.test.ts`

- [ ] **Step 1: Add session task restoration helper test**

Create `src/features/writing/__tests__/session-task-state.test.ts`:

```ts
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { resolveLoadedSessionTaskState } from "../session-task-state";

describe("session task state", () => {
  it("restores review mode for awaiting user review tasks", () => {
    assert.deepEqual(
      resolveLoadedSessionTaskState({
        id: "task-1",
        phase: "awaiting_user_review",
        updatedAt: "2026-06-19T00:00:00.000Z",
        hasAwaitingReviewArtifact: true,
      }),
      {
        taskId: "task-1",
        phase: "recording",
        shouldRefreshAwaitingReviewArtifact: true,
      }
    );
  });

  it("restores discussing mode for active tasks", () => {
    assert.deepEqual(
      resolveLoadedSessionTaskState({
        id: "task-2",
        phase: "active",
        updatedAt: "2026-06-19T00:00:00.000Z",
        hasAwaitingReviewArtifact: false,
      }),
      {
        taskId: "task-2",
        phase: "discussing",
        shouldRefreshAwaitingReviewArtifact: false,
      }
    );
  });

  it("clears task state when no task is available", () => {
    assert.deepEqual(resolveLoadedSessionTaskState(null), {
      taskId: null,
      phase: "idle",
      shouldRefreshAwaitingReviewArtifact: false,
    });
  });
});
```

- [ ] **Step 2: Run failing helper test**

Run:

```bash
npx tsx --test src/features/writing/__tests__/session-task-state.test.ts
```

Expected: FAIL because `session-task-state.ts` does not exist.

- [ ] **Step 3: Implement session task restoration helper**

Create `src/features/writing/session-task-state.ts`:

```ts
export type LoadedSessionTaskPhase =
  | "idle"
  | "active"
  | "waiting_call"
  | "awaiting_user_review"
  | "completed"
  | "error";

export type LoadedSessionTask = {
  id: string;
  phase: LoadedSessionTaskPhase;
  updatedAt: string;
  hasAwaitingReviewArtifact: boolean;
} | null;

export type LoadedSessionTaskState = {
  taskId: string | null;
  phase: "idle" | "discussing" | "recording";
  shouldRefreshAwaitingReviewArtifact: boolean;
};

export function resolveLoadedSessionTaskState(
  task: LoadedSessionTask
): LoadedSessionTaskState {
  if (!task) {
    return {
      taskId: null,
      phase: "idle",
      shouldRefreshAwaitingReviewArtifact: false,
    };
  }

  if (task.phase === "awaiting_user_review") {
    return {
      taskId: task.id,
      phase: "recording",
      shouldRefreshAwaitingReviewArtifact: task.hasAwaitingReviewArtifact,
    };
  }

  if (task.phase === "active" || task.phase === "waiting_call") {
    return {
      taskId: task.id,
      phase: "discussing",
      shouldRefreshAwaitingReviewArtifact: false,
    };
  }

  return {
    taskId: task.id,
    phase: "idle",
    shouldRefreshAwaitingReviewArtifact: false,
  };
}
```

- [ ] **Step 4: Run helper test**

Run:

```bash
npx tsx --test src/features/writing/__tests__/session-task-state.test.ts
```

Expected: PASS.

- [ ] **Step 5: Import helper in writing-conversation**

In `src/features/writing/writing-conversation.tsx`, import:

```ts
import {
  resolveLoadedSessionTaskState,
  type LoadedSessionTask,
} from "./session-task-state";
```

Extend the loaded session response type in `loadSessionMessages()` mapping to include:

```ts
currentTask?: LoadedSessionTask;
```

- [ ] **Step 6: Make createSession return the created session**

Change `createSession` to return `Promise<Session | null>`:

```ts
const createSession = useCallback(async (): Promise<Session | null> => {
  try {
    const res = await fetch("/api/writing/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ novelId, chapterId }),
    });
    if (res.ok) {
      const session = await res.json() as Session;
      await loadSessions();
      setCurrentSessionId(session.id);
      setMessages([]);
      setPhase("idle");
      setTaskId(null);
      taskIdRef.current = null;
      setShowSessionModal(false);
      return session;
    }
  } catch (err) {
    console.error("??????", err);
  }
  return null;
}, [novelId, chapterId, loadSessions]);
```

- [ ] **Step 7: Use a local session id in startDiscussionInternal**

Replace:

```ts
if (!currentSessionId) {
  await createSession();
}
```

with:

```ts
let activeSessionId = currentSessionId;
if (!activeSessionId) {
  const createdSession = await createSession();
  activeSessionId = createdSession?.id ?? null;
}
if (!activeSessionId) {
  setError("????????");
  return;
}
```

Pass `writingSessionId` to `/api/writing/session`:

```ts
body: JSON.stringify({
  novelId,
  chapterId,
  targetWordCount,
  selectedAgents,
  userMessage,
  writingSessionId: activeSessionId,
}),
```

- [ ] **Step 8: Stop relying on frontend save for workflow messages**

For workflow messages, keep optimistic display but disable frontend persistence:

```ts
const addMessage = useCallback((msg: {
  role: "user" | "agent" | "system";
  agentId?: string;
  agentName?: string;
  content: string;
  intent?: string;
  isNewProtocol?: boolean;
  persist?: boolean;
}) => {
  const newMsg: Message = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    timestamp: Date.now(),
    ...msg,
  };
  setMessages((prev) => [...prev, newMsg]);
  if (msg.persist !== false) {
    saveMessageToServer(msg.role, msg.content, msg.agentId, msg.intent);
  }
  setTimeout(scrollToBottom, 50);
}, [saveMessageToServer]);
```

Use `persist: false` for workflow user and Agent messages:

```ts
addMessage({ role: "user", content: userMessage, persist: false });
```

```ts
addMessage({
  role: "agent",
  agentId: event.agentId,
  agentName: getAgentName(event.agentId),
  content: finalContent,
  isNewProtocol: true,
  persist: false,
});
```

- [ ] **Step 9: Restore currentTask on session selection**

In `loadSessionMessages()`, after `setMessages(loadedMessages)`, add:

```ts
const sessionTaskState = resolveLoadedSessionTaskState(session.currentTask ?? null);
setTaskId(sessionTaskState.taskId);
taskIdRef.current = sessionTaskState.taskId;
setPhase(sessionTaskState.phase);
if (sessionTaskState.shouldRefreshAwaitingReviewArtifact) {
  await refreshAwaitingReviewArtifact("session_select");
}
```

Move `loadSessionMessages` below `refreshAwaitingReviewArtifact` if needed so the callback can call it without referencing an uninitialized const.

- [ ] **Step 10: Ensure no task creates a new run bound to current session**

In `handleSendMessage`, existing logic calls `startDiscussionInternal(message)` when `!taskId`. With Step 7, that creates a new task bound to the existing `currentSessionId`; keep this behavior.

- [ ] **Step 11: Run frontend helper test and typecheck**

Run:

```bash
npx tsx --test src/features/writing/__tests__/session-task-state.test.ts
npm run typecheck
```

Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add src/features/writing/writing-conversation.tsx src/features/writing/session-task-state.ts src/features/writing/__tests__/session-task-state.test.ts
git commit -m "feat: restore writing task when selecting chat sessions"
```

## Task 7: Persist User Messages from Server Workflow Entry

**Files:**
- Modify: `src/app/api/writing/session/route.ts`
- Modify: `src/app/api/writing/resume/route.ts`
- Modify: `src/agents/graph/workflow-runner.ts`

- [ ] **Step 1: Add initial user message persistence**

In `src/app/api/writing/session/route.ts`, import:

```ts
import { saveWorkflowVisibleMessage } from "@/agents/lib/message-service";
```

After `createInitialState()` returns and before `executeWritingWorkflow(initialState)`, save the user message if `authorizedWritingSessionId` and `userMessage` are present:

```ts
if (authorizedWritingSessionId && typeof userMessage === "string" && userMessage.trim()) {
  await saveWorkflowVisibleMessage({
    sessionId: authorizedWritingSessionId,
    taskId: initialState.taskId,
    role: "user",
    content: userMessage.trim(),
    dedupe: {
      kind: "user",
      taskId: initialState.taskId,
      content: userMessage.trim(),
    },
  });
}
```

- [ ] **Step 2: Add resume user message persistence**

In `src/app/api/writing/resume/route.ts`, after task authorization succeeds and before calling `resumeWriting`, load `writingSessionId`:

```ts
const task = await prisma.writingTask.findUnique({
  where: { id: taskId },
  select: { writingSessionId: true },
});
```

If `task?.writingSessionId` and normalized user message exist, call `saveWorkflowVisibleMessage()` with `kind: "user"`.

- [ ] **Step 3: Avoid duplicate user saves**

Because frontend workflow `addMessage(..., persist: false)` no longer saves user messages for workflow runs, the backend save becomes authoritative. Keep `/api/writing/messages` unchanged for manual or legacy saves.

- [ ] **Step 4: Typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/app/api/writing/session/route.ts src/app/api/writing/resume/route.ts
git commit -m "feat: persist workflow user messages on the server"
```

## Task 8: Update Agent Documentation

**Files:**
- Modify: `src/agents/AGENTS.md`

- [ ] **Step 1: Add persistence boundary section**

In `src/agents/AGENTS.md`, add a dated note near the persistence / workflow sections:

```md
## 2026-06-19 写作会话持久化边界

- `WritingSession/WritingMessage` 是用户可见聊天记录，用于会话列表、历史消息展示和刷新恢复。
- `WritingTask.conversationHistory` 是 Agent/LangGraph 内部上下文，用于恢复 Agent 协作状态、构建提示词和保留 control-event 语义。
- 新写作工作流通过可选 `WritingTask.writingSessionId` 桥接两者；桥接不代表合并职责。
- 选择历史会话时只恢复消息和关联 task 摘要，不立即推进 LangGraph。
- 继续历史会话时必须沿 `WritingSession -> WritingTask -> /api/writing/resume` 恢复，不得从 `WritingMessage` 反向拼装 LangGraph state。
```

- [ ] **Step 2: Commit**

```bash
git add src/agents/AGENTS.md
git commit -m "docs: document writing session persistence boundary"
```

## Task 9: End-to-End Verification

**Files:**
- No planned edits.

- [ ] **Step 1: Run focused tests**

Run:

```bash
npx tsx --test src/agents/lib/__tests__/message-service.test.ts src/agents/graph/__tests__/sse-adapter.test.ts src/features/writing/__tests__/review-artifact-state.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 3: Run Prisma generate**

Run:

```bash
npx prisma generate
```

Expected: Prisma Client generation succeeds.

- [ ] **Step 4: Manual database verification**

After starting the app and running a writing session manually:

```bash
npx tsx -e "import { PrismaClient } from '@prisma/client'; async function main(){ const prisma = new PrismaClient(); const sessions = await prisma.writingSession.findMany({ take: 3, orderBy: { updatedAt: 'desc' }, select: { id: true, title: true, _count: { select: { messages: true, tasks: true } }, messages: { take: 3, orderBy: { createdAt: 'asc' }, select: { role: true, agentId: true, content: true } }, tasks: { take: 1, orderBy: { updatedAt: 'desc' }, select: { id: true, phase: true, writingSessionId: true, conversationHistory: true } } } }); console.log(JSON.stringify(sessions.map(s => ({ id: s.id, title: s.title, messageCount: s._count.messages, taskCount: s._count.tasks, messages: s.messages.map(m => ({ role: m.role, agentId: m.agentId, preview: m.content.slice(0, 40) })), tasks: s.tasks.map(t => ({ id: t.id, phase: t.phase, writingSessionId: t.writingSessionId, historyLength: t.conversationHistory ? JSON.parse(t.conversationHistory).length : 0 })) })), null, 2)); await prisma.$disconnect(); } main().catch(e => { console.error(e); process.exit(1); });"
```

Expected:

- The newest session has `messageCount > 0`.
- The newest session has `taskCount > 0`.
- The latest task has `writingSessionId` equal to the session id.
- `conversationHistory` remains populated separately from visible messages.

- [ ] **Step 5: Final commit if verification-only adjustments were needed**

If verification required minor fixes:

```bash
git status --short
git add prisma/schema.prisma src/agents/lib/message-service.ts src/agents/graph/workflow-runner.ts src/app/api/writing/session/route.ts src/app/api/writing/resume/route.ts src/app/api/writing/sessions/[id]/route.ts src/shared/contracts/sse-events.ts src/features/writing/writing-conversation.tsx src/features/writing/session-task-state.ts src/agents/AGENTS.md
git commit -m "fix: stabilize writing session persistence verification"
```

If no files changed, do not create an empty commit.

## Self-Review Checklist

- Spec coverage:
  - `WritingTask.writingSessionId` relation: Task 1.
  - Server-side visible message persistence: Tasks 2, 4, 7.
  - `/api/writing/session` binding and auth: Task 3.
  - Session selection returns `currentTask`: Task 5.
  - Frontend restore and resume direction: Task 6.
  - Documentation update: Task 8.
  - Verification: Task 9.
- No plan step requires reading `WritingMessage` to reconstruct LangGraph state.
- No task adds a parallel Agent workflow or bypasses LangGraph.
- User-visible persistence remains separate from `ReviewArtifact` formal write paths.
