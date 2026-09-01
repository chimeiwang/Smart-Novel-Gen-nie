# Core 权威耐久 Agent 执行内核

日期：2026-08-31

状态：已批准，实施中

批准范围：用户明确要求在产品需求不变的前提下重构 Agent 系统，允许完成验证后发布生产，并使用指定账号做生产黑盒验收。本批准包含本规格具名迁移的设计、隔离验证、开发库执行和最终受保护生产执行；不包含跳过备份、回滚、结构契约、测试、观察窗或视频生产开关门禁。

## 背景与生产证据

当前写作链由 Java Core 的 `WritingTask/WritingRunCommand`、Python Agent 的 Redis job、LangGraph
`GraphState`、`ReviewArtifact` 和前端本地 phase 同时表达状态。一次普通写作请求会经过开放式模型工具循环、
自动复审和自动返工；用户批准或丢弃已经由 Core 完成正式事务后，仍会再次投递 Agent 只为恢复图并收尾。

2026-08-29 至 2026-08-31 的旧生产镜像样本表明：

- 受理到 Agent 开始中位约 0.86 秒，队列不是主要瓶颈；
- 成功模型段从开始到等待用户为 71.7～372.2 秒，中位 171.4 秒；
- 每段通常调用模型 3～7 次，主要时间消耗在多轮上下文增长和超长 reasoning；
- 创作调用样本中约 88.5% completion token 属于不可见 reasoning；
- 前端只收到固定“作家开始”和边界事件，真实 Operation、证据、生成、Reviewer 与返工阶段不可见；
- 两次约五分钟 SSE 断开后均能重连并最终成功，符合“任务仍运行但用户感觉卡死”；
- 供应商协议失败曾直接终止质量运行；最新容错补丁不能证明整体执行架构可靠。

问题不是缺少更多 Agent，也不是简单增加并发，而是工作流权威、执行单元、上下文、恢复和事件协议没有形成单一闭环。

## 目标

1. Java Core 成为唯一业务工作流权威，Python Agent 退化为无状态、有界的 AI 执行器。
2. 每条用户指令创建独立 `WorkflowRun`；普通下一条消息不再恢复旧任务。
3. 每次昂贵模型调用对应一个耐久 `WorkflowStep`，完成后立即形成可恢复边界。
4. Core 为每个 Run 构造不可变、可重建、可引用的最小充分证据包。
5. 用固定、有预算的阶段流水线替代跨服务 LangGraph、开放式工具循环和模型业务提交工具。
6. 保留 `proposal -> ReviewArtifact -> 复审/返工 -> 用户确认 -> Core 应用` 产品不变量。
7. Reviewer 与生成器使用同一证据；基础设施失败与内容结论严格分离。
8. PostgreSQL 保存 Run、Step、Evidence、Event 和正式结果；Redis 不得成为业务状态权威，但以持久 AOF 保存尚未
   送达 Core 的执行 journal，并继续承担唤醒、限流、缓存和重放保护。
9. 向用户持续展示真实 Operation 和阶段，刷新、断流或进程重启后从权威状态恢复。
10. 在单机 2 核 2 GB、最多三个模型槽的预算内降低时延、调用数和 reasoning 浪费。

## 非目标

- 不改变中短篇、长篇、质量检查和视频各自的产品语义；
- 不允许 Agent 连接 PostgreSQL 或直接修改正式小说数据；
- 不启用生产视频、图片生成、TTS 或真实 Seedance；
- 不引入 Kafka、Temporal、Kubernetes 或按角色拆分五个 Agent 微服务；
- 不保存或展示 chain-of-thought / `reasoning_content` 原文；
- 不使用影子模型调用、双写或让同一个 Run 同时运行新旧引擎；
- 不回填或重新解释历史 `graphStateJson`。

## 总体架构

```text
浏览器 / Java CLI
       │ 显式命令或自然语言请求
       ▼
Java Core
  ├── Command Resolver / Operation Catalog
  ├── Workflow Orchestrator（唯一状态机）
  ├── Evidence Planner（不可变证据）
  ├── Step Scheduler（租约、分车道、预算）
  ├── Artifact / Review / Decision
  ├── Event Timeline / SSE
  ├── Billing / Usage
  └── PostgreSQL
       │ 版本化 ExecutionStepRequest
       ▼
Python AI Execution Service
  ├── Step Executor
  ├── Model Profile Registry
  ├── Provider Gateway
  ├── Structured Output Validation
  ├── Usage Reporter
  └── 有界内存队列与全局模型并发门
       │
       ▼
模型 / Embedding / 受控媒体供应商
```

Core 决定做什么、依据什么、处于哪一步以及结果是否可以进入下一阶段。执行器只在给定证据、Profile、
Schema 和预算下完成一个 Step。五个中文 Agent 名称保留为专家视角和 `ModelProfile` 标签，不再拥有状态、
权限、路由或工作流决定权。

## 产品不变量

- Agent 生成的正文、设定、大纲、伏笔、Beat Plan 和视频方案只能先形成待审候选；
- 用户批准时由 Core 在一个 PostgreSQL 事务内重验来源、应用正式数据、更新 Artifact、Run 和 Event；
- 正文、进展、设定、大纲、伏笔、Beat Plan、视频方案和后期决定不得混写；
- 来源身份、版本、完整内容哈希、选区码点范围和候选 revision 必须可重建；
- 正文、候选、Diff、证据、模型结果、日志和持久数据不得静默截断；
- 202、SSE 和执行器 ACK 只表示受理或观察，完成以 PostgreSQL Run/Artifact 为准；
- 写入口保持稳定幂等键，正式 head 继续使用时间戳或 revision CAS；
- 软质量建议不能替代作者确认；基础设施故障不能伪装成内容审核不通过。

## 单一 Operation Catalog

新增版本化、语言中立的 `contracts/agent-execution/operation-catalog.v1.json`。Java、Python 和 TypeScript
不得分别维护 Operation 列表。每个定义至少包含：

```text
workflow
operation
targetKinds / scopeKinds
mutating
evidencePolicy
generatorProfile
generatorStepBudgetProfile
outputSchema
deterministicValidators
reviewPolicy
applyHandler
runBudgetProfile
lane
```

Catalog 覆盖长篇当前 12 个可执行 Operation、中短篇固定四个操作、一致性终检、文风画像、资料 embedding、
开发环境两个章节影视化模型工作流。视频渲染只作为受控媒体 Step，不混入创作 Operation。

Core 与 Agent 启动时都必须验证 execution manifest、每个原始 Registry 文件 SHA、引用完整性和 supported 能力。
Agent readiness 还要返回不含凭据的 canonical execution-manifest fingerprint；Core 以自身加载的 fingerprint 精确
比对，`DURABLE_AGENT_EXECUTION_SCHEMA_READY=true` 时不一致即 readiness 失败并禁止 V2 route。镜像/Catalog
错配必须在创建 Run 前暴露，不能等到首个付费任务才以 Profile 409 发现。
发布门禁还必须在无网络、无数据库、无卷和无运行时凭据的容器中调用 Agent 已有的 Registry loader，输出同一个
canonical manifest fingerprint；loader 必须同时验证 manifest 声明的全部版本化 Catalog/Profile/Prompt/Deployment/
Output Schema/Step Budget/System Purpose/hash-vector 资产和引用，不能只读取镜像标签或 grep import。任何允许创建
V2 Run 的 allowlist 发布，目标 Agent、按切换前不可变 Image ID 冻结的自动回滚 Agent 与当前 Git 发布清单计算出的
预期 fingerprint 必须三方精确相等。旧回滚镜像无法离线证明 fingerprint，或 fingerprint 与新发布不同，都必须在
切换容器前拒绝 canary 和自动回滚；manifest 变更只能先保持 route-off 完成 drain，并另立兼容与放量审批。route-off
且不创建新 V2 Run 时，部署入口必须先在当前运行 Core 容器内只读验证实际进程环境的
`DURABLE_AGENT_EXECUTION_ROUTE_MODE=off`，再从权威 PostgreSQL 精确读到所有 `engineVersion=2` `WorkflowRun` 均为
`completed|failed|cancelled`、非终态数量为 0，才允许目标与回滚 Agent fingerprint 不同；只要仍有一个
`pending|running|waiting_user` V2 Run，就必须保持目标、回滚与发布预期三方同 fingerprint，或在任何版本切换和
`compose up` 前拒绝。目标 `.env=off` 不能替代运行中 Core 的证明，运行态检查失败时也不得继续查询后猜测安全。
两张 Agent 镜像无论是否同 fingerprint，仍须分别通过离线 Registry 完整性探针。
具体创建边界不依赖负载均衡器缓存的健康结果：Core 先做无锁、只读的跨引擎幂等预解析；已存在的
V1/V2 记录直接按原引擎重放，不因 Agent 短暂离线或 manifest 升级被阻断。只有确认是新 V2 请求时，
Core 才在任何 Run/Step/Evidence/Event 写入前，使用同一个固定 HTTP/1.1 客户端、1 秒有界超时和实时
GET readiness 精确核对 fingerprint；失败统一返回不含 endpoint 或 hash 的稳定 503。网络探测不得发生在
用户 advisory lock、Run 锁、章节锁或其他写事务内；探测后再进入原用户锁并二次解析幂等身份，
保证并发同标识仍只创建一个 Run。检查后 Agent 若瞬时升级，仍必须由每个 `ExecutionStepRequest` 的冻结
Profile/Schema/部署元组校验 fail closed，健康握手不替代请求级协议校验。

`runBudgetProfile` 是整条 Run 的累计硬上限，不得直接下发为单 Step 预算。另设同目录、同 manifest 管理的
Step Budget Registry；`generatorStepBudgetProfile`、Reviewer 的 `stepBudgetProfile` 与 System Purpose 的
`stepBudgetProfile` 都必须引用其中一个版本化条目。每个条目固定一次主模型调用的 token、reasoning、金额、墙钟、
供应商重试和协议纠正上限。`reviewPolicy` 还必须显式固定 Reviewer 的 `outputSchema`、`rubricVersion`、
`evidencePolicy` 与 `lane`。Core 创建 Step 时冻结解析后的完整预算；Agent 只执行该快照，任何一端都不得从 Run
总额、模型名或隐藏默认值推导 Step 配额。

结构化按钮和 CLI 显式操作跳过意图模型。自然语言请求先创建低成本、无工具的 `resolve_intent` Step，只返回
严格 `ProposedCommand`。Core 补齐并校验资源 ID、范围和权限；不确定时 Run 进入可见 `waiting_user` 澄清，
不得猜测后直接变更。

迁移期间允许在 API 边界把旧请求一次性转换为规范命令，但 legacy 形态、`selectedAgents` 和自由文本关键词
不得进入新 Step、Evidence 或恢复逻辑。

## 领域模型与权威状态

### `WorkflowRun`

`WorkflowRun` 成为所有新 AI 工作流的唯一业务生命周期。现有质量运行继续兼容读取；新运行通过
`engineVersion=2` 与旧记录隔离。

权威状态沿用现有值：

```text
pending -> running -> waiting_user -> completed
                    -> failed / cancelled
```

新增列：

- `engineVersion`、`workflow`、`operation`、`operationCatalogVersion`；
- `writingSessionId`、`parentRunId`；
- `idempotencyKey`、`requestHash`；
- `targetType`、`targetId`；
- `budgetJson`、`modelPolicyJson`；
- `currentEvidenceBundleId`、`lastEventSequence`、`revision`；
- `cancelRequestId`、`cancelRequestedAt`、`completedAt`、`errorCode`。

现有 `kind` 只作为旧查询兼容投影；V2 以 `workflow + operation` 为权威。`chapterId` 在完整迁移后允许为空，
以支持小说、大纲、文风和 RAG 等目标；`userId` 对 V2 必填。

### `WorkflowStep`

一个 Step 最多包含一次主模型调用。协议纠正、Reviewer、自动返工和证据扩展都是新的 Step，不能隐藏在
同一个长对话循环中。

状态沿用现有值：

```text
pending -> running -> completed / failed / skipped
```

`pending` 且租约未到期表示已派发未开始；`running` 租约到期后的处理必须按结果确定性分类，不能盲重发。
`attemptCount` 只统计 Core 对该 Step 的派发次数，首次派发从 0 原子增加为 1；`providerAttempts` 统计该 Step
生命周期内实际发向供应商的请求次数，供应商内部重试不得伪装成新的 Core 派发。

新增列：

- `ordinal`、`purpose`、`lane`；
- `attemptCount`、`nextAttemptAt`；
- `fencingToken`、`leaseExpiresAt`、`heartbeatAt`、`activeJobId`；
- `idempotencyKey`、`requestHash`、`inputHash`、`resultHash`；
- `evidenceBundleId`、`artifactId`、`artifactRevision`；
- `modelProfile`、`modelProfileVersion`、`outputSchema`、`outputSchemaVersion`、`budgetJson`、`resolvedModelJson`；
- `usageJson`、`lastProgressSequence`、`cancelRequestId`；
- `submittedAt`、`updatedAt`、`completedAt`、`errorCode`。

`budgetJson` 是不可变的授权快照；`usageJson` 是当前 Step 的累计已知用量，`lastProgressSequence` 用于拒绝倒退或
重复进度，二者不能混写。`resolvedModelJson` 只由 Agent 受理响应冻结，保存 deployment fingerprint、provider、
model、reasoning mode 与供应商幂等能力；终报必须与该快照一致。Run 与活动 Step 的 `cancelRequestId` 必须一致，
用于校验取消终报，不能只靠瞬时 HTTP 请求或 Event 反推。

