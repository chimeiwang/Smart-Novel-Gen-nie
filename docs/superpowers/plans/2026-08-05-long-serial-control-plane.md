# 长篇控制面与共享契约 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Core 能以服务端权威契约创建、查询和恢复显式长篇任务，并让 Agent 精确执行 `plan_chapter`、`write_chapter`、`review_chapter` 而不再经过自然语言分类。

**Architecture:** 共享包定义严格长篇 job payload 和公开 Operation 投影；Core 负责请求规范化、跨命令幂等、章节互斥、来源冻结和公共 outcome；Agent 只校验并执行 Core 下发的 job。所有新增事实存入现有 JSON/Text 列，历史自然语言长篇和中短篇继续兼容读取。

**Tech Stack:** Pydantic v2、FastAPI、SQLAlchemy async、PostgreSQL advisory locks、LangGraph、pytest、Ruff、Mypy、OpenAPI TypeScript generator

---

## 执行前提

- 权威规格：[长篇 CLI 服务端控制面规格](../../specs/2026-08-05-long-serial-cli-control-plane.md)
- 总体依赖：[长篇 CLI 总体交付计划](./2026-08-05-long-serial-cli-program.md)
- 开始 Task 1 前确认 `git rev-parse --verify refs/codex/long-serial-plan-base` 成功；缺失时先按总体计划记录实施基线。
- 本计划完成后仍不得注册长篇 CLI 写命令；写命令必须等待运行安全计划全部通过。
- 不增加篇幅模式全局守卫；只在显式 start 的小说归属校验中确认 `storyLengthProfile=long_serial`。
- 不修改 `apps/core-api/src/inkforge_core/db/schema-contract.json` 或任何模型列、索引、枚举和迁移。
- 执行 Agent Task 9–10 前重新读取 `apps/agent-service/AGENTS.md`、`docs/requirements/03-ai-writing-and-agents.md` 和 `docs/requirements/04-review-quality-and-workflow.md`，并以当前代码/共享契约为准。
- 强制 TDD 节奏：每个含“写失败测试”的 Task，在测试编辑完成后、执行任何实现步骤前，立即运行该 Task 已列出的精确 pytest 命令并记录 RED；失败必须来自目标能力缺失，不能是语法、导入路径或环境错误。若意外通过，先修正测试。实现后重复同一命令确认 GREEN，再允许提交。

### Task 1：把已确定的存储与缺席绑定形状补进规格

**Files:**

- Modify: `docs/specs/2026-08-05-long-serial-cli-control-plane.md`
- Test: `docs/superpowers/plans/2026-08-05-long-serial-cli-program.md`

- [ ] 在 `sourceBindings` 段加入严格 `absenceSentinel` 形状，并明确不存在资源的稳定逻辑 ID：

```json
{
  "resourceType": "outline",
  "resourceId": "novel:<novelId>:outline",
  "exists": false,
  "updatedAt": null,
  "contentSha256": null,
  "revision": null,
  "absenceSentinel": {
    "resourceType": "novel",
    "resourceId": "<novelId>"
  }
}
```

- [ ] 明确 `WritingRunCommand.payloadJson` 的 `_inkforgeCommand + job` envelope，历史裸 payload 只兼容读取、不能命中新幂等请求。
- [ ] 明确公共 checkpoint 只返回 `eventSequence/phase/operationStage/operationStep`。
- [ ] 明确 `WritingRunStatusResponse.reviewReport`、plan/write Artifact/decision 结果事实和 review 非空 `finalResponse`；显式任务缺失真实结果或 kind 不符时必须 `inconsistent`，不能沿用旧的“completed 即 succeeded”。
- [ ] 运行占位符扫描，预期无结果：

```powershell
$placeholderHits = rg -n "TODO|TBD|待定|以后再说" docs/specs/2026-08-05-long-serial-cli-control-plane.md
if ($LASTEXITCODE -gt 1) { throw "rg 执行失败" }
if ($LASTEXITCODE -eq 0) { $placeholderHits; throw "规格仍含占位符" }
```

- [ ] 提交：

```powershell
git add docs/specs/2026-08-05-long-serial-cli-control-plane.md
git commit -m "规格：明确长篇命令持久化细节"
```

### Task 2：建立共享 Operation 和长篇 payload 契约

**Files:**

- Create: `packages/service-contracts/src/inkforge_contracts/operations.py`
- Create: `packages/service-contracts/src/inkforge_contracts/long_serial.py`
- Modify: `packages/service-contracts/src/inkforge_contracts/runs.py`
- Modify: `packages/service-contracts/src/inkforge_contracts/jobs.py`
- Modify: `packages/service-contracts/src/inkforge_contracts/__init__.py`
- Create: `packages/service-contracts/tests/test_long_serial_contracts.py`
- Create: `packages/service-contracts/tests/test_public_operation_contracts.py`
- Modify: `packages/service-contracts/tests/test_jobs.py`
- Modify: `packages/service-contracts/tests/test_run_contracts.py`

