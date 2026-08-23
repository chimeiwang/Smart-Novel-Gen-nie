# 模型策略、DeepSeek V4 与局部返工规格

**日期：** 2026-08-23
**状态：** 待用户审阅
**范围：** 只解决分场景思考策略、DeepSeek V4 专用传输、Reviewer 小修不再升级为整章重写

## 1. 背景

生产 TokenUsage 已证明，章节写作的高消耗不只来自正文，还来自默认思考、重复复审和完整返工。
当前代码存在三个直接问题：

1. 所有生产模型请求都没有显式思考策略，DeepSeek V4 使用供应商默认思考行为；
2. DeepSeek V4 经过通用 `ChatOpenAI` 适配，无法可靠保留其思考、工具和用量扩展字段；
3. Reviewer 虽能提交 `revisionMode=patch`，图合并时仍会把所有修改结论强制改成 `rewrite`。

DeepSeek V4 官方文档说明：思考模式只真正区分 `high` 和 `max`，兼容输入 `low/medium` 会映射为
`high`。因此本规格不使用虚假的 `low` 档位，而是按业务场景明确启用或关闭 thinking。
用户已明确批准先试运行“创作 high、Reviewer/Quality disabled”的策略；该选择是本规格的固定输入，
不是待实施者再次决定的可选项。

本规格采用的供应商协议依据：

- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
- [DeepSeek V4 Agent 兼容说明](https://api-docs.deepseek.com/quick_start/agent_integrations/oh_my_pi/)

其中 Agent 兼容说明明确要求 thinking 工具轮次回传 `reasoning_content`，assistant 消息必须携带
非 null 的 `content` 字段，并明确 DeepSeek V4 thinking 模式不接受 `tool_choice`。

## 2. 目标

- 创作和完整重写保留 DeepSeek 高强度思考能力；
- Reviewer、质量检查、问答和文风画像关闭 thinking，降低不可见推理消耗；
- 使用 DeepSeek V4 专用原始 JSON transport，完整处理 thinking、`reasoning_content`、工具调用和
  reasoning token 诊断；
- Reviewer 请求局部修改时，确定性修改当前 ReviewArtifact 草案，不再调用 Reviser 重写整章；
- patch 无法安全应用时停止自动返工，绝不静默降级为 rewrite；
- 保持 `proposal -> ReviewArtifact -> 用户确认 -> Core 应用` 正式内容边界；
- 不通过缩小全局模型输出上限实现降本。

## 3. 非目标

- 不实现 Reviewer 问题生命周期；
- 不隔离 Reviser 与 Primary 的读取工具；
- 不重构基础设施错误与内容结论边界；
- 不新增模型自动重试策略；generic ChatOpenAI 保持当前 SDK 重试行为，新的 DeepSeek 原始 HTTP
  transport 不在 Provider 内自动循环请求；
- 不实现跨进程结果恢复、reservation、Redis fencing、AES-GCM 恢复文件或
  `outcome_unknown`；
- 不增加 PostgreSQL 字段、表、索引或迁移；
- 不修改 ReviewArtifact 公共用户决策接口；
- 不调用真实付费模型做测试。

## 4. 总体数据流

```text
业务入口
  -> 显式解析 ModelExecutionPolicy
  -> AgentRunner / 专用任务入口
  -> AgentRuntime 每个模型轮次携带同一 policy
  -> ModelRuntime 继续负责 grant、计费、并发和日志
  -> Provider 只翻译 policy，不猜业务角色
     -> generic: 保留 ChatOpenAI
     -> deepseek_v4: 原始 HTTP JSON transport

Reviewer submit_evaluation
  -> pass/block: 进入现有用户确认边界
  -> revise + rewrite: 调用现有 Reviser 完整返工
  -> revise + patch: 确定性修改 ReviewArtifact 新 revision，不调用模型
```

## 5. 分场景模型策略

### 5.1 契约

新增严格、不可变的内部策略：

```python
class ModelExecutionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    policyId: str
    thinkingMode: Literal["provider_default", "enabled", "disabled"]
    reasoningEffort: Literal["high", "max"] | None = None
    requiredToolName: str | None = None
```

约束：

- `thinkingMode=disabled` 时 `reasoningEffort` 必须为空；
- `thinkingMode=enabled` 时本期只允许 `high`；`max` 仅保留契约能力，不在默认矩阵中使用；
- 生产调用必须显式携带策略；`ModelTurnRequest.policy` 不设置生产默认值；
- `provider_default` 只允许测试、旧快照兼容和未迁移的明确 legacy 路径；
- 策略身份进入模型请求哈希和人工日志结构头，但不进入 Core 四项 TokenUsage 计费载荷。

### 5.2 固定策略矩阵

| 场景 | thinking | effort | required tool |
| --- | --- | --- | --- |
| 长篇初稿、场景改写、整章 Reviser | enabled | high | 使用现有 Runtime 终止工具校验 |
| 长篇用户选区改写 | enabled | high | 使用现有 Runtime 终止工具校验 |
| 长篇 Reviewer | disabled | 无 | `submit_evaluation` |
| 一致性 Quality | disabled | 无 | `submit_quality_report` |
| `answer_question` | disabled | 无 | 无 |
| `review_chapter` 报告 | disabled | 无 | 无 |
| 中短篇大纲、正文、选区替换 | enabled | high | 无 |
| 中短篇 `full_check` | disabled | 无 | 无 |
| 文风画像 | disabled | 无 | 无 |

Reviewer 局部 patch 不调用 Reviser，因此不存在 patch Reviser 的思考策略。

长篇 primary 中，`create_lore`、`revise_lore`、`create_outline`、`revise_outline`、`plan_chapter`、
`write_chapter`、`rewrite_scene`、`rewrite_chapter_selection`、`rewrite_outline_selection` 和
`manage_foreshadowing` 全部属于创作策略；`answer_question` 和 `review_chapter` 属于非思考报告策略。
所有实际 Operation 必须落入且只能落入一个策略组，新增 Operation 时缺少策略映射必须使测试失败。

策略在最了解业务场景的入口创建，沿调用链原样传递。`ModelRuntime` 和 Provider 禁止根据 Agent ID、
URL、工具集合或提示词反推策略。

如果 `requiredToolName` 非空，AgentRunner 必须同时验证该工具已经暴露，并且属于当前执行契约的
终止控制工具；否则在调用 Provider 前失败。

## 6. DeepSeek V4 专用原始 transport

### 6.1 显式 profile

新增配置：

```text
OPENAI_COMPATIBILITY_PROFILE=generic|deepseek_v4
```

- `fake` 继续使用 FakeModelProvider；
- `generic` 继续使用当前 `OpenAICompatibleProvider` 和 ChatOpenAI；
- `deepseek_v4` 使用新的 `DeepSeekV4Provider`；
- 不得根据 `OPENAI_BASE_URL` 猜 profile；
- 生产 Compose 明确设置 `deepseek_v4`；
- `provider_name` 继续使用 Core 计费已接受的 `openai_compatible`，本期不改计费模型契约；
- DeepSeek 官方默认地址改为 `https://api.deepseek.com`，专用 Provider 使用
  `/chat/completions`，不再把 `/v1` 写进默认地址；
- 为兼容现有生产环境，`deepseek_v4` profile 在主机名严格等于 `api.deepseek.com` 且去除尾斜杠
  后的路径等于 `/v1` 时归一为官方根地址；官方根路径 `/` 保持不变；
- 其他主机的自定义代理路径去除尾斜杠后原样保留，再确定性追加 `/chat/completions`，不得用
  `urljoin` 意外丢弃代理前缀；base URL 带 query 或 fragment 时配置校验失败。测试必须覆盖官方根
  地址、`/v1`、`/v1/`、自定义代理前缀和非法 query/fragment，并断言最终请求 URL。

### 6.2 请求规则

`DeepSeekV4Provider` 使用 `httpx.AsyncClient` 直接发送和解析 JSON，禁止经过 LangChain
`AIMessage` 转换。

- 始终发送 `model`、`messages`、最终 grant 后的 `max_tokens`；
- 有工具时发送标准 OpenAI function tools；
- thinking enabled 时发送：

```json
{
  "thinking": {"type": "enabled"},
  "reasoning_effort": "high"
}
```

- thinking enabled 时不发送 `temperature`、`top_p` 或 `tool_choice`；DeepSeek V4 thinking
  模式不接受 `tool_choice`，Runtime 继续负责终止工具校验；
- thinking disabled 时发送 `{"thinking":{"type":"disabled"}}`；Reviewer/Quality 只暴露一个
  终止工具，并发送指定函数 `tool_choice`；
- generic profile 不发送任何 DeepSeek 专属字段。

### 6.3 多轮工具回放

`ModelMessage` 增加仅进程内使用的 `reasoningContent`。DeepSeek thinking 模式返回工具调用后，
AgentRuntime 必须在后续请求的 assistant 消息中同时回放：

- `content` 字段必须存在且不能为 null；供应商本轮没有可见文本时使用空字符串；
- 完整 `reasoning_content`；
- 原工具调用 ID、名称和参数；
- 对应 tool result。

`reasoningContent` 不进入 Agent 最终业务结果、不进入 ReviewArtifact、不进入 Core 用量上报，也不写入
人工日志正文。

### 6.4 响应与诊断

`ModelTurnResult` 增加：

```text
reasoningContent
providerResponseId
diagnostics.reasoningTokens
diagnostics.providerUsageKeys
```

映射：

```text
promptTokens      = usage.prompt_tokens
cachedTokens      = usage.prompt_cache_hit_tokens
completionTokens  = usage.completion_tokens
totalTokens       = usage.total_tokens
reasoningTokens   = usage.completion_tokens_details.reasoning_tokens
```

reasoning token 是 completion token 的子项，只用于诊断，禁止再次加到总量或计费载荷。缺失时记录为空，
不得伪造为零。

工具 `arguments` 必须先保留原始字符串再解析；非法 JSON、非对象参数、缺失工具名必须在执行工具前失败，
不得静默转成空对象。`ModelFinishReason` 增加 `insufficient_system_resource`，AgentRuntime 在接受正文或
执行工具前把它作为供应商未完成响应失败；原始原因同时保留，禁止归一成普通 stop。

## 7. Reviewer 局部 patch

### 7.1 严格 patch 契约

本期只为章节文本 ReviewArtifact 支持：

```python
class TextReplacePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["text_replace"]
    find: str = Field(min_length=1)
    replace: str
```

`EvaluationArgs` 必须满足：

- `pass/block`：不得携带 `revisionMode` 或 patches；
- `revise + patch`：必须携带至少一个、最多二十个严格 patch；
- `revise + rewrite`：不得携带 patches；
- 缺失模式、空 patch、未知字段或未知 patch 类型直接拒绝该 evaluation；
- 其他结构化 Artifact 继续只支持 rewrite。

### 7.2 Reviewer 合并

合并优先级固定为：

```text
block > rewrite > patch > pass
```

- 任一 Reviewer 返回 block，停止自动返工并进入用户确认；
- 任一 Reviewer 要求 rewrite，按现有 Reviser 完整返工；
- 全部 revise 结论都是 patch 时才进入 patch 节点；
- patch 按 Operation 中声明的 Reviewer 顺序确定性合并，不依赖并发返回顺序。

### 7.3 确定性应用

新增 `applyArtifactPatch` 图节点：

1. 从 `CoreArtifactPort` 读取当前权威 ReviewArtifact payload；
2. 只接受章节文本 payload；
3. 所有 `find` 必须在原始正文中恰好命中一次；
4. 所有命中范围必须互不重叠；
5. 从后向前应用 replacement，保持其他正文逐字不变；
6. 调用 Core 内部 Artifact 修订接口时必须携带本轮 Reviewer 所见的 `expectedRevision`；
7. Core 在现有事务和行锁内校验当前 revision 精确等于 `expectedRevision`，不一致返回 409，校验通过后
   才创建同一 artifactKey 的新 revision；该字段只进入内部 Pydantic 契约，不修改数据库；
8. Core 修订成功后才递增 `artifactIteration`，旧 `reviewResults` 保留在快照中但因 iteration 不同不参与
   新一轮合并，新 revision 重新进入 Reviewer；
9. 最终仍只能由用户 approve/revise/discard 后应用到正式章节。

patch 路径不调用 Primary 或 Reviser 模型。

如果任一 patch 找不到、命中多处、范围重叠、目标 Artifact 已变化或 Core 修订冲突：

- 不应用任何 patch；
- 不自动降级为 rewrite；
- 将当前 `ReviewOutcome` 确定性收敛为 `block`，清空 `pendingRevision`，设置
  `artifactStatus=blocked`、`operationStage=局部修订无法安全应用`，随后复用现有
  `markArtifactAwaitingUser` 进入用户确认；
- GraphState 保留固定 `patchFailureCode` 和不含原文的中文 `patchFailureMessage`，供现有任务/SSE
  状态展示与测试读取，不新增数据库字段；
- 保留原 ReviewArtifact，不修改正式正文。

`patchFailureCode` 只允许：`PATCH_TARGET_NOT_FOUND`、`PATCH_TARGET_AMBIGUOUS`、
`PATCH_OVERLAP`、`PATCH_ARTIFACT_UNSUPPORTED`、`ARTIFACT_REVISION_CONFLICT`。错误消息不得包含
章节原文或 replacement。

## 8. 日志与 Token 观测

在现有人工模型日志结构头增加：

```text
policyId
thinkingMode
reasoningEffort
reasoningTokens
providerResponseId
```

日志继续保留完整 messages 和可见 output，但明确排除 `reasoningContent`。TokenUsage 的四项计费用量、
taskId、runId 和 requestId 保持不变；本期不修改数据库 schema。

上线后按 taskId/runId 对比：

- Reviewer/Quality 的 completion token 与 reasoning token；
- 单章模型调用次数；
- patch 命中次数、patch 失败次数、完整 rewrite 次数；
- Reviewer 关闭 thinking 前后的内容接受率和用户返工率。

任何节省比例都必须由生产数据验证，不能在实现完成时提前宣称。

## 9. 影响文件

主要修改：

- `apps/agent-service/src/inkforge_agents/runtime/model_policy.py`
- `apps/agent-service/src/inkforge_agents/runtime/agent_runner.py`
- `apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py`
- `apps/agent-service/src/inkforge_agents/runtime/model_runtime.py`
- `apps/agent-service/src/inkforge_agents/providers/base.py`
- `apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py`
- `apps/agent-service/src/inkforge_agents/providers/openai_compatible.py`
- `apps/agent-service/src/inkforge_agents/providers/selector.py`
- `apps/agent-service/src/inkforge_agents/config.py`
- `apps/agent-service/src/inkforge_agents/tools/control.py`
- `apps/agent-service/src/inkforge_agents/artifacts/patch.py`
- `apps/agent-service/src/inkforge_agents/operations/graph.py`
- `apps/agent-service/src/inkforge_agents/jobs/adapters.py`
- `apps/agent-service/src/inkforge_agents/jobs/quality.py`
- `apps/agent-service/src/inkforge_agents/jobs/short_medium.py`
- `apps/agent-service/src/inkforge_agents/jobs/portrait.py`
- `apps/agent-service/src/inkforge_agents/clients/core.py`
- `apps/core-api/src/inkforge_core/reviews/schemas.py`
- `apps/core-api/src/inkforge_core/reviews/internal_router.py`
- `apps/core-api/src/inkforge_core/reviews/repository.py`
- `apps/core-api/tests/reviews/test_internal_job_identity.py`
- `apps/core-api/tests/reviews/test_artifact_lifecycle.py`
- `infra/compose.yaml`

按实际实现同步检查 `apps/agent-service/AGENTS.md`、03 号和 04 号需求文档；只有实现与测试通过后，
才能把新行为写成当前事实。

## 10. 验收标准

### 模型策略

- 所有生产 `ModelTurnRequest` 都显式携带策略，漏传在测试或类型检查阶段失败；
- 当前全部长篇 Operation、中短篇四种 operation 和文风画像都被策略矩阵覆盖；
- 创作/完整重写发送 thinking enabled + high；
- Reviewer/Quality/问答/画像发送 thinking disabled；
- required tool 同时属于暴露工具和终止控制工具；
- 不修改 `MODEL_MAX_OUTPUT_TOKENS=384000` 的部署能力语义。

### DeepSeek transport

- mock HTTP 测试直接断言最终 JSON，而不是只断言 SDK 参数；
- thinking 工具轮次完整回放 `reasoning_content`，第二轮不会因缺字段产生 400；
- thinking enabled 不发送 `tool_choice`，disabled Reviewer/Quality 发送指定终止工具；
- reasoning token 只进入诊断，不重复计费；
- `insufficient_system_resource` 在业务结果或工具副作用前失败并保留原始完成原因；
- DeepSeek 原始 HTTP transport 遇到错误响应时单次只发送一个 HTTP 请求；
- generic profile 的行为和现有 SDK 默认重试保持不变，不纳入 DeepSeek 单次 HTTP 请求断言；
- 所有测试使用 fixture/mock transport，不发出真实模型请求。

### patch

- patch-only 结论不再被改写为 rewrite；
- patch 路径 Provider mock 调用次数为零；
- 合法 patch 创建新的 ReviewArtifact revision 并重新复审；
- 找不到、多命中、重叠、冲突和非章节文本 patch 都不会触发完整 rewrite；
- patch 内部修订携带 `expectedRevision`，并发 revision 变化返回 409、零应用且不递增
  `artifactIteration`；
- patch 失败进入可读的 block/waiting_user 状态，并带固定脱敏 failure code；
- 用户确认和 Core 正式应用边界保持不变。

### 回归

- Agent Service 相关 pytest、Ruff、Mypy 通过；
- Core ReviewArtifact 相关测试通过；
- Compose 配置检查通过；
- PostgreSQL schema 指纹保持不变；
- 工作树中的既有 `.tmp/` 不进入提交。

## 11. 发布与回退

分三步发布，每一步可独立回退：

1. 先发布 DeepSeek 专用 transport 和日志诊断，策略保持等价；
2. 再启用 Reviewer/Quality thinking disabled；
3. 最后启用 patch 图节点。

回退时：

- profile 可切回 `generic`；
- 策略可切回明确的 `provider_default`，但不能恢复隐式缺省；
- patch 节点可关闭并让 patch 结论直接进入用户确认，禁止恢复“自动升级 rewrite”的旧行为。
