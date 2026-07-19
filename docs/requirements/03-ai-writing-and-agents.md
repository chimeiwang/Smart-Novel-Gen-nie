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
| manage_foreshadowing 管理伏笔 | 剧情 | 是 | 是 |
| develop_short_outline 生成或修改中短篇大纲 | 剧情 | 是 | 是 |
| write_short_story 生成或修改中短篇整稿 | 写作 | 是 | 是 |

`sync_lore` 已从当前可执行操作中删除。共享类型暂时保留该标识，仅用于解析历史任务快照；前端、关键词路由和分类器不得创建新的同步设定任务。

兼容规则：

- 用户使用 @设定、@剧情、@写作、@校验、@编辑 前缀时，系统映射为对应 Agent 的默认 CreativeOperation。
- 无法稳定识别时，回退为 answer_question。
- 上述分类和前缀兼容只适用于 `long_serial`。`short_medium` 必须由 Core 显式指定 `develop_short_outline` 或 `write_short_story`；Agent Service 不根据“短篇”“整稿”“全文”等关键词猜测。

中短篇专用流程、强类型草案和兼容边界见 `docs/specs/2026-07-18-short-medium-writing-workflow.md`。

## Operation 执行流程

下图的 Reviewer 并行扇出适用于 `long_serial` 和其他非中短篇草案流程。`short_medium` 大纲不自动复审；中短篇整稿固定串行执行“编辑 → 校验”，要求返工时最多自动生成一次完整新稿后再串行复审。

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
    I -->|"有"| J["reviewArtifact 向全部 Reviewer 并行扇出"]
    J --> K["mergeArtifactReviews 合并全部复审结论"]
    K --> L{"合并结果"}
    L -->|"pass"| M["awaitUserDecision"]
    L -->|"revise"| O["reviseArtifact 完整返工"]
    O --> H
    L -->|"block"| M
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

入口：`POST /api/v1/writing/runs`，成功返回 202，以及任务标识、命令标识和命令状态。

请求字段：

- clientRequestId；
- novelId；
- chapterId；
- writingSessionId；
- workflowKind；
- operation；
- targetWordCount；
- selectedAgents；
- userMessage。

业务规则：

- novelId 和 chapterId 必填。
- workflowKind、operation 必须与 WritingBible 的 `storyLengthProfile` 匹配，并写入持久命令和稳定快照；不匹配时在模型调用前拒绝。
- `short_medium` 只接受 `develop_short_outline`、`write_short_story`；篇幅参考可以为空，填写时必须为 6000～80000。实际正文由故事完整性决定并保持中短篇类型边界；`long_serial` 继续支持现有操作和聊天路由。
- 用户必须登录。
- 小说必须属于当前用户。
- 如果传 writingSessionId，会话必须属于同一小说、同一章节和当前用户。
- 默认 targetWordCount 为 4000。
- selectedAgents 为空时使用默认 Agent 列表。
- selectedAgents 会持久化到 WritingTask，但入口仍以 CreativeOperation 决定主责 Agent，不允许退回“只按用户选择 Agent 编排流程”的旧模式。
- Core 在同一数据库事务中保存 `WritingTask` 和 `WritingRunCommand`，再尝试投递；Redis 暂时不可用时请求仍以 pending 命令被可靠受理。
- 同一用户重复提交相同 clientRequestId 必须返回原命令，不得创建重复任务。

### 继续写作 workflow

入口：`POST /api/v1/writing/runs/{taskId}/resume`，成功返回 202。

用途：

- 继续普通聊天；
- 回复章节目标确认。

业务规则：

- taskId 必填。
- clientRequestId 必填，用于幂等受理。
- 用户必须登录。
- task 必须属于当前用户。
- 如果传 writingSessionId，必须与任务已绑定会话一致；未绑定历史任务不能在恢复时静默绑定到当前会话，只能在不携带 writingSessionId 的项目待办入口中单独处理。
- 草案批准、丢弃和返工由 `POST /api/v1/review-artifacts/{artifactId}/decision` 单独受理；前端不能再先决定、再调用 resume。

### 持久化命令

启动、普通恢复和草案决定都先写入 PostgreSQL `WritingRunCommand`。命令状态为 pending、submitted、processing、succeeded 或 failed；同一任务同一时刻最多存在一条活动命令。dispatcher 使用命令 ID 作为稳定队列 job ID，失败后按退避时间补投，Core 重启后也能继续处理到期命令。

