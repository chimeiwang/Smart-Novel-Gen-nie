# Durable Agent V2 可信开发证据 v2

日期：2026-09-01

状态：基础契约实施中；当前 development Workflow 继续失败关闭，本文不表示真实开发环境、真实供应商或
2 核 2 GB 同形主机已经接入

关联规格：

- `docs/specs/2026-08-31-core-owned-durable-agent-execution.md`
- `docs/specs/2026-09-01-durable-agent-v2-compose-e2e.md`
- `docs/specs/2026-09-01-durable-agent-v2-release-workflow.md`

## 1. 问题

旧 `inkforge-durable-agent-v2-development-evidence/1` 只把七个文件的 SHA 写进一个汇总 JSON。它能发现文件字节
漂移，但没有验证报告语义；任意 `test-report/1` JSON 只要 hash 相等，也能通过报告 bundle 校验。旧格式还把一次性
迁移资格与每个候选提交的验证混为一体，把开发环境拓扑与 canary 用户/小说 scope 混为一体，并且没有 producer
`runAttempt`、签发时间或过期时间。

因此 v1 只能继续作为失败关闭控制面的历史输入，不能作为生产级开发证据。v2 先建立离线、严格、可复用的证据格式与
构建器；真实 producer、受保护 development environment、自托管 runner、远程开发库、真实模型身份和 GitHub artifact
provenance 仍须后续接入。

## 2. 不变量

1. 一次迁移资格与每提交候选证据是两个独立、不可互换的 content-addressed bundle。
2. 迁移资格绑定具名 forward/rollback SQL、迁移前后 contract、开发拓扑和 producer run；只要这些事实不变且未过期，
   后续候选可以引用同一资格，不得为每个候选反复 rollback 已经产生 V2 事实的共享开发库。
3. 候选证据绑定精确 target commit、三张不可变镜像 digest、execution manifest fingerprint、开发拓扑、canary 场景、
   producer run/attempt 和迁移资格 SHA。
4. `developmentScopeSha256` 只标识受保护开发环境的数据库、普通 Redis、execution Redis 与运行拓扑；
   `canaryScenarioFingerprint` 只标识隔离测试主体、Operation、输入 fixture 与断言版本。二者不得相等或互相替代。
5. 每份报告都是 exact-schema、canonical UTF-8 JSON；未知字段、重复 key、浮点数、非有限数字、错误 format、错误
   reportType 或语义断言不通过都失败。
6. bundle 必须是绝对路径、0700 目录、0600 单链接普通文件、无 symlink、单文件不超过 1 MiB、精确白名单和 canonical `SHA256SUMS`；构建使用
   同文件系统临时目录、文件与目录 fsync、原子 no-replace 发布，既有目标绝不覆盖。
7. 证据只保存 hash、不可变 ID、计数、状态、时间和布尔断言；禁止正文、模型请求/响应、用户名、小说 ID、Cookie、
   bearer token、私钥、密码、数据库 URL、供应商密钥和 reasoning 原文。
8. validator 只证明“artifact 满足 v2 schema 且与调用者给出的可信期望一致”，不能证明报告观察真实发生。生产
   consumer 还必须复验受保护 producer run、artifact provenance、runner/topology 身份和外部平台事实。
9. 当前 `.github/workflows/durable-agent-v2-development-evidence.yml` 继续在上传 artifact 前硬失败；v2 helper 不被现有
   production release Workflow 消费，也不降低 v1 verifier 的任何失败条件。

## 3. 两层 artifact

### 3.1 一次迁移资格

目录固定包含：

```text
migration-qualification.json
migration-backup-report.json
live-contract-report.json
idempotent-forward-report.json
rollback-rehearsal-report.json
SHA256SUMS
```

汇总格式为 `inkforge-durable-agent-v2-migration-qualification/2`，顶层精确字段为：

```json
{
  "database": "novelwriterdev",
  "developmentScopeSha256": "<64 hex>",
  "expiresAt": "<UTC RFC3339 秒精度>",
  "format": "inkforge-durable-agent-v2-migration-qualification/2",
  "issuedAt": "<UTC RFC3339 秒精度>",
  "migration": {
    "bundleFingerprint": "<64 hex>",
    "forwardSqlSha256": "<64 hex>",
    "migrationSourceCommit": "<40 hex>",
    "postContractFingerprint": "<64 hex>",
    "preContractFingerprint": "<64 hex>",
    "rollbackSqlSha256": "<64 hex>"
  },
  "producer": {
    "headSha": "<40 hex>",
    "repository": "<owner/repo>",
    "runAttempt": "<positive decimal>",
    "runId": "<positive decimal>",
    "workflowPath": ".github/workflows/durable-agent-v2-development-evidence.yml"
  },
  "reports": {
    "backupSha256": "<64 hex>",
    "idempotentForwardSha256": "<64 hex>",
    "liveContractSha256": "<64 hex>",
    "rollbackRehearsalSha256": "<64 hex>"
  }
}
```

