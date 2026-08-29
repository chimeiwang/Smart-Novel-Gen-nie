# AI 写作与 Agent 需求

## 长篇章节影视化任务

旧 `VideoScene` 的选区创建、查询、重试、返工、批准和提示词预览公共接口已经退役。数据库表、内部回调、
dispatcher 和 Agent handler 只为已存在历史任务保留终态收敛能力，不得再形成新任务入口。

长篇视频工作台的新入口使用独立 `VideoChapterAdaptation`，不再把完整章节或镜头方案写入旧
`VideoScene.planJson`。`JobKind=video` 新增两个判别 workflow：

- `chapter_cinematic_adaptation_v2`：先识别真实 Scene、DramaticBeat 和观众覆盖目标，保存 Core 耐久 checkpoint，
  再设计有剪辑动机的 Shot，并经过连续性 Reviewer；最多一次完整返工。
- `chapter_shot_prompt_v2`：固定到一个已批准 `VideoShotPlanVersion`，只为请求镜头生成结构化即梦提示词规格。

提示词任务还必须按目标镜头冻结当前 `VideoShotVisualReferenceSet` 中的精确视觉版本，而不是只保存可变 Head 或图片
URL。每项包含 `canonVersionId/assetId/sha256/settingKind/settingId/duty/variantKey/strength`。Agent 不读取图片文件；
有 `identity/costume/scene/prop` 正式参考时，相应图片负责静态身份与造型，文字投影只保留主体名称、本镜必要锚点、
临时状态和可见变化。候选和正式 PromptVersion 都必须能重建自己采用的参考图集合。

逐镜提示词首次响应不是合法 JSON 结构，或没有通过正式时长、景别、重复与确定性编译门禁时，同一任务允许一次带
具体原因和 Schema 要求的纠正调用；第二次仍有 Schema、目标顺序、空字段、编译或预算硬错误时必须失败并返回可定位
原因，只有动作密度、重复、邻镜语言、不可见解释或未确认状态变化等语义质量问题时返回带 `qualityWarnings` 的可编辑
候选，不能从可见正文猜测结构、无限重试或保存部分提示词。调用纠正前允许执行有边界的确定性归一：移除编译器持有的画幅/时长、历史冗余字段、当前景别
不可见的表情、与正式动作直接冲突的负面约束，并将唯一冲突的显式景别词替换为正式中文标签；正式标签与一个冲突
标签并存且没有景别变化语义时可删除冲突词，主体与摄影机重复景别时只在摄影机保留。真正的运镜或景别变化不得
自动改写，也不得截断文本、改写动作或补造事件。
新候选按镜头内容选择性提交 `expressionAndGaze`：中景及更近可以写一个可见表情变化或明确视线目标，全景/大全景
只能写头部朝向、步态和身体张力；无人、物件和只见手部的镜头必须为空。历史 `performance/continuity` 继续兼容
读取，新模型不再请求；主体、动作、表情、摄影和声音不得重复堆叠同一信息。

提示词模型只读取目标镜头自己的正式 Scene、Beat、Shot、来源范围和本镜相关冻结设定，不接收完整章节正文或前后镜完整
事件。冻结设定先满足来源合法，再按本镜必要裁剪；当前镜头事实覆盖具体设定，具体设定覆盖全局风格，道具动态状态
只有本镜正式事实或来源明确发生时才能进入动作。批量任务必须按 `shotKey` 分别构建设定投影；人物外观按景别与本镜
明确锚点裁剪，近景不得携带鞋、全套服装或背包等画外信息。负面约束不得禁止完成正式动作所需的手部或正式主体，
但可明确排除其他人物或额外人物。500～2500ms、
3000～5000ms、5500～15000ms 镜头的编译文本
上限分别为 360、480、640 字；超限必须纠正或失败，不能静默截断。Agent 完成回调前必须按正式画幅和时长实际编译
每个候选，保证 Core 一定可以展示同一候选。

`visibleAction` 可以写正式主动作及其直接结果，但不得在来源未确认时追加再次、继续、反向操作或失败重试。
转动、旋转等物理变化必须来自本镜正式事实或来源，不能把道具静态设定改写成本镜动作。2500ms 及以下正式镜头若
自身包含四个以上可读信息单元，Agent 只附加延长/拆镜质量提醒，不要求提示词模型越权改写已确认镜头。
每个目标镜头上下文必须同时给出正式景别代码和产品中文标签；候选一旦显式写景别，必须与该标签一致，不能把
`close=近景` 当作“特写”等其他景别。