`modelPolicyJson` 不是只保存 Reviewer 名称的提示字段，而是 Run 创建时解析并冻结的完整执行计划：必须含
`operationCatalogVersion`、生成器及每个 Reviewer/System Step 的逻辑 Profile 与 Prompt 引用/hash、完整 Output
Schema 与 hash、Step Budget、Evidence 授权视图、lane，以及 review merge/onUnavailable 策略。后续创建 Step、
重派和回调验证只能从该快照复制/读取；当前镜像 Registry 只用于创建新 Run 和在 `preparing` 前授权新部署，不得因
Profile/Schema 在新版本下线而拒绝已越过 provider 边界的旧 Run 终报。终报计费同样只按不可变 Reservation 中冻结的
resolved model、pricingVersion 与 rates 校验/结算。这样在途 Run 可以跨 Core/Agent 重启和 Registry 升级收敛，且不
要求把可变运行时配置冒充历史权威。

数据库必须以具名 trigger 保护上述 V2 身份快照：Run 的归属/目标/请求 hash/预算/完整执行计划和 Step 的
run/ordinal/purpose/lane/input/hash/Evidence/Artifact/Profile/Prompt/Output Schema/预算在插入后不可改写；
`resolvedModelJson` 与 `resultHash` 只允许从空值冻结一次，此后不得漂移。状态、租约、累计 usage、取消和终态时间等
生命周期字段继续按 CAS 更新。该保护只作用于 `engineVersion=2`/具名 V2 Step，不能破坏现有 V1 行。

现有 `stepType` 作为宽分类：模型生成/复审为 `agent`，确定性处理为 `persistence`，用户决定为
`user_confirmation`。精确用途由 `purpose` 表达。

### Evidence

新增 `WorkflowEvidenceBundle`：

- `id, runId, version, policyVersion, manifestJson, manifestSha256, totalBytes, createdAt`；
- 同一 Run 的 version 严格单调，bundle 一经创建不可修改。

新增 `WorkflowEvidenceItem`：

- `id, bundleId, ordinal`；
- `resourceType, resourceId, exists, resourceRevision, resourceUpdatedAt`；
- `contentType, contentText, contentJson, contentSha256, byteCount`；
- `rangeJson, metadataJson`；
- 存在的 item 只能使用 text 或 JSON 内容之一并完整保存；不存在的资源使用显式 absence item，不能伪造空内容。

大文本可以显式拆块，但 manifest 必须记录总块数、每块范围和哈希。证据超出模型窗口时，只能缩小 Operation
范围或创建可审计的 `summarize_evidence` Step；Run/Event 必须说明模型实际看到哪些 item，禁止静默丢弃。

### Event

新增 `WorkflowEvent`：

- `id, runId, sequence, eventType, payloadJson, dedupeKey, createdAt`；
- 唯一 `(runId, sequence)` 与 `(runId, dedupeKey)`；
- Event 与对应 Run/Step/Artifact 状态在同一事务提交。

SSE 从 PostgreSQL Event 回放，Redis 只可作为低延迟唤醒。浏览器每次连接先获得权威 Run snapshot，再按
sequence 重放。刷新、Redis 清空和 Core 重启不能丢时间线。

SSE 的正确性仍只依赖 PostgreSQL，但阻塞等待不能永久占用稀缺平台线程。Java 21 生产镜像必须为 Spring MVC
异步请求启用虚拟线程并保持 JVM keep-alive，或提供等价的有界异步执行器；需要用并发长连接和 JFR/线程指标验证
没有 pinned-thread 导致的吞吐倒退。Core 内同一进程必须由共享 tail observer 批量观察所有已订阅 Run 的
`lastEventSequence/status`，不能让每条空闲 SSE 每秒各执行 `readAfter + readTail` 两次查询；只有 Run 高水位变化、
terminal/waiting_user 收敛或低频兜底到期时，对应连接才读取 Event。通知只负责唤醒，丢失时仍由低频 PostgreSQL
批量轮询恢复；它不能重新升级为事件权威。连接必须有心跳、关闭条件、订阅清理和全局/每用户上限。

首版共享 observer 使用以下可执行资源边界：每个 Core 进程最多保留 256 条 V2 SSE 连接，同一用户最多 8 条；
达到任一上限时必须在 `SseEmitter` 建立前以稳定 429 拒绝。observer 每秒只对当前不同的订阅
`runId + userId` 做一次批量 `lastEventSequence/status` 查询；发生高水位变化或新订阅需要补齐 snapshot 后并发提交
的 Event 时，再以每个 Run 最多 100 条的一次批量 tail 查询公平推进所有有积压 Run。同一 Run 的多条连接共享该次
Event 读取并各自按自己的 `baseSequence` 去重，初始 snapshot/baseSequence 仍由每条连接独立在同一
`REPEATABLE READ, READ ONLY` 事务读取，绝不从进程缓存构造。

每条连接最多排队 4 个共享更新批次；写端跟不上导致队列满时，observer 必须立即注销该订阅并关闭观察，客户端只能
通过重新连接取得新的权威 snapshot，禁止丢弃中间 Event 后继续伪装连续。15 秒心跳只写 SSE 注释，不触发数据库
查询。正常终态、`waiting_user`、客户端断线、输出异常、慢消费者、observer 查询异常和应用停机都必须幂等注销订阅；
最后一条订阅离开后立即移除对应 Run 的进程状态。`DURABLE_AGENT_EXECUTION_SCHEMA_READY=false` 时不装配
V2 repository、observer 或 stream service，纯 V1 请求不得探测 V2 表。Spring MVC 的异步流使用 Java 21 虚拟线程，
并显式保持 JVM 存活；阻塞数据库调用仍只能发生在共享 observer，而不能回到每连接轮询。
连接在 HTTP 200 前先预留上限名额并注册 snapshot 的 baseSequence，但只有 `run_snapshot` 已成功写入客户端后才激活
增量队列与慢消费者计数；否则 Spring 异步线程尚未获得执行机会时不能被误判为慢消费者。注册到激活之间提交的 Event
由 Run 的有界共享历史补齐；超过历史边界时统一回拨该 Run 的共享读取 cursor，既有连接按自身已发送 sequence 过滤
重读前缀，新连接仍须收到从 baseSequence 开始的完整连续后继。

写作 SSE 的 Java OpenAPI 生成类型固定映射为 Spring MVC `SseEmitter`；二进制文件下载继续映射为
`StreamingResponseBody`，两者不得共用同一个生成类型。原因是 Spring Framework 7 已把
`ServletServerHttpResponse#getBody()` 返回流的 `flush()` 改为无操作，而 `StreamingResponseBody` 的最终
`ServerHttpResponse.flush()` 只在回调返回后执行；一个尚未终态的长连接因此不会提交 200 响应头或首帧。
不得以全局 `spring.http.response.flush.enabled` 兼容开关恢复旧行为，因为它会同时改变全部响应和二进制流语义。

`SseEmitter` 适配层必须继续发送当前协议的原始 UTF-8 frame，精确保留 `id: `、`event: `、`data: ` 与
`: 心跳` 的现有字节形式；不能因使用框架 builder 改变空格、JSON 序列化或心跳。每次 frame 只能调用一次 emitter
send，由 Spring 的 emitter handler 在该次 send 后执行真实 `ServerHttpResponse.flush()`。应用 service 只返回平台
`ManagedSseEmitter`，不得读取 `RequestContextHolder` 或 Servlet 对象；Writing API 层必须把 emitter 显式 arm 到
当前请求。平台 `AsyncHandlerInterceptor.afterConcurrentHandlingStarted` 只能在 Spring 已完成 emitter handler
初始化后启动连接 worker，因此首次 send 返回即代表首帧已经经过真实 handler send/flush，随后才允许调用
subscription `activate()`。不得在 Controller 返回 emitter 前启动 worker，也不得用 sleep、反射或全局 converter
猜测 handler 是否已就绪。

V2 的 snapshot、归属、engine 和 cursor 仍须在 Controller 返回 200 前同步校验并预留订阅；每条连接由独立
Java 21 虚拟线程发送 `run_snapshot`。正常完成、timeout、异步错误、客户端断开、Spring 已完成态、worker 中断和
应用停机必须共同经过一个幂等关闭门，精确注销 subscription、移除 live session 并停止连接 worker。启动 worker
失败与本地停机必须显式完成已初始化的异步响应，不能依赖 interceptor 抛错；客户端断线则使用不再写响应正文的
清理路径。发送引发的 `IOException` 视为连接断开；`IllegalStateException` 只有在 emitter/session 已可证明完成或
中止时才可同类处理，仍处于可写态的 converter/handler 异常必须走受控错误完成。Spring
`AsyncRequestNotUsableException` 由专用 no-body handler 安全分类，不得向已提交响应二次写错误 JSON。终态必须先
成功发送其最后一帧，再调用 emitter `complete()`，不得先完成后补帧。service 必须登记全部已创建 session；bean
关闭时无论 session 是否已 arm、handler 是否已初始化或 worker 是否已启动，都必须在有界时间内完成/中止响应并使
subscription、session、worker 与共享虚拟线程 executor 全部归零。

共享 PostgreSQL 查询的单轮暂时失败不立即制造全部客户端重连风暴：连接继续只发心跳，observer 按一秒兜底间隔
重试；连续 3 轮 high-water/Event tail 查询失败后才注销受影响订阅并断开，使客户端重新走 snapshot。只有一轮完整
观察（high-water 及该轮必需的 Event tail 均成功）才清零连续失败计数。observer 循环的未知运行异常必须以稳定分类清理当前订阅并重新进入空闲观察循环，不能让
后台虚拟线程静默死亡或继续保留永远不会收到更新的连接。

observer 的两类批量查询还必须使用同一个具名超时配置：PostgreSQL 只读事务的
`statement_timeout=2s`，jOOQ/JDBC `Statement#setQueryTimeout=2s`，当前借用连接的
`Connection.networkTimeout=3s`，observer 单轮 wall-clock 为 `4s`，语句取消和连接硬中止后的等待分别为
`500ms` 和 `1s`，整个 observer 停机上限为 `5s`。该顺序必须满足
`statement/query < network < wall-clock`；这些值不得散落在 repository 和 observer 中各自漂移。
连接级 network timeout 只在该次查询的专用只读事务内设置，必须在连接归还 Hikari 前恢复原值；
不得把 observer 的短超时泄漏给其他业务 SQL，也不得依赖全局 JDBC URL `socketTimeout` 修复本局部路径。

墙钟门禁使用专用的单飞查询执行器。超时时必须先通过 repository 已注册的句柄显式调用
`Statement.cancel()`，仍未退出再对该借用连接调用 `Connection.abort()`；`Future.cancel(true)` 只能作为
辅助中断，不构成 JDBC 查询已取消或线程已退出的证明。必须以当前查询调用自身的完成门证明它已
退出，之后才能开始下一轮；硬中止后仍未退出时，observer 必须停止接受新订阅、结束现有订阅并记录稳定
错误分类，禁止继续叠加卡死查询。每次失败日志至少记录查询阶段、墙钟上限、实际耗时、取消/硬中止请求与连续失败轮数，
不记录 SQL 绑定、用户正文或凭据。应用停机必须取消当前查询、关闭共享查询执行器并在 `5s` 内证明 observer worker、
query worker 和活动查询全部归零；任一对象仍未退出必须以稳定错误明确失败停机，不得静默报告关闭成功。

### Evaluation

新增 `WorkflowEvaluation`：

- 必须绑定 `runId, stepId, evidenceBundleId`；只有评审候选时才同时绑定可空的 `artifactId, artifactRevision`；
- 保存 `evaluatorProfile, rubricVersion`；
- `executionStatus=completed|incomplete|failed`；
- `contentVerdict=pass|issues_found|cannot_assess`；
- `findingsJson` 每项包含维度、严重度、主张、候选位置、证据引用、建议和置信度。

模型、网络或协议失败只改变 `executionStatus`，不能生成 `block` 内容结论。V2 API 直接读取该表；旧
`ReviewArtifactEvaluation` 只服务 V1 历史任务，不做双写投影。

### Credit Reservation 与用量结算

新增 `WorkflowBillingReservation`，一条记录只绑定一个逻辑模型 Step：

- `id, runId, stepId, userId, requestId`；
- `pricingVersion, pricingJson, reservedMicros, chargedMicros, usageJson`；
- `status=reserved|settled|released|reconciliation_required`；
- `createdAt, updatedAt, settledAt`。

它不是供应商 `maxCostMicros` 的别名。Step/Run 中的 `maxCostMicros` 约束供应商成本事实；用户积分使用 Core
版本化计费规则单独计算。Core 必须在允许 `preparing -> waiting_provider` 之前锁定 User、Run、Step，并按同一用户
所有未结算预留计算可用余额；只有预留成功才接受 `preparing` progress。并行 Reviewer 逐个在同一 User 锁下预留，
不能分别读取同一份余额。预留不足时 Core 在同一事务把对应 Step/Run 收敛为稳定失败并发布事件，Agent 收到 stale
回执后不得调用供应商。

预留使用 Step 创建时冻结的版本化计费快照和最坏可计费上限，不能把未知 token 当 0，也不能在 Agent 回调后再
追认授权。成功、失败和取消终报都在处理 Step 终态的同一 PostgreSQL 事务中结算：

- 已知 `input/cached/completion` 时由 Core 重算金额，禁止信任 Agent 自报金额；原子写入唯一 `TokenUsage`、
  `CreditLedger`、扣减余额并把预留置为 `settled`；
