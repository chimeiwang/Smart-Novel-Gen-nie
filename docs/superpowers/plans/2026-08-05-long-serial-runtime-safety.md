# 长篇运行安全与正式写入门禁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在开放任何长篇 CLI 写命令前，完成服务端取消、迟到 job 隔离、Artifact 来源版本保护、决策 revision CAS、进展 CAS 和质量幂等/CAS。

**Architecture:** Core 以持久 cancel command 和当前 command/job 身份作为正式副作用门禁；Agent Redis 队列用 tombstone 接受先于 enqueue 的取消，并在模型、节点和工具边界观察取消；Artifact 来源指针保存在现有 payloadJson，批准/返工在统一锁序内验证原始 sourceBindings。所有实现复用控制面计划的幂等与关系锁基础设施。

**Tech Stack:** FastAPI、SQLAlchemy async、PostgreSQL advisory/row locks、Redis Lua、LangGraph、Ed25519 request binding、pytest、Ruff、Mypy、Next.js 16

---

## 执行前提

- 先完整执行 [控制面与共享契约计划](./2026-08-05-long-serial-control-plane.md)。
- 确认 `git rev-parse --verify refs/codex/long-serial-plan-base` 仍指向总体计划记录的实施基线。
- 使用其中的 `writing/idempotency.py`、`writing/transaction_locks.py`、`writing/source_bindings.py`，不得另造第二套 fingerprint 或锁 helper。
- 本计划全部通过前，CLI registry 中只能出现长篇查询与 `long.task.watch`。
- 取消不新增 `WritingTask.phase`、`WritingRunCommand.status` 或 Outbox 事件。
- 执行 Agent Task 3–5 前重新读取 `apps/agent-service/AGENTS.md`、`docs/requirements/03-ai-writing-and-agents.md` 和 `docs/requirements/04-review-quality-and-workflow.md`；执行 Web Task 10 前读取 `DESIGN.md`，即使本次只改请求契约、不调整视觉。
- 强制 TDD 节奏：每个含“写失败测试”或“扩展失败用例”的 Task，在测试编辑完成后、执行任何实现步骤前，立即运行该 Task 已列出的精确 pytest 命令并记录 RED；失败必须来自目标能力缺失。若意外通过先修正测试。实现后重复同一命令确认 GREEN，再允许提交。

### Task 1：收紧公共 resume 边界并接入指纹幂等

**Files:**

- Modify: `apps/core-api/src/inkforge_core/writing/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/writing/commands.py`
- Modify: `apps/core-api/src/inkforge_core/writing/router.py`
- Modify: `apps/core-api/tests/writing/test_commands.py`
- Modify: `apps/core-api/tests/writing/test_sessions.py`

- [ ] 写失败测试：公共 resume 对 `artifactId`、`decision` 和所有额外字段返回 422；普通 userMessage、空消息的合法 checkpoint、会话绑定继续工作；无合法 checkpoint 的空消息返回 `WRITING_RUN_NOT_RECOVERABLE`；有权威 awaiting Artifact 时无论是否带消息都返回 `ARTIFACT_DECISION_REQUIRED`，且两种拒绝都不创建 command、Outbox 或状态变化。
- [ ] 把 `ResumeWritingRunRequest` 固定为：

```python
class ResumeWritingRunRequest(WritingSchema):
    clientRequestId: str = Field(min_length=16, max_length=128)
    writingSessionId: str | None = Field(default=None, min_length=1, max_length=256)
    userMessage: str | None = None
```

- [ ] 用 `commandKind=resume`、`resourceIdentity={taskId}` 和移除 clientRequestId 后的规范 body 计算 fingerprint；事务执行 advisory → Novel → Chapter → Task → 当前 Command → 第二次幂等查询。
- [ ] 提取单一 `resolve_recoverable_checkpoint()`，同时供状态响应的 `recoverable` 和 resume 使用：持久 checkpoint 必须是可解析对象、绑定当前 task/command、包含合法 eventSequence/phase/operation 身份，且当前无 pending/submitted/processing command。空白或 null userMessage 只有该谓词为 true 才能继续。
- [ ] 锁内先检查同 task 的权威 awaiting Artifact；存在时立即返回 `ARTIFACT_DECISION_REQUIRED`，不得调用 `supersede_waiting_for_new_command()`。拒绝无 checkpoint 的空继续时返回 409 `WRITING_RUN_NOT_RECOVERABLE`，并保持所有数据库事实不变。
- [ ] 显式长篇 resume 的 `job` 从原 start command 复制 operation、target、scope、sourceBindings、targetWordCount 和 userInstruction，设置 `resume=true` 与普通 `resumeInput`；不从当前业务数据重新冻结来源。
- [ ] 历史自然语言任务继续生成历史 resume job，不强行伪装成显式 payload。
- [ ] 运行：

