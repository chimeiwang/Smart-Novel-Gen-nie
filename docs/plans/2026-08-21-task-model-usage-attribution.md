# 模型调用按任务归集实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为每个真实计费模型调用持久化 `requestId/taskId/runId` 和四项 token，用同一计费请求标识关联人工日志，并提供按写作任务查询的公共 API。

**Architecture:** Agent 已在计费回调中携带任务、运行和 usage；Core 只需在授权校验后保留这些字段，并在同一计费事务写入扩展后的 `TokenUsage`。公共 API 从 Core 按当前用户和 `WritingTask` 归属查询逐调用明细；Agent 人工日志通过一个内部调用记录对象输出相同计费 `requestId` 和 usage。PostgreSQL 迁移保持 additive、可重跑且不猜测回填历史数据。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、SQLAlchemy 2、PostgreSQL 14、pytest、Ruff、Mypy、OpenAPI TypeScript 客户端、POSIX SQL/部署脚本。

---

### Task 1: 锁定 TokenUsage 新结构和版本化迁移

**Files:**
- Create: `scripts/migrations/20260821_token_usage_task_run.sql`
- Create: `apps/core-api/tests/db/test_token_usage_attribution_migration.py`
- Modify: `apps/core-api/src/inkforge_core/db/models.py:1897-1935`
- Modify: `apps/core-api/tests/db/test_model_metadata.py`

- [ ] **Step 1: 写迁移契约失败测试**

```python
MIGRATION = ROOT / "scripts" / "migrations" / "20260821_token_usage_task_run.sql"


def test_token_usage_migration_is_transactional_and_additive() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    compact = " ".join(sql.split()).lower()
    assert compact.startswith("begin;")
    assert compact.endswith("commit;")
    assert 'alter table "tokenusage" add column if not exists "requestid" text' in compact
    assert 'alter table "tokenusage" add column if not exists "taskid" text' in compact
    assert 'alter table "tokenusage" add column if not exists "runid" text' in compact
    assert "drop table" not in compact
    assert "delete from" not in compact


def test_token_usage_migration_declares_exact_indexes() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert '"TokenUsage_requestId_key"' in sql
    assert '"TokenUsage_userId_taskId_createdAt_idx"' in sql
    assert '"TokenUsage_runId_createdAt_idx"' in sql
```

- [ ] **Step 2: 运行测试确认因迁移文件缺失而失败**

Run: `uv run pytest apps/core-api/tests/db/test_token_usage_attribution_migration.py -q`

Expected: FAIL，错误明确指向迁移文件不存在。

- [ ] **Step 3: 编写可重跑事务迁移**

```sql
BEGIN;
SET LOCAL search_path = public, pg_catalog;
SELECT pg_advisory_xact_lock(hashtext('inkforge:20260821:TokenUsage:task-run'));

ALTER TABLE "TokenUsage" ADD COLUMN IF NOT EXISTS "requestId" TEXT;
ALTER TABLE "TokenUsage" ADD COLUMN IF NOT EXISTS "taskId" TEXT;
ALTER TABLE "TokenUsage" ADD COLUMN IF NOT EXISTS "runId" TEXT;

DO $migration$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public."TokenUsage"'::regclass
      AND conname = 'TokenUsage_requestId_check'
  ) THEN
    ALTER TABLE "TokenUsage"
      ADD CONSTRAINT "TokenUsage_requestId_check"
      CHECK ("requestId" IS NULL OR btrim("requestId") <> '') NOT VALID;
  END IF;
END
$migration$;

ALTER TABLE "TokenUsage" VALIDATE CONSTRAINT "TokenUsage_requestId_check";

CREATE UNIQUE INDEX IF NOT EXISTS "TokenUsage_requestId_key"
ON "TokenUsage"("requestId");
CREATE INDEX IF NOT EXISTS "TokenUsage_userId_taskId_createdAt_idx"
ON "TokenUsage"("userId", "taskId", "createdAt");
CREATE INDEX IF NOT EXISTS "TokenUsage_runId_createdAt_idx"
ON "TokenUsage"("runId", "createdAt");

DO $verification$
DECLARE
  relation_id OID := to_regclass('public."TokenUsage"');
  request_constraint TEXT;
BEGIN
  IF relation_id IS NULL THEN
    RAISE EXCEPTION 'TokenUsage 不存在';
  END IF;

  IF (
    SELECT count(*)
    FROM pg_attribute
    WHERE attrelid = relation_id
      AND attname IN ('requestId', 'taskId', 'runId')
      AND format_type(atttypid, atttypmod) = 'text'
      AND NOT attnotnull
      AND attnum > 0
      AND NOT attisdropped
  ) <> 3 THEN
    RAISE EXCEPTION 'TokenUsage 归集列定义不符合契约';
  END IF;

  SELECT pg_get_constraintdef(oid)
  INTO request_constraint
  FROM pg_constraint
  WHERE conrelid = relation_id
    AND conname = 'TokenUsage_requestId_check'
    AND convalidated;
  IF request_constraint IS NULL
     OR position('btrim' IN request_constraint) = 0
     OR position('requestId' IN request_constraint) = 0 THEN
    RAISE EXCEPTION 'TokenUsage requestId 检查约束不符合契约';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'TokenUsage'
      AND indexname = 'TokenUsage_requestId_key'
      AND indexdef LIKE 'CREATE UNIQUE INDEX%'
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'TokenUsage'
      AND indexname = 'TokenUsage_userId_taskId_createdAt_idx'
      AND indexdef LIKE '%("userId", "taskId", "createdAt")%'
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'TokenUsage'
      AND indexname = 'TokenUsage_runId_createdAt_idx'
      AND indexdef LIKE '%("runId", "createdAt")%'
  ) THEN
    RAISE EXCEPTION 'TokenUsage 归集索引不符合契约';
  END IF;
END
$verification$;

COMMIT;
```

