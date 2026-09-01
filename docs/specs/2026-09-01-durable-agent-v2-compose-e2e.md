# Durable Agent V2 跨进程 Compose 验收

日期：2026-09-01

状态：实施中

关联规格：`docs/specs/2026-08-31-core-owned-durable-agent-execution.md`

## 背景

`long_serial.answer_question` 已具备共享 Catalog、Python 单 Step 执行器、Java Core Run/Step/Evidence/消息
物化和公共 CLI 契约，但进程内单元测试不能证明 Java Core、Python Agent、PostgreSQL、普通 Redis 与独立 AOF
execution Redis 组合后的恢复语义。尤其需要证明模型已经返回、终态尚未被 Core 接受时，任一服务重启不会再次
调用供应商或写入第二条回答消息。

本规格只冻结本机隔离验收，不授权访问 `novelwriterdev`、`novelwriter`、生产服务器或真实模型供应商，也不改变
生产 Compose、发布工作流、Web、CLI 实现或已安装 Skill。

## 目标

使用真实、相互独立的进程或镜像完成如下纵切：

```text
公共 API 或 Java CLI
  -> Java Core
  -> PostgreSQL 14 + pgvector
  -> Python Agent HTTP 执行入口
  -> FakeModelProvider
  -> 独立 execution Redis AOF journal
  -> Agent 回调
  -> Core 事务物化 WritingMessage / WorkflowStep / WorkflowRun / WorkflowEvent
  -> 公共 GET / SSE / 会话消息回读
```

验收必须覆盖：

1. 正常成功，且 PostgreSQL 中只有一个 V2 Run、一个模型 Step、一个完整章节 Evidence item、一个用户消息和一个
   Agent 回答消息；不产生 ReviewArtifact 或 Reviewer Step。
2. 相同 `clientRequestId` 与相同请求重放返回同一 Run；相同键不同正文稳定冲突；两种情况都不增加模型调用或
   消息。
3. SSE 初次连接先收到权威 `run_snapshot`；断线后以数字 `Last-Event-ID` 重连，不重放已经消费的终态副作用，
   最终 `completed` 的 `resultId` 指向唯一回答消息。
4. Fake provider 已完成、Agent 尚未收到合法 Core 终态回执时重启 Agent；AOF journal 重启后重放完全相同的
   `resultHash`，模型调用计数仍为一，回答消息仍为一。
5. callback 前重启 Core，Agent 只重放 journal；callback 事务提交后但 HTTP 回执丢失或 Core 再次重启时，重复
   callback 只得到幂等回执，不增加消息、事件、用量或账本事实。
6. 至少一种确定性取消竞争：在 provider 前取消时供应商调用为零，或 matching-fence 迟到结果只结算允许的用量而
   不生成回答。Run 只能有一个终态，取消后不能被完成反转。
7. 整个验收只连接本次创建的网络、容器、卷和临时目录；退出时自动删除容器、网络、卷和测试密钥。

## 隔离编排

Core 初始必须以 `route=off` 和 canonical `off` release guard 启动，以便只创建测试用户、小说与章节。bootstrap 得到精确
userId/novelId 后，本地 runner 计算 canonical scope SHA，发布 0444 committed guard（绑定当前 execution manifest
fingerprint），把 Core 原子重建为精确单 user+单 novel `allowlist` 后才允许创建 fresh V2 Run。E2E 禁止 `route=all`，guard
目录只读挂载；这只证明本地隔离协议，不生成生产 receipt 或生产授权。

- 新增独立 Compose overlay 和测试 harness；不得修改 `infra/compose.yaml` 的生产行为。
- PostgreSQL 固定使用 14 系列且包含 pgvector。数据库从冻结 pre-contract 重建，再只执行已批准的
  `scripts/migrations/20260831_durable_agent_execution.sql`；数据库名必须含显式测试标识。
- 普通 Redis 与 execution Redis 必须是两个实例和两个网络身份。execution Redis 必须使用独立卷，并验证
  `appendonly=yes`、`appendfsync=always`、`aof-load-truncated=no`、`maxmemory-policy=noeviction`。
