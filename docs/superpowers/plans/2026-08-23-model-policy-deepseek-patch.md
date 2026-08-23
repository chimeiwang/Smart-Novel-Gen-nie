# 模型策略、DeepSeek V4 与局部返工 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 DeepSeek V4 按业务场景显式启停 thinking，补齐每次请求的 reasoning/cache Token 明细，并让 Reviewer 的安全局部 patch 不再触发整章模型重写。

**Architecture:** 业务入口创建不可变 `ModelExecutionPolicy`，经 AgentRuntime 进入必填的 `ModelTurnRequest`；DeepSeek profile 使用原始 HTTP JSON transport，generic profile 保留 ChatOpenAI。Reviewer patch 使用严格文本替换和 Core `expectedRevision` CAS 生成新的 ReviewArtifact revision，失败时进入用户确认而不是自动 rewrite。

**Tech Stack:** Python 3.13、Pydantic v2、FastAPI、LangGraph、httpx、SQLAlchemy、PostgreSQL、pytest、Ruff、Mypy、OpenAPI TypeScript 生成客户端

---

## 执行边界

- 实施工作树：`F:\code\inkForge\.worktrees\production-main`。
- 起始分支：`codex/model-policy-review-protocol-design`。
- 权威规格：`docs/specs/2026-08-23-model-policy-deepseek-patch.md`。
- 不实现 crash recovery、Redis fencing、AES-GCM、`outcome_unknown`、Reviewer 问题生命周期、Reviser 工具隔离或通用错误边界重构。
- 不降低 `MODEL_MAX_OUTPUT_TOKENS=384000`。
- 不调用真实模型；Provider 测试只用 fixture 和 mock HTTP transport。
- 不创建或连接本地 PostgreSQL；TokenUsage 迁移只在服务器 dev PostgreSQL 验证。
- 不触碰或提交既有 `.tmp/`。

## 文件职责

- `runtime/model_policy.py`：业务场景到策略的唯一映射。
- `providers/base.py`：Provider 中立的请求、响应、usage 与诊断契约。
- `providers/deepseek_v4.py`：DeepSeek V4 原始 JSON 请求和响应解析。
- `runtime/agent_runtime.py`：唯一多轮工具循环及 `reasoning_content` 回放。
- `billing/**` 与 TokenUsage migration：新 Token 明细的校验、幂等、持久化和查询。
- `artifacts/patch.py`：无副作用的确定性文本 patch。
- `operations/graph.py`：patch/rewrite 路由，不承担 Core 持久化细节。
- `jobs/adapters.py`：ReviewArtifact patch 修订与 Core CAS 适配。

---

### Task 1：建立分场景 ModelExecutionPolicy 并贯穿所有模型入口

**Files:**

- Create: `apps/agent-service/src/inkforge_agents/runtime/model_policy.py`
- Modify: `apps/agent-service/src/inkforge_agents/providers/base.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/agent_runner.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py`
- Modify: `apps/agent-service/src/inkforge_agents/jobs/short_medium.py`
- Modify: `apps/agent-service/src/inkforge_agents/jobs/portrait.py`
- Create: `apps/agent-service/tests/runtime/test_model_policy.py`
- Modify: `apps/agent-service/tests/runtime/test_agent_runner.py`
- Modify: `apps/agent-service/tests/runtime/test_agent_runtime.py`
- Modify: `apps/agent-service/tests/short_medium/test_graph.py`
- Modify: `apps/agent-service/tests/jobs/test_portrait.py`

- [ ] **Step 1: 写策略矩阵和漏传策略失败测试**

