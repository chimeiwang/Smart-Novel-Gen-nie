# AGENTS.md

本文件为 Codex 在本仓库中工作时提供指导。

**重要：后续所有对话必须使用简体中文。回答要清晰、诚实、明确；不要为了迎合用户而忽略事实。**

## Codex 开发流程

在本仓库中，Codex 的首要目标不是“尽快手写一个能跑的局部方案”，而是**顺着现有架构扩展项目**。开始实现前必须先判断变更类型，并查找已有能力。

### 动手前必须做

- 改 UI / CSS / 交互状态前：先阅读根目录 `DESIGN.md`；它是以 Linear 为主参考、Vercel 为辅助参考的前端设计主规范。
- 改 Agent、写作流程、质量评审、商业性评估、设定同步、伏笔管理前：先阅读 `docs/AGENT_NOVEL_WRITING_ROADMAP.md` 和 `src/agents/AGENTS.md`。
- 改数据库模型或持久化逻辑前：先确认 `prisma/schema.prisma` 当前 PostgreSQL schema，不要被旧 SQLite 迁移或 `dev.db` 误导。
- 改共享协议、SSE、Agent control tool、ReviewArtifact 状态机或 LangGraph 路由后：必须同步更新 `src/agents/AGENTS.md`；如果影响仓库级准则，也更新本文件。
- 实现前优先用 `rg` 搜索已有入口、同名能力、测试和契约，确认是否可以扩展现有模块。

### 复用优先索引

开发 Agent / 写作工作流相关功能时，必须优先检查并复用这些既有能力：

- Agent 编排：`src/agents/graph/graph-definition.ts`
- Graph 状态与 Agent ID：`src/agents/graph/state.ts`
- Agent 声明式配置：`src/agents/runtime/agent-definition.ts`
- 统一运行入口：`src/agents/runtime/agent-runner.ts`
- Agent 工具循环与控制事件捕获：`src/agents/runtime/agent-runtime.ts`
- 模型单轮运行时适配：`src/agents/runtime/model-runtime.ts`
- control event 处理：`src/agents/graph/control-event-processor.ts`
- 工具注册表：`src/agents/tools/registry.ts`
- read / proposal / control tools：`src/agents/tools/**`
- ReviewArtifact 草案、复审、应用：`src/agents/artifacts/**`
- SSE 契约：`src/shared/contracts/sse-events.ts`
- 前后端共享 Zod 契约：`src/shared/contracts/**`
- 写作会话前端展示与 SSE 处理：`src/features/writing/**`

如果已有能力能覆盖需求，应扩展现有入口；只有现有抽象无法表达需求时，才新增模块，并在最终说明中解释原因。

### 禁止默认新增的平行实现

- 不要手写新的 Agent while / switch 流程状态机。
- 不要绕过 LangGraph `StateGraph`、conditional edges、`Command`、`Send`、`interrupt()` 做自定义编排。
- 不要绕过 `src/agents/tools/registry.ts` 临时拼 OpenAI tools 数组。
- 不要绕过 `ReviewArtifact` 让 Agent 直接写正式小说表。
- 不要从 Agent 可见正文中解析控制指令、JSON 信封、路由字段或评分字段。
- 不要新增与 `src/shared/contracts`、`src/agents/graph/state.ts` 重复的本地 schema / 类型。
- 不要把待审核草案默认混入正式小说上下文；只有 `artifactReview.activeArtifactId`（旧 `activeArtifactId` facade 仅兼容）或显式 artifact read tool 才能读取草案。
- 不要把历史兼容规则扩散成新规则，例如 `novel.userId = null` 只用于兼容旧数据，`WritingTask.generatedContent` 只作为旧待审核 artifact 标记 fallback。

## 项目要点

InkForge（墨铸）是面向中文小说作者的本地创作工具，包含项目/章节管理、设定管理、文风画像、AI 续写、写作会话、质量检查、待审核草案和多 Agent 协作。

