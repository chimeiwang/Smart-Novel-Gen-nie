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
API 不可达、权限不足、owner 身份不一致、分页不完整或字段漂移一律失败。列表 API 必须有界遍历全部页面、拒绝跨页
重复和 `total_count` 漂移，再输出 canonical 合并结果；不能只请求 `per_page=100` 后把超过 100 项永久当成不可部署。
3. 本地候选验证、真实 remote development 和 production approval 是三个独立阶段。生产 job 绝不先部署生产再补开发库
   迁移、故障注入或真实供应商 canary。
4. route-off 与 allowlist 发布必须在任何 SSH 前下载并复验独立 GitHub run 产生的 v2 migration qualification、candidate
   evidence、development image provenance 与目标镜像 artifact。旧
   `inkforge-durable-agent-v2-development-evidence/1`、`test-report/1` 或只校验文件 hash 的报告一律不能满足生产
   consumer。
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
  -> candidate-validation
  -> development-v2-bundles-download-and-semantic-verify
  -> production(environment approval, concurrency=production)
  -> exact-attestation-download-and-file-whitelist-normalize
  -> token-only-live-api-collection-and-owner-routing
  -> fixed-known-hosts-secret-materialization
  -> secretless-canonical-pagination-and-policy/provenance/trust-verify
  -> fixed-pre-private-key-denial