`bundleFingerprint` 是以下 canonical JSON 的 SHA-256：

```json
{
  "forwardSqlSha256": "<64 hex>",
  "migrationSourceCommit": "<40 hex>",
  "postContractFingerprint": "<64 hex>",
  "preContractFingerprint": "<64 hex>",
  "rollbackSqlSha256": "<64 hex>"
}
```

迁移资格 TTL 最大 30 天。它只允许数据库 `novelwriterdev`，且必须证明 V2 事实为零时完成 rollback rehearsal；一旦共享
开发库出现 V2 事实，不能重新用 DDL rollback 刷新资格，必须在隔离克隆库重新资格化或沿用仍有效、绑定同一迁移 bundle
的既有资格。

### 3.2 每提交候选证据

目录固定包含：

```text
candidate-evidence.json
fault-injection-report.json
resource-constrained-report.json
provider-canary-report.json
SHA256SUMS
```

汇总格式为 `inkforge-durable-agent-v2-candidate-evidence/2`，精确绑定：

```json
{
  "canaryScenarioFingerprint": "<64 hex>",
  "developmentScopeSha256": "<64 hex>",
  "executionManifestFingerprint": "<64 hex>",
  "expiresAt": "<UTC RFC3339 秒精度>",
  "format": "inkforge-durable-agent-v2-candidate-evidence/2",
  "images": {
    "agent": "sha256:<64 hex>",
    "core": "sha256:<64 hex>",
    "web": "sha256:<64 hex>"
  },
  "issuedAt": "<UTC RFC3339 秒精度>",
  "migrationQualificationSha256": "<64 hex>",
  "policies": {
    "providerMaxCompletionTokens": 1,
    "providerMaxCostMicros": 0,
    "providerMaxPromptTokens": 1,
    "providerMaxReasoningTokens": 0,
    "providerMaxTotalTokens": 1,
    "providerUsageCostPolicySha256": "<64 hex>",
    "providerUsageCostPolicyVersion": "durable-agent-v2-provider-canary-budget/1",
    "resourcePerformancePolicySha256": "<64 hex>",
    "resourcePerformancePolicyVersion": "durable-agent-v2-resource-slo/1"
  },
  "producer": {
    "headSha": "<40 hex>",
    "repository": "<owner/repo>",
    "runAttempt": "<positive decimal>",
    "runId": "<positive decimal>",
    "workflowPath": ".github/workflows/durable-agent-v2-development-evidence.yml"
  },
  "reports": {
    "faultInjectionSha256": "<64 hex>",
    "providerCanarySha256": "<64 hex>",
    "resourceConstrainedSha256": "<64 hex>"
  },
  "subjects": {
    "providerIdentitySha256": "<64 hex>",
    "resourceHostIdentitySha256": "<64 hex>"
  },
  "targetReleaseCommit": "<40 hex>"
}
```

候选 TTL 最大 24 小时，`issuedAt` 不得早于所引用迁移资格，且 `expiresAt` 不得晚于该资格。`producer.headSha` 必须等于
`targetReleaseCommit`；三个镜像 digest 必须互不相同。候选与资格的 `developmentScopeSha256` 必须相同，但 producer
run 可以不同：迁移资格是独立一次性事实，候选是当前提交的运行事实。两个 policy SHA 和五个 provider 上限都必须由
受保护 consumer 作为可信期望传入；resource host 与 provider identity SHA 同样必须作为显式 trusted subject 输入。
resource/provider 报告自报的 policy version/SHA/上限/subject 必须与汇总精确相等，不能只由报告自证，也不能用
`canaryScenarioFingerprint` 隐含替代这些绑定。

## 4. 语义报告 schema

所有报告都有以下精确 binding：`developmentScopeSha256`、`issuedAt`、`expiresAt`、`producer` 与
`sensitiveContentAbsent=true`。时间和 producer 必须与所属汇总完全相同。迁移报告另绑定 `database=novelwriterdev`、
`migrationBundleFingerprint`；候选报告另绑定 `targetReleaseCommit`、三镜像、`executionManifestFingerprint` 与
`canaryScenarioFingerprint`。

### 4.1 迁移报告