```powershell
uv run pytest apps/core-api/tests/writing/test_commands.py apps/core-api/tests/writing/test_sessions.py -q
```

- [ ] 提交：

```powershell
git add apps/core-api/src/inkforge_core/writing/schemas.py apps/core-api/src/inkforge_core/writing/commands.py apps/core-api/src/inkforge_core/writing/router.py apps/core-api/tests/writing/test_commands.py apps/core-api/tests/writing/test_sessions.py
git commit -m "修复：收紧写作任务恢复边界"
```

### Task 2：实现 Core 持久 cancel command 和 Agent DELETE 投递

**Files:**

- Create: `apps/core-api/src/inkforge_core/writing/cancellation.py`
- Modify: `apps/core-api/src/inkforge_core/writing/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/writing/router.py`
- Modify: `apps/core-api/src/inkforge_core/writing/commands.py`
- Modify: `apps/core-api/src/inkforge_core/writing/command_dispatcher.py`
- Modify: `apps/core-api/src/inkforge_core/writing/outcome.py`
- Modify: `apps/core-api/src/inkforge_core/agent_client.py`
- Modify: `apps/core-api/src/inkforge_core/app.py`
- Create: `apps/core-api/tests/writing/test_cancel.py`
- Modify: `apps/core-api/tests/writing/test_command_dispatcher.py`
- Modify: `apps/core-api/tests/writing/test_outcome.py`
- Modify: `apps/core-api/tests/test_agent_client.py`

- [ ] 写失败测试覆盖 queued/running 取消、waiting_user 拒绝、重复相同请求、不同 fingerprint、跨 task/跨 command kind 复用同一 ID、终态 no-op、cancel-vs-complete 两种提交顺序、Agent 暂时不可用重试、无 Outbox、outcome 优先投影。
- [ ] 新增：

```python
class CancelWritingRunRequest(WritingSchema):
    clientRequestId: str = Field(min_length=16, max_length=128)

class CancelWritingRunResponse(WritingSchema):
    taskId: str
    commandId: str
    commandStatus: WritingCommandStatus
    effective: bool
    alreadyTerminal: bool
    cancelledCommandId: str | None
    cancelledJobId: str | None
```

- [ ] `POST /api/v1/writing/runs/{taskId}/cancel` 对非终态返回 202；终态 no-op 可直接返回 200 或统一 202，但 OpenAPI 和测试必须固定一种，本计划采用统一 202。
- [ ] cancel 指纹固定为 `commandKind=cancel`、`resourceIdentity={taskId}`、移除 clientRequestId 后的规范 body `{}`；pending/succeeded cancel command 的 payload 都保存 `_inkforgeCommand + job` envelope，跨 task 或跨 command kind 复用同一 ID 必须 `IDEMPOTENCY_KEY_REUSED`。
- [ ] 取消事务严格执行：advisory → Novel → Chapter → Task → active Artifact → 当前 Command → 第二次幂等查询。
- [ ] waiting_user 且存在归属正确的 awaiting_user Artifact 时，在任何状态变更前返回 `ARTIFACT_DECISION_REQUIRED`。
- [ ] 非终态先把旧活动 command 置为 failed，result 写入：

```json
{
  "code": "WRITING_RUN_CANCELLED_BY_USER",
  "cancelCommandId": "...",
  "cancelledJobId": "旧 command id"
}
```

- [ ] 随后创建 pending `kind=cancel` command；payload 的 job 只描述被取消的 command/job，不能被普通 writing submitter 当成新写作 job。
- [ ] `AgentClient.cancel()` 使用签名 `DELETE /internal/v1/runs/{cancelledJobId}`，body 为 `AgentJobCancelRequest`，idempotency key 绑定旧 jobId。
- [ ] dispatcher 对 `kind=cancel` 调 DELETE；204 后把 cancel command 标为 succeeded、task phase 置现有 `error`，result 写 effective=true。503 时 command 保持 pending 并按现有退避重试。
- [ ] 终态 no-op 也保存 succeeded cancel command；`priorOutcome` 保存原 state/code/result/currentCommand，但不复制 observedAt。
- [ ] outcome projector 在通用冲突判断前识别 cancel：effective=true → cancelled；effective=false → 保留 priorOutcome 的原成功/失败和产物，并沿 `priorOutcome.currentCommand.id` 逐级解析同 task 的原业务 command。链缺失、循环或跨 task 时 inconsistent，不能退回任务 phase 猜测。
- [ ] 在 `test_cancel.py` 与 `test_outcome.py` 覆盖 review succeeded 后一次/连续两次终态 no-op cancel，断言 `reviewReport` 字节完全一致；plan/write 同测 Artifact ID 不变，并覆盖损坏 priorOutcome 链 fail-closed。
- [ ] 取消路径不得调用 `supersede_waiting_for_new_command()` 产生 Outbox。
- [ ] 运行：

