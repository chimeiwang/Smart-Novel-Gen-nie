# 中短篇可选篇幅参考实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 中短篇保留 6000～80000 字成稿类型边界，但创建和写作不再强制具体目标字数，实际篇幅由故事完整性决定。

**Architecture:** `WritingBible.targetTotalWordCount` 继续作为可空的篇幅参考，不修改 PostgreSQL schema。公共创建、写作命令和草案元数据允许 `null`；数据库非空 `WritingTask.targetWordCount` 只保存内部兼容值，并从中短篇模型上下文中隔离。Core 仍校验实际正文计数和 6000～80000 类型边界，Agent 只把非空参考描述为软倾向。

**Tech Stack:** FastAPI、Pydantic、SQLAlchemy、LangGraph、Next.js、生成 OpenAPI TypeScript 客户端、pytest、Node test、Playwright CLI

---

### Task 1: 共享契约与 Core 接受可空篇幅参考

**Files:**
- Modify: `packages/service-contracts/src/inkforge_contracts/jobs.py`
- Modify: `packages/service-contracts/src/inkforge_contracts/short_story.py`
- Modify: `apps/core-api/src/inkforge_core/novels/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/novels/service.py`
- Modify: `apps/core-api/src/inkforge_core/novels/repository.py`
- Modify: `apps/core-api/src/inkforge_core/lore/service.py`
- Modify: `apps/core-api/src/inkforge_core/lore/repository.py`
- Modify: `apps/core-api/src/inkforge_core/writing/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/writing/commands.py`
- Modify: `apps/core-api/src/inkforge_core/writing/context.py`
- Modify: `apps/core-api/src/inkforge_core/writing/tasks.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/repository.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/formal_writes.py`
- Test: `packages/service-contracts/tests/test_writing_job_payload.py`
- Test: `packages/service-contracts/tests/test_short_story_contracts.py`
- Test: `apps/core-api/tests/novels/test_novel_api.py`
- Test: `apps/core-api/tests/writing/test_sessions.py`
- Test: `apps/core-api/tests/reviews/test_short_story_draft_repository.py`

- [ ] **Step 1: 写失败测试**

覆盖以下明确行为：

```python
def test_short_medium_creation_accepts_missing_reference_word_count() -> None:
    request = ShortMediumCreateNovelRequest(
        storyLengthProfile="short_medium",
        inspiration="一个完整灵感",
        targetTotalWordCount=None,
    )
    assert request.targetTotalWordCount is None

def test_short_story_job_accepts_null_reference_but_rejects_out_of_range_value() -> None:
    assert WritingJobPayload(**payload(targetTotalWordCount=None)).targetTotalWordCount is None
    with pytest.raises(ValidationError):
        WritingJobPayload(**payload(targetTotalWordCount=5999))

def test_short_story_metadata_records_null_reference_and_exact_actual_count() -> None:
    metadata = ShortStoryDraftMetadata(targetWordCount=None, actualWordCount=6000, **source)
    assert metadata.targetWordCount is None
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `uv run pytest packages/service-contracts/tests/test_writing_job_payload.py packages/service-contracts/tests/test_short_story_contracts.py apps/core-api/tests/novels/test_novel_api.py apps/core-api/tests/writing/test_sessions.py apps/core-api/tests/reviews/test_short_story_draft_repository.py -q`

Expected: `null` 创建、命令或 metadata 被现有必填校验拒绝。

- [ ] **Step 3: 实现最小契约与 Core 改动**

使用统一语义：

```python
targetTotalWordCount: int | None = Field(default=None, ge=6_000, le=80_000)
targetWordCount: int | None = Field(default=None, ge=6_000, le=80_000)

SHORT_STORY_INTERNAL_TASK_WORD_COUNT = 80_000
task_target = request.targetWordCount or SHORT_STORY_INTERNAL_TASK_WORD_COUNT
```

启动时要求请求参考值与当前 WritingBible 一致（两者都可为空）；草案 metadata 保存生成时参考快照。提交和正式应用保留 `actualWordCount == count(content)`、正文非空、实际字数 6000～80000、来源大纲和正文基线检查，但不因当前 Bible 的参考值后来变化而拒绝用户批准的草案。

- [ ] **Step 4: 运行测试确认 GREEN**

Run: `uv run pytest packages/service-contracts/tests/test_writing_job_payload.py packages/service-contracts/tests/test_short_story_contracts.py apps/core-api/tests/novels apps/core-api/tests/writing apps/core-api/tests/reviews -q`

Expected: PASS。

### Task 2: Agent 以故事完整性决定实际篇幅

**Files:**
- Modify: `apps/agent-service/src/inkforge_agents/jobs/writing.py`
- Modify: `apps/agent-service/src/inkforge_agents/runtime/execution.py`
- Modify: `apps/agent-service/src/inkforge_agents/short_story/story_graph.py`
- Modify: `apps/agent-service/src/inkforge_agents/providers/fake.py`
- Test: `apps/agent-service/tests/runtime/test_messages.py`
- Test: `apps/agent-service/tests/short_story/test_story_graph.py`
- Test: `apps/agent-service/tests/providers/test_fake_provider.py`
- Test: `apps/agent-service/tests/jobs/test_writing.py`

- [ ] **Step 1: 写失败测试**

```python
def test_short_story_prompt_without_reference_lets_story_choose_length() -> None:
    brief = build_execution_brief("primary", "write_short_story")
    assert "故事完整性决定实际篇幅" in brief
    assert "不得为了凑字或压字" in brief