- [ ] 先写失败测试，覆盖：额外字段拒绝、`sync_lore` 不可用于新任务、target/scope 判别、scope 范围、source binding 不变量、start/resume payload 互斥、三个公开 Operation 的精确映射。
- [ ] 运行并确认 RED：

```powershell
uv run pytest packages/service-contracts/tests/test_long_serial_contracts.py packages/service-contracts/tests/test_public_operation_contracts.py packages/service-contracts/tests/test_jobs.py packages/service-contracts/tests/test_run_contracts.py -q
```

预期：因 `inkforge_contracts.long_serial` 和新类型不存在而失败。

- [ ] 在 `operations.py` 保留历史全集并新增可执行类型；不要删除 `sync_lore` 的历史解析能力：

```python
HistoricalCreativeOperationKind = Literal[
    "answer_question", "create_lore", "revise_lore", "create_outline",
    "revise_outline", "plan_chapter", "write_chapter", "rewrite_scene",
    "review_chapter", "sync_lore", "manage_foreshadowing",
]

ExecutableCreativeOperationKind = Literal[
    "answer_question", "create_lore", "revise_lore", "create_outline",
    "revise_outline", "plan_chapter", "write_chapter", "rewrite_scene",
    "review_chapter", "manage_foreshadowing",
]

# 兼容现有公共导入；历史全集不能因新增可执行子集而改名失效。
CreativeOperationKind = HistoricalCreativeOperationKind
```

- [ ] `runs.py` 删除自己的重复 Literal，改为从 `operations.py` 导入 `CreativeOperationKind`；`__init__.py` 明确导出 `CreativeOperationKind`、`HistoricalCreativeOperationKind`、`ExecutableCreativeOperationKind`、`PublicOperationDefinition` 和长篇 payload 类型，现有 import 路径全部保持有效。

- [ ] 在 `long_serial.py` 实现严格模型。`SourceBinding` 的 validator 必须保证：

```python
@model_validator(mode="after")
def validate_version_shape(self) -> Self:
    if self.exists:
        if self.updatedAt is None or self.contentSha256 is None:
            raise ValueError("存在的来源必须包含 updatedAt 和 contentSha256")
        if self.absenceSentinel is not None:
            raise ValueError("存在的来源不能包含 absenceSentinel")
    else:
        if any(value is not None for value in (
            self.updatedAt, self.contentSha256, self.revision,
        )):
            raise ValueError("不存在的来源不能包含版本或内容摘要")
        if self.absenceSentinel is None:
            raise ValueError("不存在的来源必须包含 absenceSentinel")
    return self
```

- [ ] 测试必须断言上述错误产生 Pydantic `ValidationError`，不能使用会被 `python -O` 移除的 `assert` 实现契约。
- [ ] `LongSerialRunPayload` 使用两个模型和真正的 discriminator；公共字段放入 `LongSerialRunBase`，resume job 仍完整携带原 operation、target、scope、sourceBindings、targetWordCount 和 userInstruction，只新增普通 checkpoint 输入，不接受 Artifact decision：

```python
class LongSerialRunBase(StrictModel):
    version: Literal[1]
    workflow: Literal["long_serial"]
    chapterId: Identifier
    writingSessionId: Identifier | None
    operation: ExecutableCreativeOperationKind
    target: ChapterTarget
    scope: LongSerialScope
    sourceBindings: tuple[SourceBinding, ...]
    targetWordCount: int = Field(ge=1, le=10_000_000)
    userInstruction: str = Field(min_length=1)

class StartLongSerialRunPayload(LongSerialRunBase):
    resume: Literal[False]
    resumeInput: None

class ResumeLongSerialRunPayload(LongSerialRunBase):
    resume: Literal[True]
    resumeInput: LongSerialResumeInput

LongSerialRunPayload = Annotated[
    StartLongSerialRunPayload | ResumeLongSerialRunPayload,
    Field(discriminator="resume"),
]

LONG_SERIAL_RUN_PAYLOAD_ADAPTER = TypeAdapter(LongSerialRunPayload)
```
- [ ] `TypeAdapter` 从 Pydantic 导入；`LongSerialRunPayload` 是 `Annotated` 联合别名，不得调用不存在的 `.model_validate()`。共享包显式导出 `LONG_SERIAL_RUN_PAYLOAD_ADAPTER`，Core 与 Agent 统一调用其 `validate_python()`。
- [ ] 公开投影只开放三个首阶段 Operation：

