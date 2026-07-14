# 持久化写作命令与用户私有文风实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将写作启动、恢复和草案决定改为 PostgreSQL 持久化命令，修复 SSE 终态竞态，并让文风及单节画像任务完整按用户隔离。

**Architecture:** Core API 新增 `WritingRunCommand` 事实表和单进程 dispatcher；公开请求先在数据库事务中保存业务变化与命令，再用稳定 job ID 投递 Agent。草案正式写入通过外层事务和绑定同一连接的 savepoint 会话工厂复用现有仓储。文风所有权由 `WritingStyle.userId` 统一推导，画像任务用可空 `section` 区分整套与单节。

**Tech Stack:** PostgreSQL 14、SQLAlchemy 2 async、FastAPI、Redis、LangGraph、Next.js 16、React 19、Pydantic v2、pytest、Node test、Playwright。

---

### Task 1: 版本化数据库变更与 ORM 映射

**Files:**
- Create: `scripts/migrations/20260714_durable_writing_private_styles.sql`
- Modify: `apps/core-api/src/inkforge_core/db/models.py`
- Modify: `apps/core-api/src/inkforge_core/db/__init__.py`
- Modify: `apps/core-api/src/inkforge_core/db/schema-contract.json`
- Modify: `apps/core-api/tests/db/test_model_metadata.py`
- Modify: `apps/core-api/tests/db/test_schema_guard.py`

- [ ] **Step 1: 写结构失败测试**

在 `test_model_metadata.py` 断言 `WritingRunCommand` 存在、`WritingStyle.userId` 非空且指向 `User.id`、`StylePortraitTask.section` 可空；在 `test_schema_guard.py` 把新表加入核心表集合，并断言活动命令部分唯一索引存在。

```python
def test_writing_command_and_private_style_metadata() -> None:
    command = WritingRunCommand.__table__
    style = WritingStyle.__table__
    portrait = StylePortraitTask.__table__
    assert command.c.idempotencyKey.unique is True
    assert style.c.userId.nullable is False
    assert next(iter(style.c.userId.foreign_keys)).target_fullname == "public.User.id"
    assert portrait.c.section.nullable is True
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/db/test_model_metadata.py apps/core-api/tests/db/test_schema_guard.py -q`

Expected: FAIL，原因是模型和结构契约尚无 `WritingRunCommand`、`userId`、`section`。

- [ ] **Step 3: 新增受控迁移 SQL**

SQL 脚本必须使用一个事务，并包含以下结构；不得由应用启动自动执行：

```sql
BEGIN;
UPDATE "Novel" SET "appliedStyleId" = NULL WHERE "appliedStyleId" IS NOT NULL;
DELETE FROM "StylePortraitTask";
DELETE FROM "StyleReference";
DELETE FROM "WritingStyle";

ALTER TABLE "WritingStyle" ADD COLUMN "userId" TEXT NOT NULL;
ALTER TABLE "WritingStyle" ADD CONSTRAINT "WritingStyle_userId_fkey"
  FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
CREATE INDEX "WritingStyle_userId_createdAt_idx"
  ON "WritingStyle"("userId", "createdAt" DESC);

ALTER TABLE "StylePortraitTask" ADD COLUMN "section" TEXT;
ALTER TABLE "StylePortraitTask" ADD CONSTRAINT "StylePortraitTask_section_check"
  CHECK ("section" IS NULL OR "section" IN (
    'creativeMethodology', 'uniqueMarkers', 'generationStyle',
    'expressionFeatures', 'styleTraits'
  ));

CREATE TABLE "WritingRunCommand" (
  "id" TEXT NOT NULL,
  "taskId" TEXT NOT NULL,
  "kind" TEXT NOT NULL,
  "artifactId" TEXT,
  "decision" TEXT,
  "payloadJson" TEXT NOT NULL,
  "resultJson" TEXT,
  "idempotencyKey" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "attemptCount" INTEGER NOT NULL DEFAULT 0,
  "nextAttemptAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "lastError" TEXT,
  "submittedAt" TIMESTAMP(3),
  "completedAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "WritingRunCommand_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "WritingRunCommand_taskId_fkey" FOREIGN KEY ("taskId")
    REFERENCES "WritingTask"("id") ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "WritingRunCommand_kind_check" CHECK ("kind" IN ('start','resume','artifact_decision')),
  CONSTRAINT "WritingRunCommand_decision_check" CHECK (
    "decision" IS NULL OR "decision" IN ('approve','discard','revise')
  ),
  CONSTRAINT "WritingRunCommand_status_check" CHECK (
    "status" IN ('pending','submitted','processing','succeeded','failed')
  ),
  CONSTRAINT "WritingRunCommand_idempotencyKey_key" UNIQUE ("idempotencyKey")
);
CREATE INDEX "WritingRunCommand_due_idx" ON "WritingRunCommand"("status", "nextAttemptAt");
CREATE UNIQUE INDEX "WritingRunCommand_active_task_key" ON "WritingRunCommand"("taskId")
  WHERE "status" IN ('pending','submitted','processing');
COMMIT;
```