- `providerAttempts=0` 且没有供应商用量时置为 `released`；
- 已发生供应商尝试但计费字段不足时置为 `reconciliation_required`，继续占用预留额度，禁止伪造零费用或自动释放；
- 重复 terminal callback 只能命中相同 `requestId/resultHash/usage` 并返回 duplicate，不得二次扣费；
- 后续供应商对账只能补齐该 reservation 与 TokenUsage，不得反转 Step、Run、Artifact 或 Evaluation 终态。

`reconciliation_required` 必须有受审计、可鉴权的结算出口，禁止通过 SQL 或临时脚本直接修改余额与预留。
首版固定使用
`PUT /internal/v1/workflow-runs/{runId}/steps/{stepId}/billing-reconciliation`，请求与响应由共享
Pydantic 契约生成 Java DTO。请求必须完整携带 `protocolVersion=2.0`、路径一致的 `runId/stepId`、显式可空
`novelId`、稳定 `reconciliationId`、预留的 `reservationRequestId`、不可变供应商报告引用
`supplierEvidenceRef`、报告原文 `supplierReportSha256`、`decision=exact_usage|proven_zero` 和精确累计
`StepUsage`。入口只接受独立 `billing:reconcile` 服务权限；JWT 固定绑定 `task_id=stepId`、`run_id=runId`、
`novel_id`、原始正文、路径、时间和幂等键，并继续经过直接对端 CIDR 与 Redis 防重放校验。Python 回滚 Core
只保留同形契约并稳定返回 503，不得实现第二套结算逻辑。
Java API 先校验路径与正文身份、显式 `novelId` 并完成上述验签，之后才允许调用 billing 自有
`billing::reconciliation` 应用端口；未认证请求不得触发 Workflow repository 或资源探测。该端口由 Workflow
模块实现，billing 模块不得反向依赖 Workflow，以保持单向 `workflows -> billing` 模块图。

Core 在同一短事务中严格按 Run → Step → BillingReservation → User 锁行，并再次验证 V2 身份、归属、
`reservationRequestId`、Step 终态和 reservation 恰为 `reconciliation_required`。请求 usage 必须相对终态
`WorkflowStep.usageJson` 单调不减，且不得改写 Step usage：

- `exact_usage` 只接受 `usageStatus=complete`、`providerAttempts>0` 的完整供应商用量；Core 只按 reservation
  中冻结的 `pricingVersion/pricingJson` 重算积分，金额不得超过 `reservedMicros`，并原子写入唯一
  `TokenUsage`、必要的 `CreditLedger.ai_charge`、余额和 `status=settled`；
- `proven_zero` 只接受供应商证据明确支持的 `usageStatus=unknown`、`providerAttempts=0`、零协议纠正且所有
  供应商字段均为空的快照，原子置为 `released`，不写 `TokenUsage/CreditLedger`、不扣余额；
- 余额低于应扣金额、冻结价格漂移、金额越过预留、证据引用或 SHA 不合法、usage 倒退/矛盾、已有用量或账本
  与预留冲突时全部 fail closed，reservation 继续保持 `reconciliation_required`。

不新增对账表或列。结算后的 reservation `usageJson` 保持既有顶层 `StepUsage` 字段，并追加
`reconciliation` 审计块，至少冻结 protocol、`reconciliationId`、reservation requestId、供应商证据引用与
SHA、decision、完整请求 canonical SHA、结算金额、结算后余额和时间。既有读取忽略该附加块并继续按顶层
usage 计算。Core 以 `reconciliationId` 的事务级 advisory lock 串行化，并检查该 ID 未绑定其他 reservation；
同一 ID、同一路径和完全相同正文在已结算后返回 duplicate，不重复写 TokenUsage、Ledger 或余额，任何正文漂移
固定冲突。对账事务只改变 Reservation、TokenUsage、CreditLedger 和 User 余额，不得更新 Step、Run、Artifact、
Evaluation 或其终态。

Agent journal 只保存执行和未送达回调事实，不保存余额权威。V2 不调用 V1 的 `/billing/authorize` 与
`/billing/usage` 两段式旁路；否则会出现 Core Step 与 Agent 扣费各自成功一半的分布式事务。Core 必须同时冻结并
校验允许的 deployment provider/model 与 `pricingVersion`，只校验 Agent 自算 fingerprint 不足以构成模型或价格授权。
部署授权由 manifest 管理的版本化 Deployment Profile 唯一给出，并精确绑定 environment、provider、model、
`transportProfile`、非敏感 `endpointProfile`、`structuredOutputRoute`、`capabilityVersion`、reasoning、请求幂等事实、
`pricingVersion` 与 billable。上述公开材料全部进入 deployment fingerprint；生产只授权官方 DeepSeek HTTPS 端点
Profile，custom endpoint 只能在 dev/test 的独立授权项中出现，通用 OpenAI-compatible 适配器不得冒充
`deepseek_v4` 原始适配器。

### ReviewArtifact

继续保留现有 `ReviewArtifact`、不可变 revision 和正式应用器。归属必须二选一：

```text
V1: taskId != null, workflowRunId == null
V2: taskId == null, workflowRunId != null
```

V2 Artifact 的资源 ID、来源绑定、选区和 diff 全部由 Core 从 Evidence 和规范命令物化，不信任模型回传。

V2 Artifact 还必须避免把长正文当作列表状态或在同一 revision 中重复保存。`rewrite_chapter_selection` 的耐久
revision 只保存可重建的最小事实：Schema 版本、Evidence bundle/item 身份、来源与选区哈希、Unicode code point
范围、replacement 与其哈希、candidate 哈希、生成 Step/result 身份；不得在 `payloadJson` 与 `diffJson` 中重复
保存完整 source、before、after、candidate、prefix、suffix 和上下文副本。Core 读取精确 revision 时从不可变
Evidence 与 replacement 确定性重建完整候选和 Diff，并在返回前复验全部哈希；任一 Evidence 缺失或哈希不匹配都
必须以结构化完整性错误失败，不能用当前章节内容补洞。

Artifact 集合查询只承担托盘索引，返回 ID、归属、kind/status、title/summary、revision、可操作性和时间等有界摘要，
不得携带 `payload/diff/evaluations` 或隐式逐项读取这些大字段。完整内容只由精确
`artifactId + artifactRevision` 的详情读取返回；详情使用该 revision 的稳定 ETag，支持 `If-None-Match`，前端按
`artifactId + revision` 缓存。同一 `awaiting_user` 事件不得同时触发详情与全量集合兜底；403/404 表示持久身份已
失效或不可见，必须清理本地 stale ID，不能循环重试。迁移期保留 V1 已发布响应的兼容入口，V2/Web 使用明确的
summary/detail 契约，不能通过把大字段置空来伪装旧 `ReviewArtifactResponse`。Artifact summary/detail 都必须携带
显式 `engineVersion`；CLI 和 Web 只能按该判别字段构造决定请求，不能用 `taskId/workflowRunId` 是否为空猜引擎。

## 固定执行流水线

标准可变更 Operation：

```text
run_accepted
-> intent_resolved（显式命令跳过模型）
-> evidence_ready
-> generation_started
-> candidate_ready
-> deterministic_validation
-> review_started
-> review_completed
-> awaiting_user
-> applying
-> completed
```

只读问答在生成成功后直接 completed。质量检查保存报告后 completed。中短篇生成只创建一个候选，不自动进入
下一文档阶段。视频继续服从开发环境门禁和独立正式版本链。

### `long_serial.answer_question` 首个只读纵切

长篇问答使用 Catalog 中已经保留的精确版本 `long_serial.answer_question`，不得在 Core 或 Agent 通过 Operation
名称硬编码模型、Prompt、Schema 或预算旁路。该 Operation 只创建一个 `purpose=generation`、`lane=interactive`
的模型 Step；不创建 Reviewer Step、ReviewArtifact、自动返工或用户决定 Step，也不进入 LangGraph 或开放工具循环。

执行计划固定引用：

- Evidence Policy：`evidence.long_serial.answer.v1`；
- Model Profile：`editor.answer.v1`，`reasoningMode=disabled`；
- Prompt Profile：`prompt.editor.answer.v1`；
- Deployment Profile：`deployment.editor.answer.v1`；
- Output Schema：`output.chat_answer.v1`；
- Step Budget：`step_budget.long_serial.answer_question.generator.v1`；
- Review Policy：`review.none.v1`，`mode=none`，Reviewer、rubric、Reviewer Schema 与 Reviewer Step Budget 均为空。

Core 构造的 `ExecutionStepRequest` 继续复用通用 `2.0` wire，`input.userInstruction` 保存完整、非空白的作者问题，
`artifactId/artifactRevision` 均为空。首切只接受 `targetKinds=[chapter] + scopeKinds=[chapter]`，并把目标章节
完整正文冻结进不可变 Evidence bundle；小说级、章节范围和大纲节点问答仍由 V1 收敛，不得借首切 Catalog 宣称已迁移。
创建 Run 还必须携带归属于同一用户、小说和章节的 `writingSessionId`；缺失时稳定返回
`409 WRITING_SESSION_REQUIRED`，不得创建没有会话恢复位置的回答。`writingSessionId` 是 Core 的 Run/消息归属事实，
不复制进只含 `userInstruction` 的模型 input，也不由 Agent 生成或修改。
模型结果必须严格为
`{"answer": string}`，`answer` 至少包含一个非空白 Unicode 字符，不允许额外字段、Markdown 控制信封、工具调用、
日志或推理原文。Agent 必须先按冻结 Output Schema 校验，再用共享 `ChatAnswerOutput` 做同形语义复验；空串、纯空白、
错误字段或不合法结构以稳定 `MODEL_OUTPUT_PROTOCOL_INVALID`/`MODEL_OUTPUT_SCHEMA_INVALID` 失败，不能保存半截回答或
猜测修复。

问答仍完整执行 resolved model/deployment 授权、Step/Run 预算、`preparing` 计费预留、累计 usage、AOF journal、
fence、租约、取消、未送达终态回放和 callback 回执语义。成功回调后由 Core 在同一事务持久化完整 agent
`WritingMessage`、完成 Step/Run 并写 `step_finished` 与 `completed(outcomeType=chat_answer,resultId=<messageId>)`
Event；Agent 不生成消息 ID，也不直接写会话。问答失败或取消不得留下成功消息，普通下一条问题继续创建新 Run。
消息元数据的规范化与 content hash 由 `workflows::workflow-domain` 的单一 codec 提供，V1/V2 写作消息复用该实现；
Workflow callback 不得反向导入 writing 模块内部 helper，避免形成 `workflows -> writing -> workflows` 模块环。

浏览器收到 `completed(outcomeType=chat_answer)` 后，必须按当前事件流绑定的精确 `writingSessionId` 重新读取
PostgreSQL 权威会话消息，并保留已经收敛的 Run 终态；会话已切换时，迟到响应不得覆盖新会话。该终态不能只刷新
会话摘要或依赖用户重新选择会话，也不得把 SSE payload、日志或本地拼接文本当作回答。`chat_answer` 不创建
ReviewArtifact，因此完成事件不得为它触发待审核 Artifact 全量刷新。Web 对 `editor.answer.v1` 显示稳定业务标签
“章节问答”，不暴露 deployment key、Prompt、指纹或内部端点。

模型不再调用 `begin_artifact_output`、`submit_evaluation`、`submit_quality_report`、更新构建器或其他业务提交
工具。Step 最终响应本身是严格 Schema；Core 验证后创建业务事实。

长文本输出必须使用完整单响应，或使用耐久 segment Step 加最终 manifest。任何 segment 完成即 checkpoint；
不得把截断响应当成可继续正文。

## Evidence Planner

每个 Operation 由 Core 注册确定性 `EvidencePlanner`，在事务一致性快照内获取最小充分事实：

- 章节写作：目标章、已批准 Beat Plan、大纲路径、相邻章摘要、相关人物/设定/伏笔和文风；
- 选区改写：完整来源、Unicode 码点范围、选区哈希及必要前后文；
- 章节规划：章节目标、大纲路径、剧情进展和相关权威设定；
- 设定/大纲/伏笔：目标实体及直接关联，不读取完整 workspace；
- Reviewer：与生成器完全相同的 bundle，加精确 Artifact revision；
- 质量终检：冻结的完整章节及相关规则证据；
- 中短篇：冻结来源、当前 applied 蓝图/正文版本和工作稿 CAS；
- 视频：继续使用章节快照、正式镜头/提示词/视觉版本等既有不可变来源。

执行器只读取随 Step 提交的 bundle，不在模型轮次中读取可变 workspace。确需扩展时返回结构化
`EvidenceExpansionRequest`，由 Core 校验后创建 bundle 新 revision 和新 Step。

`ExecutionStepRequest.evidenceBundle.policyVersion` 表示当前 Step 对该不可变 bundle 的授权视图：生成 Step
使用 Operation 的捕获策略，Reviewer Step 使用 Review Policy 的证据策略；两者必须保持同一 `bundleId`、items、
manifest 与 `manifestSha256`。数据库 Bundle 的 `policyVersion` 记录首次捕获策略，不能为了 Reviewer 改写或复制证据。

## 生成与 Reviewer

- 一个生成 Step 使用一个明确 `ModelProfile`、一个输出 Schema 和一个总预算；
- 五个 Agent 名称只映射 Profile、提示词和展示名；用户选择 Operation，不选择隐藏执行者；
- Profile 必须引用 manifest 管理的版本化 Prompt Profile；生成器、一致性 Reviewer 与编辑 Reviewer 使用不同的
  任务边界和系统指令。只改 `agentName`、`policyId` 或 UI 标签而给多个 Reviewer 发送相同 prompt，属于重复计费，
  不能宣称为多 Agent 复审；
