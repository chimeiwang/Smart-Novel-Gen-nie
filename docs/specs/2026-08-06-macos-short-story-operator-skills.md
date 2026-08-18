# macOS 中短篇操作员 Skills 迁移与安装规格

## 状态

- 日期：2026-08-06
- 状态：已实现；已完成本地回环代理污染与传输错误映射回归修复
- 目标平台：macOS 15、Apple Silicon
- 安装位置：`~/.codex/skills/`

## 背景

现有 `inkforge-short-story-operator` 与
`inkforge-production-short-story-operator` 由 Windows 环境导出，入口、配置路径和测试依赖
PowerShell。当前 Mac 未安装 `pwsh`，但具备 Python 3、Codex CLI、Node.js、npm、curl 和 jq。

当前工作分支落后远端 `main`，且包含大量未提交改动；远端 `origin/main@e9cbf576` 已包含完整的
`long.*` CLI 注册表与测试。迁移不得为了取得该实现而覆盖、切换或合并当前脏工作区，应使用独立的
detached worktree 作为两个 Skill 的 CLI 运行根目录。

用户确认以行为一致为目标，允许直接修改两个 Skill，不要求保留 PowerShell 文件或安装兼容层。

## 当前项目事实

- 当前工作区位于 `codex/agent-bounded-concurrency`，有未提交改动，不允许直接切换或合并 main。
- `origin/main@e9cbf576` 的 InkForge CLI registry 已实现 3 条 auth、13 条 short 和 29 条 long 命令。
- 仓库 CLI 默认凭据实现只接受 Windows Credential Manager；macOS 必须由 Skill 注入安全适配，
  不能回退为明文文件。
- 当前机器已有可用的 uv 0.7.13 和 Python 3.12.10，无需安装 PowerShell。

## 目标

- 把两个 Skill 安装到 Codex 默认个人 Skill 目录。
- 使用 macOS 自带环境可运行的 Python 3 入口替代 PowerShell 入口。
- 同时支持远端 `main` 已实现的 `short.*` 与 `long.*` 命令，不以旧分支的缺失实现收窄附件契约。
- 保持命令白名单、参数约束、身份预检、退出码和标准输出/错误输出透传行为一致。
- 本地 Skill 继续使用本地环境；生产 Skill 固定使用 `https://inkforge.cn` 和隔离的
  `production` profile，禁止回退到 HTTP 或其他地址。
- 保持工作稿、完整 Diff、确认哈希、幂等标识、候选采用和恢复边界不变。
- 提供可在 macOS 上离线运行的结构校验和 wrapper 测试。
- 本地 Skill 访问 `127.0.0.1` 时必须强制直连，不得继承 `HTTP_PROXY`、`HTTPS_PROXY` 或
  `ALL_PROXY`；Core API 未启动时应返回明确的传输连接错误，不能显示代理生成的 HTTP 502。

## 非目标

- 不修改 Web、Core API、Agent Service、服务契约、PostgreSQL schema 或生产服务器。
- 不新增业务命令，不访问 `/internal/v1/**`，不直连 PostgreSQL、Redis 或 Agent Service。
- 不把密码、Cookie、Token 或其他凭据写入 Skill 配置、命令行、输出或测试夹具。
- 不在测试中提交版本、采用候选、恢复历史版本或启动会产生模型费用的任务。
- 不安装 PowerShell、Rosetta 或其他仅用于兼容旧实现的运行时。
- 不把远端 `main` 强制合并、rebase 或 checkout 到当前含未提交改动的工作区。

## 设计方案

### 安装与文件布局

从用户提供的两个源目录复制必要的 `SKILL.md`、`agents/`、`references/` 和业务规则到
`~/.codex/skills/<skill-name>/`。安装后的目录为权威运行副本，微信临时目录只作为输入，不在其中
保存配置或运行产物。

使用已更新的 `origin/main` 创建独立 detached worktree，wrapper 配置固定到该 worktree。该运行副本
只提供当前 main 的 CLI 代码和锁文件，不替代用户正在工作的分支，也不承载 Skill 状态或凭据。

删除 PowerShell 运行入口和 Pester 测试，分别提供 Python 3 `run.py` wrapper、配置脚本及 `unittest`
测试。脚本使用 `pathlib`、`subprocess` 和参数数组，不通过 shell 拼接命令。

### 路径与配置

- 仓库根目录必须解析为包含远端 main 当前 InkForge CLI 包的绝对目录。
- 两个 Skill 都不在文件中保存凭据；保留 CLI profile 语义，并由 wrapper 注入原生 macOS Keychain
  凭据存储。
- 生产 Skill 的非敏感操作员配置放在 macOS 用户应用支持目录下；配置写入使用临时文件加
  `os.replace()` 原子替换。
- 快照目录和 profile 由 CLI 管理；wrapper 不复制认证、HTTP、SSE 或版本状态机实现。

### 进程与输出

- wrapper 只允许文档化命令和精确参数数量，拒绝调用方覆盖 origin、profile 或预期用户名。
- 使用 macOS `/usr/bin/python3` 启动标准库 wrapper，再由已固定的 uv 环境启动仓库内 CLI；保留调用方
  标准输入，并实时继承 stdout、stderr。
