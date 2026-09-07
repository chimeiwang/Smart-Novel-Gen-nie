# 耐久 Agent 发布：保全小说成果并退出旧执行

状态：仓内实现与真实开发库旧执行保全／迁移／回滚／全零 drain 已完成；两份固定 CLI 包已同步。
生产已准备独立 execution Redis 并补齐连接配置，正式库和业务代码尚未切换。
本地指定账号已完成真实开发问答、审阅、候选弃用／采用、取消及重连验收；取消现场修复后最终联合drain全零。
生产身份仍需系统钥匙串授权，正式库迁移和生产canary未执行。
沿用当前 `codex/durable-agent-execution` 分支和个人项目发布入口。

## 用户决定

2026-09-07：历史执行、聊天记录允许清理或不再兼容；设定、大纲、正文等小说成果必须原样保留和兼容。
服务器配置由执行者主动完成。该授权不允许为通过迁移门禁删除小说、丢失成果、伪造任务成功或开启生产视频。

同日用户明确授权执行者使用指定账号完成登录与后续验收。登录通过原 Java CLI 的隐藏终端输入完成，
会话仍由系统钥匙串保存，不把密码写入文件、命令参数或运行日志，不更改其他账号或系统钥匙串权限。
真实开发 canary 复用本机已有开发供应商配置，只复制明确的模型配置项，不复制生产 JWT 或服务身份；
只在新建且具名记录的隔离小说中操作，保持原有小说成果不变。维护者 canary 使用既有完整公共 Java CLI，
不为执行问答而扩大两份日常 Operator 的45命令／三种 Operation 白名单。

## 保全范围

- 正式小说、章节正文、设定、写作圣经、文本和结构化大纲、伏笔、进展、正式 Beat Plan／SceneBeat、
  参考资料与索引、文风、文件／附件、视频已有版本和 head 均不得因本次维护变更。
- ReviewArtifact、Revision、Evaluation、已采用版本、候选全文、Diff 与来源绑定全部保留。
  User、身份、积分与 TokenUsage／账务记录也不属于清理范围。
- 已知 ReviewArtifact.taskId 删除时 SET NULL，会破坏中短篇 sourceTaskId 严格绑定，故本轮不物理删除
  WritingTask、WritingRunCommand、WritingSession 或关联候选，也不截断其 graph、payload 或聊天正文。

## 具名旧执行退出

本轮只处理重新盘点并冻结 ID 的旧非终态 WritingTask；正式库首份快照为48条，开发库实际清单为44条，
不把固定数字作为后续选择器。任何新增或发生变化的任务必须重新核对，不扩大到所有账号历史数据。

1. 先制作可验证的 PostgreSQL 备份，保存精确 ID、原状态／更新时间和完整原行的归档；归档文件受保护，
   不把正文、数据库口令或令牌打印到终端。生成全部非执行业务表的逐表完整内容指纹与行数。
2. 只允许在目标任务无 pending/submitted/processing 命令、无未送达 Outbox，并已核对运行队列无活动
   模型调用时执行。实际有执行中的任务应先正常收敛，不能以本维护脚本伪造调用结果或费用。
3. 在同一事务锁定精确任务，重新核对冻结条件后将 idle／awaiting_user_review 退出为现有 error 终态；
   不写成 completed，不生成虚构产物。只更新 Task.phase／updatedAt，所有其他字段、Command、Outbox、
   候选及业务成果保持不变；具名归档记录“用户授权退出旧执行”，可供事后核对原状态。
4. 同一事务复验所有保全表和目标 Task 除允许字段外完全一致；任一差异整体回滚。提交后再独立核对，
   重复执行必须识别已退出的相同任务并稳定返回，不改原归档。禁止用直接恢复全库覆盖线上数据作为回退。
5. 旧运行不再承诺聊天续跑、旧 Graph 恢复或依赖旧执行状态的长篇返工流程；候选原文与来源仍完整可读。
   中短篇已保存版本的列表、预览、恢复及正式小说成果公共读取必须验证兼容，不能仅比较表的行数。

