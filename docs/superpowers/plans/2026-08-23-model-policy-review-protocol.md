# 模型执行策略与复审协议优化 Implementation Plan

> **状态：已废弃，不得执行。** 用户已暂停跨进程 Reviewer 恢复方案，原 Task 1 的实现也已由
> `d82e19c` 完整回退。后续只能依据
> [模型策略、DeepSeek V4 与局部返工规格](../../specs/2026-08-23-model-policy-deepseek-patch.md)
> 重新编写短实施计划。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不全局压低模型输出上限、不修改 PostgreSQL schema 的前提下，接入分场景模型策略和 DeepSeek V4 思考协议，把 Reviewer 改成严格结构化结论，并保证 reservation 后的 Reviewer 调用在 Agent Service 重启时只复用结果或明确进入 outcome unknown，绝不自动重复调用 Provider。

**Architecture:** `ModelExecutionPolicy` 由 Agent 执行场景统一解析，generic Provider 保留 ChatOpenAI，DeepSeek V4 使用原始 JSON transport 保留 reasoning/tool/usage 扩展字段。Reviewer 采用 Core reservation → runtime-only permit → fenced recovery → ReviewAttempt checkpoint → Core evaluation 的 R/A/B 阶段；Core 继续独占 PostgreSQL，Agent 只通过内部契约读写 Artifact 和 evaluation。

**Tech Stack:** Python 3.13、FastAPI、Pydantic v2、LangGraph、httpx、Redis Lua、cryptography AES-GCM、PostgreSQL 现有 `graphStateJson`、Ed25519 服务鉴权、pytest、fakeredis、Ruff、Mypy、Docker Compose

---

## 执行前提与硬边界

- 实施基线：分支 `codex/model-policy-review-protocol-design`，规格提交 `9d8996f`。
- 权威规格：[模型执行策略与复审协议优化规格](../../specs/2026-08-23-model-policy-and-review-protocol.md)。
- 执行前重新阅读 `AGENTS.md`、`apps/agent-service/AGENTS.md`、`docs/requirements/03-ai-writing-and-agents.md`、`docs/requirements/04-review-quality-and-workflow.md`。
- 不修改 `apps/core-api/src/inkforge_core/db/models.py`、`apps/core-api/src/inkforge_core/db/schema-contract.json`，不新增 migration，不执行 DDL。
- 本地不连接 PostgreSQL 做结构校验；只运行静态 schema guard 和无真实数据库依赖的测试。需要真实 PostgreSQL 的验收放到服务器 dev 数据库。
- 不调用付费模型做 smoke test；DeepSeek 适配只使用官方响应 fixture 和 mock HTTP transport。
- 不持久化 `reasoning_content`、完整 prompt、作品上下文、原始可见输出或原始非法工具参数。
- Reviewer recovery 只覆盖 `reviewer` 和 `protocol_repair`；primary/reviser 不得继承或宣称该跨进程语义。
- 强制 TDD：每个 Task 先写测试并运行获得目标 RED，再写实现并用同一命令获得 GREEN，最后单独提交。
- 计划示例中的 pytest fixture/helper（例如 `http_mock`、`reservation()`、`attempt()`、`job()`）必须在该 Task
  列出的测试文件中先定义为确定性 fixture/factory；不能依赖测试顺序、真实网络、系统时间或其他 Task 的
  私有 helper。若同名 fixture 已存在，先核对其字段与本计划完全一致再复用。
- `.tmp/` 是既有未跟踪目录，任何 Task 都不得 add、删除或移动它。

## 文件结构锁定

新增文件按职责拆分：

```text
apps/agent-service/src/inkforge_agents/runtime/errors.py
  typed model/review errors，不包含队列或业务实现

apps/agent-service/src/inkforge_agents/runtime/model_policy.py
  ModelExecutionPolicy、stage 和唯一策略解析器

apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py
  DeepSeek 原始 Chat Completions JSON transport

apps/agent-service/src/inkforge_agents/reviewing/contracts.py
  Evaluation、ReviewIdentity、Reservation、ReviewAttempt 严格模型

apps/agent-service/src/inkforge_agents/reviewing/protocol.py
  verdict 派生、Reviewer 专用提示、一次 protocol repair 输入

apps/agent-service/src/inkforge_agents/reviewing/recovery_crypto.py
  keyring、AES-GCM envelope、canonical AAD、原子文件

apps/agent-service/src/inkforge_agents/reviewing/recovery_index.py
  Redis ownerEpoch、lease、fencing、PEXPIRE Lua/CAS

apps/agent-service/src/inkforge_agents/reviewing/recovery_store.py
  容量 lease、文件/index 协调、janitor、恢复结果分类

apps/agent-service/src/inkforge_agents/reviewing/service.py
  Reviewer 主调用/repair 的 prepare、dispatch、recover 业务门面

packages/service-contracts/src/inkforge_contracts/reviews.py
  Core-Agent 内部 Artifact/evaluation 契约
```

不要把上述职责重新塞进 `operations/graph.py`、`model_runtime.py` 或 `jobs/adapters.py` 的私有 helper。

### Task 1：建立 typed error 与模型执行策略

**Files:**

- Create: `apps/agent-service/src/inkforge_agents/runtime/errors.py`
- Create: `apps/agent-service/src/inkforge_agents/runtime/model_policy.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/execution.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/agent_runner.py`
- Create: `apps/agent-service/tests/runtime/test_model_policy.py`
- Create: `apps/agent-service/tests/runtime/test_execution_errors.py`
- Modify: `apps/agent-service/tests/runtime/test_agent_runner.py`

- [ ] **Step 1: 写策略矩阵和错误不变量的失败测试**

```python
def test_reviewer_uses_low_reasoning_and_required_tool() -> None:
    policy = resolve_model_execution_policy(
        agent_id="编辑",
        execution_mode="reviewer",
        operation_kind="write_chapter",
        stage="reviewer",
        version="review-v1",
    )
    assert policy.thinkingMode == "enabled"
    assert policy.reasoningEffort == "low"
    assert policy.requiredToolName == "submit_evaluation"


def test_safe_to_retry_implies_retryable() -> None:
    with pytest.raises(ValueError, match="safeToRetry"):
        ModelExecutionError(
            code="MODEL_PROVIDER_FAILED",
            category="provider",
            stage="reviewer",
            retryable=False,
            safeToRetry=True,
            publicMessage="模型供应商调用失败",
        )
```

- [ ] **Step 2: 运行测试确认 RED**

```powershell
uv run pytest apps/agent-service/tests/runtime/test_model_policy.py apps/agent-service/tests/runtime/test_execution_errors.py apps/agent-service/tests/runtime/test_agent_runner.py -q
```

Expected: FAIL，因为 `model_policy.py`、`errors.py` 和 `AgentRunRequest.stage` 尚不存在。

- [ ] **Step 3: 新增严格策略和错误模型**

```python
ModelExecutionStage = Literal[
    "primary", "reviewer", "reviser", "quality", "protocol_repair"
]


class ModelExecutionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    policyId: str = Field(min_length=1)
    thinkingMode: Literal["provider_default", "enabled", "disabled"]
    reasoningEffort: Literal["low", "high", "max"] | None = None
    requiredToolName: str | None = Field(default=None, min_length=1)
    visibleOutputDisposition: Literal["business", "diagnostic_only"]


class ModelExecutionError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        category: str,
        stage: ModelExecutionStage,
        retryable: bool,
        safeToRetry: bool,
        publicMessage: str,
        requestId: str | None = None,
        usageReported: bool = False,
    ) -> None:
        if safeToRetry and not retryable:
            raise ValueError("safeToRetry=true 必须同时 retryable=true")
        super().__init__(publicMessage)
        self.code = code
        self.category = category
        self.stage = stage
        self.retryable = retryable
        self.safeToRetry = safeToRetry
        self.publicMessage = publicMessage
        self.requestId = requestId
        self.usageReported = usageReported


class ReviewExecutionError(ModelExecutionError):
    pass


class ProviderTransportError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, safe_to_retry: bool) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.safe_to_retry = safe_to_retry


class UnknownJobExecutionError(RuntimeError):
    pass
```

- [ ] **Step 4: 实现唯一策略解析器并把 stage 显式传入 AgentRunRequest**

策略必须固定为：primary/reviser=`enabled+high`，reviewer/quality=`enabled+low`，protocol_repair=`disabled+None`，legacy=`provider_default`。`AgentRunRequest` validator 必须拒绝 mode/stage 不一致；Provider 内不得猜测角色。