```python
def test_reviewer_and_quality_disable_thinking() -> None:
    reviewer = resolve_agent_model_policy("reviewer", "write_chapter")
    quality = resolve_agent_model_policy("quality", None)
    assert (reviewer.thinkingMode, reviewer.reasoningEffort) == ("disabled", None)
    assert reviewer.requiredToolName == "submit_evaluation"
    assert (quality.thinkingMode, quality.reasoningEffort) == ("disabled", None)
    assert quality.requiredToolName == "submit_quality_report"


def test_all_operations_have_exactly_one_policy() -> None:
    assert set(OPERATION_DEFINITIONS) == CREATIVE_OPERATIONS | REPORT_OPERATIONS


def test_model_turn_request_requires_policy() -> None:
    with pytest.raises(ValidationError, match="policy"):
        ModelTurnRequest(messages=[], tools=[], maxOutputTokens=100)
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```powershell
uv run pytest apps/agent-service/tests/runtime/test_model_policy.py apps/agent-service/tests/runtime/test_agent_runner.py apps/agent-service/tests/runtime/test_agent_runtime.py apps/agent-service/tests/short_medium/test_graph.py apps/agent-service/tests/jobs/test_portrait.py -q
```

Expected: FAIL，原因是策略模块不存在且 `ModelTurnRequest` 尚无必填 policy。

- [ ] **Step 3: 实现 Provider 中立策略模型和唯一映射**

在 `providers/base.py` 增加：

```python
class ModelExecutionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    policyId: str = Field(min_length=1)
    thinkingMode: Literal["provider_default", "enabled", "disabled"]
    reasoningEffort: Literal["high", "max"] | None = None
    requiredToolName: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_thinking(self) -> Self:
        if self.thinkingMode == "disabled" and self.reasoningEffort is not None:
            raise ValueError("关闭思考时不能设置推理强度")
        if self.thinkingMode == "enabled" and self.reasoningEffort is None:
            raise ValueError("启用思考时必须设置推理强度")
        return self
```

`ModelTurnRequest.policy` 必填，不提供默认值。

在 `runtime/model_policy.py` 固定：

```python
REPORT_OPERATIONS = frozenset({"answer_question", "review_chapter"})
CREATIVE_OPERATIONS = frozenset(OPERATION_DEFINITIONS) - REPORT_OPERATIONS

CREATIVE_HIGH = ModelExecutionPolicy(
    policyId="v1:creative-high",
    thinkingMode="enabled",
    reasoningEffort="high",
)
REVIEWER_NO_THINKING = ModelExecutionPolicy(
    policyId="v1:reviewer-no-thinking",
    thinkingMode="disabled",
    requiredToolName="submit_evaluation",
)
QUALITY_NO_THINKING = ModelExecutionPolicy(
    policyId="v1:quality-no-thinking",
    thinkingMode="disabled",
    requiredToolName="submit_quality_report",
)
REPORT_NO_THINKING = ModelExecutionPolicy(
    policyId="v1:report-no-thinking",
    thinkingMode="disabled",
)
```

`resolve_agent_model_policy()` 必须按 execution mode 和 operation 显式返回；未知 operation 直接失败。

- [ ] **Step 4: 贯穿 AgentRunner 和两个生产旁路**

`AgentRunner` 解析一次 execution contract 和 policy，验证 `requiredToolName` 同时属于暴露工具与
`terminalControlTools`，再把 policy 传给 `AgentRuntime.run()`。AgentRuntime 每轮构造
`ModelTurnRequest(policy=policy)`。

中短篇固定：大纲/正文/选区替换为 `enabled+high`，`full_check` 为 disabled。文风画像为 disabled。
所有测试中直接构造 ModelTurnRequest 的旧路径显式传 `LEGACY_PROVIDER_DEFAULT`，禁止生产默认回退。

- [ ] **Step 5: 运行测试、Ruff、Mypy 确认 GREEN**

```powershell
uv run pytest apps/agent-service/tests/runtime apps/agent-service/tests/short_medium apps/agent-service/tests/jobs/test_portrait.py -q
uv run ruff check apps/agent-service/src apps/agent-service/tests
uv run mypy apps/agent-service/src
```

Expected: PASS；所有生产调用都显式携带 policy。

- [ ] **Step 6: 提交**

```powershell
git add apps/agent-service/src/inkforge_agents/providers/base.py apps/agent-service/src/inkforge_agents/runtime/model_policy.py apps/agent-service/src/inkforge_agents/runtime/agent_runner.py apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py apps/agent-service/src/inkforge_agents/jobs/short_medium.py apps/agent-service/src/inkforge_agents/jobs/portrait.py apps/agent-service/tests
git commit -m "功能：接入分场景模型思考策略"
```

---

### Task 2：实现 DeepSeek V4 原始 transport 和 reasoning 回放

**Files:**

- Modify: `apps/agent-service/src/inkforge_agents/providers/base.py`
- Create: `apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py`
- Modify: `apps/agent-service/src/inkforge_agents/providers/openai_compatible.py`
- Modify: `apps/agent-service/src/inkforge_agents/providers/fake.py`
- Modify: `apps/agent-service/src/inkforge_agents/providers/selector.py`
- Modify: `apps/agent-service/src/inkforge_agents/config.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/model_runtime.py`
- Modify: `apps/agent-service/src/inkforge_agents/observability/model_observer.py`
- Modify: `apps/agent-service/src/inkforge_agents/observability/human_workflow_log.py`
- Create: `apps/agent-service/tests/providers/fixtures/deepseek_v4/tool_call.json`
- Create: `apps/agent-service/tests/providers/fixtures/deepseek_v4/invalid_tool_call.json`
- Create: `apps/agent-service/tests/providers/fixtures/deepseek_v4/insufficient_resource.json`
- Create: `apps/agent-service/tests/providers/test_deepseek_v4.py`
- Modify: `apps/agent-service/tests/providers/test_provider_config.py`
- Modify: `apps/agent-service/tests/runtime/test_agent_runtime.py`
- Modify: `apps/agent-service/tests/observability/test_model_log_bridge.py`

- [ ] **Step 1: 写最终 HTTP JSON、usage 和多轮回放失败测试**

```python
def deepseek_settings() -> Settings:
    return Settings.model_validate({
        "environment": "test",
        "model_provider": "openai_compatible",
        "openai_compatibility_profile": "deepseek_v4",
        "openai_api_key": "test-key",
        "openai_base_url": "https://api.deepseek.com",
        "openai_model": "deepseek-v4-flash",
    })


