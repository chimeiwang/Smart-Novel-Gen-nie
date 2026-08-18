# 生产环境中短篇 Codex Skill 规格

## 状态

- 初始日期：2026-08-04
- 直连变更确认日期：2026-08-05
- macOS Skill 迁移完成日期：2026-08-06
- 状态：服务器 HTTPS 与 macOS 个人 Skill 均已实现
- 当前生产入口：`https://inkforge.cn`

服务器端已于 2026-08-05 启用可信 HTTPS，并恢复生产 `Secure` Cookie。个人
`inkforge-production-short-story-operator` Skill 已按
`2026-08-06-macos-short-story-operator-skills.md` 安装并迁移到 macOS Keychain、固定 HTTPS wrapper 和
远端 main CLI 运行副本。下文保留的是此前已确认的临时公网 HTTP 直连设计，只用于历史追溯和迁移
核对，其中的 IP/HTTP origin、明文风险确认、Windows 路径和放行变量都不再是当前生产操作指引。

## 已完成迁移边界

- 把生产 origin 固定为 `https://inkforge.cn`，继续使用隔离的 `production` profile。
- 删除 Skill 中的 `INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN` 注入、`acceptedInsecureHttp` 配置和明文风险说明。
- 迁移不得保留到 IP/HTTP 的静默降级路径；身份核验、命令白名单、Diff、确认哈希和恢复边界保持不变。
- macOS 安装副本使用 `scripts/run.py` 与 Security.framework Keychain 适配，并把 45 条命令白名单固定到
  `origin/main@e9cbf576` 的真实 registry。

## 历史背景与决策

本机已有 `inkforge-short-story-operator`，它通过仓库内 `inkforge-cli` 操作本地 Core 公共接口。
独立的 `inkforge-production-short-story-operator` 已按相同业务流程创建，初始实现使用 SSH 隧道
保护公网 HTTP 链路。

当时的生产入口只有 HTTP：实测 `http://124.71.85.180/` 返回 200，HTTPS 端口连接超时。现有 CLI
默认拒绝远程 HTTP，只允许回环 HTTP 或远程 HTTPS，避免密码和会话 Cookie 明文经过公网。

用户已明确接受固定生产入口上的明文 HTTP 风险，并批准移除 SSH 隧道。新设计不再登录服务器、
不使用 `root`、不执行远程命令；本机 CLI 直接访问生产 Nginx。CLI 的默认安全限制仍然保留，只有
生产 Skill 启动的子进程显式放行且只能放行 `http://124.71.85.180`。

## 目标

- 生产 Skill 直接调用 `http://124.71.85.180/api/v1/**`，不再依赖 SSH。
- 继续复用现有 `inkforge-cli`、Core 登录、归属、并发、Diff、确认和版本状态机。
- 固定使用 CLI `production` profile，与本地 `default` profile 和快照目录隔离。
- 远程 HTTP 放行必须是显式、单地址、进程级的；普通 CLI 调用仍默认拒绝远程 HTTP。
- 每轮接管和每个业务命令前继续核验预期 InkForge 用户身份。

## 非目标

- 不为所有远程 HTTP 地址取消 CLI 限制。
- 不登录生产服务器，不建立 SSH 隧道，不使用服务器 `root` 账号。
- 不修改生产 Nginx、Compose、Core API 或生产环境变量。
- 不直连 PostgreSQL、Redis、Agent Service 或 `/internal/v1/**`。
- 不支持 `long_serial`，不新增小说业务命令。
- 不自动提交版本、采用候选、恢复版本或连续启动 Agent 阶段。
- 本次不配置 TLS；生产提供可信 HTTPS 后应取消明文放行。

## 方案选择

已比较三种方案：

1. **CLI 精确地址显式放行（采用）**：CLI 保留默认拒绝，只在环境变量精确匹配时允许一个远程
   HTTP origin；生产 Skill 为子进程注入固定值。
2. **全局允许远程 HTTP（拒绝）**：改动少，但会让任意远程地址都能接收密码和 Cookie。
3. **Skill 重写 HTTP 客户端（拒绝）**：会复制认证、凭据、SSE、错误码和版本控制逻辑，形成第二
   套不一致的客户端。

采用方案 1，因为它既取消 SSH，又保持现有 CLI 为唯一业务客户端，并把用户接受的风险限制在明确
的生产地址和明确的 Skill 进程内。

