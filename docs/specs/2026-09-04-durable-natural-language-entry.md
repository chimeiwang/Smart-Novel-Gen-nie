# 普通聊天的耐久意图解析与澄清

日期：2026-09-04。状态：本阶段仓内接线及本地验收完成；安装包与生产尚未切换。

## 目标与范围

落实 `2026-08-31-core-owned-durable-agent-execution.md` 已批准的自然语言入口：每条普通新消息创建独立
Run，Core 先派发低成本、无工具的 `resolve_intent`，再在同一 Run 内执行规范操作；不确定时明确询问作者。
章节问答、规划、正文采用既有业务处理器，不新增创作功能。初始自然入口只可选择当前已经实现的
`long_serial.answer_question`、`plan_chapter`、`write_chapter`；选区继续使用显式来源绑定请求。
其余操作继续按原总计划迁移，不能因本阶段未支持而删除原目标，也不能猜成问答、回落旧图或直接生成正文。

本阶段不修改数据库结构、生产发布体系、账号凭据、生产视频开关或 Skill 的既有允许集合。
现有具名迁移已允许未决 operation 和追加 Evidence/Step，复用其约束，不新增表或绕过不可变保护。

## 输入与交互

- 普通新消息使用现有 `POST /api/v1/writing/runs` 的显式自然分支：`inputMode="natural"`、
  `workflow="long_serial"`、`clientRequestId`、`novelId`、`chapterId`、`writingSessionId`、完整
  `userInstruction` 和可选 `targetWordCount`（沿用默认 4000）。不得混入 operation、target、scope、
  selectionTarget 或 selectedAgents。旧显式分支和历史 V1 读取保持兼容。
- 只有回答当前澄清才继续同一 Run。新增具名 `POST /api/v1/writing/runs/{runId}/clarification`，
  请求绑定 `clientRequestId`、`expectedRevision`、`decisionStepId`、完整 `userMessage`；返回 V2 权威快照。
  同标识同请求重放原响应，异内容或过期决定拒绝；不使用 V1 `/resume`，不复用 Artifact revise。
- 快照增加可恢复的 clarification 对象 `{clarificationCode,prompt,decisionStepId}`，只在相应
  waiting_user 中出现，与 Artifact 互斥；旧快照未包含该字段时保持合法。SSE 的已有澄清事件保持同义。
- Web 明确区分普通新消息、澄清回答、草案返工三种动作。普通下一条消息不得因存在旧 taskId 自动 resume；
  澄清时显示完整问题及专属回答动作，刷新后从快照恢复。不把澄清显示为“候选已就绪”。

## 系统 Step 的契约

- `ExecutionStepRequest.operation` 仅在 `purpose=resolve_intent` 时允许且要求为 null；其他现有用途仍
  必须有业务 operation。resolver 不绑定 Artifact，不填假业务 Operation，不进入 Operation handler 分派。
- 新严格 `IntentResolutionInput` 保存完整 userInstruction 和按顺序的 `clarifications`（最多两次），
  每次含 decisionStepId、prompt、userMessage；唯一 decisionStepId，任何消息不得静默截断。
- 唯一 `intent_context` JSON Evidence 使用 `evidence.system.intent.v1`，包含已验证的
  workflow、novelId、chapterId、chapterTitle 与 availableOperations。每项含 operation、description、
  targetType、scopeKind；均为当前章 chapter 范围，列表无重复，只含本阶段已实现并授权的操作。
  不加载章节正文、设定全集、历史模型消息或 selectedAgents 进行分类。
- `IntentResolutionOutput` 是既有 ProposedCommand 的受限子契约：模型只提出 workflow/operation、
  confidence 或 clarification；targetType/targetId/scopeKind 必须为空，arguments 必须为空对象。
  Core 根据已验证章节补齐身份及范围，不信任模型提供资源 ID、字数、正文或新指令。
- Agent 校验输出符合所给 availableOperations；结果使用既有 `resultKind=proposed_command`，完整
  ProposedCommand 参与 resultHash。无效结构明确失败，不用自然语言关键词猜测或自动修补输出。
