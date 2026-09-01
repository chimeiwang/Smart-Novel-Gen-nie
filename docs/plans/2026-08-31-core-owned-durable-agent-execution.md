# Core 权威耐久 Agent 执行内核实施计划

状态：实施中

规格：`docs/specs/2026-08-31-core-owned-durable-agent-execution.md`

架构决策：`docs/architecture-decisions/004-core-owned-durable-agent-execution.md`

## 总原则

- 新 Run 只能选择 V1 或 V2 其中一个引擎，禁止双写和影子模型调用；
- 每一阶段先写失败测试，再实现，再做跨进程验收；
- 任意阶段都不能用 202、容器 healthy 或 fake provider 代替业务终态证据；
- 生产发布只在全部功能、恢复、资源和回滚门禁完成后进行；
- V1 删除以“所有新任务均走 V2、旧活动任务归零”为前提。

## Task 0：规格、ADR 与事实基线

- [x] 记录生产时延、调用、事件和协议失败证据；
- [x] 确认队列受理不是主要瓶颈；
- [x] 冻结 Core 权威编排、无状态执行器、Evidence 和耐久 Event 决策；
- [x] 记录具名数据库迁移授权和生产 canary 边界；
- [x] 冻结取消、租约、决定、SSE、路由、usage、foreground Run 与 V1 drain 生命周期矩阵；
- [ ] 将当前 V1 入口、状态、测试和待删除组件固化为机器可检查清单。

## Task 1：Operation Catalog 与执行契约

- [ ] 新增语言中立 Operation Catalog Schema 和 v1 Catalog；
- [ ] 覆盖长篇 12 个操作、中短篇 4 个操作、质量、画像、RAG 和开发视频；
- [ ] Python、Java、TypeScript 分别加载同一 Catalog 并校验同一 SHA-256；
- [ ] 新增 `ExecutionStepRequest/Accepted/Progress/Result/Failure` 契约；
- [ ] 新增绑定 `runId/stepId/jobId/fencingToken/cancelRequestId` 的 `ExecutionCancelRequest/Ack` 契约；
- [ ] 新增 Evidence、Evaluation、Budget、ModelProfile 与错误分类契约；
- [ ] 新增 `usageStatus=complete|partial|unknown`、可空未知计费字段和累计 usage 契约；
- [ ] 新增语言中立 System Purpose Registry，覆盖 intent、evidence summary 与 protocol correction；
- [ ] 新增语言中立 Step Budget Registry；生成、Reviewer 与 System Purpose 均显式引用，Run 总额不得充当 Step 配额；
- [ ] Reviewer 策略显式冻结 output schema、rubric、evidence policy、lane 与单 Step 预算；
- [ ] 新增版本化 Run snapshot、WorkflowEvent envelope 与逐事件 payload Schema；
- [x] Python 共享契约补齐严格 `activeSteps`、逻辑 `ModelProfileRef`、冻结 `ResolvedModelRef` 与可恢复
  `latestProgress`；queued/started/progress/finished 事件和公共 V2 snapshot 使用同一模型身份与逐 Step fence，控制
  Step 显式为空，禁止正文、日志与 reasoning 原文进入 wire；
- [ ] 新增独立服务权限，禁止复用旧 callback/tool write 权限；
- [ ] 导出 JSON Schema、更新 manifest、Java DTO 和契约 golden tests；
- [ ] 冻结 DeepSeek 合法、畸形、429、5xx、超时和断流协议夹具。

## Task 2：具名数据库迁移

- [ ] 先写迁移结构和约束红灯测试；
- [ ] 实现 `20260831_durable_agent_execution.sql` 与 rollback；
- [ ] 演进 `WorkflowRun/WorkflowStep`；
- [ ] 新增 Evidence Bundle/Item、Event、Evaluation，并覆盖 `exists=false` 的显式 absence item；
- [ ] 保证 V1 表、枚举和历史数据完全兼容；
- [ ] 在临时 PostgreSQL 14 + pgvector 执行 forward 两次、rollback、再次 forward；
- [ ] 从迁移后真实结构生成并核对 contract；
- [ ] 验证旧 Java 应用可以在新增结构上启动和读取旧任务；
- [x] 新增具名迁移 helper，固定 SQL/contract SHA、目标数据库、0600 PGPASS、生产确认文件、四态 status、
  联合 PostgreSQL/execution journal 备份和空 V2 rollback；fake 测试覆盖凭据不泄露、错误 host/database、
  partial、错误 hash/token、重复 forward、缺 journal 和 V2 数据拒绝 rollback；
