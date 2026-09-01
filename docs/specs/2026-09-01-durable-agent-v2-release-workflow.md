# Durable Agent V2 受保护发布、开发证据与回滚 Workflow

状态：实施中；当前仓库没有可安全自动化的真实模型供应商身份、受保护成功 release receipt 与新 SSH
身份轮换证据，因此生产发布框架必须保持 fail closed

日期：2026-09-01

## 1. 背景

Durable Agent V2 的镜像、数据库迁移、结构契约和 rollout gate 已有独立工具，但生产发布不能把这些工具按人工顺序
拼接后就宣称安全。发布控制面必须同时解决五类风险：候选提交修改自身门禁、开发验证在生产审批后补做、旧发布
artifact 被当前 `main` 错误解释、两个发布会话交错，以及 canary allowlist 在部署过程中漂移。

本文定义新的独立发布体系。它替代 `build.yml` 的 `main` 自动部署；保留普通 CI，但生产部署、迁移、rollback 和锁清理
只能走受保护 Workflow。本文只定义和实现控制面，不表示已连接开发/生产服务器、已取得真实供应商证据、已迁移数据库
或已开放 V2 路由。

## 2. 不变量

1. `source` 的第一条命令在任何 checkout 和仓库脚本之前，只使用 GitHub 可信 context 校验：事件必须是
   `workflow_dispatch`、`github.ref` 必须是 `refs/heads/main`、输入的 workflow trusted commit 必须精确等于
   `github.sha`。之后 workflow/control-plane checkout 固定为 `${{ github.sha }}`，不能 checkout 用户给出的任意 SHA。
2. `production` environment 必须由 GitHub API 外部事实证明：至少一名 required reviewer、禁止自审，并且自定义部署
   分支策略精确只允许 `main`。API 使用独立最小权限 audit token；token 只进入环境变量，不进入 argv、日志或 artifact。
   API 不可达、权限不足、分页不完整或字段漂移一律失败。
3. 本地候选验证、真实 remote development 和 production approval 是三个独立阶段。生产 job 绝不先部署生产再补开发库
   迁移、故障注入或真实供应商 canary。
4. route-off 与 allowlist 发布必须在任何 SSH 前下载并复验一个独立 GitHub run 产生的 canonical development evidence
   artifact。`providerCanary.status=pending` 允许保存为开发记录，但永远不能满足生产 verifier。
5. 所有声明 `environment: production` 或会触发生产动作的 job 使用同一并发组 `production`，且
   `cancel-in-progress: false`。服务器还持有独立事务锁，GitHub concurrency 不能代替服务器锁。
6. `scripts/deploy-production.sh` 强制要求 release manifest、可信 dispatch context 和匹配的服务器事务锁；不保留无
   manifest 的兼容部署路径。
7. fingerprint 切换与 rollback 必须收到可复验的 `verifiedDrain` canonical 证据。联合 drain 当前由独立规格修复；在其
   verifier 未通过或证据缺失时，本发布体系保持 fail closed，本文不宣称 P1 已完成。
8. 服务器端执行的发布 driver、联合 drain verifier、迁移 helper、rollout gate、镜像 verifier、Compose 定义与固定
   SQL/contract 必须来自 workflow 在事务锁前上传并复验的不可变 control bundle。`APP_DIR` checkout 只承载目标应用
   源码和 `.env`，不能提供发布控制脚本；checkout/reset 前后均不得改变本次控制根。
9. rollback 来源只能来自上一次受保护成功 postflight 封存并被 `current` 指针引用的不可变 release receipt。Git
   `HEAD`、镜像 tag、任意 40 位输入或旧 manifest 自报都不能建立 rollback provenance。
10. 受保护 Workflow 在服务器事务锁内完成 `allowlist -> route-off`、`route-off -> allowlist` 和 rollback 的配置转换、
    Core 重启及运行态复验。不得要求操作者预先修改 `.env` 或手工重启。
11. release lock 只序列化发布控制面，不是 PostgreSQL、普通 Redis 或 execution Redis 的基础设施屏障。初始
    `verifiedDrain` 只能作为事务起点证据；每个破坏性边界必须在执行动作的同一可信服务器进程中紧邻动作前重采 live
    identity 与 zero-drain，并一次性消费绑定 `boundary/sequence` 的证据。
12. allowlist 的唯一提交点是 `current` receipt 指针完成 `os.replace`、receipt 根目录 fsync，并从磁盘重新读取后精确匹配
    本 lock/run/manifest/control/runtime。提交点前任何失败都必须关闭 route；提交点后失败不得关闭已提交 allowlist，
    只能保留具名锁等待 finalize/cleanup。

## 3. 非目标

