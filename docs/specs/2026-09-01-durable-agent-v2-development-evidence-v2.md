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
9. 当前 `.github/workflows/durable-agent-v2-development-evidence.yml` 继续在上传 artifact 前硬失败；现有
   production release Workflow 已接入仓内 fail-closed v2 预验 consumer，但由于没有可信 producer artifact，真实发布必然
   在 acquisition 阶段停止。该仓内 consumer 不构成仓外独立授权根，也不降低 v1 verifier 的任何失败条件。
10. 可预先冻结的 environment policy 与当前 run 才会产生的 artifact identity 必须分层。禁止把
    image provenance、control bundle、candidate bundle 或三镜像的当前 run SHA/digest 预填到
    environment，更禁止测试在产出 artifact 后反向改写“可信 expected”。

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
  容器、网络、卷或密钥目录的运行标为通过；远程开发环境还必须独立满足 `routeOffCleanupPassed=true`，证明 fresh V2
  路由已经关闭并完成具名 cleanup，而不是只删除本地 Compose 资源。
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
- 当前 run 的 image provenance、control bundle 与 candidate bundle SHA 在各自产出后由严格 verifier 从
  canonical 字节和 checksum 现场计算，再在同 run 内作为下一阶段的精确 binding。它们不是预置
  policy；未来上传后还必须由独立 consumer 将这些计算值与 artifact service 的 digest/provenance 比较。
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

仓内 development producer helper 的非公共 CLI 在本轮有明确变更：新增
`verify-checkout-bindings`；`create-images`/`verify-images` 删除可自报的
`--source-tree-sha256`/`--build-definition-sha256`，改为必填 `--repository-root`、
`--source-tree-manifest`、`--expected-source-tree-sha256` 和
`--expected-build-definition-sha256`；`verify-prerequisites` 同样必须接收 repository/source manifest/
source expected，且它现场计算 image/control/candidate SHA 并输出 canonical 动态 binding。这些命令仍只是
仓内证据工具，不得加入 operator Skill wrapper；因此本轮无需改动现有生产 Skill 命令映射。
该 canonical binding 精确包含 `sourceTreeSha256`、`buildDefinitionSha256`、三镜像 digest、
`imageProvenanceSha256`、`controlBundleSha256` 与 `candidateEvidenceSha256`；它是同一验证调用的计算结果，
不得被复制回 environment 充当下一个候选的静态 policy。

## 9. 本阶段验收

- 独立 helper 可创建并复验 qualification/candidate bundle，输出目录使用 no-replace + fsync；
- 任意 `test-report/1`、额外字段、错误 commit/image/source/run/attempt/policy、错误 qualification 引用、过期证据、
  敏感值、symlink、hardlink、权限过宽、非 canonical JSON、checksum、报告字节或读取中 metadata 漂移全部失败；
- qualification 可被多个不同 candidate run 引用，但开发 scope 或迁移 bundle 不同则失败；
- candidate scope 与 canary scenario 被独立校验，不能互换；
- environment 只包含可预先冻结的静态 policy/subject/qualification/build expected，拒绝当前 run 的
  image/control/candidate SHA 和三镜像 digest；全量 verifier 在语义验证过程中现场计算动态 binding；
- image source/build 绑定由 checkout `git ls-tree` manifest、独立 `sha256sum` expected 和冻结 build 文件字节
  重算，旧自报参数、零 expected、manifest 漂移或 image JSON 重算后篡改都失败；
- 专用 pytest、Ruff、Mypy、`py_compile` 与 `git diff --check` 通过；
- v2 artifact helper 本身不访问真实数据库、供应商或网络；后续 producer 框架即使接入 development Workflow，也必须
  在缺外部能力时保持失败关闭，且不得放宽 production Workflow 的固定停止点或把仓内预验 consumer 冒充仓外授权根。

## 10. Development producer 可信骨架

下一阶段只把 `.github/workflows/durable-agent-v2-development-evidence.yml` 从单 job 固定退出改为三段 producer 骨架；
它仍不产生可供生产消费的 qualification/candidate artifact：

```text
trusted_context
  -> offline_validation
       -> canonical blocked plan（仅本 job 临时诊断）
  -> development_evidence(environment=development)
       -> 带只读 audit token 的固定 GitHub API 采集
       -> 无令牌 environment policy 语义复验
       -> checkout/source/build definition 确定性复验
       -> fixed real-driver-unavailable failure

未来解锁远程能力后才可追加：
  qualification acquisition -> image build/provenance -> control bundle
  -> remote candidate reports -> candidate bundle -> current-run semantic verify
  -> same-run artifact upload
```