```python
PUBLIC_LONG_SERIAL_OPERATIONS = {
    "plan_chapter": PublicOperationDefinition(
        operation="plan_chapter", workflow="long_serial",
        targetKind="chapter", allowedScopeKinds=("chapter",),
        mutating=True, principalAgent="剧情", reviewers=("编辑",),
        artifactKind="beat_plan",
    ),
    "write_chapter": PublicOperationDefinition(
        operation="write_chapter", workflow="long_serial",
        targetKind="chapter", allowedScopeKinds=("chapter",),
        mutating=True, principalAgent="写作", reviewers=("校验", "编辑"),
        artifactKind="chapter_draft",
    ),
    "review_chapter": PublicOperationDefinition(
        operation="review_chapter", workflow="long_serial",
        targetKind="chapter", allowedScopeKinds=("chapter",),
        mutating=False, principalAgent="编辑", reviewers=(), artifactKind=None,
    ),
}
```

- [ ] `AgentJobRequest` 仅当 writing payload 同时具备 `workflow=long_serial` 时校验 `LongSerialRunPayload`；无 workflow 的历史自然语言 job 继续兼容。
- [ ] 再运行同一测试，预期全部通过。
- [ ] 提交：

```powershell
git add packages/service-contracts/src/inkforge_contracts/operations.py packages/service-contracts/src/inkforge_contracts/long_serial.py packages/service-contracts/src/inkforge_contracts/runs.py packages/service-contracts/src/inkforge_contracts/jobs.py packages/service-contracts/src/inkforge_contracts/__init__.py packages/service-contracts/tests/test_long_serial_contracts.py packages/service-contracts/tests/test_public_operation_contracts.py packages/service-contracts/tests/test_jobs.py packages/service-contracts/tests/test_run_contracts.py
git commit -m "功能：定义显式长篇运行契约"
```

### Task 3：实现规范化 JSON、指纹和跨表幂等 resolver

**Files:**

- Create: `apps/core-api/src/inkforge_core/writing/idempotency.py`
- Create: `apps/core-api/tests/writing/test_idempotency.py`
- Modify: `apps/core-api/src/inkforge_core/writing/commands.py`
- Modify: `apps/core-api/src/inkforge_core/agent_client.py`
- Test: `apps/core-api/tests/test_agent_client.py`

- [ ] 写失败测试覆盖：递归 key 排序、非 ASCII 原字符、UTC datetime、commandKind 与路径身份参与 hash、相同 ID/相同指纹命中、相同 ID/不同指纹返回 `IDEMPOTENCY_KEY_REUSED`、历史裸 payload 不命中、WritingRunCommand 与 WorkflowRun 跨表冲突。
- [ ] 运行并确认 RED：

```powershell
uv run pytest apps/core-api/tests/writing/test_idempotency.py apps/core-api/tests/test_agent_client.py -q
```

- [ ] 实现以下稳定接口；不要复用未声明递归排序的服务签名 JSON：

```python
type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

def normalize_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("指纹 JSON 不允许 NaN 或 Infinity")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("指纹 datetime 必须包含时区")
        return value.astimezone(timezone.utc).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z")
    if isinstance(value, (list, tuple)):
        return [normalize_json_value(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("指纹 JSON 对象 key 必须是字符串")
            normalized[key] = normalize_json_value(item)
        return normalized
    raise TypeError(f"指纹 JSON 不支持类型：{type(value).__name__}")

def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        normalize_json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

def request_fingerprint(*, command_kind: str,
                        resource_identity: dict[str, JsonValue],
                        body: dict[str, JsonValue]) -> str:
    value = {
        "commandKind": command_kind,
        "resourceIdentity": resource_identity,
        "body": body,
    }
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()

async def acquire_idempotency_lock(session: AsyncSession, *,
                                   user_id: str,
                                   client_request_id: str) -> None:
    digest = hashlib.sha256(
        f"{user_id}\0{client_request_id}".encode("utf-8")
    ).digest()
    lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": lock_key},
    )
```

- [ ] 上述递归别名与 `normalize_json_value()` 定义在 `idempotency.py`。字典 key 非字符串和任意自定义对象返回 TypeError；NaN/Infinity 与 naive datetime 返回 ValueError；aware datetime 统一转 UTC、固定 6 位微秒并输出 `Z`。测试精确固定这些错误类型和格式。

