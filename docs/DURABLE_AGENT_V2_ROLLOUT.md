# 耐久 Agent V2 数据库迁移与分阶段发布 Runbook

状态：实施期可执行门禁；尚未执行服务器开发库、正式库迁移或生产部署

权威规格：`docs/specs/2026-08-31-core-owned-durable-agent-execution.md`

## 1. 适用边界

本 Runbook 只操作具名迁移：

- `scripts/migrations/20260831_durable_agent_execution.sql`；
- `scripts/migrations/20260831_durable_agent_execution.rollback.sql`。

它不授权其他 DDL、不恢复 PostgreSQL 备份、不修改正式作品内容、不启用视频，也不把 202、容器 healthy 或
schema 表存在当作 V2 canary 成功。数据库目标必须显式为 `novelwriterdev` 或 `novelwriter`，不能使用别名。

所有服务器动作都必须在本地全量门禁、隔离 PostgreSQL 14 + pgvector 验证、发布清单、人工审批和维护窗口完成后
执行。当前仓库中的脚本与测试不代表任何远程数据库已迁移。

## 2. 固定工具与输出

具名迁移入口：

```text
scripts/durable-agent-execution-migration.sh \
  <status|active-v2-count|backup|forward|rollback|export-contract|verify-contract> \
  <novelwriterdev|novelwriter>
```

只读 `status` 只允许以下四种输出：

| 输出 | 含义 | 允许动作 |
| --- | --- | --- |
| `unmigrated` | 完整迁移前结构 | 部署双 contract 兼容镜像、备份、forward |
| `migrated-empty-v2` | 完整迁移后结构，尚无任何 V2 审计事实 | 重复 forward、启用 schemaReady；满足额外门禁时可 DDL rollback |
| `migrated-with-v2` | 完整迁移后结构，已有 V2 Run 或关联审计事实 | 永久禁止 DDL rollback 和 V1-only 镜像，只能 V2-aware route-off 排空 |
| `partial` | 迁移对象不完整或相互矛盾 | 所有写动作停止，人工只读诊断；不得运行 forward 猜测修复方向 |

脚本在连接 PostgreSQL 前固定校验 forward、rollback 和两份 contract 文件 SHA。`.env` 不会被 shell source；
唯一 `DATABASE_URL` 由 Python 安全解析，密码只写入临时 0600 `PGPASSFILE`。传给 `psql`、`pg_dump` 的 URL
已经删除密码并固定连接本机 `127.0.0.1`，来源 URL 必须精确使用 `host.docker.internal`。命令行、stdout、
stderr 和迁移元数据不得出现数据库密码。

分阶段发布门禁使用：

```text
scripts/durable-agent-v2-rollout-gate.sh \
  <pre-contract|post-contract-route-off|schema-ready-route-off|initialize-drain-indexes|allowlist|drain-status|verify-drain|route-off-drain|ddl-rollback> \
  <novelwriterdev|novelwriter>
```

门禁同时验证结构状态、`.env` 路由组合、双 contract/V2-aware 镜像、Java 精确 schema guard、Core/Agent
readiness、execution Redis AOF、quarantine 和 eviction。任何一项失败都不得手工跳过。

## 3. 准备发布清单

发布清单必须在变更窗口前冻结并离线复核：

- Git SHA；
- Web、Core、Agent 三张镜像不可变 digest；
- Core/Agent execution manifest fingerprint；
- Operation Catalog、Prompt/Profile、Output Schema、Step Budget 与 Deployment Profile 版本；
- 迁移 SQL SHA 与 pre/post contract 指纹；
- 当前三服务不可变回滚镜像 ID；
- execution Redis 卷身份、AOF 状态和容量报告；
- V1 Task/Command/Outbox/Artifact 与 V2 Run/Step 联合 drain 快照；
- 备份目录、`SHA256SUMS` 和恢复边界元数据。

新 Core 和 Agent 镜像先通过无网络、无卷、无环境变量的内容探针：

