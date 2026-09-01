# V1/V2 耐久 Agent 联合 drain 与新建入口封锁规格

日期：2026-09-01
状态：实现中

## 背景与结论

`DURABLE_AGENT_EXECUTION_ROUTE_MODE=off` 只禁止创建新的 V2 Run；旧实现会把原本可走 V2 的请求继续落到 V1，
因此它不是“没有新 Agent 工作”的证明。单次读取 PostgreSQL、普通 Redis 和 execution Redis 也不是同一时刻的
分布式快照：若把三个来源中最晚的时间写成统一 `observedAt`，会掩盖采样期间的新建、收敛和容器切换。

本规格把联合 drain 定义为一个封闭失败的稳定窗口：运行中的 Core 必须同时证明 V2 route 关闭和 V1 fresh start
关闭；随后严格按 `PG1 -> 普通 Redis -> execution Redis -> PG2` 采样。两次 PostgreSQL 使用各自独立的
`REPEATABLE READ READ ONLY` 事务并冻结精确阻断集合；只有 PG1/PG2 的身份、集合和水位可比较且完全不变，两个
Redis 的生产者索引完整，运行容器在采样前后没有漂移，才允许形成一份 `verified-drain` 证据。

## 新建入口门禁

Java Core 新增：

```text
V1_FRESH_AGENT_STARTS_ENABLED=true|false
```

- 默认值为 `true`，保持正常生产兼容；只有具名 drain 阶段设置为 `false`。
- 门禁只拒绝没有既有幂等身份、且最终会创建 V1 `WritingTask/WritingRunCommand` 的 fresh start。
- 检查顺序固定为：无锁只读解析既有 `clientRequestId` -> 若命中则按冻结引擎重放 -> 计算新路由 -> 对将落入 V1 的
  fresh start 应用门禁 -> Agent readiness -> advisory/Novel/Chapter 锁 -> 新写入。禁止把门禁放在幂等重放之前，
  也禁止先探测 Agent、取得业务锁或写入用户消息。
- V1 `resume`、`cancel`、Command/Outbox 重投、callback 和终态收敛不经过该门禁。既有 V2 Run 的 cancel、dispatch、
  callback 与计费对账也继续工作。
- drain 时运行中的 Core 容器必须同时精确具有
  `DURABLE_AGENT_EXECUTION_SCHEMA_READY=true`、`DURABLE_AGENT_EXECUTION_ROUTE_MODE=off` 和
  `V1_FRESH_AGENT_STARTS_ENABLED=false`。目标 `.env` 只描述下一次容器配置，不能替代运行态证明。
- 证据还必须验证当前 Core JAR 确实包含 fresh-start 门禁实现；仅有同名环境变量但旧镜像忽略它时失败。

fresh start 被封锁时返回稳定的 `503 AGENT_FRESH_STARTS_DRAINING`；该错误不得创建 Task、Command、消息、Run 或
幂等记录。已有同 `clientRequestId` 请求仍返回原结果。

## Redis 最小 drain 索引

### 普通 Redis / V1 队列

V1 队列生产者在与队列状态相同的 Lua 原子事务内维护：

```text
inkforge:runs:drain:index-version = "1"
inkforge:runs:drain:queued          # ZSET，member=jobId，score=原始 createdAt epoch ms
inkforge:runs:drain:running         # ZSET，member=jobId，score=原始 createdAt epoch ms
```

`enqueue/claim/retry/defer/recover/ack/cancel/corrupt-cleanup` 必须同步更新最小索引。快照只读取这些不含正文的索引，
并双向核对 `queued <-> ready + statuses=queued`、`running <-> processing + statuses=running`；不得读取、解析或输出
`payloads`。每个索引合计最多 256 个 active member，超过上限直接失败，不做 100,000 status 或 5,000 payload
扫描。

升级过渡时，缺少 marker 的普通 Redis 不能出具 drain 状态。具名初始化只允许在运行 Core 已关闭两个新建入口后，
由一个原子 Lua 证明 ready/processing/drain 索引为空，并在 `statuses <= 256` 的超小上限内证明没有孤立
`queued/running`，才写入空 marker；超限或存在 active 项时保持缺 marker 并封闭失败。初始化不读取 payload。

### execution Redis / V2 journal

execution journal 生产者在每个状态转换 Lua 内维护：

```text
inkforge:executions:drain:index-version = "1"
inkforge:executions:drain:active        # ZSET，member=Step hash key，score=accepted_ms
```