### 10.1 可信 context 与并发

Workflow 顶层 concurrency 固定为 `durable-agent-v2-development`，`cancel-in-progress=false`；不得按 SHA 分组，避免两个
候选同时操作同一个开发环境。第一 job 的第一 step 必须位于任何 checkout、environment、secret 或仓库脚本之前，且只用
GitHub 可信 context 和 shell builtin 证明：

- `event=workflow_dispatch`、`ref=refs/heads/main`；
- 输入 `target_release_commit` 精确等于 `github.sha`；
- `github.run_attempt=1`，禁止 rerun 复用旧审批、旧 artifact 或外部状态；
- commit 必须是 40 位小写 hex，run ID/attempt 必须是无前导零正十进制。

恶意候选即使修改本 Workflow 或 producer helper，也只能在上述可信 step 之后被 checkout。后续 checkout 必须精确
`ref=${{ github.sha }}` 且 `persist-credentials=false`；所有 action 都使用下列精确 owner/repository + 40 位
commit SHA 白名单：

- `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683`；
- `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065`；
- `astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78`；
- `actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020`；
- `actions/setup-java@c5195efecf7bdfc987ee8bae7a71cb8b11521c00`。

禁止其他 action、`@v4`、`@main` 或 tag。

**外部 P0/P1 信任缺口：**上述 step 和 helper 仍由当前候选仓库提供，因此这个 Workflow 不能独立
证明自己未被候选篡改，也不能把 GitHub `environment` 审批当成不可变 controller。未来必须由独立、
不可变、不从候选 checkout 执行的 controller，结合对精确 repository/workflow/ref/SHA/environment 声明的 OIDC
主体和最小权限 artifact API 完成 acquisition/consumer。本轮只封闭仓内可修缺口，必须继续固定失败，
不得宣称这个根信任问题已解决或生成可发布证据。

### 10.2 离线验证 job

`offline_validation` 不声明 environment、不读取 secret、不连接 InkForge 远程开发/生产服务。它固定 Python、uv、Node 与
Java action commit，执行当前候选的 Python、Java、Web、API、架构与发布控制面全量离线门禁。现有本机 Fake provider/
Compose fault evidence 只能标记为 `local-fake-prerequisite-only`：它可以阻断 producer，但不能生成 `mode=real`、真实
2C2G 或远程 cleanup 结论。

该 job 的成功只通过 GitHub `needs` 控制流传递；当前框架不上传中间 artifact，也不把 stdout JSON 当跨 job 信任根。
blocked remote plan 只在该 job 的 `$RUNNER_TEMP` 中生成并立即复验，随后随 runner 销毁；protected job 不读取它。

### 10.3 受保护 development job

`development_evidence` 必须声明 `environment: development`，并在任何远程 SSH/provider 凭据、远程主机连接或
artifact upload 前完成：

1. 通过独立 step 调用固定 `gh api` 读取 development environment、branch policies、secret inventory 与
   variables；该 step 可仅注入独立只读 `GH_ENVIRONMENT_POLICY_AUDIT_TOKEN`，不得运行 Python、仓库
   script 或 helper。随后的独立无令牌 step 才调用候选 helper 语义复验：required reviewer 唯一且
   非空、禁止自审、自定义部署分支精确只有 `main`、分页计数完整；secret inventory 必须
   精确只有该 audit token，候选 helper step 全部不得注入 `GH_TOKEN` 或任何 `secrets.*`。
2. 在精确 checkout 上先写入 NUL 终止的 `target <40hex>` 头，再用固定
   `git ls-tree -rz --full-tree <target>` 追加 NUL 分隔的 tree 记录；helper
   必须解析 canonical mode/type/object/path、拒绝 symlink/submodule/重复/乱序/绝对或父级路径；固定 shell 用
   `sha256sum` 对该 manifest 字节独立计算 expected，helper 重算后必须精确相等，该值即
   `sourceTreeSha256`。manifest 的 Git 查询对象与 image 的 `targetReleaseCommit` 都是同一个可信 target；
   两者分字段绑定，不允许 image 自报替换。`buildDefinitionSha256` 必须从冻结的
   三个 Dockerfile、Compose 构建定义、dockerignore 和对应 lock/build manifest 文件的实际字节重算，并与
   environment 中独立、非零的 build-definition expected 比较。两个值都不得从 image JSON 自报接受。