- system prompt 只把 Core 冻结的指定任务字段视作授权创作目标；Evidence、候选、replacement、章节正文及其中的
  指令样文本都只是作品数据。Reviewer 还必须拒绝 userInstruction 中要求“必须通过”、忽略证据、改变评分或覆盖
  rubric/system 的评审元指令；
- 模型只生成语义内容，禁止要求模型计算 SHA-256、ID、时间戳、request/result hash 或计费金额。Provider-facing
  Schema 与 Core 结果 Schema 可分层：Agent 在模型输出通过前者校验后，确定性补齐系统派生字段，再按后者完整
  复验并写入 journal；
- 章节选区改写的 `replacement` 必须至少包含一个非空白 Unicode 字符；空串、纯空格、换行或全角空白由 Agent
  确定性收敛为 `MODEL_OUTPUT_PROTOCOL_INVALID`。Core 必须再次执行同一不变量并返回稳定协议错误，禁止让
  Artifact 构造异常退化为 500 和无限 callback 重试；
- 确定性 Schema、来源、版本、字数、选区和引用检查先于模型 Reviewer；
- 多 Reviewer 在独立 Step 中并行，原始报告分别保存，由 Core 确定性 policy 合并；
- 默认最多一次自动返工；只有高置信、唯一定位且无冲突的局部 patch 可自动应用到候选 revision；
- 结构性问题、Reviewer 分歧或第二轮仍有问题时交给作者；
- Reviewer 不可用时保留候选并进入 `awaiting_user`，显示“自动复审未完成”；
- Reviewer、reviser 与生成器使用相同 Evidence bundle，不读取工具历史或推理原文。

## 用户决定

用户决定提交给 Core，并绑定 `expectedArtifactRevision` 与稳定 `clientRequestId`：

- `approve`：同一事务重验来源、正式应用、Artifact applied、决定 Step completed、Run completed、Event；
- `edited approve`：先创建用户编辑 revision，再按同一事务应用；
- `discard`：V2 保留 Artifact、全部 revision 和 Evaluation 审计事实，记录决定 Step/Event 后完成 Run；V1
  继续沿用现有删除语义，不做双写投影；
- `revise`：记录决定 Step，并创建新的 revision generation Step；
- 来源改变：拒绝应用，要求显式 rebase 并创建新 Evidence bundle。

approve/discard 不投递 Agent，不恢复图，不进行“建议下一步”的模型调用。

现有公共入口 `POST /api/v1/review-artifacts/{artifactId}/decision` 保持路径不变，但请求与响应必须按
`engineVersion` 明确判别。为兼容已经发布的 V1 客户端，请求省略 `engineVersion` 时只解释为 V1；显式
`engineVersion=2` 才能决定 V2 Artifact。现有 wire 字段 `expectedRevision` 在 V2 分支中的规范含义就是
`expectedArtifactRevision`，不得退化为 Run revision 或 Step ordinal。V2 仍强制携带 16～128 字符的
`clientRequestId`，且：

- `approve` 只允许可空的 `editedReplacement`；选区首切拒绝 `editedContent` 和 `selectedUpdateRefs`；
- 带 `editedReplacement` 的批准只能以锁定的精确 Artifact revision 为基线创建具名用户编辑 revision，
  重新计算 replacement hash、Unicode 码点拼接后的 candidate 与完整 Diff，不能接受用户提供或改写 source、
  prefix、suffix、范围和来源哈希；
- `revise` 必须携带非空白 `userMessage`，且不能同时提交任何 edited 字段；`discard` 也不能携带 edited 字段；
- 请求声明的 `engineVersion` 与 `ReviewArtifact.workflowRunId` 持久身份不一致时稳定拒绝，不能按当前开关或字段
  猜测后改走另一引擎。

Web 的本地 `ReviewArtifactData` 必须保留生成 DTO 中必填的 `engineVersion`，并在展示、终态清理和提交决定前
校验归属不变量：V1 只能是 `engineVersion=1 + taskId != null + workflowRunId == null`，V2 只能是
`engineVersion=2 + taskId == null + workflowRunId != null`。决定请求必须原样发送 Artifact 自身的
`engineVersion`，不得再根据哪一个 ID 非空或当前前台 Run 猜测。

Java CLI 的三条 Artifact 决定命令保留公共 API 的 V1 历史兼容：省略 `engineVersion` 时只解释为 V1；
V2 调用必须显式携带整数 `engineVersion=2`。显式值只允许 `1|2`。`approve/revise` 先按
`artifactId + expectedRevision` 精确读取详情，并核对详情中的 `engineVersion` 后再 POST；`discard` 不做前置
GET，省略时稳定发送 1，显式时按调用方提供的引擎身份直接 POST。原因是 V1 discard
会物理删除 Artifact：若首次 POST 已提交但响应丢失，只有以相同 `clientRequestId`、`engineVersion` 和完整请求
直接重放，才能命中 Core 的持久幂等结果；先 GET 会稳定得到 404 并破坏恢复路径。

决定响应是以 `engineVersion` 为 discriminator 的明确 union：V1 concrete response 保留既有
`artifactId/taskId/commandId/decision/status/savedCount/deleted` wire 字段并增加 `engineVersion=1`；V2 直接返回
提交决定事务后的权威 `WritingRunV2Response`。V2 的 `taskId` 只可为空或作为等于 `runId` 的兼容别名，
`commandId/commandStatus` 固定为空；决定 Step 只能出现在 `currentStep`，不得伪造成旧 Command 或返回虚构 task。

## 调度、租约和执行协议

Core 调度器按 PostgreSQL Step 选择可运行任务并原子增加 `fencingToken`、设置 lease 和 `activeJobId`，再通过
签名内部接口向 Agent 提交完整、版本化 `ExecutionStepRequest`。Agent 内存队列只是运输缓存；进程重启后由
Core 的租约恢复重新投递。

Agent 在任何供应商调用前必须把 accepted/started/供应商尝试边界写入启用 AOF、挂载持久卷的 execution journal；
模型返回后必须先把完整 Result/Failure 与 usage 持久化，再回调 Core。`accepted`、`started`、未送达终态以及确定性
回调拒绝记录一律不设 TTL；只有 Core 回执为 `accepted|duplicate|superseded` 后才可标 delivered 并开始终态保留期。
`stale` 表示 Core 已经换到更新但尚未终态的 fence：Agent 必须保留完整终态并退避重投，等待新 fence 的执行请求
把该终态原子重绑后回放，绝不能把 `stale` 压缩成 tombstone。
delivered 必须在同一个 Redis Lua 中删除完整 `terminal_payload` 并重建为只含 request/result hash、fence、资源身份和
解析模型的紧凑幂等 tombstone；独立保留期默认且最少 24 小时。相同 `requestHash` 的新 fence 只能更新 tombstone
运输身份并幂等收敛，不能尝试解码已经删除的终态、重新回调或再次调用模型；不同 hash 仍必须冲突。
Redis 写入或持久化不可用时必须停止新模型调用并使 readiness 告警，不能退化成内存执行。journal 只保存尚未交付的
执行事实，不授权业务状态转换；PostgreSQL 回调事务提交后仍是唯一业务权威。

未送达终态不能只等待 Core 租约重派来触发回放：Core 可能已经提交终态，只是 HTTP 回执在返回途中丢失，此时该 Step
不会再次进入调度。Agent 必须运行独立的 terminal callback replayer，从 journal 的 pending 有序集合按到期时间小批领取，
对同一 `resultHash` 继续发送同一个幂等回调；`accepted|duplicate|superseded` 停止重试并进入保留期，`stale`
保留完整终态并退避等待新 fence，确定性 4xx 转入
rejected 隔离队列并使 readiness 失败，可重试错误使用带抖动的有界指数退避。领取、下次重试时间和 pending/rejected
迁移必须由 Redis 原子脚本维护；进程启动、回调响应丢失、Core 重启与 replayer 重启都不得重复模型调用或丢失终报。

execution journal 必须使用独立的内部 Redis 实例与独立持久卷，并采用 `appendonly yes + appendfsync always +
aof-load-truncated no + noeviction`。现有队列、SSE 唤醒、登录防重放和普通缓存 Redis 不得因为 V2 journal 被整体切换为
每次 fsync；这些可重建数据继续使用原有低延迟实例。Agent 分别配置普通 `REDIS_URL` 与
`EXECUTION_REDIS_URL`，健康检查分别报告；journal Redis 不暴露公网、不供 Core 或浏览器读取，备份、AOF 重写、磁盘
耗尽和损坏启动失败都必须演练。两个 URL 指向同一实例时生产配置门禁必须拒绝，测试环境可显式使用内存替身。
单机基线使用 32 MiB `maxmemory` 与 128 MiB 容器上限，为 live dataset 的 AOF rewrite CoW 另留一份完整副本及
64 MiB 运行余量；达到 90% 或发现 eviction 时停止新 provider 调用。容量公式、隔离压力数据与仍未解除的整机
2 核 2 GB 门禁记录在 `docs/audits/2026-09-01-execution-journal-capacity.md`。

execution journal 从任何备份恢复时必须先在恢复目标中持久写入带 snapshot SHA 和 epoch 的 quarantine marker。
在具名 Core/供应商对账完成、报告哈希经人工脚本核验并显式清除 marker 前，readiness 必须失败，且所有新 provider
调用必须 fail-closed；不能因为旧备份缺少 accepted/attempt/terminal key 就推断从未调用过非幂等供应商。恢复和解除
quarantine 都必须精确验证本地 `WAITAOF` ack 为 1，返回 0 也必须失败；marker 永不自动清除。
同一规则也适用于任何 Core PostgreSQL 时间点恢复，而且必须在数据库恢复前写入当前 execution Redis；delivered
tombstone 24 小时后可能过期，不能用 journal 缺 key 证明供应商从未调用。数据库备份必须携带该恢复边界元数据；
恢复后须联合 Core、callback/resultHash、账单与供应商请求 ID 具名对账，不能把 24 小时 tombstone 宣称为跨数据库灾备。

`ExecutionStepRequest.dispatchMode=initial|pending_recovery|running_recovery` 是不进入逻辑 request hash 的运输事实。
模型前的固定顺序是：journal accepted 持久化 → Agent 纯本地构造 model request，并完成输入、schema 与 Step budget
校验；此处失败直接以 `providerAttempts=0` 回报终态，不发送 `preparing`、不占额度 → Core 接受携带
`resolvedModel` 的 `preparing` progress，在同一事务完成部署授权、Run 预算与用户额度预留并把 Step
`pending -> running` → journal started 持久化 → 回报 `waiting_provider` → 取得 lane 容量并先持久化供应商尝试计数 →
调用供应商。Core 暂时不可达时不得开始付费调用。恢复时若 journal 缺失，
`initial/pending_recovery` 可重新受理，`running_recovery` 必须直接收敛 `MODEL_OUTCOME_UNKNOWN`；这样即使 AOF 灾难性
丢失，也不会把 Core 已见过 running 的 Step 再次调用供应商。

Agent 可以在 HTTP 202 响应被 Core 记录前调度本地 task，因此 Accepted 与 `preparing` 是允许重排的两条消息。
`ExecutionStepProgress` 每一帧都必须重携完整 `resolvedModel`；Core 的两条路径都只能按相同 deployment fingerprint 做
幂等冻结，任一漂移稳定拒绝。只有 `preparing` 事务是付费调用授权门，不能要求 Accepted 先到，也不能在仅收到 202
时长期占用用户额度。余额不足或预算拒绝必须先在 Core 收敛稳定 Step/Run 事实并返回 stale，Agent 收到后保证
`providerAttempts=0`。

V2 内部 HTTP 面固定为：Core 使用 `POST /internal/v1/executions` 提交、使用
`PUT /internal/v1/executions/{jobId}/cancel` 取消；Agent 使用
`PUT /internal/v1/workflow-runs/{runId}/steps/{stepId}/progress`、`.../result`、`.../failure` 分别回报进度、
成功和失败。所有路径参数都必须与正文和服务 JWT 资源声明一致。Core 对回调返回版本化
`ExecutionCallbackReceipt(status=accepted|duplicate|stale|superseded)`。四种状态均使用 HTTP 200，但语义不同：
`accepted|duplicate|superseded` 证明该旧终态无需再投递，`stale` 只证明当前 fence 已过期且 Core 的更新 fence 仍非终态；
Agent 收到 `stale` 必须保留完整终态、退出当前执行并退避重投，直到新 fence 请求触发原子重绑，或 Core 终态后返回
`superseded`；
鉴权/协议错误使用确定性 4xx。只有精确 HTTP 200 且 receipt 完整、身份匹配时才可确认送达；损坏/截断的 200、
其他 2xx、3xx、网络错误和 5xx 都保留 Agent journal 并退避重投，receipt 身份不匹配与确定性 4xx 才进入 rejected。
重投回调只重放 journal，绝不
再次调用模型。

逻辑车道：

- `control`：批准、丢弃、取消、状态读取，不占模型槽；
- `interactive`：问答、意图、轻量 Reviewer；
- `creative`：章节规划、正文和返工；
- `batch_media`：画像、RAG、视频和长耗时后台任务。

生产总模型并发仍为 3：creative 最多占 2 个，interactive 保留 1 个，空闲时可借用；Reviewer 扇出不得占满
全部槽。冻结快照上的只读计算不持有整本小说锁；只有正式 apply 使用短事务锁与 CAS。

容量与公平调度必须遵守以下可测试规则：

