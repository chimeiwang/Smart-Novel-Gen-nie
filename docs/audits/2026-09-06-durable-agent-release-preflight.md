# Durable Agent 发布前现场检查

首份快照：2026-09-06 07:52（北京时间）；下列首段保留当时事实，后续变化见文末日期分节。
当前发布尚未完成；用户已授权保全成果并退出旧执行，生产账号仍需恢复有效登录。

## 已证明的状态

- 本次业务候选为 `ef7e702`，21 个 Operation 仓内验收完成；分支仍为 `codex/durable-agent-execution`。
- GitHub `main` 与线上源码均为 `a37d87373ce9f10ed6c41dca9ff2a74956b76718`；最近一次相应 CI／部署成功，
  但它不包含当前候选。现场 Web、Core、Agent 镜像标签与该提交一致。
- 现场只有 `inkforge` 一套 Compose，含 Nginx、Web、Core、Agent、普通 Redis；尚无 execution Redis。
  开发库 86 张表、正式库 70 张表，均未发现 V2 engineVersion 列或 BillingReservation 表。
- 正式库通过修复后的隔离探针实时读取，精确命中旧版冻结契约在“视频关闭、手机号开启”下的投影，
  指纹为 `b5d2c319303f1ca52d411b8f986aa98a5d48168338c75c65d675d23968c22c78`。
- 服务器总内存约 1771 MiB、无 swap；首次检查可用约 354 MiB。因此没有额外在生产主机并起开发全栈，
  也没有把本机独立探针的内存结果当作完整 2 核 2 GiB 容量验收。

## 检查引入的一次重启及修复

首次按旧方式在活动 Core 容器中运行结构守卫时，额外 JVM 与业务进程共用 448 MiB 内存，触发容器
内存超限并使 Core 自动重启一次。该影响由本次检查引起，不能归咎于 Agent 候选代码。

随后已确认 Core 恢复健康，并完成独立受限探针修复，详见
`docs/specs/2026-09-06-schema-probe-memory-isolation.md`。用修复后的方式再次只读检查生产时，
Core 的实例、镜像与启动时间不变，重启计数保持 1，六项 readiness 全部通过，未留下探针容器。

## 2026-09-06：当时待决定或完成事项（历史快照）

1. 线上旧 WritingTask 有 41 个 `awaiting_user_review` 和 7 个 `idle`，没有观察到 active/waiting_call
   或待投递命令、Outbox。指定账号占 18 个待审、5 个 idle；其他账号占 23 个待审、2 个 idle。
   现有迁移流程把这些未结束事实纳入 drain。没有自动取消、丢弃候选或直接改表；已询问用户保留还是
   允许处置。该数字只是现场快照，任何后续操作前必须重新核对精确任务 ID、归属和状态。
2. 生产 Operator 固定账号配置与指定账号一致，但 `auth.whoami` 在 macOS 原生
   `SecKeychainFindGenericPassword` 处等待，尚未发出网络请求。按生产 Skill 要求等待用户手动放行／
   解锁，不读取令牌或把密码改成命令行输入。没有把配置的用户名当作已通过服务端身份验证。
3. 真实开发库迁移／回滚／contract、低额度真实供应商验收、正式库联合备份和迁移、生产 canary 与放量
   观察均未完成；活动 Skills、固定 CLI 安装包和线上服务也尚未更新。

## 2026-09-06：当时的后续顺序

先明确旧任务处置并取得现有账号会话；继续原 `docs/DURABLE_AGENT_V2_ROLLOUT.md` 的开发库、兼容镜像、
联合 drain、备份、具名迁移、交集 allowlist 和新建隔离作品 canary。当前个人项目发布范围已经移除
Controller／OIDC 要求，不重新把它们作为门禁。生产视频保持关闭。

## 2026-09-07：独立 execution Redis 配置已落地

15:03（北京时间），按 `docs/specs/2026-09-07-durable-release-preserve-novel-assets.md` 的配置授权，
在服务器 `/srv/smart-novel-gen` 只新增独立 execution Redis，未切换应用镜像、迁移数据库或接入旧 Agent。
执行前可用内存为 390,416 KiB、无 swap；现场仍是 `a37d87373ce9f10ed6c41dca9ff2a74956b76718`。
该 SHA 已通过精确路径加 `git -c safe.directory=/srv/smart-novel-gen` 核实；默认 Git 查询失败不表示仓库缺失。

- 新增 `infra/redis/execution-redis.conf`，与候选仓库文件逐字节相同，SHA256 为
  `b04efbe875299ec0f1a85c61245d943a70ea2630d1693f2f60d4704464c68107`。
- 新增 `infra/compose.execution-redis-bootstrap.yaml`，只包含最终 Compose 的 execution Redis 服务、
  独立网络和卷；服务器使用同一 Compose 解析器确认这三项与候选完整 Compose 逐值一致。
  启动只使用项目 `inkforge` 的该服务，并指定 `--env-file /dev/null --no-deps --no-build --pull never`；
  不读取或改写生产 `.env`，不移除 orphan，不构建或拉取镜像。
