# DeepSeek 一致性终检 strict 工具最小修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 只让一致性终检的 `submit_quality_report` 使用真实 DeepSeek Beta strict Function Calling，并保留本地完整质量报告校验与安全失败分类。

**Architecture:** 在工具定义层增加默认关闭的 `strict` 元数据，只为质量报告工具开启；`DeepSeekV4Provider` 遇到全 strict 工具集合时切换 Beta 端点并发送供应商兼容 Schema 投影。普通工具链保持标准端点，质量结果仍由原始 Pydantic 契约复验，日志只提取异常中已有的安全大写错误码。

**Tech Stack:** Python 3.12、Pydantic v2、httpx、pytest、Ruff、Mypy

---

### Task 1: 工具 strict 元数据

**Files:**
- Modify: `apps/agent-service/src/inkforge_agents/tools/registry.py:39-61`
- Modify: `apps/agent-service/src/inkforge_agents/tools/control.py:326-334`
- Test: `apps/agent-service/tests/tools/test_registry.py`
- Test: `apps/agent-service/tests/tools/test_arguments.py`

- [ ] **Step 1: 写入失败测试**

在工具注册测试中断言普通工具仍为非 strict；在参数测试中断言默认注册表内只有质量报告工具为 strict：

```python
def test_model_tool_defaults_to_non_strict() -> None:
    tool = restricted_tool().as_model_tool()
    assert tool.strict is False


def test_only_quality_report_control_tool_is_strict() -> None:
    registry = build_default_registry()
    strict_names = {tool.name for tool in registry.all() if tool.as_model_tool().strict}
    assert strict_names == {"submit_quality_report"}
```

- [ ] **Step 2: 验证 RED**

Run:

```powershell
uv run pytest apps/agent-service/tests/tools/test_registry.py apps/agent-service/tests/tools/test_arguments.py -q
```

Expected: `submit_quality_report` 的 strict 集合断言失败。

- [ ] **Step 3: 最小实现**

给 `ToolDefinition` 增加默认关闭的字段并透传：

```python
@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    argumentsModel: type[BaseModel]
    permission: ToolPermission
    toolKind: ToolKind
    strict: bool = False
    handler: ToolHandler | None = None

    def as_model_tool(self) -> ModelTool:
        schema = self.argumentsModel.model_json_schema()
        schema.pop("title", None)
        return ModelTool(
            name=self.name,
            description=self.description,
            parameters=schema,
            strict=self.strict,
        )
```

在 `control_tools()` 的构造表达式中只标记质量工具：

```python
ToolDefinition(
    name=name,
    description=description,
    argumentsModel=model,
    permission=control_permission(capability, agent_ids),
    toolKind="control",
    strict=name == "submit_quality_report",
)
```

- [ ] **Step 4: 验证 GREEN**

Run:

```powershell
uv run pytest apps/agent-service/tests/tools/test_registry.py apps/agent-service/tests/tools/test_arguments.py -q
```

Expected: 全部通过。

### Task 2: DeepSeek Beta strict wire 与 Schema 投影

**Files:**
- Modify: `apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py:24-108`
- Test: `apps/agent-service/tests/providers/test_deepseek_v4.py`

- [ ] **Step 1: 写入端点与 wire 失败测试**

扩展测试 helper 允许设置 `ModelTool.strict` 和与策略一致的工具名：

```python
def _request(
    *,
    policy: Any = LEGACY_PROVIDER_DEFAULT,
    tool_name: str = "lookup",
    strict: bool = False,
) -> ModelTurnRequest:
    return ModelTurnRequest(
        messages=[{"role": "user", "content": "请调用工具"}],
        tools=[{
            "name": tool_name,
            "description": "提交结构化结果",
            "parameters": {"type": "object", "properties": {}},
            "strict": strict,
        }],
        maxOutputTokens=256,
        policy=policy,
    )
```

随后新增以下行为测试：