- Core 与 Agent 必须读取同一个显式 `AGENT_MAX_CONCURRENCY`（只允许 1～3，默认 3）；Compose 必须把同一变量同时
  注入两个服务。Core 以 PostgreSQL 中 `activeJobId IS NOT NULL AND leaseExpiresAt > now()` 的非终态模型 Step 作为
  `active lease`；领取事务先取得全局 advisory transaction lock，再计数和更新 Step。全局 active lease
  硬上限为该配置，多个 Core dispatcher 竞争时也不能超卖；配置为 1 时所有 lane 与 Reviewer 严格串行。到期 lease
  不继续占槽，但恢复领取仍生成新 fence/job。
- 默认容量 3 且有对应等待者时，`creative` 保留上限为 2、`batch_media` 保留上限为 1；没有竞争 lane 等待时两者可借用
  空闲槽。借槽不抢占已经开始的模型调用，但竞争 lane 到达后，下一个释放槽优先归还：interactive 优先从
  creative/batch 借槽中收回，creative 优先从 Reviewer 扇出中收回。`purpose=review` 无论是否空闲都最多 2 个，
  因此 Reviewer 扇出不能独占三个槽。所有借用仍受全局上限和同小说互斥约束。
- 未老化任务按 `interactive -> creative -> batch_media` 选择；等待满 5 秒后按 `submittedAt` 最老者优先，
  再按 lane、Run 和 ordinal 稳定排序。该 aging 只改变领取次序，不绕过 lane 上限，保证持续 Reviewer/交互流量
  不会永久饿死 creative，持续前台流量也不会永久饿死已经等待的 batch。
- Agent 只允许有限个“新建且尚无 journal 的执行”进入本地执行集合，默认与
  `AGENT_MAX_CONCURRENCY` 相同。容量已满时 `POST /internal/v1/executions` 返回带 `Retry-After` 的 503，且在返回前
  不创建 accepted journal；Core 验证专用控制帧后快速释放 lease，之后以同一逻辑请求和新 fence 重投。相同 Step 的已有 journal、
  refence、未送达 terminal replay 与 cancel 永远绕过新工作 admission，避免饱和把恢复通道堵死。
- 上述 journal 前饱和 503 必须使用严格控制帧
  `protocolVersion=2.0,errorCode=EXECUTION_ADMISSION_SATURATED,retryable=true,retryAfterSeconds`，且正文秒数与
  `Retry-After` 完全一致。Core 只有完整验证该控制帧后，才可按 matching run/step/job/fence/requestHash 原子清除 lease
  并把 `nextAttemptAt` 推迟；普通 503、正文/头不一致、超时或应答丢失仍属于提交结果未知并保留整段 lease。
- V1 与 V2 的所有供应商调用共用一个 lane-aware 模型门；总并发不超过 `AGENT_MAX_CONCURRENCY`。
  `AGENT_MAX_CONCURRENCY=1` 时严格全局串行；默认 3 时 creative/batch 可在没有竞争 lane 时借槽，竞争者
  到达后的下一次释放优先归还，Reviewer 始终至多占 2；其余等待者按 lane 轮转且同 lane FIFO。V1
  reviewer/quality 明确归 interactive，primary/reviser 与
  中短篇归 creative，画像和视频归 batch_media；V2 必须直接使用请求冻结的 `lane`，禁止从模型名或提示词猜测。
- Step 的 `maxWallClockSeconds` 从取得模型 lane 容量并成功持久化首次 provider attempt 边界后开始计时；
  admission、初始本地排队、preparing 回调和等待模型槽的时间不消耗 provider wall-clock。首次尝试后发生的
  供应商退避和再次等待仍属于同一 Step 墙钟预算。journal 的 provider attempt 必须先于任何供应商副作用。
- readiness 必须显示 execution admission 的 active/capacity/saturated 和 callback backlog。短暂满载只表示
  `saturated=true`，服务仍 ready；journal 不可用、后台执行异常、确定性 callback rejected backlog 或超过门限的
  未送达 terminal backlog 才能使 readiness 失败。

执行器终态回调必须携带 `stepId + runId + jobId + fencingToken + requestHash + inputHash + resultHash`，进度回调
携带同一资源绑定与单调 `sequence`。旧 fencing token、普通结果遇到已取消 Run、已完成 Step
和输入哈希不符全部拒绝。业务副作用 exactly-once；模型计算诚实采用 at-least-once/可能不确定语义。

V2 的 input、request、manifest、output schema 与 result 哈希统一使用
`inkforge-canonical-json/1`：对象键按 Unicode 码点排序、UTF-8、无多余空白、`null` 保留，有限数字转为无指数的
最短十进制定点形式，`-0` 归一为 `0`，拒绝 NaN、Infinity、非字符串对象键和未配对代理字符。Pydantic
可空模型字段在进入哈希材料前统一省略；任意 JSON 值中的显式 `null` 不得省略。成功与失败的 `resultHash`
都绑定完整 usage。Python 与 Java 必须共享字节级 golden vector，协议版本不允许隐式改变算法。
进入 Evidence manifest 哈希的 aware datetime 必须先截到微秒，并使用跨语言唯一文本形式：秒位始终存在，
零小数不输出 fraction，非零 fraction 固定六位，原 UTC offset 保留且 UTC 写作 `Z`。Core 构造 manifest 与持久化
Evidence item 必须复用同一个规范化时间值；禁止直接使用 Java `OffsetDateTime.toString()` 等会省略零秒位的语言默认
格式。Java `ObjectMapper` 生成的完整 `ExecutionStepRequest` 必须由 Python 严格模型通过跨语言 golden 验证。

Operation Catalog 的 `runBudgetProfile` 是 Run 累计上限；Core 必须为每个 Step 分配独立、
`maxModelCalls=1` 的 `StepBudget`，并同时执行 Run 累计与 Step 单次门禁，禁止把 Run 总量复制给每个 Step。

## 重试与错误语义

- 明确 429、连接失败和 5xx：在 Step 预算内最多重试 2 次，指数退避加抖动；
- 成功与否不确定且供应商没有幂等能力：`MODEL_OUTCOME_UNKNOWN`，禁止盲重发；
- JSON/协议错误：只允许一次不调用模型的确定性闭合恢复；仍不合法即以
  `MODEL_OUTPUT_PROTOCOL_INVALID` 失败，不在当前 canary 自动追加模型调用；
- `length`、`content_filter`、未知完成原因和矛盾工具状态均失败，不接受部分结果；
- 不在同一 Run 中静默切换 Provider、模型、思考策略、Schema 或 Evidence 版本；
- 熔断后新 Step 可见排队或明确失败，已有候选保留；
- 最大未 checkpoint 的已完成计费工作为一次模型调用；
- 每次授权、模型响应、usage 和结果哈希按 Step 对账，不持久化 reasoning 原文。

## 预算策略

禁止继续给所有阶段统一 `384000`。首版硬上限：

| 操作 | 标准调用 | 自动返工后总上限 |
| --- | ---: | ---: |
| 问答 | 1 | 1 |
| 意图解析 | 1 | 1 |
| 一致性终检 | 1，协议纠正另计 1 | 2 |
| 章节规划 | 生成 1 + Reviewer 1 | 4 |
| 正文草案 | 生成 1 + 两个并行 Reviewer | 6 |
| 设定/大纲/伏笔 | 生成 1 + Reviewer 1 | 4 |
| 中短篇单段 | 生成 1 | 按显式 segment 数量 |

每个预算同时限制模型调用数、输入 cache miss、reasoning、可见输出、金额、墙钟时间、协议纠正和供应商重试。
正文优先采用“短规划 + 受限推理正文”Profile，Reviewer 关闭 thinking。

## Event 与取消

V2 只发布可验证的语义事件：

```text
run_accepted
intent_resolved
clarification_required
evidence_ready
step_queued
step_started
step_progress
candidate_ready
review_started
review_completed
awaiting_user
applying
completed
failed
cancelled
```

`step_progress` 至少每 10 秒更新一次真实阶段、已用时和是否仍在等待供应商，不发送 chain-of-thought。
流式 token 只作为可丢失预览，不成为业务 Event 或最终正文来源。

Web 停止按钮必须调用 Core cancel API。Core 写 `cancelRequestedAt`、跳过未开始 Step，并通知运行中执行器；
执行器尽力取消供应商请求且继续上报已发生 usage。迟到结果因 fencing/cancel 状态被拒绝，不能反转终态。
具体取消、租约、usage 和竞争规则以“生命周期协议附录”为准。

## 公共接口与兼容

- 当前 `/api/v1/writing/runs`、状态、SSE、Artifact 和决定入口在迁移期保持路径可用；
- 公共响应使用带 `engineVersion` 判别字段的 V1/V2 union；V2 暴露规范 `runId`，旧 `taskId` 只可作为
  `WorkflowRun.id` 的兼容别名，`commandId/commandStatus` 必须为空，当前执行单元由独立 `currentStep` 表达，
  不得把 Step 伪装成旧 Command；
- 查询先按 V2 Run 查找，未命中才读取 V1 `WritingTask`；同一 ID 绝不双写；
- Web 和 Java CLI 改为提交显式 workflow/operation；自然语言入口允许 operation 为空并进入 resolver；
- 旧 `/resume` 只作 V1 边界兼容：V1 `WritingTask` 只继续 V1；任何 V2 Run 调用该路径都稳定返回
  `WORKFLOW_RESUME_UNSUPPORTED`，不得借此复活或复制旧状态机。V2 的后续普通指令统一通过 `POST /writing/runs`
  创建新 Run，活动或 `waiting_user` Run 必须使用对应决定入口；新 Web 不调用 `/resume`；
- `/resume` 与 `/cancel` 的引擎判别只能使用轻量持久身份探针：按请求 ID 查询是否存在
  `engineVersion=2` 的 `WorkflowRun` 并校验 `userId`，不得先构造完整公共 snapshot。V2 记录命中但 owner 不符时
  固定拒绝且禁止回退到同 ID 的 V1；没有 V2 记录时必须立即原样委托 V1 command repository，使 V1 缺失、越权、
  历史损坏但可恢复、Artifact 和命令状态错误继续由 V1 权威规则决定。V2 `/resume` 固定返回
  `WORKFLOW_RESUME_UNSUPPORTED`；V2 `/cancel` 先执行耐久取消事务，只有成功后才读取公共 snapshot 作为响应；
- V1 历史任务继续由旧 Agent 收敛，不能转换、回填或由 V2 接管；
- 新建 Run 可按账号/小说 allowlist 路由 V2，开关关闭只阻止新建，不中断既有 V2 Run。

## 生命周期协议附录

本节是 Run、Step、Artifact、Event、公共 API 与部署切换的可执行契约。实现、测试和运维脚本不得另行推断
状态含义；同一事务中涉及多行时统一先锁 Run，再按 `Step.ordinal`、Artifact ID 和正式目标 ID 的稳定顺序加锁。

### 租约、重派与重试矩阵

Core 派发必须以 `status + revision/fencingToken + leaseExpiresAt + cancelRequestedAt` 做 CAS。供应商“支持幂等”
不仅要求 Profile 声明能力，还要求本次请求实际携带并持久化供应商幂等键；二者任一缺失都按不支持幂等处理。

| 当前事实 | Core 动作 | Step 结果 | fence / job / 计数 | 必须写入的 Event |
| --- | --- | --- | --- | --- |
| `pending` 且无有效租约 | 原子领取并派发 | 保持 `pending`，执行器真正开始后转 `running` | 新 `activeJobId`，`fencingToken + 1`，`attemptCount + 1` | `step_queued`；开始回调后 `step_started` |
| `pending` 且租约有效 | 不重复派发 | 不变 | 不变 | 无 |
| `running` 且租约有效 | 等待 progress/result | 不变 | matching-fence progress 续租 | 接受的 progress 写 `step_progress` |
| `running` 租约过期 | 在 `running` 原状态下 CAS 换新租约并重投 journal 恢复请求；这一步本身不授权再次调用供应商 | Agent 有终报则只回放；journal 仍为 accepted 则开始；journal 为 started 时按下一行分类 | 新 `activeJobId`，`fencingToken + 1`，`attemptCount + 1`；旧 fence 永久失效 | `step_queued`，payload 标记 `reason=lease_recovery` |
| journal 为 `started` 且供应商明确支持幂等、实际幂等键也已持久化 | 使用同一供应商幂等键恢复 | 保持 `running` | 不新建逻辑 Step；真实调用继续累计 providerAttempts | progress；最终边界 Event |
| journal 为 `started`，但供应商能力或实际幂等键任一缺失 | Agent 禁止再次调用供应商并回报未知结果 | `failed`，`errorCode=MODEL_OUTCOME_UNKNOWN`；Run 按 Operation 失败策略收敛，Reviewer 已有候选时仍可进入 `waiting_user` | 清 lease/job，保留已知 usage | 生成阶段写 `failed`；Reviewer 写 `review_completed/awaiting_user` 并标明不可用 |
| Agent 明确返回可重试 429、连接前失败或可证明未被供应商接受的 5xx | 在同一 Step/预算内指数退避；Agent 内部重试不换 fence | 最终成功、或预算耗尽后 `failed` | 每次真实调用增加 `providerAttempts`，不增加 `attemptCount` | progress；最终边界 Event |
| 响应丢失、读超时或供应商完成与否不确定 | 只有供应商幂等键可安全复用时才允许按上表重派 | 否则 `MODEL_OUTCOME_UNKNOWN` | 禁止靠错误类型名称猜测安全性 | `failed` |

协议修复只允许一次不调用模型的确定性闭合尝试。首个
`long_serial.rewrite_chapter_selection` canary 在仍不合法时直接失败，`protocol_correction` Registry 条目保持
`supported=false`，不得在原 Step 内隐藏第二次主模型调用。未来若要启用模型纠正，必须先以独立 Step、独立
Evidence/预算/事件和端到端测试另行开放；不能把预留的 Registry 条目当成已经实现。

