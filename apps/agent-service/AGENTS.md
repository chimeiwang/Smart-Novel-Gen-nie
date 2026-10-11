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

- `short_medium` 执行 `generate_outline`、`generate_manuscript`、`replace_selection`、`full_check` 四种专用操作，不复用长篇多 Agent 自动评审链。
- 只信任 Core 随 QueueJob 提供的不可变来源、基础版本、蓝图和正文快照；长文串行分段并保存完整检查点，恢复不能重复已经完成的段。
- 选区只返回 replacement，全文由 Core 拼接；生成回传最终完整候选，全文检查只回传完整报告。

### Episode 剧本与分镜

活动视频主链以独立 `VideoEpisode` 为身份，章节只作为一个或多个不可变来源快照。旧章节改编、逐镜提示词与 VideoScene 任务不重新开放。

四项业务为 `episode_script_generate`、`episode_script_revise`、`episode_storyboard_generate`、`episode_storyboard_revise`。Core 冻结完整来源、基础版本、revision、修改范围、视觉依据与内容哈希，形成普通业务任务；`WorkflowRun(engineVersion=1)` 仅保存业务状态，实际来源中首个现存章节作为归属锚点，Episode 仍是模型目标。不可变 Evidence 是来源记录，不创建模型 Step 或依赖执行 Catalog、execution journal。

任务通过普通 `kind=video` 队列执行现有 LangGraph 生成、审阅与最多一次返工。完整检查点由 Core 保存，已完成结果恢复时不重调模型；已开始但结果未知的供应商调用明确失败并保留诊断，不能自动重复请求。Agent 每次模型调用使用既有 Core 授权与用量回报。

Core 重新校验来源哈希、工作稿版本与局部修订范围，只生成完整待审候选。候选采用、正式剧本／分镜确认和制作基线是独立作者决定；局部修订保留范围外内容。回调使用 Ed25519 服务身份绑定任务、小说、路径和正文。取消使用稳定命令标识及当前 revision，迟到成功不能覆盖取消。

生产保持 `VIDEO_PREVIEW_ENABLED=false`，不得调度视频或真实 Seedance。

现有结构要求普通任务绑定真实章节归属。若冻结来源集合中的章节全部已删除，新任务明确要求重新选择有效来源；不随机绑定无关章节，已有不可变快照和候选仍保留。

## 作家编辑原则

作家 Agent 在初稿和返工中同时遵守六项编辑原则：对白符合人物已知信息和当下目的；旁白不重复解释已由动作或对白表达的意思；每场戏带来新的变化；动作服务具体场面；解决办法有依据和铺垫；识别并保留有效对白、细节、人物特点及作品文风。
提交前把必要调整落实到最终正文，不输出自检过程。该要求只增强现有提示词，不新增 Agent、复审循环或模型调用；不把短句、方言、词语或外部 AI 检测分数作为硬门禁。跨章判断需要实际读取相关章节，不能根据未读取内容推测。

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
- 模型可见 Schema 必须表达定位、产物及复审的可表达组合规则；固定错误码对应安全纠正说明，不能只给
  根级通用错误。普通正文与选区按 Operation 收窄模型 Schema，预检使用相同约束，保留原注册工具身份。
- 新模型 Beat Plan 输入不请求 `beatCount`，只从已校验 `sceneBeats` 派生；控制事件仍保留该字段。
  历史参数及持久结果继续按原契约读取，不能用新输入 Schema 拒绝旧事件或放行矛盾计数。
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
- DeepSeek Function Calling 默认启用 Beta strict：普通读取、正文提交、Reviewer、Beat Plan、设定更新与质量终检均在供应商边界解析默认值，同一请求全部函数发送 `strict: true`；覆盖 `deepseek_v4` 原始传输和 `generic` 下的 DeepSeek 模型。非 DeepSeek 保留原默认。工具显式 `strict=false` 只用于兼容请求，与开启的工具混用必须在 HTTP 前失败，禁止自动降级。
- strict 请求仅在 DeepSeek 模型且 `OPENAI_BASE_URL` 为规范官方 HTTPS 根地址或 `/v1` 地址时自动派生 `/beta`；自定义地址、端口或其他路径必须显式设置 `OPENAI_STRICT_BASE_URL`。Provider 不隐式重发或切换协议；明确标记为 `retryable` 的传输错误仍按同一任务现有队列机制重试。纯文本没有 Function Calling strict；已冻结的 JSON Output、视频 Responses 路由与能力门禁不因本默认值改变。
- 普通工具通过可逆 wire 契约适配 DeepSeek：所有对象闭合、至少一个属性且字段全必填；正常字段直接传业务值，省略使用 `{"_inkforgeState":"omitted"}`，null 使用 `{"_inkforgeState":"null"}`。可证明交集解码一致的联合直接表达；业务值与标记同形或分支解码不等价时保留必要的判别包装。条件根联合保留完整 anyOf 约束，不能只合并属性。开放字典与任意/递归 JSON 继续使用完整 JSON 字符串，无参/真实空对象保留非空标记；见[平铺规格](../../docs/specs/2026-10-07-deepseek-flat-wire-study.md)。进程内历史从原业务参数按新契约编码，响应仍完整复验 wire、解码结果和原 JSON Schema/Pydantic；不能丢字段、静默覆盖重复 JSON 键或把空值当缺失。质量工具保留专用投影，`location` 与 `rewriteBrief` 仍只在精确路径把空字符串归一化为 `None`。
- DeepSeek wire 中相邻的纯 anyOf 联合必须等价展开，使 anyOf 的每个直接分支有具体 type，并在发出 HTTP 前预检。字段联合容器可以没有 type；带 type/properties 的条件对象必须保留全部约束，不能随意添加 object 类型或删除条件。通用 JSON Schema 校验不能代替供应商方言检查及真实验收。
- DeepSeek arguments 无法解析时必须先保留可靠 usage，再返回无原文的无效工具诊断；只允许在末尾追加缺失对象/数组闭合符，且补齐后必须通过本轮原始 JSON Schema。AgentRuntime 把一轮工具响应作为原子包，存在任一无效调用就不得接受正文或执行任何调用；无效 JSON 或 Pydantic 参数在整个运行中最多触发一次不回放坏参数的显式协议纠正，纠正调用必须独立授权、结算 usage 和记录。`length`、`content_filter`、资源不足、无暴露工具或纠正仍失败时不得继续纠正，最终以不可重试的 `MODEL_TOOL_PROTOCOL_RECOVERY_FAILED` 收敛。
- 上述一次预算仅在普通章节 `write_chapter` / `rewrite_scene` 的 primary/reviser 有一个例外：首次纠正用于纯读取工具包且已经成功，后续 `begin_artifact_output` 的 Pydantic 参数失败可以再纠正一次。每次 AgentRuntime 执行最多两次纠正，同一纠正响应再次失败立即结束；选区、reviewer 和 quality 不扩充预算。正文提示只要求 kind、summary 和完整 content，返工身份由原有权威草案校验器继承；见 [临时修补规格](../../docs/specs/2026-09-28-chapter-artifact-protocol-hotfix.md)。
- 公共错误只携带安全分类、工具名、字符数及最多 10 条白名单 `loc/type`。纠正提示可额外使用本地从已下发 wire Schema 生成的字段类型、状态说明和合法字段格式示例；不从失败参数提取示例。`toolSchemaHints` 只在进程内使用，从普通 model_dump/repr 排除，不进入公共错误或业务状态。完整失败诊断另行保留脱敏后的原始参数、wire/业务 Schema、全部校验错误、异常链与确定性恢复前后证据，按具体阶段写入服务日志和适用的 V1 帧正文，不进入纠正提示、Core 或持久业务状态；见[完整失败诊断规格](../../docs/specs/2026-10-07-complete-failure-diagnostics.md)。显式协议纠正不改变 SDK、队列重试或现有调用预算。