- [ ] **Step 4: 增加 SQLAlchemy 模型**

新增 `WritingRunCommand` 映射；给 `WritingStyle` 增加 `userId`，给 `StylePortraitTask` 增加 `section`。模型约束和索引名称必须与 SQL 完全一致，所有新增备注使用简体中文。

- [ ] **Step 5: 在验收克隆数据库执行迁移并重新导出结构契约**

Run: `psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/migrations/20260714_durable_writing_private_styles.sql`

Run: `.\.venv\Scripts\python.exe scripts/export_schema_contract.py --database-url "$env:DATABASE_URL" --output apps/core-api/src/inkforge_core/db/schema-contract.json`

Expected: 三张文风表计数为 0，新表和字段出现在契约；小说、章节、用户、会话表计数不变。

- [ ] **Step 6: 运行结构测试并提交**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/db/test_model_metadata.py apps/core-api/tests/db/test_schema_guard.py -q`

Expected: PASS。

Commit: `git commit -m "迁移：新增持久化写作命令与文风归属" -- scripts/migrations/20260714_durable_writing_private_styles.sql apps/core-api/src/inkforge_core/db apps/core-api/tests/db`

### Task 2: 写作命令仓储与幂等受理

**Files:**
- Create: `apps/core-api/src/inkforge_core/writing/commands.py`
- Create: `apps/core-api/tests/writing/test_commands.py`
- Modify: `apps/core-api/src/inkforge_core/writing/schemas.py`

- [ ] **Step 1: 写命令仓储失败测试**

覆盖相同 `clientRequestId` 返回原命令、同任务并发活动命令冲突、到期命令领取和状态流转。

```python
@pytest.mark.asyncio
async def test_same_client_request_returns_existing_command(repository) -> None:
    first = await repository.create_resume("user-1", "task-1", "request-1", {"userMessage": "继续"})
    second = await repository.create_resume("user-1", "task-1", "request-1", {"userMessage": "继续"})
    assert second.id == first.id
    assert second.status == "pending"

@pytest.mark.asyncio
async def test_task_allows_only_one_active_command(repository) -> None:
    await repository.create_resume("user-1", "task-1", "request-1", {})
    with pytest.raises(ApiError) as captured:
        await repository.create_resume("user-1", "task-1", "request-2", {})
    assert captured.value.code == "WRITING_COMMAND_ACTIVE"
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/writing/test_commands.py -q`

Expected: FAIL，`writing.commands` 尚不存在。

- [ ] **Step 3: 实现命令类型和仓储**

`commands.py` 定义：

```python
@dataclass(frozen=True, slots=True)
class WritingCommandRecord:
    id: str
    task: TaskRecord
    kind: Literal["start", "resume", "artifact_decision"]
    payload: dict[str, Any]
    status: str
    attempt_count: int

def command_idempotency_key(user_id: str, client_request_id: str) -> str:
    return f"{user_id}:{client_request_id}"