```python
_REVIEW_V1_POLICIES: dict[ModelExecutionStage, ModelExecutionPolicy] = {
    "primary": ModelExecutionPolicy(policyId="review-v1:primary", thinkingMode="enabled",
        reasoningEffort="high", visibleOutputDisposition="business"),
    "reviser": ModelExecutionPolicy(policyId="review-v1:reviser", thinkingMode="enabled",
        reasoningEffort="high", visibleOutputDisposition="business"),
    "reviewer": ModelExecutionPolicy(policyId="review-v1:reviewer", thinkingMode="enabled",
        reasoningEffort="low", requiredToolName="submit_evaluation",
        visibleOutputDisposition="diagnostic_only"),
    "quality": ModelExecutionPolicy(policyId="review-v1:quality", thinkingMode="enabled",
        reasoningEffort="low", requiredToolName="submit_quality_report",
        visibleOutputDisposition="diagnostic_only"),
    "protocol_repair": ModelExecutionPolicy(policyId="review-v1:protocol-repair",
        thinkingMode="disabled", reasoningEffort=None,
        requiredToolName="submit_evaluation", visibleOutputDisposition="diagnostic_only"),
}
```

- [ ] **Step 5: 运行同一测试确认 GREEN**

```powershell
uv run pytest apps/agent-service/tests/runtime/test_model_policy.py apps/agent-service/tests/runtime/test_execution_errors.py apps/agent-service/tests/runtime/test_agent_runner.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add apps/agent-service/src/inkforge_agents/runtime/errors.py apps/agent-service/src/inkforge_agents/runtime/model_policy.py apps/agent-service/src/inkforge_agents/runtime/execution.py apps/agent-service/src/inkforge_agents/runtime/agent_runner.py apps/agent-service/tests/runtime/test_model_policy.py apps/agent-service/tests/runtime/test_execution_errors.py apps/agent-service/tests/runtime/test_agent_runner.py
git commit -m "功能：增加分场景模型执行策略"
```

### Task 2：扩展 Provider 契约并实现 DeepSeek V4 原始 transport

**Files:**

- Modify: `apps/agent-service/src/inkforge_agents/providers/base.py`
- Create: `apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py`
- Modify: `apps/agent-service/src/inkforge_agents/providers/openai_compatible.py`
- Modify: `apps/agent-service/src/inkforge_agents/providers/selector.py`
- Modify: `apps/agent-service/src/inkforge_agents/config.py`
- Create: `apps/agent-service/tests/providers/fixtures/deepseek_v4/tool_call.json`
- Create: `apps/agent-service/tests/providers/fixtures/deepseek_v4/invalid_tool_call.json`
- Create: `apps/agent-service/tests/providers/fixtures/deepseek_v4/insufficient_resource.json`
- Create: `apps/agent-service/tests/providers/test_deepseek_v4.py`
- Modify: `apps/agent-service/tests/providers/test_openai_compatible.py`
- Modify: `apps/agent-service/tests/providers/test_provider_config.py`
- Modify: `apps/agent-service/tests/providers/test_fake_provider.py`

- [ ] **Step 1: 写 DeepSeek 最终 HTTP JSON 和响应解析失败测试**

```python
async def test_deepseek_sends_reasoning_and_required_tool(http_mock) -> None:
    provider = DeepSeekV4Provider(settings(), http_client=http_mock)
    result = await provider.complete_turn(reviewer_request())
    body = http_mock.requests[0].json()
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "low"
    assert body["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_evaluation"},
    }
    assert body["max_tokens"] == 384000
    assert result.diagnostics.reasoningTokens == 1200
```

测试还要覆盖：assistant 工具轮次回放 `reasoning_content`；非法 JSON arguments 进入 `invalidToolCalls`；`insufficient_system_resource` 映射为明确 Provider 错误；generic profile 不发送 DeepSeek 扩展字段。

- [ ] **Step 2: 运行 Provider 测试确认 RED**

```powershell
uv run pytest apps/agent-service/tests/providers/test_deepseek_v4.py apps/agent-service/tests/providers/test_openai_compatible.py apps/agent-service/tests/providers/test_provider_config.py apps/agent-service/tests/providers/test_fake_provider.py -q
```

Expected: FAIL，因为 DeepSeek transport 和 reasoning/diagnostics 契约尚不存在。

- [ ] **Step 3: 扩展 Provider 基础模型**

```python
class ModelUsageDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    reasoningTokens: int | None = Field(default=None, ge=0)
    visibleOutputChars: int = Field(ge=0)
    toolCallCount: int = Field(ge=0)
    invalidToolCallCount: int = Field(ge=0)
    toolArgumentChars: int = Field(ge=0)
    providerUsageKeys: list[str] = Field(default_factory=list)


class InvalidModelToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: str
    rawArguments: str
    errorCode: Literal["json_invalid", "arguments_not_object", "name_missing"]
```

`ModelMessage` 增加仅内存 `reasoningContent`；`ModelTurnRequest` 增加不可变 `policy`；`ModelTurnResult` 增加 `reasoningContent`、`invalidToolCalls`、`diagnostics` 和 `providerResponseId`。这些字段不得进入 Core 用量载荷。

- [ ] **Step 4: 实现 DeepSeekV4Provider 原始 JSON transport**

使用 `httpx.AsyncClient.post("/chat/completions", json=payload)`；构造标准 messages/tools，并只在 policy 要求时发送 `thinking`、`reasoning_effort`、指定函数 `tool_choice`。直接解析响应 JSON，禁止再经过 LangChain `AIMessage` 转换；HTTP fixture 必须验证供应商字段和 `max_tokens` 的最终线格式。

```python
payload: dict[str, JsonValue] = {
    "model": self.model_name,
    "messages": serialize_deepseek_messages(request.messages),
    "max_tokens": request.maxOutputTokens,
}
if request.tools:
    payload["tools"] = serialize_openai_tools(request.tools)
if request.policy.thinkingMode != "provider_default":
    payload["thinking"] = {"type": request.policy.thinkingMode}
if request.policy.reasoningEffort is not None:
    payload["reasoning_effort"] = request.policy.reasoningEffort
if request.policy.requiredToolName is not None:
    payload["tool_choice"] = {
        "type": "function",
        "function": {"name": request.policy.requiredToolName},
    }
```

- [ ] **Step 5: 保留 generic ChatOpenAI 路径并按 profile 选择**

`OPENAI_COMPATIBILITY_PROFILE=generic|deepseek_v4` 必须显式配置；URL 不能用于推断。fake provider 返回合法空 diagnostics，保证测试和本地开发不漂移。

```python
def create_model_provider(settings: Settings) -> ModelProvider:
    if settings.model_provider == "fake":
        return FakeModelProvider()
    if settings.openai_compatibility_profile == "deepseek_v4":
        return DeepSeekV4Provider(settings)
    return OpenAICompatibleProvider(settings)
```

- [ ] **Step 6: 运行同一测试确认 GREEN**

```powershell
uv run pytest apps/agent-service/tests/providers/test_deepseek_v4.py apps/agent-service/tests/providers/test_openai_compatible.py apps/agent-service/tests/providers/test_provider_config.py apps/agent-service/tests/providers/test_fake_provider.py -q
```

Expected: PASS，且没有真实网络请求。

- [ ] **Step 7: 提交**

```powershell
git add apps/agent-service/src/inkforge_agents/providers/base.py apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py apps/agent-service/src/inkforge_agents/providers/openai_compatible.py apps/agent-service/src/inkforge_agents/providers/selector.py apps/agent-service/src/inkforge_agents/config.py apps/agent-service/tests/providers
git commit -m "功能：适配 DeepSeek V4 思考与工具协议"
```

### Task 3：让 ModelRuntime 传递策略、诊断和 typed error

**Files:**

- Modify: `apps/agent-service/src/inkforge_agents/runtime/model_runtime.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/agent_runner.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/turn_result.py`
- Modify: `apps/agent-service/src/inkforge_agents/observability/model_observer.py`
- Modify: `apps/agent-service/src/inkforge_agents/observability/human_workflow_log.py`
- Modify: `apps/agent-service/tests/runtime/test_billing_runtime.py`
- Modify: `apps/agent-service/tests/runtime/test_agent_runtime.py`
- Modify: `apps/agent-service/tests/runtime/test_agent_runner.py`
- Modify: `apps/agent-service/tests/observability/test_model_log_bridge.py`

- [ ] **Step 1: 写策略身份、reasoning 回放和 observer 隔离失败测试**

```python
async def test_observer_failure_keeps_reported_result() -> None:
    runtime = runtime_with(observer=FailingObserver())
    result = await runtime.run_turn(request(), context=context())
    assert result.content == "完成"
    assert billing.report_calls == 1
    assert provider.calls == 1


def test_reasoning_tokens_are_not_added_twice() -> None:
    usage = ModelUsage(
        promptTokens=100,
        cachedTokens=20,
        completionTokens=80,
        totalTokens=180,
    )
    diagnostics = ModelUsageDiagnostics(reasoningTokens=60, visibleOutputChars=3,
        toolCallCount=1, invalidToolCallCount=0, toolArgumentChars=10,
        providerUsageKeys=[])
    assert usage.totalTokens == 180
    assert diagnostics.reasoningTokens == 60
```

- [ ] **Step 2: 运行测试确认 RED**

```powershell
uv run pytest apps/agent-service/tests/runtime/test_billing_runtime.py apps/agent-service/tests/runtime/test_agent_runtime.py apps/agent-service/tests/runtime/test_agent_runner.py apps/agent-service/tests/observability/test_model_log_bridge.py -q
```