智能体事件、检查点、完成和失败回调使用协议 `1.1`，必须携带产生回调的 `jobId`。Core 在任何任务、命令或快照写入前按 `taskId + jobId` 锁定并复核当前命令；已经被新命令取代的旧 job 回调只记录稳定错误码并幂等返回，不得污染新命令或用户事件。检查点中的 `eventSequence` 必须与回调序号一致并且只能单调前进。

没有持久命令的历史 active/waiting_call 任务在对账时先于任务行锁内创建唯一 `WritingRunCommand`，再由标准 dispatcher 使用命令 ID 投递；命令建立后旧 legacy job 立即失效。没有活动命令时也只允许最新终态命令重试原回调，不能让更早的历史命令重新获得身份。

草案决定接口把正式数据变更、草案状态或删除以及 `artifact_decision` 命令放在同一外层事务中。接口成功返回 202 后，前端只连接返回 taskId 的 SSE，Agent 恢复负责推进图状态和终态回调，不得再次应用或删除正式草案。

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
- 前端按任务保存最后一个事件 ID，重连时发送 `Last-Event-ID`，并拒绝不符合共享事件契约的载荷。
- 断流后应能从会话和任务状态恢复待审核草案。

## 工具调用边界

Agent Runtime 是唯一多轮 tool-call loop。

工具要求：

- 工具统一从注册表暴露。
- 每次调用显式声明 `primary`、`reviewer`、`reviser` 或 `quality` 执行模式，不能根据是否存在草案推断角色。
- AgentRunner 只能暴露当前 Agent toolCapabilities、CreativeOperation 工具白名单和执行模式白名单的交集。
- 工具自身 permission.agentIds 继续做服务端校验。
- Runtime 拒绝本轮未暴露的 tool call。
- 只读且并发安全的工具可以并行；control 或不安全工具必须按顺序执行。
- 每个 Operation 声明允许工具、终止控制工具、产物事件、产物类型和 artifactKey 策略；错误事件、错误 kind、变化的 artifactKey 或冲突终止产物必须在提交 Core 前失败。
- 更新构建器只允许在单次运行中启动一次；启动后隐藏开始工具，后续追加和完成必须沿用同一 `artifactKey`。跨一次纠正重试合并事件时，重复开始不得覆盖已经追加的更新。
- 新建/修改设定只使用通用更新构建器，不暴露 `append_outline_tree`；只有创建/修改大纲和管理伏笔可以追加结构化大纲树。
- 设定 Agent 调用 `propose_updates` 或 `finish_update_builder` 成功后立即结束本轮工具循环。
- reviewer 不暴露读取工具，只能接收 Core 权威草案并调用一次 `submit_evaluation`；reviser 使用原 Operation 工具契约，接收原草案、revision、artifactKey 和合并后的修改要求后生成同类新 revision。
- consistency 质量任务由“校验”Agent 的 `quality` 模式执行，只暴露 `submit_quality_report`。

控制工具示例：

- propose_updates：提交短小更新草案。
- update builder 系列：构建批量 AgentUpdates 草案。
- append_outline_tree：仅在大纲和伏笔 Operation 中提交 stage → plotUnits → chapterGroups 嵌套大纲树。
- submit_quality_report：提交固定结构的一致性终检报告。
- submit_validation_report：保留的通用冲突报告工具；当前 quality 模式不使用。
- submit_beat_plan：提交章节 Beat Plan。
- submit_evaluation：提交草案复审结论。

## Agent 产物规则

- 可见输出是自然段文本。
- 控制信息通过 tool calls 提交。
- 不再从 Agent 可见正文解析 JSON 信封、路由字段或评分字段。
- 设定/大纲/伏笔/正文/Beat Plan 等正式变更必须进入 ReviewArtifact。
- `plan_chapter` 只能提交 Beat Plan，`write_chapter/rewrite_scene` 只能提交 `chapter_draft`，长篇设定/大纲/伏笔 Operation 只能提交 `agent_updates`。中短篇 `develop_short_outline` 提交强类型 `outline_draft`，`write_short_story` 提交带来源元数据的 `chapter_draft`。
- reviewer 的任何修改请求统一进入完整 rewrite；保留具体修改意见，但不执行跨服务局部 patch。
- 职责外任务只能在正文说明边界，不得通过越权工具硬写草案。

