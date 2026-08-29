# DeepSeek 一致性终检 strict 工具修复与生产收敛实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让一致性终检使用与 DeepSeek strict 方言一致的专用 wire 契约，并在本地完整校验失败时留下不含字段值的可定位诊断。

**Architecture:** 第一阶段已在提交 `e672666` 接通质量工具的 Beta strict wire。第二阶段只为 `submit_quality_report` 内联 Pydantic 引用、移除未明确支持的 `null` 并精确归一化两个可选字符串；AgentRuntime 仍用原始 Pydantic 契约复验，并把字段路径与错误类型作为脱敏诊断交给质量日志。普通工具、其他 Agent、Core 和数据库不变。

**Tech Stack:** Python 3.12、Pydantic v2、httpx、pytest、Ruff、Mypy

---

> Task 1～4 已由提交 `e672666` 完成并部署。以下 Task 5～7 是生产重跑暴露出的第二阶段收敛工作；旧步骤保留为第一阶段审计记录。

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

### Task 5: 专用 DeepSeek 质量 wire 契约

**Files:**
- Modify: `apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py`
- Test: `apps/agent-service/tests/providers/test_deepseek_v4.py`

- [ ] **Step 1: 写入生产失配回归测试**

新增测试直接使用真实 `QualityReportArgs.model_json_schema()`，要求质量 wire：

```python
def test_quality_wire_inlines_pydantic_refs_and_avoids_null() -> None:
    projected = _project_deepseek_quality_schema(QualityReportArgs.model_json_schema())
    encoded = json.dumps(projected, ensure_ascii=False)

    assert '"$defs"' not in encoded
    assert '"$def"' not in encoded
    assert '"$ref"' not in encoded
    assert '"null"' not in encoded
    assert projected["properties"]["scores"]["type"] == "object"
    assert projected["properties"]["issues"]["items"]["type"] == "object"
    assert projected["properties"]["rewriteBrief"]["type"] == "string"
```

同时覆盖返回归一化：

```python
def test_quality_wire_normalizes_only_optional_empty_strings() -> None:
    normalized = _normalize_deepseek_quality_arguments(
        {
            "scores": _valid_scores(),
            "qualityGate": "pass",
            "issues": [{
                "dimension": "causality",
                "severity": "warning",
                "message": "完整消息",
                "evidence": "完整证据",
                "location": "",
                "suggestion": "完整建议",
            }],
            "report": "完整报告",
            "rewriteBrief": "",
        }
    )

    assert normalized["issues"][0]["location"] is None
    assert normalized["rewriteBrief"] is None
    assert normalized["report"] == "完整报告"
```

- [ ] **Step 2: 运行 RED**

Run:

```powershell
uv run pytest apps/agent-service/tests/providers/test_deepseek_v4.py -q
```

Expected: 因 `_project_deepseek_quality_schema` 和归一化函数尚不存在而失败；不得修改断言迎合旧通用投影。

- [ ] **Step 3: 实现专用投影与归一化**

在 `deepseek_v4.py` 中：

```python
_QUALITY_TOOL_NAME = "submit_quality_report"


def _project_deepseek_quality_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    definitions = schema.get("$defs")
    if not isinstance(definitions, Mapping):
        raise ValueError("质量报告 Schema 缺少 $defs")
    inlined = _inline_quality_schema_node(schema, definitions, stack=())
    projected = _project_deepseek_quality_node(inlined)
    _apply_quality_wire_descriptions(projected)
    return projected


def _normalize_deepseek_quality_arguments(arguments: Mapping[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(dict(arguments))
    if normalized.get("rewriteBrief") == "":
        normalized["rewriteBrief"] = None
    issues = normalized.get("issues")
    if isinstance(issues, list):
        for issue in issues:
            if isinstance(issue, dict) and issue.get("location") == "":
                issue["location"] = None
    return normalized
```

内联函数只接受 `#/$defs/<name>` 本地引用并防止循环；投影函数把 `string|null` 精确收敛为 `string`，其他
`anyOf` 原样递归。`complete_turn()` 仅在唯一 strict 工具名为 `submit_quality_report` 时使用该 Schema，并在
`_parse_response()` 后对同名调用执行归一化；其他 strict 工具在 HTTP 前抛出稳定错误。

- [ ] **Step 4: 运行 GREEN 与 Provider 回归**

Run:

```powershell
uv run pytest apps/agent-service/tests/providers/test_deepseek_v4.py -q
```

Expected: 全部通过；普通非 strict 请求仍使用标准端点和原始 Schema。

- [ ] **Step 5: 提交 wire 收敛**

```powershell
git add -- apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py apps/agent-service/tests/providers/test_deepseek_v4.py
git commit -m "修复：收敛 DeepSeek 质量 strict 契约"
```

### Task 6: Pydantic 字段级脱敏诊断

**Files:**
- Modify: `apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py`
- Modify: `apps/agent-service/src/inkforge_agents/jobs/quality.py`
- Test: `apps/agent-service/tests/runtime/test_agent_runtime.py`
- Test: `apps/agent-service/tests/jobs/test_quality.py`