- [x] 新增 PostgreSQL restore 前 execution quarantine 具名步骤，要求 database dump SHA、epoch 和本地
  `WAITAOF=1`，但不提供未经授权的数据库覆盖恢复入口；
- [ ] 备份后在 `novelwriterdev` 两次执行并导出权威 contract；
- [ ] 正式迁移保持待发布门禁，不提前执行。

## Task 3：Java Core 通用 Workflow 内核

- [ ] 新增独立 `workflows` Modulith 模块；
- [ ] 实现 Run/Step 状态机、幂等、CAS、租约、fencing 和过期恢复；`running` 幂等重派保持原状态并原子换
  fence/job，不具备供应商幂等保护时收敛为 `MODEL_OUTCOME_UNKNOWN`；
- [ ] 固定 `attemptCount=Core 派发次数`、`providerAttempts=Step 累计供应商尝试` 并贯通 Java/Python/数据库；
- [ ] 实现 Evidence 持久化、完整性验证和不可变约束；
- [ ] 实现 Event 事务写入、带 `baseSequence` 的 snapshot、Run sequence SSE ID 与 PostgreSQL 增量观察；
- [ ] 实现 progress 去重/升格、Run 总序分配和累计 usage 单调校验；
- [ ] 持久化 resolved model、累计 usage、last progress sequence 与 cancelRequestId，禁止借用预算或输出字段；
- [ ] 将完整解析后执行计划冻结到 `modelPolicyJson`，后续 Reviewer/System Step、重派、输出验证与终报结算不依赖
  当前 Registry 仍保留旧 Profile/Schema；覆盖在途 Run 跨镜像/Registry 升级与旧部署下线；
- [ ] 用数据库 trigger 保护 V2 Run/Step 身份快照不可变，并限制 resolved model/result hash 只能从 NULL 冻结一次；
- [ ] 实现分车道调度、System Purpose Registry 和 Run 预算原子保留/结算；
- [ ] 实现 V2 状态查询、精确绑定 cancel、后台 cancel ACK/usage 收敛和 SSE；
- [x] V2 SSE 使用进程级共享 tail observer：不同订阅 Run 批量读取高水位和 Event，同一 Run 多连接只读一次 tail；
  保留逐连接原子 snapshot/baseSequence，并覆盖 256 全局/8 每用户连接上限、4 批次慢消费者断开、15 秒无查询心跳、
  断线/异常/终态注销以及 `schemaReady=false` 零 V2 查询；
- [ ] 实现用户级锁内跨 V1/V2 幂等解析、allowlist 路由和跨引擎 mutation scope 互斥；
- [ ] 实现 approve/discard/revise/cancel 的 Run 行锁与 revision CAS，禁止终态反转；
- [ ] 实现 Agent Step 提交、进度和结果内部接口；
- [ ] 计费归属支持通用 V2 WorkflowRun/Step；
- [ ] 故障注入覆盖重复请求、旧 fencing、响应丢失和进程重启。
- [x] execution journal 使用 Redis 持久卷与 AOF；未确认/被拒终态无 TTL，只有 Core 回执后进入保留期；
- [x] 实现独立 terminal callback replayer：按 journal 到期时间小批领取、同 resultHash 幂等回放、带抖动退避，覆盖
  Core 已提交但 HTTP 回执丢失、Agent/Core/replayer 重启和确定性 rejected 隔离；
- [x] Redis 持久化失败时 readiness 失败且模型调用 fail-closed，备份/恢复覆盖未送达 journal。
- [x] 将 execution journal 拆到独立 `EXECUTION_REDIS_URL`、AOF always/noeviction 实例；普通队列/SSE/重放 Redis
  保持低延迟配置，生产禁止两个 URL 指向同一实例；

## Task 4：首个完整纵切——长篇章节选区改写