```

仓储提供 `create_start_with_task()`、`create_resume()`、`get_by_idempotency_key()`、`claim_due()`、`mark_submitted()`、`mark_processing()`、`mark_succeeded()`、`mark_failed()`。`claim_due()` 使用 `with_for_update(skip_locked=True)`；唯一索引冲突转换成稳定的 409 `WRITING_COMMAND_ACTIVE`。

- [ ] **Step 4: 让请求和响应携带客户端请求标识及命令状态**

在 `StartWritingRunRequest`、`ResumeWritingRunRequest` 增加：

```python
clientRequestId: str = Field(min_length=16, max_length=128)
```

在运行响应中增加 `commandId` 和 `commandStatus: Literal["pending","submitted","processing","succeeded","failed"]`。

- [ ] **Step 5: 运行测试并提交**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/writing/test_commands.py -q`

Commit: `git commit -m "功能：持久化写作运行命令" -- apps/core-api/src/inkforge_core/writing/commands.py apps/core-api/src/inkforge_core/writing/schemas.py apps/core-api/tests/writing/test_commands.py`

### Task 3: 命令投递器与安全对账

**Files:**
- Create: `apps/core-api/src/inkforge_core/writing/command_dispatcher.py`
- Create: `apps/core-api/tests/writing/test_command_dispatcher.py`
- Modify: `apps/core-api/src/inkforge_core/agent_client.py`
- Modify: `apps/core-api/src/inkforge_core/writing/reconciler.py`
- Modify: `apps/core-api/tests/writing/test_reconciler.py`
- Modify: `apps/core-api/src/inkforge_core/app.py`

- [ ] **Step 1: 写投递失败与重复投递测试**

```python
@pytest.mark.asyncio
async def test_dispatch_failure_keeps_command_pending() -> None:
    repository = FakeCommandRepository([command("command-1")])
    dispatcher = WritingRunCommandDispatcher(repository, FailingSubmitter())
    assert await dispatcher.run_once() == 0
    assert repository.pending_ids == ["command-1"]

@pytest.mark.asyncio
async def test_dispatch_uses_command_id_as_stable_job_id() -> None:
    submitter = RecordingSubmitter()
    await WritingRunCommandDispatcher(repository_with("command-1"), submitter).run_once()
    assert submitter.job_ids == ["command-1"]
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/writing/test_command_dispatcher.py apps/core-api/tests/writing/test_reconciler.py -q`

- [ ] **Step 3: 实现 dispatcher**

实现 `run_once()` 和可停止循环；投递失败增加 `attemptCount`，按 `min(60, 2 ** attemptCount)` 秒设置 `nextAttemptAt`。请求日志只包含命令 ID、任务 ID 和错误码。

- [ ] **Step 4: 改造 Agent submitter**

新增：

```python
async def submit_command(self, command: WritingCommandRecord, *, force: bool = False) -> None:
    await self._client.submit(AgentJobRequest(
        protocolVersion="1.0",
        jobId=command.id,
        kind="writing",
        runId=command.task.id,
        taskId=command.task.id,
        novelId=command.task.novel_id,
        userId=command.task.user_id,
        priority=10,
        payload=cast(dict[str, JsonValue], command.payload),
        force=force,
    ))
```

- [ ] **Step 5: 限制旧任务对账范围并接入生命周期**

`list_reconcilable()` 仅选择 `active`、`waiting_call`，不再选择 `idle` 或 `awaiting_user_review`。`app.py` 启动 dispatcher 循环并在 lifespan 退出时停止；现有 reconciler 只处理无活动命令的旧任务。

