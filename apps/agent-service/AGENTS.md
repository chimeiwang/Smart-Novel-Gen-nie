# 智能体服务架构

本文件描述 Python Agent Service 的当前边界。仓库级规则见根目录 `AGENTS.md` 和 `DOCS.md`。

## 服务职责

Agent Service 负责：

- 五个核心 Agent 的声明式定义与提示词；
- CreativeOperation 的 LangGraph 编排；
- 模型供应商适配和唯一多轮工具循环；
- 运行队列消费、检查点恢复和事件回调；
- 人工工作流日志。

Agent Service 不负责浏览器认证、数据库查询、正式业务写入、草案最终应用或计费落账。它不得接收 `DATABASE_URL`，不得导入 SQLAlchemy、asyncpg 或其他数据库客户端。

### 中短篇运行

- `short_medium` 只执行 `generate_outline`、`generate_manuscript`、`replace_selection` 和
  `full_check` 四种专用操作，不复用长篇多 Agent 自动评审链。
- 运行只信任 Core 随 QueueJob 提供的不可变来源、基础版本、当前蓝图和正文快照；不得用可变
  `coreContext` 覆盖它们。
- 6000 到 15000 字正文单次生成，超过 15000 字时按蓝图顺序串行分段并保存检查点。
- 选区操作只能返回 replacement；Agent Service 不负责拼接全文。文档运行只回传一个最终候选
  结果，全文检查只回传报告。

### 历史长篇视频导演规划收敛

- 旧 `VideoScene` 公共创建、查询、重试、返工、批准和提示词预览入口已经退役，不能再创建新的旧任务。
  Agent handler、内部回调和耐久 dispatcher 只用于已存在历史任务的恢复与终态收敛；不得把它们重新注册为
  浏览器或 CLI 产品入口。
- 历史视频规划任务只服务 `long_serial`；Agent 只消费 Core 冻结的原文、设定快照、时长、画幅、
  规划路由和模型身份，不得回读 PostgreSQL 或当前可变资料。
- 默认使用 DeepSeek Responses 的 `text.format=json_schema` 分三阶段生成轻量创意草案：
  场景素材、故事节拍、摄影灯光。草案不得携带数据库 ID、正式素材 ID、节拍时间、调用账本
  或 ReviewArtifact 状态。
- 故事 Responses v4 由服务器从冻结原文生成连续 `E01..ENN` 事件短别名，并在调用前把它们
  固定到闭合 `beatsByAlias` 的主/次动作槽；模型不得提交或移动 E 归属，只填写槽内动作、拍级
  表演、调度与声音。服务器把唯一归属写入 story canonical checkpoint，并复核动作是否真实落地；
  不得再用整段自然语言关键词首次位置推断事件顺序。E 归属不进入摄影草案或最终 Provider 提示词。
- 摄影阶段的焦距、T 值、数值机位、构图规则、运镜、景深和拉焦时长可以从返工基线继承；
  `focus.startTarget/endTarget`、构图前后景、摄影动机和灯光文字属于故事语义。焦点起止目标必须
  同时属于当前 B 拍的 E 事件对象或当前拍人物表演，不能沿用上一拍对象；旧故事不兼容或焦点
  错拍时只省略不可信语义，保留机械设计供模型重填，审计快照本身不得改写。
- 模型草案不是正式事实。短别名映射、连续 ID、时间轴、素材引用和兼容字段必须由共享契约的
  纯函数确定性物化，再经过完整导演语义门禁与提示词编译，最后才能回调 Core 形成待审候选。
- 每次模型调用前必须先取得 Core 原子 reservation；正常三次、全任务最多五次。阶段 canonical
  checkpoint 是唯一恢复事实，原始模型草案不持久化，也不得进入人工日志或用户界面。
- Redis 视频 job 只是可重建执行索引；Core 必须从 `VideoGenerationTask` 的到期状态使用稳定 jobId 补投。
  Agent 不得把重复投递解释成新的模型任务，必须先读取 Core 耐久进度再决定是否继续。