- 意图 Profile 使用 disabled reasoning、interactive lane、一次主调用；Step 上限 input/cache-miss
  8000、completion/visible 1000、reasoning 0、cost 50000 micros、30 秒、最多 2 次已定义供应商重试，
  protocol corrections 为 0。完整经过 reservation、usage、journal、fence、取消、重启与终态回放。
  当前 Agent 模型部署映射必须完整绑定 Profile/Prompt/Schema/能力，不能只打开 supported 标志。

## Core 的不可变计划与同 Run 续接

- 保持既有 planVersion=1 和历史哈希原样。新增待解析计划版本，冻结 resolver、可选操作的完整旧版子计划、
  最多两次澄清以及外层总预算。operation=null 的 Run 保持初始身份，不能解析后 UPDATE operation、target、
  input、budgetJson 或 modelPolicyJson；旧迁移已明确禁止这些改写。
- 外层预算在 Run 创建时固定为“可选业务计划各维度的最大值 + 最多三次 resolver 的预算”；不因解析完成或
  作者回答追加额度，原 resolver 实际费用始终计入累计用量。业务阶段同时受所选子计划原预算约束。
  `maxProviderRetriesPerStep` 是每 Step 上限，只取业务与 resolver 的最大值，不按三次累计；其余累计维度
  才相加。当前全部三个子计划对应外层 9 次调用、204000 input/cache-miss、43000 completion、16000
  reasoning、27000 visible、2150000 micros、990 秒、每 Step 最多 2 次重试、预留 1 个业务纠正 Step。
- 有效命令通过追加的不可变控制 Step 保存，绑定解析结果、选中子计划哈希和来源 Evidence；解析完成后在
  同一事务冻结业务 Evidence、创建 generation、发出 intent_resolved/evidence_ready。不创建第二个 Run。
- 模型提出合法操作且 confidence >= 0.85 时才可选择。低置信度转明确澄清；未支持操作不得暗转其他操作。
  每个问题保存不可变决定事实；回答追加新事实与下一 resolver，旧问题/回答不改写。最多两次回答后仍不确定，
  Run 以可解释的 `INTENT_UNRESOLVED` 失败，作者可重新发出更明确的新请求。
- 派发、回调、计费、审核、查询和跨 V1/V2 互斥必须一致读取“初始身份、有效操作、外层预算、业务子计划”。
  未解析时保守视为可能写，不能绕过章节互斥；解析后沿用已选操作的正式审核及应用规则。
- 新 Run 仍受 schema、route、用户和作品 allowlist、实时 Agent fingerprint、归属及会话校验；既有幂等
  重放优先，不因 Agent 暂时离线失效。自然分支未完整接通前不能开启 Web 入口或报告全量切换。
- resolver 已完成但业务来源准备被确定性业务错误拒绝时，保留该解析 Step 的成功结果及计费，并将 Run
  以对应稳定业务错误结束，不让整条回调回滚后停留在 running。数据库、未知程序异常和临时服务错误仍
  原样失败重试，不冒充业务终态；准备端口只读，不得在失败前修改正式内容。

### 同 Run 接线的持久材料

- 初始 Run 固定当前章节的 targetType=chapter/targetId，operation 保持 null，兼容 kind=chat；解析不能
  换章节。原始自然请求、字数和会话在 input 中冻结，intent_context 以当前章节 ID 为 resourceId。
- 唯一 `intent_selection` 是已完成的 persistence/control Step，不含模型身份或 BillingReservation。
  其 input 使用 `durable.intent-selection.v1`，保存 runId、operationKey、operationPlanSha256、
  resolverStepId、resolverResultHash、intentEvidenceBundleId、targetType、targetId、scopeKind。
  inputHash 绑定完整材料；查到重复 selection、错误目标或计划哈希必须拒绝，不从最后一个 Step 猜操作。
- 每个 `intent_clarification` 是已完成的 user_confirmation/control 问题事实，其 input 保存
  schema=durable.intent-clarification.v1、runId、resolverStepId、resolverResultHash、intentEvidenceBundleId、
  clarificationCode 和完整 prompt。其 Step ID 即 decisionStepId；是否仍待回答以 Run waiting_user 和后续
  回答事实共同判断，不能保留 pending control Step 冒充活动模型任务。