- [ ] **Step 6: 运行测试并提交**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/writing/test_command_dispatcher.py apps/core-api/tests/writing/test_reconciler.py apps/core-api/tests/test_agent_client.py -q`

Commit: `git commit -m "功能：可靠投递和对账写作命令" -- apps/core-api/src/inkforge_core/writing apps/core-api/src/inkforge_core/agent_client.py apps/core-api/src/inkforge_core/app.py apps/core-api/tests/writing apps/core-api/tests/test_agent_client.py`

### Task 4: 启动和普通恢复切换到持久化命令

**Files:**
- Modify: `apps/core-api/src/inkforge_core/writing/tasks.py`
- Modify: `apps/core-api/src/inkforge_core/writing/router.py`
- Modify: `apps/core-api/tests/writing/test_recovery.py`
- Modify: `apps/core-api/tests/writing/test_sessions.py`

- [ ] **Step 1: 写 Redis 不可用仍受理的失败测试**

```python
@pytest.mark.asyncio
async def test_resume_is_durable_when_immediate_dispatch_fails() -> None:
    service = WritingTaskService(repository, dispatcher=FailingKickDispatcher())
    response = await service.resume("user-1", "task-1", "session-1", ResumeWritingRunRequest(
        clientRequestId="request-00000001", writingSessionId="session-1", userMessage="继续"
    ))
    assert response.accepted is True
    assert response.commandStatus == "pending"
    assert repository.saved_messages == ["继续"]
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/writing/test_recovery.py apps/core-api/tests/writing/test_sessions.py -q`

- [ ] **Step 3: 合并任务、消息与命令事务**

`start()` 调用 `create_start_with_task()`；`resume()` 在一个事务中校验任务、会话，幂等保存用户消息并创建命令。提交后调用 dispatcher 的一次即时投递；投递异常只记录 pending，不把已持久化请求改成 503。

- [ ] **Step 4: 更新路由返回值并运行测试**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/writing/test_recovery.py apps/core-api/tests/writing/test_sessions.py -q`

Commit: `git commit -m "重构：写作启动与恢复使用持久化命令" -- apps/core-api/src/inkforge_core/writing apps/core-api/tests/writing`

### Task 5: 草案决定事务编排与单一入口

**Files:**
- Create: `apps/core-api/src/inkforge_core/reviews/decision_orchestrator.py`
- Create: `apps/core-api/tests/reviews/test_decision_orchestrator.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/service.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/router.py`
- Modify: `apps/core-api/src/inkforge_core/app.py`
- Modify: `apps/core-api/tests/reviews/test_artifact_lifecycle.py`
- Modify: `apps/core-api/tests/reviews/test_artifact_apply.py`

- [ ] **Step 1: 写事务回滚、幂等和三种决定测试**

```python
@pytest.mark.asyncio
async def test_apply_failure_rolls_back_artifact_formal_write_and_command(orchestrator) -> None:
    with pytest.raises(ApiError):
        await orchestrator.decide("user-1", "artifact-1", request(approve=True))
    assert await artifact_status("artifact-1") == "awaiting_user"
    assert await command_count("request-00000001") == 0
    assert await formal_write_count() == 0

@pytest.mark.asyncio
async def test_discard_retry_returns_original_command_after_artifact_deleted(orchestrator) -> None:
    first = await orchestrator.decide("user-1", "artifact-1", request(discard=True))
    second = await orchestrator.decide("user-1", "artifact-1", request(discard=True))
    assert second.commandId == first.commandId
    assert second.deleted is True
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/reviews/test_decision_orchestrator.py -q`

- [ ] **Step 3: 实现同连接事务工厂**

`ReviewDecisionOrchestrator.decide()` 打开外层 session 和事务，然后创建绑定同一连接的仓储工厂：

```python
async with self._session_factory() as outer:
    async with outer.begin():
        connection = await outer.connection()
        transactional_factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        service = self._build_review_service(transactional_factory)
        result = await service.decide(...)
        command = await WritingRunCommandRepository(transactional_factory).create_artifact_decision(...)
```

同一连接上的现有 Review、FormalWrite、Lore、Outline、Reference 仓储提交只释放 savepoint；任何异常由外层事务统一回滚。

- [ ] **Step 4: 先查幂等命令再查草案**