## 架构与数据流

```text
本机 Codex
  -> inkforge-production-short-story-operator
  -> scripts/operator.ps1
  -> 本机 inkforge-cli
     origin=http://124.71.85.180
     profile=production
     INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN=http://124.71.85.180
  -> 生产 Nginx
  -> Core /api/v1/**
```

密码和会话 Cookie 会在公网 HTTP 链路中明文传输，这是用户明确接受的已知风险。Skill 和 CLI 不得
用含糊措辞把该链路描述为安全或加密。

## CLI 精确放行

`tools/inkforge-cli` 新增进程级环境变量：

```text
INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN
```

规则如下：

- 未设置时，行为完全不变：远程 HTTP 仍被拒绝。
- 只接受规范化后的完整 origin，不接受路径、查询、片段、用户信息或通配符。
- 仅当待访问 origin 与环境变量的规范化值完全相同时，才允许远程 HTTP。
- HTTPS 和回环 HTTP 的原有行为不变。
- 生产 Skill 把变量固定为 `http://124.71.85.180`；调用方不能覆盖。
- CLI 不在 stdout、日志或配置文件中打印该环境变量以外的凭据内容。

这个开关是用户主动接受风险后的窄范围逃生口，不改变 Core API 的认证和权限校验。

## 生产 Skill

Skill 继续安装在：

```text
C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\
├── SKILL.md
├── agents\openai.yaml
├── scripts\configure.ps1
├── scripts\operator.ps1
└── references\
    ├── cli-contract.md
    └── recovery.md
```

### `configure.ps1`

配置文件仍位于：

```text
%LOCALAPPDATA%\InkForge\production-codex-operator\config.json
```

新配置只包含：

```json
{
  "schemaVersion": 2,
  "repositoryRoot": "F:\\code\\inkForge",
  "expectedUsername": "示例用户",
  "acceptedInsecureHttp": true
}
```

配置命令必须显式提供 `-AcceptInsecureHttp`。脚本打印简短风险提示，但不得读取、保存或输出
InkForge 密码、Cookie 或 Token。旧版包含 SSH 字段的 schema v1 配置不自动猜测迁移；用户重新
运行配置命令后原子覆盖为 schema v2。

### `operator.ps1`

wrapper 每次调用：

1. 校验 schema v2 配置、仓库、`uv` 和 CLI 包。
2. 拒绝未知命令、额外参数，以及调用方提供的 `origin`、非 `production` profile 或其他预期用户。
3. 固定准备 `origin=http://124.71.85.180` 和 `profile=production`。
4. 仅在调用 CLI 子进程期间，把
   `INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN` 设置为固定生产 origin；结束后恢复调用前的环境值。
5. 除 `auth.login`、`auth.whoami` 和 `auth.logout` 外，先执行一次静默 `auth.whoami` 身份预检。
6. 原样保留 CLI 的 stdout、stderr、JSONL 流和退出码。

wrapper 不再解析 SSH 用户、私钥、`known_hosts`、本地转发端口或隧道进程，也不调用任何 SSH
程序。

`auth.login` 仍是唯一交互命令。wrapper 固定注入配置中的用户名、生产 origin 和 `production`
profile；密码只能由用户在真实 TTY 的隐藏提示中输入。

### `SKILL.md` 与 references

- 明确说明生产 Skill 直接使用固定公网 HTTP，用户已接受明文传输风险。
- 禁止临时改成其他 IP、域名、端口或 profile。
- 删除 SSH、主机键、端口占用和隧道恢复说明。
- 保留 401、403、409、SSE 中断、幂等 ID、dirty 工作稿、完整 Diff 和确认哈希规则。
- 保留本地 Skill 与生产 Skill 的触发隔离。

## 身份与凭据

- InkForge 用户名写入非敏感生产操作员配置和 CLI profile。
- InkForge Token 只保存在 Windows Credential Manager。
- InkForge 密码只由用户在真实 TTY 中输入，不进入 Codex 上下文、配置、命令行、stdout 或日志。
- 网络传输仍是明文 HTTP；Windows Credential Manager 只保护本机静态存储，不能保护公网链路。
- 每轮先执行 `auth.whoami`，返回用户名必须与配置中的 `expectedUsername` 完全一致。

## 中短篇业务边界

