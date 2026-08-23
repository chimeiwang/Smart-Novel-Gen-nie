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
6. 同一 Agent Service 进程内，Provider 已成功返回后，下游日志、用量上报或 Core 持久化失败不得触发
   完整模型重跑；进程在结果进入 Core 稳定快照前崩溃的跨进程 exactly-once 不在第一版承诺内。
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
是输出协议，不是 token、推理长度或自然语言长度；完整响应仍进入人工日志，不能静默截断。合法
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

第一版不新增 Reviewer 专属字符数、issue 数量或 advisory 数量硬限制，也不做截断；序列化结果
仍必须满足现有 Core 签名请求和 `graphStateJson` 的通用载荷约束，超过既有通用约束时显式返回协议错误，
不能静默裁剪。`StructuredReviewEvaluation` 是 Runtime 派生模型，不直接接受 Provider 未知字段。

第一版不以字符数或列表数量截断 Reviewer 结果。Reviewer prompt 要求同一事实只形成一个 issue、证据只
引用必要位置、不得把完整草案复制进工具参数；Runtime 记录结构化参数字符数和重复率，异常膨胀仍完整
保留并作为后续策略证据，不能静默裁剪或仅因文本较长重新调用模型。

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
REVIEW_PROTOCOL_ERROR
REVIEW_EVIDENCE_INSUFFICIENT
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
requestId（已经取得时）
agentId
executionMode
operationKind
artifactId/revision/iteration（适用时）
usageReported
```

不得包含 API key、grantToken、服务私钥或完整推理内容。

#### Provider 成功后的处理

顺序保持：

```text
Provider 成功
  -> Core 用量上报
  -> 人工日志 observer
  -> AgentRuntime 业务处理
