# 中短篇双文档、版本、CLI 与 Codex Skill 实施计划

> **执行要求：** 使用 `subagent-driven-development` 或 `executing-plans` 逐任务执行；每个生产改动必须先运行对应失败测试，确认失败原因正确后再实现。

**目标：** 在不修改 PostgreSQL schema 的前提下，交付 6000～80000 字中短篇的双文档工作稿、不可变版本、Agent 候选、选区修改、Diff、恢复、简化 Web 工作区、本地认证 CLI 和 Codex 操作 Skill。

**架构：** Core API 独占工作稿、版本、并发、归属和人工确认语义；每个 `ReviewArtifact` 是一个不可变文档版本。Agent Service 复用现有队列、SSE、checkpoint、模型运行时和回调，但使用无 reviewer/返工的短篇专用执行路径。Web 与 CLI 只调用 `/api/v1/**`，CLI 会话只进入系统凭据库。

**技术栈：** FastAPI、Pydantic、SQLAlchemy asyncio、LangGraph、Next.js 16、React 19、生成的 OpenAPI TypeScript 客户端、Python 3.12、httpx、keyring、pytest、Node test runner。

---

## 文件结构

新增 Core 领域目录：

```text
apps/core-api/src/inkforge_core/short_medium/
├── __init__.py
├── constants.py
├── diff.py
├── schemas.py
├── repository.py
├── service.py
├── router.py
└── completion.py
```

新增共享契约与 Agent 专用路径：

```text
packages/service-contracts/src/inkforge_contracts/short_medium.py
apps/agent-service/src/inkforge_agents/short_medium/
├── __init__.py
├── state.py
├── context.py
├── validation.py
└── graph.py
apps/agent-service/src/inkforge_agents/jobs/short_medium.py
apps/agent-service/src/inkforge_agents/jobs/writing_dispatcher.py
```

新增 Web 功能目录：

```text
apps/web/src/features/short-medium/
├── short-medium-workspace.tsx
├── short-version-drawer.tsx
├── short-workspace-state.ts
└── selection-range.ts
```

新增 CLI：

```text
tools/inkforge-cli/
├── pyproject.toml
├── src/inkforge_cli/
│   ├── __init__.py
│   ├── cli.py
│   ├── api.py
│   ├── config.py
│   ├── credentials.py
│   ├── files.py
│   └── sse.py
└── tests/
```

## Task 1：共享短篇契约

**文件：**

- 新增：`packages/service-contracts/src/inkforge_contracts/short_medium.py`
- 修改：`packages/service-contracts/src/inkforge_contracts/jobs.py`
- 修改：`packages/service-contracts/src/inkforge_contracts/events.py`
- 修改：`packages/service-contracts/src/inkforge_contracts/__init__.py`
- 测试：`packages/service-contracts/tests/test_short_medium_contracts.py`
- 测试：`packages/service-contracts/tests/test_jobs.py`
- 测试：`packages/service-contracts/tests/test_event_contracts.py`

- [ ] **Step 1：写四类 Operation 和结果约束的失败测试**

测试必须直接断言：

```python
with pytest.raises(ValidationError):
    ShortMediumRunPayload(
        workflow="short_medium",
        operation="generate_manuscript",
        documentType="manuscript",
        chapterId="chapter-1",
        sourceOutlineVersionId=None,
    )

with pytest.raises(ValidationError):
    ShortMediumReplacementResult(
        resultType="short_medium_replacement",
        operation="replace_selection",
        documentType="manuscript",
        replacement="新文本",
        content="不允许携带完整正文",
        **selection_identity,
    )
```

- [ ] **Step 2：运行 RED**

```bash
uv run pytest packages/service-contracts/tests/test_short_medium_contracts.py -q
```

预期：因 `inkforge_contracts.short_medium` 不存在而失败。

- [ ] **Step 3：实现严格 Pydantic 契约**

实现 `generate_outline | generate_manuscript | replace_selection | full_check`，并用 model validator 约束：

- 正文生成必须绑定 `sourceOutlineVersionId`；
- 选区操作必须绑定基础版本、全文 hash、码点范围和选区 hash；
- `full_check` 必须绑定正文版本；
- replacement 结果只有替换文本，没有完整文档字段；
- `AgentJobRequest(kind="writing")` 在 `workflow=short_medium` 时使用该模型校验 payload；
- 完成回调的 `result` 对短篇三类结果执行显式校验。