### 取消矩阵

浏览器公共 cancel 以 `runId + clientRequestId` 幂等；Core 生成的执行器 cancel 必须精确绑定
`runId + stepId + activeJobId + fencingToken + cancelRequestId`。Core 首次接受取消时锁定 Run，写
`cancelRequestedAt` 并禁止创建或重派任何 Step；相同请求重放原响应。若没有运行中 Step，则在该事务内写
`completedAt`、Run `cancelled` 和唯一 `cancelled` Event；若仍有运行中 Step，Run 保持原非终态，公开 snapshot
以 `cancelRequestedAt != null` 明确显示“正在停止”，待所有运行中 Step 收敛后才一次性进入 `cancelled`。

| Run / Step 状态 | Core 与执行器动作 | Step 最终状态 | Artifact 与业务结果 |
| --- | --- | --- | --- |
| Run `pending`，Step 尚未开始 | 不投递或撤销队列项 | 所有未开始 Step `skipped`，`errorCode=RUN_CANCELLED` | 不创建候选；Run 在同一事务 `cancelled` |
| Run `running`，Step `pending` | 撤销精确 job；旧 ACK/result 受 fence 拒绝 | `skipped` | 不接受模型结果；没有其他 running Step 时 Run `cancelled` |
| Run `running`，Step `running` | 发送精确 cancel；只接受 matching-fence cancel ACK 和累计 usage | 收到 ACK/usage 后 `skipped`；matching-fence 正常结果只提取计费事实并同样收敛为 `skipped`，不能物化候选 | 已在取消前提交的耐久候选保留，否则丢弃迟到输出；最后一个活动 Step 收敛时 Run `cancelled` |
| 运行中 Step 未返回 cancel ACK 且租约过期 | 不重派；按最后已知 usage 收敛 | `skipped`，usage 标记 `partial/unknown` | 最后一个活动 Step 收敛时 Run `cancelled` |
| Run `waiting_user` | 不投递 Agent，直接完成取消事务 | 未开始决定 Step `skipped` | Run `cancelled`；V2 Artifact/revision/Evaluation 全部保留，只读且不可再决定 |
| Run 已为任一终态 | 返回 `alreadyTerminal=true`，不改终态 | 不变 | 不新增 Event 或副作用 |

matching-fence 的迟到正常 Result 可以贡献经校验的 usage，但其业务结果、Artifact、Evaluation 和后续 Step 一律
不得提交。`cancelRequestedAt` 存在后，除最终 `cancelled` 外不再创建用户语义 Event；取消尾项只更新 Step/usage，
保证 terminal snapshot 之后没有迟到 progress。取消、完成和用户决定并发时以 Run 行锁与 revision CAS 的第一笔
提交为准；后到请求返回稳定冲突或同幂等请求的已提交响应，禁止翻转终态。

### 用户决定矩阵

所有 V2 决定先验证 `Run.status=waiting_user`、Artifact 属于该 Run、`expectedArtifactRevision`、来源绑定和
用户级 `clientRequestId`。V2 Artifact 是否可操作由“Run 仍为 `waiting_user` 且 Artifact revision 匹配”共同
决定，不能只看 Artifact 自身 status。

| 决定 | 同一事务内的权威变化 | Agent 投递 | 终态 / 后续 |
| --- | --- | --- | --- |
| `approve` | 锁 Run、Artifact、来源和正式 target；重验 CAS；写决定 Step、`applying` Event、正式数据、Artifact `applied`、Run/Event | 无 | Run `completed` |
| `edited approve` | 先创建具名用户编辑 revision并执行确定性校验，再按 `approve` 应用该精确 revision | 无 | Run `completed`；旧 revision 只读 |
| `discard` | 写完成的 `user_confirmation` Step 和决定 Event；保留 V2 Artifact、全部 revision、Evaluation，不执行正式写入 | 无 | Run `completed`，Artifact 只读且 `actionable=false` |
| `revise` | 写完成的决定 Step；Artifact 转为非操作中的草案态；Run 回到 `running`，创建绑定旧 revision 的新 generation Step | 只投递新 generation Step | 成功产生新 revision 后再次 `waiting_user`；失败保留全部历史 revision |
| 来源 CAS 冲突 | 不提交决定 Step、不写正式内容 | 无 | 返回稳定冲突；显式 rebase 创建新 Evidence bundle 后再决定 |
| Run 已 `cancelled/completed/failed` | 不改变任何事实 | 无 | 返回 `RUN_TERMINAL`；同一幂等请求只重放原结果 |

V1 决定继续走现有 `WritingTask/WritingRunCommand` 语义，包括现有 discard 删除行为；V1 与 V2 不双写 Artifact
决定、Event 或结果。

首个 `rewrite_chapter_selection` 纵切还必须遵守以下可执行细则：

- 每个决定先取得用户级 `clientRequestId` advisory transaction lock，再统一按 Run → Artifact → 精确
  `ReviewArtifactRevision` → Chapter 的顺序加锁；同一 Run 的不同决定因此也由 Run 行锁串行化；
- 锁住 Chapter 后重新校验 `updatedAt`、完整正文 SHA-256、Unicode code point 范围和 selectedText SHA-256。
  任一漂移以 `ARTIFACT_SOURCE_VERSION_CONFLICT` 整体回滚，不创建用户编辑 revision、决定 Step 或 Event；
- 决定 Step 使用 `stepType=user_confirmation`、`purpose=user_decision`、`lane=control`，保存规范请求哈希和可重放
  的决定响应；同一用户的 `clientRequestId` 与 V1 Command、V2 Run 创建及其他 V2 决定共用命名空间；
- `approve` 在应用精确 replacement 前写 `applying` Event，使用 Unicode code point 只替换冻结范围，随后把
  Artifact 标记 `applied`、写 `completed` Event 并完成 Run；章节正文、重开状态与一致性终检失效必须同事务；
- `discard` 不修改或删除 Artifact、Revision、Evaluation，只写完成的决定 Step 与 `completed` Event；Artifact
  因 Run 已终态而不可再操作；
- `revise` 把 Artifact head 退回 `draft`，写完成的决定 Step，并创建绑定同一 Evidence bundle、旧
  Artifact revision 和现有生成 Schema/Profile/Step budget 的新 `generation` Step。模型成功后只能在同一
  Artifact 追加 revision，不能创建第二个活动 Artifact 或覆盖旧 revision；
- 首切仅接受 `workflow=long_serial + operation=rewrite_chapter_selection + kind=chapter_draft`，其他 V2 kind 或
  apply handler 在对应纵切完成前稳定拒绝。

### SSE snapshot、cursor 与 progress 升格

每次 SSE 连接先在同一个 PostgreSQL 只读事务中读取完整 Run snapshot 和当时的
`baseSequence=lastEventSequence`，先发送一个版本化 `run_snapshot` 控制帧，再只查询和发送
`sequence > baseSequence` 的 `WorkflowEvent`。因此 snapshot 与后续增量之间不存在空窗；Redis 通知丢失时
仍由 PostgreSQL 轮询补齐。

SSE `id` 是十进制 Run sequence，不使用数据库行 ID、Redis cursor 或 Step progress sequence。snapshot 帧携带
`baseSequence`；当其大于 0 时 `id=baseSequence`，为 0 时不写 `id`。客户端收到 snapshot 后必须把本地
`lastSequence` 重置为 `baseSequence`，之后只接受严格递增的事件。

| 连接输入 | 服务端行为 |
| --- | --- |
| 无 `Last-Event-ID` 的初次连接 | 发送当前 snapshot/baseSequence，再发送提交于 snapshot 事务之后的 `> baseSequence` 事件 |
| cursor 等于或小于当前 baseSequence | cursor 只用于诊断；当前 snapshot 覆盖旧状态，不重演 `cursor..baseSequence` 的 UI 副作用，随后从 `> baseSequence` 观察 |
| cursor 非十进制、负数或大于当前 baseSequence | 返回 `409 WORKFLOW_CURSOR_INVALID`；客户端清 cursor 后重新以 snapshot 恢复；cursor 只在当前 run path 的命名空间内使用 |
| terminal snapshot | 发送 terminal snapshot；查询并发送并发提交的 `> baseSequence` 事件后关闭，连接关闭本身不代表成功 |
| Redis 清空、Core 重启或通知延迟 | 保持同一 PostgreSQL 查询算法，不改变 cursor 和业务结果 |

`run_snapshot` 是非持久控制帧，固定包含 `protocolVersion, engineVersion, runId, baseSequence, snapshot`；耐久事件
envelope 固定包含 `protocolVersion, engineVersion, runId, sequence, eventType, occurredAt, payload`。两者都使用生成
Schema，禁止 Java/TypeScript 手写不同形状。首版持久 Event payload 的最小字段如下：

| eventType | 必填 payload |
| --- | --- |
| `run_accepted` | `workflow, operation?, targetType?, targetId?, runRevision` |
| `intent_resolved` | `workflow, operation, targetType, targetId, confidence` |
| `clarification_required` | `clarificationCode, prompt, decisionStepId` |
| `evidence_ready` | `bundleId, bundleVersion, manifestSha256, totalBytes` |
| `step_queued` | `stepId, ordinal, purpose, lane, modelProfile, attemptCount, fencingToken, reason` |
| `step_started` | `stepId, ordinal, purpose, modelProfile, attemptCount, fencingToken` |
| `step_progress` | `stepId, fencingToken, progressSequence, resolvedModel, phase, elapsedSeconds, waitingOnProvider, usageStatus` |
| `step_finished` | `stepId, fencingToken, status, errorCode`（wire 必填、值可空） |
| `candidate_ready` | `stepId, artifactId, artifactRevision` |
| `review_started` | `artifactId, artifactRevision, reviewerSteps` |
| `review_completed` | `artifactId, artifactRevision, evaluationIds, mergedVerdict, reviewAvailability` |
| `awaiting_user` | `artifactId, artifactRevision, allowedDecisions, reviewAvailability` |
| `applying` | `artifactId, artifactRevision, decisionStepId` |
| `completed` | `outcomeType, artifactId?, artifactRevision?, resultId?` |
| `failed` | `errorCode, failedStepId?, outcomeUnknown` |
| `cancelled` | `cancelRequestId, cancelledStepId?` |

Agent 的 `ExecutionStepProgress.sequence` 只在 `stepId + fencingToken` 内递增。Core 以
`progress:{stepId}:{fencingToken}:{sequence}` 去重；接受 progress 时在同一事务更新 heartbeat/累计 usage、锁 Run
分配下一条 Run sequence 并写 `step_progress`。重复 progress 不新增 Event，旧 fence、倒退 sequence 或倒退 usage
拒绝；并行 Step 通过 Run 行锁获得唯一总序。Run 已有 `cancelRequestedAt` 时，matching-fence progress 只更新取消
尾项 usage/heartbeat，不再升格为用户语义 Event。

`modelProfile` 是 Catalog 中的逻辑角色标识，不是供应商模型名或内部部署凭据；它也必须出现在
`WorkflowCurrentStepSnapshot`。前端按版本化映射显示“章节选区改写 / 一致性校验 / 编辑复审”等真实角色，不能把
所有 Step 再次显示成固定“作家”，也不能仅用 `purpose=review` 抹平两个 Reviewer 的差异。

Python 共享契约不得为公开状态另造一套可漂移的模型身份。模型 Step 的 `modelProfile` 直接使用执行协议中冻结的
`ModelProfileRef`，`resolvedModel` 直接使用 Agent 受理后冻结的 `ResolvedModelRef`；后者只包含无密钥的部署指纹、
供应商/模型、符号化 transport/endpoint/capability Profile、reasoning mode 与请求幂等能力，不包含 URL、凭据、
prompt 正文、模型输入输出或 reasoning 原文。通用 Step snapshot 中这两个字段必须在 wire 上显式出现；非模型
`control` Step 以 `null/null` 表达没有模型身份，其他 lane 必须有逻辑 Profile，进入 `running` 后必须同时有解析模型，
且 deployment Profile 与 reasoning mode 必须一致。`step_queued/step_started` 携带逻辑 Profile，`step_progress`
同时重携逻辑 Profile 与冻结解析模型，防止客户端把供应商模型名反推成角色或在并行事件之间串错身份。

并行 Reviewer 不能被单一 `currentStep` 覆盖。V2 Run snapshot 和公开状态增加完整 `activeSteps` 数组，按
`ordinal, stepId` 稳定排序；该稳定顺序的第一项就是兼容摘要，`currentStep` 必须与 `activeSteps[0]` 值相等，数组
为空时也必须为空。SSE reducer
按 `stepId + fencingToken` 分别维护每个活动 Step 的 phase、elapsed 与终态。`review_started` 不发送一组匿名 ID，
而是发送至少一个、最多 32 个按 `ordinal, stepId` 稳定排序的安全 `reviewerSteps`；每项固定
`purpose=review, status=pending, attemptCount=0, fencingToken=0`，并携带 lane 与逻辑 `modelProfile`，Step ID 和
ordinal 各自唯一。前端收到后立即建立真实 Reviewer 活动项，随后 `step_queued` 必须用同一 stepId 将对应项推进到
实际 attempt/fence，不能另造第二份 Reviewer 状态。
每个活动 Step 还必须携带 wire 上必填、值可空的 `latestProgress`：它只保存
`progressSequence, phase, elapsedSeconds, waitingOnProvider, usageStatus`，隐式归属于同一个 snapshot 中 Step 的当前
fence，不重复保存 Step ID、fence 或模型身份。`pending` Step 和所有 `control` Step 的 `latestProgress` 必须为
`null`；`running` 模型 Step 在刚收到 started、尚无 progress 时允许为 `null`。刷新时由 `activeSteps` 一次恢复全部
并行角色及各自最新进度，不能把已持久化进度重置为空；数组只能包含 `pending/running` Step，Step ID 与 ordinal
均不可重复。