- wrapper 返回 CLI 原始退出码；启动前错误返回非零退出码和明确中文诊断。
- 当前 main 对 auth/short 的 `CoreTransportError` 仍回退为通用退出码 1；macOS 适配器必须把所有
  `CoreTransportError` 统一映射为 CLI 已定义的退出码 5 和 `CORE_TRANSPORT_ERROR`，不得泄露成
  `UNEXPECTED_ERROR`。
- macOS 以 UTF-8 运行，JSON、JSONL、正文和 Diff 不做截断或重新编码。
- 除登录、身份查询和退出外，每个业务命令先执行静默 `auth.whoami`，并核对预期身份。

### 本地回环网络

- 本地 Skill 为 Core API 客户端显式注入直连 HTTP transport，确保回环请求不读取环境代理；CLI
  子进程仍可保留代理变量供 uv 获取已锁定依赖。
- 本地 `auth.login` 在调用隐藏密码输入前，先用同一直连客户端读取 `/api/v1/health/ready`；未就绪时
  返回结构化 Core 错误且不得显示密码提示。
- 只在固定为 `http://127.0.0.1:8000` 的本地 Skill 中关闭环境代理；生产 Skill 保持 CLI 默认网络
  行为，允许用户按环境需要使用可信代理。
- 回归测试必须同时设置不可用或会返回错误的 `HTTP_PROXY`，并证明本地 Core 客户端仍使用显式直连
  transport，同时 uv 子进程环境保留代理配置。
- 回归测试必须证明 ready 探针先于密码提示执行，探针失败时密码回调不会被调用。

### 生产边界

- 生产 origin 固定为 `https://inkforge.cn`，profile 固定为 `production`。
- 不保留旧 IP、HTTP 放行变量、SSH 隧道或 Windows Credential Manager 说明。
- `auth.login` 只在真实交互终端运行；密码由 CLI 隐藏读取，Skill 不接触密码值。

## 影响范围

- 新增本规格。
- 新增或更新 `~/.codex/skills/inkforge-short-story-operator/`。
- 新增或更新 `~/.codex/skills/inkforge-production-short-story-operator/`。
- 不修改现有仓库业务实现和数据库结构。

## 验收标准

- 两个目录均通过 `skill-creator` 的 `quick_validate.py`。
- `agents/openai.yaml` 与各自 `SKILL.md` 的名称、描述和默认提示一致。
- 所有离线 Python 测试在 macOS 上通过，并覆盖 Unicode、长 JSONL、short/long 精确命令白名单、
  参数拒绝、身份预检、固定生产 HTTPS、退出码与 stderr 透传。
- 两个 `run.py` wrapper 的帮助或无网络校验命令可直接由 `python3` 运行，不依赖 PowerShell。
- 在不会写业务数据或产生模型费用的前提下，完成远端 main CLI 契约检查；若已有有效登录态，可额外执行
  `auth.whoami` 和 `short.list` 只读冒烟。
- 安装副本中不再出现可执行的 `.ps1` 入口、Windows 盘符、`LOCALAPPDATA`、HTTP 生产地址或 SSH
  隧道依赖。
- 在设置 `HTTP_PROXY` 且不设置 `NO_PROXY` 的环境中，本地适配器仍绕过代理；Core API 未监听时返回
  `CORE_TRANSPORT_ERROR`，不得返回代理的 `HTTP_502`。
- 本地与生产 Skill 的 auth、short、long 命令遇到 Core 传输失败时，都返回退出码 5 和结构化
  `CORE_TRANSPORT_ERROR`，不返回退出码 1 或 `UNEXPECTED_ERROR`。

## 实施结果

- 已抓取并固定 `origin/main@e9cbf576`，使用
  `~/.codex/inkforge-main-runtime` detached worktree，未切换、合并或覆盖当前脏工作区。
- 两个 Skill 已安装到 `~/.codex/skills/`，使用 `scripts/run.py`、严格 origin/profile 绑定和
  Security.framework macOS Keychain 适配；本地固定 `http://127.0.0.1:8000/default`，生产固定
  `https://inkforge.cn/production`。
- wrapper 的 45 条 allowlist 已与远端 main registry 做集合级精确比较；本地 15 项、生产 12 项
  离线/真实 uv 加载测试通过，原生 Keychain 临时令牌写入、读取、删除闭环通过。
- 远端 main 的 `tools/inkforge-cli/tests` 共 258 项通过，CLI Ruff 与 Mypy 通过；两个 Skill 通过
  `quick_validate.py` 和 E/F/I Ruff 基础规则。
- `https://inkforge.cn/api/v1/health/live` 通过可信 HTTPS 返回 200；本地 8000 端口当前未启动。
- 默认操作员配置已写入并固定 revision，但未保存预期用户名或任何凭据。首次
  `auth.login --username ...` 成功后 wrapper 才原子绑定用户名；未登录前业务命令明确停止。
- 真实用户回归发现本机代理变量会接管 `127.0.0.1` 登录请求并返回空 HTTP 502；本地适配器现已为
  Core 客户端注入显式直连 transport，生产适配器继续保留用户代理行为。
- 使用真实伪终端验证：Core 未监听时本地 `auth.login` 会在密码提示前返回退出码 5 与
  `CORE_TRANSPORT_ERROR`，不会读取密码或写入 Keychain，也不再返回 `HTTP_502` 或
  `UNEXPECTED_ERROR`。