连接方式改变不改变业务流程：

1. `short.list` 只列出当前登录用户拥有的 `short_medium` 作品。
2. `short.pull` 导出完整文件和 manifest 到生产专用快照目录。
3. `short.draft.save` 只保存工作稿，不创建版本。
4. `submit`、`adopt`、`restore` 必须先取得完整 Diff，并由用户确认同一 `confirmationHash`。
5. Agent 只生成候选，不自动采用，也不自动连续启动下一阶段。
6. 网络结果不确定时保留原 `clientRequestId`、taskId 和 `Last-Event-ID` 对账。

生产快照继续使用：

```text
%LOCALAPPDATA%\InkForge\production-codex-operator\snapshots\
```

## 失败处理

- 未显式接受风险、配置缺失或 schema 不是 v2：联网前停止并要求重新配置。
- 环境变量缺失、不等于固定生产 origin 或被调用方尝试覆盖：联网前停止。
- `401` 或 `403`：停止业务操作，由用户在真实终端重新执行 `auth.login`，再核验身份。
- `409`：保留本地快照，重新 pull 和 preview；不自动覆盖、合并或变基。
- SSE 或普通请求结果不确定：保留原任务和幂等标识读取权威状态，不生成新 ID 重试。
- 生产入口不可达：报告直接 HTTP 连接失败，不尝试 SSH、其他地址或内部接口。
- 生产启用可信 HTTPS 后：先迁移 profile 和凭据，再删除明文放行；不同时保留静默降级路径。

## 测试设计

### CLI 测试

- 默认情况下继续拒绝 `http://124.71.85.180` 和其他远程 HTTP。
- 环境变量精确为 `http://124.71.85.180` 时只允许该 origin。
- 地址不匹配、通配符、携带路径、查询、片段或用户信息时拒绝。
- 回环 HTTP 与远程 HTTPS 的既有测试继续通过。
- API、配置和 Windows Credential Manager 使用同一套 origin 校验结果。

### Wrapper 测试

- schema v1、缺少风险确认或配置字段异常时不会调用 CLI。
- 不依赖或调用 `ssh`、`ssh-keygen`，也不监听本地端口。
- `auth.login` 精确传入固定生产 origin、配置用户名和 `production` profile。
- CLI 子进程能看到固定放行变量；调用结束后父进程原环境值被恢复。
- 调用方不能覆盖 origin、profile、预期用户名或放行变量。
- 身份预检、JSON 深度、Unicode、退出码、stderr 和 JSONL 实时输出继续通过。
- PowerShell 管道 JSON 能到达 wrapper。

### Skill 验证

- 新旧 Skill 均通过 `quick_validate.py`。
- 全文不再把 SSH 描述为生产调用前提。
- 生产 Skill 的示例、metadata、配置字段和 wrapper 行为一致。
- 真实冒烟最多执行 `auth.whoami` 和 `short.list`，登录密码仍由用户亲自输入。

## 影响范围

- 修改本机个人生产 Skill 的脚本和说明文件。
- 修改 `tools/inkforge-cli` 的 origin 校验及相关测试、README。
- 更新本规格和后续实施计划。
- 不修改 Web、Core API、Agent Service、共享契约、数据库、Compose 或生产服务器。

## 验收标准

- 生产 Skill 完全不需要 SSH 用户、私钥、主机键或隧道。
- 所有生产业务请求固定发往 `http://124.71.85.180/api/v1/**`。
- 普通 CLI 在没有显式精确放行时仍拒绝所有远程 HTTP。
- 配置明确记录用户已接受明文 HTTP，Skill 不把链路描述为安全。
- 登录身份、命令白名单、工作稿、Diff、确认、候选和恢复边界保持不变。
- 离线测试、CLI 相关 pytest、Ruff、Mypy、Skill 校验和真实只读冒烟全部通过。

## 回退与后续演进

回退时恢复 CLI 的严格远程 HTTPS 校验，并恢复或删除生产 Skill；不得遗留一个全局远程 HTTP
开关。生产 profile 的明文 HTTP origin 和对应 Windows Credential Manager 凭据应显式清理，不能
由 Codex 静默删除。

生产入口提供可信 HTTPS 后，生产 Skill 改为固定 HTTPS origin，删除
`INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN` 和风险确认字段；迁移前后都不得静默回退到 HTTP。
