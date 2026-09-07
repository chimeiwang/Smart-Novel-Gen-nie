# Durable Agent 发布前现场检查

首份快照：2026-09-06 07:52（北京时间）；下列首段保留当时事实，后续变化见文末日期分节。
当前发布已完成：生产 `8a1324c` 已通过真实canary、小说成果保全、账务和最终all门禁，已开放业务新请求全量走V2。
V1 fresh与生产视频保持关闭；8条验收Run中的3次失败及真实费用完整记录。下文历史阻塞不代表当前状态。

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

## 2026-09-07：指定账号登录与真实开发 canary

用户进一步明确授权代为登录。通过原 Java CLI 隐藏终端输入完成本地账号 `nie` 登录，并由
Operator与普通公共Java CLI分别 `auth.whoami` 成功复验；凭据仍只由系统钥匙串保存，没有密码文件、
环境变量密码或令牌导出。生产身份探针触发macOS钥匙串授权，系统不允许执行者操作该安全弹窗，
已请用户只处理系统授权，不要求重复输入InkForge账号密码；生产身份尚未核验成功。

维护者通过公共CLI新建唯一开发隔离作品“耐久Agent发布验收-20260907-dev”：
novelId为 `cmtr1lfakisj9mlmx52uwkmc0`，首章为 `cmtr1lfamisjamlmx9m2rr6yx`。
只在该章写入175字合成验收文本，既有作品没有执行写入。新小说的 `long.session.list` 返回空数组；
代码核实原125命令没有创建WritingSession的入口，问答因而无法独立开始。最小补齐范围见9月7日spec，
不使用内部API、数据库直写或临时HTTP绕过公共CLI。

本机四服务随后复用已有开发模型配置，仅导入七个明确模型项；服务身份和JWT保持独立。
原镜像在指定用户／隔离小说交集下通过 `gate-ok:allowlist:migrated-empty-v2`，
运行态为 `schemaReady=true/route=allowlist/V1 fresh=true`，两Redis未重建。
配置备份和完整容器身份见受保护输出目录内 `provider-allowlist-result.md`。

一次真实 `review_chapter` 已经完成：Run `cmtr1uzaf1kjzcxvailok8kul`、
Step `cmtr1uzag1kk1cxva97kgks27`。公共watch和独立GET均返回 `engineVersion=2/status=completed`、
完整reviewReport且Artifact为空；再次读取章节，正文与updatedAt保持提交合成文本后的原值。
该结果证明一次真实只读审阅链路，不替代尚待完成的问答、候选决定、取消与重连完整canary。
开发库从此已有V2事实，不得再执行DDL rollback；此前84表逐值不变是旧执行维护／结构迁移阶段的证据，
不能套用到合法新增隔离作品、执行记录和计费用量的canary阶段。

## 2026-09-07：真实问答、候选决定与取消现场

CLI 会话缺口已最小补齐：新增 `long.session.create` 映射既有公共会话创建接口，普通 CLI 为126命令，
Operator仍45命令／3种Operation，没有新增Core接口或直连Agent入口。Java CLI143项、Python CLI与
迁移基线712项通过；完整Maven verify为身份11、契约5、Core1208（3项既有跳过）、CLI143，全部成功。
Ruff、Mypy、注册表生成复验和两环境启动器离线测试通过。两份实际固定JAR均已安装为
`132b5429a5a38b0f742403e093df847195090d645f84a200ad3a0a8037c7e0f6`；来源如实记为
`8da04a5` 加未提交变更，不将安装称作生产服务已切换。成对备份为
`output/operator-session-backup.nUv3ML`，仅含配置与runtime，不包含钥匙串内容。

