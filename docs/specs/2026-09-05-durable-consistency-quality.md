# 一致性终检的耐久执行迁移

状态：仓内实现、全仓门禁与隔离跨进程验收完成。基线为 `3609ee6`，本项使仓内完成数由 16/21 增至 17/21。
真实供应商、固定安装更新和生产验收不在本批完成范围内，不将仓内结果当作生产已生效。

## 目标与非目标

将已有 `quality.consistency` 从旧质量队列迁到 Core 持有的 V2 Run/Step。保留原公共质量检查入口、章节送审条件、
报告契约、作者跳过/重置操作及一次显式协议纠正。不新增质量功能、上下文检索、Reviewer、内容修改或发布限制。
`qualityGate=revise` 是已完成的检查结果，不是执行失败；仍由作者决定后续写作。

本批不改变数据库结构，不部署、不推送、不调用真实供应商，不更新固定 CLI 安装包或活动 Skills。
CLI 命令数 125、Operator 允许命令 45、公共 Core 操作 152、内部 Core 操作 34 均不因本项增加。

## 原行为与冻结资料

- 继续由 `POST /quality-checks/{checkId}/run` 受理；返回的 `taskId` 仍是 `WorkflowRun.id`。
  查询、跳过和重置继续使用原质量检查 API。Web 与 CLI 不直接访问 Agent 或内部接口。
- 仅 `review` 状态章节的一致性检查可创建运行；检查项归属、可选 `sourceTaskId` 归属、用户级请求幂等与
  同检查项活动运行互斥保留。V1/V2 共用原 `quality_run` 请求指纹语义，切换路由不能重复创建同一请求。
  原可选 `taskId` 同时识别旧 WritingTask 和同归属 V2 写作 Run；不得因 V2 不创建影子 Task 而拒绝合法来源，
  也不得接受其他用户、小说、章节或质量 Run 冒充写作来源。
- V2 Run 初建时绑定 `sourceType=quality_check_v2, sourceId=checkId`，公共执行目标仍为
  `targetType=chapter, targetId=chapterId`。不在创建后改写冻结身份；旧 dispatcher 只领取 `quality_check`。
- 唯一完整 JSON Evidence 为 `quality_context`，保存 `checkId`、`novelId`、`chapterId`、`chapterContent`、
  `chapterContentSha256`、`sourceUpdatedAt`、`message`、`sourceTaskId` 八个字段，可选值显式为 null。
  只增加来源身份与摘要，不扩充模型业务资料；正文与指令来自创建时快照，不读工作区、设定、大纲或最近章节。
- 首个 Step input 为 `{userInstruction}`，指令沿原空值默认“检查本章一致性”。纠正 Step 在同一 input 中另加
  `failedStepId`、`failedResultHash`、`failureCode`，并沿用原 Evidence；不保存或回放坏工具参数。

## 单次调用与一次纠正

- 使用新版本质量 Profile/Prompt/Output/Step Budget，保留未实现的历史占位资产。正常与纠正都返回完整共享
  `ConsistencyQualityReport`：五维分数、pass/revise、issues、report、可选 rewriteBrief。
  不新增分数阈值，不放宽或额外收紧原 Pydantic 转换与验证语义，不截断报告。
- 保留 DeepSeek Beta strict `submit_quality_report`。以明确的 `quality_strict_tool_v1` 路由绑定模型部署；
  不能把实际工具请求记成普通 JSON 输出路由。真实 strict endpoint 身份必须按实际配置核对。
  其他操作的既有路由和冻结 Profile 不变；一个 Step 仅调用一次模型，不启动多轮 AgentRuntime。
- Provider 继续复用原 strict Schema 投影、两个精确空串归一化路径和不调用模型的缺失容器闭合修复。
  结果仍经原共享报告本地复验。坏响应正文、arguments、异常正文或字段值不得写入终态或诊断。
- 首个生成 Step 仅在正常完成、合法工具身份、JSON/参数校验失败且 token 用量可靠时，返回现有 Failure：
  `errorCategory=protocol, errorCode=MODEL_TOOL_PROTOCOL_CORRECTION_REQUIRED, retryable=false, outcomeUnknown=false`。
  不新增 callback 形状或 resultKind。length、过滤、预算超限、未知完成/用量、缺失工具身份、供应商错误不纠正。
- Core 先正常保存失败 Step 并精确结算，再从该 Run 创建时冻结的 `systemSteps` 新建唯一
  `protocol_correction` Step。Run 继续 running；第二次调用有独立 Step、授权、reservation、usage、journal 与事件。
  重复 Failure 回执不重复追加 Step。取消、待对账用量或剩余预算不足时不得继续调用。
- 纠正失败以 `MODEL_TOOL_PROTOCOL_RECOVERY_FAILED` 等真实终态错误收口，不再次纠正。
  `usage.protocolCorrections` 保持确定性闭合恢复次数语义；显式纠正 Step 由既有 Run purpose 预算单独计数。
- 系统用途只为 `quality.consistency` 开放一次纠正，不扩大其余 16 项操作权限。Run 仍最多两次模型调用、
  一次显式纠正；每 Step 最多一次调用及已有有界传输重试，token/费用/时间使用冻结有限预算。

## Core 报告投影与失效

- 模型完整报告保存到自身 Step/Run，公开检查项只由 Core 同事务更新。平均分沿原 HALF_EVEN 整数规则，
  六个旧商业性字段仍置空；不创建 ReviewArtifact、Evaluation 或 V1 影子任务/命令。