- [ ] **Step 1: 写入 RED 测试**

构造包含秘密字段值的非法质量参数，断言异常只暴露路径和错误类型：

```python
with pytest.raises(ModelToolArgumentsInvalidError) as caught:
    runtime._preflight_response(response, exposed, context, terminal_tools)

assert caught.value.code == "MODEL_TOOL_ARGUMENTS_INVALID"
assert "issues.0.message:string_too_long" in caught.value.validationIssues
assert "不能进入日志的秘密" not in str(caught.value)
```

质量日志测试使用 `caplog` 断言：

```python
assert "failure_code=MODEL_TOOL_ARGUMENTS_INVALID" in caplog.text
assert "validation_issues=issues.0.message:string_too_long" in caplog.text
assert "不能进入日志的秘密" not in caplog.text
```

- [ ] **Step 2: 运行 RED**

Run:

```powershell
uv run pytest apps/agent-service/tests/runtime/test_agent_runtime.py apps/agent-service/tests/jobs/test_quality.py -q
```

Expected: 专用异常和 `validation_issues` 日志尚不存在而失败。

- [ ] **Step 3: 实现安全异常与日志投影**

新增 `ModelToolArgumentsInvalidError(RuntimeError)`，只持有 `code`、安全工具名和最多 10 条
`field.path:error_type`。从 `ValidationError.errors(include_url=False, include_context=False,
include_input=False)` 读取 `loc/type`，所有片段经过字符白名单和长度限制。质量日志只读取该属性：

```python
validation_issues = getattr(error, "validationIssues", ())
safe_issues = ",".join(validation_issues) if validation_issues else "none"
logger.warning(
    "质量检查任务失败 ... failure_code=%s exception_type=%s retryable=%s "
    "validation_issues=%s",
    ...,
    safe_issues,
)
```

不得把 `str(ValidationError)`、`input`、`ctx`、工具参数或章节内容写入异常和日志。

- [ ] **Step 4: 运行 GREEN**

Run:

```powershell
uv run pytest apps/agent-service/tests/runtime/test_agent_runtime.py apps/agent-service/tests/jobs/test_quality.py -q
```

Expected: 全部通过，秘密字段值不出现在异常或日志。

- [ ] **Step 5: 提交诊断收敛**

```powershell
git add -- apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py apps/agent-service/src/inkforge_agents/jobs/quality.py apps/agent-service/tests/runtime/test_agent_runtime.py apps/agent-service/tests/jobs/test_quality.py
git commit -m "日志：记录质量参数脱敏校验路径"
```

### Task 7: 文档同步与完整验证

**Files:**
- Modify: `apps/agent-service/AGENTS.md`
- Modify: `docs/requirements/03-ai-writing-and-agents.md`
- Modify: `docs/requirements/04-review-quality-and-workflow.md`
- Modify: `docs/specs/2026-08-29-deepseek-quality-strict-tool-hotfix.md`
- Modify: `docs/plans/2026-08-29-deepseek-quality-strict-tool-hotfix.md`

- [ ] **Step 1: 同步当前事实**

三处架构/需求文档明确记录：质量 strict 使用专用内联 wire 契约；两个可选字符串通过空字符串传输并在
Provider 内精确归一化；本地完整 Pydantic 校验仍为权威；失败日志只记录字段路径和错误类型。

- [ ] **Step 2: 运行定向测试**

Run:

```powershell
uv run pytest apps/agent-service/tests/providers/test_deepseek_v4.py apps/agent-service/tests/runtime/test_agent_runtime.py apps/agent-service/tests/jobs/test_quality.py apps/agent-service/tests/tools/test_arguments.py apps/agent-service/tests/tools/test_registry.py -q
```

Expected: 全部通过。

- [ ] **Step 3: 运行 Agent Service 全量验证**

Run:

```powershell
uv run pytest apps/agent-service/tests -q
uv run ruff check apps/agent-service/src apps/agent-service/tests
uv run mypy apps/agent-service/src packages/service-contracts/src
git diff --check
```

Expected: 四条命令退出码均为 0。

- [ ] **Step 4: 最终差异审计**

Run:

```powershell
git status --short
git diff origin/main...HEAD --stat
git diff origin/main...HEAD -- apps/agent-service docs/specs/2026-08-29-deepseek-quality-strict-tool-hotfix.md docs/plans/2026-08-29-deepseek-quality-strict-tool-hotfix.md
```

Expected: 只包含质量 strict wire、脱敏诊断、测试与事实文档；无 Core、数据库、前端和其他工具路由变更。

- [ ] **Step 5: 提交文档与验证状态**

```powershell
git add -- apps/agent-service/AGENTS.md docs/requirements/03-ai-writing-and-agents.md docs/requirements/04-review-quality-and-workflow.md docs/specs/2026-08-29-deepseek-quality-strict-tool-hotfix.md docs/plans/2026-08-29-deepseek-quality-strict-tool-hotfix.md
git commit -m "文档：同步质量 strict 生产收敛边界"
```

不得在本计划内推送、部署或再次重跑生产质量检查；这些动作需要用户另行明确授权。