- [ ] advisory key 固定为 `SHA-256(userId + NUL + clientRequestId)` 前 8 字节、`byteorder="big"`、signed int64；事务第一步执行 `pg_advisory_xact_lock`。固定向量 `user-1\0client-request-0001` 的完整摘要为 `0d3dc28437d1b16474387be307d756bc91a6919db1e257bc84b33699cd1c5639`，锁键为 `954132569200374116`，测试必须精确断言。
- [ ] 实现严格 `_inkforgeCommand` envelope 解析器和 `resolve_idempotency()`。resolver 在同一 advisory lock 下查询：

```text
WritingRunCommand.idempotencyKey == userId:clientRequestId
WorkflowRun.input 中 schemaVersion=1 且 clientRequestId 相同的 envelope
```

- [ ] 为 Text 类型 `WorkflowRun.input` 只做当前用户范围内读取并在 Python 严格解析；记录这是无 schema 约束下的可接受线性扫描，不用字符串 contains 冒充 JSON 语义。
- [ ] 在 `agent_client.py` 增加 `command_job_payload()`：新 envelope 只提交 `job`；历史 command 继续提交原 payload。
- [ ] 再运行同一测试，预期全部通过。
- [ ] 提交：

```powershell
git add apps/core-api/src/inkforge_core/writing/idempotency.py apps/core-api/src/inkforge_core/writing/commands.py apps/core-api/src/inkforge_core/agent_client.py apps/core-api/tests/writing/test_idempotency.py apps/core-api/tests/test_agent_client.py
git commit -m "功能：统一写作命令幂等指纹"
```

### Task 4：建立统一关系锁顺序

**Files:**

- Create: `apps/core-api/src/inkforge_core/writing/transaction_locks.py`
- Create: `apps/core-api/tests/writing/test_transaction_locks.py`
- Modify: `apps/core-api/src/inkforge_core/writing/commands.py`

- [ ] 写失败测试记录 SQL 锁取得次序，覆盖可选 Artifact/Command 和多个 Chapter 的 ID 排序。
- [ ] 实现统一入口：

```python
@dataclass(frozen=True, slots=True)
class WritingLockRequest:
    novel_id: str
    chapter_ids: tuple[str, ...] = ()
    task_id: str | None = None
    artifact_id: str | None = None
    command_id: str | None = None

@dataclass(frozen=True, slots=True)
class LockedWritingRows:
    novel: Novel
    chapters: tuple[Chapter, ...]
    task: WritingTask | None
    artifact: ReviewArtifact | None
    command: WritingRunCommand | None
```

- [ ] 实现签名固定为 `async def lock_writing_rows(session: AsyncSession, *, user_id: str, request: WritingLockRequest) -> LockedWritingRows`；缺失任何显式请求的行或关联/归属不符时立即抛稳定 `ApiError`，可选 ID 为 null 时对应返回字段为 null。
- [ ] 查询顺序固定为 Novel → 排序后的 Chapter → WritingTask → ReviewArtifact → WritingRunCommand；每一步使用 `FOR UPDATE`，并在锁后重验归属与关联。
- [ ] 不把来源子行塞进通用 helper；调用方取得上述父行后再按 `resourceType + resourceId` 排序锁来源子行。
- [ ] 运行：

```powershell
uv run pytest apps/core-api/tests/writing/test_transaction_locks.py -q
```

- [ ] 提交：

```powershell
git add apps/core-api/src/inkforge_core/writing/transaction_locks.py apps/core-api/src/inkforge_core/writing/commands.py apps/core-api/tests/writing/test_transaction_locks.py
git commit -m "重构：统一写作事务锁顺序"
```

### Task 5：冻结章节、文本总纲和 approved Beat Plan 来源

**Files:**

- Create: `apps/core-api/src/inkforge_core/writing/source_bindings.py`
- Create: `apps/core-api/tests/writing/test_source_bindings.py`
- Modify: `apps/core-api/src/inkforge_core/writing/commands.py`
- Modify: `apps/core-api/src/inkforge_core/outlines/repository.py`
- Modify: `apps/core-api/src/inkforge_core/chapters/repository.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/formal_writes.py`

- [ ] 写失败测试覆盖完整 UTF-8 hash、CRLF、中文、缺失 Outline/Beat Plan、SceneBeat 固定排序、历史多个 approved Beat Plan fail closed、sentinel 与真实写路径共用父锁。
- [ ] 实现两个固定接口：`capture_chapter_source_bindings(session: AsyncSession, *, novel_id: str, chapter_id: str) -> tuple[SourceBinding, ...]` 读取并冻结完整来源；`verify_source_bindings(session: AsyncSession, bindings: tuple[SourceBinding, ...]) -> None` 在父行已按统一锁序锁定后，按 `resourceType + resourceId` 排序锁/读取真实子行并逐项比较。

