# AI 写作与 Agent 需求

## 目标

为作者提供可持续的 AI 创作协作能力。系统需要把用户的自然语言请求识别为创作操作，选择主责 Agent 执行，并通过流式事件把过程、草案和用户确认状态展示给前端。

## 核心 Agent

| Agent ID | 名称 | 职责 |
| --- | --- | --- |
| 设定 | 设定顾问 | 讨论、评价、创建和维护角色、世界观、势力、物品、术语等设定。 |
| 剧情 | 剧情顾问 | 处理主线、章节职责、角色行动链、伏笔生命周期、节奏结构和 Beat Plan。 |
| 写作 | 作家 | 生成整章、续写、改写、对白、场景样稿和局部桥段。 |
| 校验 | 校验员 | 检查正文、角色设定、大纲、世界观、伏笔和剧情逻辑的一致性。 |
| 编辑 | 网文编辑 | 评价作品定位、角色卖点、大纲潜力、正文追读、爽点节奏和章节尾钩。 |

默认启用全部五个 Agent。

## 创作操作

聊天入口的主抽象是 CreativeOperation，而不是直接把用户消息等同于某个 Agent。

操作类型：

| 操作 | 主责 Agent | 是否生成草案 | 是否需用户确认 |
| --- | --- | --- | --- |
| answer_question 回答问题 | 编辑 | 否 | 否 |
| create_lore 新建设定 | 设定 | 是 | 是 |
| revise_lore 修改设定 | 设定 | 是 | 是 |
| create_outline 创建大纲 | 剧情 | 是 | 是 |
| revise_outline 修改大纲 | 剧情 | 是 | 是 |
| plan_chapter 规划章节 | 剧情 | 是 | 是 |
| write_chapter 生成正文草案 | 写作 | 是 | 是 |
| rewrite_scene 改写场景草案 | 写作 | 是 | 是 |
| review_chapter 审核章节 | 编辑 | 否 | 否 |
| sync_lore 同步设定 | 设定 | 是 | 是 |
| manage_foreshadowing 管理伏笔 | 剧情 | 是 | 是 |

兼容规则：

- 用户使用 @设定、@剧情、@写作、@校验、@编辑 前缀时，系统映射为对应 Agent 的默认 CreativeOperation。
- 无法稳定识别时，回退为 answer_question。

## Operation 执行流程

~~~mermaid
flowchart TD
    A["用户发送消息"] --> B["initSession 识别 CreativeOperation"]
    B --> C["operationWorkflow"]
    C --> D["prepareOperationContext 准备上下文"]
    D --> E["executeOperation 执行主责 Agent"]
    E --> F{"是否需要草案"}
    F -->|"否"| G["直接回复聊天流"]
    F -->|"是"| H["submitArtifactOrRespond 提交 ReviewArtifact"]
    H --> I{"是否有复审 Agent"}
    I -->|"有"| J["reviewArtifact 复审"]
    J --> K{"复审结果"}
    K -->|"pass"| L{"是否还有下个 reviewer"}
    L -->|"有"| J
    L -->|"无"| M["awaitUserDecision"]
    K -->|"revise patch"| N["applyArtifactPatch 小修"]
    N --> J
    K -->|"revise rewrite"| O["reviseArtifact 返工"]
    O --> E
    K -->|"block"| M
    I -->|"无"| M
    M --> P["用户批准/修改/丢弃"]
    P --> Q["suggestNextAction"]
~~~

## 写作会话

### 会话列表

用户可以按小说和章节查询写作会话。

每个会话包含：

- 会话 ID；
- 小说 ID；
- 章节 ID；
- 标题；
- 阶段；
- 创建时间；
- 更新时间；
- currentTask：显式绑定且非终态的可继续任务；
- lastTask：completed/error 终态任务的只读历史摘要。

### 创建会话

用户可以创建写作会话。

业务规则：

- 必须登录。
- 必须校验小说归属。
- 章节必须属于该小说。
- 可以传入标题。

### 会话详情

会话详情需要返回：

- 会话基础信息；
- 消息列表；
- currentTask；
- lastTask；
- 当前 Operation；
- 当前阶段；
- activeArtifactId；
- 可恢复的待审核草案入口。

### 消息持久化

系统保存用户可见消息。

字段：

- sessionId；
- role：user、agent、system；
- agentId；
- content；
- intent；
- metadata；
- parentId。

用途：

- 恢复聊天 UI；
- 保存 Agent 可见的用户交互摘要；
- 不负责反推 LangGraph 状态。

## 写作请求 API

### 启动写作 workflow

入口：`POST /api/v1/writing/runs`，成功返回 202 和任务标识。

请求字段：

- novelId；
- chapterId；
- writingSessionId；
- targetWordCount；
- selectedAgents；
- userMessage。

业务规则：

- novelId 和 chapterId 必填。
- 用户必须登录。
- 小说必须属于当前用户。
- 如果传 writingSessionId，会话必须属于同一小说、同一章节和当前用户。
- 默认 targetWordCount 为 4000。
- selectedAgents 为空时使用默认 Agent 列表。
- selectedAgents 会持久化到 WritingTask，但入口仍以 CreativeOperation 决定主责 Agent，不允许退回“只按用户选择 Agent 编排流程”的旧模式。

### 继续写作 workflow

入口：`POST /api/v1/writing/runs/{taskId}/resume`，成功返回 202。

用途：

- 继续普通聊天；
- 审批草案；
- 丢弃草案；
- 继续修改草案；
- 回复章节目标确认。

业务规则：

- taskId 必填。
- 用户必须登录。
- task 必须属于当前用户。
- 如果传 writingSessionId，必须与任务已绑定会话一致；未绑定历史任务不能在恢复时静默绑定到当前会话，只能在不携带 writingSessionId 的项目待办入口中单独处理。