- 不在 Workflow 中创建、修改或回显 `.env`、数据库密码、模型密钥、短信密钥、生产确认令牌正文或用户密码。
- 不接受任意 SQL、任意数据库名、任意镜像仓库、`latest` 或可改指 tag 作为部署权威。
- 不自动打开 `route=all`，不把 pending provider 记录解释为 canary 通过，也不自动覆盖 canonical schema contract。
- 不从备份执行覆盖恢复，不清除 execution quarantine，不删除 V1/V2 任务、作品数据、镜像或卷。
- 不在本地测试中联网、部署、读取真实 secret 或操作 `novelwriterdev`/`novelwriter`。

## 4. Workflow 信任链

发布 DAG 固定为：

```text
trusted-context-guard
  -> checkout(github.sha)
  -> external-environment-policy
  -> candidate-validation
  -> development-evidence-download-and-verify
  -> production(environment approval, concurrency=production)
```

`trusted-context-guard` 必须是 `source` 的第一个 step。它不能执行候选仓库中的脚本。恶意候选提交即使把
`scripts/durable-agent-v2-release.sh` 改成永远成功，也不能让非 main、非 dispatch 或 input/SHA 不一致的运行到达
checkout。

环境策略由 workflow 用 `GH_ENVIRONMENT_POLICY_AUDIT_TOKEN` 调用 GitHub REST API 读取：

- `GET /repos/{owner}/{repo}/environments/production`；
- `GET /repos/{owner}/{repo}/environments/production/deployment-branch-policies?per_page=100`。
- `GET /repos/{owner}/{repo}/environments/production/secrets?per_page=100`；
- `GET /repos/{owner}/{repo}/environments/production/variables?per_page=100`。

本地 verifier 消费 API 返回的四个只读 JSON 文件。production environment 必须启用
`custom_branch_policies=true`、`protected_branches=false`，branch policy 列表只能有精确名称 `main`，并存在至少一名
required reviewer 且 `prevent_self_review=true`。仓库内的变量、manifest、候选脚本或普通 `GITHUB_TOKEN` 布尔输入不能
自证这些设置。仓库外还必须保存 environment 配置截图或 API 响应摘要作为上线审批证据；响应本身不得混入 token。

同一外部校验还必须证明旧 `SERVER_SSH_KEY` 已从 `production` environment 删除，新专用
`DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY` 已存在，并且以下三个 environment variable 均为 64 位小写 SHA-256：

- `DURABLE_AGENT_V2_RELEASE_OLD_KEY_REVOCATION_EVIDENCE_SHA256`：服务器 `authorized_keys` 已撤销旧 key 的离线证据；
- `DURABLE_AGENT_V2_RELEASE_FORCED_COMMAND_EVIDENCE_SHA256`：新 key 使用 forced-command 的离线证据；
- `DURABLE_AGENT_V2_RELEASE_MINIMUM_PERMISSION_EVIDENCE_SHA256`：部署账号/命令白名单/文件权限最小化证据。

任一 API 响应、分页、secret 名或上述外部证据 hash 缺失时，所有 job 都必须在准备 SSH 私钥、`ssh`、`scp`、Compose
或 DDL 之前失败。删除仓库当前 Workflow 中的旧 secret 引用不能阻止历史 run rerun；GitHub 侧删除旧 secret 与服务器
侧撤销旧公钥两项必须同时完成，才算关闭历史 Workflow 的生产通道。

## 4.1 不可变 control bundle

生产 job 在取得事务锁之前，从 `workflowTrustedCommit` checkout 组装精确白名单 control bundle。bundle 至少包含当前
release driver、deploy driver、联合 drain verifier、迁移/rollout helper、镜像 verifier、Compose 定义、固定 SQL 与
contract；每个相对路径都写入 canonical `SHA256SUMS`，元数据绑定：

```text
format=inkforge-durable-agent-v2-control-bundle/1
workflowTrustedCommit=<40 hex>
targetReleaseCommit=<40 hex>
producerRunId=<decimal>
producerRunAttempt=<decimal>
filesSha256=<SHA256SUMS 的 SHA-256>
```

上传只写服务器 `.partial` 目录；当前 trusted uploader 先校验内嵌 verifier 的 SHA，再由 `.partial` 内已复验 verifier
检查精确文件白名单、普通文件、0700/0600 权限、全部 SHA 和元数据，并通过 `renameat2(RENAME_NOREPLACE)`（macOS
构建侧为 `renamex_np(RENAME_EXCL)`）原子发布为
`${APP_DIR}/.durable-agent-v2-control-bundles/<workflowTrustedCommit>/<bundleSha256>`。既有同名 bundle 只能逐字节复验，
不能覆盖。事务 owner、release manifest、verifiedDrain 与 release receipt 都冻结同一 bundle SHA。后续远程命令直接执行
该目录内 driver；即使应用 bundle 随后 reset `APP_DIR`，也不能改写控制逻辑。rollback 可 checkout 旧应用 bundle，但
rollback preflight、配置转换、drain、Compose 切换、postflight 和 receipt 只能运行当前 trusted control bundle。

## 5. Development evidence