```powershell
uv run pytest apps/core-api/tests/writing/test_cancel.py apps/core-api/tests/writing/test_command_dispatcher.py apps/core-api/tests/writing/test_outcome.py apps/core-api/tests/test_agent_client.py -q
```

- [ ] 提交：

```powershell
git add apps/core-api/src/inkforge_core/writing/cancellation.py apps/core-api/src/inkforge_core/writing/schemas.py apps/core-api/src/inkforge_core/writing/router.py apps/core-api/src/inkforge_core/writing/commands.py apps/core-api/src/inkforge_core/writing/command_dispatcher.py apps/core-api/src/inkforge_core/writing/outcome.py apps/core-api/src/inkforge_core/agent_client.py apps/core-api/src/inkforge_core/app.py apps/core-api/tests/writing/test_cancel.py apps/core-api/tests/writing/test_command_dispatcher.py apps/core-api/tests/writing/test_outcome.py apps/core-api/tests/test_agent_client.py
git commit -m "功能：增加写作任务服务端取消"
```

### Task 3：让 Redis 取消 tombstone 覆盖迟到 enqueue

**Files:**

- Modify: `apps/agent-service/src/inkforge_agents/queue/repository.py`
- Modify: `apps/agent-service/src/inkforge_agents/runs/router.py`
- Modify: `apps/agent-service/tests/queue/test_repository.py`
- Modify: `apps/agent-service/tests/integration/test_run_submission.py`

- [ ] 写失败测试：DELETE 先于 POST；普通和 `force=true` enqueue 均不得复活；tombstone 能按 terminal retention 清理；重复 DELETE 仍为 204。
- [ ] 修改 `_CANCEL_SCRIPT`：status 不存在时也清理 ready/processing/payload/lease/attempt/score，写 `statuses[jobId]=cancelled` 并加入 terminal ZSET。
- [ ] 保留 `_ENQUEUE_SCRIPT` 对 completed/failed/cancelled 的拒绝，即使 force 也不能覆盖。
- [ ] `RedisRunQueue.cancel()` 的 bool 只表示是否首次落 tombstone；HTTP 204 不依赖该值。
- [ ] 运行：

```powershell
uv run pytest apps/agent-service/tests/queue/test_repository.py apps/agent-service/tests/integration/test_run_submission.py -q
```

- [ ] 提交：

```powershell
git add apps/agent-service/src/inkforge_agents/queue/repository.py apps/agent-service/src/inkforge_agents/runs/router.py apps/agent-service/tests/queue/test_repository.py apps/agent-service/tests/integration/test_run_submission.py
git commit -m "修复：持久接受迟到入队前的取消"
```

### Task 4：在模型、图节点和工具边界观察取消

**Files:**

- Create: `apps/agent-service/src/inkforge_agents/queue/cancellation.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py`
- Modify: `apps/agent-service/src/inkforge_agents/operations/graph.py`
- Modify: `apps/agent-service/src/inkforge_agents/jobs/writing.py`
- Modify: `apps/agent-service/src/inkforge_agents/queue/consumer.py`
- Modify: `apps/agent-service/src/inkforge_agents/app.py`
- Modify: `apps/agent-service/tests/runtime/test_agent_runtime.py`
- Modify: `apps/agent-service/tests/graph/test_operation_graph.py`
- Modify: `apps/agent-service/tests/jobs/test_writing.py`
- Modify: `apps/agent-service/tests/queue/test_consumer.py`

- [ ] 写失败测试：模型运行期间取消后，不接收其正文、不执行工具、不保存 checkpoint、不 complete、不 fail；图节点之间取消停止下一节点；consumer 不把 cancelled 改成 failed/completed。
- [ ] 定义：

```python
class JobCancelledError(RuntimeError):
    retryable = False

@dataclass(frozen=True, slots=True)
class RedisRunCancellation:
    queue: RedisRunQueue

    async def raise_if_cancelled(self, job_id: str) -> None:
        if await self.queue.status(job_id) == "cancelled":
            raise JobCancelledError(f"作业已取消：{job_id}")
```

- [ ] 用同一 `RedisRunQueue.status(jobId)` 实现 guard，并从 `app.py` 注入 `AgentRuntime`、OperationDependencies、WritingJobHandler。
- [ ] `AgentRuntime.run()` 至少在以下位置调用 guard：每次模型调用前、模型返回后、并行只读批次启动前、每个串行工具调用前、terminal control event 接受前。
- [ ] operation graph 每个节点入口调用同一 guard；不要仅依赖默认 5 分钟 visibility heartbeat。
- [ ] WritingJobHandler 在首次 context 后、graph 前后、event/checkpoint/complete/fail 前检查。捕获 `JobCancelledError` 时释放本地 Artifact hydration 并退出，不发送 fail callback。
- [ ] consumer 单独捕获 `JobCancelledError`，接受 Redis 已是 cancelled 的事实，不再 acknowledge 为其他终态。
- [ ] 运行：