`negativeConstraints` 只承担禁止或避免，不得用“只保留、仅保留、允许出现”等正向要求补造画面。火花、火焰、
爆炸、闪电/电弧、粒子、光束/光柱、浓烟、雨雪和血迹等高成本视觉效果，必须能在当前正式 Scene/Beat/Shot、
来源范围、本镜相关设定投影或视觉参考包含特征中找到依据。首次无依据时使用同一轮已有纠正机会；纠正后仍存在
只形成非阻断 `qualityWarnings`，不得自动删除文字、补造来源或把语义问题升级为结构硬失败。

来源句末编号只用于 Unicode code point 锚定。说话人改变、句子结束、段落或换行不得直接产生镜头；一个对白
可跨多个画面，多句对白也可保留在一个主镜头或双人镜头。每个镜头必须提交目的、景别、机位、运镜、可见动作、
本镜作用、观众获得、目标绑定、来源关系、对白位置、声音设计、成片时长和具体切镜理由。Agent 候选不得直接写
正式关系表或 PromptHead。

场景首镜、景别变化、平均镜头时长、慢镜比例和空镜数量是软评估，不得成为确定性拒绝或服务端改写镜头的理由。
Reviewer 只有在核心情节目标缺失、与原文矛盾、时间线无法理解或单镜明显不可执行时要求完整返工一次；第二轮仍有
问题时返回带非阻断 findings 的候选交给作者。已有正式方案时，Core 可冻结当前方案作为修订基线，确认后只新增
`basedOnVersionId` 指向基线的正式版本。

镜头设计输出使用闭合 `beatsByKey`。模型沿用旧方案 Beat Key 时，只能按第一阶段 checkpoint 的精确 U 集合归位；
不得用自然语言关键词猜归属。大对象遗漏 Beat 时保留已完成槽位，并最多补全缺失槽，不要求整份重写。跨 Beat 的
G 绑定剔除并进入 finding；跨 Beat U 不能进入候选，无法保留合法来源的直呈/推导草案降为视听补充并提示作者。

场景/节拍 checkpoint 成功后，at-least-once 重试必须从该阶段继续，不能重复消费第一阶段模型调用。所有模型调用
继续经过 `ModelRuntime` 的计费授权、全局并发门和结构化输出日志脱敏。

逐镜真实视频生成不进入上述模型规划 workflow，也不复用旧 `VideoGenerationTask`。Core 使用
`VideoShotRenderTask` 保存冻结 prompt/ref/output manifest 和供应商状态，并由 PostgreSQL due index 恢复短轮询；
Agent 仅通过受签名内部接口执行一次 Seedance `submit/query`，不得重编译提示词、重排参考图或长期占用队列 worker。
创建响应不确定时任务进入 `submission_unknown`，Core 禁止自动重提；每次用户显式重试都创建可能再次计费的新任务。
供应商成功 URL 只用于当次受控归档，不持久化为播放事实；归档完成后才允许创建不可变 `VideoShotTake`。

关键帧、粗剪、声音、字幕与整集导出继续由 Core 持有，不新增“AI 导演”或媒体 Agent。Core 在创建
逐镜任务时把当前关键帧按首帧、过渡锚点、尾帧顺序冻结进 manifest，并生成不可变的供应商提示文本；
Agent 只能保持该顺序透传。FFmpeg 抽帧、剪辑和导出不经过模型运行时，也不允许 Agent 读取受控素材目录。
未来图片生成或 TTS 只能作为新的素材生产器接入，不能绕过素材权利、锁定、版本和人工确认链。

## 长篇选区改写契约

`rewrite_chapter_selection` 与 `rewrite_outline_selection` 必须提交 `selectionTarget`：资源类型与资源 ID、`baseUpdatedAt`、完整正文 `baseContentHash`、Unicode 码点范围 `selectionStart/selectionEnd` 以及 `selectedTextHash`。请求不得提交 `selectedText`；选区正文由 Core 根据权威来源和 hash 冻结，客户端字段只承担身份与范围绑定。章节正文选区只能指向对应 `chapterId`，大纲总纲/节点选区分别使用 `novel`/`outline_node` scope。

