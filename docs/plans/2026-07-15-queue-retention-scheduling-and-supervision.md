# 队列保留、调度与后台监督实施计划

> **面向智能体执行者：** 必须先增加失败测试并观察正确失败，再写最小实现；队列、消费者和监督器分别完成回归后再集成。

**目标：** 限制 Redis 终态内存、消除延迟重试队头阻塞，并让 Core/Agent 后台协程崩溃后受控重启。

**架构：** 保留现有 ready ZSET 复合 score；claim 按 100 个优先级区间查询已到期任务。终态使用时间 ZSET 维护 7 天 tombstone 并有界清理。两个服务各自使用 coroutine factory 监督器，未知异常退出工作循环后由监督器退避重启。

**技术栈：** Python asyncio、Redis Lua、FastAPI lifespan、pytest。

**状态：** 已完成实现、独立交叉审查和相关验证；全仓 TypeScript 类型检查受章节测试的已知类型标注问题影响。

---

### 任务 1：终态 tombstone 与有界清理

**文件：**

- 修改：`apps/agent-service/src/inkforge_agents/queue/repository.py`
- 测试：`apps/agent-service/tests/queue/test_repository.py`

- [ ] 先写失败测试：ack/cancel 删除 payload、lease、attempt、score 和队列索引，只留下 status 与终态时间；窗口内重复 enqueue 被拒绝；截止时间后 purge 删除全部终态字段。
- [ ] 运行 repository 测试并确认当前 score/status 永久残留。
- [ ] 新增 terminal ZSET 和 `purge_terminal(cutoff)`；ack/cancel Lua 接收当前时间并原子维护 tombstone，清理脚本使用有限批次。
- [ ] 默认保留 7 天且配置不得少于 24 小时，重跑 repository 测试。

### 任务 2：消除延迟重试队头阻塞

**文件：**

- 修改：`apps/agent-service/src/inkforge_agents/queue/repository.py`
- 测试：`apps/agent-service/tests/queue/test_repository.py`

- [ ] 先写失败测试：未来 priority=0 与已到期 priority=10 并存时立即领取后者；同级按 readyAt；retry 更新恢复 score。
- [ ] 运行测试确认现有 `ZRANGE 0 0` 返回未来任务后直接空转。
- [ ] claim Lua 对 priority 0..99 使用 `ZRANGEBYSCORE` 的 `[priority*factor, priority*factor+now]` 区间；坏 payload/status 被清理后继续查找。
- [ ] retry 同时更新 score Hash，recover_expired 继续按最新 score 恢复，重跑测试。

### 任务 3：修正消费者异常分类

**文件：**

- 修改：`apps/agent-service/src/inkforge_agents/queue/consumer.py`
- 测试：`apps/agent-service/tests/queue/test_consumer.py`

- [ ] 先写失败测试：`CoreServiceError(recoverable=False)` 不重试；一次 Redis 暂态异常后下一轮继续；未知 TypeError 退出循环。
- [ ] 运行测试确认当前读取不存在的 `retryable` 或吞掉所有 Exception。
- [ ] 正确映射 `recoverable`，只捕获明确基础设施异常；CancelledError/SystemExit/KeyboardInterrupt 和未知程序错误向监督器传播。
- [ ] 在受控间隔调用 terminal purge，重跑 consumer 测试。

### 任务 4：Core 后台监督器

**文件：**

- 修改：`apps/core-api/src/inkforge_core/operations/background.py`
- 修改：`apps/core-api/src/inkforge_core/app.py`
- 测试：`apps/core-api/tests/operations/test_background.py`
- 测试：`apps/core-api/tests/test_health.py`

- [ ] 先写失败测试：worker 首次崩溃后退避重启；退避中 readiness 失败；shutdown 不重启；不会并行运行两个同名 worker。
- [ ] 把一次性 coroutine 改为 factory，监督器维护当前 inner task、失败计数和停止标记，按 1/2/4/8/30 秒退避。
- [ ] 稳定运行 60 秒后清零失败计数，readiness 根据 supervisor/inner 状态返回稳定错误码。
- [ ] 重跑 Core background/health 测试。

### 任务 5：Agent 消费者监督器

**文件：**

- 修改：`apps/agent-service/src/inkforge_agents/app.py`
- 可新增：`apps/agent-service/src/inkforge_agents/supervision.py`
- 测试：`apps/agent-service/tests/test_health.py`

- [ ] 先写与 Core 同语义的失败测试，覆盖崩溃重启、退避未就绪、shutdown 和单实例。
- [ ] 实现 Agent 本地监督器，使用 consumer coroutine factory，保持一次只处理一个模型任务。
- [ ] 重跑 Agent health 测试。

### 任务 6：需求同步与验证

**文件：**

- 修改：`docs/requirements/05-auth-billing-and-ops.md`
- 修改：`apps/agent-service/AGENTS.md`

- [ ] 写明终态保留窗口、无队头阻塞、异常分类和重启验收，不触碰 TLS/备案章节。
- [ ] 运行：

```powershell
uv run pytest apps/agent-service/tests/queue apps/agent-service/tests/test_health.py apps/core-api/tests/operations/test_background.py apps/core-api/tests/test_health.py -q
uv run ruff check .
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
```
