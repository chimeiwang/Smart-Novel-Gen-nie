# 中短篇运行日志与异常收敛实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 修复中短篇首个模型响应写日志时崩溃的问题，并保证运行层异常不会让 Agent 队列与 Core 任务长期处于不一致状态。

**架构：** 中短篇处理器复用现有 `WorkflowLogPort`，在模型运行前创建日志段，在成功、失败和重试出口结束日志。明确带有 `retryable/recoverable=True` 的基础设施异常继续交给队列重试；其他运行异常在处理器掌握的事件序号处转换为稳定的中短篇失败，先回调 Core，再由队列终态化。应用装配显式注入同一个 `HumanWorkflowLog`，不修改 Redis Lua、Core 数据库结构或公共接口。

**技术栈：** Python 3.12、FastAPI、Pydantic、pytest、Ruff、Mypy、现有 Redis 作业队列与 Core 内部回调。

---

## 文件边界

- 修改 `apps/agent-service/src/inkforge_agents/jobs/short_medium.py`：拥有中短篇日志生命周期和运行异常分类。
- 修改 `apps/agent-service/src/inkforge_agents/app.py`：把现有 `workflow_log` 注入中短篇处理器。
- 修改 `apps/agent-service/tests/short_medium/test_graph.py`：覆盖真实模型日志桥接、成功/回放/失败日志终态和异常分类。
- 修改 `apps/agent-service/tests/test_health.py`：保护生产装配，防止以后再次漏掉日志注入。
- 不修改队列消费者、Redis 脚本、Core 公共接口和 PostgreSQL schema。

### 任务一：用回归测试锁定日志崩溃和异常边界

**文件：**

- 修改：`apps/agent-service/tests/short_medium/test_graph.py`

- [ ] **步骤 1：增加真实日志桥接失败测试**

在测试文件中引入 `Path`、`HumanWorkflowLog`、`WorkflowModelObserver`、`FakeModelProvider` 和
`ModelRuntime`，使用现有 `Core` 和大纲任务构造真实调用链：

```python
workflow_log = HumanWorkflowLog(tmp_path)
runtime = ModelRuntime(
    FakeModelProvider(),
    observer=WorkflowModelObserver(workflow_log),
)
handler = ShortMediumWritingJobHandler(
    core,
    ModelShortMediumGenerator(runtime, max_output_tokens=12_345),
    workflow_log=workflow_log,
)

await handler(outline_job)

runs = workflow_log.list_runs("user-1")
assert len(core.checkpoints) == 1
assert len(core.completions) == 1
assert core.failures == []
assert len(runs) == 1
assert runs[0].status == "完成"
assert "模拟模型已完成本轮处理。" in workflow_log.read_run(
    "run-short-1", "user-1"
).content
```

修复前预期失败点是处理器不接受 `workflow_log`，或模型观察器因没有 `start_run` 抛出
`LookupError`。

- [ ] **步骤 2：增加未分类异常先结算 Core 的测试**

增加生成器：

```python
class RaisingGenerator:
    async def generate(self, resource: object, request: object) -> ModelTurnResult:
        del resource, request
        raise RuntimeError("模型运行异常")
```

调用处理器并断言：

```python
with pytest.raises(NonRetryableJobError):
    await handler(manuscript_job(15_000))

assert core.completions == []
assert core.failures == [("job-short-1", 2, "SHORT_MEDIUM_RUN_FAILED")]
assert workflow_log.list_runs("user-1")[0].status == "错误"
```

- [ ] **步骤 3：增加显式可恢复异常原样透传测试**

让生成器抛出：

```python
failure = CoreServiceError("核心服务暂时不可用", recoverable=True)
```

断言处理器抛出的仍是同一异常、不额外调用 `core.fail`，并且本次日志以“等待重试”结束：

```python
with pytest.raises(CoreServiceError) as caught:
    await handler(manuscript_job(15_000))

assert caught.value is failure
assert core.failures == []
assert workflow_log.list_runs("user-1")[0].status == "等待重试"
```

- [ ] **步骤 4：增加失败回调暂时不可用测试**

覆盖 `Core.fail()`，让未分类模型错误触发失败回调后，该回调抛
`CoreServiceError(recoverable=True)`。断言最终的 `CoreServiceError` 保持可恢复，供
`QueueConsumer` 重试；不能被转换成 `NonRetryableJobError`。

- [ ] **步骤 5：运行测试确认红灯**