artifact 固定包含 `development-evidence.json` 和单行 `SHA256SUMS`，格式为
`inkforge-durable-agent-v2-development-evidence/1`。目录权限为 0700、文件为 0600、UTF-8 canonical JSON、禁止重复
key/浮点/未知字段/symlink，发布时还必须匹配 dispatch 输入的 artifact SHA-256 与 producer GitHub run ID。

同一 producer run 还必须提供不可变 `durable-agent-v2-development-reports` artifact，精确包含 migration backup、live
contract、两次 forward、rollback rehearsal、fault injection、2C2G resource-constrained 与 real provider canary 七份
不含敏感正文的报告及其 `SHA256SUMS`。production verifier 必须实际下载这些文件并逐字节计算 SHA，与下列 evidence
JSON 引用逐项相等；只提交 hash 而报告缺失同样失败。

冻结字段至少包括：

```json
{
  "canaryScopeSha256": "<64 hex>",
  "composeValidation": {
    "faultInjectionReportSha256": "<64 hex>",
    "resourceConstrainedReportSha256": "<64 hex>"
  },
  "developmentMigration": {
    "backupEvidenceSha256": "<64 hex>",
    "database": "novelwriterdev",
    "idempotentForwardReportSha256": "<64 hex>",
    "liveContractEvidenceSha256": "<64 hex>",
    "rollbackRehearsalReportSha256": "<64 hex>"
  },
  "executionManifestFingerprint": "<64 hex>",
  "format": "inkforge-durable-agent-v2-development-evidence/1",
  "images": {
    "agent": "sha256:<64 hex>",
    "core": "sha256:<64 hex>",
    "web": "sha256:<64 hex>"
  },
  "producerRunId": "<decimal GitHub run ID>",
  "providerCanary": {
    "mode": "real|unavailable",
    "reportSha256": "<64 hex>|null",
    "status": "passed|pending"
  },
  "targetReleaseCommit": "<40 hex>"
}
```

普通 schema verifier 可接受 `pending + unavailable + null`，以便开发阶段诚实冻结尚未完成的记录；production verifier
只接受 `passed + real + 64 位 report SHA`。生产 verifier 还精确比较 target commit、三个目标镜像 digest、execution
fingerprint 与 canary scope hash。缺 artifact、run ID 不同、artifact SHA 不同、任一开发证据 hash 缺失或 provider
pending，production job 均不能装配，且不得准备 SSH。

真实 development evidence 的 producer 必须是另一个声明 `environment: development` 的受保护 job；不得在
production-approved job 中生成。consumer 还要通过 GitHub Actions API 复验 producer run 的 ID、repository、固定
workflow path、main head SHA、dispatch 事件和 success conclusion，不能只相信 evidence JSON 自报的 run ID。当前
`.github/workflows/durable-agent-v2-development-evidence.yml` 是显式 fail-closed 骨架：仓库尚无安全的真实 provider 身份
和完整 producer，因此只能由离线工具生成/保留 pending 记录，不能上传可供生产使用的 passed artifact。

## 6. Canonical release manifest v3 与 artifact provenance

release manifest 格式升级为 `inkforge-durable-agent-v2-release/3`。它分离三个曾被错误合并的提交：

- `workflowTrustedCommit`：生成 artifact 时承载受保护 workflow 的 main HEAD；
- `targetReleaseCommit`：目标镜像、CLI、SQL、contract 与 execution assets 所属提交；新发布时与 trusted commit 相同；
- `rollbackSourceReleaseCommit`：切换前正在运行且作为 rollback 镜像来源的发布提交。

固定结构为：

```json
{
  "canaryScopeSha256": "<64 hex>",
  "cliCommit": "<40 hex>",
  "controlBundleSha256": "<64 hex>",
  "developmentEvidenceSha256": "<64 hex>",
  "executionManifestFingerprints": {
    "rollback": "<64 hex>",
    "source": "<64 hex>",
    "target": "<64 hex>"
  },
  "format": "inkforge-durable-agent-v2-release/3",
  "images": {
    "rollback": {"agent": "sha256:<64 hex>", "core": "sha256:<64 hex>", "web": "sha256:<64 hex>"},
    "target": {"agent": "sha256:<64 hex>", "core": "sha256:<64 hex>", "web": "sha256:<64 hex>"}
  },
  "migration": {
    "forwardSqlSha256": "<64 hex>",
    "postContractFingerprint": "<64 hex>",
    "preContractFingerprint": "<64 hex>",
    "rollbackSqlSha256": "<64 hex>"
  },
  "rollbackSourceReleaseCommit": "<40 hex>",
  "rollbackSourceReceiptSha256": "<64 hex>",
  "routeMode": "off|allowlist",
  "producer": {
    "repository": "<owner/repo>",
    "runAttempt": "<decimal>",
    "runId": "<decimal>",
    "workflowPath": ".github/workflows/durable-agent-v2-release.yml"
  },
  "targetReleaseCommit": "<40 hex>",
  "workflowTrustedCommit": "<40 hex>"
}
```