## 数据与信任边界

- DeepSeek、通用 OpenAI-compatible、Embedding 与 Responses 请求失败时，完整保存经过凭据脱敏的 HTTP 错误正文、响应头、
  方法/地址及异常消息、因果链、调用栈，不按长度截断，不采集调用栈局部变量。详情只进入服务诊断
  和 V1 人工日志的 `model_failure`／`diagnostic` 帧正文，不进入异常 str/repr、Core 回调、SSE 或聊天回复；
  HTTP 200 但 JSON、usage、工具参数或结构化输出无效时，
  同样保存失败内容和完整校验原因；正常成功内容、推理与请求不另行复制。授权、计费回报、工具执行、
  图层降级、队列及未知异常记录完整脱敏因果链。详情采集或日志 sink 故障不能替代原结果。
  日志专用字段必须从普通 model_dump/repr 排除，结果重建时显式保留给日志层；具体见
  [完整失败诊断规格](../../docs/specs/2026-10-07-complete-failure-diagnostics.md)。

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
- 普通 V1 队列必须在既有状态迁移 Lua 内原子维护版本为 `1` 的 drain `queued/running` 最小 ZSET；索引只保存
  `jobId` 与原始 `createdAt`，不得复制或解析正文 payload。缺 marker、旧 marker、集合双向不一致或 active 超过
  256 项时联合 drain 必须封闭失败；具名空索引初始化也不得扫描超过 256 个历史 status。
- 耐久执行引擎已退役；新业务全部使用普通队列和 Core 业务检查点，Agent 不装配单 Step 执行器或 execution Redis。旧运行、候选来源与账务由 Core 提供必要的历史读取和决定兼容，不改写历史引擎身份。
- 队列消费者必须由生命周期任务监督器托管；基础设施异常按退避策略重试，消费者协程意外结束必须使就绪检查失败并触发重启，不能只凭消费者对象存在判断健康。
- 2 核 2 GB 生产环境保持一个 Uvicorn worker，消费者默认在同一事件循环内运行三个独立 job 槽；同一 `novelId` 同时只允许一个 job 执行，同项目冲突的 claim 必须通过租约校验原子回队，成功回队时撤销本次 claim 增加的 attempts。回填、清理、租约恢复和 claim 串行进入维护临界区，每个已领取 job 独立续租和收敛。`AGENT_MAX_CONCURRENCY` 只允许 1、2 或 3，配置 1 可回退原串行行为。
- 所有普通 Agent、中短篇、质量检查和文风画像模型请求共用 `ModelRuntime` 的全局并发门；默认最多三个模型调用，Reviewer `Send` 扇出也必须受该门限制，不能因三个 job 重叠放大供应商请求。
- `ModelRuntime` 包装授权、供应商和用量回报错误时必须保留下游显式声明的 `retryable/recoverable`
  决定，但不得复制底层异常正文。质量 handler 对明确可重试错误不写失败回调，由队列复用同一 job；明确
  不可重试错误在 Core 成功收敛失败终态后转为已知非重试任务，不得重启整个消费者；没有显式决定的程序
  异常仍交给监督器，不能为了保持 readiness 全绿而吞掉。
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
  明确为“无”，Provider 在返回 usage 前失败时不伪造 token，人工日志绝不记录 `grantToken`。工具协议纠正
  是新的模型调用，首次调用与纠正调用必须各自拥有计费 `requestId`、usage 回报和人工模型区块，不能合并。
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