- [ ] Core 从权威章节冻结完整选区 Evidence；
- [ ] 创建一个结构化生成 Step，不创建 WritingTask/Command/GraphState；
- [ ] Python V2 executor 一次模型调用返回完整 replacement；
- [ ] Core 确定性物化来源绑定、Diff 和 ReviewArtifact；
- [ ] 两个 Reviewer 使用同一 Evidence，分别保存证据化 Evaluation；
- [ ] Reviewer 失败保留候选并显示复审未完成；
- [ ] discard 由 Core 直接完成，保留 V2 Artifact/revision/Evaluation 并通过决定 Step/Event 变为只读；
- [ ] approve 在同一事务应用选区、Artifact、Run 与 Event；
- [ ] revise 只创建新 revision Step；
- [ ] Web 展示真实阶段、可恢复状态并调用真实 cancel；覆盖 running 与 waiting_user 取消；
- [ ] 端到端覆盖 SSE 断线、Agent/Core 重启、重复 callback、迟到结果、cancel/complete 与 cancel/approve 竞争。

## Task 5：迁移全部长篇 Operation

- [ ] answer_question / review_chapter；
- [ ] plan_chapter；
- [ ] write_chapter / rewrite_scene；
- [ ] rewrite_outline_selection；
- [ ] create_lore / revise_lore；
- [ ] create_outline / revise_outline；
- [ ] manage_foreshadowing；
- [ ] 自然语言 `resolve_intent` 与具名澄清决定入口，不借用 `/resume`；
- [ ] 每个 Operation 的 Evidence、Schema、Validator、Reviewer、Apply 和预算均来自 Catalog；
- [ ] 删除新长篇路径对可变 workspace、模型工具循环和业务提交工具的依赖。

## Task 6：迁移其他模型工作流

- [ ] 中短篇四个操作，长文使用耐久 segment manifest；
- [ ] 一致性终检，严格区分执行失败与内容结论；
- [ ] 文风画像；
- [ ] RAG embedding 与索引回调；
- [ ] 开发环境章节影视化两个模型工作流；
- [ ] Seedance 受控媒体 Step 继续保持生产关闭；
- [ ] 各工作流只复用执行底座，不混用业务状态机。

## Task 7：Web、CLI 与公共契约收敛

- [ ] Web 提交显式 workflow/operation，不再发送 selectedAgents；
- [ ] 同一 Session 首版只保留一个 foreground Run；非终态期间禁发普通消息，终态后每条普通消息创建新 Run；
- [ ] 将本地断开观察与服务端显式停止拆成两个动作，禁止发送新消息时隐式 cancel；
- [x] `/resume` 按引擎分派：V1 只继续 V1；V2 稳定拒绝，后续普通指令只通过 start 创建新 Run；
- [ ] GET/SSE 使用显式 V1/V2 union；V2 `chapterId` 可空、`commandId/status` 为空并提供规范 `currentStep`；
- [ ] GET 返回完整权威 snapshot，SSE snapshot 初始化 baseSequence 后只观察 `> baseSequence`；
- [ ] 前端事件类型从生成契约产生，删除无 producer 的巨大手写 union；
- [ ] Step snapshot/queued/started 暴露安全的逻辑 `modelProfile`，前端显示真实生成器、一致性 Reviewer 与编辑
  Reviewer 身份，不显示固定假 Agent；
- [ ] V2 status/snapshot 增加稳定排序的 `activeSteps` 与逐 Step `latestProgress`，Web 刷新后恢复并行 Reviewer 的
  独立进度，并按 stepId+fence 单调合并 progress/finished；`currentStep` 仅作兼容摘要，聚合事件不代替逐 Step 终态；
- [ ] `review_started` 携带稳定排序、身份完整且 fence=0 的 pending `reviewerSteps`，Web 立即建立真实 Reviewer
  活动项，再由同 stepId 的 queued 事件推进实际 attempt/fence；禁止维护并行的匿名 reviewer ID 权威；
- [ ] V2 Artifact revision 改存 Evidence 引用、replacement 与哈希等最小可重建事实；列表使用有界 summary，
  精确 revision 详情确定性重建 Diff、支持 ETag，Web 按 artifactId+revision 缓存且不对 403/404 循环兜底；
- [ ] Web 保留 Artifact DTO 必填 `engineVersion`，校验其与 taskId/workflowRunId 的 V1/V2 归属，决定请求原样发送
  Artifact 引擎版本，禁止从 ID 或当前 Run 猜测；
