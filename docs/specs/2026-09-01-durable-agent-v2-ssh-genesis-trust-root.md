# Durable Agent V2 SSH 与 genesis 发布信任根

状态：基础纵切实施中；canonical 证据、离线校验器和 broker 协议已冻结，但尚未接入真实
`authorized_keys`、GitHub production Workflow 或生产 receipt 根，因此生产发布必须继续 fail closed

日期：2026-09-01

## 1. 背景

现有受保护发布框架只要求三个任意非零 SHA-256 字符串，不能证明这些摘要对应什么证据、何时采集、由谁签发，
也没有把 GitHub secret、known_hosts、服务器账号、公钥和 forced-command 绑定成同一个 subject。现有发布 SSH key
同时承担 `ssh`、`scp`、stdin `docker load` 和任意远端 shell 字符串，仓内也没有可部署的 `SSH_ORIGINAL_COMMAND`
broker。release receipt 虽然形成 `previousReceiptSha256` 链，但缺少可验证的 genesis，任意手写起点都可能冒充
受保护成功发布。

本规格先建立仓内可离线验证的信任数据面。它不修改真实服务器，也不把当前生产 Workflow 解锁；只有仓外证据、
专用公钥轮换、broker 安装和 genesis 安装全部完成后，才能另行接线。

## 2. 目标

1. 冻结 `inkforge-ssh-release-attestation/1` canonical 证据，语义绑定仓库、environment、服务器
   host/port/user、known_hosts、主机公钥、旧公钥、新执行/上传公钥、三层 secret inventory、forced-command 与
   broker policy。
2. 冻结 `inkforge-release-bootstrap-attestation/1` canonical 证据，只授权一个精确
   `previousReceiptSha256=null` genesis receipt subject，并把它绑定到前述 SSH attestation。
3. 支持 Ed25519 签名证明；也冻结受保护 GitHub run provenance 模式，但该模式只有在 verifier 直接消费从精确
   run 下载的 artifact 与 GitHub API run 响应时才成立，孤立 JSON 或自报 run ID 不构成信任。
4. 冻结 `inkforge-release-broker-request/1` 固定 stdin 协议和角色/operation allowlist，拒绝 shell 字符串、TTY、
   agent/X11/TCP forwarding 与任意子命令。
5. 提供离线攻击测试，证明篡改、过期、主机或 key 漂移、旧 secret/旧公钥残留、forced-command 漂移、跨角色
   operation、额外字段和非 canonical 输入均失败。

## 3. 非目标

- 不访问 GitHub API、SSH、真实 `authorized_keys`、真实 secret、开发库或正式库。
- 不安装 key、不修改宿主机用户、不执行 `sshd` reload，不写生产 receipt/current 指针。
- 不让 broker 执行上传、Docker、Git、Compose、DDL 或 release driver；本轮 dispatcher 只生成可审计的固定计划。
- 不修改 InkForge 公共 API、数据库、产品 CLI 命令、stdin/stdout、JSONL/SSE 或 exit code。
- 不以仓内 fixture、自签测试 key、截图、人工文字或三个裸 hash 代替仓外生产证据。

## 4. Canonical 与时间规则

两类 attestation 都是 UTF-8 JSON 对象，禁止重复 key、浮点、`NaN`、未知字段和符号链接。编码固定为
`sort_keys=true`、`ensure_ascii=false`、分隔符 `(',', ':')`，并且只带一个尾换行。artifact 目录为 0700，
文件为 0600，只包含具名 JSON 与单行 `SHA256SUMS`。

完整文档使用统一 envelope：

```json
{
  "format": "<format>",
  "payload": {},
  "proof": {
    "keyId": "<稳定 key ID>",
    "kind": "ed25519",
    "signature": "<无 padding base64url>"
  }
}
```

签名输入是只含 `format` 与 `payload` 的 canonical JSON。可信公钥必须由 verifier 参数提供，不能从文档自报。
`issuedAt`/`expiresAt` 使用 UTC 秒精度 `YYYY-MM-DDTHH:MM:SSZ`；签发时间最多允许比 verifier 时钟快 300 秒，
TTL 必须大于 0 且不超过 24 小时，过期即失败。生产审批和执行不得跨过过期边界。

GitHub provenance envelope 使用 `kind=github-actions-run`，proof 必须冻结 repository、固定 workflow path、
run ID/attempt、main head SHA、`workflow_dispatch`、success conclusion、artifact 名及 unsigned subject SHA。verifier
必须同时得到从 API 读取的 run JSON，并在下载精确 run artifact 的同一可信 job 中复验；缺外部 run JSON 或把文件
复制到另一个 run 后均失败。该模式不能由候选仓库脚本或输入布尔值自证。

## 5. SSH release attestation

`payload` 精确包含：