新发布要求 `workflowTrustedCommit == targetReleaseCommit == cliCommit`。`source` 来自 target commit 的 execution
manifest；`target == source`。allowlist 还要求 `rollback == source`。所有 digest/fingerprint/SHA 使用小写十六进制。

rollback 复验分两步：先只依赖 artifact 自身 SHA 做 root-independent canonical 校验，从 manifest 读取它自己的
`targetReleaseCommit` 与 `rollbackSourceReleaseCommit`；再 checkout manifest 的 target commit，只读复验该提交的 SQL、
contract 与 execution facts。当前 main 仅提供 workflow 控制逻辑，不能覆盖旧 artifact 的事实。因此 main 前进后仍能按
旧 artifact 自身 commit 与 artifact SHA 回滚，且 rollback 部署源码绑定 `rollbackSourceReleaseCommit`，不是当前 main。

第三步必须通过 GitHub Actions API 复验输入 run ID 与 manifest `producer.runId` 相同，producer repository、固定
workflow path、`head_branch=main`、`event=workflow_dispatch`、`status=completed`、`conclusion=success`、
`head_sha=manifest.workflowTrustedCommit` 和 run attempt 全部匹配。只有在这三步完成后 production job 才可读取新专用
SSH secret。main 前进不会使合法旧 artifact 失效，因为 provenance 比较的是旧 artifact 自身 trusted commit；但任意
复制 JSON、其他 Workflow artifact、失败/取消 run 或 feature branch run 都不能回滚。

## 6.1 不可变 release receipt

服务器维护私有 0700 根目录 `${APP_DIR}/.durable-agent-v2-release-receipts`。每次全部 runtime/contract/drain postflight
通过后，当前 trusted control bundle 在事务锁内创建只读 receipt，精确绑定：

- `activeReleaseCommit`、三服务实际不可变 image ID 与 execution manifest fingerprint；
- 最终 route/schemaReady/V1 fresh-start/scope、Core 容器 ID，以及 verifiedDrain binding SHA；后者继续冻结 PostgreSQL
  身份、两个 Redis index/runtime topology、Core runtime 与 helper/verifier SHA；
- release manifest SHA、control bundle SHA、workflow/target commit、run/attempt 与 lock ID；
- 前一 receipt SHA（形成只增不改的发布链）。

receipt 目录以 canonical JSON SHA 命名，0700/0600、no-replace 发布；`current` 是只包含该 SHA 的 0600 普通文件，通过
同目录原子 replace 更新。`begin-snapshot` 必须先复验 current 指向的不可变 receipt，再把其 image IDs、fingerprint 与
正在运行容器逐项比较；全部相等后，manifest 的 `rollbackSourceReleaseCommit` 与
`rollbackSourceReceiptSha256` 才能从 receipt 的 `activeReleaseCommit` 和 SHA 生成。缺 current/receipt、receipt 被改、
运行镜像漂移或 active commit 无法对应时停止；不得回退到 `git rev-parse HEAD`。

rollback 的 `begin-rollback` 还必须证明 `current` receipt 的 `activeReleaseCommit` 与 manifest target commit 相同、其
`manifestSha256` 等于输入旧 manifest SHA，且当前运行三镜像等于 manifest `images.target`；同时 manifest 冻结的
`rollbackSourceReceiptSha256` 必须存在，其 active commit 与三镜像必须逐项等于 manifest 的 rollback source/
`images.rollback`，并精确等于 current receipt 的 `previousReceiptSha256`。旧 manifest 的
`rollbackSourceReleaseCommit` 只决定应用 bundle checkout；
rollback 控制仍来自当前 control bundle。rollback 成功也写新 receipt，把 active release 记录为旧 manifest 的
rollback source commit 与 `images.rollback`，从而让下一次发布继续拥有可证明起点。

仓内流程不提供无来源的 genesis receipt。首次切入本协议前，必须由仓外具名 bootstrap 证明并安装一个受保护成功
receipt，且撤销旧 SSH key；若 `current` 缺失，`begin-snapshot` 稳定阻断。类似地，若当前生产 Core 镜像尚不包含
可复验的 V1 fresh-start gate，脚本不能凭空关闭旧入口，生产迁移继续阻断；不得用手写 receipt、裸 Git HEAD、人工先改
`.env` 或重启来冒充上述前提。

### 6.2 receipt prepare、commit point、allowlist lease 与恢复判定

receipt 提交拆成三个不可交换的阶段：

1. `prepare`：完成最终 runtime postflight 后，在锁目录创建 candidate，no-replace 发布到 content-addressed receipt 根，
   fsync receipt 根，并把 expected receipt SHA 以 0600+fsync 写入锁目录。此时 `current` 未改变，仍属未提交。
2. `commit-current`：写 0600 临时指针并 fsync，`os.replace` 到 `current`，fsync receipt 根，再重新打开 `current` 与目标
   receipt，逐项复验 receipt SHA、lock/run/action、manifest/control 及最终 runtime digest/config。只有全部成功才是唯一
   commit point。