## 迁移 drain 的准确含义

Task 非终态、实际活动 Command、未送达 Outbox、队列活动项、V2 Run／Step／计费事实仍必须检查。
旧 Artifact 的 draft／under_review／awaiting_user 状态不是独立模型执行事实：只有它仍绑定非终态旧 Task
才计入旧执行 drain；已退出 Task 的静态候选作为成果保留，不强迫作者采用或丢弃。不忽略 applying 状态：
即便关联 Task 终态，它仍需实际查明并收敛，不能凭归档隐藏应用中的内容写入。

维护判据只核验实际作品归属：Task 与 Artifact 必须属于同一 Novel，二者各自非空的 chapterId 必须
指向该 Novel 内真实存在的 Chapter；不要求两者章节 ID 相等。真实开发库存在 2026-06-28 已 completed、
无 Command／Outbox 的旧 Task，其 draft 候选绑定同作品另一章节。这是静态历史记录，不是正在执行，
不得为迁移另行修改其绑定或状态。当前数据库分别保留 Task／Chapter／Novel 外键，没有要求这两个章节
ID 相等的复合约束；创建、采用、恢复时的既有业务校验完全不变。跨小说、缺失章节或缺失 Task 的异常
归属仍不能豁免，活动 Command 与 applying 也继续阻断。

此调整不跳过真实活动命令／队列、不缩小 V2 journal 或账务检查，不修改具名 V2 forward／rollback SQL
及其固定 hash。新增的历史维护仅为本规格授权的具名数据操作，不授权任何新表、列、索引或自动迁移。

### 维护入口与迁移前只读边界

`sh scripts/archive-legacy-writing-tasks.sh <preview|backup|apply|verify> <novelwriterdev|novelwriter>
<scope.json> <archive-dir>` 使用现有 `APP_DIR`、`DURABLE_AGENT_MIGRATION_ENV_FILE` 与服务器部署互斥锁。
清单包含版本、精确数据库名，以及每项 `id/phase/updatedAt/novelId`；备份目录只允许首次创建，不能覆盖。
事务使用 5 秒锁超时、120 秒 statement 超时，按稳定顺序短时锁住所有现有 public 业务表的写入，读取仍可进行；
任何内容变化或超时都退出，不循环持锁。归档时间按现有 `timestamp(3)` 精度冻结，提交后可凭同一意图独立核验。

apply 必须在首次兼容镜像部署后执行，旧生产镜像不具备新 gate 时不得冒充已关闭入口。原 `drain-status`
增加迁移前只读分支：两次严格确认 `unmigrated`，使用原前置 PostgreSQL 查询、真实双 Redis 采样和运行实例
前后复验，要求实际 Core 连接同一目标库且 `schemaReady=false/route=off/V1 fresh=false`。输出明确标记
`schemaState=unmigrated`、V2 数据事实因结构不存在而为空、`redisIndexes=null`；不初始化或伪造 marker。
这一前置报告用于具名旧执行退出，不替代原 forward 的全空检查或迁移后 `verify-drain` 完整索引证明。

### 生产 Python 3.10 时间戳兼容

生产只读 preview 发现48条冻结任务中6条 PostgreSQL JSON 时间戳使用 `.55/.42/.09/.43/.7/.96`
等省略末尾零的小数秒；Python 3.10 的 `datetime.fromisoformat` 不接受这些长度。维护脚本只将
合法时间戳的1～6位小数秒右补零至6位后解析，不改变实际时刻、不舍入或截断精度；无小数秒、
`Z`／带时区偏移及原 UTC 归一化继续兼容。超过6位小数、非法日期时间及非字符串必须返回固定安全错误，
不能把坏输入变成有效冻结条件。用真实 Python 3.10 和本机测试验证短小数与完整小数相等、
微秒差异仍拒绝、非法输入不泄露原文；不改变归档选择器、事务、DDL 或任何小说成果。