def turn_request(policy: ModelExecutionPolicy) -> ModelTurnRequest:
    return ModelTurnRequest(
        messages=[ModelMessage(role="user", content="检查草案")],
        tools=[ModelTool(
            name="submit_evaluation",
            description="提交结论",
            parameters={"type": "object", "properties": {}},
        )],
        maxOutputTokens=384_000,
        policy=policy,
    )


async def test_thinking_request_uses_official_wire_format(http_mock) -> None:
    provider = DeepSeekV4Provider(deepseek_settings(), http_client=http_mock)
    result = await provider.complete_turn(turn_request(CREATIVE_HIGH))
    request = http_mock.requests[0]
    assert str(request.url) == "https://api.deepseek.com/chat/completions"
    assert request.json()["thinking"] == {"type": "enabled"}
    assert request.json()["reasoning_effort"] == "high"
    assert "tool_choice" not in request.json()
    assert result.diagnostics.reasoningTokens == 1200


async def test_disabled_reviewer_forces_single_terminal_tool(http_mock) -> None:
    provider = DeepSeekV4Provider(deepseek_settings(), http_client=http_mock)
    await provider.complete_turn(turn_request(REVIEWER_NO_THINKING))
    assert http_mock.requests[0].json()["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_evaluation"},
    }


async def test_tool_round_replays_reasoning_content() -> None:
    first = turn("", ("call-1", "get_novel_info", {})).model_copy(
        update={"reasoningContent": "保留的工具轮次思考"}
    )
    provider = ScriptedProvider([first, turn("完成")])
    registry = build_default_registry(RecordingGateway())
    runtime = make_agent_runtime(ModelRuntime(provider), registry)
    await runtime.run(
        messages=[{"role": "user", "content": "分析作品"}],
        exposed_tools=registry.for_agent(
            agent_id="设定", capabilities={"novel.read"}
        ),
        context=context(),
        policy=CREATIVE_HIGH,
    )
    assistant = next(
        item for item in provider.requests[1].messages if item.role == "assistant"
    )
    assert assistant.reasoningContent == "保留的工具轮次思考"
```

fixture 的 usage 必须包含 prompt cache hit/miss、completion、total 和 reasoning tokens。

- [ ] **Step 2: 运行 Provider/Runtime 测试确认 RED**

```powershell
uv run pytest apps/agent-service/tests/providers/test_deepseek_v4.py apps/agent-service/tests/providers/test_provider_config.py apps/agent-service/tests/runtime/test_agent_runtime.py apps/agent-service/tests/observability/test_model_log_bridge.py -q
```

Expected: FAIL，原因是 DeepSeek Provider、reasoningContent 和 diagnostics 尚不存在。

- [ ] **Step 3: 扩展中立响应契约**

```python
class ModelUsageDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    promptCacheMissTokens: int | None = Field(default=None, ge=0)
    reasoningTokens: int | None = Field(default=None, ge=0)
    providerUsageKeys: list[str] = Field(default_factory=list)