3. `finalize`：commit point 已确定后把 allowlist guard 从 pending 原子改为 committed，再删除事务临时证据和固定锁。
   此阶段失败进入 `committed_cleanup_pending`，不得回落 route-off。

allowlist 转换、postflight、receipt prepare、commit-current 与 finalize 必须由一个服务器 driver 进程串行执行并安装
`EXIT/HUP/INT/TERM` trap。trap/failure handler 只按磁盘事实分类：

- `current` 精确匹配 expected receipt，且 receipt 匹配本 lock/run/manifest/control/runtime：视为已提交，保持
  allowlist；若确认 marker 滞后，则先重复执行 receipt 根 fsync、重新打开并精确读取，完成 commit point，再把 guard
  转 committed 并 finalize。不得把 current 倒退到 base；
- `current` 仍精确等于 base 才属于明确未提交：使用当前 control bundle 强制 route-off、重启复验并把 guard 转 off，
  再写 `failed`；
- `current` 已等于 expected 但 receipt/runtime 不能精确复验，属于 `ambiguous-advanced`：保持 current、路由和锁不动，
  不得伪造 `failed`，只允许同 owner 的具名恢复；其他未知指针同样不能通过裸 cleanup 猜测结果；
- 不能依赖 runner step 结果、内存布尔值或“已经调用过 replace”判断。

单进程 trap 不能覆盖 `SIGKILL`、SSH 断联未传递信号或宿主崩溃，因此 allowlist 使用 server-owned 短 lease guard。guard
目录是受保护 host 状态并只读挂载给 Core；文件以 no-replace/atomic replace 发布，固定字段绑定
`lockId/runId/runAttempt/manifestSha256/controlBundleSha256/canaryScopeSha256/executionManifestFingerprint/leaseId/issuedAt/expiresAt/state`。
Core 必须把 guard 的 execution fingerprint 与当前 `ExecutionRegistry` canonical fingerprint 内生比较，不能只信 scope。
状态机固定为：

```text
off/committed-old
  -> pending（最长 120 秒，不续租）
     -> committed（仅 receipt commit point 后，绑定 committedReceiptSha256，无过期）
     -> off（commit point 前失败或显式 fallback）
```

Core 启动装配只把无法读取的 guard 解释为“fresh V2 关闭”，不得阻断既有 Run 的收敛入口；真正授权始终在每个 fresh V2
start 中于幂等重放判定之后、任何新 Run/Step/Billing 写入之前实时重读两次：

- `pending` 只在当前服务器时间位于 `[issuedAt, expiresAt)`、TTL 不超过 120 秒、每次检查剩余窗口至少 5 秒，且
  lock/scope/fingerprint 与请求和当前 Registry 精确匹配时允许；
- `committed` 只在 scope 匹配且 `committedReceiptSha256` 为合法已提交 SHA 时允许；
- 缺失、过期、未来签发、字段/权限/symlink 漂移一律稳定返回 503，且 routing 层绝不回落 V1；
- 幂等重放先返回既有结果，resume/cancel/status/callback/materialization 与既有 V1/V2 Run 收敛不受 lease 过期影响。

5 秒剩余窗口只是额外安全余量，不能替代锁后最终检查。第二次检查必须位于 advisory/idempotency 与全部
Novel/Chapter/Session 业务锁之后，且在所有可能无界的正文 canonical/hash 派生完成后，紧贴第一条持久化
`INSERT` 执行；检查失败时不得存在新的 Run、Step、Billing、Event 或消息事实。

pending 不允许续租，避免失联 runner 无限延长开放窗口。正常 trap 立即 route-off；无法执行 trap 时，最多到 expiresAt 后
fresh V2 start 被 Core 自行封闭。宿主重启后 Core 读取同一持久 guard，不能因进程内缓存重新开放。

guard v1 只授权精确单 user+单 novel 的 `allowlist`。Core Settings、release manifest 与 Compose 门禁都稳定拒绝
`route=all`；未配置 guard 路径时所有 fresh V2 均稳定 503。未来全量开放必须另立 guard 协议版本与 spec，不能让 v1
committed guard 静默扩成通用 Skill 或任意 scope。

## 7. Canary scope 与运行配置

manifest 不公开用户/小说 ID，只保存以下 canonical JSON（无尾随换行）的 SHA-256：

```json
{"novelId":"<精确稳定小说 ID>","userId":"<精确稳定用户 ID>"}
```

两个 ID 必须是安全的单值 ID；禁止逗号、多值 allowlist、用户名、Cookie 或展示名。服务器在 transaction snapshot、
deploy preflight 和 deploy/postflight 都从正在运行的 Core 容器读取
`DURABLE_AGENT_EXECUTION_ROUTE_MODE`、`DURABLE_AGENT_EXECUTION_SCHEMA_READY` 和两个 allowlist，重新计算同一 hash。
route 与 manifest/action 不一致、scope 不是精确单 user+单 novel、部署前后 hash 不同或 `.env`/容器配置漂移时停止。