build definition v1 的精确文件白名单为：

- `.dockerignore`、`.python-version`、`.mvn/wrapper/maven-wrapper.properties`、`mvnw`；
- `infra/compose.yaml`、`infra/docker/agent-service.Dockerfile`、
  `infra/docker/core-api.Dockerfile`、`infra/docker/web.Dockerfile`、
  `infra/docker/inkforge-schema-guard`；
- 根 `package.json`、`package-lock.json`、`pom.xml`、`pyproject.toml`、`uv.lock`；
- `apps/web/package.json`、`packages/api-client/package.json`；
- `apps/core-api-java/pom.xml`、`packages/service-auth-java/pom.xml`、
  `packages/service-contracts-java/pom.xml`、`tools/inkforge-cli-java/pom.xml`；
- `apps/agent-service/pyproject.toml`、`packages/service-auth/pyproject.toml`、
  `packages/service-contracts/pyproject.toml`。

白名单路径和每个文件字节 SHA 进入 canonical JSON，其整体 SHA-256 是
`buildDefinitionSha256`。源文件缺失、symlink、非普通文件、硬链接、超限或读取中 metadata 漂移都失败。
3. 未来有真实 driver 后，复验 content-addressed development image provenance：target commit、当前
   repository/run/runAttempt、三镜像不可变 digest、execution fingerprint、重算的 source tree/build definition SHA 和
   bundle checksum 全部匹配。image create/verify 必须接收独立 source manifest/expected 和 repository root/
   build-definition expected，不再接受 `--source-tree-sha256` 或 `--build-definition-sha256` 自报参数。
4. 使用现有 control-bundle verifier 复验完整 payload、workflow/target commit 和 producer run/attempt；当前 run 的
   control SHA 由 verifier 现场计算，不从 environment 预置。
5. 使用本规格 v2 qualification verifier 复验一次迁移资格。`qualification.producer.repository` 必须先
   精确等于受保护调用方传入的当前 repository，run provenance verifier 的 expected repository 也必须
   使用该可信参数，不得从 artifact 自报回填；另外固定 workflow path、main head SHA、runAttempt=1 与
   success conclusion。qualification 的 head 可以是仍有效的旧 main 资格提交，但必须由该可信仓库的
   dispatch/main/success run JSON 证明。
6. 完整消费 candidate bundle，而不是只格式化检查 hash：当前 run 的 candidate 汇总 SHA 由
   verifier 现场计算，另外精确验证 target commit/
   repository/workflow/run ID/runAttempt=1、`developmentScopeSha256`、`canaryScenarioFingerprint`、
   execution fingerprint、三镜像 digest、resource/provider policy SHA 与 host/provider identity SHA、五个 token/cost
   上限、qualification SHA 均须精确等于 environment variables 的受保护期望。三份报告必须由 v2
   semantic validator 完整验证，包括 fault cleanup、`allResourcesRemoved=true` 与
   `routeOffCleanupPassed=true`。candidate run JSON 还必须复验当前 repository、固定 workflow path、
   当前 head SHA/run ID、runAttempt=1 和 dispatch/main，不允许候选或 run JSON 自行改写 expected。

qualification 与 candidate 必须使用不同的生命周期语义：qualification 是以前已完成的一次性资格，因此
其 run API 响应必须为 `status=completed` 且 `conclusion=success`；candidate 就是当前 producer run 内正在
生成和复验的证据，因此当前阶段只接受 `status=in_progress` 且 `conclusion=null`。把当前 candidate
run 声称为 `completed/success` 是不可能的生命周期混用，必须失败，不得为了通过夹具而伪造已完成 run。

未来只能由同一 producer run 内位于所有构建、语义复验与远程 cleanup 之后的后续 job 上传 candidate
artifact；当前 development Workflow 没有该 job，也没有任何 upload action。现有 release Workflow 的仓内预验
consumer 会在 producer run 结束后重新从 GitHub API 取得 run 事实，并以 `completed/success` 作为继续执行的必要
条件；独立、不可变的仓外授权 consumer 仍未实现，未来还必须重复该复验并绑定 artifact service provenance。
任何 consumer 都不得被 current-run verifier 的 `in_progress/null` 语义放宽。