```powershell
uv run pytest apps/agent-service/tests/runtime/test_agent_runtime.py apps/agent-service/tests/graph/test_operation_graph.py apps/agent-service/tests/jobs/test_writing.py apps/agent-service/tests/queue/test_consumer.py -q
```

- [ ] 提交：

```powershell
git add apps/agent-service/src/inkforge_agents/queue/cancellation.py apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py apps/agent-service/src/inkforge_agents/operations/graph.py apps/agent-service/src/inkforge_agents/jobs/writing.py apps/agent-service/src/inkforge_agents/queue/consumer.py apps/agent-service/src/inkforge_agents/app.py apps/agent-service/tests/runtime/test_agent_runtime.py apps/agent-service/tests/graph/test_operation_graph.py apps/agent-service/tests/jobs/test_writing.py apps/agent-service/tests/queue/test_consumer.py
git commit -m "功能：在智能体执行边界观察取消"
```

### Task 5：给所有写型内部请求绑定当前 jobId

**Files:**

- Modify: `packages/service-contracts/src/inkforge_contracts/tools.py`
- Modify: `packages/service-contracts/tests/test_tool_contracts.py`
- Modify: `apps/agent-service/src/inkforge_agents/clients/core.py`
- Modify: `apps/agent-service/src/inkforge_agents/jobs/adapters.py`
- Modify: `apps/agent-service/tests/integration/test_core_callbacks.py`
- Modify: `apps/core-api/src/inkforge_core/writing/tool_gateway.py`
- Modify: `apps/core-api/src/inkforge_core/writing/tasks.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/internal_router.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/repository.py`
- Modify: `apps/core-api/tests/writing/test_tool_gateway.py`
- Create: `apps/core-api/tests/reviews/test_internal_job_identity.py`
- Modify: `apps/core-api/tests/reviews/test_artifact_lifecycle.py`

- [ ] 写失败测试覆盖：read 工具兼容 optional jobId；write 工具缺 jobId 拒绝；旧/cancelled job 对 Artifact create/revise/evaluation 均 409 且无行变化；篡改 body jobId 使签名摘要校验失败。
- [ ] `ToolCallRequest`、`ToolCallBody`、`ToolRequest` 增加 `jobId`。通用 gateway 在解析 registration 后：read 可选，write 必须非空。
- [ ] 在 gateway 写事务和 Review repository 写事务内复核：

```text
WritingRunCommand.id == jobId
WritingRunCommand.taskId == taskId
status in pending/submitted/processing
该 command 是任务当前活动 command
```

失败统一返回 `409 WRITING_JOB_MISMATCH`。
- [ ] Agent `call_tool()`、`create_artifact()`、`submit_evaluation()` 的 body 从 `RunResource.jobId` 强制写入；调用参数内同名值不得覆盖。
- [ ] Artifact create/revise/evaluation 的 idempotency key 加入 jobId，避免新 command 复用旧 runId key。
- [ ] 不给 JWT claim 增加 jobId；现有 body SHA-256 与 Ed25519 签名已绑定 canonical body。
- [ ] Core 写入事务复用统一锁序；禁止只在 router 预查 current job 后再开一个未保护事务。
- [ ] 运行：

```powershell
uv run pytest packages/service-contracts/tests/test_tool_contracts.py apps/agent-service/tests/integration/test_core_callbacks.py apps/core-api/tests/writing/test_tool_gateway.py apps/core-api/tests/reviews/test_internal_job_identity.py apps/core-api/tests/reviews/test_artifact_lifecycle.py packages/service-auth/tests -q
```

- [ ] 提交：

```powershell
git add packages/service-contracts/src/inkforge_contracts/tools.py packages/service-contracts/tests/test_tool_contracts.py apps/agent-service/src/inkforge_agents/clients/core.py apps/agent-service/src/inkforge_agents/jobs/adapters.py apps/agent-service/tests/integration/test_core_callbacks.py apps/core-api/src/inkforge_core/writing/tool_gateway.py apps/core-api/src/inkforge_core/writing/tasks.py apps/core-api/src/inkforge_core/reviews/schemas.py apps/core-api/src/inkforge_core/reviews/internal_router.py apps/core-api/src/inkforge_core/reviews/repository.py apps/core-api/tests/writing/test_tool_gateway.py apps/core-api/tests/reviews/test_internal_job_identity.py apps/core-api/tests/reviews/test_artifact_lifecycle.py
git commit -m "修复：按当前作业隔离智能体写入"
```