- `intent_clarification_answer` 是已完成的 user_confirmation/control 决定，保存稳定 clientRequestId、
  expectedRevision、decisionStepId、完整 userMessage；inputHash 绑定完整输入，受理响应只在 output 保存一次，
  resultHash 绑定该完整响应。Run 锁内对账后才追加新 resolver，
  不改写原问题或旧回答。相同请求重放保存的响应，不随后续任务进度漂移。
  回答 Step 使用真实 completed user_confirmation/control 与 fencingToken=1；同事务发既有
  `step_finished{stepId:answerStepId,fencingToken:1,status:completed,errorCode:null}`；受理响应携带真实 pending
  resolver，既有 dispatch 成功领取后再以真实 attempt/fence 发标准 step_queued，不新增数据库事件类型。
  回答方以 API 权威响应清除 clarification；其他观察者在待澄清期间
  收到未知 step_finished 时回读 snapshot，不从该事件猜测新状态或当成 Artifact 决定。
- 新业务 Step 的 userInstruction 在无澄清时原样沿用原指令；有澄清时使用 Core 确定性生成的完整 JSON 文本
  `{initialInstruction,clarifications:[{prompt,userMessage}]}`，保留所有原文。模型不能另造规范指令或参数。
  新业务 Evidence 在解析受理事务中冻结，首个模型 Step 的幂等键仍为 runId.stepId。
- 统一有效执行上下文只解析初始冻结计划与唯一 selection 事实，公开 operation 可投影为所选短名；数据库
  operation 仍为空。业务 generation/review 使用所选子计划，resolve_intent 使用初始 resolver。外层总计费
  始终统计全部模型 Step，业务子预算只统计业务阶段，不抹去解析费用或挤占原有六调用上限。

## CLI、文档与验收

通用 CLI 复用 long.agent.start 的自然输入分支；long.task.resume 仅在显式 inputMode=clarification 时
转发新澄清入口，旧 V1 输入保持旧语义。watcher 按快照等待原因输出澄清问题/decisionStepId/revision，
不强求 Artifact。命令名仍为 125 个，但输入与 JSONL 行为变化必须同步 Java/Python 对照和 Skill 更新文档。
两份受限 Operator 仍只允许原三种显式操作，继续拒绝自然启动和澄清模式，不自动扩大 45 命令的业务范围。

验收必须覆盖：

1. 严格输入/输出、null operation 条件、完整消息、所选操作集合、无 ID/参数越权、Profile/预算/哈希绑定；
2. initial、pending/running recovery、provider 前取消、usage 与一次物理调用及迟到回调；
3. 同 Run 解析成功/澄清/回答/终态，跨 V1/V2 幂等与互斥，过期和并发回答原子零副作用；
4. 解析费用不丢失，业务全部复审和返工保留原预算，预算不足不创建半轮任务；
5. 普通两条消息两个 Run、澄清回答同 Run、刷新恢复、候选决定无回归、Java/Python watcher 对照；
6. PostgreSQL 集成、跨进程 Fake 全链、共享契约、Mypy/Ruff、Java verify、Web/生成客户端门禁。

阶段结果必须分别记录执行器支持、Core 接线、Web/CLI 可用和真实环境验收，不能用基础层单测代替入口完成。

## 前一检查点状态（提交 6db43a0）

已实现自然入口所需的共享契约、执行器与 Core 计划/裁决基础：

- 232 个机械导出的共享模型包含六个新增意图/澄清模型；Core/Agent OpenAPI 与 TypeScript 客户端已重新生成。
- Agent 的 resolve_intent 已具备完整 Profile/Prompt/Schema/部署映射/预算，不调用业务工具。初次授权和
  保留旧依赖的恢复分别校验；重复提交、终态回调重试、执行服务重建不重复模型调用，缺 journal 的
  running recovery 明确报告 MODEL_OUTCOME_UNKNOWN。相关服务测试使用隔离 journal 与回调测试协作者，
  不是新自然入口的真实 Core 跨进程验收。
