# Agent 当前架构规范

本文件是 `src/agents/**` 的当前架构权威。历史长 changelog 已归档到 `docs/archive/agent-history/AGENTS-v8-changelog-and-notes.md`，不得作为新开发依据。

铁律：本文必须服从当前代码事实。若本文与 `src/agents/**`、`src/shared/contracts/**`、`prisma/schema.prisma` 或测试冲突，先核对代码事实，再修正文档。

## 当前主路径

```text
用户消息
  -> initSession
  -> CreativeOperation 分类
  -> operationWorkflow
  -> 主责 Agent 执行
  -> ReviewArtifact 草案或直接回复
  -> reviewer 复审 / patch / rewrite / block
  -> awaitUserDecision
  -> 用户应用 / 继续修改 / 丢弃
  -> 正式落库或结束
```

核心文件：

| 领域 | 当前入口 |
| --- | --- |
| 父图 | `src/agents/graph/graph-definition.ts` |
| 创作操作图 | `src/agents/operations/operation-graph.ts` |
| 操作定义 | `src/agents/operations/operation-definition.ts` |
| 操作路由 | `src/agents/operations/operation-router.ts` |
| Agent 定义 | `src/agents/graph/nodes/*.ts` |
| Agent 运行管道 | `src/agents/runtime/agent-runner.ts` |
| Tool-call loop | `src/agents/runtime/agent-runtime.ts` |
| 模型适配 | `src/agents/runtime/model-runtime.ts` |
| 工具注册 | `src/agents/tools/registry.ts` |
| ReviewArtifact | `src/agents/artifacts/**` |
| Graph state | `src/agents/graph/state.ts` |
| SSE 契约 | `src/shared/contracts/sse-events.ts` |

## 核心 Agent

| Agent ID | 节点 | 当前职责 |
| --- | --- | --- |
| 设定 | `graph/nodes/lore-advisor-node.ts` | 设定体系、角色、世界观、势力、地点、物品、术语、设定同步 |
| 剧情 | `graph/nodes/plot-advisor-node.ts` | 主线、大纲、章节职责、伏笔、Beat Plan、剧情结构 |
| 写作 | `graph/nodes/author-node.ts` | 正文草案、续写、改写、对白、场景样稿 |
| 校验 | `graph/nodes/validator-node.ts` | 一致性校验、设定冲突、草案复审 |
| 编辑 | `graph/nodes/editor-node.ts` | 商业性、追读、节奏、爽点、章节尾钩、草案复审 |

Agent 是执行角色，不是入口抽象。入口必须先识别 `CreativeOperation`，再由操作定义决定主责 Agent、reviewer、草案策略和用户确认策略。

## CreativeOperation

当前操作定义在 `src/agents/operations/operation-definition.ts`，操作类型来自 `src/shared/contracts/creative-operation.ts`。

| 操作 | 主责 | reviewer | 草案 |
| --- | --- | --- | --- |
| 回答问题 | 编辑 | 无 | 否 |
| 新建设定 / 修改设定 / 同步设定 | 设定 | 校验 | `agent_updates` |
| 创建大纲 / 修改大纲 | 剧情 | 编辑 | `agent_updates` |
| 规划章节 | 剧情 | 编辑 | `beat_plan_draft` |
| 生成正文草案 / 改写场景草案 | 写作 | 校验、编辑 | `chapter_draft` |
| 审核章节 | 编辑 | 无 | 否 |
| 管理伏笔 | 剧情 | 校验 | `agent_updates` |

新增创作流程时优先扩展：

1. `src/shared/contracts/creative-operation.ts`
2. `src/agents/operations/operation-definition.ts`
3. `src/agents/operations/operation-router.ts`
4. `src/agents/operations/operation-graph.ts`
5. `src/shared/contracts/sse-events.ts` 和前端处理

不要退回“用户选择 Agent -> Agent 自己决定流程”的旧模式。

## 输出协议

当前唯一 Agent 输出模式是：

```ts
paragraph_text_with_control_tools
```

规则：

