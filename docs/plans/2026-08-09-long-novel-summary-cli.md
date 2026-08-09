# 长篇作品摘要安全写入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为已有长篇作品增加带版本校验的摘要更新公共接口、CLI 命令和本地/生产 Operator 流程。

**Architecture:** Core 仍是唯一状态权威：service 负责摘要清洗，repository 在锁定 Novel 后校验归属与 `updatedAt`，router 暴露窄 PUT 接口。CLI 只做严格字段校验和公开路由映射；两个 Skill 使用相同的 GET、Diff、确认、CAS、回读流程，仅环境边界不同。

**Tech Stack:** FastAPI、Pydantic v2、SQLAlchemy async、pytest、Python CLI、生成的 TypeScript API Client、PowerShell Skill 测试。

---

### Task 1: Core 摘要 CAS 契约

**Files:**
- Modify: `apps/core-api/src/inkforge_core/novels/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/novels/service.py`
- Modify: `apps/core-api/src/inkforge_core/novels/repository.py`
- Modify: `apps/core-api/src/inkforge_core/novels/router.py`
- Test: `apps/core-api/tests/novels/test_novel_api.py`

- [ ] **Step 1: 写 schema、service、router 和 repository 的失败测试**

覆盖严格类型、空白清空、归属校验、相同值不推进版本、真实变化推进版本、409
`NOVEL_VERSION_CONFLICT` 及 `currentUpdatedAt`，并断言路由只使用 Cookie 用户身份。

```python
request = UpdateNovelSummaryRequest(
    summary="  新摘要  ",
    expectedUpdatedAt=datetime(2026, 8, 9, tzinfo=UTC),
)
result = await service.update_summary("user-1", "novel-1", request)
assert result.summary == "新摘要"
```

- [ ] **Step 2: 运行 Core 目标测试并确认 RED**

Run: `uv run pytest apps/core-api/tests/novels/test_novel_api.py -q`

Expected: 因 `UpdateNovelSummaryRequest`、service/repository 方法和路由缺失而失败。

- [ ] **Step 3: 实现严格请求与仓储端口**

```python
class UpdateNovelSummaryRequest(StrictModel):
    summary: str | None
    expectedUpdatedAt: JsonDatetime

class NovelRepositoryPort(Protocol):
    async def update_summary(
        self,
        novel_id: str,
        user_id: str,
        summary: str | None,
        expected_updated_at: datetime,
    ) -> NovelResponse: ...
```

service 使用 `_clean_optional(request.summary)`；repository 锁定目标 Novel，比较 UTC 版本，不一致抛
`NOVEL_VERSION_CONFLICT`，值变化时用 `next_utc_timestamp()` 推进 `updatedAt`，最后加载 WritingBible
并返回完整 `NovelResponse`。

- [ ] **Step 4: 暴露窄 PUT 路由**

```python
@router.put("/novels/{novel_id}/summary", response_model=NovelResponse)
async def update_novel_summary(...):
    return await service.update_summary(user.id, novel_id, body)
```

- [ ] **Step 5: 运行 Core 测试、Ruff、Mypy**

Run:

```powershell
uv run pytest apps/core-api/tests/novels/test_novel_api.py -q
uv run ruff check apps/core-api/src/inkforge_core/novels apps/core-api/tests/novels/test_novel_api.py
uv run mypy apps/core-api/src
```

Expected: 全部退出 0。

### Task 2: CLI `long.novel.summary.save`

**Files:**
- Modify: `tools/inkforge-cli/src/inkforge_cli/commands/long/novels.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/registry.py`
- Modify: `tools/inkforge-cli/tests/test_long_novel_commands.py`
- Modify: `tools/inkforge-cli/tests/test_registry.py`
- Modify: `tools/inkforge-cli/README.md`

- [ ] **Step 1: 写 CLI 映射与注册表失败测试**

```python
exit_code, output, _ = _invoke_command(
    "long.novel.summary.save",
    {
        "novelId": "novel/1",
        "summary": "新摘要",
        "expectedUpdatedAt": "2026-08-09T00:00:00Z",
    },
    api,
)
assert api.calls == [
    (
        "PUT",
        "/api/v1/novels/novel%2F1/summary",
        {"json": {"summary": "新摘要", "expectedUpdatedAt": "2026-08-09T00:00:00Z"}},
    )
]
```

同时覆盖 `summary=null`、缺字段、布尔/数字摘要、空版本、`outputFile`、`clientRequestId`、未知字段和
CommandSpec；注册表精确计数改为 81 / 48，结构化写集合仍为 33。

- [ ] **Step 2: 运行 CLI 目标测试并确认 RED**

Run: `uv run pytest tools/inkforge-cli/tests/test_long_novel_commands.py tools/inkforge-cli/tests/test_registry.py -q`

Expected: 因命令未注册而失败。