- 新容器名为 `inkforge-execution-redis-1`，完整 ID 为
  `ce094f8a118358978c8f83ac2348afd8f9ab509ddc7882531298c339e82e305d`，使用既有缓存的
  `redis:7.4-alpine` 镜像 ID
  `sha256:487efc0616382465781b8fdc3d6d1db449e6fd80ae23bf48432a2da6b6929908`。
- 新网络为 `inkforge_execution_net`（internal，`172.31.0.0/24`）；新持久卷为
  `inkforge_execution_redis_data`，挂载 `/data`。未发布端口，也未把旧 Agent 加入该网络。
- 容器只读根文件系统、非 root，限额 128 MiB／0.10 CPU；Redis `maxmemory=32 MiB`、`noeviction`、
  `appendonly=yes`、`appendfsync=always`、`aof-load-truncated=no`。真实回读 `healthy`、重启 0、
  `OOMKilled=false`、`DBSIZE=0`、`WAITAOF=1/0`、AOF 写入及重写状态均 `ok`、eviction 为 0。
- 既有 Nginx／Web／Core／Agent／普通 Redis 的完整容器 ID、镜像、StartedAt、重启计数和健康状态
  前后逐值一致，Core 重启计数仍为此前事件后的 1；`.env` 文件 SHA 前后一致。

本机先完成了精简配置到最终完整 Compose 的真实接管测试：两者服务配置哈希相同，接管后 Redis
容器 ID、启动时间和重启计数不变，没有创建其他服务。本机 Docker 随后短暂不可连接；未执行停止
Docker 的命令。恢复后重新核对测试卷为空，已精确清理本次本机测试容器、网络和卷，未删除服务器卷。

无凭据证据分别位于 `output/execution-redis-bootstrap/server-result.json` 和 `local-result.json`。
该结果只证明 Redis 基础配置就绪，不证明旧 Agent 已接入、V2 已发布或整机峰值容量已通过；
该阶段尚未加入 `EXECUTION_REDIS_URL`，后续最小补齐见本文16:15记录；生产视频仍关闭。

当前未接入 Agent 阶段若需撤回，应先核对上述新容器的精确身份，再只停止并移除该容器；保留专用
卷、网络和配置，避免误删可能已有的 journal。不得对项目执行整体 down／卷删除，也不回退旧五服务。
以后 Agent 接入后，必须先按联合 drain 和 journal 恢复规则处理，不能直接沿用此未接入阶段的撤回方式。

## 2026-09-07：保全实现与真实开发库验证

按用户“历史记录可不兼容、小说成果必须保留”的决定，在当前分支增加具名旧任务维护入口，
不物理删除 Task、聊天、命令、候选或版本。只把精确清单内旧 `idle/awaiting_user_review` 改为 `error`，
原阶段与完整原行保存在受保护归档；不是把旧任务伪造成成功，也不是清空数据库。

- 完整 Maven verify 通过：服务身份11项、契约5项、Core1208项（3项既有跳过）、CLI135项。
- 真实 PostgreSQL 兼容回归证明：旧 Task 终态后中短篇候选仍可列出、预览，并可由作者显式采用和从历史
  创建恢复版本，原正文不变；全量路由仍冻结原正文且幂等重放不转换旧引擎。
- 架构测试首轮439项通过，1项因本机 Homebrew Git 动态库缺失未能执行；改用系统 Git 后，包含该项的
  HTTPS 模块6项全部通过，未为环境问题修改业务代码。归档／迁移前快照／静态候选的31项真实 PostgreSQL
  与双 Redis 验证通过，包括竞争、5秒锁超时、正文副作用回滚、提交后回执发布失败的独立核验恢复。
- 全仓 Ruff 与差异检查通过；双环境真实 Java CLI 启动器离线验收通过，无 Python／uv 业务启动依赖。
  两份固定安装包随后经备份和原 configure 同步，公共125命令／Operator45命令不变，安装事实见下文。
- 现场宿主机是 Python3.10.12，维护入口使用兼容的 UTC 别名；本机实际 Python3.10 导入三维护模块通过，
  没有为此安装服务器解释器或增加软件源。

真实开发库通过只绑定本机回环的 SSH 隧道连接，本机独立四服务不占用生产主机内存；没有复制生产 JWT、
供应商密钥或服务私钥。开发 Agent 为 Fake，关闭 fresh V1/V2 与视频调度，尚未调用真实供应商。
新 Core／Agent 镜像已通过离线能力检查，manifest 为
`920ca5f4a4b98e078bdf620dcc4f1b2e943d2290029718aa3aa749277ad15b75`；真实开发库 `pre-contract`
和六项 readiness 均通过。此时仍为 `unmigrated`，不把健康检查当作迁移完成。

