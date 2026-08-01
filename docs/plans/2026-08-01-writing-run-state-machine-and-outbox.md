# 写作运行状态机与事务 Outbox 实施计划

> **执行要求：** 所有行为修改遵循失败测试、最小实现、回归验证顺序；数据库 DDL 只在代码、迁移演练和备份验证完成后执行。

**目标：** 建立 PostgreSQL 权威 outcome、显式 callback receipt 和事务 Outbox，使业务完成不再依赖 Redis SSE 双写成功。

**架构：** Core 以 workflow-aware projector 解释任务、当前命令和真实产物；持久业务边界与 Outbox 同事务提交；后台 publisher 幂等写 Redis；SSE 直接投影 PostgreSQL outcome 控制生命周期。

**技术栈：** FastAPI、Pydantic、SQLAlchemy async、PostgreSQL 14、Redis Lua、Next.js/React、pytest、Node test runner。

**状态：** 已完成。下列复选框保留实施前的 TDD 执行顺序，最终验收以规格、自动化门禁和提交记录为准。

---

### 任务 1：冻结状态机与回调回执契约

**文件：**

- 修改：`packages/service-contracts/src/inkforge_contracts/events.py`
- 修改：`packages/service-contracts/tests/test_event_contracts.py`
- 修改：`apps/core-api/src/inkforge_core/writing/schemas.py`
- 新增：`apps/core-api/tests/writing/test_outcome.py`

- [ ] 先写 CallbackReceipt 和 WritingRunOutcome 的失败契约测试。
- [ ] 运行定向测试，确认因契约或 projector 尚不存在而失败。
- [ ] 增加版本化 receipt、outcome、command/result 投影模型。
- [ ] 定义长篇和中短篇分别适用的真值表，覆盖 inconsistent。
- [ ] 重跑定向测试并确认通过。

### 任务 2：新增 Outbox ORM、迁移与仓储

**文件：**

- 修改：`apps/core-api/src/inkforge_core/db/models.py`
- 修改：`apps/core-api/src/inkforge_core/db/__init__.py`
- 修改：`apps/core-api/src/inkforge_core/db/schema_guard.py`
- 新增：`apps/core-api/src/inkforge_core/writing/outbox.py`
- 新增：`apps/core-api/tests/writing/test_outbox.py`
- 新增：`scripts/migrations/20260801_writing_event_outbox.sql`

- [ ] 先写 ORM 元数据、唯一约束、同任务领取顺序、租约恢复和幂等失败测试。
- [ ] 运行定向测试并确认失败原因是新表和仓储尚不存在。
- [ ] 实现 `WritingEventOutbox`、事务插入、lease claim、published/retry/blocked/superseded。
- [ ] 实现 1..60 秒退避和 7 天已发布清理，不清理未完成行。
- [ ] 编写单事务 additive SQL，不加入运行时自动建表。
- [ ] 重跑定向测试。

### 任务 3：把边界回调收敛为业务事务加 Outbox

**文件：**

- 修改：`apps/core-api/src/inkforge_core/writing/tasks.py`
- 修改：`apps/core-api/src/inkforge_core/writing/callbacks.py`
- 修改：`apps/core-api/tests/writing/test_callback_identity.py`
- 修改：`apps/core-api/tests/writing/test_sse.py`
- 修改：`apps/agent-service/src/inkforge_agents/clients/core.py`
- 修改：`apps/agent-service/src/inkforge_agents/jobs/writing.py`
- 修改：`apps/agent-service/tests/integration/test_core_callbacks.py`
- 修改：`apps/agent-service/tests/jobs/test_writing.py`

- [ ] 先写失败测试：无副作用不能再返回可确认的空成功；Agent 缺少合法 receipt 不能 ack。
- [ ] 先写失败测试：complete/fail/waiting 的业务状态和 Outbox 同事务回滚、重复回调幂等。
- [ ] Core 回调返回 applied/already_applied/rejected，并保留稳定 reasonCode。
- [ ] complete、fail 和 waiting checkpoint 在事务内插入 Outbox，移除对应直接 boundary 发布。
- [ ] Agent waiting 路径不再先发送 boundary event；使用最终 checkpoint 触发 Core Outbox。
- [ ] Agent 只接受 applied/already_applied；旧 204 作为可恢复错误。
- [ ] 重跑 Core 和 Agent 定向测试。

### 任务 4：实现并监督 Outbox publisher

**文件：**

- 修改：`apps/core-api/src/inkforge_core/writing/outbox.py`
- 修改：`apps/core-api/src/inkforge_core/writing/sse.py`
- 修改：`apps/core-api/src/inkforge_core/app.py`
- 修改：`apps/core-api/tests/writing/test_outbox.py`
- 修改：`apps/core-api/tests/test_health.py`