```sh
sh scripts/verify-durable-agent-v2-image.sh core "inkforge-core-api:${INKFORGE_IMAGE_TAG}"
EXPECTED_EXECUTION_MANIFEST_FINGERPRINT=<发布提交中manifest的canonical指纹>
sh scripts/verify-durable-agent-v2-image.sh agent \
  "inkforge-agent-service:${INKFORGE_IMAGE_TAG}" \
  "$EXPECTED_EXECUTION_MANIFEST_FINGERPRINT"
```

Core 探针证明镜像包含双 contract 和 V2 收敛路径。Agent 探针不是 import grep：它在 `--network none`、只读、
无卷和无环境注入的容器内调用已有 Registry loader，验证 manifest 声明的全部版本化资产 SHA 与引用后输出
`v2-aware-image-ok:agent:<manifestFingerprint>`。该值必须与发布提交中 `contracts/agent-execution/manifest.json`
按 `inkforge-canonical-json/1` 计算的预期一致。探针仍不能代替 PostgreSQL、跨服务和业务终态测试。

进入 allowlist 前，部署脚本还会对切换前运行容器的不可变 Agent Image ID 执行同一离线探针。目标 Agent、回滚
Agent、发布预期三者必须完全相等；首次部署没有回滚镜像、旧镜像只能 import、资产损坏或 fingerprint 不同，均在
切换前拒绝 canary。manifest 发生变化时只能先发布为 route-off 并 drain；route-off 只有在部署入口先进入当前运行
Core 容器只读验证实际 `DURABLE_AGENT_EXECUTION_ROUTE_MODE=off`，再通过 `active-v2-count` 从权威 PostgreSQL
精确证明全部 `engineVersion=2` Run 已终态、非终态数量为 0 后，才允许目标与回滚 fingerprint 不同。目标 `.env`
中的 off 不能替代运行态证明；运行态检查失败、查询失败、结果不是非负十进制整数或数量非零，必须在版本切换和
`compose up` 前拒绝；两边
仍必须分别通过完整 Registry 探针，且失败回滚后继续保持 route-off。

## 4. 阶段 A：部署兼容镜像，保持旧结构与 route-off

目标配置：

```dotenv
DURABLE_AGENT_EXECUTION_SCHEMA_READY=false
DURABLE_AGENT_EXECUTION_ROUTE_MODE=off
DURABLE_AGENT_EXECUTION_USER_ALLOWLIST=
DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST=
V1_FRESH_AGENT_STARTS_ENABLED=true
```

先部署同一套 V2-aware 三服务镜像，但不迁移数据库、不装配 V2 repository/worker、不创建新 V2 Run。部署后执行：

```sh
APP_DIR=/srv/smart-novel-gen \
  sh scripts/durable-agent-v2-rollout-gate.sh pre-contract novelwriterdev
```

开发库门禁通过后，正式库在独立人工批准窗口重复同形只读门禁：

```sh
APP_DIR=/srv/smart-novel-gen \
  sh scripts/durable-agent-v2-rollout-gate.sh pre-contract novelwriter
```

必须证明同一正在运行的 Java 镜像精确接受迁移前 contract，V1 服务仍正常，execution journal 已启用 AOF 且没有
quarantine/eviction。不能先迁移再补部署兼容镜像。

## 5. 阶段 B：创建 PostgreSQL 与 execution journal 联合备份

`backup` 只允许在 `unmigrated + schemaReady=false + route=off` 下执行。它强制从当前独立 execution Redis
生成并校验 RDB 快照；没有 journal 容器、AOF 异常、RDB 校验失败或任何恢复边界元数据缺失都会失败。

```sh
APP_DIR=/srv/smart-novel-gen \
  sh scripts/durable-agent-execution-migration.sh backup novelwriterdev
```

成功只输出 `backup-ok:<绝对目录>`。记录该目录但不要把数据库 URL、`.env` 或 PGPASS 复制进发布清单。
目录必须包含并通过 `SHA256SUMS`：

- `database.dump`；
- `execution-journal.rdb` 与 `execution-journal.meta`；
- `recovery-boundary.meta`；
- `durable-agent-migration.meta`。