- `responses_json_schema_v1`、`chat_json_output_v1` 和历史 `legacy_strict_tool_v1` 不能在同一
  taskId 中切换。历史 legacy 活动任务应零模型稳定失败，由用户显式创建新的 retry/revise 任务。

### 长篇章节影视化

- `chapter_cinematic_adaptation_v2` 属于独立章节改编域，不创建或更新旧 `VideoScene`。Core 冻结完整章节并
  通过 `VideoAdaptationTask` 投递；Agent 不回读 PostgreSQL。
- 工作流使用 StateGraph 按“场景/戏剧节拍/观众覆盖目标分析 → Core dramatic checkpoint → 目标驱动镜头设计
  → 严格结构校验与非阻断审镜发现 → Cinematic Reviewer → 最多一次完整返工”执行。Reviewer 不做局部 patch；
  第二轮仍有语义问题时把完整候选和 warning 交给作者，不以电影经验规则直接判任务失败。
- 句末和换行生成的 `U` 编号只用于来源锚定，不是场景、节拍或镜头边界。对白换人、句子结束和原文换行
  不能成为切镜理由；每镜必须有本镜作用、观众获得、目标绑定、可见动作、分层对白/声音和具体剪辑动机。
- 新场景首镜、景别变化、平均镜头时长、慢镜比例和补充镜头用途只能形成有证据的建议，Agent/纯代码不得
  强行改写 `narrativePurpose`、景别或切镜理由。来源关系、镜头用途、对白位置和声音设计是独立维度。
- 正式方案修订必须由 Core 冻结当前 `baseShotPlanVersionId + baseShotPlan`；Agent 可参考基线完整重写候选，
  但不能修改旧正式版本或声称完成了跨服务局部 patch。
- Shot Designer 使用闭合 `beatsByKey`。若模型沿用基线旧 Beat Key，Agent 只按 checkpoint 中精确 U 集合把草案
  归位到正确 Beat；仍缺失的槽位只补全缺失 Beat，不重写已完成镜头。错误 G 绑定属于软元数据，剔除后形成
  finding；跨 Beat U 不得进入候选，无合法来源的直呈/推导草案降为补充并提示核对。
- Core checkpoint 是跨重试耐久事实；已有 dramatic checkpoint 时禁止重新调用分析阶段。候选只通过签名回调
  进入 `ReviewArtifact(video_adaptation_plan)`，Agent 不写正式 Scene、Beat、Shot 或 PromptVersion。
- `chapter_shot_prompt_v2` 只为当前正式镜头生成结构化 `ShotPromptSpec`；最终即梦文本由确定性编译顺序产生，
  不得改变已确认镜头边界或新增剧情结果。模型只读取目标镜头自己的正式事实和冻结设定，不读取完整章节或
  前后镜完整事件。Core 还会按目标镜头冻结已经批准的 `visualReferenceBundles`；Agent 只能读取视觉版本、设定职责、
  包含/排除特征和参考强度元数据，不读取图片路径或数据库。身份、服装、场景或道具已有正式参考时，冻结图片负责
  稳定对应静态造型，文字设定投影不得再复制完整外观；当前主体、临时状态、可见动作和摄影要求仍必须完整表达。
  首次响应不是合法结构化对象，或没有通过时长、景别、重复和编译门禁时，同一任务只允许
  追加一次带具体原因的 JSON Schema 纠正调用；第二次仍有 Schema、目标顺序、空字段、编译或预算硬错误时必须失败，
  仅剩动作密度、重复、邻镜语言、不可见解释或未确认状态变化时必须返回带 `qualityWarnings` 的可编辑候选，不得猜 JSON、
  无限重试、静默截断或保存半截提示词。新模型按镜头内容选择性提交 `expressionAndGaze`；历史 `performance/continuity` 仅兼容读取，
  新 Schema 不再请求。纠正前允许确定性移除编译器元数据、历史字段、不可见表情与动作冲突的负面约束，并把唯一
  冲突的显式景别词替换为正式中文标签；正式标签与一个冲突标签并存但没有景别变化语义时可删除冲突词，主体与
  摄影机重复景别时只在摄影机保留。真正涉及运镜或景别变化时不得自动替换，也不得
  截断文本、改写动作或补造事件。批量任务按 `shotKey` 分别构建设定投影，人物外观按景别与本镜明确锚点裁剪；
  当前镜头事实覆盖具体设定，具体设定覆盖全局风格；动态道具状态必须由本镜事实
  确认，负面约束不得禁止完成正式动作所需的手部或正式主体，但可排除其他/额外人物。主动作可包含直接结果，但不得脱离本镜来源追加再次、继续、
  反向操作或失败重试；转动、旋转等物理变化必须在本镜正式事实或来源中有依据。2500ms 及以下正式镜头若自身有
  四个以上可读信息单元，只附加延长/拆镜提醒，不要求模型越权改镜。上下文同时提供正式景别代码和产品中文标签，候选显式景别不得与标签冲突，例如
  `close=近景` 不能写成“特写”。完成回调前必须按正式画幅和时长实际编译全部候选。