```

在现有 `ModelMessage` 增加 `reasoningContent: str | None = None`；在现有 `ModelTurnResult` 增加
`reasoningContent: str | None = None`、`providerResponseId: str | None = None` 和
`diagnostics: ModelUsageDiagnostics = Field(default_factory=ModelUsageDiagnostics)`，其他已有字段不改名。

`ModelFinishReason` 增加 `insufficient_system_resource`。AgentRuntime 在执行工具或接受正文前拒绝该原因。

- [ ] **Step 4: 实现 DeepSeekV4Provider**

使用 `httpx.AsyncClient.post("chat/completions", json=payload)`，不启用 Provider 内重试。关键 payload：

```python
payload: dict[str, JsonValue] = {
    "model": self.model_name,
    "messages": serialize_messages(request.messages),
    "max_tokens": request.maxOutputTokens,
}
if request.tools:
    payload["tools"] = serialize_tools(request.tools)
if request.policy.thinkingMode != "provider_default":
    payload["thinking"] = {"type": request.policy.thinkingMode}
if request.policy.reasoningEffort is not None:
    payload["reasoning_effort"] = request.policy.reasoningEffort
if request.policy.thinkingMode == "disabled" and request.policy.requiredToolName:
    payload["tool_choice"] = {
        "type": "function",
        "function": {"name": request.policy.requiredToolName},
    }
```

官方地址 `/v1` 与 `/v1/` 归一到根；自定义代理路径保留；query/fragment 配置失败。工具参数先保存原始字符串，`json.loads()` 后必须是对象，否则在 ToolRegistry 前失败。

- [ ] **Step 5: 选择 profile、回放 reasoning 并记录诊断**

`OPENAI_COMPATIBILITY_PROFILE=generic|deepseek_v4` 必须显式配置。generic 保持 ChatOpenAI，不能根据 URL 猜能力。AgentRuntime 追加 assistant 工具消息时带 `content`、`reasoningContent`、`toolCalls`；日志结构头记录 policy/diagnostics/providerResponseId，但排除 reasoning 正文。

- [ ] **Step 6: 运行同一测试和 Agent Service 回归确认 GREEN**

```powershell
uv run pytest apps/agent-service/tests/providers apps/agent-service/tests/runtime apps/agent-service/tests/observability -q
uv run ruff check apps/agent-service/src apps/agent-service/tests
uv run mypy apps/agent-service/src
```

Expected: PASS；mock transport 证明没有真实网络请求。

- [ ] **Step 7: 提交**

```powershell
git add apps/agent-service/src/inkforge_agents/providers apps/agent-service/src/inkforge_agents/runtime apps/agent-service/src/inkforge_agents/observability apps/agent-service/src/inkforge_agents/config.py apps/agent-service/tests/providers apps/agent-service/tests/runtime apps/agent-service/tests/observability
git commit -m "功能：适配 DeepSeek V4 原始思考协议"
```

---

### Task 3：持久化完整 Token 明细并扩展任务用量 API

**Files:**

- Create: `scripts/migrations/20260823_token_usage_details.sql`
- Modify: `apps/core-api/src/inkforge_core/db/models.py`
- Modify after server dev verification: `apps/core-api/src/inkforge_core/db/schema-contract.json`
- Modify: `apps/core-api/src/inkforge_core/billing/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/billing/repository.py`
- Modify: `apps/core-api/src/inkforge_core/billing/service.py`
- Modify: `apps/agent-service/src/inkforge_agents/clients/core.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/model_runtime.py`
- Modify: `apps/core-api/tests/billing/test_usage_charge.py`
- Modify: `apps/core-api/tests/billing/test_task_usage_api.py`
- Modify: `apps/core-api/tests/db/test_model_metadata.py`
- Regenerate: `packages/api-client/`

- [ ] **Step 1: 写契约、幂等、NULL 汇总和迁移结构失败测试**

```python
def test_report_rejects_inconsistent_deepseek_details() -> None:
    with pytest.raises(ValidationError, match="缓存命中与未命中"):
        ReportModelUsageRequest(
            requestId="request-1",
            taskId="task-1",
            runId="run-1",
            novelId="novel-1",
            grantToken="grant-token",
            promptTokens=100,
            cachedTokens=30,
            promptCacheMissTokens=60,
            completionTokens=50,
            reasoningTokens=20,
            totalTokens=150,
        )