正式库在自己的批准窗口创建独立备份，不能复用开发库备份，也不能把开发数据晋升生产。

## 6. 阶段 C：在线 forward，仍保持 schemaReady=false 与 route-off

把上一阶段输出目录作为非敏感路径传给 helper：

```sh
APP_DIR=/srv/smart-novel-gen \
DURABLE_AGENT_MIGRATION_BACKUP_DIR=/受保护备份目录/inkforge-时间戳 \
  sh scripts/durable-agent-execution-migration.sh forward novelwriterdev
```

首次 forward 后，原兼容实例必须在不重启、不启用 V2 worker 的情况下继续 ready：

```sh
APP_DIR=/srv/smart-novel-gen \
  sh scripts/durable-agent-v2-rollout-gate.sh post-contract-route-off novelwriterdev
```

随后使用同一备份目录重复一次 forward，证明脚本幂等，再重复 `post-contract-route-off` 门禁。任一次结果为
`partial`、精确 Java schema guard 失败、旧实例 readiness 失败或出现 V2 数据，都立即停止；不得继续重启来掩盖问题。

正式 forward 还要求当前用户拥有的 0600 确认令牌文件，文件内容精确为：

```text
novelwriter:20260831:apply
```

令牌文件路径通过 `DURABLE_AGENT_MIGRATION_CONFIRM_FILE` 传入，令牌正文不得出现在命令参数、CI 日志或 shell
trace。脚本验证文件所有者、0600 权限和精确内容后，才设置迁移 SQL 要求的固定 GUC。正式库命令同形如下：

```sh
APP_DIR=/srv/smart-novel-gen \
DURABLE_AGENT_MIGRATION_BACKUP_DIR=/受保护正式备份目录/inkforge-时间戳 \
DURABLE_AGENT_MIGRATION_CONFIRM_FILE=/受保护临时目录/forward.confirm \
  sh scripts/durable-agent-execution-migration.sh forward novelwriter
```

### 6.1 导出并复验真实迁移后 contract 证据

两次 forward 和两次 `post-contract-route-off` 门禁通过后，必须在启用 `schemaReady` 前为当前目标库创建独立、
不可覆盖的证据目录。目录路径不得位于仓库 canonical contract 位置，也不得预先存在：

```sh
APP_DIR=/srv/smart-novel-gen \
DURABLE_AGENT_CONTRACT_EVIDENCE_DIR=/受保护证据根目录/novelwriterdev-20260831 \
  sh scripts/durable-agent-execution-migration.sh export-contract novelwriterdev
```

成功只输出：

```text
contract-export-ok:/受保护证据根目录/novelwriterdev-20260831:<contractFingerprint>
```

目录必须只包含 `schema-contract.json`、`schema-only.sql`、`contract-verification.meta` 和 `SHA256SUMS`。
`schema-contract.json` 的结构正文来自已由实时 Java guard 精确验证的冻结 post contract 按当前运行 Core schema
profile 生成的精确投影，只允许 `source` 替换为当前安全连接读取的来源元数据；`schema-only.sql` 是同一数据库的
只读结构导出，仅移除 PostgreSQL 每次随机生成、
不描述结构的 `\\restrict/\\unrestrict` 控制行以获得稳定 SHA。随后必须立即独立复验：

```sh
APP_DIR=/srv/smart-novel-gen \
DURABLE_AGENT_CONTRACT_EVIDENCE_DIR=/受保护证据根目录/novelwriterdev-20260831 \
  sh scripts/durable-agent-execution-migration.sh verify-contract novelwriterdev
```

成功只输出：

```text
contract-verify-ok:/受保护证据根目录/novelwriterdev-20260831:<contractFingerprint>
```

两个动作都复用 helper 的唯一 `.env`、0600 `PGPASSFILE`、无密码 `127.0.0.1` URL、精确数据库名和只读超时；
密码不得进入 argv、stdout、stderr、证据或 shell trace。`verify-contract` 会重新读取实时状态、Java guard 与
schema-only dump；任何目录符号链接、额外文件、SHA/fingerprint/数据库身份/post contract 漂移都必须停止发布。
证据只用于审计，helper 不会覆盖仓库 `schema-contract.json` 或执行 DDL。开发库和正式库必须分别导出，禁止复用。