- [ ] **Step 4：运行 GREEN 与共享契约回归**

```bash
uv run pytest packages/service-contracts/tests/test_short_medium_contracts.py packages/service-contracts/tests/test_jobs.py packages/service-contracts/tests/test_event_contracts.py -q
```

- [ ] **Step 5：提交**

```bash
git add packages/service-contracts
git commit -m "功能：新增中短篇运行与完成结果契约"
```

## Task 2：中短篇创建和大纲工作稿 CAS

**文件：**

- 修改：`apps/core-api/src/inkforge_core/novels/schemas.py`
- 修改：`apps/core-api/src/inkforge_core/novels/router.py`
- 修改：`apps/core-api/src/inkforge_core/novels/service.py`
- 修改：`apps/core-api/src/inkforge_core/novels/repository.py`
- 修改：`apps/core-api/src/inkforge_core/outlines/schemas.py`
- 修改：`apps/core-api/src/inkforge_core/outlines/repository.py`
- 修改：`apps/core-api/src/inkforge_core/outlines/service.py`
- 测试：`apps/core-api/tests/novels/test_novel_api.py`
- 测试：`apps/core-api/tests/outlines/test_repository_contract.py`

- [ ] **Step 1：写创建边界和大纲并发的失败测试**

覆盖：

```python
@pytest.mark.parametrize(("target", "accepted"), [(5999, False), (6000, True), (80000, True), (80001, False)])
def test_short_medium_word_range(target: int, accepted: bool) -> None:
    values = {
        "clientRequestId": "request-12345678",
        "name": "边界测试",
        "storyLengthProfile": "short_medium",
        "targetTotalWordCount": target,
        "sourceKind": "idea",
        "sourceText": "一个必须作出选择的人。",
    }
    if accepted:
        assert CreateNovelRequest.model_validate(values).targetTotalWordCount == target
    else:
        with pytest.raises(ValidationError):
            CreateNovelRequest.model_validate(values)
```

另外分别创建真实仓储测试 `test_opening_initializes_only_full_manuscript`、
`test_outline_source_initializes_only_outline`、
`test_source_artifact_keeps_full_text_without_truncation` 和
`test_outline_save_rejects_stale_expected_updated_at`，每个测试只验证名称所述的一项行为。

- [ ] **Step 2：运行 RED**

```bash
uv run pytest apps/core-api/tests/novels/test_novel_api.py apps/core-api/tests/outlines/test_repository_contract.py -q
```

- [ ] **Step 3：实现创建与 Outline CAS**

具体契约：

```python
class CreateNovelRequest(StrictModel):
    clientRequestId: str = Field(min_length=16, max_length=128)
    sourceKind: Literal["idea", "opening", "ending", "outline", "mixed"]
    sourceText: str = Field(min_length=1)
    # 保留现有长篇字段

class OutlineContentRequest(StrictModel):
    content: str
    expectedUpdatedAt: datetime

class OutlineContentResponse(StrictModel):
    content: str
    updatedAt: datetime
    contentHash: str
```

创建短篇时：

- 目标字数只接受 6000～80000；
- 作品只有一个标题为“全文”的 Chapter；
- 统一创建 `short-medium:source:{novelId}` 来源 Artifact；
- opening 写入 Chapter 工作稿，outline 写入 Outline 工作稿；
- 其他素材不猜测写入用户文档；
- Novel 列表按 `storyLengthProfile` 过滤并返回 profile/目标字数。

- [ ] **Step 4：运行 GREEN**

```bash
uv run pytest apps/core-api/tests/novels apps/core-api/tests/outlines apps/core-api/tests/chapters -q
```

- [ ] **Step 5：提交**

```bash
git add apps/core-api/src/inkforge_core/novels apps/core-api/src/inkforge_core/outlines apps/core-api/tests/novels apps/core-api/tests/outlines
git commit -m "功能：支持中短篇素材创建与大纲工作稿并发保存"
```

## Task 3：不可变版本、Diff、采用与恢复

**文件：**