迁移测试还应断言 `DO` 块核验三列可空 `TEXT`、非空值检查和三个索引，避免 `IF NOT EXISTS` 掩盖
同名漂移。

- [ ] **Step 4: 更新 ORM 元数据**

```python
class TokenUsage(Base):
    requestId: Mapped[str | None] = mapped_column(Text, nullable=True)
    taskId: Mapped[str | None] = mapped_column(Text, nullable=True)
    runId: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("id", name="TokenUsage_pkey"),
        CheckConstraint(
            '"requestId" IS NULL OR btrim("requestId") <> \'\'',
            name="TokenUsage_requestId_check",
        ),
        Index("TokenUsage_requestId_key", "requestId", unique=True),
        Index("TokenUsage_userId_taskId_createdAt_idx", "userId", "taskId", "createdAt"),
        Index("TokenUsage_runId_createdAt_idx", "runId", "createdAt"),
        # 保留现有索引
        {"schema": "public"},
    )
```

- [ ] **Step 5: 运行迁移文本测试和 ORM 元数据测试**

Run: `uv run pytest apps/core-api/tests/db/test_token_usage_attribution_migration.py apps/core-api/tests/db/test_model_metadata.py -q`

Expected: PASS。

- [ ] **Step 6: 提交结构与迁移**

```bash
git add scripts/migrations/20260821_token_usage_task_run.sql apps/core-api/src/inkforge_core/db/models.py apps/core-api/tests/db/test_token_usage_attribution_migration.py apps/core-api/tests/db/test_model_metadata.py
git commit -m "数据库：增加模型用量任务归集字段"
```

### Task 2: 在计费事务中保存任务、运行和请求身份

**Files:**
- Modify: `apps/core-api/src/inkforge_core/billing/repository.py:37-241`
- Modify: `apps/core-api/src/inkforge_core/billing/service.py:147-159`
- Modify: `apps/core-api/tests/billing/test_usage_charge.py`
- Modify: `apps/core-api/tests/billing/test_model_grants.py`

- [ ] **Step 1: 扩展测试工厂和 ChargeUsage 期望**

```python
def _usage(*, completion_tokens: int = 20, task_id: str = "task-1") -> ChargeUsage:
    return ChargeUsage(
        request_id="request-1",
        task_id=task_id,
        run_id="run-1",
        user_id="user-1",
        novel_id="novel-1",
        model="deepseek-v4-flash",
        agent_id="写作",
        prompt_tokens=100,
        cached_tokens=40,
        completion_tokens=completion_tokens,
        total_tokens=100 + completion_tokens,
    )
```

增加断言：新写 `TokenUsage` 的三个字段精确等于请求身份；相同 requestId 但不同 taskId/runId 必须
`UsageConflictError`；零 usage 写一条 TokenUsage、无 CreditLedger、余额不变，重复回调幂等。

- [ ] **Step 2: 运行测试确认 ChargeUsage 缺少字段且零 usage 语义不符**

Run: `uv run pytest apps/core-api/tests/billing/test_usage_charge.py -q`

Expected: FAIL，至少包含 `ChargeUsage` 不接受 `task_id/run_id`，以及零 usage 数量断言失败。

- [ ] **Step 3: 最小扩展计费对象和事务**