## 7. 阶段 D：同一镜像启用 schemaReady，继续 route-off

只有 `migrated-empty-v2` 和阶段 C 全部门禁通过后，才修改配置并重启同一已验证镜像：

```dotenv
DURABLE_AGENT_EXECUTION_SCHEMA_READY=true
DURABLE_AGENT_EXECUTION_ROUTE_MODE=off
DURABLE_AGENT_EXECUTION_USER_ALLOWLIST=
DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST=
```

执行：

```sh
APP_DIR=/srv/smart-novel-gen \
  sh scripts/durable-agent-v2-rollout-gate.sh schema-ready-route-off novelwriterdev
```

该阶段验证 V2 repository、dispatcher、cancel、callback、SSE 和 manifest readiness 已装配，但新建路由仍关闭。
回读数据库必须仍为 `migrated-empty-v2`。开发环境同形演练、故障注入和低额度真实供应商验证完成前，不得进入生产。

进入 allowlist 前必须安排一个短暂的“双入口关闭”窗口，先修改并重启同一镜像：

```dotenv
DURABLE_AGENT_EXECUTION_SCHEMA_READY=true
DURABLE_AGENT_EXECUTION_ROUTE_MODE=off
V1_FRESH_AGENT_STARTS_ENABLED=false
```

运行中的 Core 必须实际读取到这三个值，且 JAR 必须包含 V1 fresh-start 门禁。随后执行：

```sh
APP_DIR=/srv/smart-novel-gen \
  sh scripts/durable-agent-v2-rollout-gate.sh initialize-drain-indexes novelwriter
```

该 action 只在 PostgreSQL 全部 V2 Run 为零、普通 Redis 无 active V1 job 且 execution Redis 无任何执行 key 时，
原子写入 V1/V2 drain index marker。已有 V2 数据而缺 marker 时会进入 quarantine/具名审计，绝不根据 callback
集合猜测重建。初始化完成后才可重新开启 V1 fresh start 并进入 allowlist。

## 8. 阶段 E：账号与隔离小说交集 allowlist

只配置服务端解析的稳定用户 ID 和新建隔离小说 ID；两者取交集，用户名、Cookie、展示名或用户提交 ID 均不能替代：

```dotenv
DURABLE_AGENT_EXECUTION_SCHEMA_READY=true
DURABLE_AGENT_EXECUTION_ROUTE_MODE=allowlist
DURABLE_AGENT_EXECUTION_USER_ALLOWLIST=<稳定用户ID>
DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST=<新建隔离小说ID>
V1_FRESH_AGENT_STARTS_ENABLED=true
```

重启同一镜像后执行：

```sh
APP_DIR=/srv/smart-novel-gen \
  sh scripts/durable-agent-v2-rollout-gate.sh allowlist novelwriter
```

随后只通过公共 HTTPS 或受支持 CLI 验证指定账号与新建隔离小说，顺序为：身份只读、一次问答、一次完整候选
discard、一次 approve、一次 cancel、SSE 重连和唯一用量。内部接口、数据库直写和旧作品均不得用于 canary。
观察至少 30～60 分钟或足量样本。任何协议错误、重复产物/计费、不可恢复 Step、终态缺失、manifest 漂移或
SLO 硬失败立即停止新建路由。

当前 `scripts/deploy-production.sh` 明确拒绝 `route=all`，防止绕过本 Runbook 直接全量。canary 验收并不自动
授权全量；后续全量切换必须完成规格中的所有 Operation 迁移、V1 drain 和独立放量审批后，再修改这道代码门禁。
allowlist 门禁同时从当前发布检出计算预期 fingerprint，并让正在运行的 Agent 离线输出实际值；任一不一致都必须
先退回 route-off，不能依赖 readiness 缓存或部署失败后的旧 Agent 自动兜底。

## 9. 应用 route-off、回滚与 DDL rollback

停止 canary 时保持：