- 新增：`apps/core-api/src/inkforge_core/short_medium/constants.py`
- 新增：`apps/core-api/src/inkforge_core/short_medium/schemas.py`
- 新增：`apps/core-api/src/inkforge_core/short_medium/diff.py`
- 新增：`apps/core-api/src/inkforge_core/short_medium/repository.py`
- 新增：`apps/core-api/src/inkforge_core/short_medium/service.py`
- 新增：`apps/core-api/src/inkforge_core/short_medium/router.py`
- 修改：`apps/core-api/src/inkforge_core/app.py`
- 修改：`apps/core-api/src/inkforge_core/reviews/repository.py`
- 修改：`apps/core-api/src/inkforge_core/reviews/service.py`
- 修改：`apps/core-api/src/inkforge_core/reviews/router.py`
- 修改：`apps/core-api/src/inkforge_core/reviews/internal_router.py`
- 测试：`apps/core-api/tests/short_medium/test_version_payload.py`
- 测试：`apps/core-api/tests/short_medium/test_version_diff.py`
- 测试：`apps/core-api/tests/short_medium/test_version_service.py`
- 测试：`apps/core-api/tests/short_medium/test_version_api.py`
- 修改测试：`apps/core-api/tests/reviews/test_artifact_lifecycle.py`
- 修改测试：`apps/core-api/tests/reviews/test_artifact_apply.py`

- [ ] **Step 1：写版本语义失败测试**

至少断言：

```python
assert candidate.status == "awaiting_user"
assert work_draft.content == original_content
assert adopted.content == candidate.content
assert restored.versionNumber == current.versionNumber + 1
assert restored.restoredFromVersionId == historical.id
assert historical.payload == historical_payload_before_restore
assert result.content.endswith("八万字尾部标记")
```

并覆盖：

- 相同内容提交不增加版本；
- `clientRequestId` 重试返回同一版本；
- dirty 工作稿阻止采用和恢复；
- 过期候选阻止采用；
- 正文版本必须保留来源大纲版本；
- 跨文档类型 Diff 拒绝；
- 通用 approve/revise/discard/create 拒绝 `short-medium:*`。

- [ ] **Step 2：运行 RED**

```bash
uv run pytest apps/core-api/tests/short_medium apps/core-api/tests/reviews/test_artifact_lifecycle.py apps/core-api/tests/reviews/test_artifact_apply.py -q
```

- [ ] **Step 3：实现载荷与 Diff**

每个版本一个 Artifact：

```python
class DocumentVersionPayload(StrictModel):
    kind: Literal["outline_draft", "chapter_draft"]
    documentType: Literal["outline", "manuscript"]
    versionNumber: int = Field(ge=1)
    baseVersionId: str | None
    clientRequestId: str | None
    source: Literal["agent", "manual", "restore"]
    content: str
    contentHash: str
    sourceTaskId: str | None
    sourceJobId: str | None
    sourceOutlineVersionId: str | None
    restoredFromVersionId: str | None
```

`contentHash` 必须等于完整 UTF-8 内容的 SHA-256。Diff 使用完整文本，不做 slice/substring 截断。

- [ ] **Step 4：实现事务服务和路由**

路由：

```text
GET  /api/v1/novels/{novelId}/versions
GET  /api/v1/novels/{novelId}/versions/{versionId}
GET  /api/v1/novels/{novelId}/version-diff
POST /api/v1/novels/{novelId}/versions/preview
POST /api/v1/novels/{novelId}/versions
POST /api/v1/novels/{novelId}/versions/{versionId}/adopt
POST /api/v1/novels/{novelId}/versions/{versionId}/restore
```

大纲锁 Novel、正文锁 Chapter。Artifact 和初始 Revision 同事务创建；采用在同一事务更新工作稿与候选状态；恢复复制旧版本为新的 applied 版本。

- [ ] **Step 5：运行 GREEN 与 schema 守卫**

```bash
uv run pytest apps/core-api/tests/short_medium apps/core-api/tests/reviews apps/core-api/tests/db/test_schema_guard.py apps/core-api/tests/db/test_model_metadata.py -q
```

- [ ] **Step 6：提交**

```bash
git add apps/core-api/src/inkforge_core/short_medium apps/core-api/src/inkforge_core/reviews apps/core-api/src/inkforge_core/app.py apps/core-api/tests/short_medium apps/core-api/tests/reviews
git commit -m "功能：实现中短篇不可变版本与差异恢复"
```

## Task 4：短篇公开任务、终态与原子候选持久化

**文件：**

