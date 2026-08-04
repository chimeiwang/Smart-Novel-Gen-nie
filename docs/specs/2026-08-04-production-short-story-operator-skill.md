# 生产环境中短篇 Codex Skill 规格

## 状态

- 日期：2026-08-04
- 状态：设计已确认，尚未实施
- 生产主机：`124.71.85.180`
- 当前入口：`http://124.71.85.180/`

## 背景

当前本机 `inkforge-short-story-operator` 通过仓库内 `inkforge-cli` 操作 Core 公共接口，默认
profile 指向本机回环地址。生产入口暂时只有 IP/HTTP；Core 已提供默认关闭的
`ALLOW_INSECURE_HTTP_AUTH` 过渡配置，但 CLI 仍明确拒绝连接远程 HTTP，避免密码和会话凭据在
公网明文传输。

用户需要一套独立、可被 Codex 自动发现的生产操作 Skill。它必须固定目标生产主机，不能与本地
操作员混用，也不能为了临时 HTTP 入口删除 CLI 的远程 HTTPS 防线。

本规格显式取代 `2026-07-30-short-medium-writing-workflow.md` 中“不并存第二个相似触发 Skill”
的旧限制；本地与生产环境现在通过两个名称、触发条件和 wrapper 明确隔离。

## 当前项目事实

- 本机现有 `inkforge-short-story-operator` 通过绝对路径 wrapper 定位当前仓库并运行
  `tools/inkforge-cli`，不要求生产镜像包含 CLI。
- CLI 只接受 `/api/v1/**` 公共路径，远程 origin 必须使用 HTTPS；HTTP 只允许 loopback。
- 生产 Nginx 把 `/api/v1/**` 转发到 Core，并直接拒绝 `/internal/**`。
- 生产 Compose 当前发布 HTTP 入口，并为浏览器提供默认关闭的
  `ALLOW_INSECURE_HTTP_AUTH` 临时兼容开关；该开关不取消 CLI 的远程 HTTP 防线。
- 当前本机 CLI `default` profile 指向回环开发环境，生产环境尚无独立操作 Skill。

## 目标

- 新增本机 Skill `inkforge-production-short-story-operator`，只操作生产环境的
  `short_medium` 作品。
- 固定生产主机为 `124.71.85.180`，通过本机 SSH 加密隧道访问生产 HTTP 入口。
- 复用现有 `inkforge-cli`、Core `/api/v1/**`、登录、归属、并发、Diff、确认和版本状态机。
- 固定使用 CLI `production` profile，并与本地 `default` profile、快照和配置目录隔离。
- 任何隧道、身份或网络状态不确定时停止，不降级为公网直连 HTTP。

## 非目标

- 不为生产容器安装 CLI，不在服务器内运行 Codex。
- 不修改 CLI 的远程 HTTP 校验，不启用新的公共或内部接口。
- 不直连 PostgreSQL、Redis、Agent Service 或 `/internal/v1/**`。
- 不支持 `long_serial`，不增加新的小说业务命令。
- 不自动提交、采用候选、恢复版本或连续启动下一阶段 Agent。
- 本阶段不配置 TLS；将来 HTTPS 直连另行变更并验证。

## 设计方案

### 架构

```text
本机 Codex
  -> inkforge-production-short-story-operator
  -> 本机 scripts/operator.ps1
  -> 本机 inkforge-cli，origin=http://127.0.0.1:18080，profile=production
  -> SSH 隧道 127.0.0.1:18080 -> 124.71.85.180:80
  -> 生产 Nginx
  -> Core /api/v1/**
```

SSH 隧道是临时 HTTP 入口的传输加密层。CLI 看到的仍是被允许的回环 HTTP，公网链路只传输 SSH
密文。生产主机、远端端口和本地转发端口属于 Skill 的固定安全边界，不接受每次调用覆盖。

### Skill 结构

Skill 安装到：

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

#### `SKILL.md`

- 触发条件必须同时包含 InkForge、生产环境、远程生产、线上或 `124.71.85.180` 等明确语义。
- 明确禁止调用本地 `inkforge-short-story-operator` 代替生产 Skill。
- 只允许调用本 Skill 的 `scripts/operator.ps1`，不得自行拼接 HTTP、SSH 或 CLI 命令。
- 继承现有中短篇操作员的身份、工作稿、Diff、确认、Agent 候选和恢复边界。
- 每轮接管和每个写操作前必须执行 `auth.whoami`，并核对配置中的预期用户名。

#### `scripts/configure.ps1`

配置脚本只写入非敏感配置：

```text
%LOCALAPPDATA%\InkForge\production-codex-operator\config.json
```