## 8. 服务器 release transaction 锁

固定互斥点是 `${APP_DIR}/.durable-agent-v2-release-transaction.lock` 0600 普通文件，事务状态目录是
`${APP_DIR}/.durable-agent-v2-release-transactions/<lockId>`。`begin-snapshot` 必须先以 `O_EXCL` 在 APP_DIR 写好并 fsync
0600 临时 owner，再用 hardlink/no-replace 原子取得固定 lock；因此不存在“目录已占有但 owner 尚未写入”的窗口。
owner 冻结随机 64 位 lock ID、GitHub run/attempt、action、workflow/target commit 与 control bundle SHA，状态另存 0600
`state` 文件。已有固定 lock 无论年龄多久都不能被新运行删除、覆盖或“超时接管”。

若 runner 在 owner fsync 后、hardlink 前中断，具名 cleanup 可凭精确 owner 字段清理 `partial-only`；hardlink 成功后
固定 lock 自身已经包含完整 owner。具名 cleanup 还必须能够清理 `fixed-only`、`fixed+partial-owner`、
`fixed+state-dir` 和完整事务，并识别 env/receipt/state/TokenUsage 只读检查留下的具名 partial。普通发布动作只接受完整且
`state=active` 的事务；不能把部分状态当成无锁继续。

锁的逻辑生命周期覆盖：

```text
begin + rollback/runtime snapshot
  -> manifest upload
  -> deploy preflight / compose switch
  -> migration + contract / allowlist / rollback gates
  -> verifiedDrain / runtime postflight
  -> commit transaction
```

每个生产脚本都必须提交同一 lock ID/control bundle SHA 并精确复验 owner；无锁、错锁、错 commit、错 run/attempt 或 `state!=active` 均在
Compose/DDL 前失败。任一步失败或 runner 中断均保留锁（可标记 `failed`，不得自动释放）。只有所有 postflight 成功后
`commit-transaction` 才封存 release receipt、删除精确状态文件、unlink 精确固定 lock 并 `rmdir` 精确状态目录。

唯一清理动作名为 `cleanup-failed-transaction`。它必须再次经过 production environment 审批，提供精确 lock ID、owner
workflow commit、GitHub run/attempt 和形如 `cleanup-failed-release:<lockId>` 的确认串；同一 `production` concurrency 已排除
仍在运行的生产 job 后，才能把因 runner 中断遗留的 active 锁显式标记为 failed，再精确删除 fixed lock、该 ID 的临时
owner、白名单状态文件和空目录。禁止按
PID、mtime、TTL、glob 或 `rm -rf` 偷锁。

## 9. verifiedDrain、配置状态机与动作顺序

fingerprint 不同的 route-off 切换和所有 rollback 都要求 `verifiedDrain` 证据。原始报告必须由 control bundle 内固定
migration helper 调用同 bundle 联合 drain 的 `verify-drain novelwriter` 生成，是 canonical JSON，且
`routeMode=off && v1DrainZero=true && v2Converged=true`。发布侧另生成 canonical binding，冻结 workflow/target commit、
control bundle SHA、migration helper SHA、joint verifier SHA、lock ID、run/attempt、Core/PG/两个 Redis 身份与原始报告
SHA；复验和 deploy postflight 始终再次运行同一 control bundle 的 verifier。缺文件、SHA、接口、身份漂移、任一 metric
非零或 verifier 非零都 fail closed。禁止从 `$APP_DIR/scripts` 复制 verifier 再把复制品当成信任根。

联合 drain 的内部准确性由 `docs/specs/2026-09-01-durable-agent-joint-drain.md` 和其测试负责。本 Workflow 只接接口，
不重写查询。只要该独立审计尚未绿，release workflow 即使其他测试通过也不能声明 fingerprint/rollback P1 已完成。

### 9.1 每个破坏性 boundary 的 live drain

初始 `verifiedDrain` 禁止复用为动作授权。以下 boundary 都必须在实际动作所在的同一 trusted control 进程内重新采集，
并在动作前原子从 `ready` 变为 `claimed`，动作成功后另写不可变 `applied`：

- `compose-release` / `compose-rollback`：紧邻第一次 mutating `docker compose up`；identity/drain 漂移时 git reset 与
  mutating Compose 均为 0；
- `allowlist-config`：紧邻 pending lease 发布、`.env` replace 与 Core recreate；
- `ddl-forward-1`、`ddl-forward-2` 以及任何未来 `psql -f`：migration helper 必须在 `apply_sql` 内、紧邻每一次
  `psql -f` 前请求新证据；缺 driver、传入旧证据或复用 sequence 时 `psql -f=0`。