- 修改：`apps/core-api/src/inkforge_core/writing/schemas.py`
- 修改：`apps/core-api/src/inkforge_core/writing/router.py`
- 修改：`apps/core-api/src/inkforge_core/writing/tasks.py`
- 修改：`apps/core-api/src/inkforge_core/writing/context.py`
- 新增：`apps/core-api/src/inkforge_core/short_medium/completion.py`
- 测试：`apps/core-api/tests/writing/test_short_medium_runs.py`
- 测试：`apps/core-api/tests/writing/test_short_medium_completion.py`
- 修改测试：`apps/core-api/tests/writing/test_callback_identity.py`

- [ ] **Step 1：写显式 Operation 和终态失败测试**

覆盖：

- 不允许自由文本猜测短篇 operation；
- 正文生成只绑定当前已采用大纲；
- dirty 大纲/正文阻止 Agent；
- 选区按 Unicode 码点验证全文 hash 和选区 hash；
- `GET /writing/runs/{taskId}` 返回持久 phase、command、候选版本或检查报告；
- 候选持久化失败时 task/command 不能先成功；
- 同一 taskId/jobId 回放只得到一个候选版本。

- [ ] **Step 2：运行 RED**

```bash
uv run pytest apps/core-api/tests/writing/test_short_medium_runs.py apps/core-api/tests/writing/test_short_medium_completion.py apps/core-api/tests/writing/test_callback_identity.py -q
```

- [ ] **Step 3：实现任务快照和完成 finalizer**

`WritingTask.graphStateJson` 保存：

```json
{
  "workflow": "short_medium",
  "operation": "replace_selection",
  "documentType": "manuscript",
  "baseVersionId": "version-id",
  "baseContentHash": "sha256",
  "sourceOutlineVersionId": "outline-version-id",
  "selectionStart": 1,
  "selectionEnd": 3,
  "selectedText": "原选区",
  "selectedTextHash": "sha256",
  "userInstruction": "只加强冲突"
}
```

完成回调在同一事务中锁 task/command、校验 jobId、确定性合并 replacement、创建或回放候选、再完成 task/command。`full_check` 只持久化报告，不创建版本。

- [ ] **Step 4：运行 GREEN**

```bash
uv run pytest apps/core-api/tests/writing apps/core-api/tests/short_medium -q
```

- [ ] **Step 5：提交**

```bash
git add apps/core-api/src/inkforge_core/writing apps/core-api/src/inkforge_core/short_medium apps/core-api/tests/writing
git commit -m "功能：接入中短篇显式写作任务与候选终态"
```

## Task 5：Agent Service 短篇专用执行路径

**文件：**

- 新增：`apps/agent-service/src/inkforge_agents/short_medium/state.py`
- 新增：`apps/agent-service/src/inkforge_agents/short_medium/context.py`
- 新增：`apps/agent-service/src/inkforge_agents/short_medium/validation.py`
- 新增：`apps/agent-service/src/inkforge_agents/short_medium/graph.py`
- 新增：`apps/agent-service/src/inkforge_agents/jobs/short_medium.py`
- 新增：`apps/agent-service/src/inkforge_agents/jobs/writing_dispatcher.py`
- 修改：`apps/agent-service/src/inkforge_agents/app.py`
- 修改：`apps/agent-service/src/inkforge_agents/clients/core.py`
- 修改：`apps/agent-service/src/inkforge_agents/operations/contracts.py`
- 修改：`apps/agent-service/src/inkforge_agents/operations/definitions.py`
- 测试：`apps/agent-service/tests/short_medium/test_graph.py`
- 测试：`apps/agent-service/tests/short_medium/test_selection.py`
- 测试：`apps/agent-service/tests/jobs/test_short_medium.py`

- [ ] **Step 1：写无 reviewer、分段和回放失败测试**

断言：

- 四种操作不进入 reviewer/reviser，不调用通用 Artifact port；
- 15000 字允许单次，15001～80000 使用串行分段；
- 中间段只 checkpoint，不创建版本；
- missing/duplicate/out-of-order/length/content_filter 均失败；
- completed checkpoint 回放回调，不重跑模型；
- replacement 结果只有替换文本；
- 所有 checkpoint/回调使用同一非空 jobId。

- [ ] **Step 2：运行 RED**

```bash
uv run pytest apps/agent-service/tests/short_medium apps/agent-service/tests/jobs/test_short_medium.py -q
```

- [ ] **Step 3：实现 dispatcher 与专用图**