- 两个全新 Redis 在 Agent 启动前必须分别由现有具名
  `scripts/durable_agent_v1_drain_index_initialize.lua`、
  `scripts/durable_agent_v2_drain_index_initialize.lua` 初始化联合 drain index。one-shot 服务必须先证明数据库业务
  key 数为零，只接受脚本返回 `initialized`，随后回读 marker 精确为版本 `1`；非空、版本不一致或脚本失败都必须
  阻止 Agent 启动，禁止手工 `SET` marker。
- Java Core 和 Python Agent 使用临时生成的 Ed25519 服务密钥；浏览器 JWT 也使用测试随机值。密钥不得写入仓库、
  进程参数或测试报告。
- 模型固定为 `FakeModelProvider`。禁止设置或透传 `OPENAI_API_KEY`、生产数据库 URL、远程主机名或真实供应商地址。
- 端口只绑定 `127.0.0.1` 并由 Docker 随机分配；服务间调用使用隔离网络 DNS。
- harness 使用唯一 Compose project 和临时工作目录；无论成功、失败或中断，都执行 `down --volumes
  --remove-orphans`，再删除测试临时文件。

## 确定性故障断点

故障不能依赖 `sleep` 猜时序。测试控制面只允许在明确的 `ENVIRONMENT=test` 与随机测试令牌同时满足时启用，并仅
暴露在隔离内部网络。首版断点固定为：

- `provider_completed`：Fake provider 已生成结果并增加耐久调用计数，执行器尚未写终态 journal；
- `terminal_journaled`：完整 Result 与 `resultHash` 已写 AOF，尚未向 Core 发 callback；
- `callback_committed`：Core PostgreSQL 事务已经提交，HTTP 回执尚未返回；
- `provider_waiting`：provider 调用已进入可取消等待点，用于取消竞争。

每个断点使用一次性 gate：测试先等待带 `runId/stepId/jobId/fence` 的到达记录，再执行重启或取消，最后显式释放。
同一 gate 不能跨运行复用。生产配置、生产镜像默认环境和普通 fake provider 测试不得装配该控制面。若当前实现
没有上述可线性化边界，先新增最小测试专用适配器，不得把故障开关混入 Catalog、业务请求、模型输入或生产接口。

Fake provider 调用计数必须保存在独立耐久测试事实中，按供应商幂等键记录完整请求哈希；进程重启后仍可证明同一
逻辑 Step 只发生一次调用。仅检查 Agent 内存计数或日志行数不构成证据。

## 证据与断言

每个场景结束后，harness 从公共接口与只读 SQL 分别取证，并输出不含正文与凭据的 JSON 报告：

- Compose project、镜像 ID、配置文件 SHA 和服务健康状态；
- Run/Step 状态、fence、`attemptCount/providerAttempts`、`resultHash`、Event sequence；
- provider 幂等键的唯一调用数；
- 会话中按本 Run 元数据绑定的用户/Agent 消息计数和回答消息 ID；
- ReviewArtifact、WorkflowEvaluation、TokenUsage、CreditLedger 与 BillingReservation 的相关计数；
- execution Redis AOF 状态、pending/rejected/delivered journal 状态；
- SSE snapshot、断线 cursor、重连事件序列与终态；
- 每次重启前后的容器 ID、restart count 和故障 gate 到达/释放记录。

日志、报告和测试失败消息不得包含完整章节、完整回答、JWT、服务私钥、数据库密码或供应商请求正文。完整内容只在
测试断言进程内按 SHA-256 比较，不写入持久报告。