```python
@dataclass(frozen=True, slots=True)
class ChargeUsage:
    request_id: str
    task_id: str
    run_id: str
    user_id: str
    novel_id: str
    model: str
    agent_id: str
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int
    total_tokens: int
```

`BillingService.charge()` 从已验证的 grant claims 传入 `claims.taskId`、`claims.runId`。仓储把三个字段写入
`TokenUsage`；`_same_usage()` 同时比较 task/run。金额为零时进入一个只写 TokenUsage 的短事务，通过
`TokenUsage.requestId` 判断幂等和冲突，不创建零金额 `CreditLedger`。

- [ ] **Step 4: 运行计费测试确认通过**

Run: `uv run pytest apps/core-api/tests/billing/test_usage_charge.py apps/core-api/tests/billing/test_model_grants.py -q`

Expected: PASS。

- [ ] **Step 5: 提交计费持久化**

```bash
git add apps/core-api/src/inkforge_core/billing/repository.py apps/core-api/src/inkforge_core/billing/service.py apps/core-api/tests/billing/test_usage_charge.py apps/core-api/tests/billing/test_model_grants.py
git commit -m "计费：持久化模型调用任务身份"
```

### Task 3: 提供按写作任务查询的用量 API

**Files:**
- Modify: `apps/core-api/src/inkforge_core/billing/schemas.py:90-115`
- Modify: `apps/core-api/src/inkforge_core/billing/repository.py`
- Modify: `apps/core-api/src/inkforge_core/billing/service.py`
- Modify: `apps/core-api/src/inkforge_core/billing/router.py:35-58`
- Create: `apps/core-api/tests/billing/test_task_usage_api.py`

- [ ] **Step 1: 写公共 API 失败测试**

```python
def test_task_usage_api_returns_owned_call_details() -> None:
    app, service = _app()
    response = TestClient(app).get("/api/v1/billing/usage/tasks/task-1")
    assert response.status_code == 200
    assert response.json() == {
        "taskId": "task-1",
        "requestCount": 1,
        "promptTokens": 100,
        "cachedTokens": 40,
        "completionTokens": 20,
        "totalTokens": 120,
        "calls": [{
            "requestId": "request-1",
            "runId": "run-1",
            "agentId": "写作",
            "model": "deepseek-v4-flash",
            "promptTokens": 100,
            "cachedTokens": 40,
            "completionTokens": 20,
            "totalTokens": 120,
            "createdAt": "2026-08-21T12:00:00Z",
        }],
    }
    assert service.calls == [("user-1", "task-1")]
```

再测试未登录返回 401、服务层对不存在或越权 WritingTask 返回统一 404、存在但尚无新用量的任务返回
零汇总和空 calls。

- [ ] **Step 2: 运行测试确认路由不存在**

Run: `uv run pytest apps/core-api/tests/billing/test_task_usage_api.py -q`

Expected: FAIL，`GET /api/v1/billing/usage/tasks/task-1` 返回 404。

- [ ] **Step 3: 增加严格响应模型**

```python
class ModelCallUsageResponse(BillingSchema):
    requestId: str
    runId: str
    agentId: str
    model: str
    promptTokens: int
    cachedTokens: int
    completionTokens: int
    totalTokens: int
    createdAt: datetime


class TaskModelUsageResponse(TokenUsageBreakdown):
    taskId: str
    requestCount: int
    calls: list[ModelCallUsageResponse]
```

- [ ] **Step 4: 增加归属查询和路由**

仓储先以 `WritingTask.id + Novel.userId` 验证归属，再按 `TokenUsage.userId/taskId`、`createdAt/id` 查询。
Service 计算四项汇总，Router 新增：

```python
@router.get("/usage/tasks/{task_id}", response_model=TaskModelUsageResponse)
async def get_task_usage(task_id: str, user: User, service: Service) -> TaskModelUsageResponse:
    return await service.task_usage(user.id, task_id)
```

- [ ] **Step 5: 运行 API 和计费回归测试**

Run: `uv run pytest apps/core-api/tests/billing -q`

Expected: PASS。

- [ ] **Step 6: 提交查询 API**

```bash
git add apps/core-api/src/inkforge_core/billing apps/core-api/tests/billing/test_task_usage_api.py
git commit -m "接口：按写作任务查询模型用量"
```

### Task 4: 让每个模型日志区块携带相同计费身份和 token

