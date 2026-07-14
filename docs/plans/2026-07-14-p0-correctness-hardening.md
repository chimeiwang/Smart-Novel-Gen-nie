# P0 正确性与隔离修复实施计划

> **智能体执行要求：** 必须使用 `superpowers:executing-plans`，按任务逐项实施本计划，并使用复选框（`- [ ]`）跟踪进度。

**目标：** 修复工作区跨用户文风泄露、生产 Web/Core 会话密钥不一致，以及草案等待确认事件与稳定 checkpoint 的序号缺口。

**架构：** 文风读取统一从“小说归属 + 文风归属”两个条件收口；Web 在每次代理请求开始时解析服务端密钥，生产环境禁止默认值；Agent 先幂等发布等待确认事件，再保存包含最新事件序号的 checkpoint。所有修改保持现有数据库结构和 ReviewArtifact 状态机不变。

**技术栈：** FastAPI、SQLAlchemy 2 async、Next.js 16 Proxy、jose、LangGraph、pytest、Node test、Docker Compose。

---

### Task 1: 锁定工作区文风的用户边界

**Files:**
- Modify: `apps/core-api/tests/novels/test_novel_api.py`
- Modify: `apps/core-api/src/inkforge_core/novels/repository.py`

- [ ] **Step 1: 写双用户隔离失败测试**

在现有工作区记录型 session 测试中加入用户 A 的小说、用户 A/B 的文风和“小说错误引用用户 B 文风”的场景。断言：

```python
assert all(style.id != other_user_style.id for style in response.writingStyles)
assert response.novel.appliedStyle is None
assert "WritingStyle.userId" in compiled_style_query
```

同时覆盖兼容入口 `/api/v1/novels/{novel_id}/workspace`，响应中不得出现用户 B 的文风 ID、名称或 `portraitMarkdown`。

- [ ] **Step 2: 运行测试并确认 RED**

Run: `uv run pytest apps/core-api/tests/novels/test_novel_api.py -q`

Expected: FAIL；现有 `_load_workspace()` 会读取全局文风，并按主键读取错误归属的已应用文风。

- [ ] **Step 3: 将 user_id 传入工作区加载边界**

把 `_load_workspace` 改为显式接收 `user_id`，所有文风查询同时限定归属：

```python
applied_style = await session.scalar(
    select(WritingStyle).where(
        WritingStyle.id == novel.appliedStyleId,
        WritingStyle.userId == user_id,
    )
)
styles = list(
    (
        await session.scalars(
            select(WritingStyle)
            .where(WritingStyle.userId == user_id)
            .order_by(WritingStyle.updatedAt.desc(), WritingStyle.id.asc())
        )
    ).all()
)
```

不得使用只按主键读取文风的 `session.get`。仪表盘的批量已应用文风查询也要复核并增加相同用户条件，避免形成第二条泄露路径。

- [ ] **Step 4: 验证隔离与格式**

Run: `uv run pytest apps/core-api/tests/novels/test_novel_api.py -q`

Run: `uv run ruff check apps/core-api/src/inkforge_core/novels apps/core-api/tests/novels`

Expected: PASS。

- [ ] **Step 5: 提交文风隔离修复**

```bash
git add apps/core-api/src/inkforge_core/novels/repository.py apps/core-api/tests/novels/test_novel_api.py
git commit -m "修复：隔离工作区文风读取"
```

### Task 2: 让生产 Web 与 Core 强制使用同一会话密钥

**Files:**
- Create: `apps/web/src/lib/auth/session-secret.ts`
- Create: `apps/web/src/lib/api/__tests__/session-secret.test.ts`
- Modify: `apps/web/src/proxy.ts`
- Modify: `infra/compose.yaml`
- Modify: `tests/architecture/test_compose_security.py`

- [ ] **Step 1: 写密钥解析和 Compose 失败测试**

测试纯函数 `resolveSessionSecret(env)`：

```typescript
assert.throws(() => resolveSessionSecret({ NODE_ENV: "production" }), /JWT_SECRET/);
assert.throws(
  () => resolveSessionSecret({ NODE_ENV: "production", JWT_SECRET: "inkforge-default-secret-change-me" }),
  /默认/,
);
assert.throws(
  () => resolveSessionSecret({ NODE_ENV: "production", JWT_SECRET: "不足三十二字节" }),
  /32/,
);
assert.equal(resolveSessionSecret({ NODE_ENV: "test" }).length > 0, true);
```

架构测试同时断言 `web` 和 `core-api` 的环境块都包含 `JWT_SECRET: ${JWT_SECRET:?必须配置会话签名密钥}`。

- [ ] **Step 2: 运行测试并确认 RED**

Run: `npm --workspace @inkforge/web test -- --test-name-pattern="会话密钥"`

Run: `uv run pytest tests/architecture/test_compose_security.py -q`

Expected: FAIL；解析模块不存在，Web Compose 未注入密钥。

- [ ] **Step 3: 实现服务端密钥解析器**

解析器返回 `Uint8Array`，使用 `TextEncoder` 计算 UTF-8 字节长度。生产环境拒绝缺失、历史默认值和小于 32 字节；测试/开发环境保留明确的测试回退。错误消息使用简体中文，不输出密钥内容。