运行：

```bash
uv run pytest apps/agent-service/tests/short_medium/test_graph.py -q
```

预期：新增测试失败，现有测试继续通过；失败原因指向缺少 `workflow_log` 构造参数、没有日志生命周期或
未分类异常没有 Core 失败回调。

### 任务二：实现处理器日志生命周期和异常收敛

**文件：**

- 修改：`apps/agent-service/src/inkforge_agents/jobs/short_medium.py`
- 测试：`apps/agent-service/tests/short_medium/test_graph.py`

- [ ] **步骤 1：给处理器注入现有日志端口**

增加导入和构造参数：

```python
from .workflow_log import WorkflowLogPort

class ShortMediumWritingJobHandler:
    def __init__(
        self,
        core: CoreClientPort,
        generator: GeneratorPort,
        *,
        workflow_log: WorkflowLogPort | None = None,
    ) -> None:
        self._core = core
        self._generator = generator
        self._workflow_log = workflow_log
```

- [ ] **步骤 2：在模型执行前初始化日志段**

在确认 `job.kind == "writing"` 后、读取 Core 上下文和模型调用前执行：

```python
self._start_log(job)
```

辅助方法只读取作业自带的稳定身份：

```python
def _start_log(self, job: QueueJob) -> None:
    if self._workflow_log is None:
        return
    operation = job.payload.get("operation")
    operation_name = operation if isinstance(operation, str) else "unknown"
    chapter_id = job.payload.get("chapterId")
    self._workflow_log.start_run(
        run_id=job.runId,
        task_id=job.taskId,
        run_kind=f"中短篇：{operation_name}",
        user_id=job.userId,
        novel_id=job.novelId,
        chapter_id=chapter_id if isinstance(chapter_id, str) else None,
    )
```

每次队列重领会在同一 `runId` 文件追加一个新的运行段，不另建日志文件。

- [ ] **步骤 3：分类运行异常并保留准确事件序号**

把 `agent_start`、分段生成、checkpoint 和完成回调纳入 `_run()` 的同一个异常边界。保持
`_ShortMediumFailure` 原逻辑；明确可恢复异常原样抛出；其他异常转换成带下一事件序号的稳定失败：

```python
except _ShortMediumFailure as exc:
    exc.sequence = sequence + 1
    raise
except Exception as exc:
    if _is_explicitly_retryable(exc):
        raise
    raise _ShortMediumFailure(
        "SHORT_MEDIUM_RUN_FAILED",
        str(exc) or "中短篇运行失败",
        sequence=sequence + 1,
    ) from exc
```

辅助判断同时支持队列现有的两个契约字段：

```python
def _is_explicitly_retryable(exc: Exception) -> bool:
    return getattr(exc, "retryable", None) is True or getattr(
        exc, "recoverable", None
    ) is True
```

- [ ] **步骤 4：在所有处理器出口结束日志**

成功和已完成 checkpoint 回放后写“完成”；`_ShortMediumFailure` 回调 Core 后写“错误”；
显式可恢复异常写“等待重试”。失败回调本身抛异常时使用 `finally` 保证本次日志仍有结束状态，
同时保留回调异常本身：

```python
except _ShortMediumFailure as exc:
    try:
        await self._core.fail(
            resource,
            sequence=exc.sequence or _next_sequence(snapshot),
            code=exc.code,
            message=str(exc),
            recoverable=False,
        )
    finally:
        self._finish_log(job.runId, "错误")
    raise NonRetryableJobError("中短篇运行失败已上报核心服务") from exc
except Exception as exc:
    self._finish_log(
        job.runId,
        "等待重试" if _is_explicitly_retryable(exc) else "错误",
    )
    raise
else:
    self._finish_log(job.runId, "完成")
```

`asyncio.CancelledError` 不属于普通 `Exception`，继续由队列租约过期恢复，不伪造业务失败。

- [ ] **步骤 5：运行短篇测试确认绿灯**

运行：

```bash
uv run pytest apps/agent-service/tests/short_medium/test_graph.py \
  apps/agent-service/tests/short_medium/test_selection.py \
  apps/agent-service/tests/jobs/test_short_medium.py -q
```

预期：全部通过。

- [ ] **步骤 6：提交处理器和测试**

```bash
git add apps/agent-service/src/inkforge_agents/jobs/short_medium.py \
  apps/agent-service/tests/short_medium/test_graph.py
git commit -m "修复：收敛中短篇运行异常"
```