```python
@pytest.mark.asyncio
async def test_strict_tool_uses_beta_endpoint_and_strict_wire() -> None:
    provider, requests, client = _provider()
    request = _request(
        policy=QUALITY_NO_THINKING,
        tool_name="submit_quality_report",
        strict=True,
    )
    try:
        await provider.complete_turn(request)
    finally:
        await client.aclose()
    payload = json.loads(requests[0].content)
    assert str(requests[0].url) == "https://api.deepseek.com/beta/chat/completions"
    assert payload["tools"][0]["function"]["strict"] is True
    assert payload["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_quality_report"},
    }


@pytest.mark.asyncio
async def test_mixed_strict_tools_fail_before_http() -> None:
    provider, requests, client = _provider()
    request = _request(
        policy=QUALITY_NO_THINKING,
        tool_name="submit_quality_report",
        strict=True,
    ).model_copy(
        update={"tools": [
            _request(strict=True).tools[0],
            _request(strict=False).tools[0].model_copy(update={"name": "plain"}),
        ]}
    )
    try:
        with pytest.raises(ValueError, match="不能混用"):
            await provider.complete_turn(request)
    finally:
        await client.aclose()
    assert requests == []


@pytest.mark.asyncio
async def test_custom_endpoint_requires_explicit_strict_base_url() -> None:
    provider, requests, client = _provider("https://proxy.example/v1")
    try:
        with pytest.raises(ValueError, match="OPENAI_STRICT_BASE_URL"):
            await provider.complete_turn(_request(
                policy=QUALITY_NO_THINKING,
                tool_name="submit_quality_report",
                strict=True,
            ))
    finally:
        await client.aclose()
    assert requests == []
```

- [ ] **Step 2: 写入 Schema 投影失败测试**

使用真实 `QualityReportArgs` Schema 证明 Provider wire 不发送不兼容关键词，并把全部对象属性提升为 required：

```python
def test_quality_schema_projects_to_deepseek_strict_subset() -> None:
    source = QualityReportArgs.model_json_schema()
    projected = _project_deepseek_strict_schema(source)
    encoded = json.dumps(projected, ensure_ascii=False)
    for keyword in ("minLength", "maxLength", "minItems", "maxItems", "title", "default"):
        assert f'"{keyword}"' not in encoded
    assert projected["required"] == list(projected["properties"])
    assert projected["additionalProperties"] is False
    issue = projected["$defs"]["ConsistencyIssue"]
    assert issue["required"] == list(issue["properties"])
    assert issue["additionalProperties"] is False
```

- [ ] **Step 3: 验证 RED**

Run:

```powershell
uv run pytest apps/agent-service/tests/providers/test_deepseek_v4.py -q
```

Expected: Beta 端点、strict wire、混用拒绝或投影函数相关断言失败。

- [ ] **Step 4: 实现 strict 端点选择**

复用现有 strict 地址解析，并在 Provider 初始化时保存可选 Beta endpoint：

```python
from .openai_compatible import _resolve_deepseek_strict_base_url, normalize_finish_reason

strict_base_url = _resolve_deepseek_strict_base_url(settings)
self._strict_endpoint = (
    _completion_endpoint(strict_base_url) if strict_base_url is not None else None
)
```

在 `complete_turn()` 组装 payload 前确定请求模式：

```python
strict_tool_count = sum(tool.strict for tool in request.tools)
if 0 < strict_tool_count < len(request.tools):
    raise ValueError("DeepSeek 工具请求不能混用 strict 与非 strict 函数")
use_strict = strict_tool_count > 0
if use_strict and self._strict_endpoint is None:
    raise ValueError("DeepSeek strict 工具请求缺少 OPENAI_STRICT_BASE_URL")
endpoint = self._strict_endpoint if use_strict else self._endpoint
```

- [ ] **Step 5: 实现 strict Schema 投影与 wire**

在 `deepseek_v4.py` 中加入独立纯函数和白名单，递归投影 Schema，并为对象强制全部字段 required：

```python
_DEEPSEEK_STRICT_SCHEMA_KEYWORDS = frozenset({
    "type", "properties", "required", "additionalProperties", "enum", "const",
    "anyOf", "items", "$ref", "$defs", "description", "pattern", "format",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
})


def _project_deepseek_strict_schema(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    projected: dict[str, Any] = {}
    for key, child in value.items():
        if key not in _DEEPSEEK_STRICT_SCHEMA_KEYWORDS:
            continue
        if key in {"properties", "$defs"} and isinstance(child, Mapping):
            projected[key] = {
                str(name): _project_deepseek_strict_schema(schema)
                for name, schema in child.items()
            }
        elif key == "anyOf" and isinstance(child, list):
            projected[key] = [_project_deepseek_strict_schema(item) for item in child]
        elif key in {"items", "additionalProperties"} and isinstance(child, Mapping):
            projected[key] = _project_deepseek_strict_schema(child)
        else:
            projected[key] = child
    properties = projected.get("properties")
    if projected.get("type") == "object" and isinstance(properties, dict):
        projected["required"] = list(properties)
        projected["additionalProperties"] = False
    return projected
```