async def test_task_usage_keeps_unknown_details_null(client) -> None:
    response = await client.get("/api/v1/billing/usage/tasks/task-owned")
    assert response.json()["tokenDetailsComplete"] is False
    assert response.json()["reasoningTokens"] is None
    assert response.json()["calls"][0]["visibleCompletionTokens"] is None
```

迁移静态测试必须检查两个 nullable INTEGER、无 default、三个 CHECK 条件、无新索引和可重跑核验块。

- [ ] **Step 2: 运行 Core/Agent 测试确认 RED**

```powershell
uv run pytest apps/core-api/tests/billing/test_usage_charge.py apps/core-api/tests/billing/test_task_usage_api.py apps/core-api/tests/db/test_model_metadata.py apps/agent-service/tests/runtime/test_billing_runtime.py -q
```

Expected: FAIL，新字段、迁移和 API 响应尚不存在。

- [ ] **Step 3: 实现迁移与 Core 双重校验**

迁移核心必须是：

```sql
ALTER TABLE "TokenUsage" ADD COLUMN IF NOT EXISTS "promptCacheMissTokens" INTEGER;
ALTER TABLE "TokenUsage" ADD COLUMN IF NOT EXISTS "reasoningTokens" INTEGER;
```

并通过幂等 DO 块创建、验证：非负、cache hit + miss = prompt、reasoning <= completion。旧行不更新。

`ReportModelUsageRequest` 增加两个 nullable StrictInt，并执行同样关系校验。`_same_usage()` 和冲突恢复必须比较新字段；计费金额仍使用现有四项。

- [ ] **Step 4: 扩展逐请求与汇总 API**

```python
class TaskModelUsageCall(BillingSchema):
    # 现有字段保持不变
    promptCacheMissTokens: int | None
    reasoningTokens: int | None
    visibleCompletionTokens: int | None
    tokenDetailsComplete: bool
```

两个字段都非空时逐请求 complete=true 并派生 visible；否则全部派生明细保持 NULL/false。任务汇总只有所有 call 完整时才求和，空任务为 NULL/false。

- [ ] **Step 5: 将 DeepSeek 诊断上报 Core**

`CoreClient.report_usage()` 和 `ModelRuntime` 传递两个可选值；reasoning token 不叠加到 completion/total 或积分金额。

- [ ] **Step 6: 在服务器 dev PostgreSQL 验证迁移并更新结构指纹**

先备份 dev 数据库，再使用现有受控迁移入口执行 `20260823_token_usage_details.sql`，导出新的只读
`schema-contract.json`。本地不创建数据库、不执行 DDL。若 dev 验证不可用，本 Task 标记 BLOCKED，不得手写伪造结构指纹。

- [ ] **Step 7: 生成公共客户端并完成验证**

```powershell
npm run api:generate
npm run api:check
npm run typecheck
uv run pytest apps/core-api/tests/billing apps/core-api/tests/db/test_model_metadata.py apps/agent-service/tests/runtime/test_billing_runtime.py -q
uv run ruff check apps/core-api/src apps/core-api/tests apps/agent-service/src apps/agent-service/tests
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src
```

Expected: PASS；旧行 NULL，完整新行可按 taskId/runId/requestId 查询。

- [ ] **Step 8: 提交**

```powershell
git add scripts/migrations/20260823_token_usage_details.sql apps/core-api/src/inkforge_core/db apps/core-api/src/inkforge_core/billing apps/core-api/tests/billing apps/core-api/tests/db/test_model_metadata.py apps/agent-service/src/inkforge_agents/clients/core.py apps/agent-service/src/inkforge_agents/runtime/model_runtime.py apps/agent-service/tests/runtime/test_billing_runtime.py packages/api-client
git commit -m "功能：记录模型请求完整 Token 明细"
```

---

### Task 4：严格化 Reviewer patch 契约和确定性文本替换

**Files:**

- Modify: `apps/agent-service/src/inkforge_agents/tools/control.py`
- Modify: `apps/agent-service/src/inkforge_agents/artifacts/patch.py`
- Modify: `apps/agent-service/src/inkforge_agents/operations/graph.py`
- Modify: `apps/agent-service/tests/tools/test_arguments.py`
- Create: `apps/agent-service/tests/artifacts/test_patch.py`
- Modify: `apps/agent-service/tests/operations/test_review_routing.py`

- [ ] **Step 1: 写严格组合与 patch 合并失败测试**

```python
def test_patch_revision_requires_non_empty_strict_patches() -> None:
    with pytest.raises(ValidationError):
        EvaluationArgs(verdict="revise", summary="错字", revisionMode="patch")