- `negativeConstraints` 只能表达禁止或避免，不能借“只保留”等正向白名单加入新画面。火花、火焰、爆炸、
  闪电/电弧、粒子、光束、浓烟、雨雪和血迹等高成本视觉效果若未出现在正式镜头、来源、本镜相关设定投影或
  视觉参考包含特征中，首次响应进入现有一次纠正；第二次仍存在时只作为可编辑 `qualityWarnings`，不得自动删除或硬失败。

## 关键入口

- 应用工厂：`src/inkforge_agents/app.py`
- Agent 定义：`src/inkforge_agents/definitions/agents.py`
- 父图：`src/inkforge_agents/graph/parent_graph.py`
- Operation 图：`src/inkforge_agents/operations/graph.py`
- 图状态：`src/inkforge_agents/graph/state.py`
- AgentRunner：`src/inkforge_agents/runtime/agent_runner.py`
- 唯一工具循环：`src/inkforge_agents/runtime/agent_runtime.py`
- 模型适配：`src/inkforge_agents/runtime/model_runtime.py`
- 工具注册表：`src/inkforge_agents/tools/registry.py`
- Core 工具网关客户端：`src/inkforge_agents/clients/core.py`
- 运行队列：`src/inkforge_agents/queue/`
- 人工日志：`src/inkforge_agents/observability/`

## Agent 与工具规则