在上述唯一隔离小说中，新会话 `cmtr26ppc1kkhcxvav42rykdj` 由新公共CLI命令创建。
真实问答Run `cmtr279zu1kkicxvazw2w15hg` 完成，Agent消息的V2 source身份精确匹配；原请求重放
仍为同Run、同一消息，原问答消息字节哈希一致，没有重复模型调用或扣费。
规划Run `cmtr29ati1kl2cxvaag4qapud` 经完整候选读取后弃用；规划Run
`cmtr2d7db1km5cxva5urgxvoc` 的第二份候选经完整审阅后采用。两次均通过内置复审，最终分别为
Artifact draft与applied。仅隔离章节新增已采用BeatPlan `cmtr2g4nk1knbcxvazasrsv1q` 与两SceneBeat，
175字测试正文和其updatedAt保持不变，未修改任何既有小说。V2待审候选读取显式提供revision=1。
直接Java watcher的Ctrl-C实际退出130；重连同Run从权威snapshot继续，Step attemptCount仍1，未重新执行。

取消Run `cmtr2hc2v1knfcxvaszyyza3a` 的Core状态为cancelled，Step为skipped／RUN_CANCELLED，
watch退出5符合取消协议，未产生模型调用、预留或费用。但Agent journal仍为accepted，已有持久取消，
providerAttempts=0且无provider开始时间；联合drain唯一非零项为v2ExecutionsActive=1。
此为真实未闭环问题，不用删除Redis记录或修改数据库制造全零。开发入口已关闭为
schemaReady=true／route=off／V1 fresh=false，只重建Core，保留Agent与双Redis现场。
最小修复及验收依据为 `docs/specs/2026-09-07-durable-cancel-before-provider-convergence.md`。

五Run的独立只读审计确认：六次真实模型调用、六笔唯一用量、六笔唯一扣费，六个预留均settled，
总37.876积分；全部关联限定在新隔离小说。该审计发生于取消修复前，不能作为最终排空成功证据。
生产账号的Java钥匙串授权仍未得到结果；正式库48条历史任务、V2迁移、业务代码切换与生产canary尚未执行。

## 2026-09-07：取消修复与真实开发验收收口

取消修复未改Core、共享协议、数据库或Operation manifest，只改Agent日志候选读取、原回放循环准备钩子、
执行器取消收尾与测试。先有确定性失败再修复；执行器56项、日志／回放38项、独立真实Redis Lua测试通过。
完整Agent测试1648项通过（仅一条既有Starlette弃用提示，无跳过）；全仓Ruff、294文件Mypy和差异检查通过。
此前523通过后被精确中断的一轮不计作全套成功。镜像从冻结后的本轮源码构建，不宣称ARM开发镜像可直接用于x86生产。

仅Agent重建为 `sha256:22d8b604e111383c2bad04ba055ecbf1f6dad4c8f786b15bc129cfb18eec8934` 后，
原取消Step自动成为failure／delivered，保留原取消身份、providerAttempts=0，正常移出active和callback索引。
没有手工DEL／ZREM、重提模型或改数据库。恢复前后五Run的PostgreSQL审计除采样时间外逐值相同；
全部六笔用量、扣费、已结算预留和候选状态完全不变。证据为
`canary-recovered-scope-audit.json`、`cancel-recovery-verify-drain.log` 与前后容器身份记录。

随后在同一隔离小说短暂重开交集allowlist，公共CLI复验新的
Run `cmtr3lrwte3uy5j3lp5u55zhd` 启动、取消和独立GET成功；无模型调用、费用或新候选。
六Run最终审计 `canary-final-six-scope-audit.json` 确认4completed／2cancelled，账务仍唯一且总37.876积分；
公共CLI再次读取章节，完整data与采用测试后的回执一致。入口已关闭回route=off／V1 fresh=false，
`canary-final-verify-drain.log` 明确v1DrainZero=true／v2Converged=true，全部指标为0。
这些结果闭环真实开发canary，不代表正式库已迁移或生产服务已生效；生产Keychain授权尚未完成。

## 2026-09-07：生产身份完成、首次兼容部署回滚