def test_patch_only_reviews_remain_patch() -> None:
    outcome = decide_review_outcome([
        ReviewResult(
            reviewer="编辑",
            verdict="revise",
            summary="错字",
            revisionMode="patch",
            patches=[{"kind": "text_replace", "find": "甲", "replace": "乙"}],
        )
    ])
    assert outcome.revisionMode == "patch"


def test_overlapping_patches_are_rejected_atomically() -> None:
    with pytest.raises(PatchApplicationError, match="PATCH_OVERLAP"):
        apply_text_patches("甲乙丙", [
            TextReplacePatch(kind="text_replace", find="甲乙", replace="丁"),
            TextReplacePatch(kind="text_replace", find="乙丙", replace="戊"),
        ])
```

- [ ] **Step 2: 运行测试确认 RED**

```powershell
uv run pytest apps/agent-service/tests/tools/test_arguments.py apps/agent-service/tests/artifacts/test_patch.py apps/agent-service/tests/operations/test_review_routing.py -q
```

Expected: FAIL，现有 patch 为松散 dict，且 outcome 强制 rewrite。

- [ ] **Step 3: 实现严格 TextReplacePatch 和 evaluation validator**

```python
class TextReplacePatch(StrictArgs):
    kind: Literal["text_replace"]
    find: str = Field(min_length=1)
    replace: str
```

组合固定：pass/block 不带 revision 字段；revise+patch 必须 1..20 个 patch；revise+rewrite 不带 patches；非章节文本的 patch 在图路由拒绝。

- [ ] **Step 4: 原文定位后倒序原子应用**

`apply_text_patches()` 先在原 content 中为每个 find 找唯一位置，验证范围不重叠，再按起点倒序替换。
错误码只允许 `PATCH_TARGET_NOT_FOUND`、`PATCH_TARGET_AMBIGUOUS`、`PATCH_OVERLAP`、
`PATCH_ARTIFACT_UNSUPPORTED`，错误不包含正文。

- [ ] **Step 5: 修改 outcome 优先级并验证 GREEN**

`decide_review_outcome()` 固定 `block > rewrite > patch > pass`；Reviewer 顺序使用 Operation 定义顺序，不能依赖 Send 返回顺序。

```powershell
uv run pytest apps/agent-service/tests/tools/test_arguments.py apps/agent-service/tests/artifacts/test_patch.py apps/agent-service/tests/operations/test_review_routing.py -q
uv run ruff check apps/agent-service/src apps/agent-service/tests
uv run mypy apps/agent-service/src
```

- [ ] **Step 6: 提交**

```powershell
git add apps/agent-service/src/inkforge_agents/tools/control.py apps/agent-service/src/inkforge_agents/artifacts/patch.py apps/agent-service/src/inkforge_agents/operations/graph.py apps/agent-service/tests/tools/test_arguments.py apps/agent-service/tests/artifacts/test_patch.py apps/agent-service/tests/operations/test_review_routing.py
git commit -m "功能：保留 Reviewer 安全局部修改意图"
```

---

### Task 5：接入 patch 图节点和 Core expectedRevision CAS

**Files:**

- Modify: `apps/core-api/src/inkforge_core/reviews/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/repository.py`
- Modify: `apps/agent-service/src/inkforge_agents/clients/core.py`
- Modify: `apps/agent-service/src/inkforge_agents/operations/graph.py`
- Modify: `apps/agent-service/src/inkforge_agents/graph/state.py`
- Modify: `apps/agent-service/src/inkforge_agents/jobs/adapters.py`
- Modify: `apps/core-api/tests/reviews/test_artifact_lifecycle.py`
- Modify: `apps/core-api/tests/reviews/test_internal_job_identity.py`
- Modify: `apps/agent-service/tests/graph/test_operation_graph.py`
- Modify: `apps/agent-service/tests/jobs/test_adapters.py`

- [ ] **Step 1: 写 CAS、零模型调用和失败收敛测试**

```python
async def test_expected_revision_conflict_does_not_create_revision(repository) -> None:
    request = CreateArtifactRequest(
        runId="run-1",
        taskId="task-1",
        novelId="novel-1",
        jobId="job-1",
        chapterId="chapter-1",
        artifactKey="task-1:write_chapter",
        kind="chapter_draft",
        status="under_review",
        payload={"kind": "chapter_draft", "content": "修订正文"},
        createdByAgent="写作",
        expectedRevision=1,
    )
    with pytest.raises(ApiError) as error:
        await repository.create_or_revise("user-1", request)
    assert error.value.code == "ARTIFACT_REVISION_CONFLICT"
    assert (await repository.get_response("user-1", "artifact-1")).revision == 2