- Agent ID 固定为：设定、剧情、写作、校验、编辑。
- Agent 调用显式使用 `primary`、`reviewer`、`reviser`、`quality` 四种执行模式，禁止根据是否存在草案推断当前角色。
- AgentRunner 只暴露“Agent 能力白名单、CreativeOperation 工具白名单、执行模式工具白名单”的交集；`primary/reviser` 使用 Operation 契约，`reviewer` 无读取工具且只允许 `submit_evaluation`，`quality` 只允许 `submit_quality_report`。
- ToolRegistry 再次校验 Agent 权限；未暴露工具必须拒绝执行。
- 26 个只读工具的名称和参数模型统一定义在 `inkforge_contracts.read_tools`；Agent 与 Core 必须共同引用该契约，禁止分别维护同名参数模型。
- 只读且并发安全的工具可以并行；控制工具按模型返回顺序执行。
- 每个 CreativeOperation 必须声明上下文策略、允许工具、终止控制工具、产物事件、产物类型和 artifactKey 策略；图层在提交 Core 前确定性拒绝错误事件、错误 kind、变化的 artifactKey 和冲突终止产物。
- 设定新增/修改可使用通用更新构建器，但不暴露 `append_outline_tree`；该工具只允许创建/修改大纲和管理伏笔 Operation 使用。
- 可见正文使用自然段文本，控制信息通过工具调用或明确产物边界提交。
- 禁止从可见正文解析路由、评分或 JSON 控制信封。
- 更新构建器在单次运行中只能启动一次；启动后 Runtime 不再暴露 `start_update_builder`，追加和完成必须沿用同一 `artifactKey`。重复开始事件在跨纠正重试合并时按幂等处理，不得清空已追加批次。
- Agent 的产物提交工具必须配置为终止控制工具；`propose_updates`、`finish_update_builder` 等产物完成事件成功后应立即结束本轮工具循环。
- `sync_lore` 已从当前可执行 Operation 和前端入口中删除；共享类型仅保留历史快照解析兼容，路由和分类器不得生成新的同步设定任务。
- 当前运行创建草案后，`CoreArtifactPort` 保存已提交 Core 的完整请求快照；reviewer 只接收该权威草案并提交一次评审，reviser 接收同一草案、revision、artifactKey、原 payload 和合并后的 `requiredChanges`，按原 Operation 产物契约生成同类新 revision。`plan_chapter` 复审与返工额外接收主 Agent 生成草案时使用的冻结最小作品投影，用于核对名称、时间、数值和剧情边界，但仍不开放读取工具。没有权威快照时必须显式失败，不得猜测或从正文反推草案。
- Reviewer 的 `revise + rewrite` 才调用 Reviser 完整返工；全部 Reviewer 都是严格 `revise + patch` 时，图使用确定性 patch 节点创建同一 ReviewArtifact 的新 revision，不调用 Primary 或 Reviser。patch 找不到、多命中、重叠、非章节目标或 `ARTIFACT_REVISION_CONFLICT` 时，原子放弃修改并进入 `blocked`/`waiting_user`，不得静默升级为 rewrite；其他 Core、网络或协议错误必须作为运行错误上抛，不能伪装成内容不通过。
- 一致性终检固定由“校验”Agent 的 `quality` 模式执行，结果使用 Agent、Core 共用的严格报告契约；商业性、追读和爽点评审仍属于“编辑”职责。

### 模型策略与 DeepSeek 传输

- 生产模型请求必须在业务入口显式携带 `ModelExecutionPolicy`。长篇初稿、场景/整章/选区改写、中短篇大纲正文和选区替换使用 `thinking=enabled`、`reasoningEffort=high`；长篇 Reviewer、一致性 Quality、问答、复审报告、中短篇 `full_check` 和文风画像使用 `thinking=disabled`。`provider_default` 只保留测试、旧快照兼容和明确 legacy 路径，不能由 Agent ID、工具集合或 URL 推断。
- `OPENAI_COMPATIBILITY_PROFILE=generic` 继续使用通用 ChatOpenAI；`deepseek_v4` 使用 DeepSeek 原始 JSON transport。DeepSeek 工具轮次的 `reasoning_content` 只在进程内消息回放，不进入稳定快照、ReviewArtifact、Core 用量或人工日志正文；日志只记录策略和用量诊断结构头。

## 数据与信任边界

