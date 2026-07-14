# 异步任务持久恢复与后台任务监督实施计划

> **智能体执行要求：** 必须使用 `superpowers:executing-plans`，按任务逐项实施本计划，并使用复选框（`- [ ]`）跟踪进度。

**目标：** 让 Agent/Core 后台循环可被 readiness 监督，并让画像、质量检查和 RAG 队列任务在 Redis 投递丢失后从现有 PostgreSQL 事实恢复。

**架构：** 后台循环在循环边界捕获基础设施异常并受控退避，生命周期注册表保存真实 `asyncio.Task`；Core 分别以 `StylePortraitTask`、`WorkflowRun(kind=quality_check)`、`RagDocument` 为持久投递事实，dispatcher 使用稳定 job ID 幂等补投。PostgreSQL 仍是恢复权威，Redis 改为 `noeviction`，不新增或修改表、字段、索引。

**技术栈：** FastAPI lifespan、asyncio、SQLAlchemy 2 async、Redis、Pydantic、pytest、Ruff、Mypy、Docker Compose。

---

### Task 1: 让 Agent 消费循环从 Redis 瞬时故障恢复

**Files:**
- Modify: `apps/agent-service/tests/queue/test_consumer.py`
- Modify: `apps/agent-service/src/inkforge_agents/queue/consumer.py`

- [x] **Step 1: 写循环级故障注入测试**

Fake queue 第一次 `recover_expired()` 或 `claim()` 抛出连接异常，下一轮返回一个可处理任务。运行消费循环后等待任务完成并停止，断言 handler 被调用一次，consumer task 没有退出。

- [x] **Step 2: 运行测试并确认 RED**

Run: `uv run pytest apps/agent-service/tests/queue/test_consumer.py -q`

Expected: FAIL；当前 `run()` 让 `run_once()` 的基础设施异常直接终止协程。

- [x] **Step 3: 在循环边界增加有上限退避**

保留 `run_once()` 的单任务失败语义，只在 `run()` 捕获循环级异常；记录不含正文或密钥的中文结构化日志，失败后按 `min(base * 2**failures, max_backoff)` 等待，成功一轮后清零。等待必须能被 `request_stop()` 立即唤醒。

```python
try:
    processed = await self.run_once()
    infrastructure_failures = 0
except Exception as exc:
    infrastructure_failures += 1
    logger.exception("队列基础设施访问失败，等待后重试", extra={"errorCode": type(exc).__name__})
    await self._wait_or_stop(self._backoff(infrastructure_failures))
    continue
```

- [x] **Step 4: 验证**

Run: `uv run pytest apps/agent-service/tests/queue/test_consumer.py -q`

Run: `uv run ruff check apps/agent-service/src/inkforge_agents/queue/consumer.py apps/agent-service/tests/queue/test_consumer.py`

Expected: PASS。

### Task 2: 用真实任务状态驱动 Agent/Core readiness

**Files:**
- Create: `apps/core-api/src/inkforge_core/operations/background.py`
- Create: `apps/core-api/tests/operations/test_background.py`
- Modify: `apps/agent-service/src/inkforge_agents/app.py`
- Modify: `apps/agent-service/tests/test_health.py`
- Modify: `apps/core-api/src/inkforge_core/app.py`
- Modify: `apps/core-api/tests/test_health.py`
- Modify: `apps/core-api/tests/writing/test_reconciler.py`
- Modify: `apps/core-api/src/inkforge_core/writing/reconciler.py`

- [x] **Step 1: 写 Agent readiness 失败测试**

在 lifespan 内让 consumer task 意外返回或抛出异常，访问 `/internal/v1/health/ready`，断言 `queue_consumer` 为 `failed` 且响应 503。正常运行中的 task 仍为 200。

- [x] **Step 2: 写 Core 任务注册与恢复测试**

测试 `BackgroundTaskRegistry`：缺失、运行中、正常完成和异常完成分别映射到 `failed/ok/failed/failed`。给 `WritingRunReconciler` 注入一次 `list_reconcilable` 异常，下一轮返回任务，断言循环继续并成功提交。

- [x] **Step 3: 运行测试并确认 RED**