生产钥匙串权限随后放行，旧会话返回服务端UNAUTHENTICATED。按用户明确授权通过原生产Operator隐藏TTY
重新登录成功，auth.whoami确认账号nie／userId cmq6p5nlm0000txq43itjnypt。没有保存密码文件或导出令牌。
固定提交87dfc73a44e56a8aff062287cc37074a661c2fb0的三张linux/amd64镜像和源码bundle已构建、校验并上传；
上传前后六个运行服务完全未变。构建清单、旧镜像与上传证据位于output/release-87dfc73。

正式.env先完整备份，只补齐具名迁移阶段配置：schemaReady=false、route=off、V1 fresh=false，白名单为空，
视频与Seedance明确关闭；其他原行、UID0／GID1000／0640保持。随后使用原部署脚本尝试兼容切换，
新Agent因readiness失败而未通过依赖启动；脚本自动回滚旧三镜像，六服务healthy，结构守卫和smoke通过。
服务器Git检出已为87dfc73，但实际运行的是旧镜像的rollback-87dfc73别名，不能把源码检出当成运行生效。
正式库未迁移，旧48条任务未退出，未创建生产小说或调用模型。

原新镜像的受限只读探针复现：独立execution Redis整库keyCount=0，AOF／noeviction／listpack健康均满足，
取消候选查询返回空，但原claim_due_callbacks报“drain索引缺失或损坏”；探针后keyCount仍0、未创建marker。
根因为迁移前空journal无marker时，回放监督器仍执行严格claim并反复失败；开发验收已有marker，未覆盖
production严格readiness与首次lifespan的组合。最小修复规格已追加到取消收尾spec；不提前写marker，
不把生产改为dev、不跳过健康检查，不执行尚未获准通过的正式库后续步骤。

空库待机的最小Lua修复已通过：production真实lifespan红测1失败／8负例通过，修复后整个健康文件26项通过；
日志／回放和独立真实Redis48项通过，完整Agent1666项通过，无跳过。Ruff、294文件Mypy和差异检查通过。
空库仍不创建marker，生产accept仍拒绝新执行；任一孤儿、索引、quarantine、错误marker或其他key仍失败。
Core／Web构建输入未变，下一冻结提交按不可变镜像ID复用，并明确记录原构建提交，避免伪改OCI来源标签。

## 2026-09-07：正式迁移、成果保全与生产 canary

正式兼容部署 `d737de4` 已成功。旧任务首份清单精确为48条（idle 7、awaiting_user_review 41），
备份后仅 phase／updatedAt 退出为 error；原70表其余字段逐值一致。生产 Python 3.10 对6条短小数秒
时间戳不兼容，已以 `fceac69` 无损规范化修复；47项清单／真实PG测试及真实Python3.10的49项检查通过。
原应用角色对25张关闭视频表只有读取权限，原事务取锁失败且零变更。固定helper SHA的具名本机postgres包装器
只执行原apply事务，随后用应用角色独立verify成功；没有修改权限、所有者、候选或成果内容。

正式联合备份为 `/srv/smart-novel-gen/.durable-agent-execution-backups/novelwriter/inkforge-20260907T115651Z`。
具名forward执行两次，每次原兼容实例不重启通过post-contract-route-off。真实75表contract已导出和独立复验，
指纹 `ea1df9ad015cd8d811d6ab250a7098870aa2befcf0afa3273b845255a0ac11b2`；证据在
`/srv/inkforge-durable-maintenance-20260907/contract-final`。除两张获准演进的执行表外，原68表逐值一致。
canary前原75表10824行的真实PK／完整行hash基线已保存在服务器受保护目录；不得用canary合法新增行否定维护阶段保全。

已同镜像启用schemaReady并初始化双drain marker，首次17项联合指标全零。旧成果通过原生产Operator完成30次
公共读取，包含旧长篇正文／设定／规划／大纲、中短篇蓝图／正文和已保存／历史恢复产生的版本及完整preview。
本次不执行旧作品restore／adopt；版本抽样不冒充覆盖所有带旧Task的Agent候选。

