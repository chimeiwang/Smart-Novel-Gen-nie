# 写作回调身份与 SSE 恢复实施计划

> **面向智能体执行者：** 必须使用 `subagent-driven-development` 或等价的分任务执行方式，并为每个行为遵循 `test-driven-development` 的失败测试、最小实现、回归验证顺序。

**目标：** 让旧写作 job 无法修改新命令，并让 Redis 丢失后当前 job 能从 PostgreSQL 检查点继续事件序号。

**架构：** 回调协议 1.1 显式携带 `jobId`。Core 按 `taskId + jobId` 锁定精确命令，并在更新 checkpoint 前校验持久事件序号；Redis 序号键缺失时只允许已通过数据库身份校验的当前 job 重建基线。

**技术栈：** Pydantic、FastAPI、SQLAlchemy async、Redis Lua、pytest。

**状态：** 已完成主要实现和独立交叉审查；保留“检查点已入库但 Redis 事件发布失败时，终态重试未先补发检查点”的已知风险。

---

### 任务 1：升级回调契约

**文件：**

- 修改：`packages/service-contracts/src/inkforge_contracts/events.py`
- 修改：`packages/service-contracts/contracts/writing-sse-events.json`
- 测试：`packages/service-contracts/tests/test_event_contracts.py`
- 测试：`packages/service-contracts/tests/test_writing_sse_examples.py`

- [ ] 先为四类回调增加失败测试，断言 `protocolVersion="1.1"` 和必填 `jobId`；缺少 jobId、使用 1.0 都应验证失败。
- [ ] 运行 `uv run pytest packages/service-contracts/tests/test_event_contracts.py packages/service-contracts/tests/test_writing_sse_examples.py -q`，确认失败原因是契约尚未升级。
- [ ] 把四个 Pydantic 模型改为以下共同信封字段，并同步 JSON 样例：

```python
protocolVersion: Literal["1.1"]
eventId: Identifier
jobId: Identifier
runId: Identifier
taskId: Identifier
sequence: PositiveInt
```

- [ ] 重跑上述测试并确认通过。

### 任务 2：从 QueueJob 透传 jobId

**文件：**

- 修改：`apps/agent-service/src/inkforge_agents/clients/core.py`
- 修改：`apps/agent-service/src/inkforge_agents/jobs/writing.py`
- 测试：`apps/agent-service/tests/integration/test_core_callbacks.py`
- 测试：`apps/agent-service/tests/jobs/test_writing.py`

- [ ] 先写失败测试，断言 `QueueJob.jobId` 出现在 `RunResource` 和 event/checkpoint/complete/fail 四类请求 JSON 中。
- [ ] 运行两个定向测试文件，确认当前因 RunResource 无 jobId 或回调载荷缺字段失败。
- [ ] 给 `RunResource` 增加可验证的 `jobId`，WritingJobHandler 使用 `job.jobId` 构造资源，四类 CoreServiceClient 回调均设置 `jobId=resource.jobId`。
- [ ] 重跑定向测试并确认通过。

### 任务 3：精确命令身份与 checkpoint 单调性

**文件：**

- 修改：`apps/core-api/src/inkforge_core/writing/tasks.py`
- 修改：`apps/core-api/src/inkforge_core/writing/callbacks.py`
- 新增：`apps/core-api/tests/writing/test_callback_identity.py`
- 修改：`apps/core-api/tests/writing/test_sse.py`

- [ ] 先写失败测试：命令 A 已终态、命令 B 活动时，A 的 event/checkpoint/complete/fail 均返回幂等结果，B 与 WritingTask 不变。
- [ ] 先写失败测试：当前快照 `eventSequence=20` 时，sequence 10、bool、缺失值或 checkpoint 内值与回调不一致均不能覆盖快照。
- [ ] 运行定向测试，确认失败来自现有 `_transition_active_command()` 按 taskId 选择任意活动命令和缺少序号校验。
- [ ] 把仓储入口改为显式接收 `job_id`，查询条件至少包含：

```python
WritingRunCommand.id == job_id
WritingRunCommand.taskId == task_id
```

- [ ] 增加严格序号解析辅助函数，拒绝 bool、负数和不相等的 callback/checkpoint 序号；旧 job 或回退 checkpoint 返回无副作用处置结果。
- [ ] 确保 completion/failure 的精确旧命令重试不会触碰后来的活动命令。
- [ ] 重跑 Core 定向测试并确认通过。

### 任务 4：Redis 丢失后的安全 rebase

**文件：**

- 修改：`apps/core-api/src/inkforge_core/writing/sse.py`
- 修改：`apps/core-api/src/inkforge_core/writing/tasks.py`
- 测试：`apps/core-api/tests/writing/test_sse.py`

- [ ] 先写失败测试：持久 baseline=20、Redis 流/序号/来源键为空时，当前 job 的 sequence 21 可以追加；旧 job 或 sequence <=20 不能重建。
- [ ] 运行测试，确认当前 Lua 因缺失 key 固定使用 last=0 而失败。
- [ ] 为事件存储增加显式 durable baseline/rebase 参数。Lua 在 key 存在时保持严格 `last + 1`；key 缺失时只接受服务层已验证的 rebase，并用 CAS 建立基线。
- [ ] 增加“数据库已提交、Redis 首次失败、同一 job 重试”的幂等测试。
- [ ] 重跑全部写作相关定向测试。

### 任务 5：文档与全量验证

**文件：**

- 修改：`docs/requirements/03-ai-writing-and-agents.md`
- 修改：`docs/requirements/04-review-quality-and-workflow.md`
- 修改：`apps/agent-service/AGENTS.md`

- [ ] 把 jobId 身份、checkpoint 单调性和 Redis rebase 故障验收写入当前需求与 Agent 架构文档。
- [ ] 运行：

```powershell
uv run pytest packages/service-contracts/tests apps/core-api/tests/writing apps/agent-service/tests/jobs/test_writing.py apps/agent-service/tests/integration/test_core_callbacks.py -q
uv run ruff check .
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
```