`clientRequestId` 必填。已有命令时从 `resultJson` 返回原 `ArtifactDecisionAcceptedResponse`；新请求才校验草案状态和任务归属。命令负载固定为：

```python
{"resume": True, "chapterId": task.chapter_id, "writingSessionId": task.writing_session_id,
 "resumeInput": {"artifactId": artifact_id, "decision": decision, "userMessage": user_message}}
```

- [ ] **Step 5: 路由改为 202 且只调用 orchestrator**

响应包含 `artifactId/taskId/commandId/decision/status/savedCount/deleted`。批准、丢弃、返工均不要求前端再次调用 resume。

- [ ] **Step 6: 运行 review 全集并提交**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/reviews -q`

Commit: `git commit -m "重构：统一编排草案决定与任务恢复" -- apps/core-api/src/inkforge_core/reviews apps/core-api/src/inkforge_core/app.py apps/core-api/tests/reviews`

### Task 6: 回调终态顺序、命令结束与 SSE 游标

**Files:**
- Modify: `apps/core-api/src/inkforge_core/writing/tasks.py`
- Modify: `apps/core-api/tests/writing/test_sse.py`
- Create: `apps/web/src/features/writing/writing-event-cursor.ts`
- Create: `apps/web/src/features/writing/__tests__/writing-event-cursor.test.ts`
- Modify: `apps/web/src/features/writing/writing-conversation.tsx`
- Modify: `tests/e2e/writing-artifact.spec.ts`

- [ ] **Step 1: 写终态发布顺序失败测试**

```python
@pytest.mark.asyncio
async def test_completed_event_is_appended_after_durable_state() -> None:
    order: list[str] = []
    repository = OrderedRepository(order)
    store = OrderedEventStore(order)
    await WritingCallbackService(repository, store).complete(completion())
    assert order == ["message", "task", "command", "event"]
```

- [ ] **Step 2: 写前端游标失败测试**

```typescript
it("keeps the last event id per task", () => {
  const cursors = createWritingEventCursors();
  cursors.update("task-1", "event-4");
  assert.equal(cursors.headers("task-1")["Last-Event-ID"], "event-4");
});
```

- [ ] **Step 3: 运行两组测试并确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/writing/test_sse.py -q`

Run: `npm test --workspace @inkforge/web -- writing-event-cursor`

- [ ] **Step 4: 将终态数据库写入合并为一个事务**

新增仓储方法 `complete_with_message_and_command()` 和 `fail_with_command()`；`WritingCallbackService` 先等待仓储事务提交，再追加 Redis 终态事件。`save_checkpoint()` 在 phase 再次成为 `awaiting_user_review` 时把当前 processing 命令标记 succeeded。

- [ ] **Step 5: 提取并接入任务游标**

`writing-event-cursor.ts` 用 `Map<string,string>` 管理游标。`processStream(taskId, response, scope)` 用已保存游标初始化 `createSseState`，每个合法帧调用 `update()`；所有 start/resume/decision 连接都把 taskId 和 `Last-Event-ID` 传入。

- [ ] **Step 6: 前端决定改为单请求**

`handleArtifactDecision()` 为动作生成一次 `clientRequestId`，只调用 decision API，随后用返回的 `taskId` 打开 SSE；删除 approve/discard 的本地伪完成分支。只有收到终态或会话恢复确认终态后才显示成功。

- [ ] **Step 7: 增加刷新与重启回归并提交**