开发库重新盘点44条旧非终态 Task（37待审／7idle），无活动命令、未投递 Outbox、applying 候选或
非终态 V1 WorkflowRun。完整 PostgreSQL 备份、精确原行归档与86张表内容指纹完成后，具名 `apply` 与
独立 `verify` 均返回 `allProtectedValuesUnchanged=true`；只改变这44条 Task 的 phase／updatedAt。
正式库的48条快照记录和所有正式小说成果尚未处理。开发库联合 PostgreSQL／execution Redis 备份另行
完成，受保护目录为本机 `output/inkforge-durable-realdev-20260907/.durable-agent-execution-backups/novelwriterdev/inkforge-20260907T073639Z`。

两份固定 Java CLI 包现已实际安装为
`1f650645711bf2c5c17d9aeb5824f250f90a85136da0c95371f0449501da0995`，config／来源记录与包哈希相符；
原账号绑定、origin、profile、45命令／3操作集合保持不变。备份为
`output/operator-runtime-backup.ufPjom/local.tar.gz` 与 `production.tar.gz`，没有访问或改写 Keychain。
安装后本地 `auth.whoami` 返回尚未绑定用户名；生产只读身份探针等待于原生 `SecKeychainFindGenericPassword`，
已停止该探针，未得到新的生产身份成功结果。按两份 Operator Skill 的登录规则，已请用户在真实终端分别登录。

真实开发库随后完成：第一次 forward、原实例 post-contract、重复 forward、再次 post-contract、
结构导出／独立复验、空 V2 rollback、回滚后原86表独立保全复验与归档幂等重放、最后一次 forward。
回滚没有恢复数据库备份或撤销44条已获准的旧执行退出；恢复的是具名迁移前结构，小说成果没有改变。
最终新建5张 V2 表为空，状态为 `migrated-empty-v2`。迁移前后除获准演进结构的 WorkflowRun／WorkflowStep
外，其余84张原表的完整内容指纹和行数一致，包括设定、大纲、正文、候选、版本、身份和账务。

两份真实结构证据均导出并独立复验为 `aa41cd21af7faa11b74850d56a44a27afa65f5de483f817ffec0c678b734989c`
（开发运行配置的 WITHOUT_PHONE_AUTH 投影；物理表数91，未删除 UserPhoneIdentity）。证据在
`/Users/boqiangnie/inkforge-durable-contract-20260907.2AGcUJ/dev-before-rollback` 与 `dev-final`。
首次尝试把证据写进 APP_DIR 被既有路径检查拒绝；没有放宽门禁，改用上述仓外受保护目录后成功。

开发库另有一条6月已 completed 任务的静态 draft 候选，Artifact 与 Task 分属同小说的两个真实章节。
新 drain 最初将章节 ID 相等错误地当作历史执行结束条件；根据旧读取语义修为分别校验同小说归属后，
该静态候选不再阻断，候选和来源未改。实际17项迁移前阻断指标全为0；跨小说、缺失来源、applying 或
活动命令仍阻断。此问题没有升级成新的任务清理或业务创建／采用规则变更。

最终开发配置已启用 `schemaReady=true`，保持 `route=off、V1 fresh=false`，同一 Core 镜像按计划重建一次。
`schema-ready-route-off`、两个 drain 索引初始化和正式 `verify-drain` 均成功；17项指标全部为0，
`v1DrainZero=true、v2Converged=true`。启用结构后的原84张保全表再次逐值指纹相同，V2 新表仍为空。
最新受影响门禁99项通过，未扩大为额外产品功能；当前还未执行真实供应商业务 canary，未将开发状态
当作生产上线。四个本机验证服务与受保护 SSH 隧道暂保留，以便用户完成登录后继续验收。

## 2026-09-07：生产连接配置最小补齐

16:15（北京时间），在已有部署互斥锁保护下，为服务器 `/srv/smart-novel-gen/.env` 仅追加一条
`EXECUTION_REDIS_URL=redis://execution-redis:6379/0`。原文件全部字节保留，该键数量由0变为1；
原属主 UID 0／GID 1000 和0640权限不变。修改前完整备份为
`/srv/smart-novel-gen/.env.before-execution-redis-url-20260907T081518377021Z`，备份权限0600。

六个服务的完整容器 ID、镜像、启动时间、重启计数和健康状态前后逐值相同，未执行 Compose 重建、
数据库操作或把旧 Agent 接入 execution 网络。未修改 schema、route、V1 fresh、视频、供应商或服务身份配置。
无凭据回执为 `output/execution-redis-bootstrap/server-env-result.json`，记录
`originalBytesPreserved=true、ownerAndModePreserved=true、servicesUnchanged=true`。
这只完成未来应用切换所需的连接配置；现有 Agent 尚未使用它，正式库和生产业务代码仍未切换。