当前主数据库是 PostgreSQL；Prisma datasource 以 `prisma/schema.prisma` 为准。仓库中保留的早期 SQLite 迁移和 `dev.db` 只是历史遗留。

## 常用命令

```bash
npm run dev          # 开发服务器，端口 43119
npm run build        # 生产构建
npm run lint         # ESLint
npm run typecheck    # TypeScript 检查
npm run db:generate  # 生成 Prisma Client
npm run db:migrate   # 运行迁移
npm run studio:dev   # LangGraph Studio/Agent Server 本地调试入口；默认关闭，需 LANGGRAPH_STUDIO_ENABLED=true
npm run studio:input # 生成 Studio 可运行的完整 GraphState 输入
```

生产或 PostgreSQL 专用命令以 `package.json` 为准，必要时再查看脚本，不在这里重复展开。

### LangGraph Studio 调试

- Studio 配置文件为 `langgraph.json`，图入口为 `src/agents/graph/studio-app.ts`，只导出现有 `getGraph()` 编译结果，不新增平行 Agent 编排。
- Studio 输入可用 `npm run studio:input -- --novel-id <id> --chapter-id <id> --user-id <id> --message "..."` 生成；该脚本会创建一条调试用 `WritingTask`，并复用生产上下文聚合逻辑。
- `npm run studio:dev` 默认不会启动 LangGraph Agent Server；需要 Studio 调试时先在 `.env` 设置 `LANGGRAPH_STUDIO_ENABLED=true`，再运行该命令。
- Studio 启动后运行的是 LangGraph Agent Server，不是 Next.js 应用；它适合看节点、状态、interrupt/resume 和 LangSmith trace。
- Studio 运行会真实执行 Graph 节点，可能创建/更新 `ReviewArtifact` 和 `WritingTask`。正式章节正文仍必须经过待审核草案和用户确认应用后才写入。
- 写作会话恢复以 `WritingSession -> WritingTask.writingSessionId -> WritingTask.graphStateJson` 为主链路；`WritingMessage` 只负责用户可见聊天记录，不用于反推 LangGraph 状态。`MemorySaver` 只作为当前进程内 interrupt/resume 优化，不是生产级恢复来源；等待确认 checkpoint 默认 5 分钟 TTL，断连、异常和终态按 taskId 清理。

## 技术栈

- Next.js 16 + App Router、React 19、TypeScript strict
- Prisma 6 + PostgreSQL
- OpenAI SDK 兼容 API，默认接入 DeepSeek
- LangChain / LangGraph / LangSmith / Zod
- 原生 CSS + CSS 自定义属性；项目无 Tailwind
- Ant Design 作为依赖存在，但新增 UI 优先遵循本项目原生 CSS 风格

## 目录速览

```text
src/
├── app/                         # App Router 页面、API 路由、Server Actions
├── agents/                      # 多 Agent 系统：graph/runtime/tools/artifacts/lib
├── features/                    # 前端功能组件
└── shared/                      # contracts、db、env、通用 lib
```

详细 Agent 流程、协议和变更日志以 `src/agents/AGENTS.md` 为准。

## 通用开发规则

- **服务端变更**：普通数据变更优先使用 `src/app/actions.ts` Server Actions；流式写作、会话消息、质量检查走 `src/app/api/*` 路由。
- **鉴权**：涉及小说、写作任务、会话、质量检查的接口必须校验 `userId` 归属；历史 `novel.userId = null` 只做兼容访问。
- **路径别名**：`@/*` 映射到 `./src/*`。
- **状态管理**：无全局状态库；使用服务端数据、SSE 事件和组件本地状态。
- **Prisma 单例**：复用 `src/shared/db/prisma.ts`，不要新建 PrismaClient 单例。
- **中文优先**：界面、提示、错误、Agent 可见文本和用户内容以中文为主。

## 前端规则