选区 Agent 产物仍必须走 `proposal -> ReviewArtifact -> 用户确认 -> Core 应用`。Agent 只生成 replacement，Core 在应用时再次校验来源绑定、范围和 hash，并保持选区外正文不变；CLI 不得绕过 Artifact 直接写入章节或大纲。普通 `plan_chapter` Beat Plan 与全文 `write_chapter`/`rewrite_scene` 草案继续使用原有完整草案语义。

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

## 中短篇专用执行链

`short_medium` 不进入长篇 CreativeOperation 的多 Agent 自动评审链。公开入口只接受
`generate_outline`、`generate_manuscript`、`replace_selection`、`full_check` 四种显式操作，
并由 Core 从权威来源素材、基础版本和当前应用蓝图组装不可变运行快照。浏览器和 CLI 不能提交
正文、来源文本或目标字数来替代服务端事实。

- 6000 到 15000 字正文允许一次模型生成；更长正文按蓝图顺序串行分段，禁止并行拼接。
- 每次文档操作只产生一个待用户采用的候选版本，不自动采用，也不自动启动下一阶段。
- 选区修改使用 Unicode 码点范围和选区 SHA-256 绑定基础版本；Agent 只返回 replacement，
  Core 确定性拼接并验证选区外内容逐字不变。
- 全文检查只返回报告，不创建候选版本。
- 模型提示必须使用创建任务时的不可变快照，不能用运行中的可变工作区上下文替换蓝图或正文。

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

`sync_lore` 已从当前可执行操作中删除。共享类型暂时保留该标识，仅用于解析历史任务快照；前端、关键词路由和分类器不得创建新的同步设定任务。

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
- 草案事件只触发 Core 权威草案刷新，不得直接把事件载荷恢复成可操作卡片；审核弹窗由用户主动打开。
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
- reviewer 不暴露读取工具，只能接收 Core 权威草案并调用一次 `submit_evaluation`；reviser 使用原 Operation 工具契约，接收原草案、revision、artifactKey 和合并后的修改要求后生成同类新 revision。`plan_chapter` 是事实核对特例：reviewer 与 reviser 同时接收主 Agent 生成草案时使用的冻结 `outline` 最小投影，但不得重新查询作品资料。
- consistency 质量任务由“校验”Agent 的 `quality` 模式执行，只暴露 `submit_quality_report`。
- 仅一致性终检的 `submit_quality_report` 使用 DeepSeek Beta strict Function Calling；Reviewer、Beat Plan、设定更新、视频和其他工具路由不因该通道改变。视频规划继续走 Responses `text.format=json_schema` 主链（`responses_json_schema_v1`），不使用 Beta strict。

队列 job 与单次 Operation 内并行使用同一个有界预算。2 核 2 GB 生产环境保持一个 Agent Uvicorn worker，默认最多同时处理三个不同 `novelId` 的独立 job，同一 `novelId` 同时只执行一个 job；同项目冲突的 claim 通过租约校验原子回队，成功回队时撤销本次 claim 增加的 attempts，且不等待项目锁占住执行槽。共享 `ModelRuntime` 把所有模型调用的全局峰值限制为三个。Reviewer `Send` 仍可并行，但与其他 job 重叠时也必须等待全局模型槽；`AGENT_MAX_CONCURRENCY=1` 可恢复严格串行。该并行不改变同一任务的命令身份、事件序号、检查点和 ReviewArtifact 顺序。

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
- `plan_chapter` 只能提交 Beat Plan，`write_chapter/rewrite_scene` 只能提交 `chapter_draft`，设定/大纲/伏笔 Operation 只能提交 `agent_updates`。
- Beat Plan 是简洁剧情骨架；节拍验收只表达一句可观察结果，不得重复作品设定、全局禁令、文风要求或专业规程。章节级验收可省略，需要时最多三条结果；权威上下文中的名称、时间和数值必须原样使用。
- reviewer 的 `revise + rewrite` 进入现有 Reviser 完整返工；全部结论为严格 `revise + patch` 时，进入确定性局部 patch 节点创建同一 ReviewArtifact 的新 revision，不调用 Primary 或 Reviser。patch 找不到、多命中、重叠、非章节目标或 `ARTIFACT_REVISION_CONFLICT` 时原子放弃并等待用户，不能静默升级为 rewrite；其他 Core、网络或协议错误作为运行错误上抛，不能伪装成内容不通过。
- 职责外任务只能在正文说明边界，不得通过越权工具硬写草案。