### Task 6：持久化 Artifact 来源指针并新增可恢复列表

**Files:**

- Modify: `apps/core-api/src/inkforge_core/reviews/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/repository.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/internal_router.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/router.py`
- Create: `apps/core-api/tests/reviews/test_source_bindings.py`
- Create: `apps/core-api/tests/reviews/test_artifact_list.py`

- [ ] 写失败测试：Agent 自带 `_inkforgeControl` 被拒；Core 注入 sourceCommandId；每个 revision 继承；公共 payload 不泄漏控制字段；跨 task/缺失 command fail closed；列表过滤和稳定 cursor。
- [ ] `ReviewArtifactResponse` 墕加：

```python
sourceBindings: list[SourceBinding] | None
sourceBindingStatus: Literal["verified", "legacy_missing", "not_yet_supported"]
```

- [ ] beat_plan/chapter_draft 新 Artifact 从任务原 start command 取得 sourceBindings，由 Core 注入：

```json
{"_inkforgeControl":{"sourceCommandId":"start-command-id"}}
```

- [ ] Agent payload 含 `_inkforgeControl` 一律 422/409 拒绝；revision 只能继承当前 Artifact 的 sourceCommandId，不能由请求替换。
- [ ] public serializer 先剥离控制字段，再按 sourceCommandId 加载 sourceBindings。上线前历史同类 Artifact 标为 `legacy_missing`；其他 kind 标为 `not_yet_supported`。
- [ ] 新增 `GET /api/v1/review-artifacts`：novelId 必填，支持 chapterId/taskId/status/kind/cursor/limit；排序 `createdAt DESC,id DESC`，所有者从 Novel 过滤。
- [ ] 列表 serializer 批量加载 source command，避免逐项 N+1。
- [ ] 运行：

```powershell
uv run pytest apps/core-api/tests/reviews/test_source_bindings.py apps/core-api/tests/reviews/test_artifact_list.py apps/core-api/tests/reviews/test_artifact_lifecycle.py -q
```

- [ ] 提交：

```powershell
git add apps/core-api/src/inkforge_core/reviews/schemas.py apps/core-api/src/inkforge_core/reviews/repository.py apps/core-api/src/inkforge_core/reviews/internal_router.py apps/core-api/src/inkforge_core/reviews/router.py apps/core-api/tests/reviews/test_source_bindings.py apps/core-api/tests/reviews/test_artifact_list.py
git commit -m "功能：追踪草案来源并支持列表恢复"
```

### Task 7：重构 Artifact decision 为 revision CAS 与来源校验事务

**Files:**

- Modify: `apps/core-api/src/inkforge_core/reviews/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/decision_orchestrator.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/service.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/repository.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/formal_writes.py`
- Modify: `apps/core-api/src/inkforge_core/writing/commands.py`
- Modify: `apps/core-api/tests/reviews/test_decision_orchestrator.py`
- Modify: `apps/core-api/tests/reviews/test_artifact_apply.py`
- Modify: `apps/core-api/tests/reviews/test_source_bindings.py`

- [ ] 写失败测试覆盖 expectedRevision 三种 decision、并发重复、不同 fingerprint、跨 Artifact/跨 command kind 复用同一 ID、source drift、absence resource 并发创建、editedContent 不能绕过、legacy_missing、not_yet_supported、已知 ApiError 详情透传。对 `not_yet_supported` 必须明确断言：非 beat_plan/chapter_draft 的结构化 Artifact 继续保持现有 Web API approve/revise 行为，不能在 Core 全局 fail closed；discard 仍允许，只有长篇 CLI 做本地拒绝。
- [ ] 请求固定包含：

```python
expectedRevision: int = Field(ge=1)
decision: Literal["approve", "discard", "revise"]
```