Expected: FAIL，因为 context/policy/diagnostics 传递和 observer 失败隔离尚未实现。

- [ ] **Step 3: 扩展 ModelCallContext 和日志记录**

```python
class ModelCallContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    userId: str
    novelId: str
    taskId: str
    runId: str
    jobId: str
    agentId: str
    executionMode: AgentExecutionMode
    operationKind: CreativeOperationKind | None
    stage: ModelExecutionStage
    policyId: str
    artifactId: str | None = None
    artifactRevision: int | None = None
    artifactIteration: int | None = None
    turnIndex: int = Field(ge=0)
```

逻辑 request ID 必须使用字段名明确的 canonical JSON SHA-256，包含 context、messages、tools、policy 和 maxOutputTokens；不再使用字符串拼接后截 32 位的旧实现。

- [ ] **Step 4: 把错误点改为 typed error**

授权、Provider、用量上报、finish reason、tool arguments 和协议错误必须构造 `ModelExecutionError`；observer 异常只写脱敏 `MODEL_LOG_WRITE_FAILED` stdout，不抛弃已经 report 的结果。未知异常保持未知，不能伪装成可重试 Provider 错误。

```python
try:
    result = await self._provider.complete_turn(provider_request)
except ProviderTransportError as exc:
    raise ModelExecutionError(
        code="MODEL_PROVIDER_FAILED",
        category="provider",
        stage=context.stage,
        retryable=exc.retryable,
        safeToRetry=exc.safe_to_retry,
        publicMessage="模型供应商调用失败",
        requestId=request_id,
    ) from exc
```

- [ ] **Step 5: 在 AgentRuntime 原样回放 reasoningContent**

每次 assistant tool call 消息都同时追加 `content/toolCalls/reasoningContent`；下一轮 DeepSeek 请求原样序列化。`AgentTurnResult` 不包含 reasoning；人工日志结构头包含 diagnostics，不包含 reasoning 正文。

```python
conversation.append(
    ModelMessage(
        role="assistant",
        content=turn.content,
        toolCalls=turn.toolCalls,
        reasoningContent=turn.reasoningContent,
    )
)
```

- [ ] **Step 6: 运行同一测试确认 GREEN**

```powershell
uv run pytest apps/agent-service/tests/runtime/test_billing_runtime.py apps/agent-service/tests/runtime/test_agent_runtime.py apps/agent-service/tests/runtime/test_agent_runner.py apps/agent-service/tests/observability/test_model_log_bridge.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add apps/agent-service/src/inkforge_agents/runtime apps/agent-service/src/inkforge_agents/observability apps/agent-service/tests/runtime apps/agent-service/tests/observability/test_model_log_bridge.py
git commit -m "重构：统一模型调用诊断与错误边界"
```

### Task 4：建立 Reviewer 严格结构协议和确定性 verdict

**Files:**

- Create: `apps/agent-service/src/inkforge_agents/reviewing/__init__.py`
- Create: `apps/agent-service/src/inkforge_agents/reviewing/contracts.py`
- Create: `apps/agent-service/src/inkforge_agents/reviewing/protocol.py`
- Modify: `apps/agent-service/src/inkforge_agents/tools/control.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/execution.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/messages.py`
- Create: `apps/agent-service/tests/reviewing/test_contracts.py`
- Create: `apps/agent-service/tests/reviewing/test_protocol.py`
- Modify: `apps/agent-service/tests/tools/test_arguments.py`
- Modify: `apps/agent-service/tests/runtime/test_messages.py`
- Modify: `apps/agent-service/tests/golden/test_prompts.py`

- [ ] **Step 1: 写结构校验和 verdict 派生失败测试**

```python
def test_minor_issue_becomes_advisory_pass() -> None:
    evaluation = normalize_evaluation(
        EvaluationArgs(
            issues=[issue(severity="minor")],
            advisories=[],
            evidenceStatus="sufficient",
        )
    )
    assert evaluation.verdict == "pass"
    assert evaluation.revisionMode is None
    assert len(evaluation.advisories) == 1


def test_insufficient_evidence_has_no_business_verdict() -> None:
    evaluation = normalize_evaluation(
        EvaluationArgs(issues=[], advisories=[], evidenceStatus="insufficient")
    )
    assert evaluation.verdict is None
    assert evaluation.requiredChanges is None
```

测试必须覆盖 blocking→block、major→revise/rewrite、minor→advisory、pass、非空 UTF-8 字段、128 项/64 KiB recovery 契约、extra forbid 和 confidence 有限值。

- [ ] **Step 2: 运行测试确认 RED**

```powershell
uv run pytest apps/agent-service/tests/reviewing/test_contracts.py apps/agent-service/tests/reviewing/test_protocol.py apps/agent-service/tests/tools/test_arguments.py apps/agent-service/tests/runtime/test_messages.py apps/agent-service/tests/golden/test_prompts.py -q
```

Expected: FAIL，因为 reviewing package 和新 EvaluationArgs 尚不存在。

- [ ] **Step 3: 定义严格模型**

```python
class EvaluationArgs(StrictReviewModel):
    issues: list[ReviewIssueArgs] = Field(max_length=128)
    advisories: list[ReviewAdvisoryArgs] = Field(max_length=128)
    evidenceStatus: Literal["sufficient", "insufficient"]


class StructuredReviewEvaluation(StrictReviewModel):
    schemaVersion: Literal["1.0"] = "1.0"
    issues: list[ReviewIssueArgs]
    advisories: list[ReviewAdvisoryArgs]
    evidenceStatus: Literal["sufficient", "insufficient"]
    verdict: Literal["pass", "revise", "block"] | None
    summary: str
    requiredChanges: str | None = None
    revisionMode: Literal["rewrite"] | None = None
```

文本 validator 使用 UTF-8 字节数校验 64 KiB，不使用字符数代替；超限完整拒绝，不截断、不重调。

- [ ] **Step 4: 替换 submit_evaluation 工具参数和 Reviewer prompt**

模型不再提交 artifactId/revision/verdict/summary；身份由 Runtime 注入，verdict/summary/requiredChanges/revisionMode 由 Python 派生。Reviewer 使用校验/编辑专用 system prompt，成功只允许一次 `submit_evaluation`。

```python
def reviewer_system_prompt(agent_id: AgentId) -> str:
    standard = "一致性、因果、时间线和设定证据" if agent_id == "校验" else "节奏、钩子、读者承诺和语言效果"
    return (
        f"你是{agent_id}复审员，只按{standard}审核 Core 权威草案。"
        "只提交当前证据能够证明的问题；优化建议放 advisories。"
        "成功时必须且只能调用一次 submit_evaluation，不要在正文中输出业务 verdict。"
    )
```

- [ ] **Step 5: 运行同一测试确认 GREEN**

```powershell
uv run pytest apps/agent-service/tests/reviewing/test_contracts.py apps/agent-service/tests/reviewing/test_protocol.py apps/agent-service/tests/tools/test_arguments.py apps/agent-service/tests/runtime/test_messages.py apps/agent-service/tests/golden/test_prompts.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add apps/agent-service/src/inkforge_agents/reviewing apps/agent-service/src/inkforge_agents/tools/control.py apps/agent-service/src/inkforge_agents/runtime/execution.py apps/agent-service/src/inkforge_agents/runtime/messages.py apps/agent-service/tests/reviewing apps/agent-service/tests/tools/test_arguments.py apps/agent-service/tests/runtime/test_messages.py apps/agent-service/tests/golden/test_prompts.py
git commit -m "功能：建立 Reviewer 结构化评审协议"
```

### Task 5：增加 Core-Agent 内部 Artifact hash 与 evaluation 契约

**Files:**

- Create: `packages/service-contracts/src/inkforge_contracts/reviews.py`
- Modify: `packages/service-contracts/src/inkforge_contracts/__init__.py`
- Create: `packages/service-contracts/tests/test_review_contracts.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/internal_router.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/repository.py`
- Modify: `apps/core-api/src/inkforge_core/writing/context.py`
- Modify: `apps/agent-service/src/inkforge_agents/clients/core.py`
- Modify: `apps/agent-service/src/inkforge_agents/jobs/adapters.py`
- Create: `apps/core-api/tests/reviews/test_evaluation_identity.py`
- Modify: `apps/core-api/tests/reviews/test_internal_job_identity.py`
- Modify: `apps/core-api/tests/reviews/test_artifact_lifecycle.py`
- Modify: `apps/agent-service/tests/jobs/test_adapters.py`
- Modify: `apps/agent-service/tests/integration/test_core_callbacks.py`

- [ ] **Step 1: 写公共/内部响应隔离和过期来源拒绝测试**

```python
def test_internal_artifact_contains_hash_but_public_schema_does_not() -> None:
    internal_properties = InternalReviewArtifactResponse.model_json_schema()["properties"]
    public_properties = ReviewArtifactResponse.model_json_schema()["properties"]
    assert "artifactPayloadHash" in internal_properties
    assert "artifactPayloadHash" not in public_properties


async def test_evaluation_rejects_stale_payload_hash(repository) -> None:
    with pytest.raises(ApiError) as error:
        await repository.submit_evaluation("user-1", "artifact-1", stale_request())
    assert error.value.code == "REVIEW_SOURCE_ERROR"
```

