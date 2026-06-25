# Workflow Event 本地日志格式

本文档定义 LangGraph 写作工作流的本地审计日志格式。日志采用 JSON Lines，每行是一条独立事件，便于后续按 `runId`、`taskId`、`node`、`agentId` 或 `eventType` 过滤和回放。

## 文件位置

默认目录：

```text
logs/workflow-events/
```

默认文件名：

```text
workflow-events-YYYY-MM-DD.jsonl
```

`logs/` 已在 `.gitignore` 中忽略，本地审计日志不会进入版本库。

可视化回放页面：

```text
/debug/workflow-events
```

页面默认关闭并返回 404，避免误触发本地日志扫描。需要查看本地 JSONL 回放时，在 `.env` 中设置 `WORKFLOW_EVENT_DEBUG_ENABLED=true` 后重启 Next.js 开发服务器。页面会读取本地 JSONL 日志，展示运行列表、LangGraph 固定节点图、实际执行路径高亮、事件时间线和单步状态 payload。

可选环境变量：

```bash
WORKFLOW_EVENT_LOG_ENABLED=false
WORKFLOW_EVENT_DEBUG_ENABLED=false
WORKFLOW_EVENT_LOG_DIR=/absolute/path/to/workflow-events
WORKFLOW_EVENT_LOG_DETAIL=verbose
```

- `WORKFLOW_EVENT_LOG_ENABLED=false`：关闭本地 workflow event 日志。
- `WORKFLOW_EVENT_DEBUG_ENABLED=false`：关闭 `/debug/workflow-events` 调试入口，关闭时返回 404；需要查看日志回放时设为 `true`。
- `WORKFLOW_EVENT_LOG_DIR`：覆盖默认日志目录。
- `WORKFLOW_EVENT_LOG_DETAIL=verbose`：记录更深层的状态 patch 内容，字符串 preview 提高到 4000 字符，数组 sample 提高到 20 项；适合本地深查，但日志会明显变大。

## 写入原则

- append-only：只追加，不在运行中修改历史行。
- best-effort：写入失败不能影响 LangGraph 执行、SSE 输出或数据库写入。
- 默认不保存完整正文、完整 `novelData`、完整 prompt、完整对话历史。
- 大字段会被摘要化，保留类型、长度、键名和有限 preview。
- `agent_chunk` 不落盘，避免流式正文逐字写爆日志。
- 如需查看更完整的每步状态内容，打开 `WORKFLOW_EVENT_LOG_DETAIL=verbose` 后重新执行工作流；历史日志不会自动补全。

## 顶层字段