```text
writing job
├─ workflow 缺省或 long_serial → 现有 WritingJobHandler
└─ workflow=short_medium → ShortMediumWritingJobHandler
```

短篇图只做准备上下文、单次生成或串行分段、完整性校验、稳定 checkpoint 和一次完成回调。提示词保持“短静态身份 + 当前 Operation brief + Core 权威内容”。

- [ ] **Step 4：运行 GREEN 与 Agent 回归**

```bash
uv run pytest apps/agent-service/tests/short_medium apps/agent-service/tests/jobs apps/agent-service/tests/runtime apps/agent-service/tests/integration -q
```

- [ ] **Step 5：提交**

```bash
git add apps/agent-service packages/service-contracts
git commit -m "功能：实现中短篇无自动返工的 Agent 执行路径"
```

## Task 6：生成公共客户端并实现简化 Web 工作区

**文件：**

- 修改：`apps/web/src/shared/contracts/story-length-profile.ts`
- 修改：`apps/web/src/features/projects/create-novel-modal.tsx`
- 修改：`apps/web/src/features/workspace/workspace-shell.tsx`
- 新增：`apps/web/src/features/short-medium/short-workspace-state.ts`
- 新增：`apps/web/src/features/short-medium/selection-range.ts`
- 新增：`apps/web/src/features/short-medium/short-medium-workspace.tsx`
- 新增：`apps/web/src/features/short-medium/short-version-drawer.tsx`
- 修改：`apps/web/src/app/globals.css`
- 测试：`apps/web/src/features/short-medium/__tests__/*.test.ts`

- [ ] **Step 1：生成客户端**

```bash
npm run api:generate
npm run api:check
```

- [ ] **Step 2：写 UI 状态和码点失败测试**

覆盖：

```typescript
assert.deepEqual(toCodePointRange("甲😀乙", 1, 3), { start: 1, end: 2 });
assert.equal(canStartAgent({ dirty: true }), false);
assert.equal(requiresConfirmation("submit"), true);
assert.equal(candidateAutomaticallyAdopted, false);
```

源码测试必须证明完整 Diff 没有 `slice`、`substring` 或固定条数截断。

- [ ] **Step 3：运行 RED**

```bash
npm test --workspace @inkforge/web
```

- [ ] **Step 4：实现工作区**

- 中短篇创建字段为标题、目标字数、素材类型、完整素材、可选题材；
- WorkspaceShell 按 profile 选择简化工作区；
- 蓝图与正文均用 textarea 和 1.2 秒自动保存；
- dirty 时禁用 Agent、采用和恢复；
- 提交、采用、恢复先展示完整 Diff，再绑定确认摘要；
- 版本抽屉不复用会截断 Diff 的旧 Artifact 卡片。

- [ ] **Step 5：运行 GREEN**

```bash
npm run test:web
npm run typecheck
npm run lint
```

- [ ] **Step 6：提交**

```bash
git add apps/web packages/api-client
git commit -m "功能：新增中短篇双文档与版本工作区"
```

## Task 7：本地认证 JSON-first CLI

**文件：**

- 新增：`tools/inkforge-cli/pyproject.toml`
- 新增：`tools/inkforge-cli/src/inkforge_cli/*.py`
- 新增：`tools/inkforge-cli/tests/*.py`
- 修改：`pyproject.toml`
- 修改：`uv.lock`

- [ ] **Step 1：写 CLI 契约和凭据失败测试**

覆盖：

- 登录不是 TTY 时拒绝；
- 没有 WinVault 安全后端时拒绝；
- 密码/Cookie/Token 不出现在 stdout、stderr、异常 repr 和 config；
- 非 loopback HTTP 被拒绝；
- 普通命令 stdin 一个 JSON、stdout 一个 JSON；
- 401 退出码 3，409 退出码 4；
- pull 不覆盖 dirty 文件；
- 8 万字正文和 Diff 尾部字节存在；
- watch 输出 JSONL 并在 SSE 结束后读取持久终态；
- 网络结果不确定时保留同一 `clientRequestId`。

- [ ] **Step 2：运行 RED**

```bash
uv run pytest tools/inkforge-cli/tests -q
```

- [ ] **Step 3：实现安全会话和 API 客户端**

`credentials.py` 定义可注入 `CredentialStore`；Windows 生产只允许 keyring WinVault，未知或文件型 backend 失败。config 只保存 profile、origin 和用户名。远程 origin 强制 HTTPS。