工具 wire 在 strict 模式下使用投影并发送标记，普通模式保持原样：

```python
"parameters": (
    _project_deepseek_strict_schema(tool.parameters)
    if use_strict
    else tool.parameters
),
**({"strict": True} if use_strict else {}),
```

- [ ] **Step 6: 验证 GREEN 与普通路径回归**

Run:

```powershell
uv run pytest apps/agent-service/tests/providers/test_deepseek_v4.py -q
```

Expected: 全部通过，现有标准端点测试不变。

### Task 3: 质量失败安全错误码

**Files:**
- Modify: `apps/agent-service/src/inkforge_agents/jobs/quality.py:174-203`
- Test: `apps/agent-service/tests/jobs/test_quality.py`

- [ ] **Step 1: 写入失败测试**

```python
def test_safe_failure_code_extracts_runtime_protocol_prefix() -> None:
    error = RuntimeError("MODEL_TOOL_ARGUMENTS_INVALID：不能进入日志的工具参数")
    assert _safe_failure_code(error) == "MODEL_TOOL_ARGUMENTS_INVALID"


def test_safe_failure_code_does_not_expose_arbitrary_runtime_message() -> None:
    error = RuntimeError("不能进入日志的秘密")
    assert _safe_failure_code(error) == "RuntimeError"
```

- [ ] **Step 2: 验证 RED**

Run:

```powershell
uv run pytest apps/agent-service/tests/jobs/test_quality.py -q
```

Expected: 第一个测试得到 `RuntimeError` 而失败。

- [ ] **Step 3: 最小实现**

只检查异常第一个字符串参数的安全前缀，不调用或记录完整 `str(error)`：

```python
def _safe_failure_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code):
        return code
    first_argument = error.args[0] if error.args else None
    if isinstance(first_argument, str):
        match = re.match(r"^([A-Z][A-Z0-9_]{0,63})：", first_argument)
        if match is not None:
            return match.group(1)
    value = type(error).__name__
    return value if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", value) else "UnknownError"
```

- [ ] **Step 4: 验证 GREEN**

Run:

```powershell
uv run pytest apps/agent-service/tests/jobs/test_quality.py -q
```

Expected: 全部通过。

### Task 4: 当前架构文档与完整验证

**Files:**
- Modify: `apps/agent-service/AGENTS.md`
- Modify: `docs/requirements/03-ai-writing-and-agents.md`
- Modify: `docs/requirements/04-review-quality-and-workflow.md`

- [ ] **Step 1: 同步当前事实**

三处文档明确记录：只有一致性终检质量工具进入 DeepSeek Beta strict；其他 Agent 工具、Reviewer 和视频路由不变；strict wire 仍须通过原始 Pydantic 契约复验，且失败不自动回退普通协议。

- [ ] **Step 2: 运行定向测试**

Run:

```powershell
uv run pytest apps/agent-service/tests/providers/test_deepseek_v4.py apps/agent-service/tests/tools/test_registry.py apps/agent-service/tests/tools/test_arguments.py apps/agent-service/tests/jobs/test_quality.py apps/agent-service/tests/runtime/test_agent_runtime.py apps/agent-service/tests/runtime/test_billing_runtime.py -q
```

Expected: 全部通过。

- [ ] **Step 3: 运行 Agent Service 全量测试与静态检查**

Run:

```powershell
uv run pytest apps/agent-service/tests -q
uv run ruff check apps/agent-service/src apps/agent-service/tests
uv run mypy apps/agent-service/src packages/service-contracts/src
```

Expected: 三条命令退出码均为 0。

- [ ] **Step 4: 检查最终差异**

Run:

```powershell
git diff --check
git status --short
git diff --stat origin/main...HEAD
```

Expected: 无空白错误；仅包含本规格、计划、Agent strict 最小修复、测试和同步文档。

- [ ] **Step 5: 提交实现**

```powershell
git add -- apps/agent-service/src apps/agent-service/tests apps/agent-service/AGENTS.md docs/requirements/03-ai-writing-and-agents.md docs/requirements/04-review-quality-and-workflow.md docs/plans/2026-08-29-deepseek-quality-strict-tool-hotfix.md
git commit -m "修复：为一致性终检启用 DeepSeek strict"
```

提交后不得直接重跑生产质量检查；生产发布与重跑仍需分别取得授权并按不可变镜像验证。