- [ ] 停止按钮调用 Core cancel；
- [x] Java CLI 使用相同 V2 公共契约和安全凭据后端；Artifact 决定省略 `engineVersion` 时仅兼容 V1，
  V2 必须显式发送 2；approve/revise 按精确 revision 读取并核对详情，discard 为兼容 V1 物理删除后的
  幂等重放而直接 POST；Artifact 列表统一读取有界 summary，详情支持可选精确 revision 且保留无 revision 的
  V1 兼容读取；任务观察按引擎读取权威状态并保留 V2 数字 cursor 与 `run_snapshot` 重连语义；
- [ ] 公共 OpenAPI、生成客户端、Web/CLI 测试和文档同步。

## Task 8：V1 排空与代码删除

- [ ] 默认关闭 V1 新建入口；
- [ ] 建立 V1 Task/Command/Outbox/Artifact、Agent job/callback 和公开查询的联合 drain 视图；
- [ ] 观察并确认 V1 活动任务归零；`awaiting_user_review` 与 recoverable Task 未归零时保留 V1 runtime；
- [ ] 删除跨服务 LangGraph 写作图和 GraphState 恢复；
- [ ] 删除 V1 写作 callback、reconciler 和 Redis 业务事件权威；
- [ ] 删除模型 Artifact/Review/Quality 业务提交工具；
- [ ] 删除 selectedAgents 与 Session 业务 phase；
- [ ] 历史 WritingTask/Command/Outbox 只读适配独立隔离；
- [ ] 构建 V2-aware route-off 回滚镜像；存在 V2 数据后禁止部署不理解 V2 的旧 Core/Agent；
- [ ] 另立迁移授权后才允许删除历史表。

## Task 9：全量验证和预发布

- [ ] `./mvnw verify`；
- [ ] Agent/共享包全量 pytest、Ruff、Mypy；
- [ ] Web 全量测试、typecheck、lint、build、API check；
- [ ] 架构、迁移、Compose 与安全测试；
- [ ] 完整 Compose 逐 Operation E2E；
- [ ] 每个昂贵边界的重启和网络故障注入；
- [ ] 执行本计划末尾“生命周期协议专项测试清单”并保存逐项证据；
- [ ] 三车道公平调度、2 核 2 GB、448 MiB Core 资源验证；
- [ ] Java 21/Spring MVC SSE 使用虚拟线程或等价有界异步执行器，验证长连接、断连、线程占用、PG 轮询负载和
  pinned-thread 指标；
- [ ] SSE 使用共享 tail observer 批量观察订阅 Run，高水位未变化时不得按连接执行 `readAfter+readTail`；覆盖
  多连接 DB QPS 不线性增长、低频 PostgreSQL 兜底、心跳、断连清理和每用户/全局连接上限；
- [ ] 真实供应商低额度预发布任务；
- [ ] SLO、调用数、reasoning、成本、重复副作用和协议纠正指标满足规格；
- [ ] 独立、受保护的 V2-aware route-off 回滚与 V1/V2 drain workflow 演练通过。

## Task 10：生产迁移、canary 与全量切换

- [ ] 冻结 SHA、三服务 digest、Catalog/Profile/Schema 版本和回滚组合；
- [ ] Agent readiness 暴露安全 manifest fingerprint，Core 在 schema-ready 时与本地 Registry 精确握手；错配必须在
  创建 Run 前 fail closed；
- [ ] 新 V2 Run 必须在不持有用户/Run/章节锁时做 1 秒 HTTP/1.1 实时握手，然后回到用户 advisory
  事务二次解析幂等身份；已有 V1/V2 重放不依赖 Agent 当前可用性，并发同标识只允许一个 Run；
- [ ] 构建同时精确识别迁移前/后 contract 的 route-off 兼容镜像；`schema ready=false` 时不装配任何 V2
  worker/mutation，并拒绝 allowlist/all；
- [ ] 演练“Java 兼容镜像在旧结构 ready → 在线迁移后仍 ready → 同镜像 schema ready=true 重启 →
  route-off 收敛”；Python V1-only 回滚只允许零 V2 数据并先做空数据 DDL rollback；