- `migration-backup-report.json`：format/reportType 固定为 `migration-backup`；要求 PostgreSQL custom dump 与 execution
  Redis RDB 均 `readable=true` 且有 64 位 SHA，`executionAofStatus=ok`，并明确
  `postgresRestoreRequiresExecutionQuarantine=true`、`status=passed`。
- `live-contract-report.json`：固定为 `live-contract`；要求 `schemaState=migrated-empty-v2`、guard 与 live contract
  fingerprint 都等于迁移 bundle 的 post contract、`structureDiffCount=0`、contract evidence SHA 存在且
  `status=passed`。
- `idempotent-forward-report.json`：固定为 `idempotent-forward`；要求两次 forward exit code 都为 0，两次 post
  fingerprint 都等于冻结 post contract、引用同一 backup report SHA、`v2FactCount=0`、`partialStateObserved=false`、
  `status=passed`。
- `rollback-rehearsal-report.json`：固定为 `rollback-rehearsal`；要求 rollback 前为 `migrated-empty-v2`、V2 事实为 0、
  rollback/reforward exit code 都为 0、rollback 后等于 pre contract、最终等于 post contract、`residueCount=0`、
  `status=passed`。

### 4.2 候选报告

- `fault-injection-report.json`：固定为 `fault-injection`；要求 happy/idempotency、SSE cursor 重连、callback 回执丢失、
  Agent journal replay、Core 重启 callback replay、execution Redis AOF 重启和 submit 前取消全部通过，取消场景
  `providerCalls=0`，重复回答/终态/TokenUsage/BillingReservation 计数均为 0。callback 丢回执必须保存脱敏
  `callbackReceiptIdentitySha256` 并证明重复回放命中同一 receipt；AOF 重启后必须由全新 Agent 进程完成 healthcheck，
  不能只看 Redis 容器 healthy。场景结束还必须同时满足 `cleanupPassed=true`、`allResourcesRemoved=true`，不能把遗留
  容器、网络、卷或密钥目录的运行标为通过。
- `resource-constrained-report.json`：固定为 `resource-constrained`；要求真实开发主机精确 2 CPU/2048 MiB、`swapMiB=0`，
  记录脱敏 `hostIdentitySha256` 与 `cgroupMode=v1|v2`，观察至少 1800 秒且至少 30 个独立样本。报告必须保存非负
  `cpuThrottledMicros` 和不超过宿主内存的 `peakRssMiB`，并证明 OOM、非预期重启、Redis eviction、quarantine event、
  pending execution、非终态 Run 与 SLO 硬失败全部为 0，provider 最大并发不超过 3。当前没有权威的统一 p95/p99
  毫秒阈值，因此禁止临时拍一个数字：必须使用 `durable-agent-v2-resource-slo/1`、受保护 consumer 传入的 policy SHA、
  `measuredLatencySummarySha256` 与 `latencySloPassed=true`。policy artifact 和完整 measured summary 须由未来 producer
  artifact/provenance 保存；本 helper 只验证其绑定与脱敏摘要。Docker Desktop 的容器 limit 或本地短测不得生成该报告。
- `provider-canary-report.json`：固定为 `provider-canary`；只接受 `mode=real`、`status=passed`、
  `providerAttempts=providerCalls=1`、一个完成 Run 和一个回答。报告以
  `durable-agent-v2-provider-canary-budget/1`、受保护 consumer 传入的 policy SHA 和 `usageCostSummarySha256` 绑定
  prompt/completion/reasoning/total token 与 cost micros 的测量值和各自上限；每个测量值必须不超过对应上限。
  `WorkflowBillingReservation` 必须恰有一条、`status=settled`、剩余预留为 0、charged micros 精确等于报告 cost 且 usage
  绑定成立；`TokenUsage` 必须恰有一条且绑定唯一，reconciliation required 为 0。completed result 必须绑定唯一回答消息，
  同一幂等请求回放后物理 provider call 不增加。重复 TokenUsage/Reservation 均为 0。报告只保存 provider identity SHA，
  不保存供应商密钥、请求、响应或正文，并显式断言三类敏感 payload 均未持久化。

仅文件名、hash 或 `status=passed` 不足；上述嵌套字段任何一个缺失、额外、类型错误或值不满足约束都失败。

## 5. 指纹分离

`developmentScopeSha256` 由下列 canonical JSON 计算：

```json
{
  "databaseIdentitySha256": "<64 hex>",
  "environment": "development",
  "executionRedisIdentitySha256": "<64 hex>",
  "ordinaryRedisIdentitySha256": "<64 hex>",
  "topologySha256": "<64 hex>"
}
```