- 新增或修改 UI 前必须先读根目录 `DESIGN.md`。
- 使用原生 CSS + 自定义属性，优先复用 `globals.css` 中的 `.panel`、`.stack`、`.button`、`.badge`、`.input`、`.textarea`、`.select` 等类。
- 本项目 PC 优先，不写移动端响应式方案；不同桌面屏幕通过 `minmax`、flex、grid 等方式自适应。
- 章节正文编辑器是 `textarea`；自动保存延迟为 1.2 秒。
- 字数统计使用 `countTextLength()`，去除空白字符。
- 当前 Agent 聊天正文按普通段落文本渲染，不使用 ReactMarkdown 解析。

## Agent 系统规则

所有 Agent 位于 `src/agents/`，统一从 `src/agents/index.ts` 导出。根文档只写开发护栏；详细流程图、控制协议和变更日志看 `src/agents/AGENTS.md`。

### 当前核心 Agent

| Agent ID | Node 文件 | 身份 |
|---------|-----------|------|
| 设定 | `graph/nodes/lore-advisor-node.ts` | 设定体系架构师 |
| 剧情 | `graph/nodes/plot-advisor-node.ts` | 剧情结构顾问 |
| 写作 | `graph/nodes/author-node.ts` | 正文创作者 |
| 校验 | `graph/nodes/validator-node.ts` | 一致性审计员 |
| 编辑 | `graph/nodes/editor-node.ts` | 网文商业编辑 |

### LangChain / LangGraph / 自研层边界

- LangChain 当前主要承接模型 runtime 适配、结构化调用和单轮 tool-call turn。
- LangGraph 承接 CreativeOperation 路由后的执行编排、状态、路由、interrupt、短流程恢复和后续可扩展的 checkpointer 能力。
- 项目自研层包括 `AgentDefinition`、`AgentRunner`、control tools、ReviewArtifact、SSE 协议和业务契约。
- 新能力应扩展这些既有层，不要另起一套 Agent 框架或流程引擎。
- `AgentRuntimeImpl` 是唯一多轮 tool-call loop 和 control tool 捕获层；`ModelRuntimePort` 只做模型供应商适配，不解析 `propose_updates`、`submit_evaluation` 等业务控制事件。

### CreativeOperation 入口

- 当前聊天入口先识别 `CreativeOperation`，再选择内部执行 Agent；Agent 是执行角色，不是入口层唯一抽象。
- Operation 契约在 `src/shared/contracts/creative-operation.ts`，包含操作类型、目标、主责 Agent、预期产物、是否需要草案和用户确认。
- `@设定/@剧情/@写作/@校验/@编辑` 前缀仍兼容，但也必须映射为默认 Operation。
- 前端通过 `operation_classified` SSE 事件展示当前操作状态；旧 `intent_classified`/`command_parsed` 仅作为兼容事件继续保留。
- 新增创作流程时优先扩展 Operation 契约、Graph state 和 ReviewArtifact 链路，不要把入口逻辑重新退回“只选 Agent”。

### v7 Agent 协议

- Agent 节点采用声明式 `AgentDefinition`，通过 `runAgent()` 进入统一执行管道。
- 当前输出模式是 `paragraph_text_with_control_tools`：可见正文是自然段文本；控制信息必须通过 OpenAI tool calls。
- 不再使用旧 JSON 信封协议承载 `wantsToCall`、`updates`、`scores`、`conflicts` 等字段。
- `callLLMWithTools()` 仍可服务非 Agent 的历史调用；当前 AgentRuntime 主路径不复用它。

主要 control tools：

| Tool | 作用 |
|------|------|
| `propose_updates` | 生成短小的待审核更新草案 |
| `start_update_builder` | 开始或打开批量 AgentUpdates 草稿箱 |
| `append_update_batch` | 向草稿箱批量追加结构化变更 |
| `append_outline_tree` | 向草稿箱追加嵌套大纲树，由服务端展开为 outlineAdjustments |
| `put_update_text_block` | 写入 `outlineContent` / `worldSetting` / `storyBackground` 长文本 section |
| `finish_update_builder` | 完成草稿箱构建，统一校验并提交待审核草案 |
| `submit_quality_report` | 提交编辑/质量评分 |
| `submit_validation_report` | 提交一致性冲突报告 |
| `submit_beat_plan` | 提交章节 Beat Plan 摘要 |
| `submit_evaluation` | 对 ReviewArtifact 提交 pass/revise/block 复审 |