```typescript
const LEGACY_DEFAULT_SECRET = "inkforge-default-secret-change-me";

export function resolveSessionSecret(env: SessionSecretEnvironment = process.env) {
  const configured = env.JWT_SECRET;
  if (env.NODE_ENV === "production") {
    if (!configured || configured === LEGACY_DEFAULT_SECRET) {
      throw new Error("生产环境必须配置非默认 JWT_SECRET");
    }
    if (new TextEncoder().encode(configured).byteLength < 32) {
      throw new Error("生产环境 JWT_SECRET 至少需要 32 个 UTF-8 字节");
    }
  }
  return new TextEncoder().encode(configured ?? LEGACY_DEFAULT_SECRET);
}
```

- [ ] **Step 4: 把解析移动到请求边界**

删除 `proxy.ts` 的模块级常量，在 `proxy()` 开始处调用解析器。这样 `/login` 健康检查也能暴露生产配置错误，而 `next build` 不会因构建期没有运行时 Secret 失败。`jwtVerify` 继续固定 `algorithms: ["HS256"]`。

- [ ] **Step 5: 注入 Compose 密钥并验证**

在 `web.environment` 增加：

```yaml
JWT_SECRET: ${JWT_SECRET:?必须配置会话签名密钥}
```

Run: `npm --workspace @inkforge/web test`

Run: `uv run pytest tests/architecture/test_compose_security.py -q`

Run: `npm run typecheck && npm run lint`

Expected: PASS。

- [ ] **Step 6: 提交生产密钥修复**

```bash
git add apps/web/src/lib/auth/session-secret.ts apps/web/src/lib/api/__tests__/session-secret.test.ts apps/web/src/proxy.ts infra/compose.yaml tests/architecture/test_compose_security.py
git commit -m "修复：统一生产会话签名密钥"
```

### Task 3: 固定草案事件与 checkpoint 的持久化顺序

**Files:**
- Modify: `apps/agent-service/tests/jobs/test_writing.py`
- Modify: `apps/agent-service/src/inkforge_agents/jobs/writing.py`
- Modify: `apps/core-api/tests/writing/test_sse.py`

- [ ] **Step 1: 把现有顺序测试改为正确契约**

将 `test_writing_job_persists_waiting_checkpoint_before_artifact_event` 重命名为“先发布等待确认事件再保存 checkpoint”，并断言调用序列：

```python
assert core.calls == [
    ("event", 1, "agent_start"),
    ("event", 2, "artifact_awaiting_user_approval"),
    ("checkpoint", 3),
]
assert core.checkpoints[-1]["eventSequence"] == 3
```

- [ ] **Step 2: 写故障注入失败测试**

Fake Core 第一次让等待确认事件成功、checkpoint 抛出异常；第二次执行同一个 job 时，事件 ID 和序号仍为 `runId/2/artifact_awaiting_user_approval`，Core 幂等接受重放，随后 checkpoint 以序号 3 成功。断言最终用户可见事件只有一条、序号无缺口。

Core SSE 测试补充同一 `eventId` 的重放不会重复发布，且同一序号不同事件被拒绝。

- [ ] **Step 3: 运行测试并确认 RED**

Run: `uv run pytest apps/agent-service/tests/jobs/test_writing.py apps/core-api/tests/writing/test_sse.py -q`

Expected: FAIL；当前实现先保存 checkpoint，再发送事件。

- [ ] **Step 4: 重排稳定状态持久化**

在 `WritingJobHandler.__call__` 中明确计算：

```python
next_sequence = sequence + 1
if has_review_event:
    await self._core.send_event(
        resource,
        sequence=next_sequence,
        event="artifact_awaiting_user_approval",
        data={"agentId": active_agent, "artifactId": artifact_id},
    )
    next_sequence += 1

stable["eventSequence"] = next_sequence
await self._core.save_checkpoint(
    resource,
    sequence=next_sequence,
    checkpoint=to_typescript_snapshot(serialize_snapshot(stable)),
)
```

终态 `complete`/`fail` 从实际 `next_sequence + 1` 继续，不得保留依赖旧 `checkpoint_sequence` 的魔法偏移。事件身份继续使用 CoreClient 现有 `_event_id(runId, sequence, kind)`，不新造随机 ID。

- [ ] **Step 5: 验证重放和序号连续性**

Run: `uv run pytest apps/agent-service/tests/jobs/test_writing.py apps/core-api/tests/writing/test_sse.py -q`

Run: `uv run ruff check apps/agent-service/src/inkforge_agents/jobs/writing.py apps/agent-service/tests/jobs/test_writing.py apps/core-api/tests/writing/test_sse.py`

Run: `uv run mypy apps/agent-service/src apps/core-api/src`

Expected: PASS。

- [ ] **Step 6: 提交事件顺序修复**

```bash
git add apps/agent-service/src/inkforge_agents/jobs/writing.py apps/agent-service/tests/jobs/test_writing.py apps/core-api/tests/writing/test_sse.py
git commit -m "修复：先发布草案事件再保存快照"
```

### Task 4: P0 汇总回归

**Files:**
- Verify only

- [ ] **Step 1: 运行 P0 定向测试**

Run: `uv run pytest apps/core-api/tests/novels/test_novel_api.py apps/core-api/tests/writing/test_sse.py apps/agent-service/tests/jobs/test_writing.py tests/architecture/test_compose_security.py -q`

- [ ] **Step 2: 运行静态检查**

Run: `uv run ruff check .`

Run: `uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src`

Run: `npm run typecheck && npm run lint`

Expected: 全部 PASS；不得修改 `apps/core-api/src/inkforge_core/db/schema-contract.json`。