```

但错误语义调整为：

- Provider 成功后，先把 `ModelTurnResult`、确定性模型请求 ID、grantRequestId、四项用量和临时
  reasoning content 放入进程内 `PendingModelTurnStore`；
- 用量上报失败：抛出可重试 `MODEL_USAGE_REPORT_FAILED`，缓存项保持 `usageReported=false`；同一进程
  恢复相同确定性请求时必须先重放原 report，成功后消费缓存结果，禁止再次调用 Provider；
- `PendingModelTurnStore` 的响应内容不进入 Core、人工日志或稳定图状态；如果 Agent 进程在 report 成功前
  崩溃，由于本规格禁止持久化 reasoning content，供应商侧严格 exactly-once 无法保证，这是明确保留的
  限制。Core requestId 幂等仍保证用户不会重复扣费；
- 人工日志写入失败：捕获 observer 异常，发出带 requestId 的 `MODEL_LOG_WRITE_FAILED` 结构化 stdout
  诊断并更新进程内日志健康状态；不得丢弃已经完成计费和校验的模型结果、改变当前任务结果或触发模型
  重跑。本规格不因单次日志失败新增全局 readiness 状态机；连续失败的服务级熔断另立运维规格；
- `invalidToolCalls`、非法 finish reason 或非法终止工具：进入协议错误，不得执行工具副作用；
- Reviewer 协议错误进入独立 `protocol_repair` 模式，修复输入只包含原始可见结果、内存中的无效工具
  参数、目标 schema 和 `ReviewIdentity`，不经过普通 AgentRunner，也不重新注入完整作品上下文。修复
  仍不能形成合法终止事件时标记复审未完成，不能返回完整 Reviewer 流程重新推理。

`PendingModelTurnStore` 的生命周期契约如下：

- key 是包含完整消息、工具 schema、模型参数、`policyId` 和 stage 的确定性模型请求 ID；同 key 通过
  每键异步锁和共享 Future 做 single-flight，只有锁的 owner 可以调用 Provider，其他并发调用只等待 owner
  的完成状态，不取得原始模型结果；
- entry 状态固定为 `provider_inflight -> report_pending -> runtime_pending -> committed`，状态迁移必须
  原子；每个逻辑 turn 只有取得 owner lease 的调用可以得到原始结果并进入 AgentRuntime。重复调用者只等待
  owner 完成或由 QueueJob 延后，不取得原始结果、不执行工具副作用；现有 task/job 单活 claim 是第一层
  保证，Store 的 owner lease 是第二层防御；
- 任一 `report_pending` 存在时，ModelRuntime 暂停接受新的 Provider 调用，只处理 pending report 恢复；
  因为 Provider 调用仍受现有全局模型并发门保护，pending entry 上限自然不超过该并发门配置，不另设任意
  token 或正文长度限制；
- 用量上报成功后 entry 进入 `runtime_pending`，直到 AgentRuntime 已形成最终 AgentTurnResult，或 Reviewer
  形成 complete/incomplete ReviewAttempt 才提交 owner lease。提交后立即清除响应和 reasoning content，
  但保留只含 requestId、owner 和 committed 状态的 tombstone 到 task/job 终态；同一进程内相同逻辑请求
  不能再次调用 Provider；
- owner 在提交前发生预期协议问题时继续使用原结果完成 protocol repair；发生未分类业务/工具异常时任务
  直接进入 error，不自动重启完整 Agent。Reviewer 阶段形成 ReviewAttempt 后由 Handler 持有同一稳定状态
  反复保存 checkpoint，不能重新进入模型图；
- entry 最迟使用对应 grant 的 `expiresAt` 作为 report 重试截止时间。到期仍无法上报时记录永久
  `MODEL_USAGE_REPORT_FAILED`，清除响应和 reasoning content，只保留不含正文的失败 tombstone 到本次
  task/job 终态；相同逻辑请求不得在当前任务内自动重新调用 Provider；
- Provider 返回后的取消仍先尝试上报已发生用量；上报成功后再传播取消。授权不匹配等明确不可重试的
  report 失败立即记录 tombstone 并清除敏感结果；
- 用量已上报后，observer 或业务协议失败不阻止消费；调用者取得结果后，Store 在 `finally` 中删除响应、
  reasoning content 和 grantToken 引用，只保留 committed tombstone。进程在 `report_pending` 或
  `runtime_pending` 状态崩溃会丢失 entry，属于前述第一版跨进程限制。

第一版不新增持久化用量 outbox，也不允许过期 grant 迟到扣费。`expiresAt` 前由同一进程按原 requestId 和
原四项 usage 自动重报，Core 依靠现有 TokenUsage requestId 幂等；到期后任务以
`MODEL_USAGE_REPORT_FAILED` 进入 error，SSE/任务详情显示 requestId 和脱敏说明，用户不产生该笔扣费，
供应商成本由平台承担。tombstone 随 task/job 终态清理；第一版没有人工重报已过期 grant 的入口。若生产
数据证明该情况并非罕见，再单独设计不含模型正文的持久化 usage outbox，不能在本规格中顺带扩张。

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
        "REVIEW_PERSISTENCE_ERROR",
        "REVIEW_SOURCE_ERROR",
    ]
    category: Literal["provider", "protocol", "evidence", "persistence", "source"]
    retryable: bool
    stage: ReviewExecutionStage
    publicMessage: str = Field(min_length=1)

class ReviewAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schemaVersion: Literal["1.0"]
    attemptId: str
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

固定映射为：Provider/授权/用量类错误沿用原 typed error 的 `retryable`；协议修复仍失败为
`protocol + retryable=false`；证据不足为 `evidence + retryable=false`；Core 临时失败不生成 failed attempt，
保持 `pending` 交给队列重试；只有明确不可重试的 Core 失败才形成
`persistence/source + retryable=false`。`publicMessage` 必须是预定义脱敏说明，不能直接复制异常字符串。

稳定状态只允许保存 `ReviewIdentity`、结构化 evaluation、失败分类和 billingRequestIds，不得包含
reasoning content、完整作品上下文、原始无效工具参数、API key 或 grantToken。

仅在同一次 `graph.ainvoke()` 中增加 LangGraph 节点不能形成可恢复边界。第一版把复审拆成两个外层图阶段：

```text
阶段 A：reviewArtifactWorker（并行模型调用）
  -> 图以 operationStep=review_checkpoint_pending 返回 WritingJobHandler
  -> WritingJobHandler 把含 pending ReviewAttempt 的稳定快照保存到 Core