Agent 间流程跳转不再通过 control tool 表达。入口路由由 `CreativeOperation` 分类决定，审核、返工、用户确认由 `operationWorkflow` 的 LangGraph 节点和 conditional edges 决定。Agent 发现职责外需求时只能在正文中说明边界和缺口，不得自行转交。

AgentRunner 只能向模型暴露当前 Agent 的 `toolCapabilities` 允许的工具，并且必须尊重工具自身的 `permission.agentIds` 白名单；禁止把所有 control tools 无条件给所有 Agent。Runtime 还会拒绝本轮未暴露的 tool call。复审中要求返工时使用 `submit_evaluation(revise)` 和 `requiredChanges`，由 LangGraph 返工边把 brief 交给主责 Agent。

### LangGraph 编排

当前主结构在 `src/agents/graph/graph-definition.ts`：

```text
START → initSession → operationWorkflow 创作操作图 → END
                 └→ statusReport → END
```

- `initSession` 负责识别创作操作，并写入 `currentOperation`。
- `operationWorkflow` 位于 `src/agents/operations/operation-graph.ts`，按“识别创作操作 → 准备操作上下文 → 执行创作操作 → 提交草案或直接回复 → 审核草案 → 返工草案 → 等待用户决策 → 建议下一步”推进。
- 使用 `StateGraph`、`StateSchema`、conditional edges、`Command`、`interrupt()` 和 `MemorySaver`。`MemorySaver` 仅用于当前进程内短流程，不是生产级停机恢复承诺；等待确认 checkpoint 的保留时长由 `LANGGRAPH_MEMORY_SAVER_TTL_MS` 控制。runtime-only 数据必须用 `UntrackedValue` 或 runtime context，不能进入可恢复快照。
- 新增多 Agent 循环、人工确认、动态分派、并行子任务或长流程恢复时，必须优先使用 LangGraph 原生能力。

### 工具层与 ReviewArtifact

- 工具统一注册在 `src/agents/tools/registry.ts`。
- 工具按能力域分组：`read/`、`proposals/`、`control/`。
- 新增或修改 control tool 时，要同步检查各 Agent 的 `toolCapabilities`，并补充工具暴露测试，确认非主责 Agent 看不到越权工具。
- Agent 可落库修改必须先进入 `ReviewArtifact` 待审核草案；正式写库由用户确认后通过服务端应用。
- 设定 Agent 只允许保存设定类 section；剧情 Agent 只允许保存大纲/伏笔类 section；服务端会再次校验。

### 结构化大纲规则

- `Outline.content` 是全书总纲文本；`OutlineNode` 是结构化大纲树；`PlotProgress` 是当前写作指针；`ChapterBeatPlan` 只服务当前章写前规划。
- `OutlineNode.kind` 只允许三层：`stage`（阶段/卷）、`plot_unit`（剧情单元）、`chapter_group`（章节组）。
- 层级约束：`stage` 只能顶层；`plot_unit` 只能挂在 `stage` 下；`chapter_group` 只能挂在 `plot_unit` 下。
- 聊天流里生成、展开或重构结构化大纲时，剧情 Agent 应提交 `agent_updates` 草案：`outlineContent` 更新总纲，最终由 `outlineAdjustments` 更新节点树；短小变更可用 `propose_updates`，批量节点树、长总纲或复杂重构必须使用 update builder 工具链。
- 复杂大纲树主路径必须使用 `append_outline_tree`，只提交 `stage → plotUnits → chapterGroups` 嵌套树，不得提供 `parentId`、`parentKey`、`clientKey`；服务端负责展开为合法 `outlineAdjustments`。
- 只有短小修补、已有节点更新或兼容旧流程才直接提交 `outlineAdjustments`。手写创建大纲节点时，必须通过 `outlineAdjustments[].kind` 标明节点类型，并提供 `title` 或 `nodeTitle`；同一草案创建父子节点时用 `clientKey/parentKey` 临时引用，已有父节点才用 `parentId`，不得同时提供 `parentId` 和 `parentKey`。
- `estimatedWordCount` / `actualWordCount` 是辅助规划字段，不作为结构化大纲通过的硬门槛；核心门槛是节点类型、父子关系、标题和必要内容是否清楚。
- 所有结构化大纲变更继续走 `ReviewArtifact` 待审核草案链路，不能用纯文本 `outline_draft` 替代节点树。