Fake provider 的 `billable=false` 只表示用户扣费为零，不表示跳过 V2 计费协议或删除审计事实。成功的
`answer_question` 必须精确保留一条绑定该 Run/Step/User 的 `WorkflowBillingReservation` 和一条
`TokenUsage`：reservation 必须为 `settled`，`reservedMicros=0`、`chargedMicros=0`、`settledAt` 非空，且
reservation `usageJson` 与 Step 累计 usage 逐字段一致；TokenUsage 的 request/run/task/user 绑定及 token 字段必须
与该 reservation usage 一致。该测试用户在 Run 前后的余额差必须为零，且该 reservation requestId 对应的
`CreditLedger` 行数必须为零。已结算 reservation 是必须保留的幂等审计行，不能用
`reservationCount=0` 断言把它误报成副作用；反之，`reserved`、`reconciliation_required`、非零金额、重复
TokenUsage、余额变化或账本行都必须作为红灯停止。

失败报告必须在业务断言前保存上述脱敏结构证据：只允许记录计数、状态、零金额、`settledAt` 是否存在、usage
规范化 SHA-256、绑定是否一致、token 数值、余额差和布尔结论；不得保存 usage JSON 原文、余额绝对值或正文。
`20260901T101654Z-d9d6e766` 首次恢复 `happy` 时已经完成一次 provider、Run/Step、会话与 SSE，但旧 runner 在
`reservationCount != 0` 处提前失败并已删除隔离卷；该报告没有保存 reservation 状态/金额/usage、TokenUsage 或余额，
因此只能证明验收断言过时，不能事后宣称实际 reservation 已结算或发生泄漏。修正 runner 与其门禁后只允许再运行
一次 `phase=happy`；任何实际字段不满足上述精确形状都必须停止，不扩展到故障矩阵。

修正门禁后的唯一 `happy` 重跑 `20260901T104858Z-181a4988` 已在本地隔离栈通过。报告绑定最终 Core 镜像
`sha256:f609ce3f62692c6b22afa28a06bd7c2a3a9500faec3d88e4f3e187aa249f3b1b` 与 Agent 镜像
`sha256:d67c918f0a8e9090ffd0ef45cbf8ed85642fe1f23d3bbf4514f5dd23ea0ee339`，且 Agent 镜像内 journal/queue
源码 SHA 与冻结值精确一致。该场景证明：Agent submit 为一次 202，Fake provider 物理/完成调用均为一次；Run 与唯一
generation Step 完成，公共会话恰为一问一答，同幂等键返回原 Run 且不增加 provider、消息或数据库事实；首次 SSE
响应头/首帧均为 80 ms，数字 cursor 断线重连的响应头/首帧均为 96 ms，并连续收到唯一 completed Event。

同一报告还证明 Fake 计费审计为一条 `settled` reservation 和一条 TokenUsage，reserved/charged 均为零、
`settledAt` 存在、reservation 与 Step usage SHA 相同，全部 request/run/step/user/token 绑定为真；CreditLedger 为零且
余额差为零。退出时 `down -v` 返回零，project 容器、网络、卷均为零，临时密钥目录已删除。该结果只完成本规格的
`happy` 阶段；callback 丢回执/AOF、Core/Agent 重启、取消竞争、真实供应商与真实 2 核 2 GB 整机门禁仍未验证。

Java Core 实际 `ExecutionStepRequest` 还必须经过独立跨语言 wire golden：Java 从隔离 PostgreSQL fixture 领取
`answer_question` Step，并由生产 `ObjectMapper` 写入临时 JSON；Python 只能使用
`ExecutionStepRequest.model_validate_json` 严格校验。422 诊断代理只记录请求 SHA、资源身份和
`detail[].loc/type`，不得记录请求正文、校验 input、message 或 context。

### SSE 首帧诊断边界

`20260901T083737Z-4bcef18b` 的本地 `happy` 阶段已经证明 Core 只向 Agent 提交一次且 Agent 返回 202，
provider 进入确定性等待点；但公共 SSE 客户端在 45 秒内没有收到响应头。该次失败报告只保存了安全的提交身份和
客户端超时，没有在清理前保存 Core 日志、JVM thread dump、`pg_stat_activity`、`pg_locks` 或 cgroup
`cpu.stat`。Core 当前也没有分别覆盖 Controller 进入、snapshot 查询完成、observer 激活和首帧写出的成功日志，
因此不得事后把该失败归因为具体代码行或 0.45 CPU 配额。