- [ ] 生产备份与恢复清单验证；
- [x] 固化 `docs/DURABLE_AGENT_V2_ROLLOUT.md` 与可执行阶段门禁：pre contract → 在线迁移后 route-off →
  schemaReady route-off → 用户/隔离小说交集 allowlist → V2-aware route-off drain；
- [x] 部署入口在本地测试中拒绝 partial、迁移后 Python/V1-only 自动回滚、已有 V2 却 schemaReady=false，
  并以无网络/无卷/无环境变量内容探针验证新旧 Core/Agent V2-aware 能力且保留 execution Redis 卷；
- [ ] 在精确数据库名与确认令牌门禁下执行具名迁移；
- [ ] 部署 V2 默认关闭版本并完成公网与跨服务 smoke；
- [ ] 按服务端用户 ID 和隔离测试小说开启指定账号 canary；
- [ ] 通过公共 HTTPS/CLI 验证身份、问答、discard、approve、cancel、SSE 重连和唯一用量；
- [ ] 观察至少 30～60 分钟或足量样本；
- [ ] 无硬停止条件后逐步放量并继续观察；
- [ ] 全量新任务切 V2，确认 V1 活动任务归零；
- [ ] 完成逐项证据审计后才宣称重构完成。

## 生命周期协议专项测试清单

### 租约、重派与重试

- [ ] `pending` 首次领取只递增一次 `attemptCount/fencingToken`，重复 dispatcher 不重复派发；
- [ ] `running` 租约过期且供应商请求具备真实幂等键时，状态保持 `running`，CAS 换新 fence/job 后只接受新 fence；
- [ ] `running` 租约过期但不支持幂等时不重派，Step 以 `MODEL_OUTCOME_UNKNOWN` 失败，Run 按生成/Reviewer
  失败策略分别收敛；
- [ ] 429、连接前失败和可证明未接受的 5xx 最多重试两次，`providerAttempts` 累计而 `attemptCount` 不变；
- [ ] 响应丢失、读超时、旧 fence callback、重复 callback 和 Core/Agent 重启不重复 Artifact、正式 apply 或计费；
- [ ] running 租约换 fence 与旧终态并发时，`stale` 保留完整 journal 并等待新 fence 原子重绑；只有 Core 已终态的
  `superseded` 才能压缩 tombstone，覆盖“换 fence 已提交但新 dispatch 尚未到达 Agent”的精确竞态；
- [ ] protocol correction 是独立 Step 并消费 Run 预算，原 Step 不隐藏第二次主模型调用。

### 取消与决定

- [ ] cancel envelope 精确绑定 run/step/job/fence/cancelRequestId，重复 cancel 重放同一响应和 Event；
- [ ] pending Step 取消后 skipped；running Step 只接收 matching-fence cancel ACK/累计 usage 后 skipped；
- [ ] matching-fence 迟到正常 Result 只补 usage，不创建候选、不推进 Run；旧 fence 连 usage 也拒绝；
- [ ] cancel ACK 丢失时租约到期不重派，Step 以 partial/unknown usage 收敛，最后一个活动 Step 收敛后 Run 才
  进入 cancelled；
- [ ] waiting_user cancel 保留 V2 Artifact/revision/Evaluation，但所有决定入口返回 RUN_TERMINAL；
- [ ] cancel/complete、cancel/approve、approve/approve 与 revise/cancel 并发由 Run 锁和 revision CAS 产生唯一结果；
- [ ] V2 discard 保留完整审计事实且不投递 Agent；V1 discard 继续删除且不写 V2 投影；
- [ ] edited approve 创建精确用户 revision、重验来源并一次性提交正式数据、Artifact、Run 和 Event；
- [ ] revise 失败时旧 revision 仍可审计但不可操作，新 revision 成功后才再次进入 waiting_user。

### SSE 与公共契约

- [ ] snapshot 与 baseSequence 在同一事务读取；snapshot 后提交的首个 Event 必须是 `baseSequence + 1`；
- [ ] 初次、旧 cursor、非法/超前 cursor、terminal、Redis 清空及 Core 重启按规格矩阵收敛；
- [ ] SSE `id` 只使用 Run sequence，客户端以 snapshot baseSequence 初始化后严格去重且不报假 gap；
- [ ] progress 在 `stepId+fence` 内严格递增、重复不新增 Event、并行 Step 获得唯一 Run 总序；snapshot 携带当前
  fence 的 `latestProgress`，`step_finished` 只按精确 fence 收敛单个活动 Step；