Run: `uv run pytest apps/agent-service/tests/test_health.py apps/core-api/tests/test_health.py apps/core-api/tests/operations/test_background.py apps/core-api/tests/writing/test_reconciler.py -q`

Expected: FAIL；readiness 只检查对象存在，Core 对账循环会被一次数据库错误杀死。

- [x] **Step 4: 实现后台任务注册表**

`BackgroundTaskRegistry` 只管理进程内监督信息，不持久化业务数据：

```python
@dataclass(slots=True)
class BackgroundTaskRegistration:
    name: str
    task: asyncio.Task[None]
    stop: Callable[[], None]

class BackgroundTaskRegistry:
    def start(self, name: str, worker: BackgroundWorker) -> None:
        self._items[name] = BackgroundTaskRegistration(
            name=name,
            task=asyncio.create_task(worker.run()),
            stop=worker.request_stop,
        )
    def readiness(self) -> bool:
        return all(not item.task.done() for item in self._items.values())
    async def stop_all(self) -> None:
        for item in self._items.values():
            item.stop()
        await asyncio.gather(
            *(item.task for item in self._items.values()),
            return_exceptions=True,
        )
```

关闭时先调用所有 `request_stop()`，再汇总等待注册表中的全部 task 并启用 `return_exceptions=True`；不直接取消正在运行的模型任务。

- [x] **Step 5: 接入两个应用生命周期**

Agent readiness 同时检查 `queue_consumer` 对象和 `consumer_task`：task 必须存在且未 `done()`。Core 把 writing reconciler、writing command dispatcher 以及后续三个 dispatcher 全部经注册表启动，并注册 `background_tasks` readiness check。

`WritingRunReconciler.run()` 采用现有 command dispatcher 的循环级异常边界，单条提交异常仍按原有逻辑隔离。

- [x] **Step 6: 验证并提交监督基础设施**

Run: `uv run pytest apps/agent-service/tests/test_health.py apps/core-api/tests/test_health.py apps/core-api/tests/operations/test_background.py apps/core-api/tests/writing/test_reconciler.py -q`

Run: `uv run mypy apps/core-api/src apps/agent-service/src`

```bash
git add apps/agent-service/src/inkforge_agents/queue/consumer.py apps/agent-service/src/inkforge_agents/app.py apps/agent-service/tests/queue/test_consumer.py apps/agent-service/tests/test_health.py apps/core-api/src/inkforge_core/operations/background.py apps/core-api/src/inkforge_core/writing/reconciler.py apps/core-api/src/inkforge_core/app.py apps/core-api/tests/operations/test_background.py apps/core-api/tests/writing/test_reconciler.py apps/core-api/tests/test_health.py
git commit -m "修复：监督后台任务并恢复基础设施异常"
```

### Task 3: 从 StylePortraitTask 恢复画像投递

**Files:**
- Create: `apps/core-api/src/inkforge_core/styles/portrait_dispatcher.py`
- Create: `apps/core-api/tests/styles/test_portrait_dispatcher.py`
- Modify: `apps/core-api/src/inkforge_core/styles/repository.py`
- Modify: `apps/core-api/src/inkforge_core/styles/service.py`
- Modify: `apps/core-api/src/inkforge_core/app.py`
- Modify: `apps/core-api/tests/styles/test_style_service.py`

- [x] **Step 1: 写首次提交失败后的恢复测试**

创建画像任务时 submitter 抛错，断言 API 仍返回持久 task ID、状态 `pending`。dispatcher 下一轮读取该记录并用同一 `portrait-{taskId}` 投递；第二次补投不创建新数据库任务。

- [x] **Step 2: 写 processing 防重测试**

dispatcher 默认只领取 `pending`。对于超过恢复阈值的 `processing`，仅当队列检查器确认稳定 job ID 不存在时才重投；队列仍有 active/completed job 时不得重投。已删除文风的级联记录不得被查询出来。

- [x] **Step 3: 运行测试并确认 RED**

Run: `uv run pytest apps/core-api/tests/styles/test_style_service.py apps/core-api/tests/styles/test_portrait_dispatcher.py -q`

Expected: FAIL；当前没有画像对账器。

- [x] **Step 4: 实现持久记录读取和 dispatcher**