在再次启动 Compose 前，必须先新增一个 Java `RANDOM_PORT`、隔离 PostgreSQL 的真实 HTTP 回归，冻结以下最小
边界：

- 启用 V2 schema 与路由并直接 seed 一个 `running` V2 Run 及其连续 WorkflowEvent；不启动 Agent，也不直接调用
  `StreamingResponseBody.writeTo`；
- 使用有界流式 HTTP 客户端分别记录连接开始到 200 响应头、连接开始到首个完整 SSE frame 的耗时；
- 首帧必须是与请求 Run 绑定、`engineVersion=2`、数字 cursor 等于 `baseSequence` 的 `run_snapshot`；
- 测试失败只保留状态、耗时、事件类型和资源身份，不保留正文。

若该真实 HTTP 回归失败，先保留测试失败证据并定位 Servlet/异步写出链，不得启动 Compose。只有该回归通过后，
才可另行批准一次保持 Core 0.45 CPU 配额的诊断栈；该栈必须在超时后、清理前采集 Core 容器日志、JVM
`SIGQUIT` thread dump、PostgreSQL 活动/锁和 cgroup CPU throttling 事实，再区分代码缺口与资源门。

### Spring 7 首帧根因与终态修复门禁

隔离 PostgreSQL + `RANDOM_PORT` 的真实 HTTP 回归已经把边界收敛为：Controller、`readSnapshot`、共享 observer
订阅和 `StreamingResponseBody.writeTo` 都已进入，虚拟线程最终阻塞在
`WorkflowEventTailObserver.Subscription.await`；但客户端在 5 秒内仍收不到响应头。线程转储保存在该测试的
Surefire 诊断证据中，不包含正文。根因不是 PostgreSQL、observer、Tomcat 或 0.45 CPU 配额，而是 Spring
Framework 7 的响应 flush 语义：body `OutputStream.flush()` 不再提交响应，框架只在整个
`StreamingResponseBody` 回调返回后调用真实 `ServerHttpResponse.flush()`，running SSE 因而永远不能首发。

修复不得启用临时全局 flush property。Core OpenAPI generator 只能把 `WritingEventStream` 改映射为
`SseEmitter`，`BinaryFileStream` 必须继续使用 `StreamingResponseBody`；公共 OpenAPI JSON、URL、媒体类型、
SSE event/id/data/heartbeat 字节和 CLI 均不变。V1 与 V2 写作事件路径必须统一进入 emitter 生命周期，每连接使用
虚拟线程；V2 在返回 emitter 前同步校验 snapshot/cursor 并预留 subscription，成功发送首个 `run_snapshot`
后才激活有界 observer。completion、error、timeout、客户端断开和 worker 退出都必须幂等关闭 subscription 与
worker；send 的 `IOException` 和 Spring 7 已完成态 `IllegalStateException` 不得重试，终态最后一帧成功后才
`complete()`。

为消除 `SseEmitter` handler 初始化前 early-send 的竞态，应用 service 必须返回平台 `ManagedSseEmitter`，但不得
读取 Servlet 请求；Writing API 层显式把该 emitter arm 到当前请求，平台 `AsyncHandlerInterceptor` 只在
`afterConcurrentHandlingStarted` 启动 worker。此回调发生在 Spring 为 emitter 安装 handler 之后，因此首次 send
成功返回才可作为物理 flush 回执并激活 subscription。若 controller 忘记 arm、executor 拒绝、handler 初始化后
bean 关闭或请求同步结束，session registry 都必须显式完成/中止 emitter 并回收 stream；不能依赖 Spring 吞掉的
interceptor 异常。客户端断线使用 no-body 清理；仍可写 emitter 的 converter/handler
`IllegalStateException` 必须走错误完成，不能伪装成正常断线。专用 `AsyncRequestNotUsableException` handler 不得
对已提交响应二次写 JSON。