配置包含 `schemaVersion`、本机仓库绝对路径、SSH 用户、预期 InkForge 用户、可选 SSH 私钥路径和
受信 `known_hosts` 文件路径。配置脚本必须确认该文件中已有 `124.71.85.180` 的受信记录。生产
IP、远端端口 `80`、本地端口 `18080` 和 profile
`production` 固定在 wrapper 中，不写成可变配置。

配置脚本不得读取、保存或打印 SSH 私钥内容、InkForge 密码、Cookie 或 Token。SSH 只允许密钥、
ssh-agent 或 OpenSSH 配置提供的非交互认证，不支持把 SSH 密码交给 Codex。

#### `scripts/operator.ps1`

wrapper 每次调用执行以下顺序：

1. 校验本机配置、仓库、`uv`、`ssh`、`known_hosts` 和可选私钥路径。
2. 确认 `127.0.0.1:18080` 未被其他进程占用。
3. 使用 `BatchMode=yes`、`StrictHostKeyChecking=yes`、固定 `UserKnownHostsFile` 和
   `ExitOnForwardFailure=yes` 启动隐藏 SSH 子进程，将本地 `18080` 转发到生产主机回环地址的
   `80` 端口。
4. 等待本地端口可连接；SSH 提前退出或超时则停止，不启动 CLI。
5. 除 `auth.login`、`auth.whoami` 和 `auth.logout` 外，先用配置中的预期用户名执行一次
   `auth.whoami`；身份校验失败则不执行目标命令。
6. 调用仓库内 `uv run --package inkforge-cli inkforge` 执行目标命令。
7. 在 `finally` 中结束本次 wrapper 创建的 SSH 子进程，不遗留常驻隧道。

`auth.login` 不接受调用方覆盖用户名、origin 或 profile；wrapper 从本机非敏感配置读取预期用户名，
并固定注入 `--origin http://127.0.0.1:18080 --profile production`。其他命令必须解析 stdin JSON，
拒绝调用方指定其他 profile，并统一注入 `"profile":"production"` 后交给 CLI。wrapper 不解释
小说业务，不修改 `clientRequestId`、taskId、manifest 或确认摘要。显式 `auth.whoami` 还必须固定
注入配置中的 `expectedUsername`，不能由调用方覆盖成其他身份。

#### References

- `cli-contract.md` 记录生产 profile、命令面、文件协议、确认摘要和一次完整只读示例。
- `recovery.md` 记录 401、409、SSH 失败、端口占用、SSE 中断和网络结果不确定时的恢复边界。
- 两份 reference 不复制 CLI 源码字段全集，只记录生产操作需要的稳定规则。

#### 现有本地 Skill 隔离

现有 `inkforge-short-story-operator` 的 description 和正文入口必须收窄为本地开发、loopback 或
`127.0.0.1` 场景，并明确把生产、线上、远程生产和 `124.71.85.180` 交给新 Skill。只调整触发与
环境边界，不改变现有本地 wrapper、命令面或业务操作流程。

### 配置与凭据

- `production` profile 的 origin 固定为 `http://127.0.0.1:18080`。
- profile 的 origin 与用户名保存在现有 CLI JSON 配置中。
- InkForge 会话 Token 只保存在 Windows Credential Manager。
- InkForge 密码只由用户在真实 TTY 的隐藏输入中填写；Codex 不接收、读取或转述。
- SSH 主机公钥必须由用户通过可信渠道核验后写入指定 `known_hosts`；禁止运行时
  `ssh-keyscan`、`StrictHostKeyChecking=no` 或自动接受新主机键。
- SSH 私钥文件路径可以进入非敏感配置，但私钥内容和口令不得进入 Skill 配置、命令行、日志或
  Codex 上下文。

### 标准数据流

#### 一次性配置与登录

1. 用户运行 `configure.ps1`，提供仓库路径、SSH 用户、预期 InkForge 用户和受信主机键文件。
2. 用户在真实终端运行生产 wrapper 的 `auth.login`。
3. wrapper 建立 SSH 隧道，CLI 隐藏读取 InkForge 密码并写入 `production` profile 与 Windows
   Credential Manager，然后 wrapper 关闭隧道。
4. 用户或 Codex 执行 `auth.whoami` 验证生产身份。

#### 日常操作

1. Codex 触发生产 Skill。
2. 先调用 `auth.whoami`，确认返回用户名与配置一致。
3. `short.list` 定位生产作品，`short.pull` 拉取到生产专用快照根目录。
4. 后续保存、预览、提交、Agent、采用和恢复继续遵循现有受控流程。
5. 每个 wrapper 调用独立创建并关闭 SSH 隧道；会话 Token 可跨隧道复用。