E2E 断言批准和丢弃后刷新：`currentTask` 为空、任务为 completed、旧草案事件不重复显示。

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/writing/test_sse.py -q`

Run: `npm run test:web`

Commit: `git commit -m "修复：保证写作终态持久化与SSE连续性" -- apps/core-api/src/inkforge_core/writing apps/core-api/tests/writing apps/web/src/features/writing tests/e2e/writing-artifact.spec.ts`

### Task 7: 文风用户归属

**Files:**
- Modify: `apps/core-api/src/inkforge_core/styles/repository.py`
- Modify: `apps/core-api/src/inkforge_core/styles/service.py`
- Modify: `apps/core-api/src/inkforge_core/styles/router.py`
- Modify: `apps/core-api/tests/styles/test_style_service.py`
- Modify: `apps/core-api/tests/styles/test_style_api.py`
- Modify: `apps/core-api/tests/styles/test_repository_contract.py`

- [ ] **Step 1: 写双用户失败测试**

```python
@pytest.mark.asyncio
async def test_second_user_cannot_read_or_mutate_private_style(client, users) -> None:
    style = await create_style(client, users.owner, "私有文风")
    assert (await list_styles(client, users.other)).json() == []
    for request in private_style_requests(style["id"], users.other):
        assert request.status_code == 404
```

- [ ] **Step 2: 运行 styles 测试并确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/styles -q`

- [ ] **Step 3: 所有公开操作传递 user_id**

把 repository port 和实现统一为 `list_styles(user_id)`、`create_style(user_id, name)`、`require_style(user_id, style_id)`。参考资料、任务、分节和删除均通过：

```python
select(WritingStyle).where(WritingStyle.id == style_id, WritingStyle.userId == user_id)
```

应用文风同时过滤 `Novel.userId == user_id` 和 `WritingStyle.userId == user_id`。公开任务查询通过 `StylePortraitTask -> WritingStyle` join 校验所有者。

- [ ] **Step 4: 运行测试并提交**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/styles -q`

Commit: `git commit -m "功能：按用户隔离文风及画像资源" -- apps/core-api/src/inkforge_core/styles apps/core-api/tests/styles`

### Task 8: 真正的单节画像生成

**Files:**
- Modify: `apps/core-api/src/inkforge_core/styles/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/styles/router.py`
- Modify: `apps/core-api/src/inkforge_core/styles/service.py`
- Modify: `apps/core-api/src/inkforge_core/styles/repository.py`
- Modify: `apps/core-api/src/inkforge_core/agent_client.py`
- Modify: `apps/core-api/tests/styles/test_style_service.py`
- Modify: `apps/core-api/tests/styles/test_internal_portrait_callback.py`
- Modify: `apps/agent-service/src/inkforge_agents/jobs/portrait.py`
- Modify: `apps/agent-service/tests/jobs/test_portrait.py`
- Modify: `apps/web/src/features/styles/style-library-panel.tsx`

- [ ] **Step 1: 写只改变目标分节的失败测试**

```python
@pytest.mark.asyncio
async def test_section_portrait_updates_only_requested_section(service, repository) -> None:
    task = await service.create_portrait("user-1", "style-1", section="uniqueMarkers")
    await service.complete_portrait("user-1", "style-1", task.taskId, section_success("新标记"))
    style = repository.styles["style-1"]
    assert style["uniqueMarkers"] == "新标记"
    assert style["creativeMethodology"] == "原方法"
```

- [ ] **Step 2: 写 Agent 单节调用失败测试并确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/styles apps/agent-service/tests/jobs/test_portrait.py -q`

- [ ] **Step 3: 增加区分整套和单节的契约**

`PortraitTaskResponse` 增加 `section`。成功回调使用判别联合：

```python
class FullPortraitSuccessRequest(StrictModel):
    mode: Literal["full"]
    runId: str
    creativeMethodology: str
    uniqueMarkers: str
    generationStyle: str
    expressionFeatures: str
    styleTraits: str
    originalCharCount: int
    usedCharCount: int
    truncated: Literal[False]

class SectionPortraitSuccessRequest(StrictModel):
    mode: Literal["section"]
    runId: str
    section: PortraitSection
    content: str = Field(min_length=1)
    originalCharCount: int
    usedCharCount: int
    truncated: Literal[False]
```

- [ ] **Step 4: 实现公共单节入口和任务绑定校验**

新增 `POST /styles/{style_id}/sections/{section}/portrait`。创建任务时保存 section；回调模式、section 与任务记录不一致时返回 409。单节成功只 set 一个字段并调用 `build_portrait_markdown()`。