隔离 PostgreSQL + `RANDOM_PORT` 门禁须把 handler-ready 与资源生命周期一并冻结：延迟启动 handler 并推进超过
4 个 observer 更新批次时，首帧 flush 前不得 activate 或误判慢消费者；executor reject、本地 bean close、真实
客户端 RST 和终态 EOF 都须在有界时间内让 subscription/session/worker 归零。主动断线测试必须使用读到首帧后
设置 `SO_LINGER(0)` 的原始 TCP RST，或等待协议规定的下一次心跳写失败；关闭 Java HTTP 客户端的小响应流不能作为
内核已观察到断线的确定性证据。

再次运行 Compose 前，真实 HTTP 门禁至少必须覆盖：未认证 401、错误归属 403、running 首帧在有界时间内收到、
数字 `Last-Event-ID` 重连、终态最后一帧后 EOF、客户端主动断开后的 subscription/worker 清理，以及 V1 同路径
兼容。原有只直接调用 `StreamingResponseBody.writeTo` 的测试必须迁移为 emitter 会话/协议帧测试；它不能继续充当
HTTP 首帧证明。只有这些用例通过，才允许重新启动唯一一栈 `phase=happy`。

## 资源边界

overlay 应尽量沿用生产限制：Core 448 MiB、Agent 640 MiB、普通 Redis 96 MiB、execution Redis 128 MiB，并给
PostgreSQL 设置显式限制。验收期间周期采集 `docker stats --no-stream`，记录各服务峰值内存、CPU、OOM 与重启数。

本机 Docker Desktop 上所有服务限制之和、一次短测试或容器未 OOM，均不能证明含宿主 PostgreSQL 的真实
2 核 2 GB 整机稳定性。只有在同形 2 CPU / 2 GiB 主机完成规定观察窗和并发压力后才能解除该生产门禁；本规格的
本地报告必须明确保留这一限制。

## 实现边界

- 优先新增 `infra/compose.durable-agent-v2-e2e.yaml`、`tests/durable_agent_v2_e2e/**` 与一个具名本地 runner。
- E2E 测试默认不随普通 `pytest` 自动执行，必须使用显式 marker 和具名命令；静态架构测试仍纳入普通测试，防止
  overlay 泄露生产地址、密钥、端口或弱化 AOF。
- runner 只能接受本地工作区路径和可选保留证据目录，不接受任意数据库 URL、SSH 主机、生产 profile 或供应商 key。
- 不修改发布 workflow、联合 drain、真实供应商验证、Web/CLI 业务实现或生产 Skill。

## 验收命令与完成标准

最终具名入口必须完成：编译/构建镜像、创建隔离资源、迁移、seed、运行所有场景、采集证据和清理。并另有快速的
静态/单元门禁验证 overlay 与故障钩子只在测试环境可用。

本地分阶段命令固定为：

```bash
.venv/bin/python tests/durable_agent_v2_e2e/validate_wire_golden.py
.venv/bin/python tests/durable_agent_v2_e2e/run_e2e.py --phase happy
.venv/bin/python tests/durable_agent_v2_e2e/run_e2e.py --phase minimum
```

`happy` 只验证成功、同 `clientRequestId` 幂等、公共会话消息与 SSE 数字 cursor 断线重连；任一失败即清理并停止。
`minimum` 才继续验证 callback 已提交后丢回执与 execution Redis AOF 重启。`--rebuild-agent` 只允许重建本地测试
Agent 镜像，且必须在启动栈前通过当前 `execution/journal.py`、`queue/repository.py` 与镜像内源码 SHA-256 精确相等
门禁；`--reuse-built-images` 不得用于掩盖源码与镜像漂移。

只有以下条件同时成立才可把本地跨进程验收标为完成：

- 成功、幂等、SSE 重连、Agent 重启、Core 重启和取消竞争全部通过；
- 所有故障场景 provider 调用数、回答消息数、终态和计费副作用均满足精确唯一性；
- execution Redis 确实经过 AOF 容器重启恢复，而不是测试内存替身；
- 测试退出后不存在本次 project 的容器、网络、卷或密钥临时文件；
- 报告明确区分“本地隔离跨进程通过”和“真实 2 核 2 GB、真实供应商、dev/prod 仍未验证”。