## 模型消息、上下文与恢复

模型输入统一由运行时构造，顺序为：静态 Agent system prompt、服务端 Operation/模式 system brief、只读作品资料 user 消息、当前轮之前的历史消息、唯一当前 user 消息。作品正文、设定、参考资料和历史 system 记录都不能成为当前 system 指令；当前用户请求只能出现一次。

Operation 的 `contextStrategy` 只生成最小投影：`brief` 提供任务、小说和章节摘要；`lore` 提供设定摘要索引；`outline` 提供大纲、节点、剧情进度、章节组、outlinePath 和伏笔摘要；`chapter` 提供当前章、相邻章摘要、章节目标、已批准 Beat Plan、outlinePath 和相关人物摘要；`review` 提供当前章及必要审阅资料。详细内容由只读工具按需获取，完整聚合 `workspace` 不进入稳定快照。

中短篇使用独立的最小上下文组装器。改纲时按“用户本轮直接编辑、修改要求原文、已确认锚点、当前完整大纲、原始灵感、最近对话”的顺序裁决；最近对话只用于理解指代，不能覆盖前五项。全部历史继续持久化，但不把几十轮聊天全部注入模型。整稿只读取已批准大纲、锚点、必要设定、文风、可选篇幅参考、6000～80000 类型边界和本轮整稿修改要求；篇幅参考不得成为凑字或压字指令。

中短篇会话可以显式附加项目级大纲或正文版本，也可以在用户原文中使用“大纲 v2”“正文第 3 版”等无歧义表达。Core 必须在模型调用前解析并校验精确 Artifact、revision 与 hash，把完整版本载荷按高于当前稿和最近对话的优先级注入；不存在、类型不清或多个修改基线冲突时明确失败，禁止静默回退最新版。

`get_recent_chapters` 是按需读取最近章节正文的只读工具，必须由 Agent 显式调用；`count` 可选且范围为 `1..20`，省略时 Core 默认读取 3 章。基础上下文不自动注入任何最近章节正文。该工具不扩大现有 RAG 每份资料 64 块容量或 `topK`，也不改变 embedding 回调协议。

写作处理器在初次运行、命令恢复和当前 job 快照恢复时附加仅运行时 `runtimeContext`，其中 `RunResource.runId/jobId` 只来自当前 QueueJob。Agent 执行、工具、草案创建、评审和草案水合统一使用该身份；`runtimeContext` 在稳定快照序列化前移除，不能成为可恢复业务状态。

恢复自动复审、自动返工或用户 revise 决定前，Agent Service 使用 Core `planning.activeArtifact` 水合权威草案并校验 task、novel、chapter、kind、artifactKey 与 revision；Core 已事务处理的 approve/discard 不要求草案继续存在。进程内草案记录只在等待态 checkpoint、完成回调或失败回调成功后，按同一 `runId/jobId` 释放。

Agent Service 使用 `MODEL_MAX_OUTPUT_TOKENS` 表达当前部署模型的单次最大输出能力，默认 `384000`，合法范围为 `1..1_000_000`；普通 Agent 与文风画像共用该值。它不是目标篇幅，不要求模型必须生成到该长度，也不承诺无限输出。

计费模型调用仍先向 Core 申请有限正整数 grant；Core 可以按可用余额缩小额度，`ModelRuntime` 校验授权后把实际 `maxOutputTokens` 精确传给 Provider，任何调用都不得绕过授权上限。

Provider 必须提供规范化完成原因并保留供应商原始值。`length`、`content_filter`、`stop`/`tool_calls` 与实际工具状态矛盾、以及没有合法工具调用的 `unknown` 都在接受正文或执行工具副作用前失败，当前不把 `length` 作为自动续写信号；文风画像只接受 `stop`、无工具调用且正文非空的纯文本响应，半截画像不能成功。人工模型日志记录规范化值和完整原始值。

上述输出与上下文能力不修改 PostgreSQL schema、公共 OpenAPI 或 ReviewArtifact 状态机。

## 验收标准