- [ ] 每个 WorkflowEvent payload 都通过同一生成 Schema；未知类型/字段不会触发终态副作用；
- [ ] V1/V2 GET、list、SSE、Artifact 和决定 DTO 可明确判别；V2 不伪造 command 状态且允许空 chapterId。
- [ ] Artifact summary 查询不读取/返回 payload、diff 或 evaluation；同一 awaiting_user 只发一次精确详情请求，
  304 复用缓存，Evidence/候选哈希不一致 fail-closed，403/404 清理 stale ID；

### 路由、预算、usage 与前端

- [ ] 同一 clientRequestId 在 allowlist 开关翻转和响应丢失后仍只创建 V1 或 V2 一份；不同 hash 稳定 409；
- [ ] 同一 mutation scope 的 V1/V2 并发创建只有一个成功，读/取消/决定不重新计算路由；
- [x] V1 `/resume` 不创建 V2；V2 任意状态调用 `/resume` 都稳定拒绝且不触碰 V1 Command；
- [ ] 并行 Reviewer、自动返工和摘要通过 Run 锁原子保留预算，合计不能超过 runBudgetProfile；首个 canary
  对协议错误确定性闭合一次后失败，`protocol_correction` 保持未启用；
- [ ] usage 是累计快照；complete 字段齐全，partial/unknown 不用 0 冒充未知，重复回调不重复 TokenUsage；
- [ ] `providerAttempts=0` 只接受 unknown 且无供应商字段；零尝试却携带 token/cost、无 Reservation 的伪造终报
  在任何 Step/Run/计费写入前被双端契约与 Core 域模型拒绝；
- [ ] 新增每 Step 的 `WorkflowBillingReservation`；Core 在接受 `waiting_provider` 前锁用户并原子预留，
  终报事务内按冻结价格重算、唯一写 TokenUsage/CreditLedger，余额不足时保证 0 次供应商调用；
- [ ] 覆盖结算矩阵：成功、模型失败、取消、`providerAttempts=0` 释放、unknown 保留待对账、重复回调不重复扣费、
  两个并行 Reviewer 不得超卖同一余额；
- [ ] 覆盖供应商实际 usage 超出 Step 预算：只允许 `STEP_BUDGET_EXCEEDED` Failure 入账并阻断产物/后续 Step；
  实际积分高于预留转 reconciliation、不自动超扣，终报仍幂等接受而非永久 4xx/5xx 重试；
- [ ] 覆盖 Accepted/preparing 乱序：progress 重携 resolvedModel，preparing 原子完成部署授权、Run 预算和额度预留；
  202 迟到只同值幂等，余额不足保证 providerAttempts=0；
- [ ] Core 冻结并验证 deployment provider/model 与 pricingVersion；V2 禁止复用 Agent 侧 V1 两段式 billing 旁路；
- [ ] 新增 manifest 管理的版本化 Prompt Profile，并验证 generation、consistency review、editorial review 的
  实际 system prompt 不同；模型输出只含语义字段，所有 SHA-256/ID/时间/金额由执行器确定性派生；
- [ ] 同一 Session 有非终态 foreground Run 时普通消息禁用；关闭 SSE 不取消任务，停止按钮才调用 cancel；
- [ ] 刷新后从 GET/snapshot 恢复 foreground Run、等待决定与停止状态，不依赖组件本地 phase。

### Drain、回滚与发布

- [ ] V1 联合 drain 视图覆盖 Task/Command/Outbox/Artifact/Agent job/callback，不能只看 Redis 或单一 phase；
- [ ] 存在长期 awaiting_user/recoverable V1 Task 时 V1 runtime 不删除、不转换、不静默超时；
- [ ] V2-aware route-off 镜像关闭新建后仍能查询、取消、调度、接 callback 并收敛既有 V2 Run；
- [ ] 存在 V2 数据时部署前 V2 旧镜像或执行 DDL rollback 均被门禁拒绝；
- [ ] canary 停止放量后，既有 V1/V2 Run 均能 drain，公开 HTTPS/CLI 显示唯一终态和唯一用量。
