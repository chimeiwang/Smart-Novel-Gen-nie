# macOS Operator Skill 的 Java CLI 入口切换

日期：2026-09-04。状态：本机 macOS 双 Skill 的 Java executable 切换与离线验收已完成。

## 目标与范围

用户要求完成 Agent 相关 CLI 配套，并继续完成实际 Skill executable 的 Java 切换。本次在当前
`codex/durable-agent-execution` 分支实现，把本机本地、生产两份 Operator Skill 的业务执行入口从
`uv → Python CLI` 改为 `shell → Java Operator → Java CLI → Core 公共 API`。

不修改 Agent 服务、Core 公共接口、125 个 CLI 命令名或数据库；不部署、推送、不调用真实写入命令，
不扩大 Skill 的 45 命令白名单或启用 `answer_question`。Python CLI 保留为契约对照，不作为新版
macOS Skill 的业务执行入口。Windows CLI 原生凭据支持保留，本次不宣称完成 Windows 实机验收。

## 设计

- 为现有 Java CLI 增加独立的 Operator 启动入口，不给公共命令注册表新增命令。
- 两份 Skill 使用自包含的 `scripts/configure.sh` 与 `scripts/run.sh`，不再启动 Python 或 uv。
  配置时安装当前本机已构建的 shaded JAR，并记录 Java 路径及来源提交；日常运行不触发构建、联网安装
  或修改源码仓库。保留旧 Python CLI 源码及已安装 Skill 的可恢复备份，不改旧 runtime checkout。
- 配置沿用各自的 Application Support 状态目录，升级为 schemaVersion 5；保留原有
  `expectedUsername`、固定 origin 与 profile。显式重新配置才替换运行包；不存在隐式 Python 回退。
  不传 `--expected-username` 时保留已有绑定；显式传入时可重新绑定账号，与旧 configure 能力一致，
  但配置器不修改会话，后续仍须通过新绑定用户名的身份核对。
- 本地始终绑定 `http://127.0.0.1:8000` / `default`；生产始终绑定 `https://inkforge.cn` /
  `production`。拒绝 payload origin、跨 profile、跨已绑定用户名和被改成其他 origin 的 CLI profile。
- 业务命令先执行 `auth.whoami` 校验绑定账号，再调用原有 Java 命令实现。登录仍只允许真实 TTY 读取密码；
  本地登录在读取密码前检查 `/api/v1/health/ready`，回环请求绕过代理。
- 原样保留 JSON / JSONL、完整输入输出、watcher、文件输出和退出码。Operator 中所有传输错误统一为
  `CORE_TRANSPORT_ERROR` / 5，原生安全凭据后端不可用统一为 `SECURE_CREDENTIAL_BACKEND_REQUIRED` / 3，
  不打印密码/token，不使用明文回退。
- Java 与既有 CLI 使用相同配置文件与 Keychain service/account，不读取、复制或重新写入用户 token。
  生产代理行为需要显式检查，不能因为更换语言而无声改变代理配置。
- 生产原生 HTTP 客户端支持无认证 HTTP 代理及 HTTPS CONNECT，解析大小写代理环境变量和 NO_PROXY。
  TLS/SOCKS/认证代理暂不支持，显式报 `OPERATOR_PROXY_UNSUPPORTED` / 2，不静默直连。本机现有代理是
  无认证 HTTP 代理，处于支持范围；这不是宣称与 Python httpx 的全部代理形态完全等价。
- `long.agent.start` 仍只允许 Skill 原有三种 operation；V2 watcher 与 artifact decision 复用已实现契约。
  Agent 不直接暴露给 CLI，所有网络业务调用仍由 Core 公共 API 承接。

## 验证与收口

1. Java 单元测试覆盖双环境绑定、白名单、身份预检、TTY、凭据错误、传输错误及配置升级；保留现有
   Python/Java CLI 对照测试，并运行完整 Maven verify。
2. 在隔离本机配置和模拟 Core 中验证真实 JAR、shell 入口、JSON/JSONL、错误退出和无 Python/uv 路径；
   不使用真实账号凭据或发起真实写作。
3. 备份后更新本机两份 Skill 及其配置，检查实际入口和安装包一致性。运行 Skill 结构检查与独立验收。
4. 同步根级事实、产品基线、CLI 文档、Skill 命令契约和迁移说明。明确“本机入口已切换”“真实服务器
   功能是否部署”“跨平台实机验收”是不同结果，不互相代替。

## 实际安装与验证结果

- 本机两份 Skill：`inkforge-short-story-operator` 与 `inkforge-production-short-story-operator`，均已使用
  `scripts/configure.sh` / `scripts/run.sh`。Java 21 与 JAR 安装到各自原状态目录下的 `runtime/`，
  `config.json` 已升级为 5。保留原 origin/profile/expectedUsername；没有访问、迁移或重写用户 token。
- 两份已安装 JAR 的 SHA-256 均为
  `5f16d669cb8dfc3f6da904da3c680f07079c1e0a9e9a189aa04e55a167fee37b`，与最终构建输出相同。
  来源记录为 `072f26e01780ba23c24ef3ac7fa66f0dc7ab8044` 加 `repositoryDirty=true`；这准确表示在该
  HEAD 的未提交工作区构建，不能把运行包说成已经包含在该提交中。未 push。
- 每份活动 Skill 中的四个旧 Python 启动/适配脚本及对应旧测试已移除。两份完整旧 Skill 和升级前配置的
  可恢复备份位于本机 `/Users/boqiangnie/.codex/inkforge-cli-cutover-backup.5CtzBq`；旧 runtime checkout
  未修改，仓内 Python CLI 契约对照源码仍保留。
- 最终兼容复核保留了旧配置器的显式换账号能力：升级省略用户名时保留绑定，用户显式重新 configure
  可以改绑定，但不会改 Keychain 会话。没有把此次 Java 迁移变成禁止用户切换账号的新限制。
- 完整 `./mvnw --batch-mode --no-transfer-progress verify`：5 个模块全部成功；服务身份 11 项、服务契约
  5 项、Core 650 项（3 项跳过）、CLI 107 项（无跳过），无失败。CLI 包含新增 Operator、代理、原生凭据
  异常测试，以及现有 125 命令最小输入和代表成功/文件/watcher 的 Python/Java 差异测试。
- Python CLI：578 passed；全仓架构检查：349 passed、3 skipped；Ruff 和 `git diff --check` 通过。
- `operator/test-launchers.sh`：真实 JAR 与双环境 shell 在隔离配置中通过安装、无 Python/uv 启动、无
  profile、命令白名单、origin 拒绝和包哈希检查。期间发现并修复测试脚本的中文邻接变量展开及清理退出码问题。
- 两份实际安装入口的 help 和配置加载/固定 origin 拒绝均通过，拒绝发生在读取会话及联网前。
  两份 Skill 的结构检查通过；独立前向验收补齐已有任务 payload 示例、waiting_user/完成区别、V2 文件
  编辑字段和 Keychain/401/403 恢复说明。具体升级步骤见 `tools/inkforge-cli-java/README.md`。

本次未执行真实账号登录/业务调用、服务器部署、数据库变更或远程写操作。Java 的原生凭据格式兼容已经验证，
不等于读取过用户真实会话；如系统要求允许 Java 读取既有 Keychain 项，由用户确认，再先执行 whoami。
未完成的真实服务器 V2 上线、问答开放和 Windows 实机验收不属于本次完成声明。