**Files:**
- Modify: `apps/agent-service/src/inkforge_agents/runtime/model_runtime.py:11-157`
- Modify: `apps/agent-service/src/inkforge_agents/observability/model_observer.py`
- Modify: `apps/agent-service/src/inkforge_agents/observability/human_workflow_log.py:80-112`
- Modify: `apps/agent-service/tests/runtime/test_billing_runtime.py`
- Modify: `apps/agent-service/tests/observability/test_model_log_bridge.py`
- Modify: `apps/agent-service/tests/observability/test_human_workflow_log.py`
- Modify: `apps/agent-service/tests/integration/test_debug_logs.py`

- [ ] **Step 1: 写 Runtime 到日志桥接失败测试**

扩展 `test_model_runtime_records_complete_provider_result_in_human_log`，断言：

```python
assert "任务标识：task-bridge" in written
assert "运行标识：run-bridge" in written
assert "计费请求标识：无" in written
assert "模型：bridge-test/bridge-test-model" in written
assert "Token 消耗：输入 10 | 缓存 0 | 输出 20 | 合计 30" in written
```

在 billable Runtime 测试中断言 observer 收到 `billingRequestId="grant-request-1"` 和原始
`ModelUsage(100,20,30,130)`；调用两次时 `A01/A02` 分别记录各自 usage，不写聚合值。

- [ ] **Step 2: 运行测试确认 observer 协议缺少字段**

Run: `uv run pytest apps/agent-service/tests/runtime/test_billing_runtime.py apps/agent-service/tests/observability/test_model_log_bridge.py apps/agent-service/tests/observability/test_human_workflow_log.py -q`

Expected: FAIL，日志中缺少任务、模型、计费请求和 token 行。

- [ ] **Step 3: 定义内部模型调用日志记录对象**

```python
class ModelCallLogRecord(BaseModel):
    context: ModelCallContext
    provider: str
    model: str
    billingRequestId: str | None = None
    messages: list[dict[str, str]]
    output: str
    usage: ModelUsage
    finishReason: str
    rawFinishReason: str | None
```

`ModelCallObserver.record_model_call(record)` 改接收单一严格对象，避免继续扩大位置参数。billable 分支在
usage report 成功后传入 Core grant requestId；非 billable 分支传 `None`。绝不传递或记录 grantToken。

- [ ] **Step 4: 格式化逐调用日志**

`HumanWorkflowLog.record_model_call()` 从 record 输出稳定中文行，再完整输出 messages 和模型正文。保留
现有 `Axx` 递增规则、完成原因和不截断语义。

- [ ] **Step 5: 运行 Agent 日志与调试 API 测试**

Run: `uv run pytest apps/agent-service/tests/runtime/test_billing_runtime.py apps/agent-service/tests/observability apps/agent-service/tests/integration/test_debug_logs.py -q`

Expected: PASS。

- [ ] **Step 6: 提交日志关联**

```bash
git add apps/agent-service/src/inkforge_agents/runtime/model_runtime.py apps/agent-service/src/inkforge_agents/observability apps/agent-service/tests/runtime/test_billing_runtime.py apps/agent-service/tests/observability apps/agent-service/tests/integration/test_debug_logs.py
git commit -m "日志：记录逐次模型调用用量"
```

### Task 5: 同步权威文档和生成客户端

**Files:**
- Modify: `DOCS.md`
- Modify: `AGENTS.md`
- Modify: `apps/agent-service/AGENTS.md`
- Modify: `docs/requirements/03-ai-writing-and-agents.md`
- Modify: `docs/requirements/05-auth-billing-and-ops.md`
- Modify: `docs/WORKFLOW_EVENT_LOG_FORMAT.md`
- Modify: `packages/api-client/openapi.json`
- Modify: generated files under `packages/api-client/src/`

- [ ] **Step 1: 更新当前事实**

文档明确本次用户批准的 Schema 例外、TokenUsage 新字段、逐任务 API、零 usage 记录和人工日志格式；把
“数据库结构指纹迁移前后保持不变”改为“除已批准版本化迁移外必须与当前 contract 精确一致”。

- [ ] **Step 2: 重新生成客户端**

Run: `npm run api:generate`

Expected: OpenAPI 快照和 TypeScript 客户端出现 `TaskModelUsageResponse`、
`GET /api/v1/billing/usage/tasks/{task_id}`，没有手写重复 DTO。

- [ ] **Step 3: 验证生成契约**

Run: `npm run api:check`

Expected: PASS。

- [ ] **Step 4: 提交文档和客户端**

```bash
git add DOCS.md AGENTS.md apps/agent-service/AGENTS.md docs/requirements/03-ai-writing-and-agents.md docs/requirements/05-auth-billing-and-ops.md docs/WORKFLOW_EVENT_LOG_FORMAT.md packages/api-client
git commit -m "文档：补充模型用量任务归集契约"
```