- [ ] **Step 2: 运行契约/Core/Agent 测试确认 RED**

```powershell
uv run pytest packages/service-contracts/tests/test_review_contracts.py apps/core-api/tests/reviews/test_evaluation_identity.py apps/core-api/tests/reviews/test_internal_job_identity.py apps/core-api/tests/reviews/test_artifact_lifecycle.py apps/agent-service/tests/jobs/test_adapters.py apps/agent-service/tests/integration/test_core_callbacks.py -q
```

Expected: FAIL，因为共享 review 契约、payload hash 和 attempt 字段尚不存在。

- [ ] **Step 3: 新增共享内部契约**

```python
class InternalArtifactEvaluationResponse(ReviewContract):
    id: str
    artifactId: str
    revision: int = Field(ge=1)
    evaluatorAgent: CoreAgentId
    verdict: Literal["pass", "revise", "block"]
    summary: str
    requiredChanges: str | None
    createdAt: AwareDatetime


class InternalReviewArtifactResponse(ReviewContract):
    id: str
    novelId: str
    chapterId: str | None
    taskId: str | None
    workflowRunId: str | None
    artifactKey: str | None
    kind: str
    status: Literal["draft", "under_review", "awaiting_user", "applying", "applied"]
    title: str | None
    summary: str | None
    payload: dict[str, JsonValue]
    diff: JsonValue | None
    createdByAgent: str | None
    updatedByAgent: str | None
    reviewerAgent: str | None
    revision: int = Field(ge=1)
    evaluations: list[InternalArtifactEvaluationResponse] = Field(default_factory=list)
    sourceBindings: list[SourceBinding] | None
    sourceBindingStatus: Literal["verified", "legacy_missing", "not_yet_supported"]
    artifactPayloadHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    createdAt: AwareDatetime
    updatedAt: AwareDatetime


class SubmitArtifactEvaluationRequest(ReviewContract):
    attemptId: str = Field(min_length=64, max_length=64)
    artifactPayloadHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reservationEpoch: int = Field(ge=1)
    runId: str
    taskId: str
    novelId: str
    jobId: str
    artifactKey: str
    revision: int = Field(ge=1)
    evaluatorAgent: CoreAgentId
    verdict: Literal["pass", "revise", "block"]
    summary: str = Field(min_length=1)
    requiredChanges: str | None = None
```

`InternalReviewArtifactResponse` 复用公共业务字段并单独增加 `artifactPayloadHash`；公共 `ReviewArtifactResponse` 保持不变。

- [ ] **Step 4: Core 使用 canonical payload hash 并在事务内复核**

复用 `writing.idempotency.canonical_json_bytes()` 对解析后的完整 `payloadJson` 做 SHA-256。`submit_evaluation()` 在同一事务锁定 task/artifact，验证 run/job/current command、artifactKey/revision/hash/evaluator/reservationEpoch；读取 `WritingTask.graphStateJson` 核对 attempt/epoch。相同 evaluation 返回幂等成功，不同内容返回 `ARTIFACT_EVALUATION_CONFLICT`。

```python
def artifact_payload_hash(payload_json: str) -> str:
    payload = json.loads(payload_json)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


if artifact_payload_hash(artifact.payloadJson) != request.artifactPayloadHash:
    raise ApiError(
        status_code=409,
        code="REVIEW_SOURCE_ERROR",
        message="复审结论对应的草案内容已变化",
    )
```

- [ ] **Step 5: Agent 只信任内部 hash 并用 attemptId 作 Idempotency-Key**

`CoreArtifactPort` 保存 Core 返回的 hash；hydrate/context 路径也必须带回。`submit_evaluation()` body 绑定 attempt/hash/epoch，header idempotency key 使用 attemptId，不再用 runId+payload 临时摘要。

```python
await self._core.submit_evaluation(
    record.resource,
    artifact_id,
    request.model_dump(mode="json"),
    idempotency_key=request.attemptId,
)
```

- [ ] **Step 6: 运行同一测试确认 GREEN**

```powershell
uv run pytest packages/service-contracts/tests/test_review_contracts.py apps/core-api/tests/reviews/test_evaluation_identity.py apps/core-api/tests/reviews/test_internal_job_identity.py apps/core-api/tests/reviews/test_artifact_lifecycle.py apps/agent-service/tests/jobs/test_adapters.py apps/agent-service/tests/integration/test_core_callbacks.py -q
```

Expected: PASS。

- [ ] **Step 7: 验证无数据库结构变化并提交**

```powershell
uv run pytest apps/core-api/tests/db/test_schema_guard.py -q
git diff --exit-code -- apps/core-api/src/inkforge_core/db/models.py apps/core-api/src/inkforge_core/db/schema-contract.json
git add packages/service-contracts/src/inkforge_contracts/reviews.py packages/service-contracts/src/inkforge_contracts/__init__.py packages/service-contracts/tests/test_review_contracts.py apps/core-api/src/inkforge_core/reviews apps/core-api/src/inkforge_core/writing/context.py apps/core-api/tests/reviews apps/agent-service/src/inkforge_agents/clients/core.py apps/agent-service/src/inkforge_agents/jobs/adapters.py apps/agent-service/tests/jobs/test_adapters.py apps/agent-service/tests/integration/test_core_callbacks.py
git commit -m "功能：绑定复审来源与内部幂等身份"
```

### Task 6：增加 ReviewAttempt、reservation 和快照兼容 reducer

**Files:**

- Modify: `apps/agent-service/src/inkforge_agents/reviewing/contracts.py`
- Modify: `apps/agent-service/src/inkforge_agents/graph/state.py`
- Modify: `apps/agent-service/src/inkforge_agents/graph/snapshots.py`
- Modify: `apps/agent-service/tests/reviewing/test_contracts.py`
- Modify: `apps/agent-service/tests/graph/test_snapshots.py`
- Create: `apps/agent-service/tests/graph/test_review_reducer.py`

- [ ] **Step 1: 写 attempt reducer、legacy 读取和敏感字段拒绝测试**

```python
def test_review_attempt_reducer_replaces_same_attempt() -> None:
    pending = attempt(persistence_status="pending")
    persisted = attempt(persistence_status="persisted")
    assert reduce_review_attempts([pending], [persisted]) == [persisted]


def test_snapshot_rejects_dispatch_permit() -> None:
    state = create_state()
    state["dispatchPermits"] = {"model-1": "secret"}
    with pytest.raises(ValueError, match="仅运行时字段"):
        serialize_snapshot(state)
```

- [ ] **Step 2: 运行测试确认 RED**

```powershell
uv run pytest apps/agent-service/tests/reviewing/test_contracts.py apps/agent-service/tests/graph/test_snapshots.py apps/agent-service/tests/graph/test_review_reducer.py -q
```

Expected: FAIL，因为 reservation/attempt/reducer 和 snapshot v2 尚不存在。

- [ ] **Step 3: 定义稳定模型和 reducer**

```python
class ReviewIdentity(StrictReviewModel):
    taskId: str
    runId: str
    jobId: str
    artifactId: str
    artifactKey: str
    artifactRevision: int = Field(ge=1)
    artifactPayloadHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    iteration: int = Field(ge=0)
    reviewer: AgentId
    policyId: str


class ReviewModelReservation(StrictReviewModel):
    schemaVersion: Literal["1.0"] = "1.0"
    attemptId: str = Field(pattern=r"^[0-9a-f]{64}$")
    modelRequestId: str = Field(min_length=1)
    identity: ReviewIdentity
    stage: Literal["reviewer", "protocol_repair"]
    ownerEpoch: int = Field(ge=1)
    sourceModelRequestId: str | None = None
    status: Literal["reserved", "result_committed", "outcome_unknown"]


ReviewExecutionStage = ModelExecutionStage | Literal[
    "artifact_source_validation", "evaluation_persistence"
]
ReviewErrorCode = Literal[
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


class ReviewFailure(StrictReviewModel):
    code: ReviewErrorCode
    category: Literal[
        "provider", "protocol", "evidence", "recovery", "persistence", "source"
    ]
    retryable: bool
    safeToRetry: bool
    stage: ReviewExecutionStage
    publicMessage: str = Field(min_length=1)


class ReviewAttempt(StrictReviewModel):
    schemaVersion: Literal["1.0"] = "1.0"
    attemptId: str = Field(pattern=r"^[0-9a-f]{64}$")
    reservationEpoch: int = Field(ge=1)
    identity: ReviewIdentity
    modelStatus: Literal["complete", "incomplete"]
    persistenceStatus: Literal["not_applicable", "pending", "persisted", "failed"]
    evaluation: StructuredReviewEvaluation | None = None
    failure: ReviewFailure | None = None
    billingRequestIds: list[str] = Field(default_factory=list)


def reduce_review_attempts(
    current: list[dict[str, JsonValue]],
    incoming: list[dict[str, JsonValue]],
) -> list[dict[str, JsonValue]]:
    by_id = {str(item["attemptId"]): item for item in current}
    for item in incoming:
        by_id[str(item["attemptId"])] = item
    return list(by_id.values())
```