每份 canonical evidence 冻结 workflow/target commit、boundary helper SHA、`lockId`、control bundle SHA、manifest SHA、
boundary、单调 sequence、采样模式、原始报告
SHA、Core container/image/config、PostgreSQL identity、普通 Redis container/image/run-id 与 execution Redis
container/image/run-id。claim 使用 no-replace 原子转换；一旦 claimed，无论 destructive syscall 是否已返回，都永不恢复为
ready，也不得重新签发同名 boundary。claimed 而没有 applied 属于 outcome-unknown，只能进入具名事务恢复，绝不自动重放
该 syscall。receipt 绑定按 sequence 排序、只含 claimed+applied 对的 canonical ledger SHA；任何 ready、partial 或
outcome-unknown 都禁止提交。

采样模式必须诚实区分：

- `pre-contract`：完整 unmigrated schema，Core 必须 `schemaReady=false + route=off + V1 fresh=false`；PostgreSQL 只查询
  迁移前存在的 V1 blockers，普通 Redis 对 ready/processing/status 做有界一致性验证，execution Redis 对 active 与
  pending/leased/rejected/quarantine 做有界空状态验证；不得查询不存在的 V2 列/表，也不得伪造 V2 drain marker；
- `post-contract-closed`：第一次 DDL 后仅允许 `migrated-empty-v2 + schemaReady=false + route=off + V1 fresh=false`，
  PostgreSQL 同时证明 V1/V2 空，两个 Redis 使用尚未开放路由阶段的有界原始集合验证；
- `migrated`：只接受现有 joint-drain v2 报告、两个 drain index version=1、两个 fresh 入口关闭且所有指标为零。

每次采样在联合窗口外再各读取一次完整 topology；outer-before、报告内 topology hash、outer-after 必须相同。PG identity、
任一 Redis run-id/container/image 或 Core container/image 漂移，以及新 pending/leased/rejected callback，都使当前 boundary
失败。该机制不能阻止采样完成后由独立管理员瞬时替换基础设施；若威胁模型包含此能力，必须另加平台 maintenance
barrier，不能把 release 文件锁宣传为基础设施屏障。

生产动作：

- `route_off_release`：先验证 development evidence 与锁；若起点为 allowlist，workflow 原子保存 `.env` 前像、写入
  `route=off + V1 fresh=false`、以当前冻结 Core digest 重启并验证，再生成 drain。只允许先完成真实 development 证据
  的目标进入生产。生产迁移在部署/结构状态允许时执行，不能在 production job 内补做 development migration。同一动作
  必须按当前权威状态选择且只选择一个合法 gate：迁移前/迁移后 route-off、schema-ready route-off、初始化 drain indexes
  或 V1/V2 fresh-start 全关闭后的 route-off drain；不得把 `post-contract-route-off` 机械用于所有后续重启阶段。
- `allowlist_release`：无论起点是旧 allowlist 还是 route-off，workflow 都先强制收敛为 route-off；再以 route-off 部署
  并验证同 fingerprint 目标，最后由单个服务器 finalize 进程重采 `allowlist-config` boundary、发布 pending lease、
  原子写入 `schemaReady=true + route=allowlist + V1 fresh=true + manifest 精确 user/novel`，只重启冻结 target Core，完成
  postflight、receipt commit point 与 guard committed 转换。要求 provider canary passed，不执行 DDL。commit point 前
  失败恢复 route-off；commit point 后 finalize 失败保持 allowlist 并保留 committed-cleanup 锁。
- `rollback`：使用旧 manifest 自身 target/rollback source commit 与冻结 rollback digest；workflow 先把当前 allowlist
  原子转换为 route-off/V1 fresh=false 并验证，再生成 verifiedDrain，最后部署旧应用 bundle与冻结 rollback digest；不执行
  durable DDL rollback。进入 rollback drain 后任一步失败都保持 route-off，不自动重新开放 allowlist。

target Compose 与其在同一进程内、route-off 下发生的一次即时旧镜像补偿被定义为一个 compound closed-ingress boundary：
同一 claimed token 最多触发一次 target 切换和一次冻结起点补偿；补偿成功写 `outcome=compensated`，事务仍失败且不生成
receipt。自动补偿必须先完成旧栈健康复验，并在 release lock 仍为 `active` 时持久写入 `compensated`；只有该写入成功或
明确失败后，才把事务状态改为 `failed`，且始终返回最初的部署失败码。不得先写 `failed` 再补记 outcome，也不得把
“旧容器已启动”冒充为“补偿已被持久证明”。若进程在任一 syscall 后崩溃、补偿失败或 `compensated` 写入失败，则保留
claimed/failed 锁并进入 outcome-unknown，禁止再次自动 Compose。Workflow 的失败收口可在完整复验同一 owner、inode 与
control bundle 后，把已是 `failed` 的同一事务视为只读幂等成功；该兼容不得让任何其他命令在 terminal lock 上继续执行。

