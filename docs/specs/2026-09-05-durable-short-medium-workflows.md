# Durable Agent V2 中短篇四操作迁移

日期：2026-09-05。状态：四项仓内接线、隔离跨进程和全仓门禁通过，Catalog 已启用 16/21；未部署生产。
前序提交 `8427de6` 的仓内完成计数为 12/21；本规格完成原计划中短篇 generate_outline、generate_manuscript、
replace_selection、full_check 四项，不代表剩余五项或总目标完成。

## 目标与范围

把现有中短篇模型执行迁移到 Core 权威的 WorkflowRun/Step、冻结 Evidence、计费与 execution journal。
不改变双文档产品、版本预览/确认/采用、6,000～80,000 字范围、起始素材与正文溯源规则；不引入长篇自动
复审、自动采用、下一阶段自动启动或新的 CLI 命令。不修改数据库结构，不部署或更新固定安装包。
其余五个未迁移操作不在本批实现范围，生产与真实模型验收仍在总目标中，不能用本批替代。

事实依据：当前 ShortMediumRunAssembler、ShortMediumCompletionMaterializer、ShortMediumVersionService、
Agent jobs/short_medium.py、共享 short_medium 契约、03/04 号需求和总执行内核规格。旧规格中的图名称不代表
实际使用 LangGraph：当前中短篇是专用串行 handler，不得为迁移额外引入业务图。

## 必须保留的业务语义

| 操作 | 来源与输出 | 完成后状态 |
| --- | --- | --- |
| generate_outline | 完整起始素材、可选已应用蓝图及完整指令；生成完整蓝图文本 | Run completed，一份 awaiting_user 版本 |
| generate_manuscript | 当前已应用且干净的蓝图、可选正文底稿、固定起始素材；串行生成完整正文 | Run completed，一份 awaiting_user 版本 |
| replace_selection | 已应用基础版本、完整正文/蓝图、Unicode 码点范围及哈希；仅生成 replacement | Core 拼接完整候选；Run completed，不采用 |
| full_check | 已应用完整正文、其原来源蓝图及既有上下文；完整文本报告 | Run completed，checkReport={text:原文}，无候选 |

中短篇的生成任务完成与版本采用是两个生命周期。继续使用现有 short.version.preview/adopt 和
confirmationHash；不能改为长篇的 waiting_user → long.artifact.approve，也不能把生成完成当作采用完成。
自动保存不创建版本，人工提交/恢复/显式来源大纲重绑定保持原语义。当前工作稿变脏、基础版本变化和固定
开头/结尾等已有校验继续由 Core 执行，不额外增加全资料 CAS、每段字数下限或必须精确达到目标字数的限制。
此处的基础版本冲突指目标文档的 applied head；来源蓝图则验证启动时冻结的精确已应用版本及完整哈希，
不要求它在生成结束时仍是最新蓝图。旧物化器与采用服务均无源蓝图最新 head 门禁，正文选区与检查还会沿用
正文自身的历史来源；不能借本次迁移增加源蓝图 CAS 或悄悄改绑新来源。

## 执行与来源契约

公共启动继续使用 ShortMediumStartWritingRunRequest 原字段。来源文本、目标字数、当前工作稿与版本内容均由
Core 读取，调用者和模型不得补写。显式原文按现有 Core 规范化后冻结；V2 新模型不另做 strip、截断或字段补猜。
蓝图 Run 不伪造章节身份；正文绑定既有唯一 Chapter。内部 target 使用 Catalog 的短篇文档类型，选区使用
document_selection scope，其余使用 novel scope，不改变公共请求形状。

初始 bundle 包含唯一 short_medium_context JSON，保存原 assembler 的完整二十字段快照，含已提供的
全文、来源、版本、哈希与选区前后文。保留 null、缺少业务来源的合法状态和完整 Unicode，不从后续 workspace
回填。初始 Run input 保存规范化公共业务请求，clientRequestId 继续使用独立身份列而不重复写入 input；
模型 Step input 只保存 Core 派生的 segmentIndex/segmentCount。

新共享严格模型独立于 V1 strip 类型，校验 operation/document 组合、完整内容哈希、选区重建及分段身份。
生成器只返回语义字段：蓝图/正文段为 {content}、选区为 {replacement}、检查为 {text}，均保持当前执行器的
非空字符串要求，不顺便把纯空白升级成通用新禁令。Agent 在校验后派生对应 UTF-8 SHA-256；模型不生成版本
ID、segment manifest、序号、确认哈希、状态或用量。Core 独立复验冻结 Schema、完整原文与派生哈希。