- [ ] Chapter/Outline 对完整原始字符串的 UTF-8 字节做 SHA-256；不做换行或 Unicode 规范化。
- [ ] Beat Plan 使用公开响应字段组装完整对象，SceneBeat 按 `(order, id)` 排序后使用 Task 3 的 canonical JSON hash。
- [ ] 找到多个 approved Beat Plan 时返回稳定 409 `BEAT_PLAN_SOURCE_AMBIGUOUS`，不能任选一条。
- [ ] Outline 所有写路径先锁 Novel；Beat Plan 创建、更新、删除和正式应用先锁 Chapter。Chapter 正文写路径继续以 Chapter 行作为自身 source lock。
- [ ] 运行：

```powershell
uv run pytest apps/core-api/tests/writing/test_source_bindings.py apps/core-api/tests/outlines apps/core-api/tests/chapters apps/core-api/tests/reviews/test_artifact_apply.py -q
```

- [ ] 提交：

```powershell
git add apps/core-api/src/inkforge_core/writing/source_bindings.py apps/core-api/src/inkforge_core/writing/commands.py apps/core-api/src/inkforge_core/outlines/repository.py apps/core-api/src/inkforge_core/chapters/repository.py apps/core-api/src/inkforge_core/reviews/formal_writes.py apps/core-api/tests/writing/test_source_bindings.py
git commit -m "功能：冻结长篇章节来源版本"
```

### Task 6：实现显式长篇 start、会话约束和章节目标互斥

**Files:**

- Modify: `apps/core-api/src/inkforge_core/writing/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/writing/commands.py`
- Modify: `apps/core-api/src/inkforge_core/writing/records.py`
- Modify: `apps/core-api/src/inkforge_core/writing/tasks.py`
- Create: `apps/core-api/tests/writing/test_long_serial_runs.py`
- Modify: `apps/core-api/tests/writing/test_commands.py`
- Modify: `apps/core-api/tests/writing/test_sessions.py`
- Create: `apps/core-api/tests/test_openapi_long_serial.py`

- [ ] 先写失败测试覆盖严格 body、`workflow=long_serial` 与目标作品类型的一次性启动契约、归属、chapter/target/scope 三者一致、会话绑定、`selectedAgents` 拒绝、unsupported operation/scope、同章 mutating 互斥、review_chapter 可并行、waiting_user 继续占用、并发相同 ID 命中原响应；不得把这项启动校验扩展成全局篇幅模式守卫。
- [ ] 定义新公共请求：

```python
class LongSerialStartWritingRunRequest(WritingSchema):
    clientRequestId: str = Field(min_length=16, max_length=128)
    workflow: Literal["long_serial"]
    novelId: str = Field(min_length=1, max_length=256)
    chapterId: str = Field(min_length=1, max_length=256)
    writingSessionId: str | None = Field(default=None, min_length=1, max_length=256)
    operation: ExecutableCreativeOperationKind
    target: ChapterTarget
    scope: LongSerialScope
    targetWordCount: int = Field(default=4000, ge=1, le=10_000_000)
    userInstruction: str = Field(min_length=1)
```

- [ ] 在一个事务中执行：advisory → Novel+篇幅/归属 → Chapter → 会话与交叉矩阵 → 第二次幂等查询 → mutating task 查询 → sourceBindings → Task/Command。
- [ ] 不在 Pydantic 层把合法但未开放的 executable operation 伪装成 422；Core 查不到首阶段公开映射时返回 `LONG_SCOPE_NOT_SUPPORTED`。
- [ ] 章节冲突判断以任务实际终态和 start command 的公开 `mutating` 定义为准；历史自然语言长篇在未分类时保守视为 mutating。
- [ ] 新 command 使用 `_inkforgeCommand + job`。`job` 必须能通过 `LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python()`，且不包含 `clientRequestId` 或 envelope。
- [ ] `selectedAgents`、主责 Agent、reviewers、artifactKind 全部由共享公开定义推导。
- [ ] 运行并确认通过：

```powershell
uv run pytest apps/core-api/tests/writing/test_long_serial_runs.py apps/core-api/tests/writing/test_commands.py apps/core-api/tests/writing/test_sessions.py apps/core-api/tests/test_openapi_long_serial.py -q
```

- [ ] 提交：

```powershell
git add apps/core-api/src/inkforge_core/writing/schemas.py apps/core-api/src/inkforge_core/writing/commands.py apps/core-api/src/inkforge_core/writing/records.py apps/core-api/src/inkforge_core/writing/tasks.py apps/core-api/tests/writing/test_long_serial_runs.py apps/core-api/tests/writing/test_commands.py apps/core-api/tests/writing/test_sessions.py apps/core-api/tests/test_openapi_long_serial.py
git commit -m "功能：受理显式长篇章节任务"
```