## 模型消息、上下文与恢复

模型输入统一由运行时构造，顺序为：静态 Agent system prompt、服务端 Operation/模式 system brief、只读作品资料 user 消息、当前轮之前的历史消息、唯一当前 user 消息。作品正文、设定、参考资料和历史 system 记录都不能成为当前 system 指令；当前用户请求只能出现一次。

Operation 的 `contextStrategy` 只生成最小投影：`brief` 提供任务、小说和章节摘要；`lore` 提供设定摘要索引；`outline` 提供大纲、节点、剧情进度、章节组、outlinePath 和伏笔摘要；`chapter` 提供当前章、相邻章摘要、章节目标、已批准 Beat Plan、outlinePath 和相关人物摘要；`review` 提供当前章及必要审阅资料。详细内容由只读工具按需获取，完整聚合 `workspace` 不进入稳定快照。

`get_recent_chapters` 是按需读取最近章节正文的只读工具，必须由 Agent 显式调用；`count` 可选且范围为 `1..20`，省略时 Core 默认读取 3 章。基础上下文不自动注入任何最近章节正文。该工具不扩大现有 RAG 每份资料 64 块容量或 `topK`，也不改变 embedding 回调协议。

写作处理器在初次运行、命令恢复和当前 job 快照恢复时附加仅运行时 `runtimeContext`，其中 `RunResource.runId/jobId` 只来自当前 QueueJob。Agent 执行、工具、草案创建、评审和草案水合统一使用该身份；`runtimeContext` 在稳定快照序列化前移除，不能成为可恢复业务状态。

恢复自动复审、自动返工或用户 revise 决定前，Agent Service 使用 Core `planning.activeArtifact` 水合权威草案并校验 task、novel、chapter、kind、artifactKey 与 revision；Core 已事务处理的 approve/discard 不要求草案继续存在。进程内草案记录只在等待态 checkpoint、完成回调或失败回调返回合法 `applied/already_applied` 凭证后，按同一 `runId/jobId` 释放。

Agent Service 使用 `MODEL_MAX_OUTPUT_TOKENS` 表达当前部署模型的单次最大输出能力，默认 `384000`，合法范围为 `1..1_000_000`；普通 Agent 与文风画像共用该值。它不是目标篇幅，不要求模型必须生成到该长度，也不承诺无限输出。

计费模型调用仍先向 Core 申请有限正整数 grant；模型授权生命周期为 1200 秒，供单次模型调用完成后上报实际用量，不改变内部服务请求令牌的短期约束。Core 可以按可用余额缩小额度，`ModelRuntime` 校验授权后把实际 `maxOutputTokens` 精确传给 Provider，任何调用都不得绕过授权上限。

billable Provider 成功响应形成 `ModelTurnResult` 后，Agent 使用同一调用的 `taskId`、`runId` 和 Core
计费 `requestId` 上报 `promptTokens`、`cachedTokens`、`completionTokens`、`totalTokens`，以及可选的
`promptCacheMissTokens`、`reasoningTokens` 诊断。只有 Core 成功接受 usage report 且配置了 observer，
人工模型日志才记录这些身份、provider/model、四项 usage、诊断结构头、完整 messages 与 output；
DeepSeek 原始 `reasoning_content` 只用于进程内工具轮次回放，绝不写入稳定快照、ReviewArtifact、Core
或日志正文。report 失败时异常向上传播，不留下该次模型区块。非 billable Provider 成功后直接调用
observer，但只有 observer 与运行 context 都存在时才写区块，并明确显示没有计费请求标识。
任何日志都不得记录 `grantToken`；Provider 在返回可靠 usage 前失败时不伪造 token。

Provider 必须提供规范化完成原因并保留供应商原始值。`length`、`content_filter`、`stop`/`tool_calls` 与实际工具状态矛盾、以及没有合法工具调用的 `unknown` 都在接受正文或执行工具副作用前失败，当前不把 `length` 作为自动续写信号；文风画像只接受 `stop`、无工具调用且正文非空的纯文本响应，半截画像不能成功。人工模型日志记录规范化值和完整原始值。