生产唯一新测试小说为 `cmtr6uta5jw2i7k3q6zjsm1vc`，章节 `cmtr6uta7jw2j7k3qm7aoxu60`，
会话 `cmtr6uvp1jw2n7k3qyim1iznd`；正式CLI创建、写入177字合成章、启动模型和候选决定均只在此范围。
首条问答completed且同请求重放前后PG事实完全相同，1调用／1.091积分；规划生成／编辑审核／弃用完成且正文不变。
另有一次独立审阅以 `MODEL_STRUCTURED_OUTPUT_INVALID` 失败，outcomeUnknown=false，1调用／6.082积分已唯一结算。
原失败诊断细分类未被旧代码保留，不能倒推模型原文或把它说成已修复的特定供应商故障。

遇到该协议失败后已关闭新建路由；三Run均终态、4个模型调用合计21.79024积分、17项联合指标全零。
`924c857` 仅补Executor具名安全诊断日志，不改Prompt、Schema、registry、计费、哈希或重试。
120项定向、完整Agent1674项、Ruff、294文件Mypy通过。只有Agent重建，Core/Web复用原87dfc73镜像ID，
原OCI revision保持不变。上传首次SSH断线未部署，原上传器重试同一镜像成功；正式部署和编排冒烟已通过。
补丁部署前后原三Run/Step/用量/账务事实SHA完全相同。生产后续canary及最终all结果另据下文更新，不能仅据此节报全量成功。

本节直接证据在 `output/release-d737de4/` 与 `output/release-924c857/`，完整业务回执受0700目录／0600文件保护，
无密码、Cookie、Token、私钥或数据库URL入文档。仓外不可变controller／OIDC未实现；个人项目规格已退役该外部门禁，
不得把本次仓内与服务器验收冒充完成了外部信任根，也不再因此另建发布控制面。

## 2026-09-07：审阅格式兼容修复及再次真实验收

第二次同指令审阅 `cmtrb3j1th15cu521pla8qt1u` 仍以 `MODEL_STRUCTURED_OUTPUT_INVALID` 终止；
新增安全日志明确为 `output.chapter_review_text.v1 / json_decode_error / json`。1次模型调用、4.981积分已唯一结算，
原失败保留且未重放。此时四Run（2completed／2failed）共5次调用、26.77124积分，全部终态且账务与Redis活动索引收敛。
这条诊断只证明JSON解码失败，不能据此倒推原输出一定含未转义换行。

`8a1324c18356b8b7cb325e9352582c33aa94ab01` 增加一次有界、无损的JSON字符串LF／CR／tab转义恢复，
恢复后仍经过原严格JSON与完整Schema验收；不放宽Schema、不截断输出、不增加模型重试。301项定向、
完整Agent1741项、全仓Ruff、294文件Mypy及diff-check通过；独立代码复核未发现正文丢失、额外调用或计费问题。
生产精确镜像组合为：

| 服务 | 实际镜像ID | 来源 |
| --- | --- | --- |
| Core | `sha256:822d1c0c522e6912523f9615900b3ef2cfef4f2cb141951e5fedb887ee6564de` | 构建输入与87dfc73零差异，复用原ID／OCI来源 |
| Agent | `sha256:9c3a67c0600965cad42ca20a8c9ced3fb2076f36c753a9d2d3fe683551fcf178` | 8a1324c真实重建 |
| Web | `sha256:95c863115fd5202ad4f39ebf86b278abeb55256cd1dd808334260e3c8bd05cd2` | 构建输入与87dfc73零差异，复用原ID／OCI来源 |

三服务部署标签均为完整8a1324c，linux/amd64；不伪造复用镜像的OCI revision。原部署脚本退出0，六服务healthy、
精确schema守卫、编排冒烟和重新启用交集allowlist门禁全部通过；execution manifest仍为
`920ca5f4a4b98e078bdf620dcc4f1b2e943d2290029718aa3aa749277ad15b75`。