async def test_patch_path_does_not_call_reviser() -> None:
    executor = PatchReviewExecutor(patch_find="旧句", patch_replace="新句")
    artifacts = ArtifactPort()
    graph = build_operation_graph(
        OperationDependencies(agentExecutor=executor, artifacts=artifacts)
    )
    result = await graph.ainvoke(_explicit_write_state())
    assert executor.reviser_calls == 0
    assert "patch" in artifacts.actions
    assert result["artifactIteration"] == 1


async def test_ambiguous_patch_waits_for_user_without_rewrite() -> None:
    executor = PatchReviewExecutor(patch_find="重复", patch_replace="新句")
    artifacts = ArtifactPort(initial_content="重复。重复。")
    graph = build_operation_graph(
        OperationDependencies(agentExecutor=executor, artifacts=artifacts)
    )
    result = await graph.ainvoke(_explicit_write_state())
    assert executor.reviser_calls == 0
    assert result["patchFailureCode"] == "PATCH_TARGET_AMBIGUOUS"
    assert result["phase"] == "waiting_user"
```

在同一测试文件新增 `PatchReviewExecutor`：primary 返回章节草案，两个 Reviewer 返回相同的严格
patch evaluation，若收到 `execution_mode="reviser"` 就递增 `reviser_calls` 并使测试失败。扩展现有
`ArtifactPort` 支持可配置 `initial_content` 和 `patch()`，每次调用把 `"patch"` 追加到 actions。

- [ ] **Step 2: 运行 Core/Graph 测试确认 RED**

```powershell
uv run pytest apps/core-api/tests/reviews/test_artifact_lifecycle.py apps/core-api/tests/reviews/test_internal_job_identity.py apps/agent-service/tests/graph/test_operation_graph.py apps/agent-service/tests/jobs/test_adapters.py -q
```

Expected: FAIL，内部请求没有 expectedRevision，图没有 patch 节点。

- [ ] **Step 3: 增加内部 expectedRevision CAS**

`CreateArtifactRequest.expectedRevision: int | None = Field(default=None, ge=1)`。创建新 Artifact 时必须为空；
修订请求携带时，Core 在现有任务锁和 Artifact 行锁内要求 `existing.revision == expectedRevision`，否则返回
409 `ARTIFACT_REVISION_CONFLICT`，不写 payload、不创建 Revision。

- [ ] **Step 4: 扩展 ArtifactPort 并实现 patch adapter**

```python
class ArtifactPort(Protocol):
    async def patch(
        self,
        state: dict[str, Any],
        artifact_id: str,
        patches: list[TextReplacePatch],
    ) -> str:
        raise NotImplementedError