### Task 7：让现有 Web 自然语言长篇也冻结来源并参与互斥

**Files:**

- Modify: `apps/core-api/src/inkforge_core/writing/commands.py`
- Modify: `apps/core-api/src/inkforge_core/writing/context.py`
- Modify: `apps/core-api/tests/writing/test_commands.py`
- Modify: `apps/core-api/tests/writing/test_read_tool_service.py`

- [ ] 写测试证明自然语言 start 仍不携带显式 operation，Agent 后续仍会分类，但 start command 已保存同章、总纲、approved Beat Plan 的保守并集。
- [ ] 自然语言 job 可以继续使用历史形状；sourceBindings 从 command/context 注入，不得因为增加 `workflow=long_serial` 而误入显式 payload validator。
- [ ] 同章已有显式 mutating 或自然语言活动任务时，另一入口返回同一 `WRITING_TARGET_BUSY` 与占用 taskId。
- [ ] 运行：

```powershell
uv run pytest apps/core-api/tests/writing/test_commands.py apps/core-api/tests/writing/test_read_tool_service.py -q
```

- [ ] 提交：

```powershell
git add apps/core-api/src/inkforge_core/writing/commands.py apps/core-api/src/inkforge_core/writing/context.py apps/core-api/tests/writing/test_commands.py apps/core-api/tests/writing/test_read_tool_service.py
git commit -m "修复：统一网页与 CLI 长篇来源保护"
```

### Task 8：新增任务列表、稳定 cursor 和状态公共投影

**Files:**

- Create: `apps/core-api/src/inkforge_core/http/cursor.py`
- Create: `apps/core-api/src/inkforge_core/writing/run_queries.py`
- Modify: `apps/core-api/src/inkforge_core/writing/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/writing/router.py`
- Modify: `apps/core-api/src/inkforge_core/writing/commands.py`
- Modify: `apps/core-api/src/inkforge_core/writing/outcome.py`
- Create: `apps/core-api/tests/writing/test_run_queries.py`
- Modify: `apps/core-api/tests/writing/test_outcome.py`
- Modify: `apps/core-api/tests/writing/test_sse.py`
- Modify: `apps/core-api/tests/test_openapi_long_serial.py`

- [ ] 写失败测试覆盖：novelId 必填、归属不可探测、无 session task、所有过滤器、`createdAt DESC,id DESC`、cursor 篡改、历史长篇归一、checkpoint 白名单、七种 outcome 和 activeArtifactId/recoverable；另覆盖 plan/write 的 awaiting/applied/discard/revise 结果事实、80,000 字以上 review 非空完整报告，以及缺失/错误 kind/空报告投影 inconsistent。
- [ ] 模型使用：

```python
WritingRunOutcomeState = Literal[
    "queued", "running", "waiting_user", "succeeded",
    "failed", "cancelled", "inconsistent",
]

class WritingRunCheckpointResponse(WritingSchema):
    eventSequence: int
    phase: str
    operationStage: str | None
    operationStep: str | None

class WritingRunStatusResponse(WritingSchema):
    # 保留现有字段
    reviewReport: str | None
```

- [ ] 新增 `GET /api/v1/writing/runs`，参数为 novelId、chapterId、writingSessionId、operation、outcome、cursor、limit；limit 默认 50、最大 100。
- [ ] cursor 为 base64url 编码的严格 JSON `{createdAt,id}`；无页码、无 updatedAt。
- [ ] operation/outcome 需要派生时按稳定数据库 cursor 分批扫描、批量加载命令和 Artifact，直到收集 `limit+1` 个匹配项或耗尽；不能先截断一页再过滤。
- [ ] 历史无 workflow 的长篇任务只读投影为 `long_serial`；内部 `long_form` 不再出现在公共响应，不回写历史行。
- [ ] legacy 任务的 target/scope 从其非空 chapterId 合成 chapter 形状；operation 无可靠事实时返回 null，不从聊天文本猜测。
- [ ] `recoverable=true` 仅用于具备合法持久命令/checkpoint/Artifact 且 outcome 为 queued/running/waiting_user 的任务；终态和 inconsistent 为 false。
- [ ] 显式 plan/write 只从同 task 的匹配 Artifact 和持久 decision command 推导真实结果；显式 review 只从有效结果 command `resultJson` 的终态 callback 中读取非空 `finalResponse`，完整投影为 `reviewReport`，不读取或泄露完整 LangGraph snapshot。普通任务的有效结果 command 就是当前 command；当前 command 为 `effective=false` 的终态 no-op cancel 时，按 `priorOutcome.currentCommand.id` 逐级读取同 task 的前一个持久 command，直到原业务 command，缺失、循环或跨 task 一律 inconsistent。历史无 command 任务保留旧只读兼容。
- [ ] 在 `test_outcome.py` 增加真实结果回归：review succeeded 后执行一次和连续两次终态 no-op cancel，outcome 仍为 succeeded 且 `reviewReport` 字节完全一致；plan/write 同样验证 Artifact ID 不变，损坏 priorOutcome 链必须 inconsistent。
- [ ] 运行：