active 索引精确包含：

1. `state=accepted|started` 的尚未终态 Step；
2. `state=result|failure` 且 callback 仍为 `pending`（含 leased）或 `rejected` 的未送达 Step。

`accept/start/provider-attempt/terminal/refence/cancel/claim/lease-expire/reschedule/rejected/delivered` 均须在同一 Lua
中校验 marker 并维护或核对 active 索引；`delivered` 必须同时移出 active 和三个 callback 索引。快照最多读取 256
个 active/callback member，并双向核对：

- active member 必须绑定存在的 Step hash，且 `member == prefix + step_id`、`accepted_ms` 合法；
- accepted/started 不得出现在 callback 集合；
- terminal pending 必须恰好出现在 pending 或 leased，leased 必须有匹配 claim；
- terminal rejected 必须恰好出现在 rejected；delivered 不得留在 active 或 callback 集合；
- callback 集合的每个 member 必须反向存在于 active，member 不得跨集合重复；
- restore quarantine 存在、marker 缺失/版本旧、索引孤儿、hash 损坏、超限或 eviction 均直接失败。

生产环境不允许自动猜测重建 execution active 索引。只有权威 PostgreSQL 两次都证明 `engineVersion=2` 的全部 Run
为零、独立 execution Redis 在写入前确实没有任何 key、运行 Core 的 V2 route 始终为 off，才允许具名 action 原子
初始化空 marker。已有任一 V2 DB 记录或 Redis key 时必须进入 quarantine/具名审计，不得把 callback 集合猜成完整
索引。非生产隔离测试可以从全空 Redis 初始化 marker，但不能改变生产规则。

## 权威阻断集合

PostgreSQL 每轮均冻结下列精确、排序后的 `{id, createdAt}` 集合，而不只记录 `count/oldest`。原始集合仅存在于
`0600` 临时文件；最终证据输出每项 `count/oldestId/oldestAt/setSha256` 和整轮 `blockerSetSha256`，不输出全部 ID。

### V1 PostgreSQL

| metric | 非零条件 |
| --- | --- |
| `v1WritingTasksActive` | `WritingTask.phase IN (idle, active, waiting_call)` |
| `v1WritingTasksAwaitingUser` | `WritingTask.phase = awaiting_user_review` |
| `v1WritingTasksRecoverable` | `phase IN (active, waiting_call)` 且 `graphStateJson IS NOT NULL` |
| `v1CommandsActive` | `WritingRunCommand.status IN (pending, submitted, processing)` |
| `v1OutboxUndelivered` | `WritingEventOutbox.deliveryState IN (pending, delivering, blocked)` |
| `v1ArtifactsAwaitingUser` | V1 Artifact 且 `status=awaiting_user` |
| `v1ArtifactsRecoverable` | V1 Artifact 且 `status IN (draft, under_review, applying)` |

`awaiting_user_review/awaiting_user` 无论多老都阻断 drain。终态历史不阻断。

### V2 PostgreSQL

| metric | 非零条件 |
| --- | --- |
| `v2RunsActive` | V2 Run status 不在 `completed/failed/cancelled` |
| `v2StepsActive` | V2 Step status 在 `pending/running` |
| `v2BillingReserved` | BillingReservation `status=reserved` |
| `v2BillingReconciliationRequired` | BillingReservation `status=reconciliation_required` |

### Redis

| metric | 来源 |
| --- | --- |
| `v1AgentJobsQueued` | V1 drain queued 索引 |
| `v1AgentJobsOrCallbacksRunning` | V1 drain running 索引 |
| `v2ExecutionsActive` | execution active 中 accepted/started |
| `v2CallbacksPending` | execution callback pending |
| `v2CallbacksLeased` | execution callback leased |
| `v2CallbacksRejected` | execution callback rejected |

## 稳定采样与输出协议

采样前后分别冻结 `core-api`、`redis`、`execution-redis` 的容器 ID 和不可变 image ID；Redis 快照还返回 Redis
`run_id`。任一容器重建、镜像变化、Redis 进程变化或 Core 白名单配置变化都失败。顺序固定为：

```text
runtime topology 1 -> PG1(RR/RO) -> V1 Redis(EVAL_RO) -> execution Redis(EVAL_RO)
                   -> PG2(RR/RO) -> runtime topology 2
```

PG1/PG2 各自包含数据库 OID、server address/port/version、事务 snapshot、WAL LSN 和观察时间。必须满足：