逐 Step 终态统一由 `step_finished` 表达，`status` 只能是 `completed|failed|skipped`；`failed` 必须带结构化
`errorCode`，其余状态必须为空。前端只有在 `stepId + fencingToken` 同时匹配时才能移除对应活动 Step；旧 fence
终态只推进 Run cursor，不能清掉新尝试。`candidate_ready`、`review_completed` 等聚合事件只更新 Artifact 或评审
聚合，不得代替逐 Step 终态，也不得按 `purpose` 批量清空并行 Reviewer。所有活动 Step 收到各自终态后才清空
活动面板。`currentStep` 只能引用 `activeSteps` 中的一项，不能成为数组之外的第二份活动状态权威。

### 路由、幂等、公共 DTO 与前台 Run

创建请求先规范化并计算 request hash，再获得用户级 advisory lock；在决定 allowlist 前同时查询 V2
`WorkflowRun.idempotencyKey/requestHash` 与 V1 Command 幂等信封。相同 key/hash 重放原引擎响应，相同 key/不同
hash 返回 `IDEMPOTENCY_KEY_REUSED`；只有两边都未命中时才计算路由。路由结果随 Run/Task 一次持久化，后续读取、
取消、决定和 callback 只按持久化引擎身份分派，不重新读取开关。

可变更 Operation 还必须从 Catalog 目标生成稳定 mutation scope key，并在创建前同时检查 V1 活动 Task 与 V2
非终态 Run；同一 scope 跨引擎互斥。账号 allowlist 与小说 allowlist 在 canary 中取交集，必须同时匹配服务端认证
用户 ID 和具名隔离小说 ID；关闭开关只阻止新 V2 Run，不中断既有 V2。

V1/V2 新建入口在用户级幂等 advisory lock 后统一按 `Novel -> Chapter -> 可选 WritingSession` 加锁，再在同一
事务内检查并创建 Task 或 Run；嵌套 starter/repository 只能加入该事务并重复取得已经持有的同序锁，禁止先锁
Chapter 再回头锁 Novel。章节 mutation scope 中，当前已支持的 V1 `plan_chapter`、`write_chapter`、
`rewrite_scene`、`rewrite_chapter_selection` 与 `rewrite_outline_selection`，以及无法从历史或损坏的启动
payload 证明为只读的 V1 Task，都必须与同章节活动 V2 Run 互斥；V2 新建同样必须拒绝活动 V1 写任务。
`review_chapter` 只读运行在未绑定 WritingSession 时不占章节 mutation scope，可以与章节写任务并存。

只要请求绑定 WritingSession，单 foreground 规则优先于上述只读豁免：同一会话内任一 V1 非终态
`WritingTask` 或 V2 `pending/running/waiting_user` Run 都阻止新的 V1/V2 foreground Run，包括
`review_chapter`。跨引擎章节写冲突固定返回 `WRITING_TARGET_BUSY`；会话 foreground 冲突固定返回
`WORKFLOW_FOREGROUND_RUN_EXISTS`。已经持久化的同幂等请求仍须在路由、readiness 与这些新建锁之前按原引擎
重放，不能被后来出现的活动 Run 阻断。

公共 DTO 使用显式 union：

- 公共共有字段为 `engineVersion, runId, workflow, operation?, status, chapterId?, currentStep?, cancelRequestedAt?,
  lastEventSequence, revision, artifact?, error?`；`cancelRequestedAt != null` 且 Run 非终态时统一展示“正在停止”；
- V1 分支保留 `taskId, commandId, commandStatus`，V2 分支的 `commandId/commandStatus` 固定为空；
- V2 的 `chapterId`、`taskId` 兼容别名和 Artifact `taskId` 均可空；Artifact 通过 `workflowRunId` 归属 V2；
- V2 `currentStep` 使用 Step 状态 `pending|running|completed|failed|skipped`，不映射成
  `submitted|processing|succeeded`；
- 所有浏览器、CLI 和 SSE 响应必须带可判别的 `engineVersion`，不得靠字段猜测引擎。

首版同一 `WritingSession` 只允许一个非终态 foreground Run。`pending/running/waiting_user` 期间普通消息输入禁用，
只开放当前 Run 的结构化决定和显式停止；终态后下一条消息创建新 Run。关闭本地 SSE/fetch 只表示停止观察，绝不
调用服务端 cancel；停止按钮单独调用 cancel API，并继续通过 snapshot/GET 观察到 `cancelled`。自然语言澄清使用
当前 V2 Run 的具名 clarification 决定入口，不借用 `/resume`。

### System Purpose Registry 与 Run 预算

在 Operation Catalog 同一版本化目录中维护语言中立的 System Purpose Registry，至少包含
`resolve_intent`、`summarize_evidence`、`protocol_correction`。每项固定 `purpose, modelProfile, outputSchema,
evidencePolicy, lane, stepBudgetProfile` 和适用 workflow/父 Operation；`resolve_intent` 允许在 operation 尚未确定时
按 workflow 选择。Java、Python、TypeScript 使用同一 hash，禁止三端硬编码隐藏 Profile 或预算。

Run 创建时冻结 Catalog `runBudgetProfile`。创建或派发每个模型 Step 前，Core 锁 Run/revision，按已结算 usage
加所有非终态 Step 的预算保留量做原子检查；通过后才保留一次模型调用及 token/cost/reasoning/墙钟额度。Step
终态时用实际累计 usage 结算并释放未用保留量。并行 Reviewer 也必须经过同一 Run 锁，不能分别看到相同剩余额度。
已启用的证据摘要、自动返工和租约重派都消费原 Run 预算；重派不重复保留逻辑模型调用，但新的真实供应商尝试
继续累计 providerAttempts、token 和 cost。`protocol_correction` 仅是未来扩展预留，当前不创建也不计入 canary。

### Usage 完整性与累计规则

所有 progress、Result、Failure 和 cancel ACK 使用 `usageStatus=complete|partial|unknown`：

- `complete`：所有供应商计费字段齐全且精确；
- `partial`：只提交确定已知的字段，未知字段为 `null`，不得用 0 或估算值代替；
- `unknown`：没有可信供应商计费明细，保留本地可证明的 `providerAttempts`、墙钟和授权事实，其余可空；
- usage 始终是单 Step 跨 provider retry、Core 重派和当前 fence 回调的累计快照，不是 delta；
- Core 只接受同 Step 单调不减的已知值；重复 callback 幂等覆盖同一快照，不重复创建 TokenUsage；
- Step 预算是调用前授权上限，不是丢弃已发生费用事实的理由。供应商实际用量超过任一冻结维度时，Agent 必须返回
  `STEP_BUDGET_EXCEEDED` Failure 与真实累计 usage；Core 只在这个失败分支接受超预算事实，禁止物化结果或继续
  后续 Step。若按冻结价格重算的金额超过原预留，则 Reservation 进入 `reconciliation_required`，不自动超额扣款，
  也不能以 4xx/5xx 拒绝终报使其无限重试；普通 progress 或 Result 携带超预算 usage 仍是协议错误。正常终报使用
  `errorCategory=validation`；若预算越界与 matching cancel ACK 同时发生，则保留 `errorCategory=cancelled`、
  `cancelRequestId` 和 `errorCode=STEP_BUDGET_EXCEEDED`，既收敛取消身份也不丢弃实际用量。
- 最终 Result/Failure/cancel ACK 不得低于已接受 progress；后续供应商对账只能补全 `partial/unknown`，不能改变
  Step、Run、Artifact 或 Evaluation 终态；
- matching-fence cancel ACK 必须携带 usageStatus；取消不构成免记已发生费用，未知费用也不得伪造为零。
- `providerAttempts=0` 必须同时是 `usageStatus=unknown` 且所有供应商 token/cost 字段为 `null`；任何
  complete/partial 或已知供应商字段都与“零尝试”矛盾，Core 必须在业务状态与预留变化前拒绝，不能因没有
  Reservation 而直接放行终报。
- 用户积分结算以 `WorkflowBillingReservation` 为幂等边界；Step `usageJson` 是执行事实快照，不得代替预留、账本或
  `TokenUsage`。任何非假模型 Step 若没有预留，Core 必须拒绝进入 `waiting_provider`。

### V1 drain 与部署回滚矩阵

| 对象/阶段 | 切换期处理 | 删除 V1 代码前的门禁 |
| --- | --- | --- |
| V1 新建入口 | 全量切换后关闭 | 连续观察无新 V1 Task |
| V1 `pending/active/waiting_call` | 只由 V1 dispatcher/Agent/callback 收敛 | 活动 Task 与 Agent job 均为 0 |
| V1 `awaiting_user_review` | 保留旧 Artifact 决定与 `/resume` 能力，不转换 V2、不设静默 TTL | 用户显式决定后归零；未决定时不得删除 V1 runtime |
| V1 非终态 Task 上的 recoverable Command/GraphState | 继续使用 V1 `/resume`，或由用户显式放弃 | recoverable Task 为 0 |
| V1 terminal Task | 只读历史适配 | GET/list/Artifact 历史查询契约通过 |
| V1 Command | 继续 dispatch/reconcile 到终态 | pending/submitted/processing 为 0 |
| V1 Outbox/Redis 通知 | Outbox 继续投递；Redis 只作现有观察通道 | pending/delivering/blocked 为 0，或已由 PostgreSQL snapshot 明确替代 |
| V2 非终态 Run | 无论开关变化都由 V2-aware 镜像收敛 | V2 route-off/rollback 演练能继续处理既有 Run |

一旦存在任何 `engineVersion=2` 数据，禁止把 Core 或 Agent 回滚到不理解 V2 的旧镜像。生产应用回滚只能部署
“V2-aware、禁止新建、保留查询/取消/调度/callback/drain”的 route-off 镜像；DDL rollback 仍只允许完全没有
V2 数据时执行。V1 活动归零必须由 PostgreSQL Task/Command/Outbox/Artifact、Agent job/回调和公开查询共同证明，
不能只看 Redis、容器状态或单一 phase。

自动回滚不是“镜像存在”即可授权。allowlist 切换前必须冻结目标与回滚 Agent 的离线 manifest fingerprint 并与
发布预期精确一致；没有完整三服务回滚快照、旧 Agent 只能通过 import 检查或 fingerprint 不同，均不得开始 canary。
route-off 发布不会创建新 manifest 事实，但不同 fingerprint 的旧 Agent 只能在切换前先从当前运行 Core 的实际
进程环境证明 route 已经为 off，再从权威 PostgreSQL 证明全部 V2 Run 已终态、非终态数量精确为 0 后作为回滚点；
运行态检查失败、查询失败、结果非法或仍有任一非终态 V2 Run，都必须在版本切换
和 `compose up` 前停止。通过该门禁后还要证明两边各自的 manifest 与全部资产内部一致；恢复后继续
route-off/drain，不能自动恢复 allowlist。

## 数据库迁移

具名迁移：

- `scripts/migrations/20260831_durable_agent_execution.sql`
- `scripts/migrations/20260831_durable_agent_execution.rollback.sql`

迁移只允许：

1. 为 `WorkflowRun`、`WorkflowStep` 增加本规格列和索引；
2. 允许 `WorkflowRun.chapterId` 对 V2 非章节目标为空；
3. 新增 `WorkflowEvidenceBundle`、`WorkflowEvidenceItem`、`WorkflowEvent`、`WorkflowEvaluation`、
   `WorkflowBillingReservation`；
4. 增加本规格要求的 CHECK、唯一键和外键；
5. 不回填历史 Graph、正文或评审，不改正式作品内容。

迁移必须先在临时 PostgreSQL 14 + pgvector 从当前 contract 重建的结构上执行并重复执行，验证 forward、
应用兼容、回滚和重新 forward；随后备份 `novelwriterdev`、执行两次验证幂等并导出真实 contract。正式执行前
再次备份、校验数据库名和精确确认令牌。生产回滚只允许切换到本附录定义的 V2-aware route-off 应用镜像；只要
存在 V2 数据，旧 V1-only 镜像和 DDL rollback 均禁止使用。

数据库切换必须使用可分阶段部署的兼容镜像，禁止依赖“迁移后立刻重启”制造不可观测空窗：

- 镜像同时内置迁移前与本具名迁移后的两份精确 schema contract，只允许完整匹配其中一份；这不是忽略新增表、
  放宽字段比较或接受任意 additive drift；
- 迁移前以 `DURABLE_AGENT_EXECUTION_SCHEMA_READY=false` 运行，V2 新建路由必须为 off，且不得装配会读取 V2
  列/表的 dispatcher、cancel reconciler 或 mutation repository；V1 继续正常服务；
- 先部署并验收上述兼容镜像，再执行事务迁移。迁移提交后原实例仍须因精确命中“迁移后 contract”保持 ready，
  但仍不运行 V2 worker；
- 随后以同一已验证镜像和 `DURABLE_AGENT_EXECUTION_SCHEMA_READY=true` 重启，先保持 route-off 验证查询、取消、
  dispatcher/callback 与 schema readiness，再单独开启账号和小说 allowlist；
- 配置必须拒绝 `schema ready=false` 与 V2 allowlist/all 路由组合。存在任何 V2 Run 后，route-off 回滚也必须保持
  `schema ready=true`，继续装配 V2 收敛能力；