`canaryScenarioFingerprint` 由下列 canonical JSON 计算：

```json
{
  "actorScopeSha256": "<64 hex>",
  "assertionsSha256": "<64 hex>",
  "fixtureSha256": "<64 hex>",
  "operation": "long_serial.answer_question",
  "scenarioVersion": "durable-agent-v2-real-provider-canary/1"
}
```

actor scope 仍只保存 hash。开发 scope 改变表示环境身份或拓扑改变；场景 fingerprint 改变表示测试主体、fixture、Operation
或断言改变。两者都必须重新执行候选验证，但只有迁移 bundle 或开发 scope 改变才使既有迁移资格不匹配。

## 6. 时间、来源与消费

- 时间只接受 `YYYY-MM-DDTHH:MM:SSZ`；`issuedAt < expiresAt`，签发时间不得比可信 verifier 时钟未来超过 5 分钟。
- verifier 必须在 `[issuedAt - 5 分钟, expiresAt)` 内运行；过期、未来签发或 TTL 超限均失败。
- `runId`、`runAttempt` 是无前导零的正十进制；repository、workflow path 和 head SHA 必须由 consumer 再与 GitHub API
  事实逐项比较。helper 的 `--expected-*` 是必须由受保护调用方给出的绑定，不是 artifact 自证。
- qualification 和 candidate 输出都以 canonical 汇总文件 SHA 作为 artifact identity；`SHA256SUMS` 覆盖汇总与所有
  report，按文件名排序，不能遗漏或加入额外文件。
- create 先完整读取、复验并冻结输入 report 字节，再在临时目录写出；输入在读取时是 symlink、硬链接计数不为 1、
  权限过宽、非 canonical、SHA 漂移或 schema 不符都失败。安全读取在同一已打开 fd 前后精确比较 device、inode、size、
  mode、`mtime_ns`、`ctime_ns` 与 `nlink`，任一读取中漂移都失败。最终目录已存在时绝不覆盖。

## 7. 安全边界

helper 是纯离线工具：不访问网络、不读取环境 secret、不连接 PostgreSQL/Redis、不调用 Docker 或模型，不执行迁移，
也不上传 artifact。它拒绝常见 PEM、bearer/JWT、带凭据 URL、password/token/api-key/cookie 片段；更重要的是 exact
schema 根本没有正文或凭据字段。

构建器不能把手写的 `passed` 报告变成真实证据。后续 producer 至少还需：

1. 受保护 `development` environment 和独立、最小权限、自托管 runner；
2. 在可信 source guard 后构建不可变三镜像并保存镜像/源码 provenance；
3. 一次性隔离库 migration qualification producer；
4. 真实 `novelwriterdev` route-off、同形 2 CPU/2 GiB 整机与完整故障矩阵 driver；
5. 通过公共 CLI 在隔离测试账号/小说上执行真实供应商 canary，密钥只留在开发主机；
6. GitHub run/repository/workflow/head SHA/runAttempt、artifact retention 和 API provenance consumer；
7. route-off 清理与开发 scope 漂移检测。

在这些外部事实全部实现并复验前，现有开发 Workflow 和生产发布必须继续失败关闭。

## 8. CLI 与 Skill 影响

本阶段不新增、不删除、不改名任何 InkForge Java CLI 命令、参数、JSONL/SSE 语义或 exit code；新增的 Python helper
只是仓库内开发证据构建/复验工具，不得加入生产 operator Skill 的业务命令 wrapper，也不能从 Skill 绕过受保护
Workflow。未来真实 provider canary 只能复用现有公共 CLI 流程，并遵守
`docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md` 冻结的命令映射、TTY 凭据输入和敏感信息边界。若公共
CLI 以后发生变化，必须先更新该 operator Skill 规格和安装 Skill，再生成可消费的候选证据。

## 9. 本阶段验收

- 独立 helper 可创建并复验 qualification/candidate bundle，输出目录使用 no-replace + fsync；
- 任意 `test-report/1`、额外字段、错误 commit/image/source/run/attempt/policy、错误 qualification 引用、过期证据、
  敏感值、symlink、hardlink、权限过宽、非 canonical JSON、checksum、报告字节或读取中 metadata 漂移全部失败；
- qualification 可被多个不同 candidate run 引用，但开发 scope 或迁移 bundle 不同则失败；
- candidate scope 与 canary scenario 被独立校验，不能互换；
- 专用 pytest、Ruff、Mypy、`py_compile` 与 `git diff --check` 通过；
- 不修改或启用现有 development/production Workflow，不访问真实数据库、供应商或网络。