## SSE 与共享契约

SSE 契约在 `src/shared/contracts/sse-events.ts`。新增或修改 SSE 事件必须先更新共享契约，再同步前端处理逻辑和相关测试。

常见事件类型包括：

- 基础：`start`、`done`、`completed`、`error`、`resume`
- Agent：`agent_start`、`agent_status`、`agent_chunk`、`agent_done`
- 路由：`classifying_intent`、`intent_classified`、`command_parsed`
- 操作：`operation_classified`
- 用户交互：`user_input_required`、`updates_saved`、`updates_declined`
- 草案：`artifact_submitted`、`artifact_review_started`、`artifact_awaiting_user_approval`、`artifact_applied`、`artifact_deleted`
- 状态：`state_update`、`status_report`、`phase_start`、`phase_change`

## 按变更类型检查

### 修改 Agent / 节点 / 路由

至少检查：

1. `src/agents/graph/nodes/*.ts` 中的 `AgentDefinition`
2. `src/agents/graph/nodes/index.ts` 导出
3. `src/agents/graph/state.ts` 的 Agent ID、输出字段和共享类型
4. `src/agents/graph/graph-definition.ts` 的节点注册、别名路由、conditional edges / Command
5. `src/agents/tools/registry.ts` 与具体 read / proposal / control 工具
6. `src/shared/contracts/*` 中的 Zod 契约
7. `src/features/writing/*` 中的前端展示和 SSE 处理
8. `src/agents/AGENTS.md` 与本文件是否需要同步更新

### 修改工具

- 在 `src/agents/tools/registry.ts` 注册或复用工具。
- 入参必须使用 Zod schema。
- 明确权限元信息：readOnly、concurrencySafe、requiresConfirmation、capability。
- control tool 要检查 `src/shared/contracts/agent-control.ts`、AgentDefinition capability 声明、runtime 解析测试和工具暴露测试。

### 修改 ReviewArtifact / 写库链路

- 保持 `proposal → ReviewArtifact → evaluation / revision → user approval → apply` 链路。
- 不允许 LLM 工具直接写正式小说表。
- 用户丢弃草案时按现有 Artifact 规则处理，不新增旁路状态。

### 修改数据库

- 以 PostgreSQL schema 为准。
- 同步 Prisma schema、迁移、Server Actions / API、前端读取逻辑和必要测试。
- 不要基于旧 SQLite 文件推断当前模型。

## 测试与验证

- 修改共享 Agent 协议、runtime、LangGraph 路由或 control tools 时，优先查看并补充：
  - `src/agents/runtime/__tests__`
  - `src/agents/graph/__tests__`
  - `src/shared/contracts/__tests__`
  - `src/features/writing/__tests__`
- 修改前端时至少运行相关 lint / typecheck；必要时启动 `npm run dev` 做交互验证。
- 修改 Prisma schema 后运行相应 generate / migrate / push 命令，并说明使用的是哪条数据库路径。

## AI 配置

```bash
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-v4-flash
```

未配置 `OPENAI_API_KEY` 时，普通 AI 续写、文风画像、LLM wrapper 和 AgentRuntime 会返回 Mock 内容或提示。完整工具调用能力需要真实 API Key。

LangSmith 可选：

```bash
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=inkforge
LANGCHAIN_TRACING_V2=true
```
