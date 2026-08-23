# 模型执行策略与复审协议优化规格

**日期：** 2026-08-23
**状态：** 待用户审阅
**范围：** Agent Service 模型策略、DeepSeek 适配、复审错误边界、Reviewer 结构化协议

## 背景

生产环境完成 `TokenUsage.requestId/taskId/runId` 归集后，首个完整长篇正文任务暴露出明确的成本结构：

- 正文生成与自动复审共 22 次模型调用，累计 673,472 token、742.028 积分；
- 写作 Agent 调用 14 次；校验和编辑各调用 4 次；
- 两个 Reviewer 的持久评审结果合计约 6,260 字符，但产生 199,860 个输出 token；
- 正文应用后的一致性终检又产生 4,121 输入 token、18,934 输出 token，消耗约 41.989 积分；
- 全流程合计 23 次调用、696,527 token、784.017 积分；
- 最后一次自动校验已经完成用量上报，却只留下“复审智能体暂时不可用”的兜底结论。

当前生产使用 DeepSeek 官方接口和 `deepseek-v4-flash`。DeepSeek V4 默认开启思考模式，默认推理强度为
`high`，并在响应的完成 token 明细中提供推理 token。现有 Provider 只读取四项总用量，没有读取推理
token，也没有显式选择思考模式或推理强度。

供应商事实以官方文档为准：