DeepSeek strict 通道仅在规范官方 HTTPS 根地址或 `/v1` 地址上自动派生 `/beta`；自定义地址、带端口或其他路径必须显式配置 `OPENAI_STRICT_BASE_URL`。strict 与非 strict 工具混用在 HTTP 请求前失败，不回退、自动重试或切换协议。在 `deepseek_v4` 配置下，`DeepSeekV4Provider` 发送的是兼容性投影 Schema，原始 `QualityReportArgs`/Pydantic 完整复验仍是业务权威，strict 不替代本地校验。质量协议错误日志可以保留安全大写 `failure_code`，但不得包含异常正文、工具参数或原始响应。

上述输出与上下文能力不修改 ReviewArtifact 状态机。模型用量归集只使用用户于 2026-08-21 和 2026-08-23
明确批准的两个 `TokenUsage` 有界版本化迁移，并新增按写作任务查询的公共 OpenAPI；不授权其他 PostgreSQL
结构调整。两个新增可空诊断字段的代码、契约和迁移脚本已实现，服务器 dev 迁移与 schema-contract 导出
仍属远程门禁，未在本地执行。

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
- 智能体事件、检查点、完成和失败只接受可信网段内的 Ed25519 签名内部回调；签名请求体和来源幂等标识都包含 `jobId`。
- Redis 事件序号键丢失时，Core 先用 PostgreSQL 当前命令身份和持久检查点授权，再允许当前 job 从持久序号后重建基线；旧 job 或小于等于持久序号的事件不能抬高、回退或重置基线。
- 普通过程事件和非边界 checkpoint 仍按“精确身份授权、Redis 序号预检、PostgreSQL 二次锁定并持久化、Redis Lua 原子发布”执行。相同来源标识只有在 sequence、事件类型和规范化数据完全一致时才视为安全重复，否则返回明确冲突；来源内容核验先于命令终态和持久序号短路。等待用户、完成和失败边界不依赖事务前 Redis：Core 在同一 PostgreSQL 事务内收敛业务事实并插入 `WritingEventOutbox`，提交后返回显式接收凭证；Publisher 再按稳定来源标识幂等写入 Redis Stream。Outbox 的 `durableBaseline` 只能取持有任务行锁后、修改本次事实前的 PostgreSQL 快照序号，不能由回调层按 `sequence - 1` 推测；相同来源、序号、终态幂等键或终态原始 result 对应不同事实时返回明确 rejected 回执。迁移前无命令的历史终态只接受可从任务字段严格核验的 completion result，无法核验的额外字段必须拒绝。
- 同一 job 已保存 `completed/error` 快照后，Agent 重试必须从持久序号直接重放 completion/failure，不能重新执行图或重新生成正文；failure 回调自身的 5xx、超时或断线保留可重试语义。
- Agent 图返回 `phase=error` 时，Agent Service 保存错误快照并调用失败回调，不得发送完成回调。
- 稳定快照写入 `WritingTask.graphStateJson`，并拒绝 `runtime`、回调、聚合作品数据和控制事件等仅运行时字段。
- Python 智能体服务已迁移五个智能体定义、系统提示词、能力与工具白名单、严格工具参数校验和唯一多轮工具循环；模型运行时仍只负责单次供应商调用。
- 只读且并发安全的工具可以并行执行，控制工具按模型调用顺序生成结构化事件；未暴露工具、无效参数和最大轮次均明确终止，不截断用户可见文本。
- Python LangGraph 已迁移 CreativeOperation 路由、复审 `Send` 扇出、四种显式执行模式、确定性复审优先级、rewrite/patch 分流、最大修订次数、用户中断和 `Command` 恢复；图状态快照使用版本信封并排除 `runtimeContext` 等运行时字段。确定性 patch 错误及 `ARTIFACT_REVISION_CONFLICT` 进入脱敏 `patchFailureCode` 的 `blocked`/`waiting_user`，不会调用 Reviser；其他 Core、网络或协议错误保持运行错误传播。
- OperationDefinition 已成为工具、终止事件、产物 kind 和 artifactKey 的运行契约；reviewer 无读取工具，reviser 只基于 Core 权威草案返工，错误产物不会静默兜底。
- OpenAI-compatible Provider 已把规范化和原始完成原因传入 Runtime 与人工日志；长度截断、内容过滤、矛盾完成原因和非法 unknown 响应不会被当成成功。
- 人工模型日志按 v2 长度分帧保存；Core 成功接受 usage report 后形成的 billable 模型调用区块，可用
  计费 `requestId` 与 `TokenUsage` 对账，report 失败不形成该次区块。日志正文不参与结构解析，旧版
  原文处于未验证边界，残缺尾部隔离后才恢复追加，完整输入输出不截断。