`attemptId` 对 `schemaVersion+ReviewIdentity` 的 canonical JSON 做完整 SHA-256；validator 强制 complete/incomplete、evaluation/failure、persistenceStatus 和 reservationEpoch 组合。`GraphState` 增加 `reviewReservations` 和 `reviewAttempts`，移除新流程对 `reviewResults operator.add` 的依赖；legacy snapshot 仍能读取旧 `reviewResults`。snapshot v2 只保存严格结构结果，不保存 permit/reasoning/grant/raw output。

`REVIEW_PROTOCOL_VERSION=legacy` 只阻止尚未进入阶段 R 的新任务写 v1；已经含 v1 reservation/attempt 的 snapshot 必须继续走 v1 恢复路由。增加测试证明 legacy 与 v1 均可读取，旧镜像格式不能覆盖 v1 sequence。

- [ ] **Step 4: 运行同一测试确认 GREEN**

```powershell
uv run pytest apps/agent-service/tests/reviewing/test_contracts.py apps/agent-service/tests/graph/test_snapshots.py apps/agent-service/tests/graph/test_review_reducer.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add apps/agent-service/src/inkforge_agents/reviewing/contracts.py apps/agent-service/src/inkforge_agents/graph/state.py apps/agent-service/src/inkforge_agents/graph/snapshots.py apps/agent-service/tests/reviewing/test_contracts.py apps/agent-service/tests/graph/test_snapshots.py apps/agent-service/tests/graph/test_review_reducer.py
git commit -m "功能：增加可恢复复审状态协议"
```

### Task 7：实现 AES-GCM 恢复文件、Redis fencing 和有界清理

**Files:**

- Create: `apps/agent-service/src/inkforge_agents/reviewing/recovery_crypto.py`
- Create: `apps/agent-service/src/inkforge_agents/reviewing/recovery_index.py`
- Create: `apps/agent-service/src/inkforge_agents/reviewing/recovery_store.py`
- Modify: `apps/agent-service/src/inkforge_agents/config.py`
- Modify: `apps/agent-service/src/inkforge_agents/app.py`
- Create: `apps/agent-service/tests/reviewing/test_recovery_crypto.py`
- Create: `apps/agent-service/tests/reviewing/test_recovery_index.py`
- Create: `apps/agent-service/tests/reviewing/test_recovery_store.py`
- Modify: `apps/agent-service/tests/test_config.py`
- Modify: `apps/agent-service/tests/test_health.py`

- [ ] **Step 1: 写 nonce/AAD、fencing、容量和 janitor 失败测试**

```python
def test_same_payload_uses_distinct_gcm_nonce(tmp_path: Path) -> None:
    store = crypto_store(tmp_path)
    first = store.encrypt(payload(), aad())
    second = store.encrypt(payload(), aad())
    assert first.nonce != second.nonce


async def test_expired_owner_cannot_commit(redis_index) -> None:
    owner = await redis_index.acquire(reservation())
    await redis_index.expire_for_test(owner)
    assert not await redis_index.begin_staging(owner)


async def test_capacity_failure_happens_before_provider(capacity_store) -> None:
    capacity_store.fill_to_limit()
    with pytest.raises(ReviewRecoveryError, match="容量"):
        await capacity_store.reserve_capacity(reservation())
```

覆盖 12-byte CSPRNG nonce、canonical JSON AAD、keyId 轮换、0400/0600 keyring、symlink 拒绝、8 MiB/256 MiB/256 文件、PEXPIRE、ownerEpoch、迟到 owner、坏文件、grant 到期去敏和 24 小时 janitor。

- [ ] **Step 2: 运行 recovery 测试确认 RED**

```powershell
uv run pytest apps/agent-service/tests/reviewing/test_recovery_crypto.py apps/agent-service/tests/reviewing/test_recovery_index.py apps/agent-service/tests/reviewing/test_recovery_store.py apps/agent-service/tests/test_config.py apps/agent-service/tests/test_health.py -q
```

Expected: FAIL，因为 recovery 模块和配置尚不存在。

- [ ] **Step 3: 实现 AES-GCM envelope 和 keyring**

```python
class RecoveryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schemaVersion: Literal["1.0"] = "1.0"
    keyId: str
    nonce: str
    ciphertext: str
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class RecoveryIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schemaVersion: Literal["1.0"] = "1.0"
    keyId: str
    modelRequestId: str
    attemptId: str
    ownerEpoch: int = Field(ge=1)
    taskId: str
    runId: str
    jobId: str
    artifactId: str
    revision: int = Field(ge=1)
    reviewer: AgentId
    stage: Literal["reviewer", "protocol_repair"]


class ReviewTurnRecoveryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schemaVersion: Literal["1.0"] = "1.0"
    providerResponseId: str | None = None
    finishReason: ModelFinishReason
    evaluation: EvaluationArgs | None = None
    protocolErrorCode: str | None = None
    toolNames: list[str] = Field(default_factory=list)
    usage: ModelUsage
    billingRequestId: str
    usageReported: bool
    grantToken: str | None = None
    grantExpiresAt: AwareDatetime | None = None


class ReviewRecoveryError(RuntimeError):
    pass


def canonical_aad(identity: RecoveryIdentity) -> bytes:
    return json.dumps(
        identity.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
```

`ReviewTurnRecoveryRecord` validator 强制 evaluation 与 protocolErrorCode 二选一；`usageReported=false` 时 grantToken/expiresAt 必填，true 时两者必须清空。每次 encrypt 使用 `os.urandom(12)`；文件名只用 SHA-256 modelRequestId；拒绝非普通文件和 symlink；原子流程严格执行 temp→fsync→fence→replace→dir fsync→commit CAS。

- [ ] **Step 4: 实现 Redis Lua/CAS owner index**

状态固定为 `reserved/provider_inflight/result_staging/result_committed/consumed`。每个脚本校验 `ownerEpoch+ownerLease+state` 并设置不超过 absolute deadline 的 PEXPIRE；失租只允许 outcome unknown，绝不重新 acquire 同一 modelRequestId 调 Provider。

```python
class ReviewOwner(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    modelRequestId: str
    attemptId: str
    ownerEpoch: int = Field(ge=1)
    ownerLease: str
    state: Literal[
        "reserved", "provider_inflight", "result_staging",
        "result_committed", "consumed",
    ]
    absoluteDeadlineMs: int = Field(ge=1)
```

- [ ] **Step 5: 实现容量 lease 和 janitor 生命周期**

Provider 前预留 8 MiB；结果超限、卷满或文件数满均完整失败。启动和运行期 janitor 清理无 Core reservation 索引、超龄文件和过期 grant；敏感文件删除后只留无正文 tombstone。production 缺 keyring/目录/权限时 readiness 失败。

```python
class RecoveryLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    recordMaxBytes: int = 8_388_608
    volumeMaxBytes: int = 268_435_456
    maxFiles: int = 256
    maxAgeSeconds: int = 86_400
```

- [ ] **Step 6: 运行同一测试确认 GREEN**

```powershell
uv run pytest apps/agent-service/tests/reviewing/test_recovery_crypto.py apps/agent-service/tests/reviewing/test_recovery_index.py apps/agent-service/tests/reviewing/test_recovery_store.py apps/agent-service/tests/test_config.py apps/agent-service/tests/test_health.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add apps/agent-service/src/inkforge_agents/reviewing/recovery_crypto.py apps/agent-service/src/inkforge_agents/reviewing/recovery_index.py apps/agent-service/src/inkforge_agents/reviewing/recovery_store.py apps/agent-service/src/inkforge_agents/config.py apps/agent-service/src/inkforge_agents/app.py apps/agent-service/tests/reviewing apps/agent-service/tests/test_config.py apps/agent-service/tests/test_health.py
git commit -m "功能：增加复审结果加密恢复区"
```

### Task 8：实现 recovery-aware Reviewer 调用与一次 protocol repair

**Files:**

- Create: `apps/agent-service/src/inkforge_agents/reviewing/service.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/agent_runner.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/model_runtime.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py`
- Modify: `apps/agent-service/src/inkforge_agents/jobs/adapters.py`
- Create: `apps/agent-service/tests/reviewing/test_service.py`
- Create: `apps/agent-service/tests/runtime/test_reviewer_runtime.py`
- Modify: `apps/agent-service/tests/runtime/test_billing_runtime.py`
- Modify: `apps/agent-service/tests/jobs/test_adapters.py`

- [ ] **Step 1: 写 permit/recovery/protocol repair 失败测试**