```ts
interface WorkflowEventLogEntry {
  schemaVersion: number;
  runId: string;
  seq: number;
  timestamp: string;
  source: "workflow" | "langgraph" | "sse" | "persistence" | "error";
  eventType: string;
  taskId: string;
  runKind: "writing-workflow" | "resume-writing-workflow";
  userId?: string | null;
  novelId?: string | null;
  chapterId?: string | null;
  qualityCheckId?: string | null;
  node?: string | null;
  agentId?: string | null;
  langGraphEvent?: string | null;
  changedKeys?: Record<string, string[]> | string[];
  payload?: unknown;
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `schemaVersion` | 当前为 `1`。后续格式变化时递增。 |
| `runId` | 单次 SSE 工作流运行 ID。同一个 `taskId` 可以有多次 `runId`。 |
| `seq` | 单次 `runId` 内从 `1` 开始递增的事件序号。 |
| `timestamp` | ISO 时间。 |
| `source` | 事件来源。 |
| `eventType` | 事件类型，例如 `workflow_started`、`updates`、`agent_done`。 |
| `taskId` | `WritingTask.id`，用于关联一次写作任务。 |
| `runKind` | 新会话执行或 resume 执行。 |
| `userId` / `novelId` / `chapterId` | 业务上下文。resume 早期事件可能缺少 `novelId` / `chapterId`，加载任务后补齐。 |
| `qualityCheckId` | 如果本次工作流来自章节质量检查，则记录检查项 ID。 |
| `node` | LangGraph 节点名或 SSE state update 节点名。 |
| `agentId` | 业务 Agent ID，例如 `写作`、`校验`、`编辑`。 |
| `langGraphEvent` | 原始 LangGraph event 名称。 |
| `changedKeys` | 状态变更字段。`updates` 事件按节点分组。 |
| `payload` | 摘要化 payload。 |

## source 类型

| source | 含义 |
|---|---|
| `workflow` | 工作流生命周期事件，例如开始、完成、中断、resume 模式选择。 |
| `langgraph` | `graph.streamEvents()` 返回的原始事件摘要。 |
| `sse` | 后端向前端发送的 SSE 业务事件摘要。 |
| `persistence` | 显式记录的本地持久化或数据库副作用摘要。 |
| `error` | 工作流运行器捕获的错误或鉴权失败等异常路径。 |

## 当前会记录的事件

`workflow`：

- `sse_stream_created`
- `workflow_started`
- `workflow_interrupted`
- `workflow_completed`
- `resume_started`
- `resume_mode_selected`
- `resume_completed`

`langgraph`：

- `updates`
- `custom`
- `on_custom_event`
- `interrupt`
- 其他 LangGraph 事件会以原始 `event` 名称记录。

`sse`：

- `start`
- `state_update`
- `agent_start`
- `agent_done`
- `intent_classified`
- `command_parsed`
- `artifact_submitted`
- `quality_report_submitted`
- `validation_report_submitted`
- `done`
- `error`
- 其他通过 SSE 发给前端的业务事件。

`persistence`：

- `history_loaded`
- `history_saved`
- `task_state_updated`
- `artifact_applied`
- `artifact_deleted`

`error`：

- `workflow_runner_error`
- `task_not_found`
- `task_auth_failed`

## 示例

```json
{"schemaVersion":1,"runId":"task_123-1780000000000-ab12cd","seq":1,"timestamp":"2026-06-17T10:00:00.000Z","source":"workflow","eventType":"workflow_started","taskId":"task_123","runKind":"writing-workflow","userId":"user_1","novelId":"novel_1","chapterId":"chapter_1","qualityCheckId":null,"payload":{"novelId":"novel_1","chapterId":"chapter_1","targetWordCount":1200}}
{"schemaVersion":1,"runId":"task_123-1780000000000-ab12cd","seq":6,"timestamp":"2026-06-17T10:00:01.000Z","source":"langgraph","eventType":"updates","taskId":"task_123","runKind":"writing-workflow","userId":"user_1","novelId":"novel_1","chapterId":"chapter_1","qualityCheckId":null,"langGraphEvent":"updates","changedKeys":{"initSession":["conversationHistory","activeAgent","callChainDepth"]},"payload":{"data":{"initSession":{"conversationHistory":{"type":"array","length":1,"sample":[{"type":"object","keys":["id","role","content","timestamp"]}]},"activeAgent":"写作","callChainDepth":0}}}}
{"schemaVersion":1,"runId":"task_123-1780000000000-ab12cd","seq":9,"timestamp":"2026-06-17T10:00:02.000Z","source":"sse","eventType":"agent_done","taskId":"task_123","runKind":"writing-workflow","userId":"user_1","novelId":"novel_1","chapterId":"chapter_1","qualityCheckId":null,"agentId":"写作","payload":{"agentId":"写作","agentName":"作家","durationMs":3220,"hasOutput":true,"content":{"type":"string","length":1800,"preview":"正文已自动保存到章节...","truncated":true},"insights":{"type":"array","length":0,"sample":[]}}}
```

## 查询建议

按一次请求回放：

```bash
rg '"runId":"task_123-1780000000000-ab12cd"' logs/workflow-events
```

按任务查看所有运行：

```bash
rg '"taskId":"task_123"' logs/workflow-events
```

只看状态变更：

```bash
rg '"source":"langgraph".*"eventType":"updates"' logs/workflow-events
```

只看持久化副作用：

```bash
rg '"source":"persistence"' logs/workflow-events
```