旧四项 Profile/Prompt/Output 的 unsupported 占位保持可追溯；新增明确版本的真实资产和每 Step 预算。
四项均是 generation，不是绑定 Artifact 的 Reviewer；尤其 full_check 不沿用占位中的 evaluation purpose，
也不新增评分模型。三项创作保持 enabled/high，检查保持 disabled；不走 V1 模型授权/计费旁路。
沿用 V2 Catalog 的 creative / batch_media 车道：前三项 creative、full_check batch_media；与 V1 检查使用
creative 的区别必须明确记录，不把车道调度迁移解释为产品检查语义变化。

## 耐久正文分段

分段数由 Core 按 ceil(targetTotalWordCount / 15000) 确定，6,000～15,000 字为一段，最多六段。
保持按蓝图顺序串行，不预派并行段；每段是一个独立模型 Step，一段成功的原文与结果哈希立即持久化。
下一段使用新 Evidence bundle，保留原 context 并按连续序号加入已有成功段的完整内容、来源 Step 和哈希。
Agent 校验原来源唯一、段号连续、段数匹配及完整前缀；不能接受重复、缺失、乱序或未经 Core 冻结的段。

每个后续请求保留完整已完成正文前缀，不只携带尾部摘要；固定开头只由首段承担，固定结尾只在末段承担。
模型只输出当前连续单元，Core 按原规则无额外分隔符拼接。最后一个模型 Step 成功后，Core 写入零模型的
持久化汇总 Step，保存有序生产 Step/哈希、最终全文哈希及唯一业务结果引用；manifest 由 Core 生成。
最后统一验证完整字数、固定素材、基础来源与实际版本写面，再创建一份候选。中间段不创建候选或工作稿版本。
length、过滤、未知完成原因和工具输出仍失败，不能把截断响应当续写信号；重启不得重新调用已完成段。

调用上限保留 1/6/1/1，正文真实数量按冻结 segmentCount 约束；没有 Reviewer 或自动返工。
每段须有有限的独立输入、cache-miss、completion、reasoning、visible、费用和墙钟预算，完整六段之和不得超出
冻结 Run 总额；旧全局 384000 不能复制给每段。具体资产向量在实现前核对并补记，不把 placeholder 当实际可运行配置。
取消、未知用量、重放及供应商不确定结果使用现有通用协议，不增加重试旁路。

### 冻结预算向量

实读 Java assembler 的 `emptyPayload()` 与 V1 共享模型确认均为 20 字段；先前口头计数 22 属于误计，
不新增字段补齐数字。新 Context 保留全部字段（包括显式 null），所有原文保持原字节语义。

以下各列依次为调用数、输入、无缓存输入、completion、reasoning、visible、费用微单位、墙钟秒。
每个模型 Step 均 `maxProviderRetries=2`、`maxProtocolCorrections=0`；Run 同为 2/0。
当前未实现的 `protocol_correction.parentOperations` 同步移除本批四项：它们没有该用途关联，
不得因旧占位关联预派纠错模型调用。其余父操作及通用预算一致性断言保持不变。
零模型汇总不追加模型额度。正文 Run 是六段上限的逐项和；实际 1～6 段由来源目标字数确定。

| 操作/层级 | 调用 | 输入 | 无缓存 | completion | reasoning | visible | 费用 | 秒 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 蓝图 Step/Run | 1 | 120000 | 120000 | 24000 | 12000 | 12000 | 500000 | 300 |
| 正文单段 Step | 1 | 240000 | 240000 | 40000 | 8000 | 32000 | 1000000 | 300 |
| 正文 Run | 6 | 1440000 | 1440000 | 240000 | 48000 | 192000 | 6000000 | 1800 |
| 选区 Step/Run | 1 | 240000 | 240000 | 24000 | 12000 | 12000 | 500000 | 300 |
| 全文检查 Step/Run | 1 | 240000 | 240000 | 24000 | 0 | 24000 | 500000 | 300 |

输入上限覆盖冻结全文、选区前后文、完整已完成前缀与协议开销；无缓存输入与输入上限相等，不以命中缓存
作为执行前提。超出完整输入预算必须明确失败，不裁剪任何来源。预算不是新的作品字数规则。

## Core 业务接线与兼容采用

启动复用 ShortMediumRunAssembler 的真实来源和干净工作稿校验，加入现有跨引擎幂等与配置路由。
不创建影子 WritingTask、WritingRunCommand、GraphState 或 V1 outbox；V1 旧任务继续按原路径恢复与查询。
Workflow 模块通过自身应用端口请求中短篇业务物化，不反向导入 writing/shortmedium 内部实现。