- Java Core 兼容镜像必须通过“迁移前结构启动 → 在线迁移 → 迁移后仍 ready → 重启启用 V2 → route-off
  收敛”的 PostgreSQL/Compose 演练。保留的 Python V1-only Core 只允许在没有任何 V2 数据且先完成空数据 DDL
  rollback 后使用；一旦存在 V2 Run，它退出生产回滚集合。旧 schema contract 不得在产生 V2 数据后作为应用回滚目标。

兼容镜像的两份资源必须明确命名且各自不可变：迁移前资源为
`db/pre-durable-agent-v2/schema-contract.json`，完整指纹
`4f8cbf58820c7e601026012249f1896e4f8ad0231cfa6b9bd2fdad1c83c3d195`；迁移后资源为
`db/post-durable-agent-v2/schema-contract.json`，完整指纹
`15d50f0b8572d6b7fffbeecc2b9f762ff16500efa94cd93729e4a84c393fa798`。后者只从本机隔离的
PostgreSQL 14.19 + pgvector 0.8.0 以当前 86 表契约重建、重复执行最终具名迁移后只读导出，共 91 表、22 个枚举；
该导出不表示开发库或正式库已经执行迁移，也不得提前覆盖它们各自的真实 canonical contract。

### 可执行迁移、备份与恢复门禁

具名操作入口固定为 `scripts/durable-agent-execution-migration.sh`，动作包括
`status|active-v2-count|backup|forward|rollback|export-contract|verify-contract`，完整步骤见
`docs/DURABLE_AGENT_V2_ROLLOUT.md`。入口必须把目标数据库显式限定为 `novelwriterdev` 或 `novelwriter`，并把
实时状态判定为 `unmigrated`、`migrated-empty-v2`、`migrated-with-v2` 或 `partial`；`partial` 对所有写动作
fail closed。结构对象状态只能决定迁移代次，forward/rollback 前还必须由已经运行的双 contract Java 镜像执行
精确只读 schema guard，不能用对象计数替代 contract。

数据库密码只能从唯一 `.env` 中安全解析到临时 0600 `PGPASSFILE`；传给 `psql/pg_dump` 的 URL 必须删除密码，
密码不得进入 argv、stdout、stderr、shell trace 或备份元数据。forward/rollback 与两份 contract 文件 SHA 固定在
helper 中，任何字节漂移都必须在连接数据库前拒绝。正式 forward 与空数据 rollback 还必须分别读取当前用户拥有的
0600 确认文件，并精确匹配 SQL 已冻结的生产令牌；令牌正文不能作为命令参数。

真实开发库和正式库完成 forward 后必须使用同一个具名 helper 导出结构证据，禁止调用会把含密码
`DATABASE_URL` 放入 argv 的通用开发脚本。`export-contract` 只接受迁移后的两种完整状态，复用上述安全 URL
解析与 0600 `PGPASSFILE`，把无密码的本机 URL 交给 `psql/pg_dump`，并在只读事务、固定 statement/lock timeout
下同时取得数据库身份、schema-only dump 和正在运行的 Java 精确 schema guard 指纹。导出目录必须由操作者以
`DURABLE_AGENT_CONTRACT_EVIDENCE_DIR` 显式指定为尚不存在的绝对路径；helper 只能在同父目录临时目录中完整生成
`schema-contract.json`、`schema-only.sql`、`contract-verification.meta` 与 `SHA256SUMS`，全部校验后原子改名，
不得覆盖仓库 canonical contract、既有证据目录或执行任何 DDL。

证据中的结构正文使用已通过 Java guard 与实时数据库精确比较的冻结 post contract 按当前运行 Core schema profile
生成的精确投影，并只替换从当前连接只读取得的 `source` 元数据；其结构 fingerprint 必须与该投影的 fingerprint
精确一致。`verify-contract` 必须
校验目录无符号链接、文件白名单、SHA、自洽 fingerprint、目标数据库、迁移状态和冻结 post contract 文件 SHA，
随后重新执行实时 Java guard 与 schema-only dump 比较；任何漂移、凭据泄漏风险、非迁移后状态或原子目录残留都
必须失败。该证据证明导出时和复验时的实时结构精确匹配冻结 contract，不授权把证据文件反向覆盖仓库或数据库。

迁移备份必须同时包含可读的 PostgreSQL custom dump、当前独立 execution Redis 的一致 RDB、各自 SHA-256、
迁移 SQL/contract 绑定和 `postgresRestoreRequiresExecutionQuarantine=true` 恢复边界。缺少 journal 快照、AOF
异常、RDB 不可读或元数据不完整时不得 forward。forward 只能引用这份已验证备份；重复 forward 继续使用同一备份
证明幂等。rollback 只允许 `migrated-empty-v2`，SQL 与 helper 都要检查 V2 Run、Evidence、Event、Evaluation、
BillingReservation、Artifact 绑定和新增列无数据；一旦出现任一 V2 事实，DDL rollback 永久关闭。

本仓库不提供自动 PostgreSQL 覆盖恢复。任何另行获准的 PostgreSQL restore 前，必须先运行
`scripts/prepare-postgres-restore-quarantine.sh`。操作顺序固定为：V2 route-off、停止新的 execution dispatch、通过
`docker compose stop` 等待具名 Core 与 Agent 容器完全退出，再把 database dump SHA 与具名 epoch 写入当前
execution Redis 的 restore quarantine 并精确取得本地 `WAITAOF` ack 1；然后才允许进入另行授权的 PostgreSQL
restore，ack 0 也必须失败。脚本必须从当前 execution Redis 容器的 Compose project、config files 与 working dir
标签确定权威编排身份，再按同一 project + `core-api|agent-service|execution-redis` 枚举全部容器；每个 service 必须
恰有一个实例、等于显式传入 ID、三者 config 身份一致，且 Core/Agent 精确为
`exited + Running=false + Paused=false + Restarting=false`。传入旧 stopped 容器而同 project 仍有现行或残留实例、
跨 project/config、运行、暂停、重启、缺失或多实例都必须在写 marker 前失败。相同全量检查还必须在本地
`WAITAOF=1` 后复验，不能只复查调用者提供的两个 ID。进程 quiesce 使已进入 Core 的 callback 事务先完成或随连接
断开回滚，也使 Agent 不可能继续发起新的
terminal HTTP；仅 route-off、dispatch flag 或 HTTP 前再次 `GET` marker 都不能单独构成线性化写屏障。

quarantine marker 是服务恢复后的第二层 fail-closed 防线：后台 replayer 与执行完成后的立即终态投递都不得发起
Core HTTP；新形成的 Result/Failure 只耐久保留为 callback pending，已经 delivered 的小型 tombstone 仍可幂等读取
但绝不重新投递。marker 在 claim 前由 Redis Lua 原子校验，已取得 claim 的发送路径在 HTTP 前二次校验只属于纵深
防御，不能替代进程 quiesce。隔离本身是预期维护态，不得使 replayer supervisor 崩溃或把服务永久毒化为后台错误。
数据库恢复期间 Core 与 Agent 必须保持停止；恢复完成后先保持 route-off 与 quarantine 启动对账所需服务，且不得
接回公网流量。随后须联合 Core、callback/resultHash、BillingReservation、TokenUsage/CreditLedger 和供应商请求 ID
具名对账，报告 SHA 人工确认前不得解除 quarantine；精确解除后继续保持 route-off，pending 终态由同一 replayer
逐项幂等回放一次，全部未知与拒绝项收敛后才能恢复 dispatch 或进入 allowlist。
部署脚本在迁移后结构上必须拒绝 Python Core、V1-only Agent 或不能收敛 V2 Run/Step 的回滚镜像，同时保留
execution Redis 卷；route-off 不得被解释为可关闭 `schemaReady`。

## 新旧切换与删除

1. 新引擎以独立 `engineVersion=2`、内部接口和 Agent handler 实现；V2 禁止导入 LangGraph 写作图、
   `AgentRuntime` 工具循环或 Artifact 控制工具。
2. 首个端到端纵切使用显式 `rewrite_chapter_selection`，覆盖 Run、Evidence、生成、Reviewer、Artifact、
   SSE、discard/approve 和取消；随后迁移所有长篇 Operation。
3. 迁移中短篇、质量、画像、RAG 和开发视频模型工作流；各产品链只共享执行底座，不共享业务状态机。
4. 新请求在用户级幂等锁内按 allowlist 只走一个引擎，不做影子模型调用或双写；同 mutation scope 跨引擎互斥，
   旧任务继续 V1 到终态。
5. 指定账号生产 canary 成功并观察后，全量新请求切 V2。
6. 没有 V1 活动任务且历史查询兼容后，删除跨服务 LangGraph 写作编排、旧 callback、模型业务工具和 V1 新建入口；历史表暂时只读保留。
7. 另立具名清理迁移后才能删除 `WritingTask/WritingRunCommand/WritingEventOutbox` 表。

## 验证策略

### 契约与单元

- Operation Catalog 在 Python、Java、TypeScript 三端同 hash；
- Run/Step 状态机、租约、fencing、预算、幂等和 Event 序号做单元与性质测试；
- Evidence 完整性、Unicode 码点、哈希、显式分块和无静默截断测试；
- 每个 Operation 的输入/输出 Schema、确定性门禁和 apply handler 测试；
- V2 包依赖测试禁止导入 LangGraph、旧 GraphState、控制工具和 V1 callback。

### PostgreSQL 与跨服务

- PostgreSQL Testcontainers 验证迁移、约束、锁顺序、并发和事务回滚；禁止 H2；
- Java Core + Python Executor + Redis + Nginx + fake provider 完整 Compose E2E；
- 在每个昂贵 Step 后注入 Core/Agent/Redis 重启，证明不重复模型结果、Artifact、计费或正式 apply；
- 覆盖响应丢失、重复 callback、旧 fencing、租约过期、cancel/complete 竞争和 SSE 游标重连；
- 用安全夹具覆盖 DeepSeek 合法与畸形 JSON、429、5xx、超时、断流和 usage 不完整；
- 真实供应商低额度预发布验证不能由 fake provider 代替；
- 在 2 核 2 GB、三个模型槽下验证车道公平、内存、队列和 SLO。

### Web

- 创建请求只发送一次，刷新后由 GET 恢复；
- SSE cursor 不重复终态副作用；
- 真实阶段最长 10 秒无更新；
- 停止按钮调用服务端 cancel；
- Artifact 完整 Diff、revise、discard、edited approve 与 CAS 全链路；
- Agent 消息继续按普通段落文本展示，不解析 Markdown。

## SLO 与验收指标

- 受理响应 p95 ≤ 1 秒；首个真实状态 p95 ≤ 2 秒；运行中无状态更新 ≤ 10 秒；
- 控制操作 p95 ≤ 2 秒；常态队列等待 p95 ≤ 5 秒；
- 章节规划 p50/p95 ≤ 90/180 秒；4,000 字正文 p50/p95 ≤ 180/300 秒；
- Reviewer p95 ≤ 30 秒；用户返工 p95 ≤ 240 秒；
- 成功 Run ≥ 99%，协议纠正率目标 < 2%；
- 重复 Artifact、正式应用、TokenUsage 和终态反转必须为 0；
- 最终 prompt 不超过首个 canonical context 的 2 倍；
- 4,000 字正文总 reasoning 目标 ≤ 16k，reasoning/visible 目标 ≤ 5:1；
- 日志只记录 hash、字节数、token、阶段、错误码和耗时，不记录凭据、正文、工具参数或 reasoning 原文。

## 生产发布门禁

1. 全量 Java、Python、Web、契约、API、架构、Compose、故障注入和负载测试绿色；
2. 隔离库与 `novelwriterdev` 迁移、contract、回滚能力和零残留验收通过；
3. 生成 `Git SHA -> 三服务镜像 digest -> catalog/profile/schema 版本 -> 回滚 digest` 发布清单；
4. 生产环境增加人工批准规则，并提供独立受保护的镜像回滚 workflow；
5. 生产备份可读，活动 V1/V2 任务满足安全切换或恢复条件；
6. 真实供应商低额度预发布同形任务成功；
7. 新引擎默认关闭，只按服务端解析的用户 ID/测试小说 ID allowlist 开启；
8. 部署后自动检查公网 TLS、重定向、内部路径 404、目标 digest、容器重启数、schema 和跨服务 POST；
9. 用指定账号只在新建、具名隔离测试小说中通过公共 HTTPS/受支持 CLI 验收，不访问内部接口或数据库；
10. 凭据只在 TTY/安全凭据存储中输入，不进入命令参数、环境变量、源码、日志或文档；
11. canary 依次验证只读身份、一次问答、一次完整候选 discard、一次批准、一次取消、SSE 重连、唯一用量；
12. 观察至少 30～60 分钟或足量样本。任何协议错误、重复计费/产物、不可解释状态、不可恢复 Step、终态缺失或 SLO 硬失败立即停止放量并回滚应用镜像。

## 完成标准

只有同时满足以下条件才能宣称本重构完成：

- 所有新模型任务均由 Core `WorkflowRun/WorkflowStep` 编排；
- 新写作请求不再创建 `WritingTask/WritingRunCommand` 或 `graphStateJson`；
- Python V2 执行路径不使用 LangGraph、业务提交工具或可变 workspace；
- 所有 Operation、审核、批准、返工、取消、计费和 SSE 通过端到端与故障恢复验收；
- 生产指定账号 canary 与全量切换观察通过；
- V1 不再接收新任务，旧活动任务归零，旧代码已删除或只保留明确只读历史适配；
- 生产权威日志和 PostgreSQL 证据满足 SLO、幂等、无重复副作用和无静默截断要求。