```json
{
  "broker": {
    "executableSha256": "<64 hex>",
    "executionForcedCommand": "/usr/local/libexec/inkforge-release-broker execution",
    "policySha256": "<64 hex>",
    "protocol": "inkforge-release-broker/1",
    "uploadForcedCommand": "/usr/local/libexec/inkforge-release-broker upload"
  },
  "environment": "production",
  "evidence": {
    "authorizedKeysSha256": "<64 hex>",
    "environmentSecretsSha256": "<64 hex>",
    "knownHostsSha256": "<64 hex>",
    "organizationSecretsSha256": "<64 hex>",
    "repositorySecretsSha256": "<64 hex>"
  },
  "expiresAt": "<UTC>",
  "issuedAt": "<UTC>",
  "keys": {
    "executionPublicKeySha256": "<64 hex>",
    "retiredPublicKeySha256": ["<64 hex>", "..."],
    "uploadPublicKeySha256": "<64 hex>"
  },
  "repository": "<owner/repo>",
  "server": {
    "host": "<精确连接 host>",
    "hostPublicKeySha256": "<64 hex>",
    "port": 22,
    "user": "<精确部署用户>"
  },
  "secretPolicy": {
    "activeEnvironmentSecrets": [
      "DURABLE_AGENT_V2_RELEASE_EXECUTION_SSH_PRIVATE_KEY",
      "DURABLE_AGENT_V2_RELEASE_UPLOAD_SSH_PRIVATE_KEY"
    ],
    "retiredSecrets": [
      "DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY",
      "SERVER_SSH_KEY"
    ]
  }
}
```

主机绑定必须同时满足：known_hosts 文件字节摘要匹配；存在精确 `host`（非 22 端口使用 `[host]:port`）条目；
该条目的规范化 OpenSSH 公钥摘要等于签名 `server.hostPublicKeySha256`，并且 verifier 必须从独立
`host-public-key` 证据重新计算同一摘要；不能只依赖 `knownHostsSha256` 间接绑定。禁止 `ssh-keyscan`、`StrictHostKeyChecking=no`、
散列 host 作为本次具名证明，或只证明 known_hosts 文件存在。

执行 key 与上传 key 必须不同，也不得等于任一 retired key。完整 `authorized_keys` 证据中：retired key 必须为零；
两个 active key 必须各出现且只出现一次；其 options 必须分别精确为
`restrict,command="/usr/local/libexec/inkforge-release-broker execution"` 和
`restrict,command="/usr/local/libexec/inkforge-release-broker upload"`。额外 release key、不同命令、缺 `restrict`、
`no-pty` 的不完整拼接或允许 forwarding 均失败。非 release 管理 key 可以存在，但不能复用 active/retired key。

GitHub API secret inventory 必须完整分页并交叉验证：

- environment scope 只允许存在两个新角色 key，且两个 retired secret 均不存在；
- repository 与 organization scope 必须同时不存在两个新 key与两个 retired secret，防止历史 workflow 从更宽
  scope 继续取到生产私钥；
- inventory 文件 SHA 与 attestation 逐项相等，API 权限不足、`total_count` 不完整或重复名称都失败。

## 6. 固定 broker 协议

两个 authorized key 都只能进入 forced-command broker。sshd 必须使用 `restrict`，不得允许 PTY、agent/X11/TCP
forwarding 或用户 rc。broker 只接受 `SSH_ORIGINAL_COMMAND` 精确等于 `inkforge-release-broker/1`；空值、参数、
换行、`scp -t`、`sftp-server`、shell 或其他命令全部拒绝。

stdin 只接受一个不超过 64 KiB 的 canonical JSON 请求：

```json
{"format":"inkforge-release-broker-request/1","operation":"<enum>","payload":{}}
```

本轮冻结的角色 allowlist 为：

- `upload`：`put_control_bundle`、`put_release_manifest`、`put_deploy_bundle`、`put_image_archive`；
- `execution`：`begin_snapshot`、`begin_rollback`、`transition_route_off`、`prepare_release`、
  `deploy_release`、`release_database`、`finalize_allowlist`、`rollback_postflight`、
  `transaction_postflight`、`commit_transaction`、`mark_transaction_failed`、
  `cleanup_failed_transaction`、`transaction_status`。

每个 operation 有精确 required/optional 字段、类型、长度和字符集。dispatcher 只能选择代码内固定 executable 与
argv 模板；请求不得提交 executable、argv、环境变量名、工作目录、重定向或 shell 文本。上传二进制帧与真正的固定
程序执行不在本轮实现，生产接线前必须另补流式长度/SHA、no-replace、配额、断线清理和 outcome-unknown 测试。

## 7. Bootstrap attestation 与 genesis 状态机