- [ ] **Step 5: Agent 只调用目标维度**

`ModelPortraitGenerator.generate(resource, source_text, section=None)`：section 为空时遍历五节；有值时只运行 `_SECTIONS[section]`。job payload 携带 section，成功请求使用 full/section 判别体。

- [ ] **Step 6: 前端单节按钮调用新 API**

删除 `_section` 忽略参数；`generateSection(styleId, section)` 只把目标 section 设为 generating，并调用新路径。`generateAllSections()` 继续调用整套画像路径。

- [ ] **Step 7: 运行测试并提交**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/styles apps/agent-service/tests/jobs/test_portrait.py -q`

Run: `npm run test:web`

Commit: `git commit -m "功能：支持文风画像单节重新生成" -- apps/core-api/src/inkforge_core/styles apps/core-api/src/inkforge_core/agent_client.py apps/agent-service/src/inkforge_agents/jobs/portrait.py apps/core-api/tests/styles apps/agent-service/tests/jobs/test_portrait.py apps/web/src/features/styles/style-library-panel.tsx`

### Task 9: 草案查询授权语义

**Files:**
- Modify: `apps/core-api/src/inkforge_core/reviews/repository.py`
- Modify: `apps/core-api/tests/reviews/test_artifact_lifecycle.py`

- [ ] **Step 1: 写 404 与 200 null 的失败测试**

```python
async def test_foreign_task_artifact_is_not_disclosed(client, other_user, task_id):
    response = await client.get(f"/api/v1/writing/tasks/{task_id}/artifact", headers=other_user)
    assert response.status_code == 404

async def test_owned_task_without_artifact_returns_null(client, owner, task_id):
    response = await client.get(f"/api/v1/writing/tasks/{task_id}/artifact", headers=owner)
    assert response.status_code == 200
    assert response.json() is None