- [ ] 先写失败测试：SKIP LOCKED claim、同 task 严格顺序、不同 task 可推进、租约 token 防旧 worker 回写。
- [ ] 先写失败测试：Redis 失败退避、Lua duplicate 补标、确定性错误 blocked、stale waiting superseded。
- [ ] 实现 publisher worker、轮询调度、readiness 和优雅停止。
- [ ] 复用来源事件 Lua 幂等，不修改业务聚合。
- [ ] 重跑 publisher、SSE 和应用生命周期测试。

### 任务 5：统一 GET outcome 与 SSE 控制帧

**文件：**

- 新增：`apps/core-api/src/inkforge_core/writing/outcome.py`
- 修改：`apps/core-api/src/inkforge_core/writing/commands.py`
- 修改：`apps/core-api/src/inkforge_core/writing/tasks.py`
- 修改：`apps/core-api/src/inkforge_core/writing/router.py`
- 修改：`apps/core-api/src/inkforge_core/writing/sse.py`
- 修改：`apps/core-api/tests/writing/test_outcome.py`
- 修改：`apps/core-api/tests/writing/test_sse.py`

- [ ] 先写长篇、中短篇和 artifact_decision currentCommand 真值表失败测试。
- [ ] 实现只读 PostgreSQL projector，不读取 Redis/Outbox。
- [ ] GET additive 返回 outcome，并保留 raw 兼容字段。
- [ ] SSE 建连、变化和关闭前发送无 id 的 run_outcome；只按 streamShouldClose 结束。
- [ ] 覆盖 Redis 空、Outbox pending、产物缺失和 stale boundary。

### 任务 6：迁移 Web 消费者

**文件：**

- 修改：`apps/web/src/shared/contracts/sse-events.ts`
- 修改：`apps/web/src/shared/contracts/__tests__/sse-events.test.ts`
- 修改：`apps/web/src/features/writing/writing-conversation.tsx`
- 修改：`apps/web/src/features/short-medium/short-medium-workspace.tsx`
- 新增或修改相关 `apps/web/src/features/**/__tests__/*.test.ts`

- [ ] 先写 run_outcome 解析、等待结束和 inconsistent 展示失败测试。
- [ ] 长篇事件流只用 outcome 控制完成/失败/等待用户。
- [ ] 中短篇只在 result.ready 后打开候选或报告；缺失产物显示对账异常。
- [ ] stream 结束后 GET outcome，queued/running 才重连。
- [ ] 重跑相关 Web 测试。

### 任务 7：数据库契约与受控迁移

**文件：**

- 修改：`apps/core-api/src/inkforge_core/db/schema-contract.json`
- 修改：`apps/core-api/tests/db/test_schema_guard.py`
- 修改：`apps/core-api/tests/db/test_model_metadata.py`
- 使用：`scripts/backup.sh`、`scripts/restore_verify.sh`

- [ ] 安装或定位与 PostgreSQL 14 兼容的 pg_dump/pg_restore 客户端。
- [ ] 创建完整 custom-format 备份和 SHA-256，执行 `pg_restore --list`，优先完成独立恢复验证。
- [ ] 在隔离数据库演练 SQL，验证约束、索引和回滚路径。
- [ ] 导出新 schema contract，并运行 exact guard。
- [ ] 在维护边界内对共享远程数据库执行事务迁移。
- [ ] 迁移后核验表、约束、索引、现有任务数量和 Outbox 初始为空。

### 任务 8：文档、全量验证与提交

**文件：**

- 修改：`apps/agent-service/AGENTS.md`
- 修改：`docs/requirements/03-ai-writing-and-agents.md`
- 修改：`docs/requirements/04-review-quality-and-workflow.md`
- 保留并纳入：`docs/specs/2026-08-01-model-grant-lifetime.md` 及其 1200 秒实现修改

- [ ] 更新当前架构事实，删除“边界事件先发 Redis 再存 checkpoint”的旧描述。
- [ ] 运行定向 pytest、Web 测试、结构守卫和迁移验证。
- [ ] 运行 `uv run ruff check .`。
- [ ] 运行 `uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src`。
- [ ] 运行 `npm run api:generate`、`npm run api:check`、`npm run typecheck`、`npm run lint` 和相关 Web 测试。
- [ ] 审查全部差异，确保只包含本次状态机、Outbox、1200 秒授权和用户已有相关文档。
- [ ] 使用简体中文提交信息创建一次提交。