### 任务三：保护应用装配

**文件：**

- 修改：`apps/agent-service/src/inkforge_agents/app.py`
- 修改：`apps/agent-service/tests/test_health.py`

- [ ] **步骤 1：增加装配红灯测试**

扩展 `test_应用装配向模型运行时传入相同输出预算`，用捕获类替换
`ModelShortMediumGenerator` 和 `ShortMediumWritingJobHandler`：

```python
class CapturingShortMediumHandler:
    def __init__(
        self,
        core: object,
        generator: object,
        *,
        workflow_log: object | None = None,
    ) -> None:
        del core, generator
        captured["short_log"] = workflow_log is not None

    async def __call__(self, job: object) -> None:
        del job
```

断言 `captured["short_log"] is True`。修复前预期为 `False`。

- [ ] **步骤 2：把同一个日志实例注入中短篇处理器**

修改应用装配：

```python
short_medium_writing = ShortMediumWritingJobHandler(
    core,
    ModelShortMediumGenerator(
        model_runtime,
        max_output_tokens=settings.model_max_output_tokens,
    ),
    workflow_log=workflow_log,
)
```

- [ ] **步骤 3：运行装配与日志测试**

运行：

```bash
uv run pytest apps/agent-service/tests/test_health.py \
  apps/agent-service/tests/observability/test_model_log_bridge.py \
  apps/agent-service/tests/integration/test_debug_logs.py -q
```

预期：全部通过。

- [ ] **步骤 4：提交装配保护**

```bash
git add apps/agent-service/src/inkforge_agents/app.py \
  apps/agent-service/tests/test_health.py
git commit -m "测试：保护中短篇日志装配"
```

### 任务四：全量验证与现场恢复

**文件：**

- 不新增代码文件。

- [ ] **步骤 1：运行 Agent 相关回归**

```bash
uv run pytest apps/agent-service/tests/short_medium \
  apps/agent-service/tests/jobs/test_short_medium.py \
  apps/agent-service/tests/queue/test_consumer.py \
  apps/agent-service/tests/queue/test_repository.py \
  apps/agent-service/tests/test_health.py \
  apps/agent-service/tests/observability \
  apps/agent-service/tests/integration/test_debug_logs.py -q
```

预期：全部通过。

- [ ] **步骤 2：运行静态检查**

```bash
uv run ruff check apps/agent-service/src/inkforge_agents/jobs/short_medium.py \
  apps/agent-service/src/inkforge_agents/app.py \
  apps/agent-service/tests/short_medium/test_graph.py \
  apps/agent-service/tests/test_health.py
uv run mypy apps/agent-service/src packages/service-contracts/src packages/service-auth/src
```

预期：Ruff 和 Mypy 均无错误。

- [ ] **步骤 3：确认没有越界改动**

```bash
git status --short
git diff --check HEAD
```

预期：不包含数据库 schema、Redis Lua 或公共接口改动；保留用户原有
`apps/web/next-env.d.ts` 修改且不纳入提交。

- [ ] **步骤 4：让旧任务通过现有持久命令对账收敛**

读取原任务 `cms73qj3548urrbgrwwp3b0r6` 的公共任务状态。默认命令调度器会在活动命令陈旧
10 分钟后重新查询同一 Agent job；Agent 返回 `failed` 后，Core 将命令和任务置为错误终态。
不得重开原 Redis terminal job，也不得直接修改数据库。

- [ ] **步骤 5：使用新请求 ID 重启故事大纲生成**

旧任务进入错误终态后，对作品 `cms73p8j748ukrbgrr0sabm4j` 使用新的
`clientRequestId` 启动 `generate_outline`。观察到持久成功终态和候选版本后，展示完整 Diff 与
`confirmationHash`，等待用户确认；不得自动采用候选版本。

## 自检结果

- 规格覆盖：日志初始化、成功/回放/失败结束、显式重试、未分类异常 Core 结算、旧任务对账和新请求重启
  均有对应任务。
- 范围控制：没有修改消费者的未知异常策略，没有重开 Redis terminal job，没有数据库或公共契约改动。
- 类型一致性：处理器新增的参数统一为 `workflow_log: WorkflowLogPort | None`；生产装配和测试捕获类均使用
  关键字参数 `workflow_log`。
- 占位符检查：计划不含待定实现或省略的测试命令。