第三次审阅 `cmtrc8bvbz6ywrgpaamft69g4` 复用完全相同指令，仅使用新建且已授权的 `review-003` 请求身份，
已completed、error=null、activeSteps为空。公共CLI完整回读550字报告，哈希为
`a378fc0ea2b8517d718c44174497a5dd6b20c0773cf7c075e147b8051035a6cb`；章节正文／标题／updatedAt与问答前基线完全一致。
本次成功证明新版本的真实审阅链路通过，不证明前两次坏输出的具体字符原因，也不把随机一次成功解释为模型永不出错。
直接证据：`output/release-8a1324c/production-json-recovery-deploy.log`、
`production-json-recovery-allowlist.log`，以及 `output/release-d737de4/production-canary/review-third-check-5ba61866795847c39ee34fe6b95df21b/`。

规划采用 `cmtrcahnwz6zhrgpay6bsxnxt` 已completed，Artifact `cmtrcbg54z703rgpagwp0wzes` rev1已applied，
正式两场景BeatPlan为 `cmtrccniez70prgpaah38lsyn`；完整候选与Diff保留，章节正文／标题不变。
运行中的真实PTY watcher按Ctrl-C退出130，同一watch请求重连同Run，未重发start或cancel。
独立末次读取最初漏传revision，被公共API以 `ARTIFACT_REVISION_REQUIRED` 正确拒绝；只修验收脚本参数后用新回执
复验成功，原失败回执保留，没有重复采用或修改产品代码。

取消样本 `cmtrcflavz70trgpas17bp5mv` 未进入waiting_user，在生成Step以 `STEP_BUDGET_EXCEEDED` 终止，
因此没有发送cancel，也不计作取消验收通过。正式库冻结预算与实际usage的独立对照确认唯一越界维度为
reasoningTokens 7999 > maxReasoningTokens 6000；completionTokens为7999（上限8000）、visibleOutputTokens为0，
耗时65.675秒（上限180秒）、1次调用、0次格式纠正。`bounded → thinking enabled/high` 是原有创作策略，
未发现本次映射缺陷；供应商总输出上限不保证给可见正文预留token，系统依原预算正确终止，不扩大预算或偷偷重试。
本次19.79912积分已唯一settled；七Run共9次模型调用、68.2946积分，4completed／3failed，账务全部匹配、无未知用量。
正文和先前已采用BeatPlan不变；恢复route-off后的17项正式联合drain全零。
完整回执为 `production-canary-seven-runs-budget-failure-audit.json`、`production-plan-cancel-failed-step-budget.json`，
以及 `output/release-8a1324c/production-cancel-budget-route-off-drain.log`。旧失败完整保留，后续仅补一条具名取消样本，
不以无限新建任务凑成功率；该受控错误不伪装成模型调用成功或用户取消。

## 2026-09-07：最终业务、账务与小说成果验收

唯一补充取消样本 `cmtrcvbchpigjbnudrgpmt4gc` 已先进入waiting_user，经完整读取精确rev1候选后显式cancel，
回读为cancelled／error=null／无活动Step。Artifact `cmtrcvubspih3bnudrn4mk5n5` 保留awaiting_user状态及完整payload／diff，
Run不再可操作；此前已采用BeatPlan `cmtrccniez70prgpaah38lsyn`、正文和标题均不变。
原预算失败样本未被改为成功或取消，没有继续新增第三个取消样本。

最终精确8个Run（4completed／3failed／1cancelled）全部纳入审计，而非只抽取成功样本：

| Run | 实际结果 | 模型调用 | 积分 |
| --- | --- | ---: | ---: |
| `cmtr71lss3fckr0be0dcxszrd` | 问答完成，同请求重放不重复产物或计费 | 1 | 1.091 |
| `cmtr75du53fd5r0besvklv1s5` | 第一次审阅结构错误，原失败保留 | 1 | 6.082 |
| `cmtr76w9u3fdor0bez0zeqojb` | 规划生成、复审、用户弃用完成 | 2 | 14.61724 |
| `cmtrb3j1th15cu521pla8qt1u` | 第二次审阅JSON解码错误，原失败保留 | 1 | 4.981 |
| `cmtrc8bvbz6ywrgpaamft69g4` | 第三次审阅完成，550字报告 | 1 | 4.686 |
| `cmtrcahnwz6zhrgpay6bsxnxt` | 规划采用完成，真实PTY退出130并重连同Run | 2 | 17.03824 |
| `cmtrcflavz70trgpas17bp5mv` | 思考预算超限，未发cancel | 1 | 19.79912 |
| `cmtrcvbchpigjbnudrgpmt4gc` | 待确认阶段显式取消，候选保留 | 2 | 13.81224 |