```python
async def test_missing_permit_with_no_record_becomes_unknown(service) -> None:
    result = await service.execute(reservation(), dispatch_permit=None)
    assert result.modelStatus == "incomplete"
    assert result.persistenceStatus == "not_applicable"
    assert result.failure.code == "MODEL_PROVIDER_OUTCOME_UNKNOWN"
    assert provider.calls == 0


async def test_recovery_record_skips_provider_and_reports_usage(service) -> None:
    await recovery_store.put(valid_record(usage_reported=False))
    result = await service.execute(reservation(), dispatch_permit=None)
    assert result.modelStatus == "complete"
    assert provider.calls == 0
    assert billing.report_calls == 1
```

还要覆盖：旧 owner 迟到只补报 usage；`result_committed` 坏文件→recovery failed；observer 前崩溃→gap 帧；invalid tool 参数只在内存 repair；repair 缺内存→protocol incomplete；repair 使用独立 reservation。

- [ ] **Step 2: 运行测试确认 RED**

```powershell
uv run pytest apps/agent-service/tests/reviewing/test_service.py apps/agent-service/tests/runtime/test_reviewer_runtime.py apps/agent-service/tests/runtime/test_billing_runtime.py apps/agent-service/tests/jobs/test_adapters.py -q
```

Expected: FAIL，因为 ReviewingService 和 recovery-aware ModelRuntime 接口尚不存在。

- [ ] **Step 3: 把 AgentRunner 拆成 prepare/execute**

```python
class PreparedAgentRun(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    agentId: AgentId
    stage: ModelExecutionStage
    modelRequest: ModelTurnRequest
    modelContext: ModelCallContext
    terminalControlTools: frozenset[str]
    maxIterations: int = Field(ge=1)


@dataclass(frozen=True, slots=True)
class DispatchPermit:
    model_request_id: str
    attempt_id: str
    owner_epoch: int
    checkpoint_sequence: int
    capacity_lease_id: str


class ReviewRepairCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    attemptId: str
    sourceModelRequestId: str
    repairModelRequestId: str
    reviewer: AgentId
    transientCacheKey: str


class TransientRepairPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    visibleContent: str
    invalidToolNames: list[str]
    invalidArguments: list[str]
    identity: ReviewIdentity

    def to_repair_json(self) -> str:
        return self.model_dump_json()


class RecoveryLoadResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["available", "missing", "invalid"]
    record: ReviewTurnRecoveryRecord | None = None
    errorCode: str | None = None
```

普通 `run()` 继续 `prepare()` 后直接执行；Reviewer 阶段 R 只调用 prepare 取得稳定 modelRequestId，阶段 A 重建 PreparedAgentRun 并验证 requestId 与 reservation 完全一致。`ReviewingService.execute()` 的参数固定为 keyword-only `reservation: ReviewModelReservation`、`prepared: PreparedAgentRun`、`dispatch_permit: DispatchPermit | None`，返回 `ReviewAttempt | ReviewRepairCandidate`。

- [ ] **Step 4: 实现 ReviewingService 状态机**

有 permit：校验 capacity lease→Redis owner→Provider→encrypted record→usage→observer→protocol。无 permit：只允许读取合法 record；缺失/坏记录形成 unknown/recovery failure。Provider 明确证明没有生成结果且 `safeToRetry=true` 时，只返回“需要新 reservation”，不得在 service 内直接循环。

```python
if dispatch_permit is None:
    recovered = await self._recovery.load(reservation)
    if recovered.kind == "available":
        assert recovered.record is not None
        return await self._consume_recovered(reservation, recovered.record)
    if recovered.kind == "invalid":
        assert recovered.errorCode is not None
        return recovery_failed_attempt(reservation, recovered.errorCode)
    return outcome_unknown_attempt(reservation)
return await self._dispatch_with_permit(reservation, prepared, dispatch_permit)
```

- [ ] **Step 5: 实现一次 protocol repair**

repair 输入只含当前进程中的可见结果、非法参数、目标 schema 和 ReviewIdentity；不走普通 AgentRunner，不带作品上下文。先返回 repair candidate，外层保存聚合 repair reservation 后才执行；第二次仍非法直接 incomplete。

```python
def build_protocol_repair_messages(candidate: TransientRepairPayload) -> list[ModelMessage]:
    return [
        ModelMessage(role="system", content="只修复 submit_evaluation 参数结构，不重新评审作品。"),
        ModelMessage(role="user", content=candidate.to_repair_json()),
    ]
```

- [ ] **Step 6: 运行同一测试确认 GREEN**

```powershell
uv run pytest apps/agent-service/tests/reviewing/test_service.py apps/agent-service/tests/runtime/test_reviewer_runtime.py apps/agent-service/tests/runtime/test_billing_runtime.py apps/agent-service/tests/jobs/test_adapters.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add apps/agent-service/src/inkforge_agents/reviewing/service.py apps/agent-service/src/inkforge_agents/runtime/agent_runner.py apps/agent-service/src/inkforge_agents/runtime/model_runtime.py apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py apps/agent-service/src/inkforge_agents/jobs/adapters.py apps/agent-service/tests/reviewing/test_service.py apps/agent-service/tests/runtime/test_reviewer_runtime.py apps/agent-service/tests/runtime/test_billing_runtime.py apps/agent-service/tests/jobs/test_adapters.py
git commit -m "功能：接入可恢复 Reviewer 执行"
```

### Task 9：把 Operation 图和 WritingJobHandler 拆成 R/A/B 阶段

**Files:**

- Modify: `apps/agent-service/src/inkforge_agents/operations/graph.py`
- Modify: `apps/agent-service/src/inkforge_agents/graph/state.py`
- Modify: `apps/agent-service/src/inkforge_agents/jobs/adapters.py`
- Modify: `apps/agent-service/src/inkforge_agents/jobs/writing.py`
- Modify: `apps/agent-service/src/inkforge_agents/clients/core.py`
- Modify: `apps/agent-service/tests/graph/test_operation_graph.py`
- Modify: `apps/agent-service/tests/operations/test_review_routing.py`
- Modify: `apps/agent-service/tests/jobs/test_adapters.py`
- Modify: `apps/agent-service/tests/jobs/test_writing.py`
- Modify: `apps/agent-service/tests/integration/test_core_callbacks.py`

- [ ] **Step 1: 写聚合 sequence、首次 applied permit 和阶段 B 恢复失败测试**

```python
async def test_review_batch_saves_one_reservation_checkpoint_before_provider(handler) -> None:
    await handler(job())
    reservation_saves = [
        item for item in core.checkpoints
        if item["checkpoint"]["operationStep"] == "review_model_reservation_pending"
    ]
    assert len(reservation_saves) == 1
    assert len(reservation_saves[0]["checkpoint"]["reviewReservations"]) == 2
    assert provider.calls_happened_after(reservation_saves[0]["appliedAt"])


async def test_already_applied_does_not_create_dispatch_permit(handler) -> None:
    core.checkpoint_disposition = "already_applied"
    await handler(job())
    assert provider.calls == 0
    assert final_attempt().failure.code == "MODEL_PROVIDER_OUTCOME_UNKNOWN"
```

覆盖：主 Reviewer 一个聚合 reservation sequence；repair 下一连续 sequence；并行分支不能独立 checkpoint；ReviewAttempt checkpoint 后重启直接阶段 B；Core evaluation 临时失败不回阶段 A。

- [ ] **Step 2: 运行 graph/job 测试确认 RED**

```powershell
uv run pytest apps/agent-service/tests/graph/test_operation_graph.py apps/agent-service/tests/operations/test_review_routing.py apps/agent-service/tests/jobs/test_adapters.py apps/agent-service/tests/jobs/test_writing.py apps/agent-service/tests/integration/test_core_callbacks.py -q
```

Expected: FAIL，因为图仍在 Reviewer 分支内调用模型/evaluation，Handler 仍只在整图结束后保存一次 checkpoint。

- [ ] **Step 3: 增加阶段 R/A/B 节点和路由**

```text
prepareReviewReservations
  -> reviewReservationBoundary（返回 Handler）
  -> reviewArtifactWorker Send
  -> prepareRepairReservations（有 candidate 时返回 Handler）
  -> persistReviewAttemptsBoundary（返回 Handler）
  -> persistArtifactReviews
  -> mergeArtifactReviews
```

Reviewer worker 只返回 ReviewAttempt/repair candidate，不调用 Core evaluation。`persistArtifactReviews` 只处理 complete+pending；merge 只处理 complete+persisted，incomplete/failed 进入带警告的用户审核，不生成内容 block。

- [ ] **Step 4: 把 WritingJobHandler 改成 phased loop**

`save_checkpoint()` 返回并验证 `CallbackReceipt`。只有本进程刚创建 reservation、disposition=`applied` 且 recovery store 已为该 reservation 取得容量 lease，才生成含 `capacity_lease_id` 的 permit；`already_applied`、响应丢失、容量不足和恢复均无 permit。同一 snapshot 保存重试使用相同 sequence，确认前不再次 `ainvoke()`；内部 boundary 保存后继续下一次图调用，waiting_user 语义不变。