```dotenv
DURABLE_AGENT_EXECUTION_SCHEMA_READY=true
DURABLE_AGENT_EXECUTION_ROUTE_MODE=off
V1_FRESH_AGENT_STARTS_ENABLED=false
```

并执行：

```sh
APP_DIR=/srv/smart-novel-gen \
  sh scripts/durable-agent-v2-rollout-gate.sh route-off-drain novelwriter
```

`route-off-drain` 同时关闭 V2 新建路由和 V1 fresh start；既有幂等重放、resume、cancel、Command/Outbox 重投、
callback 与终态收敛继续允许。只有运行中 Core 容器实际证明两个入口均关闭，才可开始
`PG1 -> 普通 Redis -> execution Redis -> PG2` 联合采样：

```sh
APP_DIR=/srv/smart-novel-gen \
  sh scripts/durable-agent-v2-rollout-gate.sh drain-status novelwriter
APP_DIR=/srv/smart-novel-gen \
  sh scripts/durable-agent-v2-rollout-gate.sh verify-drain novelwriter
```

`drain-status` 对合法非零阻断项仍退出 0；`verify-drain` 只有 V1/V2 全部收敛且两轮 PostgreSQL 精确阻断集合、
容器/镜像/Redis run_id、时间水位与两个索引版本均稳定时退出 0。任一 marker 缺失、孤儿、超限、quarantine、
采样期间变化或身份漂移都失败，不能把多个来源中最晚时间冒充同一时刻。

route-off 不能中断已有 V2。回滚镜像必须同时满足：Core 和 Agent 均通过 V2-aware 内容探针，
Core 保持 `schemaReady=true`，能继续查询、取消、调度、接收 callback、结算并收敛既有 Run。目标与回滚 Agent
fingerprint 不同时还必须先证明当前运行 Core 的实际 route 为 off，再通过 `active-v2-count` 证明 V2 非终态为 0；
否则即使目标配置写着 route-off 也不能切换。生产部署脚本
会在迁移后结构上拒绝 Python Core 或不含 V2 收敛代码的旧 Agent 自动回滚组合。

一旦 `status` 返回 `migrated-with-v2`，以下结论永久成立：

- 禁止执行 DDL rollback；
- 禁止部署 V1-only Python Core；
- 禁止把旧 contract 当回滚目标；
- 只能 route-off 后由 V2-aware 镜像排空和修复。

DDL rollback 只服务“刚完成结构迁移、尚无任何 V2 事实”的短窗口。先切回：

```dotenv
DURABLE_AGENT_EXECUTION_SCHEMA_READY=false
DURABLE_AGENT_EXECUTION_ROUTE_MODE=off
V1_FRESH_AGENT_STARTS_ENABLED=false
```

再执行 `ddl-rollback` 门禁。正式 rollback 的 0600 令牌文件必须精确包含：

```text
novelwriter:20260831:rollback-empty-v2
```

最后使用原备份目录调用 `rollback novelwriter`。SQL 自身会再次验证所有 V2 表、V2 列和 Artifact 绑定均为空；
任一事实存在时事务整体拒绝。脚本不自动从备份覆盖数据库。

## 10. PostgreSQL 恢复前的 execution quarantine

数据库备份不等于数据库覆盖恢复授权。本仓库刻意不提供自动 `pg_restore` 覆盖入口。若未来另有精确恢复授权，
必须先把 `DURABLE_AGENT_EXECUTION_ROUTE_MODE=off` 部署并确认生效，再停止新的 V2 execution dispatch。随后先记录
当前 Core、Agent 容器 ID，并使用 `docker compose stop core-api agent-service` 等待两个进程完全退出；这样已经进入
Core 的 callback 事务会先完成或随连接断开回滚，Agent 内尚未收敛的 provider attempt 则保留为待联合对账事实。
仅 route-off、dispatch flag 或 Redis marker 前后重复 `GET` 都不能消除最后一次 `GET -> HTTP` 竞态。两个进程退出后，
才可在任何 PostgreSQL restore 命令之前对当前 execution Redis 执行：