- `IntentExecutionPlanSnapshot` 冻结版本 2 外层计划，嵌入完整版本 1 业务子计划。既有版本 1 存储形状
  不变；`DurableIntentDecision` 只负责已授权操作、置信度和两次澄清限制，不执行数据库状态推进。
- Core 已补齐 proposed_command canonical hash 投影、生成 Schema 的 maxProperties 校验及
  ProposedCommand.arguments 显式 null 的精确拒绝。省略 arguments 仍按既有共享契约补 {}，不能把两者
  混淆；问题原文和内层 JSON null 不被改写。固定结果哈希向量由 Python 独立计算并在 Java 复验。
- 专项测试发现并修复“取消已到达，仍可能先开始 Provider”的入口竞态；该情形现在零模型调用。
- execution manifest 指纹为
  `7405feccad1c014edbae8833ce260e2db67772b96d90d2814af9892203382142`。
  业务 Catalog 仍为 4/21 已接通，新增的是一个系统用途的执行器支持，不增加业务操作或生产开放范围。

该检查点尚未完成的工作（后续结果见文末）：

1. 自然输入公共分支及 Core start/replay、同 Run 意图结果持久化、业务 Evidence/Step 续接；
2. dispatch/callback/billing/review/query/SSE 统一读取初始外层计划与所选业务子计划，保留解析费用和各自预算；
3. 具名澄清入口、决定 CAS/幂等、消息持久化与取消/迟到回复收敛；
4. Web 普通新消息/澄清/草案返工三分流、Java/Python CLI watcher 和输入模式、对应 Skill 更新说明；
5. 本规格列明的 PostgreSQL 与完整跨进程自然入口 E2E。

该检查点没有新建自然 Run 的公共入口，既有普通聊天仍走 V1；没有修改 CLI 命令实现或本机已安装的 Skill
运行包，没有推送、部署、远程数据库变更或真实模型调用。这是实施检查点，不是自然入口、整体 Agent
重构或生产验收完成；其余原定业务迁移和 V1 退役仍须继续。

### 本检查点验证证据

- 先行缺实现红灯：`/tmp/inkforge-intent-core-red.log`、`/tmp/inkforge-intent-plan-red.log`。
  跨语言显式 null 和 maxProperties 行为红灯：`/tmp/inkforge-intent-json-schema-red.log`；测试本身的
  Jackson 泛型编译问题单独保留于 `/tmp/inkforge-intent-json-red.log`，不把编译失败当作行为已覆盖。
- 最终完整 Python：4387 passed、3 skipped，仅既有 Starlette 弃用警告，证据
  `/tmp/inkforge-intent-python-final.log`。首轮 4386 passed、1 failed 是公共 OpenAPI 字段集合测试尚未
  计入新 clarification 字段，已补精确可选引用/闭合字段断言，并通过 14 项公共契约测试及完整重跑。
- 完整 Maven verify：5/5 模块成功；服务身份 11、契约 5、Core 747（3 项跳过）、CLI 120，无失败；
  证据 `/tmp/inkforge-intent-maven-full.log`。其中新计划 31、意图裁决 7、输出 Schema 12、结果投影 4、
  真实 Spring mapper 4 项全部通过。
- Web 327 与 API 客户端 3 项通过；typecheck、lint、api:check、生产构建通过，日志前缀
  `/tmp/inkforge-intent-` 下的 `web-tests/typecheck/lint/api-check/build.log`。
- Ruff 全仓、Mypy 280 个源码文件、机械执行资产/Agent OpenAPI 漂移检查、git diff --check 通过。

上述验证包含既有 PostgreSQL Testcontainers 回归，但不包含尚未接通的自然入口数据库状态推进、真实
Core/Agent 端到端澄清、真实供应商或生产验收；这些仍在前述未完成清单中。

## 当前接线与本地验收结果

本轮在同一分支追加自然公共入口、同 Run 解析结果收敛、澄清决定和客户端接线。Core 保持初始 Run 身份
不可变，通过控制 Step 保存问题、完整回答与业务选择；业务 Evidence 在选定操作时冻结，派发、预算、
查询、SSE 和审核使用同一个有效执行上下文。自然回调的成功、等待、失败和取消已纳入 PostgreSQL 定向测试。