阶段 B：WritingJobHandler 以刚保存的稳定状态再次调用 Operation 图
  -> persistArtifactReviews（只做 Core 幂等提交）
  -> mergeArtifactReviews（只做内容结论合并）
```

Reviewer 分支把 `ReviewAttempt` 聚合进图状态，不能在分支内部同时完成模型调用和 Core 写入。
`GraphState.reviewAttempts` 使用按 attemptId 去重替换的 reducer，不能继续使用简单 `operator.add`；恢复时
相同 attemptId 更新状态，不重复累加。当前 iteration 已有 pending/persisted attempt 时，恢复路由直接进入
`persistArtifactReviews` 或 `mergeArtifactReviews`，不得重新进入 `reviewArtifactWorker`。

`WritingJobHandler` 增加内部 phased loop，但 `review_checkpoint_pending` 不是用户 interrupt：阶段 A 返回后
必须以相同 sequence 和相同 snapshot 反复重试同一个 `save_checkpoint`，Core 确认前不能递增 sequence，
也不得再次调用图。若进程在 Core 确认保存前崩溃，可能重跑 Reviewer，这是目标中已声明的跨进程限制；
Core 已确认保存后，即使进程崩溃，QueueJob 也从该快照进入阶段 B。自动队列重试必须读取同一 task/run 的
最新 Core checkpoint 并按 `operationStep` 恢复，不要求伪造用户 `resume` 输入；现有用户 `waiting_user`
checkpoint 语义保持不变。

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

结构化 stdout 至少记录错误类别、调用身份和阶段，用于人工日志本身不可写时诊断。完整消息和正文不能
复制到 stdout。

## 配置与发布

新增配置：

```text
OPENAI_COMPATIBILITY_PROFILE=deepseek_v4
MODEL_EXECUTION_POLICY_VERSION=review-v1
REVIEW_PROTOCOL_VERSION=review-v1
```

发布分三步：

1. **观测发布：** 只采集 reasoning token、无效工具调用和策略候选，不改变模型行为；
2. **策略发布：** 为 Reviewer 和 quality 启用 low reasoning，正文 primary/reviser 保持 high；
3. **协议发布：** 启用 Reviewer 结构化问题和错误边界。

`MODEL_EXECUTION_POLICY_VERSION=legacy` 只回退模型参数行为，不能回退已经写入的图状态协议。
`REVIEW_PROTOCOL_VERSION=legacy` 只允许阻止尚未进入阶段 A 的新任务采用 review-v1；已经写入
`ReviewAttempt schemaVersion=1.0` 的任务必须继续由保留 v1 parser、reducer 和阶段 B 路由的兼容代码恢复。
发布后二进制至少跨一个发布周期同时读取 legacy `reviewResults` 和 v1 `reviewAttempts`，写入格式由任务首次
进入复审时固定；存在未完成 v1 任务时，禁止回滚到完全不认识 v1 graph state 的旧镜像。回退不能删除已经
写入的日志、用量记录或稳定快照。

## 影响范围

- `apps/agent-service/src/inkforge_agents/providers/base.py`：策略、临时 reasoning content 和诊断契约；
- `apps/agent-service/src/inkforge_agents/providers/openai_compatible.py`：DeepSeek profile、推理用量、
  invalid tool call 和 tool choice 映射；
- `apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py`：保留供应商扩展字段的原始 JSON transport；
- `apps/agent-service/src/inkforge_agents/runtime/model_runtime.py`：策略传递、错误分类和日志失败隔离；
- `apps/agent-service/src/inkforge_agents/runtime/pending_turns.py`：进程内 PendingModelTurnStore；
- `apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py`：工具轮次 reasoning content 回放和最小协议修复；
- `apps/agent-service/src/inkforge_agents/runtime/agent_runner.py`：按执行场景解析策略；
- `apps/agent-service/src/inkforge_agents/runtime/execution.py`：Reviewer/quality 的终止工具和可见输出约束；
- `apps/agent-service/src/inkforge_agents/tools/control.py`：结构化 Evaluation 参数；
- `apps/agent-service/src/inkforge_agents/jobs/adapters.py`：模型结果与 Core evaluation 持久化拆分；
- `apps/agent-service/src/inkforge_agents/jobs/writing.py`：复审两阶段调用、稳定 checkpoint 和 typed error 映射；
- `apps/agent-service/src/inkforge_agents/jobs/quality.py`：quality 策略和 typed error 映射；
- `apps/agent-service/src/inkforge_agents/queue/consumer.py`、`app.py`：typed retryable、失败回调和脱敏出口；
- `apps/agent-service/src/inkforge_agents/operations/graph.py`：ReviewAttempt 聚合、持久化节点和失败合并；
- `apps/agent-service/src/inkforge_agents/graph/state.py`：ReviewAttempt 稳定状态；
- `apps/agent-service/src/inkforge_agents/observability/`：调用策略、推理 token 和错误阶段日志；
- `apps/agent-service/src/inkforge_agents/config.py`、`infra/compose.yaml`：兼容 profile 和策略版本配置；
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
- 同一进程内用量上报失败只重放原 report，Provider 调用次数保持一次；
- 相同确定性请求并发进入时只有一个 owner 调用 Provider 和消费业务结果，重复调用者不执行工具副作用；
- report pending 时新 Provider 调用受到背压，grant 到期、取消、永久 report 失败和成功消费都按契约清理；
- committed tombstone 在 task/job 终态前禁止同进程再次调用相同 Provider 请求；
- grant 到期后的未上报用量不补扣，任务/SSE 明确失败且敏感响应已清理；
- Agent 进程在 report 前崩溃的供应商 exactly-once 限制有显式测试和文档；
- 协议修复不重新携带完整作品上下文。

### Reviewer

- Reviewer 成功结果必须包含合法 `submit_evaluation` 终止事件；
- 结构化 Evaluation 的省略字段、非空字段及 pass/revise/block/insufficient 组合由 validator 严格校验；
- 合法 evaluation 与可见文本同时出现时保留 evaluation、完整记录可见文本并标记协议诊断，不重跑模型；
- advisory 不触发自动返工；
- evidence insufficient 不形成内容 block；
- evidence insufficient 形成 `incomplete + not_applicable`，跳过 Core evaluation 并进入带警告的用户审核；
- blocking/major/minor/advisory 能确定性派生现有 block/revise/pass；
- `changeKind` 完整保存，但第一版自动返工始终诚实派生为 rewrite；
- Core 和 Agent 对 payload canonical JSON/hash 的 fixture 一致，Artifact revision/hash/job 过期时拒绝持久化；
- attemptId 覆盖完整 ReviewIdentity/policyId；同 attempt 相同内容幂等、不同内容冲突；
- Reviewer 主调用和 protocol repair 的 billingRequestIds 都能与各自 TokenUsage 对账；
- ReviewAttempt reducer 按 attemptId 去重，恢复从 pending 持久化节点继续；
- 阶段 A 返回后必须先成功保存 Core checkpoint，阶段 B 才能开始；已保存 checkpoint 后模拟进程重启不重跑
  Reviewer；
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
- 模型成功后因下游失败产生的模型重跑次数；
- 分别统计同进程恢复和 checkpoint 前进程崩溃两类重跑；
- 每章总积分、返工次数和最终用户采用率。

验收指标用于判断方案效果，不作为运行时硬限制。不得为了达成 token 指标牺牲正文完整性、ReviewArtifact
边界或错误可见性。

## 预期结果

第一阶段主要建立可信观测，不承诺立即降本。启用 Reviewer/quality 低推理策略和结构化协议后，“单章
成本从当前约 784 积分降至 480 至 580 积分”作为待生产数据验证的工程假设，不作为发布门槛。问题账本、
局部 patch 和自适应 Reviewer 不在本规格内；
完成后如仍存在多轮完整返工，再基于新日志单独设计，目标区间可进一步下降到 350 至 480 积分。