- [ ] decision 先无锁读取关联 ID 计算锁集合，正式事务执行 advisory → Novel → Chapter → Task → Artifact → 当前 Command → 排序来源子行 → 第二次幂等查询。
- [ ] decision 指纹固定为 `commandKind=artifact_decision`、`resourceIdentity={artifactId}`、移除 clientRequestId 后包含 expectedRevision/decision/全部合法可选字段的规范 body；decision command payload 保存 `_inkforgeCommand + job`，不能只用旧 idempotencyKey 比较 command kind。
- [ ] 在锁内重验 owner、task/artifact/sourceCommand 关联、awaiting_user、expectedRevision、current command 和 sourceBindings。
- [ ] revision 不一致返回 `ARTIFACT_REVISION_CONFLICT`，details 至少含 expectedRevision/currentRevision。
- [ ] discard 不读取 sourceBindings；即使 legacy_missing 或 drift 也允许，但仍需 revision CAS 和归属校验。
- [ ] beat_plan/chapter_draft 的 approve/revise：legacy_missing → `ARTIFACT_SOURCE_BINDINGS_MISSING`；漂移 → `ARTIFACT_SOURCE_VERSION_CONFLICT`，Artifact 保持 awaiting_user。
- [ ] `sourceBindingStatus=not_yet_supported` 只是 CLI 阶段能力标记；Core decision 不得借此改变现有结构化 Artifact 的 Web 行为，待 Stage C 为具体 kind 增加 sourceBindings 后再收紧。
- [ ] revise 创建的 command 继续引用原 start sourceBindings，不重新冻结；新来源必须启动新任务。
- [ ] `ReviewService` 对已知 `ApiError` 原样抛出，只把未知异常包装成 `ARTIFACT_APPLY_FAILED`。
- [ ] 相同 clientRequestId/同 fingerprint 返回首次保存的 accepted response；不同 fingerprint 返回 `IDEMPOTENCY_KEY_REUSED`。
- [ ] 运行：

```powershell
uv run pytest apps/core-api/tests/reviews/test_decision_orchestrator.py apps/core-api/tests/reviews/test_artifact_apply.py apps/core-api/tests/reviews/test_source_bindings.py -q
```

- [ ] 提交：

```powershell
git add apps/core-api/src/inkforge_core/reviews/schemas.py apps/core-api/src/inkforge_core/reviews/decision_orchestrator.py apps/core-api/src/inkforge_core/reviews/service.py apps/core-api/src/inkforge_core/reviews/repository.py apps/core-api/src/inkforge_core/reviews/formal_writes.py apps/core-api/src/inkforge_core/writing/commands.py apps/core-api/tests/reviews/test_decision_orchestrator.py apps/core-api/tests/reviews/test_artifact_apply.py apps/core-api/tests/reviews/test_source_bindings.py
git commit -m "功能：保护草案决策的来源与修订"
```

### Task 8：给 ChapterProgress 增加首次创建语义和 CAS

**Files:**

- Modify: `apps/core-api/src/inkforge_core/chapters/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/chapters/service.py`
- Modify: `apps/core-api/src/inkforge_core/chapters/repository.py`
- Modify: `apps/core-api/tests/chapters/test_chapter_api.py`
- Modify: `apps/core-api/tests/chapters/test_atomic_status.py`

- [ ] 写失败测试：字段必须出现；首次 null 成功；首次非 null 冲突；已有记录传 null 冲突；过期时间冲突；相同内容返回原 updatedAt；内容变化 updatedAt 至少前进 1ms。
- [ ] 模型：

```python
class ChapterProgressRequest(StrictModel):
    content: str
    expectedUpdatedAt: JsonDatetime | None
```

- [ ] `expectedUpdatedAt` 不设置 default，确保调用方必须显式提供 null 或时间。
- [ ] 事务先锁 Chapter，再锁 ChapterProgress；冲突 code 固定 `CHAPTER_PROGRESS_VERSION_CONFLICT`，details 返回 currentUpdatedAt 或 null。
- [ ] 内容相同视为幂等，不更新时间；内容不同且 CAS 成功时显式生成单调递增的 updatedAt。
- [ ] 运行：

```powershell
uv run pytest apps/core-api/tests/chapters/test_chapter_api.py apps/core-api/tests/chapters/test_atomic_status.py -q
```

- [ ] 提交：

```powershell
git add apps/core-api/src/inkforge_core/chapters/schemas.py apps/core-api/src/inkforge_core/chapters/service.py apps/core-api/src/inkforge_core/chapters/repository.py apps/core-api/tests/chapters/test_chapter_api.py apps/core-api/tests/chapters/test_atomic_status.py
git commit -m "功能：为章节进展增加版本前置条件"
```

### Task 9：实现质量运行幂等和质量状态 CAS

**Files:**

- Modify: `apps/core-api/src/inkforge_core/quality/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/quality/service.py`
- Modify: `apps/core-api/src/inkforge_core/quality/repository.py`
- Modify: `apps/core-api/tests/quality/test_quality_state.py`
- Modify: `apps/core-api/tests/quality/test_dispatcher.py`

- [ ] 写失败测试：clientRequestId 必填；跨 check/task 的相同 ID 冲突；并发相同请求只建一个 WorkflowRun；响应丢失重放命中原 run；skip/reset 过期 CAS；相同状态幂等。
- [ ] 请求：

```python
class RunQualityCheckRequest(StrictModel):
    clientRequestId: str = Field(min_length=16, max_length=128)
    taskId: str | None = None
    message: str | None = None

class UpdateQualityCheckRequest(StrictModel):
    status: Literal["pending", "skipped"]
    resetResult: bool = False
    expectedUpdatedAt: JsonDatetime
```