- 所有业务读取和草案提交都通过 Core `/internal/v1/**`。
- `semantic_search_references` 的查询向量由 Agent Service 复用现有 embedding 客户端生成，Core 只接收内部查询向量并在当前用户和小说范围内执行 pgvector 检索；未配置 embedding 时必须明确返回未启用。
- 只有 Core 与 Agent 同时设置 `RAG_INDEX_ENABLED=true` 且 Agent 已配置完整 embedding 客户端时才允许启用索引；启用后 embedding 不可用必须使就绪检查失败，不能静默降级为已就绪。
- 请求使用 Ed25519 短期服务令牌，绑定受众、权限、任务、运行、小说、请求体摘要和查询摘要。
- 写入类内部请求必须经过 Redis 重放保护。
- Agent 只能生成 ReviewArtifact 或评审结果，不能直接写章节、设定、大纲或计费表。
- 运行恢复以 Core 持久化的 `WritingTask.graphStateJson` 为权威；Redis 只承载队列、短期事件和重放保护。
- 模型消息统一按“静态 Agent system prompt、服务端执行 brief、只读资料 user 消息、历史消息、唯一当前 user 消息”构造；作品数据和历史 system 记录不得提升为当前 system 指令。`contextStrategy` 只生成最小资料投影，完整聚合 `workspace` 不进入稳定快照。
- `get_recent_chapters` 必须由 Agent 显式按需调用；`count` 可选且范围为 `1..20`，省略时 Core 默认读取 3 章。基础上下文不自动注入任何最近章节正文，该工具也不改变现有 RAG 每份资料 64 块容量或 `topK`。
- 写作处理器在每次初始、命令恢复或当前 job 快照恢复时重新附加仅运行时 `runtimeContext`；其中 `RunResource` 的 `runId/jobId` 必须来自当前 QueueJob，供工具、草案、评审和水合统一使用，并在稳定快照序列化前移除。
- 需要继续自动复审、自动返工或用户选择 revise 时，写作处理器必须先用 Core 的 `planning.activeArtifact` 水合本地权威草案；approve/discard 不依赖草案仍存在。等待、完成或错误稳定收敛后，只能在相应 checkpoint/回调成功后按同一 `runId/jobId` 释放缓存，失败时保留以供重试。
- 写作事件、检查点、完成和失败回调必须携带当前队列 `jobId`，协议版本为 `1.1`；来源事件 ID 也必须绑定 jobId，禁止只靠 runId 猜测命令身份。Agent 只有校验 Core 返回的 `applied/already_applied` 接收凭证后才能确认回调成功，204、空响应、无效凭证或 `rejected` 都不能当作成功。
- 当前 job 已锚定 `completed/error` 持久快照时，重试必须从快照序号直接重放终态回调，禁止重新执行图；终态回调自身暂时不可用时必须保留可重试异常。
- 图进入等待用户确认时，不再单独直发 `artifact_awaiting_user_approval`；必须用下一个连续序号保存等待态稳定快照，由 Core 在保存快照的同一 PostgreSQL 事务中登记 Outbox 边界事件。
- 图稳定结束为 completed/error 时仍先保存可恢复快照，但该 checkpoint 不能提前结束数据库任务；任务、命令终态和 terminal Outbox 只由随后 complete/fail 回调的同一 Core 事务提交。
- 图稳定结束于 `phase=error` 时必须保存错误快照并调用 Core 失败回调，禁止用完成回调表达失败终态。
- Core 强制对账只允许修复 Redis 中缺失的 queued 索引或完全丢失的运行键；Redis 已记录为 completed、failed 或 cancelled 的运行不得被 `force` 重新打开。
- 队列消费者必须由生命周期任务监督器托管；基础设施异常按退避策略重试，消费者协程意外结束必须使就绪检查失败并触发重启，不能只凭消费者对象存在判断健康。
- 2 核 2 GB 生产环境保持一个 Uvicorn worker，消费者默认在同一事件循环内运行三个独立 job 槽；同一 `novelId` 同时只允许一个 job 执行，同项目冲突的 claim 必须通过租约校验原子回队，成功回队时撤销本次 claim 增加的 attempts。回填、清理、租约恢复和 claim 串行进入维护临界区，每个已领取 job 独立续租和收敛。`AGENT_MAX_CONCURRENCY` 只允许 1、2 或 3，配置 1 可回退原串行行为。
- 所有普通 Agent、中短篇、质量检查和文风画像模型请求共用 `ModelRuntime` 的全局并发门；默认最多三个模型调用，Reviewer `Send` 扇出也必须受该门限制，不能因三个 job 重叠放大供应商请求。
- 任一消费槽发生未知程序错误后必须立即停止领取新 job 并使 readiness 返回 `BACKGROUND_TASK_FAILURE_DRAINING`；已经领取的其他 job 继续收敛，随后再交给监督器退避重启。旧 handler 因取消或 lease 失效退出时不得覆盖当前队列状态，也不得把该已知条件升级为整个消费者崩溃。
- 队列终态必须进入时间 ZSET 并在保留窗口后有界清理；ack/cancel 同时删除 payload、lease、attempt 和 score。领取任务时按优先级查询已到期成员，不能让未来重试任务形成队头阻塞。
- 升级前旧终态使用 HSCAN 游标分批补齐 tombstone；保留天数由 `QUEUE_TERMINAL_RETENTION_DAYS` 配置，默认 7、最少 1。
- Redis OOM、MISCONF、READONLY 和达到阈值的连续基础设施失败必须交给监督器并使 readiness 失败；TypeError、Pydantic 契约错误和未知程序异常不得在消费循环中无限吞掉。
- `MODEL_MAX_OUTPUT_TOKENS` 表达当前部署模型的单次最大输出能力，默认 `384000`，合法范围为 `1..1_000_000`；普通 Agent 与文风画像共用该值。它不是目标篇幅，不要求模型生成到该长度，也不承诺无限输出。
- 计费模型每次调用前仍必须向 Core 申请有限正整数 grant；模型授权生命周期为 1200 秒，供单次模型调用完成后上报实际用量，不改变内部服务请求令牌的短期约束。Core 可以按可用余额缩小额度，`ModelRuntime` 必须把实际授权的 `maxOutputTokens` 精确传给 Provider，禁止绕过授权上限。
- Provider 成功形成规范化 `ModelTurnResult` 后，`ModelRuntime` 先向 Core 上报四项实际 token 及可选
  `promptCacheMissTokens`/`reasoningTokens` 诊断，再把同一调用的 `taskId`、`runId`、Core 计费
  `requestId`、provider、model、usage、完整 messages 和完整 output 交给人工日志 observer。DeepSeek
  原始 `reasoning_content` 永不写入快照、ReviewArtifact、Core 或日志正文；非计费调用的计费请求标识
  明确为“无”，Provider 在返回 usage 前失败时不伪造 token，人工日志绝不记录 `grantToken`。