- assistant 可见正文只能是自然段文本。
- 控制信息只能来自 OpenAI-compatible tool calls。
- 禁止恢复 JSON 信封，例如 `{"content": "...", "updates": ...}`。
- 禁止从 assistant 正文解析路由、评分、保存请求、返工结论或草案字段。
- 禁止新增 `---META---`、HTML 注释、Markdown 表格等替代控制协议。
- 长文本产物必须走 ReviewArtifact 文本边界或 update builder 的文本块机制，不把长正文塞进 tool arguments。

`AgentDefinition.outputMode` 只允许 `paragraph_text_with_control_tools`。旧 `response-parser.ts`、`legacy_json`、`parseOutput` 主路径已删除。

## Control Tools

工具统一注册在 `src/agents/tools/registry.ts`。AgentRunner 按 `AgentDefinition.toolCapabilities` 和工具 `permission.agentIds` 暴露工具。

主要 control tools：

| Tool | 作用 |
| --- | --- |
| `propose_updates` | 提交短小结构化更新草案 |
| `start_update_builder` | 开始或打开批量更新草稿箱 |
| `append_update_batch` | 追加短结构化更新 |
| `append_outline_tree` | 追加三层结构化大纲树 |
| `put_update_text_block` | 写入总纲、世界设定、故事背景等长文本 |
| `put_update_item_text_block(s)` | 给结构化 item 挂载长文本 |
| `finish_update_builder` | 校验并提交 `agent_updates` 草案 |
| `begin_artifact_output` | 提交文本类 ReviewArtifact 草案 |
| `submit_quality_report` | 提交编辑/质量评分 |
| `submit_validation_report` | 提交一致性冲突报告 |
| `submit_beat_plan` | 提交章节 Beat Plan 草案 |
| `submit_evaluation` | reviewer 提交 pass / revise / block |

约束：

- control tool 是控制面事件，不是直接写库工具。
- mutating 工具不得暴露给模型直接写正式表。
- 未暴露工具被模型调用时，runtime 必须拒绝。
- 参数校验失败时，runtime 返回字段级错误和最小示例；连续失败必须终止本轮并显示未保存变更。

## ReviewArtifact

Agent 产物写正式库前必须进入 ReviewArtifact。

允许链路：

```text
proposal/text output
  -> ReviewArtifact revision
  -> reviewer submit_evaluation
  -> patch/rewrite/block/pass
  -> awaiting_user
  -> 用户 approve/revise/discard
  -> applyReviewArtifact 或删除草案
```

禁止：

- Agent 直接写正式小说表。
- 把待审核草案默认混入正式小说上下文。
- 使用 `WritingTask.generatedContent` 作为新草案状态源。
- 用户丢弃后保留“废弃草案”污染当前查询。

`artifactReview` 是 Graph state 中的权威草案状态；旧 `activeArtifactId` 等字段只是兼容 facade。

## LangGraph 状态与恢复

父图在 `graph-definition.ts`：

```text
START -> initSession -> operationWorkflow -> END
                  \-> statusReport -> END
```

状态规则：

- 使用 `StateSchema`、`ReducedValue`、`UntrackedValue`。
- `novelData`、SSE callbacks、runtime context、controlEvents 是 runtime-only，不进入可恢复快照。
- `conversationHistory` 和 `agentOutputs` 是可恢复业务状态。
- `MemorySaver` 只做当前进程内 interrupt/resume 优化。
- 持久恢复以 `WritingTask.graphStateJson` 为准。
- 等待用户确认的 checkpoint 有 TTL；终态、断连、应用、丢弃、异常后按 taskId 清理。

写作会话恢复只认：

```text
WritingSession -> WritingTask.writingSessionId -> WritingTask.graphStateJson
```

禁止按小说、章节或时间窗猜测任务归属。`WritingMessage` 只负责用户可见聊天记录，不用于反推 LangGraph 状态。

## 上下文与大纲

写作上下文由 `src/shared/lib/context-aggregator.ts` 和 `src/agents/graph/context-builder.ts` 生成。

当前规则：