```python
async def save_checkpoint(
    self,
    resource: RunResource,
    *,
    sequence: int,
    checkpoint: dict[str, JsonValue],
) -> CallbackReceipt:
    job_id = _writing_job_id(resource)
    event_id = _event_id(resource.runId, job_id, sequence, "checkpoint")
    body = CheckpointCallback(
        protocolVersion="1.1",
        eventId=event_id,
        jobId=job_id,
        runId=resource.runId,
        taskId=resource.taskId,
        sequence=sequence,
        checkpoint=checkpoint,
        occurredAt=_occurred_at(event_id),
    )
    value = await self._request(
        "PUT",
        f"/internal/v1/writing/runs/{resource.runId}/checkpoint",
        body.model_dump(mode="json"),
        scope=ServiceScope.CALLBACK_CHECKPOINT,
        resource=resource,
        idempotency_key=event_id,
        require_callback_receipt=True,
    )
    return CallbackReceipt.model_validate(value)
```

- [ ] **Step 5: 删除 CoreGraphAgentExecutor 的隐式 evaluation 提交**

`CoreGraphAgentExecutor.run()` 只返回 Agent 结果；新增显式 `persist_review_attempt()` 调用 `CoreArtifactPort.submit_evaluation()`，以 attemptId 为 idempotency key。临时错误保持 pending，永久 source/persistence 错误写 typed ReviewFailure。

```python
async def persist_review_attempt(
    artifacts: CoreArtifactPort,
    attempt: ReviewAttempt,
) -> ReviewAttempt:
    if attempt.modelStatus != "complete" or attempt.persistenceStatus != "pending":
        return attempt
    await artifacts.submit_review_attempt(attempt)
    return attempt.model_copy(update={"persistenceStatus": "persisted", "failure": None})
```

- [ ] **Step 6: 运行同一测试确认 GREEN**

```powershell
uv run pytest apps/agent-service/tests/graph/test_operation_graph.py apps/agent-service/tests/operations/test_review_routing.py apps/agent-service/tests/jobs/test_adapters.py apps/agent-service/tests/jobs/test_writing.py apps/agent-service/tests/integration/test_core_callbacks.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add apps/agent-service/src/inkforge_agents/operations/graph.py apps/agent-service/src/inkforge_agents/graph/state.py apps/agent-service/src/inkforge_agents/jobs/adapters.py apps/agent-service/src/inkforge_agents/jobs/writing.py apps/agent-service/src/inkforge_agents/clients/core.py apps/agent-service/tests/graph/test_operation_graph.py apps/agent-service/tests/operations/test_review_routing.py apps/agent-service/tests/jobs/test_adapters.py apps/agent-service/tests/jobs/test_writing.py apps/agent-service/tests/integration/test_core_callbacks.py
git commit -m "重构：拆分复审调用与持久化阶段"
```

### Task 10：统一 job/queue 错误映射和恢复日志

**Files:**

- Modify: `apps/agent-service/src/inkforge_agents/jobs/writing.py`
- Modify: `apps/agent-service/src/inkforge_agents/jobs/quality.py`
- Modify: `apps/agent-service/src/inkforge_agents/queue/consumer.py`
- Modify: `apps/agent-service/src/inkforge_agents/app.py`
- Modify: `apps/agent-service/src/inkforge_agents/observability/model_observer.py`
- Modify: `apps/agent-service/src/inkforge_agents/observability/human_workflow_log.py`
- Modify: `apps/agent-service/tests/jobs/test_writing.py`
- Modify: `apps/agent-service/tests/jobs/test_quality.py`
- Modify: `apps/agent-service/tests/queue/test_consumer.py`
- Modify: `apps/agent-service/tests/observability/test_model_log_bridge.py`
- Modify: `apps/agent-service/tests/observability/test_human_workflow_log.py`

- [ ] **Step 1: 写 typed retry、内容 block 隔离和 recovery gap 失败测试**

```python
async def test_provider_failure_is_not_content_block(graph) -> None:
    state = await graph.ainvoke(state_with_provider_error())
    attempt = ReviewAttempt.model_validate(state["reviewAttempts"][0])
    assert attempt.modelStatus == "incomplete"
    assert attempt.failure.code == "MODEL_PROVIDER_FAILED"
    assert attempt.evaluation is None


def test_recovery_gap_does_not_fake_full_output(log) -> None:
    frame = log.record_recovery_gap(recovery_gap_record())
    assert frame.header["recoveredFromDurableResult"] is True
    assert frame.header["rawVisibleOutputAvailable"] is False
    assert frame.body is None
```

- [ ] **Step 2: 运行错误/日志测试确认 RED**

```powershell
uv run pytest apps/agent-service/tests/jobs/test_writing.py apps/agent-service/tests/jobs/test_quality.py apps/agent-service/tests/queue/test_consumer.py apps/agent-service/tests/observability/test_model_log_bridge.py apps/agent-service/tests/observability/test_human_workflow_log.py -q
```

Expected: FAIL，因为现有 writing/queue 仍使用字符串错误提取，日志没有 recovery gap 帧。

- [ ] **Step 3: 按 code/category/retryable/safeToRetry 映射**

writing/quality 的 Core 失败回调只暴露错误码和预定义中文说明；QueueConsumer 只读 typed `retryable`，不解析字符串。Redis/队列基础设施异常继续用既有分类器，未知程序错误保持 draining/restart 语义。

```python
def job_error_policy(exc: Exception) -> tuple[str, str, bool]:
    if isinstance(exc, ReviewExecutionError):
        return exc.code, exc.publicMessage, exc.retryable
    if isinstance(exc, ModelExecutionError):
        return exc.code, exc.publicMessage, exc.retryable
    raise UnknownJobExecutionError("未分类程序异常") from exc
```

- [ ] **Step 4: 扩展人工日志结构头和恢复缺口帧**

新增 `policyId/stage/turnIndex/reasoningTokens/invalidToolCallCount/usageReported/recoveredFromDurableResult/rawVisibleOutputAvailable/recoveryGapReason/ownerEpoch/reservationEpoch`。正常路径仍记录完整 messages/output；observer 前崩溃只写元数据、Provider response ID 和结构化结果摘要 hash，不伪造正文。

```python
class RecoveryGapLogRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    requestId: str
    providerResponseId: str | None = None
    resultDigest: str = Field(pattern=r"^[0-9a-f]{64}$")
    recoveredFromDurableResult: Literal[True] = True
    rawVisibleOutputAvailable: Literal[False] = False
    recoveryGapReason: Literal["process_crash_before_observer"]
```

- [ ] **Step 5: 运行同一测试确认 GREEN**

```powershell
uv run pytest apps/agent-service/tests/jobs/test_writing.py apps/agent-service/tests/jobs/test_quality.py apps/agent-service/tests/queue/test_consumer.py apps/agent-service/tests/observability/test_model_log_bridge.py apps/agent-service/tests/observability/test_human_workflow_log.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add apps/agent-service/src/inkforge_agents/jobs apps/agent-service/src/inkforge_agents/queue/consumer.py apps/agent-service/src/inkforge_agents/app.py apps/agent-service/src/inkforge_agents/observability apps/agent-service/tests/jobs apps/agent-service/tests/queue/test_consumer.py apps/agent-service/tests/observability
git commit -m "修复：区分复审内容结论与执行失败"
```

### Task 11：接入 recovery secret、持久卷、部署门禁和当前文档

**Files:**

- Create: `scripts/generate-model-recovery-keyring.py`
- Modify: `scripts/deploy-production.sh`
- Modify: `infra/compose.yaml`
- Modify: `infra/compose.test.yaml`
- Modify: `.env.example`
- Modify: `.env.local.example`
- Create: `tests/architecture/test_model_recovery_security.py`
- Modify: `tests/architecture/test_compose_security.py`
- Modify: `tests/architecture/test_deploy_scripts.py`
- Modify: `docs/WORKFLOW_EVENT_LOG_FORMAT.md`
- Modify: `docs/requirements/03-ai-writing-and-agents.md`
- Modify: `docs/requirements/04-review-quality-and-workflow.md`
- Modify: `docs/requirements/05-auth-billing-and-ops.md`
- Modify: `apps/agent-service/AGENTS.md`

- [ ] **Step 1: 写 Compose 挂载、权限和部署顺序失败测试**

```python
def test_recovery_secret_is_agent_only(compose) -> None:
    agent = compose["services"]["agent-service"]
    assert any("model-recovery-keyring.json" in item for item in agent["volumes"])
    for name in ("core-api", "web", "redis"):
        mounts = compose["services"][name].get("volumes", [])
        assert all("model-recovery" not in item for item in mounts)
```

测试还要断言 root filesystem 仍 read-only、独立 named volume、keyring ro、部署先校验 key/owner/mode 再切镜像、初始化失败阻断。

- [ ] **Step 2: 运行架构测试确认 RED**

```powershell
uv run pytest tests/architecture/test_model_recovery_security.py tests/architecture/test_compose_security.py tests/architecture/test_deploy_scripts.py -q
```

Expected: FAIL，因为 keyring/volume/deploy 初始化尚不存在。

- [ ] **Step 3: 新增离线 keyring 生成器**

脚本使用 `secrets.token_bytes(32)` 生成 AES key，输出 `{currentKeyId, keys}` JSON；拒绝覆盖已有文件，写入 mode 0600。它不得打印 key 内容，只打印目标路径和 keyId。