### Task 6: 导出新 Schema Contract 并完成全量本地验证

**Files:**
- Modify: `apps/core-api/src/inkforge_core/db/schema-contract.json`

- [ ] **Step 1: 在隔离 PostgreSQL 克隆执行迁移两次**

Run:

```bash
psql "$VERIFY_DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/migrations/20260821_token_usage_task_run.sql
psql "$VERIFY_DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/migrations/20260821_token_usage_task_run.sql
```

Expected: 两次均提交成功，历史 TokenUsage 三列保持 NULL。

- [ ] **Step 2: 从隔离库导出新 contract**

Run: `uv run python scripts/export_schema_contract.py --database-url "$VERIFY_DATABASE_URL" --output apps/core-api/src/inkforge_core/db/schema-contract.json --overwrite`

Expected: 输出新指纹，TokenUsage 包含三个新字段、一个检查约束和三个新索引；其他表定义不变。

- [ ] **Step 3: 运行 Python 验证**

```bash
uv run pytest apps/core-api/tests/billing apps/core-api/tests/db/test_token_usage_attribution_migration.py apps/core-api/tests/db/test_model_metadata.py apps/core-api/tests/db/test_schema_guard.py apps/agent-service/tests/runtime/test_billing_runtime.py apps/agent-service/tests/observability apps/agent-service/tests/integration/test_debug_logs.py
uv run ruff check apps/core-api/src apps/core-api/tests apps/agent-service/src apps/agent-service/tests
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
```

Expected: 全部退出 0。

- [ ] **Step 4: 运行仓库门禁**

```bash
npm run api:check
npm run typecheck
npm run lint
uv run pytest tests/architecture/test_compose_security.py
```

Expected: 全部退出 0；不得为通过测试修改生产数据库。

- [ ] **Step 5: 复核差异并提交 contract**

```bash
git diff --check
git status --short
git add apps/core-api/src/inkforge_core/db/schema-contract.json
git commit -m "数据库：更新模型用量结构契约"
```

### Task 7: 受控生产迁移与发布验证

**Files:**
- Use: `scripts/migrations/20260821_token_usage_task_run.sql`
- Use: `scripts/schema_fingerprint.sh`
- Use: `.github/workflows/build.yml`
- Use: `scripts/deploy-production.sh`

- [ ] **Step 1: 确认发布前门禁**

确认 CI 全绿、目标提交三张镜像已构建、生产迁移窗口已开始、没有新的模型任务进入。记录迁移前
`TokenUsage` 行数、用户总数和当前 schema 指纹，只记录计数和指纹，不输出连接串或业务数据。

- [ ] **Step 2: 完成并验证可恢复备份**

在生产服务器仓库根目录使用现有脚本生成全量备份：

```bash
BACKUP_ROOT=/srv/backups/inkforge sh scripts/backup.sh
```

读取脚本输出的本次绝对备份目录，将其作为 `BACKUP_DIR`，再对独立验证库执行：

```bash
ALLOW_RESTORE_VERIFY=yes BACKUP_DIR="$BACKUP_DIR" sh scripts/restore_verify.sh
```

`DATABASE_URL`、`VERIFY_DATABASE_URL` 和可选 `UPLOADS_PATH` 只从维护终端现有环境取得，不在命令输出
或 CI 日志中展开。没有成功备份、校验和或独立恢复证据立即停止，不执行 DDL。

- [ ] **Step 3: 执行一次版本化事务迁移**

在生产服务器受控终端中，以 `.env` 的现有 `DATABASE_URL` 调用：

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/migrations/20260821_token_usage_task_run.sql
```

不得回显 `.env` 或连接串。迁移失败保持事务回滚，并停止新版本部署。

- [ ] **Step 4: 核验 Schema 与历史数据**

运行目标提交的只读 schema guard；确认旧 TokenUsage 行数不减少、历史新列为 NULL、新索引有效。核验失败
时在开放新写入前恢复备份并回到旧镜像。

- [ ] **Step 5: 部署并做一笔真实冒烟**

部署目标提交后，发起一个明确的小型模型任务，随后通过任务 usage API 和人工日志核对：同一 requestId、
相同 taskId/runId、四项 token 完全一致，CreditLedger 只扣一次。不得用大章生成作为首次冒烟。

- [ ] **Step 6: 恢复任务入口并观察**

恢复模型任务入口，观察至少一章完整的主写、双审和可能返工调用。确认每个 Provider 成功响应均有一条
TokenUsage 和一个日志区块；发现漏记或重复立即关闭新增查询/日志功能并切换到理解新 schema 的兼容镜像，
不删除新增列。