## 发布与配置

- 先完成隔离验证和真实开发库验证，再按既有 Runbook 备份、迁移正式库并执行指定账号 canary。
- 可以主动准备独立 execution Redis、配置文件备份、精确发布镜像、服务密钥与受控开发验证环境；
  不在内存不足的生产主机同时启动另一套完整业务栈，不在服务器构建镜像，不改已有供应商密钥或计价。
- 代码部署、schemaReady、试用 allowlist 与全量开启分别验证；生产视频始终关闭。全量路由必须在
  试用通过后启用，不再为聊天历史保持新请求的 V1 执行兼容。
- CLI 命令面若有变化，先同步维护说明；本次运维脚本不得加入普通 CLI／Operator 的命令白名单。

全量配置补齐 `route=all`：只允许 `schemaReady=true` 且 `V1 fresh=false`，小说级入口仍必须有有效
用户和小说归属，用户私有资产入口仍必须有用户归属；不绕过认证、权限、readiness、计费或视频关闭开关。
既有幂等 Run 保持原引擎，不批量转换旧记录。发布脚本与 `all` 验收阶段要求已迁移且已有 V2 事实、
精确兼容的回滚镜像、contract 与 execution journal 正常；这些机器检查不等于业务 canary 成功，
首次全量前仍必须记录指定账号公共 CLI 的真实 canary 结果。不开设新的审批框架或凭据服务。
全量发布的目标和回滚 Core 必须同时通过 `core-all` 镜像检查，包含明确的 all 能力标签；
不能仅凭 V2-aware 类存在就把只支持 off／allowlist 的旧 Core 当作全量配置下可启动的回滚镜像。

## 验收

真实 PostgreSQL 证明精确 ID、状态竞争拒绝、幂等、成果逐值不变、无级联删除；迁移 drain 回归证明
静态候选不阻断但 applying／活动命令仍阻断。验证新引擎可继续读取与使用原设定、大纲和正文，旧中短篇
版本仍可列出与预览，且没有因维护导致新增模型调用、扣费或正式成果写入。所有服务器动作记录真实终态。

### 真实 canary 暴露的 CLI 会话创建缺口

本轮实际新建隔离小说后，`long.session.list` 返回空数组；Novel／Chapter 创建、运行启动与恢复均不隐式
创建 WritingSession。问答要求非空 `writingSessionId`，因此原125命令不能独立完成新小说问答。
只补齐普通公共 CLI 的 `long.session.create`，映射已经存在的 `POST /api/v1/writing/sessions`：

- 输入为 `novelId`、`chapterId`，可选 `title` 和本地 `profile`；使用原认证／Keychain，不传 origin 或 token。
- 两个 ID 为1～256字符字符串；title 可省略或 null，非 null 时为1～500字符字符串；拒绝其他字段，
  Java／Python 按同一 Unicode 字符计数与错误契约验收。
- 输出原公共 `WritingSessionResponse`；创建不调用模型、不写正文／设定／大纲，也不新增 Core API 或数据库结构。
- 原接口没有请求幂等字段，不伪造 `clientRequestId` 支持；网络结果不确定时先按同小说／章节读取会话核对，
  不自动重试创建。canary 使用具名标题记录唯一结果。
- 普通 CLI 注册表从125增为126，Java与Python契约对照同步；Operator仍为45命令／三操作，仍拒绝该命令。
  同步当前产品基线、CLI README和Skills维护说明；历史125基线明确保留为历史，不机械全仓替换数字。

这只是已有公共能力的缺失入口修复，不把会话完整 CRUD 或任意 HTTP 功能加入 CLI。

本次实际结果、测试计数、备份位置、开发结构指纹及生产未执行事项统一见
`docs/audits/2026-09-06-durable-agent-release-preflight.md` 的2026-09-07分节；CLI 实际安装哈希与
Skills 更新说明见 `docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md` 文末。