- [ ] **Step 3: 实现 handler 与 CommandSpec**

```python
def save_summary(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(
        payload,
        required=frozenset({"novelId", "summary", "expectedUpdatedAt"}),
    )
    summary = payload["summary"]
    if summary is not None and not isinstance(summary, str):
        raise CliInputError("INVALID_FIELD", "summary 必须是字符串或 null")
    return ensure_command_json_result(
        runtime.require_api().request(
            "PUT",
            f"/api/v1/novels/{public_id(require_string(payload, 'novelId'))}/summary",
            json={
                "summary": summary,
                "expectedUpdatedAt": require_expected_updated_at(payload),
            },
        )
    )
```

CommandSpec 声明为 JSON 写命令、需身份、不要求 `clientRequestId`、无文件输出。

- [ ] **Step 4: 更新 README 和精确命令清单**

说明摘要写入的 GET/Diff/CAS/回读边界，并在命令列表中加入 `long.novel.summary.save`。

- [ ] **Step 5: 运行 CLI 全量测试、Ruff、Mypy**

Run:

```powershell
uv run pytest tools/inkforge-cli/tests -q
uv run ruff check tools/inkforge-cli/src tools/inkforge-cli/tests
uv run mypy tools/inkforge-cli/src
```

Expected: 全部退出 0。

### Task 3: 生成公共 TypeScript 客户端

**Files:**
- Modify: `packages/api-client/src/generated/**`（由生成脚本决定具体文件）

- [ ] **Step 1: 运行生成前检查并确认接口差异**

Run: `npm run api:check`

Expected: 因新增 OpenAPI 路由尚未生成而非零退出。

- [ ] **Step 2: 生成客户端**

Run: `npm run api:generate`

- [ ] **Step 3: 校验生成结果与 TypeScript**

Run:

```powershell
npm run api:check
npm run typecheck
```

Expected: 全部退出 0，生成代码包含摘要 PUT 方法和严格请求类型。

### Task 4: 同步本地与生产 Operator Skills

**Files:**
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/scripts/operator.ps1`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/SKILL.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/references/cli-contract.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/references/long-serial-workflow.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/references/recovery.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/tests/long-cli.Tests.ps1`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/tests/structured-writes.Tests.ps1`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-short-story-operator/SKILL.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-short-story-operator/references/cli-contract.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-short-story-operator/references/long-serial-workflow.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-short-story-operator/references/recovery.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-short-story-operator/tests/long-cli.Tests.ps1`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-short-story-operator/tests/long-workflow-parity.Tests.ps1`

- [ ] **Step 1: 先修改 Skill 测试并确认 RED**

生产 allowlist 期望加入 `long.novel.summary.save`，计数改为 81 / 65 / 48 / 33；本地与生产流程测试要求
包含 `long.novel.get`、完整 Diff、`expectedUpdatedAt`、写后回读和 `NOVEL_VERSION_CONFLICT`。

Run: 生产 `long-cli.Tests.ps1`、`structured-writes.Tests.ps1` 与本地 `long-cli.Tests.ps1`、
`long-workflow-parity.Tests.ps1`。

Expected: wrapper/文档尚未更新，测试失败。

- [ ] **Step 2: 更新两个 Skill 的命令、流程和恢复规则**

摘要修改作为独立作品元数据闭环，不进入章节闭环，也不计入 33 条结构化创作资料写命令。生产 wrapper
增加精确 allowlist 项；本地 wrapper 保持通用透传。

- [ ] **Step 3: 运行两个 Skill 的全部测试与 quick_validate**

Run: 两个 `tests/*.ps1` 全部脚本，以及：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8:strict'
python C:\Users\niebo\.codex\skills\.system\skill-creator\scripts\quick_validate.py <Skill目录>
```

Expected: 全部退出 0。

### Task 5: 集成验证与提交

**Files:**
- Verify: all files above

- [ ] **Step 1: 运行仓库相关完整验证**

```powershell
uv run pytest apps/core-api/tests/novels/test_novel_api.py tools/inkforge-cli/tests -q
uv run ruff check .
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src tools/inkforge-cli/src
npm run api:check
npm run test:web
npm run typecheck
npm run lint
```

- [ ] **Step 2: 检查范围和 diff**

Run: `git status --short`、`git diff --check`、`git diff --stat`。

Expected: 不包含 PostgreSQL schema、Agent Service 业务实现或无关用户文件。

- [ ] **Step 3: 请求独立代码审查并修复发现的问题**

审查必须核对 CAS、归属、null 清空、API 客户端、命令计数与两个 Skill 业务一致性。

- [ ] **Step 4: 重新运行受影响验证并提交**

```powershell
git add -- <本计划列出的仓库文件>
git diff --cached --check
git commit -m "功能：开放长篇作品摘要写入"
```