共11次模型调用、11份TokenUsage、11份唯一结算账务／Reservation，合计82.10684积分；无重复计费、未知用量或
未结算预留。指定账号余额从42160928440降为42078821600微积分，差额恰为82106840；用户决定Step不伪造模型用量。
正式route-off／V1 fresh=false后的联合drain17项全部为0，V1/V2索引版本均为1。

原75表10824行基线保持不变。首次严格核验发现9条WritingEventOutbox旧行缺失，未直接忽略或重取基线；从具名原备份
只解析该表的COPY数据，在只读事务中按真实行类型重建hash，9行完整hash与原基线逐项相同。它们均为published，
publishedAt为2026-08-31 12:30:16.335～13:44:00.231 UTC，7天到期时刻严格处于本次采样窗口内，符合未改动的原有终态
事件保留规则。没有具体删除日志，故结论是“与既有自动过期规则一致”，不伪称证明了某个清理线程的执行。
Outbox不是作品来源表，没有指向它的入向外键；其余74表和Outbox剩余旧行均逐值保全，小说正文、设定、大纲、版本、候选
及来源没有因本次发布损坏。指定User只按原约定排除余额／updatedAt，并已独立对平费用。

最终保全回执明确 `allPreexistingRowsPreserved=false`、`allProtectedPreexistingRowsPreserved=true`、
`expiredHistoricalOutboxRows=9`，不宣称10824行全部仍在；没有恢复备份、修改基线或手工清理数据库／Redis。
证据为 `output/release-d737de4/production-canary-final-eight-runs-audit.json`、
`production-canary-outbox-expiry-evidence.json`、`production-canary-preservation-verify.json`，以及
`output/release-8a1324c/production-final-canary-route-off-drain.log`。本轮四个具名临时开发容器已停止，数据卷与备份保留。

## 最终生产状态

全量配置经原具名helper备份后写入，同一8a1324c镜像只重建Core并reload Nginx，
`durable-agent-v2-rollout-gate.sh all novelwriter` 真实退出0，输出 `gate-ok:all:migrated-with-v2`；六服务均healthy，
服务器源码HEAD为 `8a1324c18356b8b7cb325e9352582c33aa94ab01`，三服务镜像ID与前述部署清单相同。
当前配置：

```dotenv
DURABLE_AGENT_EXECUTION_SCHEMA_READY=true
DURABLE_AGENT_EXECUTION_ROUTE_MODE=all
V1_FRESH_AGENT_STARTS_ENABLED=false
DURABLE_AGENT_EXECUTION_USER_ALLOWLIST=
DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST=
VIDEO_PREVIEW_ENABLED=false
VIDEO_DISPATCH_ENABLED=false
SEEDANCE_ENABLED=false
```

全量只指已开放业务的新Agent执行，不表示生产视频、所有CLI操作或Windows凭据平台同时开放。
后续故障只能保留schemaReady并关闭新建路由，使用V2-aware兼容镜像收敛；禁止DDL rollback或V1-only旧镜像。
本次沿用当前工作分支和原源码bundle发布，没有向GitHub main合并或推送；末次文档收口不另造业务镜像。
全量直接证据为 `output/release-8a1324c/production-final-all-gate.log` 与
`output/release-87dfc73/production-config-all.json`。仓外controller／OIDC未实现，已依个人项目规格退役，不属于本次上线结论。
2026-09-08 00:58（北京时间）完成切换后的公共HTTPS身份／同一取消Run／章节回读，正文、标题与已采用BeatPlan仍一致，
没有新模型调用；回执为 `output/release-d737de4/production-canary/final-all-readback/summary.json`。