- [ ] **Step 4：实现命令与文件协议**

命令：

```text
auth.login | auth.whoami | auth.logout
short.list | short.create | short.pull | short.draft.save
short.version.preview | submit | list | get | diff | adopt | restore
short.agent.start | short.agent.watch
```

大纲、正文、Diff 写 UTF-8 文件并原子替换；stdout 只返回绝对路径、hash、字数和版本元数据。

- [ ] **Step 5：运行 GREEN**

```bash
uv run pytest tools/inkforge-cli/tests -q
uv run ruff check tools/inkforge-cli
uv run mypy tools/inkforge-cli/src
```

- [ ] **Step 6：提交**

```bash
git add tools/inkforge-cli pyproject.toml uv.lock
git commit -m "功能：新增本地认证中短篇操作 CLI"
```

## Task 8：重写并测试 Codex Skill

**文件：**

- 修改：`C:\Users\niebo\.codex\skills\inkforge-short-story-operator\SKILL.md`
- 修改：`C:\Users\niebo\.codex\skills\inkforge-short-story-operator\agents\openai.yaml`
- 修改：`C:\Users\niebo\.codex\skills\inkforge-short-story-operator\scripts\operator.ps1`
- 修改：`C:\Users\niebo\.codex\skills\inkforge-short-story-operator\references\cli-contract.md`
- 修改：`C:\Users\niebo\.codex\skills\inkforge-short-story-operator\references\recovery.md`
- 新增测试记录：`docs/audits/2026-07-30-short-story-operator-skill-tests.md`

- [ ] **Step 1：RED——用旧 Skill 运行压力场景**

至少记录以下错误倾向：

- “保存改好大纲”是否直接创建 current；
- “一直写到正文完成”是否自动生成并采用多阶段版本；
- dirty 工作稿是否仍启动 Agent；
- 选区要求是否扩展到全文；
- restore 是否跳过 Diff/确认；
- 超时是否创建新 task；
- 401 是否尝试旁路登录。

- [ ] **Step 2：写最小新 Skill**

Skill 只保留：

- 只调用 wrapper 和公开 API；
- 每次写前 whoami；
- 保存工作稿不成版；
- Agent 只产候选；
- submit/adopt/restore 均先 Diff 后确认；
- 选区外只报告；
- 409 不自动覆盖或变基；
- 401 要求用户真实终端登录。

- [ ] **Step 3：GREEN——重复相同压力场景**

全部场景必须停止在正确的人机边界，并把逐场结果写入审计文档。

- [ ] **Step 4：验证 wrapper**

```powershell
& "$env:USERPROFILE\.codex\skills\inkforge-short-story-operator\scripts\operator.ps1" auth.whoami
```

预期：调用仓库 CLI；未登录时只返回安全的 401/退出码 3，不输出凭据。

## Task 9：文档、端到端与完整验证

**文件：**

- 修改：`docs/requirements/01-projects-and-chapters.md`
- 修改：`docs/requirements/03-ai-writing-and-agents.md`
- 修改：`docs/requirements/04-review-quality-and-workflow.md`
- 修改：`apps/agent-service/AGENTS.md`
- 新增：`tests/e2e/short-medium-workflow.spec.ts`

- [ ] **Step 1：写端到端失败用例**

覆盖创建、两份工作稿、人工提交、Agent 候选不自动采用、选区修改、任意版本 Diff、恢复为新版本，以及 CLI 与 Web 交替操作。

- [ ] **Step 2：运行相关端到端用例并修正真实流程**

```bash
npm run test:e2e -- tests/e2e/short-medium-workflow.spec.ts
```

- [ ] **Step 3：同步当前需求文档**

只写已实现事实，删除与中短篇新工作流冲突的旧表述。

- [ ] **Step 4：完整验证**

```bash
npm run api:check
npm run test:web
npm run typecheck
npm run lint
uv run pytest
uv run ruff check .
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src tools/inkforge-cli/src
git diff --check
```

- [ ] **Step 5：代码审查**

先做规格符合性审查，再做代码质量审查；修复后重新运行受影响测试和完整验证。

- [ ] **Step 6：提交收口**

```bash
git add docs apps tests packages tools pyproject.toml uv.lock package-lock.json
git commit -m "功能：完成中短篇 Codex 协作写作流程"
```