```powershell
uv run pytest apps/core-api/tests/writing/test_run_queries.py apps/core-api/tests/writing/test_outcome.py apps/core-api/tests/writing/test_sse.py apps/core-api/tests/test_openapi_long_serial.py -q
```

- [ ] 提交：

```powershell
git add apps/core-api/src/inkforge_core/http/cursor.py apps/core-api/src/inkforge_core/writing/run_queries.py apps/core-api/src/inkforge_core/writing/schemas.py apps/core-api/src/inkforge_core/writing/router.py apps/core-api/src/inkforge_core/writing/commands.py apps/core-api/src/inkforge_core/writing/outcome.py apps/core-api/tests/writing/test_run_queries.py apps/core-api/tests/writing/test_outcome.py apps/core-api/tests/writing/test_sse.py apps/core-api/tests/test_openapi_long_serial.py
git commit -m "功能：提供长篇任务查询与统一状态"
```

### Task 9：校验 Agent 完整定义与共享公开投影一致

**Files:**

- Modify: `apps/agent-service/src/inkforge_agents/operations/contracts.py`
- Modify: `apps/agent-service/src/inkforge_agents/operations/definitions.py`
- Modify: `apps/agent-service/src/inkforge_agents/app.py`
- Modify: `apps/agent-service/tests/operations/test_definitions.py`
- Modify: `apps/agent-service/tests/operations/test_router.py`

- [ ] 先写失败测试逐字段比较三个公开 Operation 的 operation、target、scope、mutating、principal、reviewers、artifactKind。
- [ ] `operations/contracts.py` 导入共享历史类型，不再维护第二份 `CreativeOperationKind` 字面量。
- [ ] 在完整定义上实现 `to_public_definition()`；工具白名单、prompt、context strategy 仍只留在 Agent。
- [ ] `create_app()` 在消费者启动前执行一致性校验，漂移时 fail fast；Core 不得导入 Agent 定义。
- [ ] 运行：

```powershell
uv run pytest apps/agent-service/tests/operations/test_definitions.py apps/agent-service/tests/operations/test_router.py -q
```

- [ ] 提交：

```powershell
git add apps/agent-service/src/inkforge_agents/operations/contracts.py apps/agent-service/src/inkforge_agents/operations/definitions.py apps/agent-service/src/inkforge_agents/app.py apps/agent-service/tests/operations/test_definitions.py apps/agent-service/tests/operations/test_router.py
git commit -m "重构：统一长篇 Operation 公开定义"
```

### Task 10：显式长篇 job 绕过 classifier 并稳定保存 scope

**Files:**

- Modify: `apps/agent-service/src/inkforge_agents/jobs/writing.py`
- Modify: `apps/agent-service/src/inkforge_agents/graph/state.py`
- Modify: `apps/agent-service/src/inkforge_agents/graph/snapshots.py`
- Modify: `apps/agent-service/src/inkforge_agents/operations/graph.py`
- Modify: `apps/agent-service/tests/jobs/test_writing.py`
- Modify: `apps/agent-service/tests/graph/test_operation_graph.py`
- Modify: `apps/agent-service/tests/graph/test_snapshots.py`

- [ ] 写失败测试：parent graph/classifier 使用会立即失败；operation graph 必须收到精确 operation、target、scope、sourceBindings；checkpoint 序列化/反序列化保持这些字段；resume 不重新分类。
- [ ] `GraphState` 增加稳定字段：

```python
workflow: Literal["long_serial"]
target: dict[str, Any]
scope: dict[str, Any]
sourceBindings: list[dict[str, Any]]
```

- [ ] `WritingJobHandler._prepare_state()` 对显式 payload 先做 `LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python()`，再由完整定义构造 `CreativeOperation(confidence=1.0)`，直接返回 `operation_graph`。
- [ ] `currentOperation` 的 primary/reviewers/output/artifact 要从定义推导；不得相信 payload 自带第二份 Agent 身份。
- [ ] legacy Web 初次任务继续返回 parent graph；short_medium 继续由现有 dispatcher 分流。
- [ ] operation graph 节点入口重新校验 currentOperation 的公开字段，防止恢复快照扩大 scope 或替换 Agent/Artifact kind。
- [ ] 运行：