- [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion)
- [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)
- [Multi-round Conversation](https://api-docs.deepseek.com/guides/multi_round_chat)

当前所有 Agent 和执行模式共用同一个部署级 `MODEL_MAX_OUTPUT_TOKENS=384000`。该值应继续表达供应商
能力和最后安全边界，不能继续充当所有业务场景的唯一模型策略，也不能简单整体调小来降低成本。

## 当前项目事实

### 缺少执行场景模型策略

`AgentRunner` 已明确区分 `primary/reviewer/reviser/quality`，但 `AgentRuntime` 最终只接收统一的
`max_output_tokens`。写正文、复审、终检和协议修复因此使用相同模型行为。

### DeepSeek 思考模式适配不完整

现有 `ModelMessage` 和 `ModelTurnResult` 没有供应商推理内容字段。DeepSeek 在思考模式和工具调用组合下
要求后续工具轮次带回上一轮的 `reasoning_content`；当前多轮工具循环只保留可见正文和工具调用。

同时，现有实现没有采集：

- `reasoningTokens`；
- `invalidToolCalls`；
- 可见正文字符数和工具参数字符数；
- 本次调用使用的执行策略；
- Reviewer 所属 Artifact revision 和自动复审 iteration。

### 复审业务失败与基础设施失败混淆

`review_worker` 捕获除取消以外的全部异常，并构造普通内容结论 `verdict=block`。Provider、授权、计费
上报、日志、工具协议、Core 持久化和程序错误因此都被伪装成“草案内容被阻塞”。

### Reviewer 协议允许无界自然语言分析

Reviewer 虽然只暴露 `submit_evaluation`，但仍复用普通 Agent system prompt，`summary` 没有明确职责
边界，模型可以在调用终止工具前进行大量推理或输出。现有 `pass/revise/block` 也把内容建议、实质问题
和执行失败混在同一维度。

## 目标

1. 不通过全局缩小 `max_tokens`、截断正文或粗暴减少 Reviewer 数量降低费用。
2. 按 `agentId + executionMode + operationKind + stage` 选择模型执行策略。
3. 完整适配 DeepSeek 的思考模式、推理用量和工具轮次要求。
4. Reviewer 只提交严格、可由程序合并的结构化问题；不对推理或自然语言做硬性长度截断。
5. 基础设施、协议和持久化失败不得再伪装成内容 `block`。
6. Reviewer 调用在 Provider 前必须先形成 Core 稳定 reservation；Agent Service 进程或容器重启后，已提交
   到加密恢复区的结果必须复用，结果不确定时不得自动重调 Provider。
7. 不修改 PostgreSQL schema，不改变 ReviewArtifact 用户确认边界。

## 非目标

本规格不包含：

- ReviewIssue 跨轮问题账本；
- 局部 Artifact patch 应用；
- 自适应 Reviewer 路由；
- Core 写作工具按需查询重构；
- Agent `ReadSession` 和大结果引用；
- 更换供应商或减少双 Reviewer；
- 修改积分价格。

DeepSeek Chat Completions 是无状态接口，当前没有按客户端 requestId 查询历史完成结果的契约。因此，本
规格不承诺从“Provider 已返回、加密结果尚未提交”的不确定窗口恢复成功结果；该窗口必须收敛为明确的
`outcome_unknown`，而不是用第二次 Provider 调用猜测第一次是否成功。

上述能力应根据本规格上线后的真实推理 token 和失败分类数据另立规格。

## 设计方案

### 设计一：模型执行策略

#### 策略契约

在 Agent Service 内新增不可变 `ModelExecutionPolicy`：

```python
class ModelExecutionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policyId: str
    thinkingMode: Literal["provider_default", "enabled", "disabled"]
    reasoningEffort: Literal["low", "high", "max"] | None
    requiredToolName: str | None
    visibleOutputDisposition: Literal["business", "diagnostic_only"]
```

策略由独立解析器根据以下输入确定：

```text
agentId
executionMode
operationKind
stage
```

`stage` 使用稳定枚举：

```python
ModelExecutionStage = Literal[
    "primary", "reviewer", "reviser", "quality", "protocol_repair"
]
```

`CoreGraphAgentExecutor` 显式填写 primary/reviewer/reviser，`QualityJobHandler` 填写 quality，只有独立协议
修复入口可以填写 protocol_repair。`stage`、executionMode、Artifact ID/revision/iteration 同时进入
`AgentRunRequest`、`ModelCallContext`、日志结构头和逻辑模型请求身份，禁止在 Provider 内猜测。

禁止在 Prompt、LangGraph 节点或 Provider 中分别散落角色判断。

`thinkingMode=disabled` 时 `reasoningEffort` 必须为空。`requiredToolName` 必须来自当前
`ExecutionToolContract` 已允许的终止工具，只能缩小工具选择，不能扩大 Operation 或 Agent 权限；
具有多个合法终止工具的普通 Operation 保持自动选择，不强行指定单个工具。

#### 第一版策略

| 场景 | 思考模式 | 推理强度 | 终止工具 | 可见正文 |
| --- | --- | --- | --- | --- |
| 正文 primary | enabled | high | Operation 声明值 | 允许 |
| 正文 reviser | enabled | high | Operation 声明值 | 允许 |
| Reviewer | enabled | low | submit_evaluation | 仅诊断 |
| 一致性 quality | enabled | low | submit_quality_report | 仅诊断 |
| 协议修复 | disabled | 无 | 原目标工具 | 仅诊断 |
| 其他普通操作 | provider_default | 无 | Operation 声明值 | 按现状 |

第一版不改变 `MODEL_MAX_OUTPUT_TOKENS`。它继续作为供应商请求的有限正整数安全上限，由 Core grant
缩小的现有语义保持不变。降本依靠思考策略、严格输出通道和错误恢复边界，而不是依靠截断。

#### 传递路径

```text
CoreGraphAgentExecutor / QualityJobHandler
  -> AgentRunRequest
  -> AgentRunner 解析 ModelExecutionPolicy
  -> AgentRuntime
  -> ModelTurnRequest
  -> Provider capability adapter
```

`ModelTurnRequest` 的规范化序列化必须包含策略字段，因此策略变化会形成新的逻辑模型请求身份；同一策略、
同一消息和同一工具集合的重试仍保持幂等。

#### Provider capability

`openai_compatible` 不能通过 URL 猜测供应商能力。新增显式兼容配置，例如：

```text
OPENAI_COMPATIBILITY_PROFILE=generic | deepseek_v4
```

`deepseek_v4` profile 声明：

- 支持 `thinking.type`；
- 支持 `reasoning_effort`；
- 支持推理 token 明细；
- 思考模式工具轮次需要回放 `reasoning_content`；
- 支持指定单个终止工具。

generic profile 对未知扩展参数保持关闭，不得把 DeepSeek 参数发送给其他兼容服务。

当前 `ChatOpenAI` 标准消息转换不能作为 DeepSeek `reasoning_content` 的可靠载体。因此：

- generic profile 继续复用 `ChatOpenAI`；
- deepseek_v4 profile 使用独立 `DeepSeekV4Transport`，通过原始 Chat Completions JSON 请求/响应保留
  `reasoning_content`、原始工具参数、完成原因和 token 明细；
- transport 可以复用现有 HTTP 客户端或官方 OpenAI 异步客户端，但不能再经过会丢弃第三方响应字段的
  LangChain 消息转换；
- deepseek_v4 只发送官方声明支持的 `thinking`、`reasoning_effort` 和指定函数 `tool_choice`；Reviewer
  只暴露一个终止工具，Runtime 同时拒绝同一响应中的重复终止调用，不依赖未验证的并行工具参数；
- `insufficient_system_resource` 映射为明确、可重试的 Provider 基础设施错误，不能归入 unknown。

### 设计二：DeepSeek 推理状态和用量

#### 临时推理内容

为 Provider 内部模型增加可选 `reasoningContent`：

```python
class ModelMessage(BaseModel):
    ...
    reasoningContent: str | None = None

class ModelTurnResult(BaseModel):
    ...
    reasoningContent: str | None = None
```

约束：

- 只在同一次 `AgentRuntime` 工具循环中回放；
- 不进入 `AgentTurnResult`；
- 不进入 LangGraph 稳定快照；
- 不写入人工工作流日志；
- 不发送给 Core；
- 不向浏览器或用户展示。

这保证 DeepSeek 工具协议正确，同时不持久化模型思维链。

#### 推理用量诊断

新增不参与计费公式的 `ModelUsageDiagnostics`：

```python
class ModelUsageDiagnostics(BaseModel):
    reasoningTokens: int | None
    visibleOutputChars: int
    toolCallCount: int
    invalidToolCallCount: int
    toolArgumentChars: int
    providerUsageKeys: list[str]
```

诊断只描述单次 Provider turn，不是整个 AgentRuntime 工具循环。传递路径固定为：

```text
Provider
  -> ModelTurnResult.diagnostics
  -> ModelRuntime / ModelCallLogRecord.diagnostics
  -> 人工日志模型帧结构头
```

`AgentTurnResult` 仍只聚合四项计费用量，不聚合 diagnostics；每个 turn 依靠自己的 billingRequestId 与
日志、`TokenUsage` 对账。diagnostics 不进入 Core 用量载荷或 LangGraph 稳定快照。

`invalidToolCalls` 的原始参数和解析错误只在当前进程内用于协议分类或最小修复；日志只记录数量、工具名
和错误类别，不记录原始非法参数。任何 invalid tool call 都不得进入 ToolRegistry 执行。

读取顺序：

1. LangChain 标准化 `usage_metadata.output_token_details.reasoning`；
2. 供应商原始 `completion_tokens_details.reasoning_tokens`；
3. 两处都没有时记为 `null`，不能伪造为零。

Core 计费继续只接收并校验现有四项 token：

```text
promptTokens
cachedTokens
completionTokens
totalTokens
```

`reasoningTokens` 是 `completionTokens` 的诊断子项，不能重复加入总量或重复计费。

### 设计三：Reviewer 结构化协议

#### Reviewer 专用提示

Reviewer 模式不再直接复用包含通用讨论职责的完整 Agent system prompt。校验和编辑分别提供专用
Reviewer system prompt，只保留其专业判断标准和以下结构协议：

- 只审核 Core 权威草案；
- 只引用当前可证明证据；
- 可见自然语言仅作为完整诊断记录，不能充当业务评审结论；
- 成功结果必须包含一个合法 `submit_evaluation` 终止事件；
- 信息不足只能标记为证据不足，不能猜测冲突；
- 优化建议和实质问题必须分开。

Provider 对 Reviewer 请求显式选择 `submit_evaluation`。Reviewer 模式只暴露这一个工具；Runtime 再次
拒绝同一响应中的重复终止调用。终止工具成功后继续沿用现有立即结束 AgentRuntime 的语义。这里约束的
是输出协议，不是 token、推理长度或自然语言长度；正常进程路径的完整响应仍进入人工日志，不能静默
截断。合法
evaluation 与可见文本同时出现时，evaluation 可以继续使用，可见文本只记录 `unexpectedVisibleOutput`
诊断，不能导致模型重跑。

#### 结构化问题

新增严格参数模型：

```python
ReviewDimension = Literal[
    "character", "world_rule", "timeline", "causality", "foreshadowing",
    "pacing", "hook", "reader_promise", "language", "other"
]

class ReviewIssueArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    dimension: ReviewDimension
    severity: Literal["blocking", "major", "minor"]
    location: str | None = Field(default=None, min_length=1)
    evidence: str = Field(min_length=1)
    requiredChange: str = Field(min_length=1)
    changeKind: Literal["local", "structural"]
    confidence: float = Field(ge=0, le=1)

class ReviewAdvisoryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    dimension: ReviewDimension
    suggestion: str = Field(min_length=1)
    evidence: str | None = Field(default=None, min_length=1)

class EvaluationArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    issues: list[ReviewIssueArgs]
    advisories: list[ReviewAdvisoryArgs]
    evidenceStatus: Literal["sufficient", "insufficient"]

class StructuredReviewEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schemaVersion: Literal["1.0"]
    issues: list[ReviewIssueArgs]
    advisories: list[ReviewAdvisoryArgs]
    evidenceStatus: Literal["sufficient", "insufficient"]
    verdict: Literal["pass", "revise", "block"] | None
    summary: str = Field(min_length=1)
    requiredChanges: str | None = Field(default=None, min_length=1)
    revisionMode: Literal["rewrite"] | None = None
```

上述模型是扁平结构，不允许递归对象；模型提交或 Runtime 派生的文本只要存在就必须是非空字符串，
`confidence` 必须是有限数值。`StructuredReviewEvaluation.model_validator` 还必须强制：

- `insufficient` 时 `verdict/requiredChanges/revisionMode` 全部为空；
- `sufficient` 时 verdict 必须非空；`pass` 的 `requiredChanges/revisionMode` 为空；
- `revise` 的 `requiredChanges` 非空且 `revisionMode=rewrite`；
- `block` 的 `requiredChanges` 非空且 `revisionMode` 为空。

第一版不通过降低 Provider token 上限或静默截断 Reviewer 结果控制成本。Reviewer prompt 要求同一事实只
形成一个 issue、证据只引用必要位置、不得把完整草案复制进工具参数；Runtime 记录结构化参数字符数和
重复率。为了防止恶意或异常输出耗尽恢复卷，结果还必须满足后文明确的 recovery 字节、条目和容量契约；
超限时完整拒绝并标记复审未完成，不能裁剪、只保存前 N 项或仅因超限重新调用模型。

`StructuredReviewEvaluation` 是 Runtime 派生模型，不直接接受 Provider 未知字段。

Artifact 身份不由模型提交。新增独立的共享 `InternalReviewArtifactResponse`，只供 `/internal/v1/**`
创建/读取/评价响应使用，并在公共 `ReviewArtifactResponse` 的字段基础上增加只读
`artifactPayloadHash`；浏览器公共 GET、公共 OpenAPI 模型和生成 TypeScript 客户端不增加该字段。Core 对
`ReviewArtifact.payloadJson` 解析后的完整 JSON 值计算哈希。哈希算法复用
`writing.idempotency.canonical_json_bytes()`：UTF-8、对象 key 排序、`ensure_ascii=false`、紧凑分隔符、
拒绝 NaN/Infinity，再取小写十六进制 SHA-256。运行时从 Core 权威 `review_context` 构造不可变
`ReviewIdentity`：

```python
class ReviewIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    taskId: str
    runId: str
    jobId: str
    artifactId: str
    artifactKey: str
    artifactRevision: int
    artifactPayloadHash: str
    iteration: int
    reviewer: AgentId
    policyId: str
```

内部 evaluation 请求扩展 `attemptId` 和 `artifactPayloadHash`，但不新增数据库列。持久化时 Core 在同一
事务内锁定当前 Artifact，重新按上述算法计算 payload hash，并核对 taskId、runId、jobId、Artifact ID、
artifactKey、revision、reviewer 和 hash。`attemptId` 同时作为签名请求的 `Idempotency-Key`；Core 继续用
现有 `artifactId + revision + evaluatorAgent` 语义记录去重，相同 attempt 的相同派生 evaluation 返回现有
结果，不同内容返回 `ARTIFACT_EVALUATION_CONFLICT`。迟到、过期、跨 job 或 hash 不一致的
`ReviewAttempt` 以 409 `REVIEW_SOURCE_ERROR` 拒绝，不能重新绑定到新 revision。上述扩展只修改内部
Pydantic/服务契约和请求校验，不修改 PostgreSQL schema。

`summary`、`requiredChanges`、`revisionMode` 和业务 verdict 由 Python 确定性派生：

- `evidenceStatus=insufficient`：生成 `modelStatus=incomplete`、`persistenceStatus=not_applicable` 的
  ReviewAttempt；保留规范化 evaluation 供图状态诊断，写入 `REVIEW_EVIDENCE_INSUFFICIENT`，完全跳过
  Core evaluation 持久化，不形成内容 block；合并阶段把草案送到用户审核并显示“复审证据不足”；
- 存在 `blocking`：保留现有内容 `block` 语义，停止自动返工并交给用户决定；
- 存在 `major` 且没有 blocking：`revise`；
- 只有 `minor`：确定性转为 advisory，不自动触发整章返工；
- 只有 advisory 或没有问题：`pass`；
- 本规格中的自动返工继续明确使用 `revisionMode=rewrite`；`changeKind` 只作为诊断和后续局部 patch
  规格的输入，不能对外宣称已经完成局部修补。

结构化问题完整保存在 `WritingTask.graphStateJson` 的当前评审结果中；提交 Core 的
`ReviewArtifactEvaluation` 继续使用确定性生成的 `summary/requiredChanges/verdict`，不修改数据库结构。
结构化 Evaluation 和 ReviewAttempt 由 Agent Service Pydantic 模型统一定义，控制工具和图状态共同引用；
Core 只接收派生后的现有 evaluation 业务字段以及可信来源校验所需的 `attemptId/artifactPayloadHash`。
历史 evaluation API 暂不提供逐条结构化 issues，这是本规格接受的限制，不能通过把 JSON 偷塞进
summary 或 requiredChanges 绕过。

### 设计四：错误边界

#### 异常分类

新增 typed error 基类 `ModelExecutionError` 和 `ReviewExecutionError`。错误码优先复用当前已经进入测试、
日志和任务错误提取的名称，避免无意义改名：

```text
MODEL_PROVIDER_FAILED
MODEL_AUTHORIZATION_FAILED
MODEL_USAGE_REPORT_FAILED
MODEL_OUTPUT_TRUNCATED / MODEL_OUTPUT_FILTERED
PROVIDER_FINISH_REASON_INVALID / PROVIDER_FINISH_REASON_UNKNOWN
MODEL_TOOL_ARGUMENTS_INVALID / MODEL_TOOL_PROTOCOL_ERROR
MODEL_LOG_WRITE_FAILED
MODEL_PROVIDER_OUTCOME_UNKNOWN
REVIEW_PROTOCOL_ERROR
REVIEW_EVIDENCE_INSUFFICIENT
REVIEW_RESULT_RECOVERY_FAILED
REVIEW_PERSISTENCE_ERROR
REVIEW_SOURCE_ERROR
```

业务代码通过异常对象属性读取 code/category/retryable，禁止继续用异常字符串正则判断。未知异常不映射成
已知可重试错误。

错误对象至少包含：

```text
code
stage
retryable
safeToRetry
requestId（已经取得时）
agentId
executionMode
operationKind
artifactId/revision/iteration（适用时）
usageReported
recoveredFromDurableResult
rawVisibleOutputAvailable
recoveryGapReason
```

不得包含 API key、grantToken、服务私钥或完整推理内容。

#### Provider 成功后的处理

本次崩溃窗口修复只覆盖 Reviewer 主调用和 `protocol_repair`；这些调用只有诊断控制工具，不执行正式业务
写入。正文 primary/reviser 的中间工具轮次需要完整 reasoning 回放和工具副作用恢复，不在本次结果持久化
范围内，不能借 Reviewer 方案宣称所有 Agent turn 都已经跨进程 exactly-once。

Reviewer 调用顺序改为：

```text
Core 稳定保存 ReviewModelReservation
  -> Handler 生成仅本进程有效的 dispatchPermit
  -> Redis CAS 取得 modelRequestId owner lease
  -> Provider
  -> 原子写入加密 ReviewTurnRecoveryRecord
  -> Core 用量上报
  -> 人工日志 observer
  -> Reviewer 协议处理
  -> Core 稳定保存 ReviewAttempt
  -> 删除加密恢复记录和 Redis owner 记录
```

新增稳定模型：

```python
class ReviewModelReservation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schemaVersion: Literal["1.0"]
    attemptId: str
    modelRequestId: str
    identity: ReviewIdentity
    stage: Literal["reviewer", "protocol_repair"]
    ownerEpoch: int = Field(ge=1)
    sourceModelRequestId: str | None = None
    status: Literal["reserved", "result_committed", "outcome_unknown"]
```

`sourceModelRequestId` 在 reviewer 主调用中必须为空，在 `protocol_repair` 中必须指向原始 Reviewer 调用；
validator 必须拒绝其他组合。

`dispatchPermit` 只在 Handler 本进程刚创建 reservation snapshot，并首次收到 Core checkpoint 的
`applied` 凭证时生成，绝不进入 GraphState、Redis 或日志。响应丢失后的 `already_applied`、从 checkpoint
恢复的新进程以及 legacy snapshot 都不能生成 permit。这样即使进程在 checkpoint 后、Provider 前崩溃，
也会保守收敛为 `outcome_unknown`，不会猜测 Provider 是否执行。

Redis 只保存非敏感执行索引：
`modelRequestId/attemptId/ownerEpoch/ownerLease/state/resultDigest/expiresAt`。`ownerEpoch` 在阶段 R 使用 Redis
`INCR` 单调分配并写入 Core reservation，后续所有 Redis 状态、恢复文件和 ReviewAttempt 都绑定该 epoch。
使用 Lua/CAS 完成
`reserved -> provider_inflight -> result_staging -> result_committed -> consumed`，同一 modelRequestId 只能有
一个 owner；
等待者不取得结果也不执行协议处理。Redis 不是业务权威，Redis key 丢失时以 Core reservation 和加密恢复
文件为准，不能因为 key 缺失再次调用 Provider。

每个 Redis 索引 key 在创建和每次 Lua 状态迁移时都必须设置物理 `PEXPIRE`，绝对过期时间不得超过
reservation 创建时间加 `MODEL_RECOVERY_MAX_AGE_SECONDS`；owner 心跳只能缩短剩余窗口内续租，不能延长
绝对上限。`consumed` 立即删除，`outcome_unknown` 和失效 owner 在 Core 状态确认后删除；启动和运行期
janitor 清理无对应 Core reservation 的残留索引。key 丢失、损坏或清理失败都不能触发 Provider 重调。

`provider_inflight` owner lease 由独立心跳续期，心跳间隔小于 lease TTL 的三分之一，并与 QueueClaim
lease 一起受取消/失租监督；它不是 Provider 超时。lease 失效后禁止新 owner 取得同一 modelRequestId 并
调用 Provider，只能把 reservation 条件收敛为 `outcome_unknown`。所有 Redis 写入都必须 CAS 校验
`ownerEpoch + ownerLease + state`；旧 owner 失去 fence 后不能更新状态、observer、ReviewAttempt 或 Core
evaluation，只能按原 billing requestId 尽力补报已经发生的 usage，然后销毁响应。

当前 Redis 使用 `appendonly no`、`save ""` 和 tmpfs，不能承担结果持久化；本规格不顺带把整个队列改成
AOF，也不把 Reviewer 内容写入 Redis 明文。

`ReviewTurnRecoveryRecord` 使用独立持久卷 `/data/model-recovery`。文件名只使用 modelRequestId 的 SHA-256，
写入采用“带 ownerEpoch 的同目录临时文件 -> flush/fsync -> CAS 进入 result_staging -> 原子 rename ->
目录 fsync -> CAS 进入 result_committed”。写入前、rename 前后均校验 fence；任一 CAS 失败都删除本 epoch
临时/目标文件，不能提交结果。恢复时即使 Redis 状态丢失，只要 Core reservation 仍是相同 epoch 的
`reserved`、目标文件存在且身份/摘要校验通过，就复用结果；Core 已是 `outcome_unknown` 时任何迟到文件都
只能清理。目录权限固定为 `0700`、文件为 `0600`，卷只挂载到 Agent Service。

恢复记录使用独立 AES-256-GCM keyring 加密，配置为 `MODEL_RECOVERY_KEYRING_PATH`，不得复用 Ed25519
服务私钥。每次写入或覆盖都必须由密码学安全随机数生成器产生全新的 96-bit nonce；同一 key 下绝不复用
nonce，禁止从 modelRequestId、时间戳或 ownerEpoch 确定性派生。密文 envelope 记录
`schemaVersion/keyId/nonce/ciphertext/digest`。

AAD 使用字段名明确、key 稳定排序的 canonical JSON，不使用字符串拼接；至少包含
`schemaVersion/keyId/modelRequestId/attemptId/ownerEpoch/taskId/runId/jobId/artifactId/revision/reviewer/stage`。
部署轮换密钥时必须保留仍在恢复保留期内的旧 key，缺失 key 形成
`REVIEW_RESULT_RECOVERY_FAILED`，不得降级为 Provider 重调。keyring 由 Agent Service UID 持有，权限为
`0400` 或 `0600`，只挂载到 Agent Service；Core、Web、Redis 和日志采集进程不得挂载。keyring 不进入镜像、
普通备份、stdout 或异常信息。旧 key 只能在最后一份对应密文超过独立最大恢复年龄后撤销，撤销顺序为先
切换写入 key、验证新旧均可读、等待旧密文清理、最后移除旧 key。

加密明文只允许包含：

- schemaVersion、Provider response ID、finish reason；
- 严格 schema 校验后的 `EvaluationArgs`，或不含参数正文的协议错误类别、工具名和计数；
- 四项 usage、billing requestId、usageReported；
- 用量尚未上报时所需的 grantToken 和 grant expiresAt。

不得包含完整 prompt、作品上下文、API key、服务私钥或 `reasoning_content`。Reviewer 的合法终止结果已经
具备形成 Evaluation 所需的全部信息。原始可见输出、原始合法/非法工具参数只允许在当前 owner 进程内用于
observer 或一次 protocol repair，不进入恢复记录；若进程在 protocol repair reservation 提交前丢失这些
内存数据，恢复时形成 `REVIEW_PROTOCOL_ERROR` incomplete 结果，不重调完整 Reviewer。protocol repair 自身
一旦取得 dispatchPermit，仍按相同 reservation/recovery 协议保存其严格结果。

恢复区限制只保护恢复基础设施，不改变 Provider `max_tokens`，也不截断模型响应：

- 单份 recovery canonical plaintext 最大 8 MiB；issues 和 advisories 各最多 128 项；每个结构化文本字段
  最大 64 KiB UTF-8；
- recovery 卷最多 256 MiB、最多 256 个活动文件；阶段 R 在发放 dispatchPermit 前按单份最大值取得容量
  lease，容量不足时 Provider 调用次数必须为零；
- 任一结果超过上述恢复契约、实际磁盘写满或容量 lease 失效时，不截断、不保存半份结果；尽力上报 usage，
  形成 `REVIEW_RESULT_RECOVERY_FAILED`，禁止 Provider 重调。

这些上限远高于当前 Reviewer 正常结构化结果，只是磁盘和恶意输出防护；生产验收必须同时观察命中次数，
若正常结果触发上限，应先分析协议异常并单独调整配置，不能静默丢字段。

恢复规则固定为：

- Core reservation + 合法恢复记录：解密并复用，先按同一 billing requestId 补报 usage，再继续 observer 和
  协议处理，禁止调用 Provider；
- reservation/Redis 已标记 `result_committed`，但文件缺失、超龄、无法解密或摘要不一致：形成
  `REVIEW_RESULT_RECOVERY_FAILED` 的 incomplete ReviewAttempt；不得假定结果可恢复，也不得调用 Provider；
- Core reservation + 无恢复记录，或记录未完成/无法校验：写入
  `MODEL_PROVIDER_OUTCOME_UNKNOWN`，生成 `incomplete + not_applicable` ReviewAttempt，Artifact 带“复审
  结果不确定”警告进入用户审核，禁止自动调用 Provider；
- 明确收到供应商错误响应且供应商确认没有生成完成结果时，才允许按 typed `safeToRetry=true` 创建新的
  modelRequestId，并重新经过聚合 reservation checkpoint；连接重置、超时和进程消失等无法证明结果未生成
  的错误一律是 outcome unknown；
- Provider 返回后恢复文件写入失败：尽力按原 grant 上报实际 usage，然后形成
  `REVIEW_RESULT_RECOVERY_FAILED`，禁止再次调用 Provider；
- 用量上报失败：保留加密 grant 和 usage，在 grant 有效期内按原 requestId 重报；到期后任务显示
  `MODEL_USAGE_REPORT_FAILED`，立即删除含 grantToken 的完整记录并改写为不含正文、参数和凭证的 tombstone，
  用户不补扣该笔、平台承担供应商成本；明确不可重试的永久 report 失败执行相同清理；
- Core 确认 ReviewAttempt checkpoint 后立即删除完整恢复文件；孤儿文件按现有
  `MODEL_RECOVERY_MAX_AGE_SECONDS` 独立上限清理，不能依赖 Queue 终态。janitor 在进程启动时和运行期间周期
  扫描；完整文件默认最大年龄 24 小时，tombstone 才可沿用 `QUEUE_TERMINAL_RETENTION_DAYS`。清理失败告警
  但不能回滚已确认 checkpoint；文件超龄且 Core 尚无 ReviewAttempt 时，后续恢复按 outcome unknown 收敛。

人工日志 observer 失败仍只发出带 requestId 的 `MODEL_LOG_WRITE_FAILED` 脱敏 stdout 诊断，不得改变已恢复
结果、内容 verdict 或重新调用模型。`invalidToolCalls` 和非法 finish reason 在任何工具副作用前失败；一次
`protocol_repair` 仍失败时直接形成复审未完成，不返回完整 Reviewer 流程。

typed error 在 `jobs/writing.py`、`jobs/quality.py` 和 `queue/consumer.py` 统一按
`code/category/retryable` 消费：Core 失败回调、SSE 和任务 `errorMessage` 只暴露错误码及脱敏中文说明，
队列只根据 typed retryable 决定重试，不解析异常字符串。Redis/网络等既有队列基础设施异常仍沿用其独立
分类器，不能强行包装成模型错误。未识别异常保持任务 error，并由 `app.py` 的统一异常出口记录脱敏诊断。

#### 复审执行与 Core 持久化分离

`CoreGraphAgentExecutor.run()` 不再在返回前隐式提交 evaluation。Reviewer 模型调用先形成
`ReviewAttempt`：

```python
ReviewExecutionStage = ModelExecutionStage | Literal[
    "artifact_source_validation", "evaluation_persistence"
]

class ReviewFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: Literal[
        "MODEL_PROVIDER_FAILED",
        "MODEL_PROVIDER_OUTCOME_UNKNOWN",
        "MODEL_AUTHORIZATION_FAILED",
        "MODEL_USAGE_REPORT_FAILED",
        "MODEL_OUTPUT_TRUNCATED",
        "MODEL_OUTPUT_FILTERED",
        "PROVIDER_FINISH_REASON_INVALID",
        "PROVIDER_FINISH_REASON_UNKNOWN",
        "MODEL_TOOL_ARGUMENTS_INVALID",
        "MODEL_TOOL_PROTOCOL_ERROR",
        "REVIEW_PROTOCOL_ERROR",
        "REVIEW_EVIDENCE_INSUFFICIENT",
        "REVIEW_RESULT_RECOVERY_FAILED",
        "REVIEW_PERSISTENCE_ERROR",
        "REVIEW_SOURCE_ERROR",
    ]
    category: Literal[
        "provider", "protocol", "evidence", "recovery", "persistence", "source"
    ]
    retryable: bool
    safeToRetry: bool
    stage: ReviewExecutionStage
    publicMessage: str = Field(min_length=1)

class ReviewAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schemaVersion: Literal["1.0"]
    attemptId: str
    reservationEpoch: int = Field(ge=1)
    identity: ReviewIdentity
    modelStatus: Literal["complete", "incomplete"]
    persistenceStatus: Literal["not_applicable", "pending", "persisted", "failed"]
    evaluation: StructuredReviewEvaluation | None
    failure: ReviewFailure | None
    billingRequestIds: list[str]
```

`ReviewIdentity` 另包含 Runtime 权威 `policyId`。`attemptId` 由 `schemaVersion + ReviewIdentity` 的完整
canonical JSON 做 SHA-256 确定性生成，因此 task、run、job、Artifact、revision、payload hash、iteration、
reviewer 或策略任一变化都会产生新 attempt。`billingRequestIds` 按调用顺序保存 Reviewer 主调用和所有
protocol repair turn 的 requestId；每个 requestId 仍各自对应 TokenUsage 和 turn diagnostics。

模型不变量由 Pydantic `model_validator` 强制：

- `complete` 必须有 `evidenceStatus=sufficient` 的 evaluation；持久化前为 `pending`，成功为 `persisted`，
  明确不可重试失败为 `failed`；
- 证据不足必须为 `incomplete + not_applicable`，保留 `evidenceStatus=insufficient` 的 evaluation，并带
  `REVIEW_EVIDENCE_INSUFFICIENT`；
- Provider 或协议未完成必须为 `incomplete + not_applicable + evaluation=None` 并带对应 failure；
- `persisted` 不允许 failure；`failed` 必须带 persistence/source failure；`billingRequestIds` 必须有序去重。
- `reservationEpoch` 必须等于对应 Core reservation 的 ownerEpoch；不一致结果按 source/recovery failure 拒绝。

固定映射为：只有能够证明 Provider 没有产生完成结果的错误才能同时设置 `safeToRetry=true`；
`outcome_unknown` 和恢复记录失败固定为 `retryable=false`。Provider/授权/用量类错误沿用原 typed error
的 `retryable`；协议修复仍失败为
`protocol + retryable=false`；证据不足为 `evidence + retryable=false`；Core 临时失败不生成 failed attempt，
保持 `pending` 交给队列重试；只有明确不可重试的 Core 失败才形成
`persistence/source + retryable=false`。`publicMessage` 必须是预定义脱敏说明，不能直接复制异常字符串。
`safeToRetry=true` 必须蕴含 `retryable=true`；`retryable=true` 不一定允许再次调用 Provider，例如仅重试
usage report 或 Core persistence 时 `safeToRetry` 仍为 false。

稳定状态只允许保存 `ReviewIdentity`、结构化 evaluation、失败分类和 billingRequestIds，不得包含
reasoning content、完整作品上下文、原始无效工具参数、API key 或 grantToken。

仅在同一次 `graph.ainvoke()` 中增加 LangGraph 节点不能形成可恢复边界。第一版把复审拆成三个外层图阶段；
协议修复需要模型时复用同一 reservation 阶段：

```text
阶段 R：prepareReviewReservations（不调用模型）
  -> 为本 iteration 的全部 Reviewer 生成一个聚合 reservation snapshot
  -> 图以 operationStep=review_model_reservation_pending 返回 WritingJobHandler
  -> WritingJobHandler 保存 Core checkpoint 并生成本进程 dispatchPermit

阶段 A：reviewArtifactWorker（持 permit 并行调用或复用加密结果）
  -> 如需协议修复，先以 review_repair_reservation_pending 再经过一次阶段 R
  -> 图以 operationStep=review_checkpoint_pending 返回 WritingJobHandler
  -> WritingJobHandler 把含 pending ReviewAttempt 的稳定快照保存到 Core

阶段 B：WritingJobHandler 以刚保存的稳定状态再次调用 Operation 图
  -> persistArtifactReviews（只做 Core 幂等提交）
  -> mergeArtifactReviews（只做内容结论合并）
```

同一 iteration 的全部主 Reviewer reservation 必须由一个聚合 snapshot、一个 eventSequence 和一次 Core CAS
保存；不能让并行 `Send` 分支各自抢 checkpoint sequence。只有整个批次 reservation 都校验通过并取得单个
`applied` 凭证，Handler 才为批次内每个 modelRequestId 生成 permit。需要协议修复时，也先收集本批次所有
repair candidate，再以一个新的连续 sequence 保存聚合 repair reservation snapshot。Core 任一时刻只把最新
成功 sequence 的完整 snapshot 作为权威，旧分支结果不能覆盖。

Reviewer 分支把 `ReviewAttempt` 聚合进图状态，不能在分支内部同时完成模型调用和 Core 写入。
`GraphState.reviewAttempts` 使用按 attemptId 去重替换的 reducer，不能继续使用简单 `operator.add`；恢复时
相同 attemptId 更新状态，不重复累加。当前 iteration 已有 pending/persisted attempt 时，恢复路由直接进入
`persistArtifactReviews` 或 `mergeArtifactReviews`，不得重新进入 `reviewArtifactWorker`。

`WritingJobHandler` 增加内部 phased loop，但 reservation、repair reservation 和 review checkpoint 都不是
用户 interrupt。每次阶段返回后必须以相同 sequence 和相同 snapshot 反复重试同一个 `save_checkpoint`，
Core 确认前不能递增 sequence，也不得再次调用图。Core 确认 reservation 后若进程崩溃，新进程没有
dispatchPermit：存在合法恢复记录就复用，不存在就收敛为 outcome unknown，绝不重跑 Reviewer。Core 已确认
ReviewAttempt 后，即使进程崩溃，QueueJob 也从该快照进入阶段 B。自动队列重试必须读取同一 task/run 的
最新 Core checkpoint 并按 `operationStep` 恢复，不要求伪造用户 `resume` 输入；现有用户 `waiting_user`
checkpoint 语义保持不变。

只收到 `already_applied`、checkpoint 响应丢失或恢复时缺少 permit，即使能够推断 Provider 很可能尚未调用，
也必须进入 outcome unknown。这是用户已确认的“避免重复成本优先于自动完成复审”取舍。第一版不提供隐式
受控重发；用户看到未完成警告后可以显式重新发起新的复审任务，新任务必须生成新的 attemptId 和
modelRequestId。

`persistArtifactReviews` 只负责把 `modelStatus=complete` 且 `persistenceStatus=pending` 的 evaluation
以 `attemptId` 作为幂等键提交给 Core。临时 Core 失败时，图返回
`operationStep=review_persistence_retry` 和原 pending attempt；Handler 先保存该快照，再把 typed retryable
错误交给 Queue consumer，后续恢复只重放阶段 B。明确不可重试的错误改为 `persistenceStatus=failed`，
保存对应 `REVIEW_PERSISTENCE_ERROR` 或 `REVIEW_SOURCE_ERROR` 后继续合并。证据不足和 Provider/协议未完成
是 `not_applicable`，不调用 Core。Artifact 最终进入用户审核，并通过现有最终回复/SSE 明确显示“复审未
完成”和错误码，不能伪造内容 block。完整草案仍由 Artifact 接口读取，用户可以基于明确警告决定是否采用
或重新发起复审。

#### 复审合并

合并节点只处理 `modelStatus=complete` 且 `persistenceStatus=persisted` 的内容结论：

- blocking、major、minor 和 advisory 按前述确定性规则派生现有 `block/revise/pass`；
- advisory 不触发自动返工；
- 任一 Reviewer 模型结果 incomplete 或持久化 failed，不参与内容 verdict，草案进入用户审核并携带复审
  未完成警告；
- 取消继续抛出原有 `JobCancelledError`；
- 未分类程序错误使任务进入 error，不允许降级成普通 ReviewResult。

## 可观测性

在现有人工日志 v2 结构头中增加以下字段，不修改正文分帧规则：

```text
policyId
agentId
executionMode
operationKind
stage
turnIndex
artifactId
artifactRevision
artifactIteration
requestedMaxOutputTokens
grantedMaxOutputTokens
reasoningTokens
visibleOutputChars
toolCallCount
invalidToolCallCount
toolArgumentChars
latencyMs
errorCode
usageReported
```

现有 `taskId/runId/requestId/provider/model` 和四项 token 保持不变。日志仍不记录供应商 reasoning 正文。

如果进程在恢复文件提交后、人工日志写入前崩溃，恢复记录只能重建严格 Evaluation 和用量，不能重建已
明确禁止持久化的原始 messages/可见输出。此时写入一个 `recoveredFromDurableResult=true`、
`rawVisibleOutputAvailable=false` 的恢复诊断帧，包含 requestId、Provider response ID、结构化结果摘要哈希和
`recoveryGapReason=process_crash_before_observer`；不得伪造空正文为完整日志，也不得为了补日志重调 Provider。
这是仅限崩溃恢复窗口的显式日志例外，实施时必须同步更新 05 号需求和人工日志格式文档。正常路径仍记录
完整 messages/output。

`docs/requirements/05-auth-billing-and-ops.md` 和 `docs/WORKFLOW_EVENT_LOG_FORMAT.md` 描述当前已实现事实，
设计提交阶段不得提前把本规格写成现状；它们必须在恢复协议实现并通过测试的同一实现提交/发布批次中同步
更新，缺少该同步则实现不能宣称完成。

结构化 stdout 至少记录错误类别、调用身份和阶段，用于人工日志本身不可写时诊断。完整消息和正文不能
复制到 stdout。

## 配置与发布

新增配置：

```text
OPENAI_COMPATIBILITY_PROFILE=deepseek_v4
MODEL_EXECUTION_POLICY_VERSION=review-v1
REVIEW_PROTOCOL_VERSION=review-v1
MODEL_RECOVERY_KEYRING_PATH=/run/inkforge-keys/model-recovery-keyring.json
MODEL_RECOVERY_DIR=/data/model-recovery
MODEL_RECOVERY_MAX_AGE_SECONDS=86400
MODEL_RECOVERY_RECORD_MAX_BYTES=8388608
MODEL_RECOVERY_VOLUME_MAX_BYTES=268435456
MODEL_RECOVERY_MAX_FILES=256
```

发布分四步：

1. **观测发布：** 只采集 reasoning token、无效工具调用和策略候选，不改变模型行为；
2. **策略发布：** 为 Reviewer 和 quality 启用 low reasoning，正文 primary/reviser 保持 high；
3. **恢复发布：** 先启用 recovery keyring、持久卷、reservation 和故障注入测试，但仍使用 legacy Reviewer
   协议；
4. **协议发布：** 启用 Reviewer 结构化问题、错误边界和 outcome-unknown 收敛。

`MODEL_EXECUTION_POLICY_VERSION=legacy` 只回退模型参数行为，不能回退已经写入的图状态协议。
`REVIEW_PROTOCOL_VERSION=legacy` 只允许阻止尚未进入阶段 A 的新任务采用 review-v1；已经写入
`ReviewAttempt schemaVersion=1.0` 的任务必须继续由保留 v1 parser、reducer 和阶段 B 路由的兼容代码恢复。
发布后二进制至少跨一个发布周期同时读取 legacy `reviewResults` 和 v1 `reviewAttempts`，写入格式由任务首次
进入复审时固定；存在未完成 v1 任务时，禁止回滚到完全不认识 v1 graph state 的旧镜像。回退不能删除已经
写入的日志、用量记录或稳定快照。
存在未完成 reservation 或恢复文件时，同样禁止卸载 `model_recovery` 卷、移除对应旧 keyId 或回滚到不认识
`ReviewModelReservation` 的旧镜像。

## 影响范围

- `apps/agent-service/src/inkforge_agents/providers/base.py`：策略、临时 reasoning content 和诊断契约；
- `apps/agent-service/src/inkforge_agents/providers/openai_compatible.py`：DeepSeek profile、推理用量、
  invalid tool call 和 tool choice 映射；
- `apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py`：保留供应商扩展字段的原始 JSON transport；
- `apps/agent-service/src/inkforge_agents/runtime/model_runtime.py`：策略传递、错误分类和日志失败隔离；
- `apps/agent-service/src/inkforge_agents/runtime/review_recovery.py`：Redis owner lease、AES-GCM 恢复记录、
  原子文件提交、keyring 和清理；
- `apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py`：工具轮次 reasoning content 回放和最小协议修复；
- `apps/agent-service/src/inkforge_agents/runtime/agent_runner.py`：按执行场景解析策略；
- `apps/agent-service/src/inkforge_agents/runtime/execution.py`：Reviewer/quality 的终止工具和可见输出约束；
- `apps/agent-service/src/inkforge_agents/tools/control.py`：结构化 Evaluation 参数；
- `apps/agent-service/src/inkforge_agents/jobs/adapters.py`：模型结果与 Core evaluation 持久化拆分；
- `apps/agent-service/src/inkforge_agents/jobs/writing.py`：reservation/review/persistence 多阶段调用、dispatchPermit、
  稳定 checkpoint 和 typed error 映射；
- `apps/agent-service/src/inkforge_agents/jobs/quality.py`：quality 策略和 typed error 映射；
- `apps/agent-service/src/inkforge_agents/queue/consumer.py`、`app.py`：typed retryable、失败回调和脱敏出口；
- `apps/agent-service/src/inkforge_agents/operations/graph.py`：ReviewModelReservation、ReviewAttempt 聚合、
  持久化节点和失败合并；
- `apps/agent-service/src/inkforge_agents/graph/state.py`：reservation 与 ReviewAttempt 稳定状态；
- `apps/agent-service/src/inkforge_agents/observability/`：调用策略、推理 token 和错误阶段日志；
- `apps/agent-service/src/inkforge_agents/config.py`、`infra/compose.yaml`、架构安全测试：兼容 profile、策略版本、
  独立 recovery keyring secret 和 `model_recovery` 持久卷；
- `apps/core-api/src/inkforge_core/reviews/schemas.py`、`internal_router.py`、`repository.py`：独立内部响应、权威
  payload hash、attemptId 请求绑定和事务内来源复核；公共 ReviewArtifact 响应保持不变；
- `packages/service-contracts` 与生成契约：内部 ReviewArtifact hash/evaluation 请求字段；
- Agent 架构文档、03/04/05 号需求与人工日志格式文档：同步当前事实。

## 验收标准

### Provider

- DeepSeek profile 能发送 enabled/disabled 和 low/high/max；
- generic profile 不发送 DeepSeek 扩展参数；
- 使用真实 DeepSeek 请求/响应 fixture 验证 `thinking`、`reasoning_effort`、指定函数 `tool_choice`、
  `reasoning_content`、`completion_tokens_details.reasoning_tokens` 和 `insufficient_system_resource`；
- 验证最终 HTTP JSON 仍使用 DeepSeek 支持的 `max_tokens`，不能只验证上层 SDK 参数名；
- 能从标准化和供应商原始字段读取 reasoning token；
- 两处都缺失时保持 null；
- 思考模式工具轮次正确回放临时 reasoning content；
- reasoning content 不进入日志、Core 载荷或稳定状态；
- invalid tool call 不会被误判成普通无工具响应。

### ModelRuntime

- 相同请求和策略产生稳定逻辑请求身份；
- 策略变化产生不同请求身份；
- Reviewer/quality/primary/reviser 选择正确策略；
- observer 失败不丢弃已完成计费的模型结果；
- Core reservation 未确认时 Provider mock 调用次数必须为零；只有持 runtime-only dispatchPermit 的 owner
  可以调用 Reviewer Provider；
- 相同确定性请求并发进入时只有一个 Redis owner 调用 Provider 和消费业务结果，重复调用者不执行协议
  处理；
- Agent Service 在 Provider 前、请求发送后、恢复文件 rename 前后、usage report 前后被强制终止时，恢复
  分别得到可复用结果或 outcome unknown，同一 modelRequestId 的 Provider 调用次数不得超过一次；
- Redis owner key 丢失但 Core reservation/恢复文件仍在时，不得触发 Provider；
- Redis 索引创建/迁移都会设置不超过 recovery absolute deadline 的 PEXPIRE；consumed、unknown、失效 owner
  和无 Core reservation 索引被有界清理；
- owner 心跳停止、lease 过期和旧 owner 迟到返回时，fencing CAS 必须阻止恢复文件提交、observer 和
  ReviewAttempt；旧 owner 只允许幂等补报 usage；
- AES-GCM nonce 在同 key 下不重复；篡改、canonical AAD 身份不匹配、未知 keyId 和摘要不一致必须显式
  失败，不能使用或重调；
- keyring 文件权限/挂载隔离、当前/旧 key 轮换和撤销顺序通过架构测试；
- usage report pending 时保留加密 grant，grant 到期、取消、永久 report 失败和成功消费都按契约清理；
- grant 到期后的未上报用量不补扣，任务/SSE 明确失败且敏感响应已清理；
- grant 过期后恢复文件不再包含 grantToken；完整文件超过独立最大年龄会被 janitor 删除，tombstone 有界；
- 单文件/条目/字段/卷容量/文件数上限在 Provider 前预留并在写入时复核；超限不截断、不重调；
- 协议修复不重新携带完整作品上下文。

### Reviewer

- Reviewer 成功结果必须包含合法 `submit_evaluation` 终止事件；
- 结构化 Evaluation 的省略字段、非空字段及 pass/revise/block/insufficient 组合由 validator 严格校验；
- 正常路径中合法 evaluation 与可见文本同时出现时保留 evaluation、完整记录可见文本并标记协议诊断；
  observer 前崩溃恢复只写明确的日志缺口帧，两种路径都不重跑模型；
- advisory 不触发自动返工；
- evidence insufficient 不形成内容 block；
- evidence insufficient 形成 `incomplete + not_applicable`，跳过 Core evaluation 并进入带警告的用户审核；
- blocking/major/minor/advisory 能确定性派生现有 block/revise/pass；
- `changeKind` 完整保存，但第一版自动返工始终诚实派生为 rewrite；
- Core 和 Agent 对 payload canonical JSON/hash 的 fixture 一致，Artifact revision/hash/job 过期时拒绝持久化；
- attemptId 覆盖完整 ReviewIdentity/policyId；同 attempt 相同内容幂等、不同内容冲突；
- Reviewer 主调用和 protocol repair 的 billingRequestIds 都能与各自 TokenUsage 对账；
- ReviewAttempt reducer 按 attemptId 去重，恢复从 pending 持久化节点继续；
- 阶段 R reservation 保存前不能调用 Provider；保存后模拟进程重启只能复用加密结果或形成
  outcome unknown，不重跑 Reviewer；
- 两个并行 Reviewer 的主 reservation 使用同一聚合 snapshot/sequence；repair reservation 使用下一聚合
  sequence，分支不能独立覆盖 checkpoint；
- 恢复记录和稳定快照中都不存在 reasoning content、完整 prompt 或作品上下文；
- 非法工具响应的原始参数和可见正文不进入恢复文件；进程丢失后形成 incomplete 协议错误；
- protocol repair 也必须先经过独立 reservation checkpoint，不能作为隐藏的重复模型调用；
- `result_committed` 但文件缺失、损坏、超龄或无法解密时形成 recovery failure，不调用 Provider；
- ReviewAttempt checkpoint 成功后恢复文件立即删除；终态/孤儿清理保持有界；
- Core evaluation 暂时失败只重试持久化，不重跑模型；
- legacy 和 v1 graph state 都能读取，v1 任务不能被错误路由到 legacy reviewer；
- 未分类程序异常使任务失败，不伪装成草案内容问题。

### 回归

- 正文、草案和工具结果不发生静默截断；
- ReviewArtifact 仍必须等待用户决定后才能应用；
- 双 Reviewer 和一致性终检仍然保留；
- Core 计费四项 token 和现有 requestId 幂等语义不变；
- fake Provider 和 generic OpenAI-compatible Provider 保持可用。
- 公共 ReviewArtifact OpenAPI/生成客户端不出现 `artifactPayloadHash`，内部契约包含该字段；运行
  `npm run api:generate` 后 `npm run api:check` 保持通过且无非预期公共接口 diff。

### 生产验收

使用上线后的至少三个正常章节任务做烟雾对比，并持续保留更长周期基线：

- Reviewer 和 quality 的 reasoning token 占比；
- 每个 Reviewer 的完成 token 和持久结果字符数；
- `invalidToolCallCount`；
- `review_incomplete` 和各错误类别；
- `MODEL_PROVIDER_OUTCOME_UNKNOWN`、`REVIEW_RESULT_RECOVERY_FAILED` 及发生阶段；
- reservation 确认后的同 modelRequestId 重复 Provider 调用次数，验收目标为零；
- 加密结果复用次数、outcome unknown 次数和恢复文件清理延迟；
- 每章总积分、返工次数和最终用户采用率。

验收指标用于判断方案效果，不作为运行时硬限制。不得为了达成 token 指标牺牲正文完整性、ReviewArtifact
边界或错误可见性。

## 预期结果

第一阶段主要建立可信观测，不承诺立即降本。启用 Reviewer/quality 低推理策略和结构化协议后，“单章
成本从当前约 784 积分降至 480 至 580 积分”作为待生产数据验证的工程假设，不作为发布门槛。问题账本、
局部 patch 和自适应 Reviewer 不在本规格内；
完成后如仍存在多轮完整返工，再基于新日志单独设计，目标区间可进一步下降到 350 至 480 积分。