```

- [ ] **Step 2: 运行失败测试、实现先校验任务再查草案、重新运行**

Run: `.\.venv\Scripts\python.exe -m pytest apps/core-api/tests/reviews/test_artifact_lifecycle.py -q`

实现时先查询 `WritingTask -> Novel.userId`；无匹配返回 `WRITING_TASK_NOT_FOUND` 404，再查询活动草案。

- [ ] **Step 3: 提交**

Commit: `git commit -m "修复：明确任务草案查询授权语义" -- apps/core-api/src/inkforge_core/reviews/repository.py apps/core-api/tests/reviews/test_artifact_lifecycle.py`

### Task 10: Mypy 与 React key 警告

**Files:**
- Modify: `packages/service-auth/tests/test_service_auth_security.py`
- Modify: `apps/web/src/features/writing/writing-conversation.tsx`
- Modify: `apps/web/src/features/writing/__tests__/` 中与复现列表对应的测试文件

- [ ] **Step 1: 固化当前 Mypy 失败**

Run: `.\.venv\Scripts\python.exe -m mypy packages/service-auth/tests/test_service_auth_security.py`

Expected: 8 个既有类型错误。

- [ ] **Step 2: 精确标注故意非法参数并给动态参数定型**

只在故意验证非法构造参数的行使用：

```python
ServiceTokenSigner(private_key=invalid_key)  # type: ignore[call-arg]  # 故意验证非法参数
```

把动态 kwargs 改为显式分支调用或 `TypedDict`；不得使用文件级 ignore、`Any` 扩散或修改生产鉴权代码。

- [ ] **Step 3: 用 Playwright 复现 key 警告并写失败断言**

在写作草案主流程收集 `page.on("console")`；断言不存在 `unique key`。定位具体 `.map()` 后使用实体 ID、事件 ID 或稳定组合键，不使用随机值。

- [ ] **Step 4: 运行 Mypy、Web 测试和 E2E 并提交**

Run: `.\.venv\Scripts\python.exe -m mypy packages/service-auth/tests/test_service_auth_security.py`

Run: `npm run test:web`

Run: `$env:E2E_BASE_URL='http://127.0.0.1:43119'; npx playwright test tests/e2e/writing-artifact.spec.ts`

Commit: `git commit -m "修复：清理类型门禁与写作列表警告" -- packages/service-auth/tests/test_service_auth_security.py apps/web/src/features/writing tests/e2e/writing-artifact.spec.ts`

### Task 11: 契约、需求文档与全量本地验收

**Files:**
- Modify: `packages/api-client/src/generated/schema.d.ts`
- Modify: `docs/requirements/02-creative-knowledge-base.md`
- Modify: `docs/requirements/03-ai-writing-and-agents.md`
- Modify: `docs/requirements/04-review-quality-and-workflow.md`
- Modify: `docs/requirements/05-auth-billing-and-ops.md`
- Modify: `docs/audits/2026-07-14-functional-verification.md`
- Modify: `docs/superpowers/plans/2026-07-14-comprehensive-functional-verification.md`

- [x] **Step 1: 生成并校验 OpenAPI 客户端**

Run: `npm run api:generate`

Run: `npm run api:check`

Expected: decision 202、`clientRequestId`、命令状态、私有文风和单节画像路径均出现在生成类型中。

- [x] **Step 2: 更新当前需求事实**

明确 PostgreSQL schema 变更是用户批准的单次例外；写作采用持久化命令；文风按用户私有；单节生成是真实单节任务。删除“前端两步决定+恢复”和“文风全局可写”的旧描述。

- [x] **Step 3: 运行全量门禁**

```powershell
$env:E2E_BASE_URL='http://127.0.0.1:43119'; npx playwright test
npm run api:check
npm run test:web
npm run typecheck
npm run lint
npm run build
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy apps/core-api/src apps/agent-service/src packages
```

Expected: 全部通过；不接受仅重跑失败测试替代全量门禁。

- [x] **Step 4: 重启三服务和 Redis 恢复验收**

验证 pending 命令可补投、awaiting_user_review 无决定时不被重投、批准/丢弃后刷新保持 completed、第二用户看不到第一用户文风、单节任务只改变一个字段。

- [x] **Step 5: 更新审计并提交**

Commit: `git commit -m "文档：完成持久化命令与私有文风验收" -- packages/api-client/src/generated/schema.d.ts docs/requirements docs/audits/2026-07-14-functional-verification.md docs/superpowers/plans/2026-07-14-comprehensive-functional-verification.md`

### Task 12: 生产备份、迁移、部署与线上验收

**Files:**
- Modify only if required by verified deployment evidence: `.github/workflows/**`, `scripts/deploy-production.sh`, `docs/audits/2026-07-14-functional-verification.md`

- [x] **Step 1: 备份 PostgreSQL 与 uploads 并校验备份可读**

运行现有 `scripts/backup.sh`，记录备份路径、大小和校验和；未得到可恢复备份时停止，不执行迁移。

- [x] **Step 2: 记录生产文风清理计数并执行 SQL**

先只读查询 `Novel.appliedStyleId`、三张文风表行数和参考文件路径，再用 `psql -v ON_ERROR_STOP=1` 执行版本化迁移。迁移后运行 schema guard；任何不一致立即停止部署并按设计文档恢复备份。

- [x] **Step 3: 推送代码并观察 GitHub Actions**

只推送所有本地门禁已通过的提交。检查构建、镜像发布和 SSH 部署日志；若服务器缺少备份、数据库权限、HTTPS 或必需密钥，按用户要求停止并明确报告。

- [x] **Step 4: 线上感知验收**

在有效 HTTPS 可用时验证登录、创建私有文风、双用户隔离、单节生成、写作草案批准与刷新恢复；验证公网 `/internal/**` 仍为 404。若仍只有 HTTP，记录 secure cookie 阻塞并停止浏览器登录验收。

- [x] **Step 5: 完成审计与最终提交**

审计列出迁移计数、备份证据、Actions 运行链接、三服务健康、通过/未测项和环境阻塞。不得把 fake provider 或 disabled embedding 记作真实模型质量通过。