```powershell
uv run pytest apps/agent-service/tests/jobs/test_writing.py apps/agent-service/tests/graph/test_operation_graph.py apps/agent-service/tests/graph/test_snapshots.py apps/agent-service/tests/operations/test_router.py -q
```

- [ ] 提交：

```powershell
git add apps/agent-service/src/inkforge_agents/jobs/writing.py apps/agent-service/src/inkforge_agents/graph/state.py apps/agent-service/src/inkforge_agents/graph/snapshots.py apps/agent-service/src/inkforge_agents/operations/graph.py apps/agent-service/tests/jobs/test_writing.py apps/agent-service/tests/graph/test_operation_graph.py apps/agent-service/tests/graph/test_snapshots.py
git commit -m "功能：直通显式长篇创作操作"
```

### Task 11：生成公共客户端并完成本计划验证

**Files:**

- Modify: `packages/api-client/src/generated/schema.d.ts`
- Test: `apps/core-api/tests/test_openapi_long_serial.py`

- [ ] 运行 Task 6/8 已按 RED→GREEN 建立的 OpenAPI 回归，断言显式长篇 start、任务列表/status/outcome、严格 target/scope 和新增错误响应仍在公共 schema；再运行相关 Python 全量测试：

```powershell
uv run pytest packages/service-contracts/tests apps/core-api/tests/test_openapi_long_serial.py apps/core-api/tests/writing apps/agent-service/tests/jobs apps/agent-service/tests/graph apps/agent-service/tests/operations -q
```

- [ ] 生成并核验客户端：

```powershell
npm run api:generate
npm run api:check
```

- [ ] 运行静态检查：

```powershell
uv run ruff check packages/service-contracts/src packages/service-contracts/tests apps/core-api/src apps/core-api/tests apps/agent-service/src apps/agent-service/tests
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
npm run typecheck
npm run lint
```

- [ ] 运行 schema 只读守卫，预期全部通过且无 DDL 差异：

```powershell
uv run pytest apps/core-api/tests/db/test_schema_guard.py apps/core-api/tests/db/test_model_metadata.py -q
git diff --exit-code refs/codex/long-serial-plan-base..HEAD -- apps/core-api/src/inkforge_core/db/schema-contract.json apps/core-api/src/inkforge_core/db/models.py scripts/migrations
git diff --cached --exit-code -- apps/core-api/src/inkforge_core/db/schema-contract.json apps/core-api/src/inkforge_core/db/models.py scripts/migrations
git diff --exit-code -- apps/core-api/src/inkforge_core/db/schema-contract.json apps/core-api/src/inkforge_core/db/models.py scripts/migrations
$untrackedSchemaPaths = git ls-files --others --exclude-standard -- apps/core-api/src/inkforge_core/db/schema-contract.json apps/core-api/src/inkforge_core/db/models.py scripts/migrations
if ($LASTEXITCODE -ne 0) { throw "无法检查未跟踪 schema 文件" }
if ($untrackedSchemaPaths) { $untrackedSchemaPaths; throw "发现未跟踪 schema 或迁移文件" }
```

预期：三条差异命令都无输出。

- [ ] 确认没有占位符：

```powershell
$implementationPlaceholders = rg -n "TODO|TBD|NotImplemented" packages/service-contracts/src/inkforge_contracts/long_serial.py apps/core-api/src/inkforge_core/writing apps/agent-service/src/inkforge_agents
if ($LASTEXITCODE -gt 1) { throw "rg 执行失败" }
if ($LASTEXITCODE -eq 0) { $implementationPlaceholders; throw "实现范围仍含占位符" }
```

- [ ] 提交生成物与必要修正：

```powershell
git add packages/api-client/src/generated/schema.d.ts apps/core-api/tests/test_openapi_long_serial.py
git commit -m "构建：同步长篇控制面公共客户端"
```

## 本计划完成门槛

- 三个显式 Operation 都通过共享契约，其他 operation/scope 得到 `LONG_SCOPE_NOT_SUPPORTED`。
- 显式 job 从未调用 classifier；自然语言 Web 路径仍会调用。
- 相同 clientRequestId 的并发 start 只创建一个任务，不同请求确定性 409。
- 同一章节最多一个活动 mutating task，waiting_user 继续占用。
- 所有新旧长篇任务都能通过列表重新发现，公共 workflow 统一为 `long_serial`。
- target、scope、sourceBindings 进入稳定 checkpoint，Agent 无法扩大或替换。
- PostgreSQL schema 指纹未变化。