V2 候选继续保存原 ShortMediumVersionPayload、完整 Diff 和 revision 1，ReviewArtifact.taskId 为空、
workflowRunId 绑定真实 Run；兼容来源字段 sourceTaskId 表示该 Run，sourceJobId 绑定真实产出身份，不能伪造
WritingTask 外键。候选、汇总结果、Run/Step 完成、用量及 WorkflowEvent 在同一事务收敛；报告不创建 Artifact。
公共通用长篇采用入口不能把中短篇版本当成长篇正文草案应用，中短篇继续走原版本 API。

V2 全文检查复用通用 kind=quality_check，但 sourceType 是 short_medium_manuscript。旧一致性终检的扫描和
运行读取必须限定其原有 sourceType=quality_check，不能仅凭 kind 接管短篇 Run。此处只隔离旧队列与新执行器，
不提前迁移一致性终检，也不新增质量门禁；使用既有来源字段，避免要求未迁移数据库提前存在 V2 列。

当前采用幂等保存依赖 V1 WritingRunCommand，须为 V2 增加既有 WorkflowStep 的零模型持久化回执适配。
回执绑定同一用户/小说/候选和原确认请求；已完成的生成 Run 不回到 running/waiting_user，也不改旧版本 payload
存回执。优先复用既有锁、版本仓储与 confirmationHash 规则，不新增表或第二份作品状态。V1 采用回执保持原路。

## 公共查询、Web 与 CLI

先修改 Python 权威 WritingRunV2Response，新增可选 candidateVersionId 和 checkReport 投影并生成客户端。
它们只能来自该 Run 的已验证完成收据，不从最后版本列表、SSE 文本或可变工作稿猜测；旧长篇响应不强加空字段。
GET/list 共用精确结果身份投影；SSE 保持有界 WorkflowRunSnapshot，完成事件使用既有 completed
outcomeType/resultId，完整报告以 GET 回读为准，不把报告全文塞进每次快照或重复事件。
不新增 API 路径或操作数量，生成接口发生加法变化须统一复验 Java/Python/OpenAPI 与 TypeScript。

Web 中短篇目前明确拒绝 engineVersion!=1，CLI short.agent.watch 也只读 V1 phase/commandStatus；两处必须
显式区分 V1/V2。V2 使用当前 WorkflowEvent/baseSequence 协议并回读同一 Run 的权威终态，再加载精确候选或
展示完整报告；非完成不能显示成功，断开观察不等于取消。保持双文档编辑、版本 Drawer 与确认流程，不重做 UI。
短篇 CLI 仍为十三个命令，start 四操作/别名和参数不变，不顺便新增 short.agent.cancel。源码、构建、固定包、
活动 Skills 与生产分别验收；所有返回/观察变化同步现有 CLI README 和 Skills 更新契约。

## 实施顺序与验收

1. 严格共享输入/输出、版本化资产、Agent 单 Step 与有界分段输入校验；目录仍关闭。
2. Core 显式启动、逐段完成/接续、唯一候选/报告、采用幂等与查询投影；不借长篇状态机改变产品。
3. Web/CLI 双引擎消费者、完整公共 HTTP/隔离 PostgreSQL 用例及独立跨进程验证，最后才逐项启用。
4. 相关 pytest/Ruff/Mypy/JUnit、完整 Maven、Web/typecheck/lint/build、生成客户端与架构门禁。

必须覆盖四操作、15,000/15,001/80,000 边界、已完成段恢复、完整前缀与 Unicode、固定开头/结尾、基础版本/
工作稿变化、选区外逐字不变、唯一候选、全文报告零候选、重复完成/采用、原确认哈希、取消与未知模型用量。
使用真实 Core/Agent 协议的隔离验证，不把单进程 callback 测试当完整跨进程或真实供应商证据；本批结束仍须明确
尚未实施的其他五项和生产门禁，不缩小总目标。

独立进程需从真实执行资产构建 Core/Agent。公共 HTTP 验证通过后，可在本地未提交候选中打开这四项并重建
隔离测试镜像；这不是验收完成或生产启用。若跨进程验证失败，不提交启用状态；完成跨进程与全仓门禁后才
更新正式仓内完成计数。此测试准备不增加配置入口、资产加载旁路或部署系统。

## 仓内完成与最终验证