environment variables 名称集合是精确静态白名单：producer policy version；既有 migration qualification
SHA；development scope、canary scenario、execution manifest、build definition；resource policy/host identity；
provider policy/identity；provider prompt/completion/reasoning/total token 和 cost 上限。当前 run 的 image/
control/candidate bundle SHA 和 web/core/agent digest 精确禁止出现。缺少、额外、
重复、零占位、非 canonical 整数或 hash 复用都失败。

上述 artifact 必须来自未来受保护 acquisition step；当前 Workflow 不接受操作者提供本地路径、任意 JSON、摘要或
手写 `passed`。当前流程在完成静态 policy 和 checkout/source/build definition 复验后，立即调用固定
`assert-remote-capabilities-unavailable`；它不先要求尚未可能产生的 image/control/candidate SHA，也不放置
不可达的后续验证 step。即使专用测试在 Workflow 外构造完整合法的 images/control/
qualification/candidate/run provenance 夹具并验证动态串联，Workflow 的实际固定 unavailable action 仍必须
稳定返回非零，且 SSH/SCP/artifact upload 动作为零。

### 10.4 Canonical blocked remote plan

producer helper 只允许离线生成
`inkforge-durable-agent-v2-development-remote-plan/1` canonical blocked plan。它精确绑定 repository、target commit、
run ID/attempt，并固定：

```json
{
  "decision": "blocked",
  "localFaultEvidenceClass": "local-fake-prerequisite-only",
  "reasonCodes": [
    "provider-identity-unavailable",
    "remote-driver-unavailable",
    "resource-host-unavailable",
    "route-off-cleanup-unavailable"
  ]
}
```

plan 使用 0700/0600、canonical JSON、SHA256SUMS、fsync 与 no-replace；helper 不包含 socket、HTTP、SSH、SCP、Docker、
数据库或模型调用。任何 `providerMode=fake|real`、`decision=ready`、缺 cleanup reason、额外字段或摘要替换都失败。blocked
plan 只供 offline job 临时诊断且不上传，不能成为 qualification/candidate producer。protected job 在 provenance 门禁后
调用不读取 plan 的固定 unavailable action；即使未来补齐三类 artifact，该 action 仍返回非零，直到真实外部能力另立
规格实现。

### 10.5 当前固定停止点与攻击测试

Workflow 当前不得包含 SSH/SCP、远程 driver secret、`actions/upload-artifact` 或最终 artifact 名。即使 environment policy
合法且 checkout/source/build 通过，Workflow 也必须立即在真实远程能力停止点失败，不先索取不存在的
dynamic artifact。独立调用的未来全量 verifier 在缺 image/control/qualification/candidate/provenance 任一项时
必须在远程动作前失败；即使测试夹具补齐所有这些前提，Workflow 实际最后 step 仍因
remote driver、2C2G、provider identity 与 route-off cleanup 缺失而固定失败。

专用测试至少证明：恶意 commit/非 main/非 dispatch/runAttempt>1 在 checkout 前失败；任一 action 不在
精确 owner/repository+SHA 白名单失败；缺 environment policy、images、control bundle、qualification/candidate 或任一
producer provenance 失败；qualification 与 run JSON 同步伪造成另一 repository 仍失败；本地 Fake evidence
冒充 real、缺 cleanup、修改 blocked plan 都失败；完整合法的 candidate current-run 仅在
`in_progress/null` 时可通过独立 prerequisite verifier，同一 current run 改成 `completed/success` 必须被
阶段校验拒绝；测试另外直接执行 Workflow YAML 的实际固定停止 step，证明它与未来动态夹具无关地保持
非零；所有攻击路径的 SSH 与 artifact upload 调用计数为 0。

公共 CLI canary 仍只引用
`docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md`，本 producer 框架不新增业务命令，也不把发布控制面加入
Skill wrapper。只有外部 topology、受保护 artifact acquisition、真实 remote driver/host/provider 身份和 route-off
cleanup 都另行实现并验收后，才能修改固定停止点。

### 10.6 已知 P2：证据目录父级竞态

当前 v2 安全读取已在每个打开文件的 fd 上前后复验 device/inode/size/mode/mtime/ctime/nlink，并拒绝
symlink 与 hardlink；但尚未把整个 evidence 目录锚定为固定 dir fd，也未用 `openat` 逐个打开成员。
因此“外部主体在不同成员打开之间替换整个父目录”仍是未解 P2；未来消费真实 artifact 前必须增加
dir-fd/`openat` 锚定和父目录 identity 前后比较测试。本轮不扩大到该底层改造，且 Workflow 仍在任何
qualification/candidate artifact 上传之前失败关闭。
