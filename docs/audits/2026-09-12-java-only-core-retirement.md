# Java-only Core／CLI 清理验收

日期：2026-09-12

状态：代码迁移与初次 Java／Python／Web／Compose 回归通过；追加发布前发现并保全线上独有修复，
最终候选全量回归与生产发布进行中。各轮结果分开记录，未通过的中间版本不作为发布依据。
本记录初次提交时未推送、未部署、未修改服务器数据库。用户随后明确授权重试验证，测试通过后普通应用部署；
以下历史结果不等同于追加发布已经成功，追加执行结果单独记录。

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

## 追加发布授权与重试

用户于 2026-09-12 明确要求再次尝试验证，测试没有问题后部署。授权包括本次分支推送、CI、普通应用发布及
发布后的只读验收，不包含 DDL、服务器数据迁移、生产视频开放或既有小说内容修改。

- 发布准备重新 fetch 后，`origin/main` 仍为 `7b1de237b3709612583932a516e9536520deebfa`。
- 对实现提交 `503a59b1` 的镜像构建继续重试：最初两次仍在 BuildKit 获取 Docker Hub 令牌时失败；
  使用 Docker 已有代理路径预拉官方 `docker/dockerfile:1.7` 后，第三次通过 frontend 阶段，随后在
  Eclipse Temurin 基础镜像令牌处遇到相同网络问题。正在按同样方式预拉官方基础镜像，没有禁用 TLS、
  改用第三方镜像或放宽应用验收。
- 最新成功发布来自 `codex/chapter-input-budget-release` 的 `57524ab6`，不是 `origin/main`；发布前必须完成
  与本次候选的差异和 execution manifest 核对，不能只以 main 为线上基线。
- 官方基础镜像通过 Docker 现有代理全部预拉成功；`8b481ad7` 的 Java Core 和 Agent 镜像构建通过，
  隔离 Compose 最小恢复验收通过（20:11:05 至 20:17:42）：幂等、回执丢失、Agent 终态重放、Core 重启、
  派发前取消五场景以及 execution Redis AOF 重启均通过，重启前后数据库事实哈希和 Provider 调用事实一致。
  容器、网络、卷零残留；未访问开发库、生产库或真实供应商。报告保存在
  `logs/java-only/mac-recovery-8b481ad7-report.json`；后续热修复合并后的最终候选仍需重新验证。
- 分支已推送并创建 PR 13。首轮远端 CI `34692779148` 的 Java Core 为 1210 项、1 失败、5 跳过；
  唯一失败为 SSE 慢消费者注销测试等待超时，其他阶段尚未执行，正在独立复现修复。

### 生产只读基线与兼容差异

- 经已固定主机身份的既有 SSH 通道确认，生产源码和三业务镜像标签均为 `57524ab6`，各服务一份且 healthy。
- 生产 V2 为 `schemaReady=true / route=all / V1 fresh=false`，两份 allowlist 为空；
  `active-v2-count novelwriter=0`，`all` 门禁为 `gate-ok:all:migrated-with-v2`。
- Core 重启次数基线 1，其他业务及 Redis 为 0，均 `OOMKilled=false`；Core 内存约 357.1/448 MiB。
  宿主机可用内存约 431 MiB，无 swap，磁盘使用率约 81%。这些是发布前采样，不是新版本验收。
- 生产 manifest 为 `2faa340853bfe503c99569675dca481274d8c7d8b6594df83bc6fa52d981dd8b`；
  初次 Java-only 候选为 `aa9d1838a436ea5588ae034e4097fde419ca9e8300324443fb55a1f90c1d1fec`。
  除 Episode 迁移外，候选还遗漏生产正文 v3 十万 token 预算、Reviewer v2 输出协议、安全字段路径诊断和
  精确历史首次派发兼容。因此禁止直接部署初次候选，先保全线上热修复并重新验证。
- 最终 manifest 仍会因 Episode 迁移变化。待镜像上传完成后才短暂关闭新建路由，核对实际运行 Core 为 off
  且权威活动 V2 为零，再切换；后续恢复原 all 路由并执行全量门禁，不取消、删除或改写任何历史任务。

### 热修复与测试夹具同步

- 仅保全生产 `37285460`／`91812ba4` 的正文 Step v3、Reviewer v2、独立 token 上限语义、安全 JSON Pointer
  和精确历史首次派发兼容；保留当前 Episode 迁移及一次自动修订／六次调用，不带入其他任务的未合入配置。
- SSE 原测试没有确定制造队列溢出，依赖初轮查询时序。只在测试中连续发布两个未消费事件；生产实现未改，
  定向连续 12 次通过，完整测试类 11 项通过。
- 中间全量回归暴露的旧 v2/v1 断言及余额夹具按生产既有修复同步：返工测试依据冻结 Run token 预算准备余额，
  不修改真实余额、费率、业务上限或历史固定快照断言。
- Agent execution 目录 654 通过、1 跳过；Catalog 架构与共享执行契约 110 通过；Ruff、Mypy 131 源码及
  API 生成漂移检查通过。中间全量失败已保留日志，最终全量和 Compose 正在重跑。

### 最终候选本地验收

- 最终 manifest 为 `08ed0e1a9d7d2f965a039c0aa37f875233f8314b3f59185891df86adb29633a9`。
  `write_chapter`、`rewrite_scene` 两个完整 Operation 与生产 `57524ab6` 逐项相等。
- 最终 Windows Python 全量（继续拆出已在 Mac 验证的运维迁移夹具）3478 通过、20 跳过；
  Ruff、Mypy 131 源码和执行资产派生检查通过。日志为 `logs/java-only/python-release-final-green.log`。
- Mac 最终完整 Maven verify：service-auth 11、service-contracts 5、Core 1212（3 个外部环境门禁跳过）、
  CLI 147，零失败／错误，BUILD SUCCESS；日志为 `logs/java-only/mac-release-verify-final.log`。
- 最终 Compose 最小恢复再次通过五场景及 AOF 验收，报告 `logs/java-only/mac-final-recovery-report.json`。
- 最终正文写作 Compose 八场景通过：Core 重启后丢弃、幂等采用、作者返工、自动完整返工、局部 patch 后双审、
  patch 冲突、编辑批准全文和派发前取消。报告 `logs/java-only/mac-final-chapter-writing-report.json`。
  两轮均使用独立 Fake Provider／测试数据库，容器、网络、卷零残留，不接触真实创作数据或供应商。
- 上述结果尚不代表远端 CI 或生产发布成功，后续发布状态单独记录。

### Linux CI 探针夹具修复

`90c61f11` 的远端 CI `34694456077` 已通过 Java、API 和 Web 测试，但 Python 为 3554 通过、19 失败、
2 跳过。19 项全部来自同一 schema 探针夹具：此前所有平台只创建 Windows `docker.exe`，POSIX 查找
`docker` 时未命中替身。现仅在测试内按平台分别创建替身，真实生产探针和全部权限／清理断言不变。
Windows、macOS、真实隔离 Linux 容器均为 30/30 通过；Linux 容器无网络且仓库只读挂载，仅测试临时目录可写。
修复后重新执行完整远端 CI，不把此前失败轮次计作发布通过。