## 会话恢复

~~~mermaid
flowchart TD
    A["用户打开写作会话"] --> B["读取 WritingSession"]
    B --> C["读取 WritingMessage"]
    B --> D["查找绑定 WritingTask"]
    D --> E{"任务是否有待审核草案"}
    E -->|"有"| F["读取 ReviewArtifact 并显示草案卡片"]
    E -->|"无"| G["恢复普通聊天状态"]
    D --> H["读取 graphStateJson"]
    H --> I["恢复 operation、stage、activeArtifactId"]
~~~

恢复原则：

- WritingMessage 用于用户可见聊天记录。
- WritingTask.graphStateJson 用于恢复 LangGraph 状态。
- currentTask 只来自 WritingSession 显式绑定的非终态 task。
- completed/error 任务只能作为 lastTask 历史摘要，不得成为恢复接口的默认句柄。
- 未绑定历史 task 不能在恢复时静默绑定到当前 session。
- 进程内 checkpointer 只提供短时优化，不是唯一恢复来源。

## SSE 事件

写作 workflow 通过 SSE 向前端报告过程。

主要事件：

| 类别 | 事件 |
| --- | --- |
| 基础 | start、done、completed、error、resume |
| Agent | agent_start、agent_status、agent_chunk、agent_done |
| 路由 | classifying_intent、intent_classified、operation_classified、operation_stage、command_parsed |
| 用户交互 | user_input_required、phase_start、phase_change |
| 草案 | artifact_submitted、artifact_review_started、artifact_awaiting_user_approval、artifact_applied、artifact_deleted、review_artifact_requested |
| 更新构建器 | update_builder_started、update_builder_batch_appended、update_builder_outline_tree_appended、update_builder_text_put、update_builder_validation_failed 等 |
| 兼容/状态 | updates_saved、updates_declined、call_confirmed、call_declined、agent_insights、proactive_suggestions、state_update、status_report |

前端需求：

- 显示当前 Operation 和阶段。
- 显示 Agent 开始、状态、工具摘要、流式正文和完成状态。
- 不把 Agent 聊天正文当 Markdown 解析，按普通段落文本渲染。
- 草案事件只刷新聊天流草案卡片；审核弹窗由用户主动打开。
- 断流后应能从会话和任务状态恢复待审核草案。

## 工具调用边界

Agent Runtime 是唯一多轮 tool-call loop。

工具要求：

- 工具统一从注册表暴露。
- AgentRunner 只能暴露当前 Agent toolCapabilities 允许的工具。
- 工具自身 permission.agentIds 继续做服务端校验。
- Runtime 拒绝本轮未暴露的 tool call。
- 只读且并发安全的工具可以并行；control 或不安全工具必须按顺序执行。

控制工具示例：

- propose_updates：提交短小更新草案。
- update builder 系列：构建批量 AgentUpdates 草案。
- append_outline_tree：提交 stage → plotUnits → chapterGroups 嵌套大纲树。
- submit_quality_report：提交质量评分。
- submit_validation_report：提交一致性报告。
- submit_beat_plan：提交章节 Beat Plan。
- submit_evaluation：提交草案复审结论。

## Agent 产物规则

- 可见输出是自然段文本。
- 控制信息通过 tool calls 提交。
- 不再从 Agent 可见正文解析 JSON 信封、路由字段或评分字段。
- 设定/大纲/伏笔/正文/Beat Plan 等正式变更必须进入 ReviewArtifact。
- 职责外任务只能在正文说明边界，不得通过越权工具硬写草案。

## 验收标准

- 用户发送普通问题时，系统能直接回复，不生成草案。
- 用户要求写正文时，系统生成 chapter_draft 草案，并经过校验和编辑复审。
- 用户要求设定或大纲变更时，系统生成 agent_updates 草案。
- 前端能看到 Operation 分类、Agent 过程、草案卡片和用户决策入口。
- 用户刷新或重新打开会话后，能恢复消息和待审核草案入口。
- 未登录或越权用户不能启动或恢复写作任务。

## Python 重构阶段实现

- Core API 已提供 `/api/v1/writing/sessions`、消息、运行启动、恢复和事件流接口。
- 写作事件使用短期 Redis Stream 保存，支持 `Last-Event-ID` 重放、来源事件去重和序号缺口对账；没有 Redis 的测试环境使用同契约内存实现。
- 智能体事件、检查点、完成和失败只接受可信网段内的 Ed25519 签名内部回调。
- 稳定快照写入 `WritingTask.graphStateJson`，并拒绝 `runtime`、回调、聚合作品数据和控制事件等仅运行时字段。
- Python 智能体服务已迁移五个智能体定义、系统提示词、能力与工具白名单、严格工具参数校验和唯一多轮工具循环；模型运行时仍只负责单次供应商调用。
- 只读且并发安全的工具可以并行执行，控制工具按模型调用顺序生成结构化事件；未暴露工具、无效参数和最大轮次均明确终止，不截断用户可见文本。
- Python LangGraph 已迁移 CreativeOperation 路由、复审 `Send` 扇出、确定性复审优先级、补丁或重写返工、最大修订次数、用户中断和 `Command` 恢复；图状态快照使用版本信封并排除运行时字段。
- Core API 已把启动、恢复、画像、质量检查和 RAG 任务提交到 Redis 持久队列；Agent Service 消费任务并通过签名回调保存检查点、事件、草案和终态。
- Core 对账器可以强制修复 Redis 中缺失的 queued 索引或完全丢失的运行键，但不得重新打开 Redis 已记录为 completed、failed 或 cancelled 的运行。
- Agent Service 不连接数据库，所有读取工具和业务写入都通过 Core 内部工具网关完成。