- 数据库身份完全相同，PG2 时间不得早于 PG1；
- 每个 metric 的精确集合哈希、数量和 oldest 完全相同；
- 两轮整体验证哈希相同；
- 全窗口不超过 30 秒；Redis 的观察时间必须位于 PG1 与 PG2 之间（容许 1 秒时钟误差，但不改写时间）。

成功 stdout 只输出一行 canonical JSON，协议固定为 `schemaVersion=2`，核心结构为：

```json
{
  "schema": "inkforge.durable-agent-joint-drain",
  "schemaVersion": "2",
  "database": "novelwriterdev",
  "coreRuntime": {
    "containerId": "...",
    "imageId": "sha256:...",
    "schemaReady": true,
    "routeMode": "off",
    "v1FreshStartsEnabled": false
  },
  "sampleWindow": {
    "startedAt": "2026-09-01T00:00:00.000Z",
    "ordinaryRedisAt": "2026-09-01T00:00:00.010Z",
    "executionRedisAt": "2026-09-01T00:00:00.020Z",
    "finishedAt": "2026-09-01T00:00:00.030Z",
    "durationMillis": 30
  },
  "postgres": {
    "beforeSnapshot": "100:100:",
    "afterSnapshot": "100:100:",
    "beforeWalLsn": "0/1",
    "afterWalLsn": "0/1",
    "blockerSetSha256": "..."
  },
  "redisIndexes": {
    "v1Version": "1",
    "v2Version": "1"
  },
  "v1DrainZero": true,
  "v2Converged": true,
  "metrics": {}
}
```

`metrics` 必须精确包含本规格全部 metric。`count=0` 时 oldest 为 `null`；非零时必须有合法 UTC oldest；每项必须有
64 位 `setSha256`。输出不把“最晚来源时间”冒充同一观察时刻，并绑定实际运行 Core 身份与两个 Redis index 版本。

## action

```sh
sh scripts/durable-agent-execution-migration.sh initialize-drain-indexes <novelwriterdev|novelwriter>
sh scripts/durable-agent-execution-migration.sh drain-status <novelwriterdev|novelwriter>
sh scripts/durable-agent-execution-migration.sh verify-drain <novelwriterdev|novelwriter>
```

- `initialize-drain-indexes`：仅执行上述空状态初始化；不创建/修改业务数据，不重建已有索引。
- `drain-status`：入口已关闭且采样可信时输出报告；存在阻断项仍以 0 退出，便于监控。来源不可信时不输出报告并
  非 0 退出。
- `verify-drain`：先生成同一报告，再严格复验；仅当运行 Core 两个入口关闭、`v1DrainZero=true`、
  `v2Converged=true` 且所有稳定窗口约束成立时退出 0。合法未收敛报告仍输出并退出 3。
- rollout 的 `route-off-drain` 只表示进入 drain 配置，不得替代 `verify-drain`。

数据库密码仍只进入 `0600 PGPASSFILE`；Redis 仅通过 Compose 具名服务执行 Lua；所有子命令有硬超时。不得 shell
source `.env`，不得输出 Redis URL、数据库 URL、凭据、payload、terminal payload、模型响应或 quarantine 内容。

## 验收

1. Java PostgreSQL Testcontainers 覆盖：默认兼容、fresh V1 被封锁、同幂等请求仍重放、门禁早于 readiness/业务锁/
   写入，以及并发 fresh start 无法穿透；resume/cancel/终态收敛不受影响。
2. 真实 Redis Lua 覆盖 V1 的 enqueue/claim/retry/defer/recover/ack/cancel 和 V2 的
   accept/start/terminal/refence/claim/reschedule/rejected/delivered，证明索引随状态原子变化。
3. 反例覆盖缺 marker、旧 marker、孤儿 member/hash、重复 callback member、超 256 项、超大 payload（快照不得
   读取它）、quarantine、eviction、PG1/PG2 集合变化、时间倒退、容器/镜像/Redis run_id 漂移。
4. 用隔离 PostgreSQL 14 证明 `PG1 -> Redis -> PG2` 期间并发创建或收敛会令证据失败，而不是生成瞬时“零”。
5. migration helper 和 rollout/deploy 架构测试证明 drain 配置来自运行 Core；目标 `.env` 与运行容器不一致时失败。
6. 运行相关 Agent pytest、真实 Redis、Ruff、Mypy、Java PG/JUnit、Modulith 和架构门禁；本实现不联网、不连接真实
   开发/生产、不部署、不执行迁移 SQL。
