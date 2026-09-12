# Java-only Core／CLI 清理验收

日期：2026-09-12

状态：代码迁移与构建修复已实施，Java／Python／Web 回归通过；Compose 恢复演练受镜像仓库网络阻塞。
未推送、未部署、未修改服务器数据库。

## 范围与工作区

- 基于拉取时最新 `origin/main` 的 `7b1de237b3709612583932a516e9536520deebfa`，隔离分支为 `codex/java-only-core`。
- 本任务未覆盖原 `F:\code\inkForge` 的未提交修改，仓内实现只在 `.worktrees/java-only-core` 实施。
- 删除 Python Core／CLI 跟踪源码、旧导出器、Python Core rollback overlay 及已退出公共契约的 Java 旧视频实现；
  删除内容可从 Git 历史和原工作区恢复。没有删除服务器历史任务、候选、正式内容或数据库表。
- Python Agent、Pydantic 服务协议、Ed25519 鉴权和必要测试／运维脚本保留；Agent 仍不能访问数据库。

## 当前接口流程

唯一可编辑来源为 `contracts/core/openapi.json`。Java API interface／DTO、Java CLI 与公共 TypeScript 客户端
消费 canonical 或其生成公共投影。`npm run api:generate` 与 `api:check` 均从 canonical 检查或生成到 TS，
不会启动 Python Core，也不会仅比较两份过期生成物。

完整契约 207 操作，其中 public 182、internal 24、provider media 1。测试通过 Spring 的真实
`RequestMappingHandlerMapping` 双向核对路径／方法／consumes／produces；V2 条件路由使用已开启门禁的 mock
Controller 上下文，不启动业务后台任务或数据库。语言中立 HTTP、Cookie、SSE、鉴权和数据库 golden 继续保留。

## 构建修复与运维

- 删除失去 DTO 的旧 chapter adaptation／legacy video plan／render/take/post 实现及孤立装配；
  保留 Episode、VisualCanon、素材存储和共享 jOOQ／schema 投影，不执行 P4 物理退役。
- 修复最新配置更新后遗留的 manifest、预算边界测试，仍以冻结 Run 预算验证真正超额，不修改生产上限。
- `npm run dev` 先构建再启动 Java Core；Agent 仍为独立 Python 进程。
- 结构导出改为 Java。恢复验证显式指定数据库时不得回退查询运行 Core；TokenUsage 工作流导出使用独立
  192 MiB 容器，不在 448 MiB 活动 Core 内增加第二个 JVM。
- `.gitattributes` 固定原始字节校验资产为 LF，避免 Windows／归档导致合法历史 fixture 哈希漂移。

## 已取得的验证证据

- Web：371 项；API client：3 项；TypeScript、Lint、Next.js 生产构建通过。
- Node 契约生成测试：6 项；API 生成及漂移检查通过。
- Python Mypy：131 个 Agent／共享库源码无错误；Ruff 通过。
- Windows Python 全量回归（单独拆出运维迁移夹具文件）：3447 通过、20 个外部环境门禁跳过；
  命令设置 `PYTHONUTF8=1`，避免系统默认 GBK 解释既有 UTF-8 fixtures。
  拆出的迁移夹具在 Mac 上 77 项全通过，覆盖真实 PostgreSQL 14 pre／post／partial 结构；
  两组不重叠，合计 3524 通过、20 跳过。Windows 的 POSIX 0700／0600 文件权限用例明确按平台跳过，
  在 Mac 真实验证，不伪造文件权限或放宽生产检查。
  同一迁移夹具在 Windows 最终回归为 62 通过、15 个 POSIX／外部环境门禁跳过，零失败。
- 部署／回滚／Compose 五套架构测试：168 项通过；运行中 Core schema 探针：30 项通过。
- 运维审查修复后的 schema／TokenUsage 工作流回归：48 项通过。
- Mac 临时隔离副本使用 Java 21、真实 Testcontainers PostgreSQL／Redis，完整 Maven `verify` 成功：
  service-auth 11、service-contracts 5、Core 1206（3 个外部环境门禁跳过）、CLI 147，零失败／错误。
  `INKFORGE_MEDIA_SMOKE=true` 下真实 FFmpeg 抽帧、双片段、音轨与中文字幕测试通过。
  最后一处 `wall_long` 保留 32 位以上数值覆盖的测试补充，另跑真实 PostgreSQL 的 23 项审核回归全部通过。
  新增四种 post schema 投影的冻结指纹后，Java schema 回归 10 项全通过，与 Python 运维导出交叉核对。

完整日志位于工作树 `logs/java-only/`，仅测试生成物，不作为提交源码。
冻结 Python workspace 中 `inkforge_core`、`inkforge_cli` 均不可导入，Agent 与两个共享 Python 包仍可导入。

## Windows Operator

两份已安装 Skill 及配置已备份至：
`C:\Users\niebo\AppData\Local\Temp\inkforge-java-operator-backup-20260912-164638`。

使用固定 Java JAR、schemaVersion 5 和 Windows ACL；不依赖 Windows 符号链接权限。两套 configure、帮助、
非法命令拒绝、JAR 哈希与权限检查已通过。Windows 原有 84 命令／五操作与凭据 target 保留，macOS 45／3 未扩大。
本次只调整运行入口及 Skill 安装说明，不扩大其业务授权；没有导出、转述或搬迁用户令牌。

Windows CLI JUnit 147 项全通过、零跳过；服务身份 11 项（1 项缺少符号链接权限而跳过）、服务契约 5 项，
独立 CLI reactor `verify` 成功。临时 Credential Manager target 的写入、兼容读取和精确删除已通过；
生产 wrapper 复用原有会话完成 `auth.whoami`，未重新登录或覆盖用户凭据。
两套实际安装 JAR 与已验证构建 SHA-256 一致：
`ca097b5cb559bca16c87a1a6e5061ab133e07ef805b5e227c1f927819b314ecd`。

## 未取得的验证与发布边界

已尝试从当前源码运行隔离 V2 Compose 恢复演练。Docker Hub `auth.docker.io` 在拉取
`docker/dockerfile:1.7` 时两次连接重置，镜像构建未完成，尚未进入应用启动；不能宣称 Compose 恢复验收通过。
失败演练报告确认其容器、网络、卷为零残留，未访问开发库、生产库或真实模型供应商。

本地提交不等于远端 CI 成功；没有推送、生产发布、生产业务回归或数据迁移。