```python
parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
args = parser.parse_args()
target: Path = args.output
key_id = f"model-recovery-{datetime.now(UTC):%Y%m%d}"
document = {
    "currentKeyId": key_id,
    "keys": {key_id: base64.b64encode(secrets.token_bytes(32)).decode("ascii")},
}
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
print(f"已创建恢复 keyring：{target}，keyId={key_id}")
```

- [ ] **Step 4: 修改 Compose 和部署脚本**

Agent Service 独占挂载 `/data/model-recovery` 和只读 keyring；顶层新增 `model_recovery` volume。部署脚本校验 secret owner `10001:10001`、mode 0400/0600，并用临时容器初始化卷目录为 owner 10001、mode 0700；任一步失败都在 Compose 更新前退出。

```yaml
environment:
  MODEL_RECOVERY_KEYRING_PATH: /run/inkforge-keys/model-recovery-keyring.json
  MODEL_RECOVERY_DIR: /data/model-recovery
volumes:
  - model_recovery:/data/model-recovery
  - ${SERVICE_KEYS_DIR:-./secrets}/model-recovery-keyring.json:/run/inkforge-keys/model-recovery-keyring.json:ro
```

- [ ] **Step 5: 同步当前需求和日志文档**

实现已通过前十个 Task 的测试后，才把 03/04/05、Agent 架构和日志格式更新为当前事实：分场景策略、DeepSeek reasoning 仅内存、Reviewer R/A/B、outcome unknown、正常完整日志与恢复 gap 例外。不得把规格中的成本预测写成已验证结果。

```text
正常模型调用继续记录完整 messages/output，但永不记录 reasoning_content。
若进程在恢复记录提交后、observer 前崩溃，恢复路径只写显式 recovery gap 帧；
该帧不伪造原始正文，也不得触发 Provider 重调。
```

- [ ] **Step 6: 运行架构测试和 Compose 解析确认 GREEN**

```powershell
uv run pytest tests/architecture/test_model_recovery_security.py tests/architecture/test_compose_security.py tests/architecture/test_deploy_scripts.py -q
docker compose --env-file .env.example -f infra/compose.yaml config --quiet
```

Expected: pytest PASS，Compose config 命令 exit 0。

- [ ] **Step 7: 提交**

```powershell
git add scripts/generate-model-recovery-keyring.py scripts/deploy-production.sh infra/compose.yaml infra/compose.test.yaml .env.example .env.local.example tests/architecture docs/WORKFLOW_EVENT_LOG_FORMAT.md docs/requirements/03-ai-writing-and-agents.md docs/requirements/04-review-quality-and-workflow.md docs/requirements/05-auth-billing-and-ops.md apps/agent-service/AGENTS.md
git commit -m "运维：接入复审恢复密钥与持久卷"
```

### Task 12：执行故障注入、全量验证和发布前审计

**Files:**

- Create: `apps/agent-service/tests/integration/test_reviewer_recovery_drill.py`
- Modify: `tests/architecture/test_stability_drill.py`
- Modify: `tests/architecture/test_rollback_drill.py`
- Modify: `docs/specs/2026-08-23-model-policy-and-review-protocol.md`

- [ ] **Step 1: 写完整故障矩阵测试**

故障点固定为：reservation 前；applied 后 permit 前；Redis owner 后；Provider 请求发出后；result_staging 前后；rename 前后；usage report 前后；observer 前后；ReviewAttempt checkpoint 前后；Core evaluation 临时失败；Redis key 丢失；lease 过期；旧 owner 迟到；keyring 轮换；文件损坏/超龄；容量不足。

每个用例必须断言：

```text
同一 modelRequestId Provider 调用次数 <= 1
无合法恢复结果时不自动重调
reservation/attempt sequence 单调
同 attempt 同结果幂等、不同结果冲突
旧 owner 不能写 recovery/observer/ReviewAttempt
usage 只按原 requestId 幂等上报
Artifact 仍等待用户确认
reasoning/grant/raw invalid args 不进入快照和日志
```

- [ ] **Step 2: 运行定向集成测试确认 GREEN**

```powershell
uv run pytest apps/agent-service/tests/integration/test_reviewer_recovery_drill.py tests/architecture/test_stability_drill.py tests/architecture/test_rollback_drill.py -q
```

Expected: PASS。

- [ ] **Step 3: 运行 Python 全量验证**

```powershell
uv run pytest
uv run ruff check .
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
```

Expected: 全部 exit 0。若仓库存在与本分支无关的既有失败，记录精确命令、测试名和基线证据，不能删除测试或放宽断言。

- [ ] **Step 4: 生成并核对 API 客户端**

```powershell
npm run api:generate
npm run api:check
npm run typecheck
npm run lint
```

Expected: 全部 exit 0；公共 ReviewArtifact 客户端不得出现 `artifactPayloadHash`。

- [ ] **Step 5: 运行数据库与 Compose 静态护栏**

```powershell
uv run pytest apps/core-api/tests/db/test_schema_guard.py tests/architecture/test_compose_security.py tests/architecture/test_model_recovery_security.py tests/architecture/test_openapi_generation.py tests/architecture/test_agent_readiness_probe.py -q
git diff --exit-code -- apps/core-api/src/inkforge_core/db/models.py apps/core-api/src/inkforge_core/db/schema-contract.json
docker compose --env-file .env.example -f infra/compose.yaml config --quiet
```

Expected: 全部 exit 0；无 migration、DDL 或 schema contract diff。

- [ ] **Step 6: 在服务器 dev 数据库执行非付费全链路验收**

只使用 fake/mock Provider，验证 Core checkpoint/evaluation/重启恢复和 SSE 错误显示；不得调用 DeepSeek。保存 taskId/runId/modelRequestId、checkpoint sequence、Provider mock call count 和最终 Artifact 状态作为证据。

- [ ] **Step 7: 更新规格状态并提交最终验证记录**

只有全部必需验证通过后，把规格状态从“待用户审阅”改为“已实现，待生产观测”；记录未做的真实付费模型质量/成本验证仍是生产假设。

```powershell
git add apps/agent-service/tests/integration/test_reviewer_recovery_drill.py tests/architecture/test_stability_drill.py tests/architecture/test_rollback_drill.py docs/specs/2026-08-23-model-policy-and-review-protocol.md
git commit -m "测试：覆盖复审恢复故障矩阵"
```

## 任务依赖与并行边界

```text
Task 1 -> Task 2 -> Task 3
Task 1 -> Task 4
Task 4 -> Task 5 -> Task 6
Task 3 + Task 6 -> Task 7
Task 7 + Task 8 -> Task 9
Task 9 -> Task 10 -> Task 11 -> Task 12
```

- Task 4 与 Task 2/3 可以在不同 worktree 并行，但合并前必须重跑 Task 3 和 Task 4 的联合测试。
- Task 5 依赖 Task 4 的结构契约；Task 6 依赖 Task 5 的 attempt/hash 身份。
- Task 7 是安全基础设施，Task 8 不得在 recovery 单测通过前接入 Provider。
- Task 9 改变 checkpoint 边界，必须在 Task 8 完整 GREEN 后单独实施。
- Task 11 的 requirements 文档只能在实现测试通过后更新，不能提前宣称当前事实。

## 规格覆盖索引

| 规格要求 | 实施任务 |
| --- | --- |
| ModelExecutionPolicy、stage、legacy/review-v1 | Task 1、Task 6、Task 9 |
| DeepSeek thinking/reasoning/tool/usage 原始协议 | Task 2、Task 3 |
| reasoning 只在工具循环回放、不持久化 | Task 2、Task 3、Task 7、Task 10 |
| Reviewer 严格 issues/advisories 和确定性 verdict | Task 4 |
| Artifact payload hash、attemptId、epoch、内部幂等 | Task 5 |
| ReviewReservation/ReviewAttempt 稳定状态与兼容 reducer | Task 6 |
| AES-GCM、Redis fencing、容量、TTL、janitor | Task 7 |
| recovery-aware Reviewer 与 protocol repair | Task 8 |
| R/A/B checkpoint 与 Core evaluation 分离 | Task 9 |
| typed error、outcome unknown、恢复日志缺口 | Task 10 |
| secret/volume/部署/当前需求同步 | Task 11 |
| 故障矩阵、公共 API、schema、生产观测 | Task 12 |

## 生产观测门槛

发布后使用至少三个正常章节任务观察，不作为运行时硬限制：

```text
Reviewer/quality reasoning token 占比
每个 Reviewer completion token 与结构化结果字符数
invalidToolCallCount
MODEL_PROVIDER_OUTCOME_UNKNOWN / REVIEW_RESULT_RECOVERY_FAILED
同 modelRequestId 重复 Provider 调用次数（目标 0）
recovery 复用次数、gap 帧次数、文件清理延迟
每章总积分、返工次数和最终采用率
```

“单章约 784 积分降至 480–580 积分”仍是待生产验证的工程假设，不能作为实现完成声明。