```

`trusted-context-guard` 必须是 `source` 的第一个 step。它不能执行候选仓库中的脚本。恶意候选提交即使把
`scripts/durable-agent-v2-release.sh` 改成永远成功，也不能让非 main、非 dispatch 或 input/SHA 不一致的运行到达
checkout。

但该结论只描述当前诚实 Workflow 的顺序，不构成根信任：Workflow YAML、checkout 前 shell 与 verifier 都来自可变的
`github.sha`，恶意 main 候选可以同时删除门禁并声明 production environment。生产启用必须另有候选无法修改或取消的
仓外执行根：独立受规则集保护的 release repository，或其中 full-SHA 固定的 required reusable workflow，再叠加 custom
deployment protection；该执行根按 GitHub OIDC repository/workflow/ref/SHA/run subject 只签发短期单操作 broker
capability。静态 SSH private key 不得直接暴露给本仓候选 Workflow。main ruleset、CODEOWNERS、required workflow、
environment 审批、bypass/audit 与 OIDC policy 都必须保留仓外 API 证据。当前仓内固定失败不能替代此根，只能保证当前
已审核版本不执行生产动作。

`source` 不读取任何自定义 secret；它只做 dispatch/input 格式、trusted commit 与 checkout 复验。只有 production
environment 审批通过后的 job 才能读取 `GH_ENVIRONMENT_POLICY_AUDIT_TOKEN`。带 token 的 step 只允许固定调用 GitHub
REST API、把响应写入 0600 文件，并用固定 `jq` 读取 repository owner type 以决定是否请求 organization endpoint；禁止
执行任何 checkout 中的 Python/shell verifier。canonical 分页合并、policy、provenance 与 trust verifier 必须在后续没有
secret env 的 step 中运行：

- `GET /repos/{owner}/{repo}/environments/production`；
- `GET /repos/{owner}/{repo}`；
- `GET /repos/{owner}/{repo}/environments/production/deployment-branch-policies?per_page=100`。
- `GET /repos/{owner}/{repo}/environments/production/secrets?per_page=100`；
- `GET /repos/{owner}/{repo}/actions/secrets?per_page=100`；
- owner type 为 `Organization` 时才调用 `GET /orgs/{owner}/actions/secrets?per_page=100`；owner type 为 `User` 时生成并
  复验 canonical `no-org-scope` 证据；
- `GET /repos/{owner}/{repo}/environments/production/variables?per_page=100`。
- `GET /repos/{owner}/{repo}/actions/runs/{sshProducerRunId}`；
- `GET /repos/{owner}/{repo}/actions/runs/{bootstrapProducerRunId}`。

所有列表调用使用 `gh api --paginate --slurp` 保存有界 page array；无 token normalizer 要求每页 `total_count` 一致、
单页不超过 100、聚合计数精确、名称不重复且页数/项数未越界，再写出 canonical 单 inventory。本地 verifier 使用
`O_NOFOLLOW` descriptor reader 消费 API 返回文件。repository metadata 的 `full_name` 必须等于本次 repository，
`owner.login` 必须等于 repository owner，`owner.type` 只能为 `User|Organization`。production environment 必须启用
`custom_branch_policies=true`、`protected_branches=false`，branch policy 列表只能有精确名称 `main`，并存在至少一名
required reviewer 且 `prevent_self_review=true`。仓库内的变量、manifest、候选脚本或普通 `GITHUB_TOKEN` 布尔输入不能
自证这些设置。仓库外还必须保存 environment 配置截图或 API 响应摘要作为上线审批证据；响应本身不得混入 token。

`GH_ENVIRONMENT_POLICY_AUDIT_TOKEN` 必须只存在于 production environment，repository/organization scope 都不得存在。
它必须是与发布 SSH key 隔离的只读 GitHub App installation token 或 fine-grained token，最小权限只允许读取本仓
Actions run、repository environment/secrets/variables 与 organization Actions secret inventory；禁止 contents、workflow、
secret 或 environment 写权限。source job 不得引用它。

同一外部校验必须证明 production environment 存在且只在该 scope 暴露两个新角色 key
`DURABLE_AGENT_V2_RELEASE_EXECUTION_SSH_PRIVATE_KEY`、
`DURABLE_AGENT_V2_RELEASE_UPLOAD_SSH_PRIVATE_KEY` 及
`DURABLE_AGENT_V2_RELEASE_SSH_KNOWN_HOSTS`；旧 `DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY` 与
`SERVER_SSH_KEY` 在 environment/repository/organization 三层都不存在，两个新 key、known_hosts 与 audit token 在
repository/organization 也不存在。服务器 host/port/user 只读取三个 production environment variable 并与签名 subject
逐项相等。以下三个旧变量只允许作为可选的 64 位小写 SHA-256 诊断值，不再参与授权：

- `DURABLE_AGENT_V2_RELEASE_OLD_KEY_REVOCATION_EVIDENCE_SHA256`：服务器 `authorized_keys` 已撤销旧 key 的离线证据；
- `DURABLE_AGENT_V2_RELEASE_FORCED_COMMAND_EVIDENCE_SHA256`：新 key 使用 forced-command 的离线证据；
- `DURABLE_AGENT_V2_RELEASE_MINIMUM_PERMISSION_EVIDENCE_SHA256`：部署账号/命令白名单/文件权限最小化证据。

dispatch 对 SSH 与 bootstrap attestation 各要求精确 producer run ID、run attempt 与 artifact SHA。production job 按
run ID 下载固定名称 artifact。GitHub proof 只绑定 canonical stable run identity projection 与 identity SHA，不绑定会在
producer 完成时变化的完整 REST 响应 SHA；producer 可用 `in_progress` 响应生成，production 用 `completed/success` 响应
重算同一 identity，并用当前 trusted checkout 复验 producer workflow/head SHA/main/dispatch/success、canonical
artifact SHA、TTL、repository/environment/host/port/user、known_hosts/host key、双公钥、完整 `authorized_keys`、三层
inventory 与 broker policy；任何额外/缺失文件或字段都失败。known_hosts secret 由固定无仓库脚本 step 落入 0600 文件，
并由同一次 trust verifier descriptor snapshot 完成 evidence 比对、host/key 解析与 attestation hash 绑定，不保留独立
`cmp`。三个诊断 hash 缺失不影响授权，semantic artifact 或任一外部 API 事实缺失则必须在准备 SSH 私钥、`ssh`、
`scp`、Compose 或 DDL 前失败。当前流式双角色 broker 与 sealed
genesis/current 尚未接线，production 在上述复验后仍固定失败，且 workflow 不引用 private key 或远端执行路径。

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
检查精确文件白名单、普通文件、0700/0600 权限、全部 SHA 和元数据。构建器必须对根目录和每一层新建子目录显式设置
`0700`，对每个文件显式设置 `0600`，不得依赖 runner 的 ambient umask；在 `umask=022` 下构建后的自校验与
独立复验仍必须通过。
通过 `renameat2(RENAME_NOREPLACE)`（macOS
构建侧为 `renamex_np(RENAME_EXCL)`）原子发布为
`${APP_DIR}/.durable-agent-v2-control-bundles/<workflowTrustedCommit>/<bundleSha256>`。既有同名 bundle 只能逐字节复验，
不能覆盖。事务 owner、release manifest、verifiedDrain 与 release receipt 都冻结同一 bundle SHA。后续远程命令直接执行
该目录内 driver；即使应用 bundle 随后 reset `APP_DIR`，也不能改写控制逻辑。rollback 可 checkout 旧应用 bundle，但
rollback preflight、配置转换、drain、Compose 切换、postflight 和 receipt 只能运行当前 trusted control bundle。

## 5. Development evidence v2 consumer

生产发布只消费 `docs/specs/2026-09-01-durable-agent-v2-development-evidence-v2.md` 定义的两层语义证据。固定 artifact
名称和来源为：

- candidate producer run：`durable-agent-v2-candidate-evidence`、
  `durable-agent-v2-development-images` 与 `durable-agent-v2-target-images`；
- qualification producer run：`durable-agent-v2-migration-qualification`。

dispatch 必须显式提供 candidate run ID/run attempt，以及 qualification run ID/run attempt/source commit。两个
run attempt 都必须精确为 `1`；source 前置门禁对缺失、零、前导零、非十进制、非 40 位小写 commit 或 rollback/cleanup
携带这些发布输入全部失败。production consumer 通过 GitHub Actions API 对两个 run 分别复验 repository、固定
workflow path、main head、`workflow_dispatch`、`completed/success` 和精确 run attempt。candidate head 必须等于本次
`workflowTrustedCommit`；qualification head 必须等于输入的历史 migration source commit。只在 artifact JSON 里自报
`runAttempt`，或只对 candidate 复验 attempt，均不构成 provenance。

所有由 dispatch 提供的十进制 run ID/run attempt，包括 SSH、bootstrap、development candidate、qualification、rollback
manifest 与失败锁 owner，都必须在首个 checkout 前按无前导零正十进制验证；后续 verifier 的重复校验不能替代此前置
门禁。固定为 `1` 的 candidate/qualification attempt 继续只接受字面量 `1`。

artifact 的静态可信期望不由 artifact 自证，也不接受操作者预填尚未产生的当前 run hash。`development` environment
的受保护 variables 必须通过只读 audit token 从 GitHub API 取得，并由无 token step 按 producer policy 精确白名单
复验；它冻结：

- 既有 qualification bundle SHA；
- development scope、canary scenario、execution manifest fingerprint 与 build definition SHA；
- resource/provider policy SHA、resource host/provider identity SHA；
- provider prompt/completion/reasoning/total token 与 cost 上限。

当前 candidate/image provenance SHA 与三镜像 digest 是本 run 完成后才存在的事实，禁止循环预填进 environment
variables。consumer 从已完成、固定名称、绑定精确 run/attempt 的下载 bundle 现场计算 candidate/image SHA；从复验并
实际加载的目标镜像 snapshot 取得三个 digest，再要求这些动态事实与 candidate/image provenance 逐项相等。未来独立
controller 还必须把计算值与 GitHub artifact service 的 digest/provenance 对齐；当前仓内固定失败不冒充该外部根。

带 audit token 的 step 只能固定调用 `gh api` 写 0600 响应，不能运行 checkout 中的脚本；后续无 token step 才运行
policy、run provenance 和 v2 semantic consumer。目标镜像 archive 仍须先按自身 `SHA256SUMS` 复验、加载，并由当前
trusted checkout 重新生成 `target-images.current`；它必须逐字节等于 producer snapshot。consumer 再同时要求 actual
web/core/agent digest 与 execution fingerprint 精确等于 development image provenance、candidate 汇总和受保护
variables 中的 execution/build 事实，任一漂移都失败。consumer 还从可信 target checkout 生成 NUL 分隔的完整 Git tree
manifest，重算 source tree 与冻结 build definition；image provenance 的 source/build 自报不能直接通过。
目标镜像 artifact 在 checksum、`docker load` 或再次上传前，顶层成员必须精确只有 `SHA256SUMS`、
`target-images.snapshot` 与 `target-images.tar.gz` 三个单链接普通文件；额外目录、symlink、socket、FIFO、设备或其他特殊
节点全部失败，不能因只枚举 `-type f` 而被漏过。现场生成的 `target-images.current` 只能在上述白名单复验后加入本次
release 的短期已复验输入。

qualification bundle 必须完整包含四份 v2 migration report；consumer 使用只读 checkout 的 qualification source commit
重新计算具名 forward/rollback SQL SHA、pre/post contract fingerprint，并把这些事实、development scope、producer
repository/run/attempt/head 与 qualification SHA 一次传给语义 verifier。candidate bundle 必须完整包含三份 v2 report，
并把 target commit、candidate producer run/attempt、qualification SHA、scope、scenario、actual images、execution
fingerprint、policy、subject 与 token/cost caps 一次传给语义 verifier。verifier 必须检查 exact schema、canonical JSON、
文件白名单、权限/链接、checksum、TTL 以及全部报告语义；`status=passed` 或报告文件 hash 相等本身不够。

旧 `development-evidence.json`、`durable-agent-v2-development-reports`、
`inkforge-durable-agent-v2-development-evidence/1`、`test-report/1`、pending/unavailable provider 以及缺任一 v2 report 的
artifact 全部明确失败。release manifest v3 的历史字段 `developmentEvidenceSha256` 从本版本起只承载已复验的
`candidate-evidence.json` SHA；它不再表示 v1 汇总，也不能替代 qualification/image provenance 复验。

真实 v2 producer 必须是另一个声明 `environment: development` 的受保护 job，不得在 production-approved job 中补做
迁移、2C2G 或 provider canary。当前 `.github/workflows/durable-agent-v2-development-evidence.yml` 在 artifact upload 前
固定失败且没有 upload action，因此当前真实 release 必然在 v2 artifact acquisition 阶段失败；即使测试提供完整合法
fixture，production 仍在 streaming broker/sealed genesis 门禁固定失败，本文不授权 SSH、部署或生产 DDL。

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

- `route_off_release`：先验证 development evidence v2 与锁；若起点为 allowlist，workflow 原子保存 `.env` 前像、写入
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

`mark-transaction-failed` 的成功输出必须对应磁盘权威事实：只允许“已提交并完成恢复”或“同一 owner/inode 的锁已精确
落为 `failed`”两种结果。`reconcile` 非零后若 state 仍不是可复验的 `failed`，包括 `ambiguous-advanced`、route-off
补救失败、commit-recoverable 确认失败或 committed finalize 失败，都必须返回
`durable-release:error:transaction-outcome-unknown` 非零并原样保留 lock/current/route，禁止把未知结果打印成成功失败终态。

锁 state 的每次转换必须使用同目录、`O_EXCL` 创建且名称同时绑定完整 owner SHA 与目标 state 的唯一 partial；partial
内容只能是目标 state 单行。写入后依次执行 0600、文件 fsync、`os.replace` 与父目录 fsync。崩溃恢复只接受同 owner、
同目标、严格白名单名称且内容/权限精确的唯一 partial；symlink、异 owner、异目标或多个 partial 一律拒绝，绝不按 TTL
删除、接管或“偷锁”。replace 已完成而父目录 fsync 未完成时，同 owner 对磁盘目标 state 的重试必须只补 fsync 并成功。
失败清理只能在复验 owner 后识别并移除上述具名 partial，不再接受历史固定 `.state.partial` 或 deploy 自写 state 临时文件。

`.env` 写入使用同一 APP_DIR 文件系统内事务目录的具名 0600 临时文件、fsync 和 `os.replace`，拒绝重复键；前像及 SHA
保存在事务状态目录，恢复前再次核对 SHA。每次重启前后
都冻结 Core digest/container/config。release 成功 receipt 记录最终配置；失败清理只清锁，不擅自改回业务路由。任何人工
预改 `.env`、目标配置与 manifest scope 不一致或容器未吃到新配置均失败。

## 10. 验收与攻击测试

- `build.yml` 只保留 CI；任何旧 main push 自动 deploy 路径均不存在。
- 所有 production job 的 concurrency group 精确为 `production`，取消策略为 false。
- 非 dispatch、非 main、input/SHA 不同的恶意候选在 checkout 和任何仓库脚本之前失败。
- environment API 缺 audit token、required reviewer、prevent-self-review 或精确 main branch policy 时稳定失败。
- environment API、三层 secret inventory 或 semantic attestation 任一权威事实缺失时，SSH 调用次数精确为 0；旧三个
  轮换/forced-command/最小权限诊断 hash 缺失不影响授权，但若存在而不是 64 位小写十六进制则稳定失败。
- v2 candidate/qualification/image artifact 缺失、SHA/run ID/run attempt 错、旧 `test-report/1`、报告语义错误或
  target/scope/scenario/policy/subject/digest 漂移时在 SSH 前失败。
- 所有 dispatch 十进制 run ID/attempt 的前导零在首个 checkout 前失败；目标镜像 artifact 含额外目录、symlink 或特殊
  节点时在 checksum、`docker load` 和已复验输入上传前失败。
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
- deploy 自动补偿必须用真实 release driver 做跨脚本回归：目标切换失败后只允许一次目标 Compose 与一次冻结起点
  Compose；旧镜像、Nginx 和 runtime 复验完成时锁仍为 `active`，随后同一 claimed `compose-release` boundary 先落盘
  `applied(outcome=compensated)`，最后才把事务标为 `failed`。回归必须同时证明返回最初的目标部署错误码、未生成新
  receipt，且 terminal `failed` 锁除精确同 owner/inode 的 `mark-transaction-failed` 只读重试外拒绝任何一般破坏性命令。
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
- production environment 使用分离的
  `DURABLE_AGENT_V2_RELEASE_EXECUTION_SSH_PRIVATE_KEY`、
  `DURABLE_AGENT_V2_RELEASE_UPLOAD_SSH_PRIVATE_KEY` 与
  `DURABLE_AGENT_V2_RELEASE_SSH_KNOWN_HOSTS`；不得在 repository/organization 复制，也不得重新创建
  `DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY` 或 `SERVER_SSH_KEY`；
- route-off/allowlist 输入必须提供 exact workflow commit、candidate run/attempt、qualification run/attempt/source commit 与
  canary user/novel；candidate/qualification 两个 attempt 都必须为 `1`。candidate/image SHA 和镜像 digest 由完成 run 的
  固定 artifact 现场计算，不再使用旧 `development_evidence_run_id/development_evidence_sha256` 输入。rollback/cleanup
  必须拒绝携带任何 development v2 producer 输入；原有 manifest SHA、lock owner 与确认串规则不变；
- SSH/bootstrap run/attempt/SHA 六项输入为所有 action 必填；缺 production environment API、三层 inventory、semantic
  attestation、旧公钥撤销、双 forced-command、sealed genesis 或真正流式 broker 时，不得把“代码已实现”解释为可运行
  生产发布。

完整 operator skill 更新清单另见 `docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md`。