仓储返回最小不可变记录：`task_id/style_id/user_id/section/status/updated_at`，查询必须 join `WritingStyle` 获取真实用户归属。dispatcher 对每条调用现有 `PortraitAgentSubmitter.submit`，传入 `user_id`、`style_id`、`task_id`、`run_id=task_id` 和 `section`；稳定 job ID 继续由 submitter 构造。单条失败记录错误码并保留 `pending`，不得把临时 Redis 错误写成业务终态。

- [x] **Step 5: 接入注册表并验证**

Run: `uv run pytest apps/core-api/tests/styles -q`

Run: `uv run ruff check apps/core-api/src/inkforge_core/styles apps/core-api/tests/styles`

Expected: PASS。

### Task 4: 用 WorkflowRun 持久化每次质量检查意图

**Files:**
- Create: `apps/core-api/src/inkforge_core/quality/dispatcher.py`
- Create: `apps/core-api/tests/quality/test_dispatcher.py`
- Modify: `apps/core-api/src/inkforge_core/quality/repository.py`
- Modify: `apps/core-api/src/inkforge_core/quality/service.py`
- Modify: `apps/core-api/src/inkforge_core/quality/internal_router.py`
- Modify: `apps/core-api/src/inkforge_core/agent_client.py`
- Modify: `apps/core-api/src/inkforge_core/app.py`
- Modify: `apps/core-api/tests/quality/test_quality_state.py`

- [x] **Step 1: 写持久输入和重复运行失败测试**

每次公开运行请求都在同一事务中创建新的 `WorkflowRun(kind="quality_check", status="pending")`，`input` 保存紧凑 JSON：

```json
{"checkId":"check-1","sourceTaskId":"task-1","message":"重点检查时间线"}
```

同一检查项前一次完成后再次运行，断言得到不同 WorkflowRun ID 和 `quality-{runId}` job ID，不复用旧 completed job。

- [x] **Step 2: 写 Redis 丢失恢复和回调收敛测试**

dispatcher 读取 pending/running 记录，重建完整 payload 并按 run ID 幂等投递。成功提交推进 `running`；Agent success/failure 回调用 body 中的 `runId` 同时收敛 `ChapterQualityCheck` 与对应 `WorkflowRun`。输入损坏时将该 run 标为 failed，并记录不含用户正文的诊断原因，不猜测投递。

- [x] **Step 3: 运行测试并确认 RED**

Run: `uv run pytest apps/core-api/tests/quality -q`

Expected: FAIL；当前只用 `quality-{checkId}` 直接投递，没有持久运行事实。

- [x] **Step 4: 实现事务创建与 dispatcher**

把 `authorize_run` 与创建 WorkflowRun 合并成仓储事务方法，先完成所有归属/绑定校验，再插入记录。`QualityService.run()` 不因首次投递失败撤销持久事实；可尝试立即 `dispatch(run_id)` 降低延迟，失败后由后台循环补投。

`QualityAgentSubmitter.submit` 改接收 `run_id`，并设置：

```python
jobId=f"quality-{run_id}"
runId=run_id
taskId=source_task_id or run_id
```

- [x] **Step 5: 接入 callback 和监督注册表**

内部回调先验证服务令牌和资源绑定，再锁定 `WorkflowRun.id == body.runId` 且其 input 中的 checkId 匹配 URL。重复终态回调保持幂等，不允许一个 run 收敛别的检查项。

- [x] **Step 6: 验证并提交质量检查持久化**

Run: `uv run pytest apps/core-api/tests/quality apps/agent-service/tests/jobs/test_quality.py -q`

Run: `uv run mypy apps/core-api/src apps/agent-service/src`

```bash
git add apps/core-api/src/inkforge_core/quality apps/core-api/src/inkforge_core/agent_client.py apps/core-api/src/inkforge_core/app.py apps/core-api/tests/quality
git commit -m "修复：持久化并恢复质量检查任务"
```

### Task 5: 从 RagDocument 恢复当前内容版本的索引任务