- 成功、普通失败、提交前拒绝、预算拒绝、取消回调和取消租约到期均接入同一个质量业务投影端口，
  不允许检查项永久停在 running。投影在既有 Run/Step/计费事务内执行，不触发新网络调用。
- 正文编辑、草案采用和重新送审继续在自身事务重置检查项；不得在已持 Chapter/Check 锁后反锁 V2 Run。
  使用现有持久状态发现失效：完整正文不同、检查项不再 running 或该 Run 已被新运行取代。
  只比较正文 hash 不足以识别 A→B→A 和同正文重新送审。
- 失效取消复用既有取消协调器：有界发现后调用原 durable cancel，保留 Run/Step/reservation/journal 的
  收敛路径，不新增表、队列或另一份工作流状态。提交后通知可加速，但不能作为唯一恢复依据。
  回调同事务锁定检查项和章节后再次核对有效性，旧结果不得覆盖 pending、skipped 或较新结果。
  已失效的检查不阻止编辑；取消发现窗口内已开始的模型按真实用量结算，不伪称零调用。
- 新运行创建前处理旧运行失效与互斥；路由关闭后仍可读取并收敛已存在 V2，不将旧 V1 回调当成 V2 回调。

## 验收

1. 共享协议、资产哈希与保留资产恢复测试；合法报告、revise 完成、strict 传输、有限闭合修复、一次独立纠正、
   再失败、未知用量和不完整响应拒绝，均有定向测试。
2. PostgreSQL 测试覆盖原 API 路由、跨引擎幂等、归属与活动互斥、完成/失败/取消的检查项投影、正文失效、
   同正文重新送审、迟到/重复终态和账务一致性；不得使用 H2 或真实库 DDL 代替。
3. 独立 Core/Agent/双 Redis/PostgreSQL 的受控供应商测试验证正常及纠正链、终态重放/重启不重复模型，
   不把 Fake Provider 验收称为真实供应商或生产验收。
4. 全仓 Maven、Python、Ruff、Mypy、Web、类型、lint、生成契约与构建检查后复核 17/21 是否成立；
   CLI 原 run/get 路径回归并更新 Skills 维护说明，明确源码、固定安装与生产各自状态。

## 完成证据（2026-09-05）

- 最终 execution manifest：`6a82ee99498b02c83add8b170f119cff02cf36dc18a26fb780dfc236bc74d612`；
  287 个共享 Schema，公共 Core 152、内部 Core 34、CLI 125、Operator 45 不变。
- `./mvnw verify` 全仓通过：身份 11、共享契约 5、Core 1130（3 skipped）、CLI 135；
  `/tmp/inkforge-quality-v2-maven-all-2.log`。覆盖真实 Spring 质量 API、原 CLI 路径、跨引擎请求重放、
  V2 写作 taskId 来源与越权拒绝、迟到报告、正文失效、旧队列隔离和独立纠正/计费/取消。
- 全仓 Python：5188 passed、3 skipped；`/tmp/inkforge-quality-v2-python-all-1.log`。
  最终 harness 289 项另行通过；`/tmp/inkforge-quality-v2-harness-final-2.log`。
  新 DeepSeek strict MockTransport 测试直接覆盖真实请求投影，不仅依赖 Fake 输出。
- Web 347、API client 3 通过；typecheck、lint、build、api:check、全仓 Ruff 与 Mypy 285 源文件通过。
  证据前缀为 `/tmp/inkforge-quality-v2-`：`web-1.log`、`typecheck-1.log`、`lint-1.log`、`build-1.log`、
  `api-check-1.log`、`ruff-2.log`、`mypy-all-1.log`。Core 19 文件与 Agent Service 2 文件基线检查一致，
  manifest 派生检查与最终 `git diff --check` 通过；文档/目录/CLI 基线定向 25 项通过。

独立 Java Core、Python Agent、PostgreSQL、普通 Redis 与 execution Redis 的报告：
`output/durable-agent-v2-e2e/20260905-quality-1/report.json`，`status=passed`。
镜像由本批最终代码重新构建，未复用旧中短篇镜像。

1. 正常终检通过原 run/get API 完成，完整报告、HALF_EVEN 分数与 pass 结论一致；1 个模型 Step、
   1 份预留/结算和 1 条 TokenUsage，模型 physical_calls/completed_calls 均为 1。
2. 首次格式失败已进入 journal、回调尚未送达时真正重启 Agent；重启后重放同一 Failure，Core 只追加一个
   纠正 Step。两 Step 的 physical_calls/completed_calls 各为 1，各有独立结算；最终 revise 报告仍完成。
3. 两场景均唯一完成事件、完整来源与报告，零 Artifact/Evaluation/V1 Task/Command，不修改正文。
   失败和成功 journal 均 delivered，已送达完整终态清除；临时容器、网络、卷和服务密钥目录全部清理。

实施中修复了严格工具路由在已内联 Schema 上的投影兼容、生成 OpenAPI 枚举同步、质量域自己的就绪端口和
精确模块依赖，以及旧测试遗漏的真实 V1 sourceType。没有通过放宽源隔离、降低报告校验或改变产品规则让测试通过。

本批未推送、部署、修改真实数据库、调用真实供应商、重装固定 JAR 或修改活动 Skills。
报告的 `twoCoreTwoGiBHostGate=not_proven` 保持原意，不宣称真实 2 核 2 GB 主机容量验收。
剩余四项为文风画像、RAG embedding 与两个开发视频模型工作流；生产视频继续关闭。