- [ ] 在 `quality/schemas.py` 内定义与 `chapters/schemas.py` 完全相同的 `_parse_json_datetime()` 和 `JsonDatetime = Annotated[datetime, BeforeValidator(_parse_json_datetime)]`；不要从章节 feature 模块反向导入类型。测试覆盖 `Z`、显式 offset 和无效时间。
- [ ] 合并当前分离的 `authorize_run()` 与 `create_run()` 为一个事务：advisory → 跨表 resolver → Novel → Chapter → QualityCheck → task 绑定 → 第二次 resolver → 活动运行检查 → 写 WorkflowRun。
- [ ] fingerprint 的 resourceIdentity 精确包含 novelId/chapterId/checkItemId；WorkflowRun.input 使用 `_inkforgeCommand + quality` envelope。
- [ ] dispatcher 只使用 `quality` 业务字段，不能把 envelope 整体传给 Agent。
- [ ] skip/reset 在 Chapter → Check 锁序内比较 expectedUpdatedAt；冲突 code 固定 `QUALITY_CHECK_VERSION_CONFLICT`。
- [ ] 运行：

```powershell
uv run pytest apps/core-api/tests/quality/test_quality_state.py apps/core-api/tests/quality/test_dispatcher.py -q
```

- [ ] 提交：

```powershell
git add apps/core-api/src/inkforge_core/quality/schemas.py apps/core-api/src/inkforge_core/quality/service.py apps/core-api/src/inkforge_core/quality/repository.py apps/core-api/tests/quality/test_quality_state.py apps/core-api/tests/quality/test_dispatcher.py
git commit -m "功能：保证质量操作幂等与并发安全"
```

### Task 10：同步 Web 调用方与生成客户端

**Files:**

- Modify: `apps/web/src/features/writing/writing-conversation.tsx`
- Modify: `apps/web/src/features/editor/chapter-editor.tsx`
- Modify: `apps/web/src/features/workspace/workspace-shell.tsx`
- Modify: `apps/web/src/shared/contracts/quality-check.ts`
- Create: `apps/web/src/features/writing/__tests__/review-artifact-request.test.ts`
- Create: `apps/web/src/features/editor/__tests__/chapter-editor-concurrency-source.test.ts`
- Modify: `apps/web/src/features/workspace/__tests__/workspace-shell-source.test.ts`
- Modify: `apps/web/src/shared/contracts/__tests__/quality-check.test.ts`
- Modify: `packages/api-client/src/generated/schema.d.ts`

- [ ] 先运行生成客户端和 typecheck，记录因 expectedRevision/clientRequestId/expectedUpdatedAt 新必填字段产生的 RED：

```powershell
npm run api:generate
npm run typecheck
```

- [ ] writing conversation 的 approve/revise/discard 都从当前 Artifact 传 `expectedRevision`。
- [ ] chapter editor 的 progress 保存传 progress 自身 updatedAt 或首次 null；成功后更新本地服务器响应时间。
- [ ] quality run 生成并在不确定重试中稳定复用 clientRequestId；skip/reset 传 check.updatedAt。
- [ ] 不引入新的篇幅模式 UI 或 guard。
- [ ] 运行：

```powershell
npm run api:check
npm run typecheck
npm run lint
npm run test:web
```

- [ ] 提交：

```powershell
git add apps/web/src/features/writing/writing-conversation.tsx apps/web/src/features/editor/chapter-editor.tsx apps/web/src/features/workspace/workspace-shell.tsx apps/web/src/shared/contracts/quality-check.ts apps/web/src/features/writing/__tests__/review-artifact-request.test.ts apps/web/src/features/editor/__tests__/chapter-editor-concurrency-source.test.ts apps/web/src/features/workspace/__tests__/workspace-shell-source.test.ts apps/web/src/shared/contracts/__tests__/quality-check.test.ts packages/api-client/src/generated/schema.d.ts
git commit -m "适配：同步写作安全契约调用方"
```

### Task 11：验证取消后的迟到回调与并发锁序

**Files:**

- Modify: `apps/core-api/tests/writing/test_callback_identity.py`
- Create: `apps/core-api/tests/writing/test_long_serial_concurrency.py`
- Modify: `apps/core-api/tests/reviews/test_internal_job_identity.py`
- Modify: `tests/architecture/test_compose_security.py`