通用 Java/Python CLI 已接自然启动、澄清回答与等待原因；Web 已区分新请求、当前澄清、草案返工和明确的
旧 V1 恢复。受限 Operator 仍拒绝这两个新输入模式，不扩大现有命令或操作允许集合。CLI 行为示例和
Skill 更新要求见两份 CLI README 及 `2026-09-01-durable-agent-v2-operator-skill-update.md`。

本地最终验证如下：

- 完整 `./mvnw --batch-mode --no-transfer-progress verify`：5/5 模块成功，服务身份 11、服务契约 5、
  Core 837（3 项环境门控跳过）、CLI 125 项，无失败。证据 `/tmp/inkforge-natural-maven-verify-final.log`。
- 完整 Python：4467 passed、3 skipped，仅既有 Starlette 弃用警告，证据
  `/tmp/inkforge-natural-python-final-5scenarios.log`。首轮 4 个失败是旧 API 数量断言，已按真实生成结果
  修正为公共 119 路径/152 操作、完整 154 路径/187 操作；不是修改业务行为迎合旧数字。
- Web 335 项及 API 客户端 3 项、typecheck、lint、生产构建、api:check 全部通过。日志分别为
  `/tmp/inkforge-natural-web-tests.log`、`/tmp/inkforge-natural-typecheck-final.log`、
  `/tmp/inkforge-natural-web-lint.log`、`/tmp/inkforge-natural-build.log` 和
  `/tmp/inkforge-natural-api-check-final-20260904.log`。
- 全仓 Ruff、服务 Mypy 280 个文件、CLI long Mypy 24 个文件及新增跨进程测试模块的 Mypy 通过。
- 独立复核复现并修复了“resolver 成功后业务准备被拒绝，回滚整个终报而卡住”的问题。先行行为红灯在
  `/tmp/inkforge-natural-preparation-red.log`；修复后 34 项回调测试通过，证据
  `/tmp/inkforge-natural-preparation-green.log`。确定性业务拒绝保留解析结算并结束 Run，临时/未知异常
  不被吞掉；取消中的迟到意图结果不会新建业务 Step。

真实隔离 Core/Agent/PostgreSQL/Fake Provider 的 `natural-entry` 五场景全部通过：

1. 自然问答在同一个 Run 完成；
2. 同会话相同完整原文、不同 clientRequestId 创建两个独立 Run，旧 start 重放仍指向原 Run；
3. Core 重启后恢复澄清，回答后同 Run 生成规划、编辑复审并由作者批准；
4. 两次回答仍不明确时第三个 resolver 结束为 `INTENT_UNRESOLVED`，不再创建问题或业务；
5. 自然正文生成、双复审及作者采用，正式内容按既有业务规则写入。

上述场景逐模型 Step 核验唯一物理 Provider 调用、TokenUsage/Reservation 绑定、完整原文和历史、
不同业务 Evidence、不可变初始 operation=null 与公开有效操作，并证明控制 Step 不占模型或计费。
首轮四场景报告为 `output/durable-agent-v2-e2e/20260904-natural-entry-1/report.json`，补齐连续消息后的
最终报告为 `output/durable-agent-v2-e2e/20260904-natural-entry-2/report.json`。第二轮复用与首轮完全一致的
Core/Agent 镜像 ID；两轮均未访问开发服务器数据库、生产或真实模型供应商，隔离容器、网络、卷和临时密钥
目录已完整清理。测试宿主机并非实际 2 核 2 GB，报告中的该整机性能验收仍为 not_proven，不冒充生产性能证据。

这只完成本规格的三项自然可选业务入口；Catalog 仍为 4/21 已接通。本轮未更新本机已安装 JAR 或活动
Skill，未推送、部署、修改数据库结构或执行远程写入。原总目标的其余 17 项业务迁移、V1 退役、真实
开发/生产具名迁移和真实供应商验收仍须继续，不能把本地 Fake 通过说成整体 Agent 重构或生产交付完成。