四项共享严格模型、版本化执行资产、Agent 单 Step、Core 启动/分段接续/候选或报告、V2 采用回执和查询投影，
以及 Web、Java CLI 与 Python 对照 CLI 的双引擎观察接线已经完成。四项成功测试现读取真实已启用 Catalog，
不再用临时开启的成功夹具；禁用零模型负例仍在隔离目录中显式关闭四项。旧 V1 占位、旧任务与长篇自然入口
授权不变。执行资产指纹为 `244e14ec00c4cf11f02926759ec153aae1c9800b57528e669f1913d02f064b8f`，共享 Schema 285 个。

- 完整 `./mvnw verify` 最终复跑通过：服务身份 11 项、服务契约 5 项、Core 1098 项（3 skipped）、CLI 135 项。
  日志为 `/tmp/inkforge-short-v2-maven-final-2.log`。包含四操作公共 HTTP 启动/回调/GET/采用、重复请求、
  取消、运行期间工作稿变化、历史蓝图来源以及两段完整前缀回归；业务冲突保留已付模型用量但不创建候选。
- 全仓 Python 首轮发现 OpenAPI 精确字段断言尚未加入两个新增可选字段，修正后完整复跑为
  5134 passed、3 skipped，日志为 `/tmp/inkforge-short-v2-python-all-2.log`；保留既有 Starlette 弃用警告。
  后续跨进程测试准备流程补充的离线用例另有 28 passed；最终完整 harness 与其架构测试 259 passed，
  全部架构检查再跑为 359 passed，日志分别为 `/tmp/inkforge-short-v2-harness-final.log` 和
  `/tmp/inkforge-short-v2-architecture-final.log`。
- Web 347 项与 API client 3 项、typecheck、lint、build、api:check 通过。网页缺少完整报告正文的负例先失败
  后修复，终态错误码使用生成契约的 errorCode。日志前缀为 `/tmp/inkforge-short-v2-`，对应 `web-all-1`、
  `typecheck-3`、`lint-2`、`web-build-1`、`api-check-1` 和 `web-report-red/green`。
- 全仓 Ruff、Mypy（324 个服务/共享/CLI 源文件）、执行 manifest 检查及 diff 空白检查通过。

独立 Compose 四场景最终证据为 `output/durable-agent-v2-e2e/20260905-short-medium-3/report.json`，状态 passed。
使用真实 Java Core、Python Agent、隔离 PostgreSQL 和两个 Redis，但模型为测试专用确定性 Provider：

- 蓝图生成并通过原确认接口采用；首次正文生成前通过原预览/人工提交接口把初始固定开头保存为合法基础版本。
- 正文两段串行：首段模型终态已入 journal、回调暂缓时真正重启 Agent，恢复同一终态后继续第二段。
  每段 physical_calls/completed_calls 均为 1，后续请求保留完整已完成前缀；最终只生成并采用一份正文候选。
- 正文选区修改只替换精确 Unicode 范围，候选再次通过原确认接口幂等采用；全文检查 GET 返回完整报告且零候选。
- 四项均无 V1 Task/Command、无 Evaluation；模型 Step、唯一汇总、完成事件、journal、计费预留/结算与
  TokenUsage 一一对应。临时容器、网络、卷与服务密钥已清理，报告保留。

首轮 `20260905-short-medium-1` 的蓝图场景通过，随后因测试遗漏初始工作稿提交而被既有 dirty 规则拒绝；
修复的是测试准备，不是放宽业务规则。第二轮复用同一已构建 Core/Agent 镜像完整通过。

最终兼容复核另复现旧终检调度器仅按 kind 扫描而误读 V2 全文检查的问题：新增真实 V2 pending/running
回归先触发 `WorkflowRun_terminal_time_check`，补充原有 sourceType=quality_check 条件后，旧质量仓储与
短篇公共 HTTP 共 14 项通过。旧调度与运行读取不再接管短篇 Run，V1 终检语义不变；红绿日志为
`/tmp/inkforge-short-v2-legacy-quality-red.log`、`/tmp/inkforge-short-v2-legacy-quality-green.log`。
随后重建含此修复的 Core 镜像，第三轮四场景再次完整通过；不是拿修复前镜像的成功代替最终实现验收。

本批仓内完成计数为 16/21。其余一致性终检、文风画像、RAG 索引与开发视频两项尚未迁移；真实模型、
真实开发/生产验收和固定安装包更新仍未完成。未推送、部署、修改活动 Skills 或访问真实数据库/供应商；
隔离报告也不证明真实 2 核 2 GB 主机验收，更不能替代总目标的生产 canary。