- Core API 已把写作启动、恢复和草案决定先保存为 PostgreSQL 持久命令，再由 dispatcher 提交到 Redis 队列。文风画像以 `StylePortraitTask`、质量检查以 `WorkflowRun(kind=quality_check)`、资料索引以 `RagDocument` 的待重建状态作为持久事实；各自 dispatcher 使用稳定任务标识补投，Redis 只承载可重建的投递状态。Agent Service 消费任务并通过签名回调保存检查点、事件、草案和终态。
- 草案进入等待用户确认时，Agent Service 使用下一个连续序号直接保存稳定快照，不再先直发等待事件；Core 在保存快照的同一事务中创建 `artifact_awaiting_user_approval` Outbox。后续 resume/artifact_decision 命令会在自身事务内作废尚未发布的旧 waiting，Publisher 遇到 waiting 序号竞争时也会再次核对并转为 superseded。长篇 completed/error 稳定 checkpoint 只保存图内终态，数据库任务和命令保持非终态，直到 complete/fail 与 terminal Outbox 在同一事务收敛。SSE 只重放 published 边界事件，跳过 superseded，并在 pending/delivering/blocked 边界前保留原游标等待；同时发送不带游标的 PostgreSQL `run_outcome` 控制帧。客户端在建连或断流后重新读取 outcome，只按 `streamShouldClose` 收敛生命周期，legacy 事件只承担展示兼容且不能直接恢复可操作草案；非 waiting_user 终态按任务清理临时草案入口并使较早的在途读取失效，相同 succeeded outcome 的完成副作用按任务、命令和结果只执行一次。
- Core 对账器可以强制修复 Redis 中缺失的 queued 索引或完全丢失的运行键，但不得重新打开 Redis 已记录为 completed、failed 或 cancelled 的运行。
- Agent 队列消费者已在单进程内提供默认三个执行槽，不同 `novelId` 可并行、同一 `novelId` 只执行一个 job，每个 claim 独立续租；共享 `ModelRuntime` 同时把普通 Agent、Reviewer、中短篇、质量和画像的模型调用总数限制为三个。消费槽致命错误会立即停止新领取并使 readiness 失败，其他已领取任务排空后由监督器重启；配置 1 保留串行回退路径。
- `ModelRuntime` 对授权、供应商和用量回报阶段只输出稳定错误码，并透传下游明确给出的重试决定。质量任务
  遇到明确可重试错误时保留活动运行并由队列重试；明确不可重试错误只有在 Core 失败回调成功后才按已知
  任务失败收敛，不得让整个消费者退出；未知程序异常继续触发监督器和 readiness 失败。分类日志只记录
  job/task/run/check、阶段、稳定错误码、异常类型和重试决定，不记录异常正文、模型输入、令牌或供应商响应。
- Agent Service 不连接数据库，所有读取工具和业务写入都通过 Core 内部工具网关完成。
- 生产模型请求使用显式 `ModelExecutionPolicy`：创作/完整重写使用 thinking enabled + high；Reviewer、Quality、问答、复审报告、中短篇 `full_check` 和文风画像使用 thinking disabled。DeepSeek 原始 transport 的 `reasoning_content` 仅用于进程内工具轮次回放，绝不进入稳定快照、ReviewArtifact、Core 用量或人工日志正文。
- `TokenUsage` 已在应用代码、共享契约和迁移脚本中支持可空 `promptCacheMissTokens`/`reasoningTokens`；服务器 dev 迁移、真实库只读 schema-contract 导出及生产部署仍是远程门禁，未在本地执行或宣称完成。