生产快照统一放在：

```text
%LOCALAPPDATA%\InkForge\production-codex-operator\snapshots\
```

不得与本地 Skill 的快照目录复用。

### 失败处理

- 缺少配置、`uv`、`ssh`、仓库或 CLI 包：在联网前停止。
- SSH 用户、主机键、密钥、agent 认证或服务器 TCP 转发策略不满足要求：停止并让用户在真实
  终端修复，不要求 Codex 接收 SSH 密码，也不修改服务端 SSH 配置。
- 本地端口已占用：停止；不得复用无法证明归属的既有监听进程。
- SSH 隧道建立失败或中途退出：停止当前 CLI 调用，不降级到 `http://124.71.85.180`。
- `401`：停止业务操作，要求用户重新执行生产 `auth.login`，随后重新 `auth.whoami`。
- `409`：保留本地快照并报告冲突，不自动覆盖、合并或切换版本重试。
- SSE 或普通请求结果不确定：保留原 `clientRequestId`、taskId 和 `Last-Event-ID` 对账。
- wrapper 退出时只终止自己创建的 SSH 子进程，不结束用户其他 SSH 会话。

### 测试设计

#### Skill RED/GREEN 场景

创建 Skill 前，使用不加载新 Skill 的子 Agent 运行至少三类只读压力场景，记录其是否误用本地
Skill、直接访问公网 HTTP、遗漏 `production` profile 或跳过 `auth.whoami`。创建后用相同场景
加载新 Skill，要求全部遵守生产 wrapper 与停止边界。

场景测试不得执行生产写操作。需要真实连通性时最多执行用户已授权的 `auth.whoami` 和
`short.list`；登录仍由用户在真实 TTY 完成。

#### Wrapper 测试

使用临时目录和 PATH 中的假 `ssh`、`uv` 可执行文件验证：

- 缺少或损坏配置时不会联网。
- 固定使用 `124.71.85.180`、远端端口 `80`、本地端口 `18080` 和严格主机键参数。
- `auth.login` 固定注入配置中的预期用户名、回环 origin 与 `production` profile。
- JSON 命令拒绝非生产 profile，并正确注入 `production`。
- `auth.whoami` 固定注入预期用户名，业务命令会先完成身份预检，失败时不会调用目标接口。
- SSH 未就绪、提前退出、端口占用和 CLI 非零退出码都被保留并停止。
- 成功、失败和中断路径都会清理本次 SSH 子进程。
- stdout 保持 CLI JSON/JSONL，诊断只写 stderr，不输出敏感数据。

#### 结构验证

- 使用 Skill Creator 的 `quick_validate.py` 校验目录、frontmatter 和命名。
- 检查 `agents/openai.yaml` 与 `SKILL.md` 的触发语义一致。
- 检查 `SKILL.md` 保持简短，详细命令和恢复规则位于 references。

## 影响范围

- 新增一个本机个人 Skill 及其非敏感本机配置。
- 收窄现有本地 Skill 的触发描述，避免生产请求同时命中两个 Skill；不改变其运行行为。
- 更新中短篇工作流规格，允许本地与生产两个环境明确分离的 Skill。
- 不修改 Web、Core API、Agent Service、共享契约、数据库结构、Compose 或生产 `.env`。
- 不把个人 Skill 文件提交到 InkForge 仓库；仓库只保留本规格与后续实施计划。

## 验收标准

- Codex 在用户明确提到生产、线上、远程生产或 `124.71.85.180` 时选择新 Skill；本地任务仍选择
  原 Skill。
- 新 Skill 只调用自己的 wrapper，所有业务请求仍由现有 CLI 发往 `/api/v1/**`。
- 公网 HTTP 上不出现 InkForge 密码或会话 Token；远程 HTTP 校验保持不变。
- 生产 IP、端口与 `production` profile 不能由一次业务调用覆盖。
- 身份不匹配、SSH 失败、端口占用、401、409 或网络不确定时停止，不执行扩展写操作。
- 现有工作稿、Diff、确认、候选采用和恢复边界完整保留。
- 本地 Skill、default profile 和本地快照目录不受影响。
- wrapper、Skill 场景和结构验证全部通过后才视为安装完成。

## 回退与后续演进

回退时删除新 Skill 目录和生产操作员非敏感配置，不修改现有本地 Skill。生产 profile 的会话凭据
应由用户先执行 `auth.logout` 或直接在 Windows Credential Manager 中删除，不能由 Codex 静默
清理。

生产入口提供可信 HTTPS 后，可用新规格把 wrapper 改为固定 HTTPS origin 并删除 SSH 隧道；在
迁移完成前不得同时保留可选的 HTTP 直连路径。