**Files:**
- Create: `apps/core-api/src/inkforge_core/references/rag_dispatcher.py`
- Create: `apps/core-api/tests/references/test_rag_dispatcher.py`
- Modify: `apps/core-api/src/inkforge_core/references/repository.py`
- Modify: `apps/core-api/src/inkforge_core/references/service.py`
- Modify: `apps/core-api/src/inkforge_core/app.py`
- Modify: `apps/core-api/tests/references/test_rag.py`

- [x] **Step 1: 写当前哈希恢复测试**

配置 embedding 服务时，创建或影响索引的更新先将文档置为 `disabled`、`errorMessage="等待重新索引"`，再尝试投递。首次提交失败后 dispatcher 只补投当前 `contentHash`；旧哈希、`failed/ready` 或“服务未配置”的记录都不投递。

- [x] **Step 2: 运行测试并确认 RED**

Run: `uv run pytest apps/core-api/tests/references/test_rag.py apps/core-api/tests/references/test_rag_dispatcher.py -q`

Expected: FAIL；当前创建/更新的投递失败没有统一可扫描标记和对账器。

- [x] **Step 3: 实现明确的待索引状态**

仓储新增批量读取方法，join `ReferenceMaterial` 和 `Novel` 返回 `user_id/novel_id/reference_id/content_hash`，where 条件固定为：

```python
RagDocument.sourceType == "reference_material"
RagDocument.status == "disabled"
RagDocument.errorMessage == "等待重新索引"
RagDocument.contentHash == content_sha256(ReferenceMaterial.content)  # 在领取后再次校验
```

未配置 submitter 时创建/更新保持“服务未配置”语义，不进入 dispatcher 忙循环。完成和失败回调继续由现有哈希校验拒绝过期任务。

- [x] **Step 4: 接入 dispatcher 并验证**

稳定 ID 继续使用 `sha256("rag:{referenceId}:{contentHash}")`，不得引入随机 ID。

Run: `uv run pytest apps/core-api/tests/references apps/agent-service/tests/jobs/test_rag.py -q`

Expected: PASS。

### Task 6: 禁止 Redis 淘汰关键任务键

**Files:**
- Modify: `infra/redis/redis.conf`
- Modify: `tests/architecture/test_compose_security.py`
- Modify: `docs/requirements/03-ai-writing-and-agents.md`
- Modify: `docs/requirements/04-review-quality-and-workflow.md`
- Modify: `docs/requirements/05-deployment-and-operations.md`
- Modify: `apps/agent-service/AGENTS.md`

- [x] **Step 1: 写架构失败测试**

```python
assert re.search(r"(?m)^maxmemory-policy\s+noeviction$", redis_config)
assert "allkeys-lru" not in redis_config
```

- [x] **Step 2: 运行测试并确认 RED**

Run: `uv run pytest tests/architecture/test_compose_security.py -q`

- [x] **Step 3: 修改策略并同步权威文档**

仅把淘汰策略改为 `noeviction`，保持 `maxmemory 64mb` 和 `appendonly no`。文档说明 PostgreSQL 持久事实、dispatcher 补投、后台 task readiness，以及必须监控 `used_memory`、`evicted_keys` 和 Redis 拒绝写入次数。

- [x] **Step 4: 验证并提交**

Run: `uv run pytest tests/architecture/test_compose_security.py tests/architecture/test_agent_db_boundary.py -q`

```bash
git add infra/redis/redis.conf tests/architecture/test_compose_security.py docs/requirements/03-ai-writing-and-agents.md docs/requirements/04-review-quality-and-workflow.md docs/requirements/05-deployment-and-operations.md apps/agent-service/AGENTS.md
git commit -m "修复：禁止 Redis 淘汰持久任务键"
```

### Task 7: 运行时可靠性全量验证

**Files:**
- Verify only

- [x] **Step 1: 定向测试**

Run: `uv run pytest apps/agent-service/tests/queue apps/agent-service/tests/test_health.py apps/core-api/tests/styles apps/core-api/tests/quality apps/core-api/tests/references apps/core-api/tests/writing/test_reconciler.py apps/core-api/tests/test_health.py tests/architecture/test_compose_security.py -q`

- [x] **Step 2: Python 全量质量门**

Run: `uv run pytest`

Run: `uv run ruff check .`

Run: `uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src`

Expected: 全部 PASS；`schema-contract.json` 和现有迁移文件没有变化。