- 新建项目必须确定 `WritingBible.storyLengthProfile`：`short_medium` 或 `long_serial`。
- Agent 上下文必须注入篇幅模式、目标字数和策划重点。
- `OutlineNode.kind` 只有三层：`stage`、`plot_unit`、`chapter_group`。
- `chapterStartOrder/chapterEndOrder` 是章节映射权威，禁止从标题猜章号。
- 作家上下文按 approved Beat Plan、ChapterWritingGoal、唯一命中当前章的 `chapter_group` 选择。
- 无映射、范围重叠或重复命中时，必须在模型调用前阻断。
- 只读工具结果和复审证据不得静默截断；容量不足时显式失败。
- RAG 只读召回通过 `semantic_search_references`，索引是 `ReferenceMaterial` 的可重建派生数据，不是事实主库。

## 日志与调试

人工排查入口：

```text
logs/workflow-events/runs/YYYY-MM-DD/<task短号>.log
```

当前人工日志只保留两类内容：

- LLM 输入 messages 原文、模型输出正文原文和 token 消耗。
- LangGraph 中文状态切换。

LLM 部分按 `Axx` 分组，只渲染 `REQUEST` / `RESPONSE`。人工日志不展开 tools schema、供应商 reasoning、模型 tool calls、工具参数或工具返回；`TOOL_CALL`、`AGENT_RUN_FINAL` 与 `agent_done.content` 不进入人工日志。

人工日志文件延迟到第一条可见 LLM 记录或第一个 LangGraph 状态出现后才创建；审批、丢弃等既没有 LLM 调用也没有 LangGraph 状态变化的短路操作不创建空壳文件。

机器 JSONL 默认关闭，仅在显式设置 `WORKFLOW_MACHINE_EVENT_LOG_ENABLED=true` 时生成。

LangGraph Studio：

- 配置：`langgraph.json`
- 图入口：`src/agents/graph/studio-app.ts`
- 启动：`npm run studio:dev`
- 输入生成：`npm run studio:input`

Studio 运行会真实创建或更新 `WritingTask`、`ReviewArtifact` 和 evaluation；正式章节正文仍必须经过用户确认应用。

## 修改检查表

修改 Agent / 写作工作流时至少检查：

1. `src/shared/contracts/creative-operation.ts`
2. `src/agents/operations/**`
3. `src/agents/graph/state.ts`
4. `src/agents/graph/graph-definition.ts`
5. `src/agents/graph/nodes/*.ts`
6. `src/agents/runtime/**`
7. `src/agents/tools/registry.ts` 和具体工具
8. `src/agents/artifacts/**`
9. `src/shared/contracts/sse-events.ts`
10. `src/features/writing/**`
11. `docs/requirements/03-ai-writing-and-agents.md`
12. `docs/requirements/04-review-quality-and-workflow.md`

修改共享协议、SSE、control tool、ReviewArtifact 状态机或 LangGraph 路由后，必须同步检查本文。

## Python 重构阶段边界

当前迁移分支已由 `apps/core-api/src/inkforge_core/writing/**` 接管写作会话、消息、
WritingTask 稳定快照、浏览器 SSE 重放和签名智能体回调；由
`apps/core-api/src/inkforge_core/reviews/**` 接管 ReviewArtifact 修订、复审结论、用户决策
和正式应用。智能体工具只能通过签名的 Core 工具网关读取上下文或草案，并同时校验
智能体白名单与用户、小说、任务绑定。

`apps/agent-service/src/inkforge_agents/**` 已接管五个智能体定义、系统提示词、能力矩阵、
工具参数契约、显式模型提供方和唯一多轮工具循环。模型运行时只执行一次供应商调用；
智能体运行时负责完整可见文本累积、只读工具并发、控制事件捕获、终止工具和越权拒绝。
控制工具仍只生成结构化事件，不执行正式写入。

在任务 19 删除旧后端前，`src/agents/**` 仍作为行为迁移依据，但不得再成为 Python
服务的持久化入口。Python 智能体服务不得连接数据库，正式写入继续只发生在 Core。