```

CoreArtifactPort 从本地权威 record 读取 chapter_text payload 和 revision，确定性计算新 content，克隆同一
artifactKey/kind/身份，调用 Core 时带 `expectedRevision=record.revision`。Core 成功后才更新本地 record。

- [ ] **Step 5: 增加 applyArtifactPatch 图节点**

patch outcome 路由到新节点；成功后递增 `artifactIteration` 并重新进入 reviewArtifact，不调用 Reviser。
失败设置固定 `patchFailureCode`、脱敏 message、`artifactStatus=blocked`、`pendingRevision=None`，然后进入
markArtifactAwaitingUser。`ARTIFACT_REVISION_CONFLICT` 同样禁止降级 rewrite。

- [ ] **Step 6: 运行同一测试与相关回归确认 GREEN**

```powershell
uv run pytest apps/core-api/tests/reviews apps/agent-service/tests/graph apps/agent-service/tests/jobs/test_adapters.py apps/agent-service/tests/operations -q
uv run ruff check apps/core-api/src apps/core-api/tests apps/agent-service/src apps/agent-service/tests
uv run mypy apps/core-api/src apps/agent-service/src
```

- [ ] **Step 7: 提交**

```powershell
git add apps/core-api/src/inkforge_core/reviews apps/core-api/tests/reviews apps/agent-service/src/inkforge_agents/clients/core.py apps/agent-service/src/inkforge_agents/operations/graph.py apps/agent-service/src/inkforge_agents/graph/state.py apps/agent-service/src/inkforge_agents/jobs/adapters.py apps/agent-service/tests/graph apps/agent-service/tests/jobs/test_adapters.py
git commit -m "功能：局部修订草案并校验修订版本"
```

---

### Task 6：同步当前文档、部署配置并完成全量验证

**Files:**

- Modify: `infra/compose.yaml`
- Modify: `.env.example`
- Modify: `.env.local.example`
- Modify: `apps/agent-service/AGENTS.md`
- Modify: `docs/requirements/03-ai-writing-and-agents.md`
- Modify: `docs/requirements/04-review-quality-and-workflow.md`
- Modify: `docs/requirements/05-auth-billing-and-ops.md`
- Modify: `DOCS.md`
- Modify: `docs/specs/2026-08-23-model-policy-deepseek-patch.md`
- Modify: relevant architecture and OpenAPI tests

- [ ] **Step 1: 配置显式 DeepSeek profile**

生产 Compose 设置：

```yaml
OPENAI_COMPATIBILITY_PROFILE: ${OPENAI_COMPATIBILITY_PROFILE:-deepseek_v4}
OPENAI_BASE_URL: ${OPENAI_BASE_URL:-https://api.deepseek.com}
```

示例环境文件说明 generic/deepseek_v4 边界，不记录密钥。

- [ ] **Step 2: 只把已通过测试的行为写成当前事实**

更新 Agent 架构与 03/04/05：分场景 thinking、DeepSeek reasoning 仅内存回放、Token 明细查询、patch 不调用 Reviser、patch 失败进入用户确认。删除“所有 revise 强制 rewrite”的当前要求。`DOCS.md` 记录用户批准的
`20260823_token_usage_details.sql` 是仅限两个 nullable TokenUsage 字段的迁移例外。

- [ ] **Step 3: 运行完整 Python、API 和架构验证**

```powershell
uv run pytest
uv run ruff check .
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
npm run api:check
npm run typecheck
npm run lint
uv run pytest tests/architecture/test_compose_security.py tests/architecture/test_openapi_generation.py apps/core-api/tests/db/test_schema_guard.py -q
```

Expected: PASS；不调用真实模型，不连接本地数据库。

- [ ] **Step 4: 运行 mock 端到端验收**

使用 fake/mock Provider 验证：

```text
creative request -> thinking enabled/high
reviewer request -> thinking disabled + submit_evaluation
tool turn -> reasoning_content 原样回传
usage report -> taskId/runId/requestId + cache miss/reasoning
patch-only review -> Provider 调用次数 0 -> 新 Artifact revision -> 再复审
ambiguous patch -> waiting_user -> Reviser 调用次数 0
```

- [ ] **Step 5: 提交**

```powershell
git add infra/compose.yaml .env.example .env.local.example apps/agent-service/AGENTS.md docs/requirements DOCS.md docs/specs/2026-08-23-model-policy-deepseek-patch.md tests/architecture
git commit -m "文档：同步模型策略与局部返工事实"
```

---

## 完成门禁

- 六个 Task 均有独立 RED/GREEN 证据和中文提交。
- 每个 Task 完成后先规格审查，再代码质量审查；Critical/Important 清零后才能继续。
- Server dev 数据库迁移与 schema contract 是 Task 3 的硬门禁，不能用本地临时数据库替代。
- 最终报告分别列出：代码验证、dev 数据库验证、生成客户端、部署准备、生产效果待验证。
- “降低了多少 Token”只能在生产新 taskId/runId 数据出现后分析，不能由 mock 测试推断。