- Provider 必须返回规范化 `finishReason` 并保留供应商原始原因；`length`、`content_filter`、完成原因与工具状态矛盾，以及无合法工具调用的 `unknown` 都必须在接受正文或执行工具副作用前失败，当前不把 `length` 作为自动续写信号。文风画像只接受 `stop`、无工具调用且正文非空的纯文本响应，半截画像不得成功。人工模型日志同时记录规范化值和未经截断的原始值。
- 人工日志当前使用 `INKFORGE-HUMAN-LOG/2` 长度分帧格式，结构头与正文按字节长度隔离，正文中的
  日志标记或 JSON 不参与结构解析。旧版文本迁入 `trust=unverified` 的只读 legacy 帧；残缺尾部只在
  已存在完整可信运行元数据时隔离为带 SHA-256 和字节数的恢复文件，再从最后完整帧继续追加。追加
  前必须校验当前运行与日志中的 task、run、user、novel 和适用时的 chapter 身份。

## LangGraph 规则

- 编排必须复用现有 `StateGraph`、conditional edges、`Send`、`Command` 和 `interrupt()`。
- 复审、返工和用户确认不得另写 while/switch 状态机。
- runtime-only 客户端、回调和聚合上下文不能进入可恢复快照。
- 快照必须使用版本化信封；无法兼容的版本明确失败，不能静默猜测。

## 验证

修改运行时、工具或图后至少运行对应目录 pytest、Ruff 和 Mypy。修改服务契约或内部鉴权时，还要运行 `packages/service-contracts/tests` 与 `packages/service-auth/tests`。