`.env` 写入使用同一 APP_DIR 文件系统内事务目录的具名 0600 临时文件、fsync 和 `os.replace`，拒绝重复键；前像及 SHA
保存在事务状态目录，恢复前再次核对 SHA。每次重启前后
都冻结 Core digest/container/config。release 成功 receipt 记录最终配置；失败清理只清锁，不擅自改回业务路由。任何人工
预改 `.env`、目标配置与 manifest scope 不一致或容器未吃到新配置均失败。

## 10. 验收与攻击测试

- `build.yml` 只保留 CI；任何旧 main push 自动 deploy 路径均不存在。
- 所有 production job 的 concurrency group 精确为 `production`，取消策略为 false。
- 非 dispatch、非 main、input/SHA 不同的恶意候选在 checkout 和任何仓库脚本之前失败。
- environment API 缺 audit token、required reviewer、prevent-self-review 或精确 main branch policy 时稳定失败。
- environment API 未证明旧 `SERVER_SSH_KEY` 删除、新专用 key 存在，或三份 key 轮换/forced-command/最小权限
  离线证据 hash 缺失时，SSH 调用次数精确为 0。
- dev artifact 缺失、SHA/run ID 错、provider pending 或 target/scope/digest 漂移时在 SSH 前失败。
- rollback artifact 的 producer run/workflow/main commit/conclusion/attempt 任一不符时 SSH 为 0；main 前进后，合法旧
  manifest 仍按自己的 trusted/target commit + artifact SHA 复验，不能被当前仓库 facts 错杀或替换。
- 服务器 APP_DIR 中植入恶意同名 drain/helper、在 deploy reset 后植入旧 helper，都不能被执行；control bundle 缺文件、
  SHA 漂移或 owner/binding 中 bundle SHA 不同，在 Compose/DDL 前失败。
- rollback source 缺 current receipt、receipt 被改、manifest receipt 不匹配或运行 digest 漂移时失败；裸 Git HEAD 与
  任意 40 位输入不能成为来源。
- route-off→allowlist 与 allowlist→route-off 的原子 env/重启/运行态断言成功；中断点能恢复前像或保持已建立的安全
  route-off，不能依赖人工预改配置。
- 两个 lock 竞争时后者失败；hardlink 后任一断点均已有完整 fixed owner；cleanup 能精确处理所有已取得锁状态；任一步
  失败保留 owner；错 lock/错确认不能清理；成功 postflight + receipt 才释放。
- canary scope 在 manifest、部署前 Core、部署后 Core 任一处漂移都在路由/后续动作前失败。
- fingerprint/rollback 无 canonical `verifiedDrain` 时在 Compose/DDL 前失败。
- 初始 drain 后切换 PostgreSQL identity、任一 Redis container/image/run-id，或注入 execution pending/leased/rejected
  callback 时，下一 boundary 必须重采失败；git reset、mutating Compose、allowlist env replace 与 `psql -f` 计数为 0。
- unmigrated 只接受 `pre-contract`；直接调用 `release-database`/migration `forward` 时缺 boundary、旧 sequence 或伪造
  migrated drain，`psql -f=0`；稳定 identity 与第二次 zero-drain 才允许动作。
- receipt create/publish/current 临时写/replace 前故障最终 route-off；replace 后只要 current/receipt/owner/runtime 精确
  匹配，就重复 fsync+精确 reread并完成 commit，绝不 route-off/failed；匹配不清则保持 `ambiguous-advanced` 与锁。
  commit point 后锁清理失败保持 allowlist 与 `committed_cleanup_pending`。runner HUP/TERM、SIGKILL 后 lease 过期和宿主重启
  均使未提交 fresh V2 start 稳定 503 且不回落 V1；既有 Run 仍可收敛。
- shell `-n`、Ruff、相关 pytest、`git diff --check` 全绿；两个获批迁移 SQL SHA 不变。
- 实现和测试期间不联网、不读取真实 secret、不上传 artifact、不部署、不操作真实数据库。

## 11. CLI 与 operator skill 兼容性

本次 release trust 改造不新增、不删除、也不改名任何 InkForge CLI 命令、参数、JSONL/SSE 语义或 exit code，CLI
commit 仍必须与新发布 target commit 相同。因此 CLI skill 不需要命令映射迁移。需要更新的是生产 operator skill：

- 只能触发 `durable-agent-v2-release.yml` 的四个具名 action；旧 TokenUsage 一次性迁移 Workflow 已永久退役且必定失败；
- 使用新的 `DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY`/`DURABLE_AGENT_V2_RELEASE_SSH_KNOWN_HOSTS`，不得重新创建
  `SERVER_SSH_KEY`；
- release/rollback/cleanup 输入必须按本规格提供 exact commit、artifact SHA、producer run/attempt、lock owner 与确认串；
- 缺 production environment API 证据、旧公钥撤销、forced-command 或最小权限离线证据时，不得把“代码已实现”解释为
  可运行生产发布。

完整 operator skill 更新清单另见 `docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md`。