```sh
POSTGRES_BACKUP_DIR=/受保护备份目录/inkforge-时间戳 \
EXECUTION_REDIS_CONTAINER=<当前execution-redis容器ID> \
CORE_API_CONTAINER=<已停止的core-api容器ID> \
AGENT_SERVICE_CONTAINER=<已停止的agent-service容器ID> \
RESTORE_EPOCH=postgres-restore-<具名epoch> \
POSTGRES_RESTORE_CONFIRM_FILE=/受保护临时目录/postgres-restore.confirm \
DURABLE_AGENT_EXECUTION_ROUTE_MODE=off \
EXECUTION_DISPATCH_STOPPED=true \
  sh scripts/prepare-postgres-restore-quarantine.sh
```

0600 确认文件内容为：

```text
PREPARE_POSTGRES_RESTORE_QUARANTINE:<RESTORE_EPOCH>:<database.dump的SHA-256>
```

脚本验证备份与恢复边界，并从 execution Redis 容器的 Compose project、config files 与 working dir 标签确定权威
编排身份；随后按同一 project + service 枚举全部 execution Redis、Core 和 Agent 容器。三类 service 必须各自恰有
一个实例、与显式传入 ID 一致、共享同一 config 身份，且 Core/Agent 精确为
`exited + Running=false + Paused=false + Restarting=false`。传入旧 stopped 容器而同 project 仍有现行实例、跨
project/config、暂停、重启、缺失或残留多实例时，都必须在 Redis `EVAL` 前拒绝；相同全量检查还会在 `WAITAOF=1`
后复验。随后脚本才把
数据库快照 SHA/epoch 写入 `inkforge:executions:restore:quarantine`，并精确要求本地 `WAITAOF` ack 为 1。它不会运行
`psql` 或 `pg_restore`，也不会替操作者关闭路由或停止容器。ack 为 0、AOF 异常或已有不同 quarantine 时，数据库
恢复必须停止。数据库覆盖恢复期间 Core 与 Agent 必须保持停止。

获准的外部恢复完成后，先保持 `route=off` 和 quarantine marker，仅启动对账所需的 Core、Agent；此时 Agent
readiness 失败和 terminal HTTP fail-closed 都是预期维护态，禁止把服务接回公网流量。必须联合 Core Run/Step、
callback/resultHash、TokenUsage/CreditLedger、BillingReservation 和供应商请求 ID 生成具名对账报告。只有报告 SHA
人工核验后，才能用现有 `scripts/clear-execution-journal-quarantine.sh` 精确解除；journal 缺 key 或 24 小时
tombstone 过期不能证明供应商从未调用。解除取得本地 AOF 确认后继续保持 route-off，由 replayer 对 callback pending
做精确幂等回放并联合回读 Core 权威结果；pending/rejected/unknown 全部归零且报告复核前不得恢复 dispatch，更不得
开启 allowlist。

## 11. 硬停止条件

出现以下任一事实立即停止当前阶段，不自动推断修复方向：

- `status=partial`、数据库名或来源 host 不匹配；
- SQL/contract SHA 漂移；
- 双 contract Java schema guard 失败；
- 备份缺 PostgreSQL dump、execution RDB、校验和或恢复边界；
- execution Redis AOF 不健康、WAITAOF 本地 ack 不为 1、出现 quarantine/eviction；
- PostgreSQL restore 写 marker 前 Core 或 Agent 任一具名容器未达到 `exited|false`；
- `schemaReady=false` 却配置 allowlist/all，或已有 V2 数据仍试图关闭 schemaReady；
- 迁移后自动回滚目标是 Python Core/V1-only Agent；
- manifest fingerprint、部署模型或 pricing snapshot 不匹配；
- callback rejected backlog、重复 Artifact/usage/ledger/apply、终态反转或 outcome unknown 被盲重试。

硬停止后保留数据库、journal、备份、日志和三服务镜像原状。禁止运行 `down -v`、删除卷、删除镜像、清空
quarantine、执行任意 SQL 或从备份覆盖恢复来“快速回到绿色”。