async def test_short_story_accepts_null_reference_in_authoritative_context() -> None:
    state = short_story_state(target_total_word_count=None)
    result = await graph.ainvoke(state)
    assert result["shortStoryDraft"]["metadata"]["targetWordCount"] is None
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `uv run pytest apps/agent-service/tests/runtime/test_messages.py apps/agent-service/tests/short_story apps/agent-service/tests/jobs/test_writing.py apps/agent-service/tests/providers/test_fake_provider.py -q`

Expected: Agent 当前拒绝空参考，旧提示词仍把目标视为硬目标。

- [ ] **Step 3: 实现最小 Agent 改动**

整稿提示统一为：

```text
实际篇幅由批准大纲、故事完整性、结构、节奏、高潮和结局兑现决定，并保持 6000～80000 字。
referenceWordCount 为空时不得假定固定目标；非空时仅作篇幅倾向，不要求接近或命中，不得为了凑字或压字破坏故事。
```

中短篇上下文只暴露 `referenceWordCount`，不暴露数据库兼容用的 `WritingTask.targetWordCount`。完整性协议继续要求单次完整边界、`finishReason=stop`、不续写、不拼接。

- [ ] **Step 4: 运行测试确认 GREEN**

Run: `uv run pytest apps/agent-service/tests/runtime/test_messages.py apps/agent-service/tests/short_story apps/agent-service/tests/jobs/test_writing.py apps/agent-service/tests/providers/test_fake_provider.py -q`

Expected: PASS。

### Task 3: Web 将篇幅参考改为可选并重新生成客户端

**Files:**
- Modify: `apps/web/src/features/projects/create-novel-modal.tsx`
- Modify: `apps/web/src/features/workspace/short-story/short-story-workflow-state.ts`
- Modify: `apps/web/src/features/workspace/short-story/short-story-workspace.tsx`
- Modify: `apps/web/src/shared/contracts/story-length-profile.ts`
- Modify: `tests/e2e/helpers.ts`
- Modify: `tests/e2e/short-story-workflow.spec.ts`
- Test: `apps/web/src/features/workspace/__tests__/short-medium-entry-source.test.ts`
- Test: `apps/web/src/features/workspace/__tests__/short-story-workflow-state.test.ts`
- Test: `apps/web/src/shared/contracts/__tests__/story-length-profile.test.ts`
- Generated: `packages/api-client/src/generated/**`

- [ ] **Step 1: 写失败测试**

测试中短篇只填灵感即可提交，空输入发送 `null`，工作区无参考值仍允许生成大纲和正文；填写越界值时阻止保存，展示文案为“篇幅参考（可选）”。E2E 不再断言成稿恰好等于参考值，只断言实际计数与正文一致、正文完整、双审核完成并应用为唯一正文。

- [ ] **Step 2: 运行测试确认 RED**

Run: `npm run test:web -- --test-name-pattern="中短篇|篇幅参考"`

Expected: 现有 `required/min/max` 与 null 门禁导致失败。

- [ ] **Step 3: 先生成契约，再实现 Web**

Run: `npm run api:generate`

使用明确解析，禁止 `Number("") === 0`：

```ts
function parseOptionalReferenceWordCount(value: string): number | null {
  const normalized = value.trim();
  return normalized ? Number(normalized) : null;
}
```

仅当非空参考不是 6000～80000 整数时禁用提交；空值不阻止任何中短篇 Operation。列表和工作区有值时显示“篇幅参考约 N 字”，无值时不显示目标 badge；正文始终显示实际字数。

- [ ] **Step 4: 运行测试确认 GREEN**

Run: `npm run api:check && npm run test:web && npm run typecheck && npm run lint`

Expected: PASS。

### Task 4: 真实 LLM 完整验收

**Files:**
- No source changes expected
- Artifact: `output/playwright/real-short-medium/**`

- [ ] **Step 1: 启动真实 provider 并核验配置**

停止当前仅属于功能 worktree 的 fake 服务进程，使用 `.env.local` 的 `MODEL_PROVIDER=openai_compatible` 重启。只输出 provider、model 和 key 是否存在，不输出密钥。

- [ ] **Step 2: 创建不填写篇幅参考的全新中短篇**

使用新的灵感和标题，确认创建请求中的 `targetTotalWordCount=null`，大纲生成来自真实模型。

- [ ] **Step 3: 完整走通用户流程**

至少执行一次局部改纲，确认未涉及分节保持不变；批准大纲；生成一次完整正文；等待编辑和校验串行审核；如审核要求修改，确认最多自动完整返工一次；最终由用户操作批准并应用唯一“正文”Chapter。

- [ ] **Step 4: 人工验收真实正文**

检查正文不是占位或重复字符，具有完整开端、发展、高潮和结局，实际字数处于 6000～80000，尾部可见，Artifact metadata 的实际字数与正文一致。保存大纲、审核结论和正式正文截图，并检查浏览器控制台无功能错误。

- [ ] **Step 5: 最终验证**

Run: `uv run pytest && uv run ruff check . && uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src && npm run api:check && npm run test:web && npm run typecheck && npm run lint && npm run build`

Expected: 全部命令退出码 0；`apps/core-api/src/inkforge_core/db/schema-contract.json` 指纹不变。