bootstrap payload 精确绑定 repository/environment/server subject、SSH attestation SHA 和一个完整
`genesisReceipt`。该 receipt 必须是 `inkforge-durable-agent-v2-release-receipt/1`、
`previousReceiptSha256=null`，并冻结 active commit、三镜像 digest、execution fingerprint、最终 route/schema/V1
fresh 配置、manifest/control/boundary ledger、Core container、run/attempt/lock 与 workflow commit。任何字段不能在
安装时重新推断。

服务器未来使用独立 0700 bootstrap 状态目录和 0600 canonical state：

```text
absent
  -> prepared  （签名 attestation 已复验；current 必须不存在）
  -> installed （receipt no-replace 发布并写 current；磁盘回读匹配）
  -> sealed    （receipt 根、current、SSH attestation 和 broker 全部复验）
```

状态只允许同一 attestation SHA 与同一 genesis receipt SHA 单向推进；禁止跳步、回退、换 subject、第二次 genesis、
覆盖 current 或从普通 release receipt 走 `previous=null`。`sealed` 后每个新 receipt 必须令
`previousReceiptSha256` 等于当时 current；遍历链必须最终且只最终到达 attestation 绑定的 genesis，不能有环、断链、
缺 receipt 或第二个 null。

通用 `durable_agent_v2_release_receipt.py` 不再被允许创建或独立认可 null previous；只有未来受控 bootstrap installer
在验证 SSH/bootstrap attestation 和完整 receipt 链后才能使用专用入口。当前 release driver 尚未接入该链校验，
所以 GitHub Workflow 必须在任何 SSH 前保持硬阻断。

## 8. 本轮仓内集成与 fail-closed 边界

- 新 validator/builder 和 broker policy 文件进入 control bundle 白名单，但不被远端执行。
- 当前 production environment policy verifier 仍只有裸 hash 门禁，生产 Workflow 也尚未下载 semantic attestation、
  repository/org secret inventory 或调用本 verifier；因此这两处明确保持“未完成”，不能把现有 Workflow 视为安全
  发布入口。本轮不为赶发布接线，后续必须先加入 semantic trust 严格模式并用攻击测试证明失败时 SSH 次数为 0。
- 旧三个 `*_EVIDENCE_SHA256` 只能作为历史诊断，不再足以通过严格模式。
- release receipt 通用 helper 拒绝 `previousReceiptSha256=null`；当前无 genesis 的服务器仍然无法
  `begin-snapshot`。
- 本轮不变更产品 CLI，因此 operator Skill 暂不调整命令映射。未来 SSH broker、Workflow 输入或发布操作方式接线时，
  必须同步更新 `docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md` 与已安装生产 Skill 文档。

## 9. 外部完成条件

以下都属于仓外证据，缺一不可：

1. 由独立管理员取得精确生产 host key 并离线核对，生成受签名 SSH attestation；
2. 在 environment 创建分离的 execution/upload key，删除 environment/repository/organization 三层旧 key，并证明
   GitHub 历史 workflow 不能再读取；
3. 在服务器安装经过 SHA 核对的 broker，按精确 options 写入两个新公钥，删除旧公钥并复验完整
   `authorized_keys`；
4. 在独立受保护 bootstrap 流程采集运行镜像、配置、fingerprint 和 receipt subject，签发 bootstrap attestation；
5. 受控安装唯一 genesis receipt 与 sealed 状态，完成断电/重复/篡改/链遍历演练；
6. 把 Workflow 改为下载并验证上述 artifact，使用分离 key 与固定 broker 请求，删除所有 inline remote shell、scp/SFTP
   和宽权限 stdin 路径；
7. GitHub production environment、main ruleset、reviewer、bypass/audit 日志与固定 action/runner 供应链另行复验。

完成这些条件前，不得把本基础纵切描述为“生产发布通道已安全”“forced-command 已安装”或“genesis 已建立”。

## 10. 验收

- signed SSH/bootstrap attestation 的 create/verify、canonical、TTL 和 subject 比对通过；
- signed `server.hostPublicKeySha256` 缺失或与独立 host key/known_hosts 任一不一致均失败；known_hosts host/key
  交换、authorized_keys 旧 key/缺 restrict/命令漂移、三层旧 secret 任一残留均失败；
- 所有证据读取使用 `O_NOFOLLOW` 打开的单链接普通文件描述符；mode/size/nlink 受限，读取前后
  dev/ino/size/mode/mtime_ns/ctime_ns 任一漂移均失败；
- 签名、payload、proof、SHA、时间或外部 GitHub run provenance 任一漂移均失败；
- bootstrap 状态跳步、换 attestation、第二个 genesis、receipt 断链/环/第二个 null 均失败；
- broker 原命令注入、未知/跨角色 operation、额外字段、非 canonical JSON、shell 元字符均失败；
- strict environment mode 缺 semantic evidence 时在任何 SSH 前失败；
- 相关 pytest、Ruff、Mypy、shell `-n` 与 `git diff --check` 全绿；测试不联网、不读取真实 secret、不访问真实环境。