- [ ] 扩展四类 callback：cancel command pending 和 succeeded 后，旧 event/checkpoint/complete/fail 都返回 `WRITING_JOB_MISMATCH`，且 task snapshot、Artifact、Outbox、cancel result 完全不变。
- [ ] 并发压力测试至少覆盖 start-vs-start、cancel-vs-complete、cancel-vs-decision、approve-vs-chapter-save、absence BeatPlan create-vs-approve，以及 approve/revise/discard-vs-同章新 start 的两种提交顺序；设置合理超时，断言结果只由统一锁序与前置条件决定且没有死锁。
- [ ] 验证 cancel 不创建 Outbox，但 SSE 的 PostgreSQL `run_outcome` 控制帧最终收敛 cancelled。
- [ ] 运行：

```powershell
uv run pytest apps/core-api/tests/writing/test_callback_identity.py apps/core-api/tests/writing/test_long_serial_concurrency.py apps/core-api/tests/reviews/test_internal_job_identity.py apps/core-api/tests/writing/test_sse.py -q
uv run pytest tests/architecture/test_compose_security.py -q
```

- [ ] 提交：

```powershell
git add apps/core-api/tests/writing/test_callback_identity.py apps/core-api/tests/writing/test_long_serial_concurrency.py apps/core-api/tests/reviews/test_internal_job_identity.py tests/architecture/test_compose_security.py
git commit -m "测试：覆盖长篇取消与写入竞态"
```

### Task 12：完成安全门禁总验证

- [ ] 运行相关 Python 回归：

```powershell
uv run pytest packages/service-contracts/tests packages/service-auth/tests apps/core-api/tests/writing apps/core-api/tests/reviews apps/core-api/tests/chapters apps/core-api/tests/quality apps/agent-service/tests/queue apps/agent-service/tests/runtime apps/agent-service/tests/jobs apps/agent-service/tests/graph -q
```

- [ ] 运行静态检查：

```powershell
uv run ruff check .
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
npm run api:check
npm run typecheck
npm run lint
npm run test:web
```

- [ ] 运行 schema 只读校验并确认模型/契约未变化：

```powershell
uv run pytest apps/core-api/tests/db/test_schema_guard.py apps/core-api/tests/db/test_model_metadata.py -q
git diff --exit-code refs/codex/long-serial-plan-base..HEAD -- apps/core-api/src/inkforge_core/db/schema-contract.json apps/core-api/src/inkforge_core/db/models.py scripts/migrations
git diff --cached --exit-code -- apps/core-api/src/inkforge_core/db/schema-contract.json apps/core-api/src/inkforge_core/db/models.py scripts/migrations
git diff --exit-code -- apps/core-api/src/inkforge_core/db/schema-contract.json apps/core-api/src/inkforge_core/db/models.py scripts/migrations
$untrackedSchemaPaths = git ls-files --others --exclude-standard -- apps/core-api/src/inkforge_core/db/schema-contract.json apps/core-api/src/inkforge_core/db/models.py scripts/migrations
if ($LASTEXITCODE -ne 0) { throw "无法检查未跟踪 schema 文件" }
if ($untrackedSchemaPaths) { $untrackedSchemaPaths; throw "发现未跟踪 schema 或迁移文件" }
```

- [ ] 扫描禁止项：

```powershell
$databaseDriverHits = rg -n "DATABASE_URL|asyncpg|psycopg" apps/agent-service/src
if ($LASTEXITCODE -gt 1) { throw "rg 执行失败" }
if ($LASTEXITCODE -eq 0) { $databaseDriverHits; throw "Agent Service 出现数据库依赖" }
$implementationPlaceholders = rg -n "TODO|TBD|NotImplemented" apps/core-api/src/inkforge_core/writing apps/core-api/src/inkforge_core/reviews apps/agent-service/src/inkforge_agents
if ($LASTEXITCODE -gt 1) { throw "rg 执行失败" }
if ($LASTEXITCODE -eq 0) { $implementationPlaceholders; throw "实现范围仍含占位符" }
```

预期：两项检查都正常完成且没有命中。

- [ ] 若总验证失败，回到引入问题的 Task，按该 Task 的精确 Files 范围修复、运行 RED/GREEN 回归并提交；总验证阶段禁止使用目录级 `git add` 或兜底大包提交。全部通过时不创建空提交。

## 本计划完成门槛

- cancel 早于 enqueue 也不会丢失，旧 job 的 callback 和所有写型请求均无法产生正式副作用。
- waiting_user 只能 approve/revise/discard，cancel 不会暗中删除 Artifact。
- beat_plan/chapter_draft 的 approve/revise 必须通过 expectedRevision 和原始 sourceBindings；discard 始终显式可用。
- ChapterProgress、quality run、quality skip/reset 不再最后写入覆盖。
- start/resume/cancel/decision/quality.run 的相同 ID 重放确定性返回原结果，不同请求确定性 409。
- 所有关键事务遵循同一锁序并通过并发测试。
- Web 现有功能完成契约适配，中短篇业务语义未改变。
- PostgreSQL schema 指纹保持不变。