- 用户发送普通问题时，系统能直接回复，不生成草案。
- 用户要求写正文时，系统生成 chapter_draft 草案，并经过校验和编辑复审。
- 用户要求设定或大纲变更时，系统生成 agent_updates 草案。
- 中短篇从显式 Operation 进入专用流程，可以反复修改完整大纲；大纲批准前不能生成整稿。
- 中短篇每个首稿或返工轮次只调用一次作家模型并输出完整正文；一次用户发起的整稿运行最多首稿加一次自动返工，即最多两个整稿生成轮次、两次作家调用。供应商截断时当前轮次整体失败，不保存半稿、不续写、不拼接。
- 前端能看到 Operation 分类、Agent 过程、草案卡片和用户决策入口。
- 用户刷新或重新打开会话后，能恢复消息和待审核草案入口。
- 未登录或越权用户不能启动或恢复写作任务。

## Python 重构阶段实现

- Core API 已提供 `/api/v1/writing/sessions`、消息、运行启动、恢复和事件流接口。
- 写作事件使用短期 Redis Stream 保存，支持 `Last-Event-ID` 重放、来源事件去重和序号缺口对账；没有 Redis 的测试环境使用同契约内存实现。
- 智能体事件、检查点、完成和失败只接受可信网段内的 Ed25519 签名内部回调；签名请求体和来源幂等标识都包含 `jobId`。
- Redis 事件序号键丢失时，Core 先用 PostgreSQL 当前命令身份和持久检查点授权，再允许当前 job 从持久序号后重建基线；旧 job 或小于等于持久序号的事件不能抬高、回退或重置基线。
- 回调按“精确身份授权、Redis 序号预检、PostgreSQL 二次锁定并持久化、Redis Lua 原子发布”执行；数据库已成功而首次发布失败时，同一来源事件能够幂等补发。
- 同一 job 已保存 `completed/error` 快照后，Agent 重试必须从持久序号直接重放 completion/failure，不能重新执行图或重新生成正文；failure 回调自身的 5xx、超时或断线保留可重试语义。
- Agent 图返回 `phase=error` 时，Agent Service 保存错误快照并调用失败回调，不得发送完成回调。
- 稳定快照写入 `WritingTask.graphStateJson`，并拒绝 `runtime`、回调、聚合作品数据和控制事件等仅运行时字段。
- Python 智能体服务已迁移五个智能体定义、系统提示词、能力与工具白名单、严格工具参数校验和唯一多轮工具循环；模型运行时仍只负责单次供应商调用。
- 只读且并发安全的工具可以并行执行，控制工具按模型调用顺序生成结构化事件；未暴露工具、无效参数和最大轮次均明确终止，不截断用户可见文本。
- Python LangGraph 已迁移 CreativeOperation 路由、复审 `Send` 扇出、四种显式执行模式、确定性复审优先级、rewrite-only 返工、最大修订次数、用户中断和 `Command` 恢复；图状态快照使用版本信封并排除 `runtimeContext` 等运行时字段。
- OperationDefinition 已成为工具、终止事件、产物 kind 和 artifactKey 的运行契约；reviewer 无读取工具，reviser 只基于 Core 权威草案返工，错误产物不会静默兜底。
- OpenAI-compatible Provider 已把规范化和原始完成原因传入 Runtime 与人工日志；长度截断、内容过滤、矛盾完成原因和非法 unknown 响应不会被当成成功。
- Core API 已把写作启动、恢复和草案决定先保存为 PostgreSQL 持久命令，再由 dispatcher 提交到 Redis 队列。文风画像以 `StylePortraitTask`、质量检查以 `WorkflowRun(kind=quality_check)`、资料索引以 `RagDocument` 的待重建状态作为持久事实；各自 dispatcher 使用稳定任务标识补投，Redis 只承载可重建的投递状态。Agent Service 消费任务并通过签名回调保存检查点、事件、草案和终态。
- 草案进入等待用户确认时，Agent Service 先发送 `artifact_awaiting_user_approval` SSE 事件，再保存带有最新事件序号的稳定快照；前端据此刷新待确认草案。
- Core 对账器可以强制修复 Redis 中缺失的 queued 索引或完全丢失的运行键，但不得重新打开 Redis 已记录为 completed、failed 或 cancelled 的运行。
- Agent Service 不连接数据库，所有读取工具和业务写入都通过 Core 内部工具网关完成。
