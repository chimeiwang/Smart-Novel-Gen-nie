# 长篇创作资料 CLI 安全写入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为长篇创作资料交付 32 条具备 CAS、创建幂等、删除影响和生产回拉验证的公共 CLI 写命令。

**Architecture:** Core API 继续是唯一业务权威；单例、更新和删除在目标事务内执行版本比较，创建使用稳定
`clientRequestId` 生成确定性资源 ID。Web 同步使用同一公共 CAS 契约，CLI 只做严格 JSON/文件映射，
生产 Skill 用精确白名单、完整 Diff、一次确认和写后 GET 管理线上操作。

**Tech Stack:** FastAPI、Pydantic v2、SQLAlchemy async、PostgreSQL、pytest、Python 3.12、Next.js 16、
React 19、openapi-fetch、TypeScript、Node test runner、PowerShell。

---

## 执行前约束

- 当前主工作区包含与本功能无关的未提交改动。执行时从提交 `1b153d4` 创建隔离 worktree 和
  `codex/long-creative-material-writes` 分支，不复制主工作区脏文件。
- 不修改 `apps/core-api/src/inkforge_core/db/schema-contract.json`，不新增迁移或 DDL。
- 每项功能严格执行 RED → GREEN → 重构；没有观察到目标测试按预期失败，不写对应生产代码。
- 公共接口变化后只通过 `npm run api:generate` 更新生成客户端，禁止手写生成 DTO。
- 生产 Skill 位于仓库外，不能混入仓库提交；其离线测试必须在仓库实现完成后单独执行。

## 文件职责

### Core

- 新增 `apps/core-api/src/inkforge_core/concurrency.py`：UTC 版本比较、单调时间和确定性资源 ID。
- 修改 `lore/schemas.py`、`service.py`、`repository.py`、`router.py`：单例、五类实体、关系和经历。
- 修改 `outlines/schemas.py`、`service.py`、`repository.py`：剧情进度 CAS。
- 修改 `references/schemas.py`、`service.py`、`repository.py`、`router.py`：资料 CAS、创建幂等和重索引。
- 修改 `styles/schemas.py`、`service.py`、`repository.py`、`router.py`：文风应用值 CAS。
- 修改 `novels/schemas.py`、`repository.py`：planning GET 返回 `storyProgressUpdatedAt`。

### Web

- 修改 `lib/api/response.ts`：完整保留 Core 错误结构并识别 409。
- 修改 `workspace/library-pane.tsx`、`progress/progress-panel.tsx`：单例资料版本来源与草稿保留。
- 新增 `features/lore/lore-mutation-plan.ts`：关系和经历的纯函数差量计划。
- 修改 `features/lore/lore-panel.tsx`：实体 CAS、稳定创建请求 ID 和差量关系/经历写入。
- 修改 `features/references/reference-panel.tsx`、`features/styles/style-panel.tsx`：创建幂等和应用值 CAS。

### CLI

- 新增 `commands/long/mutation_support.py`：字段、ID、CAS、文件和 patch 公共校验。
- 新增 `planning_mutations.py`、`lore_entities.py`、`lore_relationships.py`、`references.py`、`styles.py`：
  32 条命令的五个内聚模块。
- 修改 `registry.py` 和 `tools/inkforge-cli/README.md`：精确注册、清单与恢复语义。

### 生产 Skill

- 修改 `SKILL.md`、`scripts/operator.ps1`、`references/cli-contract.md`、
  `references/long-serial-workflow.md`、`references/recovery.md`。
- 新增 `references/long-creative-material-writes.md` 和 `tests/structured-writes.Tests.ps1`。

## Task 1：建立 Core 并发基础设施和单例设定 CAS

**Files:**
- Create: `apps/core-api/src/inkforge_core/concurrency.py`
- Modify: `apps/core-api/src/inkforge_core/lore/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/lore/service.py`
- Modify: `apps/core-api/src/inkforge_core/lore/repository.py`
- Modify: `apps/core-api/src/inkforge_core/lore/router.py`
- Modify: `apps/core-api/src/inkforge_core/novels/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/novels/repository.py`
- Test: `apps/core-api/tests/lore/test_safe_content_mutations.py`
- Test: `apps/core-api/tests/lore/test_lore_service.py`
- Test: `apps/core-api/tests/lore/test_contracts.py`

- [ ] **Step 1: 写单例首次创建、幂等、版本冲突和长篇篇幅守卫失败测试**

```python
def test_content_request_requires_explicit_nullable_version() -> None:
    with pytest.raises(ValidationError):
        ContentRequest.model_validate({"content": "背景"})
    request = ContentRequest.model_validate(
        {"content": "背景", "expectedUpdatedAt": None}
    )
    assert request.expectedUpdatedAt is None

@pytest.mark.asyncio
async def test_stale_world_setting_does_not_overwrite_current_value(repository) -> None:
    current = await repository.upsert_content(
        "novel-1", "user-1", "world-setting", "当前", None
    )
    with pytest.raises(ApiError) as caught:
        await repository.upsert_content(
            "novel-1", "user-1", "world-setting", "旧草稿", EPOCH
        )
    assert caught.value.code == "LORE_CONTENT_VERSION_CONFLICT"
    assert (await repository.get_content("novel-1", "user-1", "world-setting"))["content"] == "当前"
```

- [ ] **Step 2: 运行测试并确认 RED 原因是缺少版本字段和 CAS**

Run:

```powershell
uv run pytest apps/core-api/tests/lore/test_safe_content_mutations.py apps/core-api/tests/lore/test_lore_service.py apps/core-api/tests/lore/test_contracts.py -q
```

Expected: FAIL，错误明确指向 `expectedUpdatedAt` 不存在、仓储签名不接受版本或旧内容仍被覆盖。

- [ ] **Step 3: 实现公共版本帮助函数**

```python
def require_expected_updated_at(
    current: datetime | None,
    expected: datetime | None,
    *,
    code: str,
) -> None:
    if utc(current) != utc(expected):
        raise ApiError(
            status_code=409,
            code=code,
            message="资源版本已变化，请重新读取",
            details={"currentUpdatedAt": utc(current).isoformat() if current else None},
        )

def next_utc_timestamp(current: datetime | None) -> datetime:
    candidate = datetime.now(UTC)
    return max(candidate, utc(current) + timedelta(microseconds=1)) if current else candidate

def command_resource_id(namespace: str, user_id: str, novel_id: str, request_id: str) -> str:
    source = "\x1f".join((namespace, user_id, novel_id, request_id)).encode("utf-8")
    return "ifc_" + hashlib.sha256(source).hexdigest()
```

- [ ] **Step 4: 给单例请求、服务和仓储接入显式 CAS**

```python
class ContentRequest(StrictModel):
    content: str | None
    expectedUpdatedAt: JsonDatetime | None

class WritingBibleRequest(WritingBibleFields):
    expectedUpdatedAt: JsonDatetime | None

async def upsert_content(
    self,
    novel_id: str,
    user_id: str,
    kind: str,
    content: Any,
    expected_updated_at: datetime | None,
) -> dict[str, Any]:
    async with self._session_factory() as session:
        async with session.begin():
            await self._require_owner(session, novel_id, user_id)
            current = await self._lock_content(session, novel_id, kind)
            current_version = _utc(current.updatedAt) if current is not None else None
            require_expected_updated_at(
                current_version,
                expected_updated_at,
                code="LORE_CONTENT_VERSION_CONFLICT",
            )
            if current is not None and self._content_matches(kind, current, content):
                return _model_dict(current)
            return await self._write_content(
                session,
                novel_id,
                kind,
                content,
                next_utc_timestamp(current_version),
            )
```

实施时拆分 `WritingBibleFields`，让请求携带 `expectedUpdatedAt`，响应只携带业务字段和服务端版本；
不得让请求前置条件回显到 `WritingBibleResponse`。实际更新显式写入
`updatedAt=next_utc_timestamp(current_version)`。
`story-progress` 以锁定后的 `Novel.updatedAt` 为版本，并由 planning GET 新增
`storyProgressUpdatedAt` 返回该值。

- [ ] **Step 5: 在服务层固定长篇作品圣经守卫**

```python
if kind == "writing-bible" and content.get("storyLengthProfile") not in {None, "long_serial"}:
    raise ApiError(
        status_code=422,
        code="WRITING_BIBLE_PROFILE_MISMATCH",
        message="长篇作品不能改为中短篇模式",
    )
```

- [ ] **Step 6: 运行单例相关测试并确认 GREEN**

Run:

```powershell
uv run pytest apps/core-api/tests/lore -q
```

Expected: PASS，且单例实际更新后的 `updatedAt` 严格大于旧值。

- [ ] **Step 7: 提交单例 CAS**

```powershell
git add apps/core-api/src/inkforge_core/concurrency.py apps/core-api/src/inkforge_core/lore apps/core-api/src/inkforge_core/novels apps/core-api/tests/lore
git commit -m "核心：为长篇单例设定增加版本控制"
```

## Task 2：实现五类设定实体的幂等创建、CAS 和删除影响

**Files:**
- Modify: `apps/core-api/src/inkforge_core/lore/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/lore/service.py`
- Modify: `apps/core-api/src/inkforge_core/lore/repository.py`
- Modify: `apps/core-api/src/inkforge_core/lore/router.py`
- Create: `apps/core-api/tests/lore/test_safe_entity_mutations.py`
- Modify: `apps/core-api/tests/lore/test_crud_matrix.py`
- Modify: `apps/core-api/tests/lore/test_repository_boundaries.py`

- [ ] **Step 1: 写五类矩阵的创建重放、旧版本更新和引用删除失败测试**

```python
@pytest.mark.parametrize("kind", ["characters", "items", "locations", "factions", "glossary"])
@pytest.mark.asyncio
async def test_same_create_request_does_not_duplicate_entity(repository, kind, create_fields) -> None:
    first = await repository.create_entity(
        "novel-1", "user-1", kind, "stable-request-0001", create_fields
    )
    second = await repository.create_entity(
        "novel-1", "user-1", kind, "stable-request-0001", create_fields
    )
    assert second["id"] == first["id"]
    assert second["effective"] is False

@pytest.mark.asyncio
async def test_character_delete_reports_dependencies(repository) -> None:
    with pytest.raises(ApiError) as caught:
        await repository.delete_entity(
            "novel-1", "user-1", "characters", "character-1", CURRENT_VERSION
        )
    assert caught.value.code == "LORE_ENTITY_REFERENCED"
    assert caught.value.details == {"relations": 1, "experiences": 1, "ownedItems": 1}
```

- [ ] **Step 2: 运行矩阵测试确认 RED**

Run:

```powershell
uv run pytest apps/core-api/tests/lore/test_safe_entity_mutations.py apps/core-api/tests/lore/test_crud_matrix.py apps/core-api/tests/lore/test_repository_boundaries.py -q
```

Expected: FAIL，当前创建产生随机 ID，更新/删除签名没有 `expectedUpdatedAt`，角色删除没有引用报告。

- [ ] **Step 3: 重构请求/响应 DTO，避免操作字段泄漏**

```python
class CreateCharacterRequest(CharacterFields):
    clientRequestId: str = Field(min_length=16, max_length=256)

class UpdateCharacterRequest(CharacterPatch):
    expectedUpdatedAt: JsonDatetime

class CharacterResponse(CharacterFields):
    id: str
    effective: bool = True
    createdAt: datetime
    updatedAt: datetime

class DeleteImpactResponse(StrictModel):
    deletedType: str
    deletedId: str
    affected: dict[str, int]
```

对角色、物品、地点、势力和术语分别保留严格字段类型；创建请求包含稳定 ID，更新请求包含版本，响应不
包含 `clientRequestId` 或 `expectedUpdatedAt`。删除路由从空 204 改为显式 `DeleteImpactResponse`；无下游
影响时 `affected={}`，引用冲突仍返回带计数的 409。

- [ ] **Step 4: 在仓储事务中实现确定性 ID、版本锁和引用拒绝**

```python
entity_id = command_resource_id(kind, user_id, novel_id, client_request_id)
current = await session.scalar(
    select(model).where(model.id == entity_id).with_for_update()
)
if current is not None:
    if _creation_fields(current) != fields:
        raise ApiError(status_code=409, code="RESOURCE_CREATE_CONFLICT", message="创建请求已绑定其他内容")
    return {**_model_dict(current), "effective": False}
```

更新和删除先使用带 `with_for_update()` 的目标实体查询，再用 `require_expected_updated_at()` 比较；实际变化推进
版本。删除角色、地点和势力前查询规范中列出的引用计数，存在引用时返回 `LORE_ENTITY_REFERENCED`，
不依赖数据库隐式级联。

- [ ] **Step 5: 运行五类实体测试并确认 GREEN**

Run:

```powershell
uv run pytest apps/core-api/tests/lore/test_safe_entity_mutations.py apps/core-api/tests/lore/test_crud_matrix.py apps/core-api/tests/lore/test_repository_boundaries.py -q
```

Expected: PASS，五类资源均覆盖相同请求重放、不同内容冲突、CAS 和删除引用。

- [ ] **Step 6: 提交实体安全写入**

```powershell
git add apps/core-api/src/inkforge_core/lore apps/core-api/tests/lore
git commit -m "核心：开放设定实体安全写入契约"
```

## Task 3：实现人物关系和人物经历的安全写入

**Files:**
- Modify: `apps/core-api/src/inkforge_core/lore/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/lore/service.py`
- Modify: `apps/core-api/src/inkforge_core/lore/repository.py`
- Modify: `apps/core-api/src/inkforge_core/lore/router.py`
- Create: `apps/core-api/tests/lore/test_safe_relationship_mutations.py`

- [ ] **Step 1: 写关系/经历幂等、版本和跨小说引用失败测试**

```python
@pytest.mark.asyncio
async def test_experience_update_requires_its_own_version(client) -> None:
    response = await client.patch(
        "/api/v1/novels/novel-1/experiences/experience-1",
        json={"content": "修订", "expectedUpdatedAt": "2026-08-06T00:00:00Z"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "LORE_EXPERIENCE_VERSION_CONFLICT"

@pytest.mark.asyncio
async def test_relation_create_replay_returns_one_relation(repository) -> None:
    first = await repository.create_relation("novel-1", "user-1", "relation-request-0001", FIELDS)
    second = await repository.create_relation("novel-1", "user-1", "relation-request-0001", FIELDS)
    assert first["id"] == second["id"]
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```powershell
uv run pytest apps/core-api/tests/lore/test_safe_relationship_mutations.py -q
```

Expected: FAIL，当前关系/经历没有创建请求身份或更新/删除版本。

- [ ] **Step 3: 拆分创建和更新 DTO 并接入仓储版本**

```python
class CreateExperienceRequest(ExperienceFields):
    clientRequestId: str = Field(min_length=16, max_length=256)

class UpdateExperienceRequest(ExperiencePatch):
    expectedUpdatedAt: JsonDatetime

class CreateRelationRequest(RelationFields):
    clientRequestId: str = Field(min_length=16, max_length=256)

class UpdateRelationRequest(RelationPatch):
    expectedUpdatedAt: JsonDatetime
```

经历 create 继续验证 `characterId` 与可选 `chapterId` 属于当前小说；关系 create 验证两端角色。更新和
删除分别返回 `LORE_EXPERIENCE_VERSION_CONFLICT`、`LORE_RELATION_VERSION_CONFLICT`。成功删除返回
`DeleteImpactResponse`，明确只删除目标关系或经历。

- [ ] **Step 4: 运行关系/经历测试并确认 GREEN**

Run:

```powershell
uv run pytest apps/core-api/tests/lore/test_safe_relationship_mutations.py apps/core-api/tests/lore -q
```

Expected: PASS，且没有跨小说引用或无版本删除路径。

- [ ] **Step 5: 提交关系和经历安全写入**

```powershell
git add apps/core-api/src/inkforge_core/lore apps/core-api/tests/lore
git commit -m "核心：为人物关系和经历增加安全写入"
```

## Task 4：实现剧情进度 CAS

**Files:**
- Modify: `apps/core-api/src/inkforge_core/outlines/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/outlines/service.py`
- Modify: `apps/core-api/src/inkforge_core/outlines/repository.py`
- Create: `apps/core-api/tests/outlines/test_plot_progress_cas.py`
- Modify: `apps/core-api/tests/outlines/test_repository_contract.py`

- [ ] **Step 1: 写首次创建、幂等和旧版本冲突测试**

```python
def test_plot_progress_request_requires_explicit_nullable_version() -> None:
    with pytest.raises(ValidationError):
        PlotProgressRequest.model_validate({"currentStage": "开篇"})

def test_plot_progress_conflict_uses_stable_code() -> None:
    with pytest.raises(ApiError) as caught:
        require_expected_updated_at(CURRENT, OLD, code="PLOT_PROGRESS_VERSION_CONFLICT")
    assert caught.value.code == "PLOT_PROGRESS_VERSION_CONFLICT"
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```powershell
uv run pytest apps/core-api/tests/outlines/test_plot_progress_cas.py apps/core-api/tests/outlines/test_repository_contract.py -q
```

Expected: FAIL，`PlotProgressRequest` 没有版本，`_upsert_singleton` 不推进更新时间。

- [ ] **Step 3: 在既有小说锁内比较版本并显式推进时间**

```python
class PlotProgressRequest(StrictModel):
    currentStage: str
    currentGoal: str | None = None
    currentConflict: str | None = None
    nextMilestone: str | None = None
    expectedUpdatedAt: JsonDatetime | None
```

`OutlineService.save_plot()` 把业务字段和版本分开传入；`upsert_plot()` 锁定 Novel 与 PlotProgress，版本
正确后才判断内容相同或更新，并返回新的 `updatedAt`。

- [ ] **Step 4: 运行 outlines 测试并提交**

Run:

```powershell
uv run pytest apps/core-api/tests/outlines -q
```

Expected: PASS。

```powershell
git add apps/core-api/src/inkforge_core/outlines apps/core-api/tests/outlines
git commit -m "核心：为剧情进度增加版本控制"
```

## Task 5：实现参考资料 CAS、创建幂等和稳定重索引

**Files:**
- Modify: `apps/core-api/src/inkforge_core/references/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/references/service.py`
- Modify: `apps/core-api/src/inkforge_core/references/repository.py`
- Modify: `apps/core-api/src/inkforge_core/references/router.py`
- Create: `apps/core-api/tests/references/test_safe_mutations.py`
- Modify: `apps/core-api/tests/references/test_reference_service.py`
- Modify: `apps/core-api/tests/references/test_repository_contract.py`

- [ ] **Step 1: 写创建重放、更新/删除版本和 reindex 请求复用测试**

```python
@pytest.mark.asyncio
async def test_reference_create_replay_returns_same_id(service) -> None:
    body = CreateReferenceRequest(
        clientRequestId="reference-create-0001",
        title="资料", type="note", content="正文", sourceUrl=None,
    )
    first = await service.create_reference("user-1", "novel-1", body)
    second = await service.create_reference("user-1", "novel-1", body)
    assert first.id == second.id

@pytest.mark.asyncio
async def test_reindex_same_request_submits_one_job(service, submitter) -> None:
    body = ReindexReferenceRequest(expectedContentHash=HASH)
    await service.reindex("user-1", "novel-1", "reference-1", body)
    await service.reindex("user-1", "novel-1", "reference-1", body)
    assert len(submitter.jobs) == 1
```

- [ ] **Step 2: 运行 reference 测试确认 RED**

Run:

```powershell
uv run pytest apps/core-api/tests/references/test_safe_mutations.py apps/core-api/tests/references/test_reference_service.py apps/core-api/tests/references/test_repository_contract.py -q
```

Expected: FAIL，当前 create 随机生成 ID，update/delete/reindex 没有目标版本或稳定请求身份。

- [ ] **Step 3: 实现资料事务版本和重索引绑定**

```python
class CreateReferenceRequest(StrictModel):
    clientRequestId: str = Field(min_length=16, max_length=256)
    title: str
    type: ReferenceType
    content: str
    sourceUrl: str | None = None

class UpdateReferenceRequest(ReferencePatch):
    expectedUpdatedAt: JsonDatetime

class ReindexReferenceRequest(StrictModel):
    expectedContentHash: ContentHash
```

创建使用 `command_resource_id("reference", user_id, novel_id, body.clientRequestId)`；update/delete 锁定
ReferenceMaterial 与 RagDocument 后比较版本。reindex 在 `expectedContentHash` 匹配时复用现有
`referenceId + contentHash` 确定性任务身份；相同任务直接返回，不重复入队。删除成功响应包含
`{"reference": 1, "ragDocuments": 1, "ragChunks": n}`。

- [ ] **Step 4: 运行 references 测试并提交**

Run:

```powershell
uv run pytest apps/core-api/tests/references -q
```

Expected: PASS，资料写入成功与 `ragStatus` ready/failed 仍严格区分。

```powershell
git add apps/core-api/src/inkforge_core/references apps/core-api/tests/references
git commit -m "核心：开放参考资料安全写入契约"
```

## Task 6：实现文风应用值 CAS

**Files:**
- Modify: `apps/core-api/src/inkforge_core/styles/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/styles/service.py`
- Modify: `apps/core-api/src/inkforge_core/styles/repository.py`
- Modify: `apps/core-api/src/inkforge_core/styles/router.py`
- Create: `apps/core-api/tests/styles/test_apply_style_cas.py`
- Modify: `apps/core-api/tests/styles/test_style_api.py`

- [ ] **Step 1: 写 apply/clear 幂等和旧应用值冲突测试**

```python
@pytest.mark.asyncio
async def test_style_apply_rejects_stale_expected_style(repository) -> None:
    with pytest.raises(ApiError) as caught:
        await repository.apply_style(
            "user-1", "novel-1", "style-new", expected_style_id="style-old"
        )
    assert caught.value.code == "APPLIED_STYLE_VERSION_CONFLICT"

@pytest.mark.asyncio
async def test_style_clear_is_idempotent(repository) -> None:
    result = await repository.apply_style("user-1", "novel-1", None, expected_style_id=None)
    assert result["effective"] is False
```

- [ ] **Step 2: 运行 style 测试确认 RED**

Run:

```powershell
uv run pytest apps/core-api/tests/styles/test_apply_style_cas.py apps/core-api/tests/styles/test_style_api.py -q
```

Expected: FAIL，当前请求只有 `styleId`，旧值能够覆盖。

- [ ] **Step 3: 增加 expectedStyleId 并在小说行锁内比较**

```python
class ApplyStyleRequest(StrictModel):
    styleId: str | None
    expectedStyleId: str | None
```

仓储锁定 Novel 后先比较 `appliedStyleId`；目标相同返回 `effective=false`，否则验证新文风归属和完整画像
后更新。路由返回显式 JSON 结果，不再用空 204 隐藏 effective 状态。

- [ ] **Step 4: 运行 styles 测试并提交**

Run:

```powershell
uv run pytest apps/core-api/tests/styles -q
```

Expected: PASS。

```powershell
git add apps/core-api/src/inkforge_core/styles apps/core-api/tests/styles
git commit -m "核心：为小说文风应用增加并发控制"
```

## Task 7：生成公共客户端并让 Web 单例资料使用 CAS

**Files:**
- Modify: `apps/core-api/tests/test_openapi_long_serial.py`
- Modify: `packages/api-client/src/generated/schema.d.ts`（仅生成命令）
- Modify: `apps/web/src/lib/api/response.ts`
- Modify: `apps/web/src/features/workspace/library-pane.tsx`
- Modify: `apps/web/src/features/progress/progress-panel.tsx`
- Test: `apps/web/src/lib/api/__tests__/response.test.ts`
- Create: `apps/web/src/features/workspace/__tests__/creative-material-cas.test.ts`
- Modify: `apps/web/src/features/workspace/__tests__/library-pane-source.test.ts`

- [ ] **Step 1: 写 OpenAPI 字段、完整 409 和单例版本来源失败测试**

```typescript
test("409 保留 Core 冲突信息", () => {
  const error = apiError({
    status: 409,
    error: { code: "LORE_CONTENT_VERSION_CONFLICT", message: "冲突", details: { currentUpdatedAt: "v2" }, requestId: "req-1" },
  });
  assert.equal(error.code, "LORE_CONTENT_VERSION_CONFLICT");
  assert.deepEqual(error.details, { currentUpdatedAt: "v2" });
  assert.equal(error.requestId, "req-1");
});
```

Python OpenAPI 测试精确断言 `expectedUpdatedAt`、`clientRequestId`、`expectedStyleId` 和
`storyProgressUpdatedAt` 出现在对应 schema，且 32 条能力没有生成内部接口。

- [ ] **Step 2: 运行 OpenAPI/Web 测试确认 RED**

Run:

```powershell
uv run pytest apps/core-api/tests/test_openapi_long_serial.py -q
npm exec --workspace @inkforge/web -- tsx --test src/lib/api/__tests__/response.test.ts src/features/workspace/__tests__/creative-material-cas.test.ts src/features/workspace/__tests__/library-pane-source.test.ts
```

Expected: FAIL，生成 DTO 和 Web 请求尚无 CAS，错误包装丢失 code/details/requestId。

- [ ] **Step 3: 重新生成 API 客户端**

Run:

```powershell
npm run api:generate
npm run api:check
```

Expected: 两条命令均退出 0，第二条报告无生成漂移。

- [ ] **Step 4: 实现统一冲突错误和单例版本传递**

```typescript
export class ApiResponseError extends Error {
  constructor(
    readonly status: number,
    readonly code: string | undefined,
    message: string,
    readonly details: unknown,
    readonly requestId: string | undefined,
  ) { super(message); }
}

function savePlanningText(path: PlanningTextPath, content: string, expectedUpdatedAt: string | null) {
  return browserApi.PUT(path, {
    params: { path: { novel_id: novelId } },
    body: { content, expectedUpdatedAt },
  });
}
```

故事背景、世界设定使用各自 DTO 的 `updatedAt`；作品圣经使用自身版本；剧情进度改用生成
`PlotProgressDto`；故事进展使用新增 `planning.storyProgressUpdatedAt`。409 时保留组件草稿，只显示冲突并
等待用户刷新，不自动把新版本塞进原请求重试。

- [ ] **Step 5: 运行 Web 单例测试并提交**

Run:

```powershell
npm exec --workspace @inkforge/web -- tsx --test src/lib/api/__tests__/response.test.ts src/features/workspace/__tests__/creative-material-cas.test.ts src/features/workspace/__tests__/library-pane-source.test.ts
```

Expected: PASS。

```powershell
git add apps/core-api/tests/test_openapi_long_serial.py packages/api-client/src/generated/schema.d.ts apps/web/src/lib/api apps/web/src/features/workspace apps/web/src/features/progress
git commit -m "前端：接入创作资料版本冲突保护"
```

## Task 8：让 Web 实体、关系、经历、参考资料和文风使用安全契约

**Files:**
- Create: `apps/web/src/features/lore/lore-mutation-plan.ts`
- Create: `apps/web/src/features/lore/__tests__/lore-mutation-plan.test.ts`
- Modify: `apps/web/src/features/lore/lore-panel.tsx`
- Modify: `apps/web/src/features/references/reference-panel.tsx`
- Create: `apps/web/src/features/references/__tests__/reference-mutation-state.test.ts`
- Modify: `apps/web/src/features/styles/style-panel.tsx`
- Create: `apps/web/src/features/styles/__tests__/style-panel-cas-source.test.ts`

- [ ] **Step 1: 写差量计划、稳定请求 ID 和应用值来源失败测试**

```typescript
test("关系和经历按 id 生成增改删，不全删全建", () => {
  const plan = buildChildMutationPlan(original, draft);
  assert.deepEqual(plan.deletes.map((item) => item.id), ["removed"]);
  assert.deepEqual(plan.updates.map((item) => item.id), ["changed"]);
  assert.equal(plan.creates[0].clientRequestId, "stable-create-id");
});

test("文风请求使用 resources GET 的当前值", () => {
  assert.deepEqual(buildApplyStyleBody("new", "current"), {
    styleId: "new",
    expectedStyleId: "current",
  });
});
```

- [ ] **Step 2: 运行 Web 资料测试确认 RED**

Run:

```powershell
npm exec --workspace @inkforge/web -- tsx --test src/features/lore/__tests__/lore-mutation-plan.test.ts src/features/references/__tests__/reference-mutation-state.test.ts src/features/styles/__tests__/style-panel-cas-source.test.ts
```

Expected: FAIL，纯函数不存在，当前关系/经历仍全删全建，请求缺少版本和创建请求 ID。

- [ ] **Step 3: 实现纯差量计划并更新 LorePanel**

```typescript
export function buildChildMutationPlan<T extends VersionedDraft>(
  original: readonly T[],
  draft: readonly T[],
): MutationPlan<T> {
  const before = new Map(original.map((item) => [item.id, item]));
  const after = new Map(draft.filter((item) => item.id).map((item) => [item.id!, item]));
  return {
    deletes: original.filter((item) => !after.has(item.id!)),
    updates: draft.filter((item) => item.id && !sameBusinessFields(before.get(item.id), item)),
    creates: draft.filter((item) => !item.id),
  };
}
```

五类实体 update/delete 使用实体 DTO 的 `updatedAt`；create 使用一次编辑会话内稳定保存的
`newClientRequestId()`。关系和经历本地状态保留 `updatedAt` 与新条目的 `clientRequestId`，按差量顺序
执行 delete/update/create；任一 409 停止后续请求并保持编辑层和表单。

- [ ] **Step 4: 更新参考资料创建与文风 apply/clear**

参考资料表单创建时生成并保留一个 `clientRequestId`，成功后才替换；重试复用原值。文风请求始终以
最新 `resources.appliedStyle?.id ?? null` 为 `expectedStyleId`，不回退 bootstrap；当前应用项提供清除
按钮，发送 `{styleId: null, expectedStyleId}`。

- [ ] **Step 5: 运行 Web 资料测试并提交**

Run:

```powershell
npm exec --workspace @inkforge/web -- tsx --test src/features/lore/__tests__/lore-mutation-plan.test.ts src/features/references/__tests__/reference-mutation-state.test.ts src/features/styles/__tests__/style-panel-cas-source.test.ts
```

Expected: PASS。

```powershell
git add apps/web/src/features/lore apps/web/src/features/references apps/web/src/features/styles
git commit -m "前端：安全保存长篇设定和素材"
```

## Task 9：实现 CLI 公共校验和五条单例命令

**Files:**
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/long/mutation_support.py`
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/long/planning_mutations.py`
- Create: `tools/inkforge-cli/tests/test_long_planning_mutations.py`

- [ ] **Step 1: 写五条路由、nullable CAS、文件无损和字段拒绝测试**

```python
@pytest.mark.parametrize(
    ("command", "path"),
    [
        ("long.lore.story-background.save", "/api/v1/novels/novel-1/story-background"),
        ("long.lore.world-setting.save", "/api/v1/novels/novel-1/world-setting"),
        ("long.lore.writing-bible.save", "/api/v1/novels/novel-1/writing-bible"),
        ("long.lore.story-progress.save", "/api/v1/novels/novel-1/story-progress"),
        ("long.plot-progress.save", "/api/v1/novels/novel-1/plot-progress"),
    ],
)
def test_planning_commands_send_exact_routes(command, path):
    module = importlib.import_module("inkforge_cli.commands.long.planning_mutations")
    spec = next(item for item in module.PLANNING_COMMAND_SPECS if item.name == command)
    api = RecordingApi()
    payload = {
        "novelId": "novel-1",
        "expectedUpdatedAt": None,
        "data": {"genre": "末法修仙"},
    } if command == "long.lore.writing-bible.save" else {
        "novelId": "novel-1",
        "expectedUpdatedAt": None,
        "data": {
            "currentStage": "开篇",
            "currentGoal": None,
            "currentConflict": None,
            "nextMilestone": None,
        },
    } if command == "long.plot-progress.save" else {
        "novelId": "novel-1",
        "expectedUpdatedAt": None,
        "content": "正文",
    }
    spec.handler(make_runtime(spec, api), payload)
    assert api.calls[0][0:2] == ("PUT", path)
```

文件测试写入 `"正文\r\n" + "甲" * 80_000 + "尾部😀e\u0301\r\n"`，断言发送字节解码后的字符串
完全一致；缺少 `expectedUpdatedAt`、同时提供 content/contentFile、出现 outputFile/未知字段均不得发请求。

- [ ] **Step 2: 运行 CLI 单例测试确认 RED**

Run:

```powershell
uv run --package inkforge-cli pytest tools/inkforge-cli/tests/test_long_planning_mutations.py -q
```

Expected: FAIL，新模块和命令尚不存在。

- [ ] **Step 3: 实现公共 mutation_support 和 planning handlers**

```python
def require_payload_fields(payload: JsonObject, *, required: set[str], optional: set[str]) -> None:
    allowed = required | optional | {"profile"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise CliInputError("UNEXPECTED_FIELDS", f"命令包含不支持的字段：{', '.join(unknown)}")

def require_content_source(payload: JsonObject) -> str:
    has_text = "content" in payload
    has_file = "contentFile" in payload
    if has_text == has_file:
        raise CliInputError("CONTENT_SOURCE_REQUIRED", "content 与 contentFile 必须且只能提供一个")
    return require_string(payload, "content", allow_empty=True) if has_text else read_utf8_text_exact(require_string(payload, "contentFile"))
```

`planning_mutations.py` 定义 5 个显式 `CommandSpec`；structured data 逐字段白名单，圣经拒绝
`storyLengthProfile=short_medium`。五条均为 CAS，不要求 `clientRequestId`。

- [ ] **Step 4: 运行 CLI 单例测试并提交**

Run:

```powershell
uv run --package inkforge-cli pytest tools/inkforge-cli/tests/test_long_planning_mutations.py -q
```

Expected: PASS。

```powershell
git add tools/inkforge-cli/src/inkforge_cli/commands/long/mutation_support.py tools/inkforge-cli/src/inkforge_cli/commands/long/planning_mutations.py tools/inkforge-cli/tests/test_long_planning_mutations.py
git commit -m "命令行：增加长篇单例资料写命令"
```

## Task 10：实现其余 27 条 CLI 命令并注册完整命令面

**Files:**
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/long/lore_entities.py`
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/long/lore_relationships.py`
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/long/references.py`
- Create: `tools/inkforge-cli/src/inkforge_cli/commands/long/styles.py`
- Modify: `tools/inkforge-cli/src/inkforge_cli/registry.py`
- Modify: `tools/inkforge-cli/README.md`
- Create: `tools/inkforge-cli/tests/test_long_lore_entity_commands.py`
- Create: `tools/inkforge-cli/tests/test_long_lore_relationship_commands.py`
- Create: `tools/inkforge-cli/tests/test_long_reference_commands.py`
- Create: `tools/inkforge-cli/tests/test_long_style_commands.py`
- Modify: `tools/inkforge-cli/tests/test_registry.py`
- Modify: `tools/inkforge-cli/tests/test_long_output_files.py`

- [ ] **Step 1: 写 27 条映射、注册集合、请求 ID 和无文件输出失败测试**

```python
def test_new_structured_mutations_have_exact_capabilities() -> None:
    registry = get_command_registry()
    names = {name for name in registry if name in EXPECTED_STRUCTURED_WRITES}
    assert names == EXPECTED_STRUCTURED_WRITES
    assert len(registry) == 77
    assert sum(name.startswith("long.") and spec.mutation for name, spec in registry.items()) == 44
    assert {
        name for name, spec in registry.items() if name in EXPECTED_STRUCTURED_WRITES and spec.requiresClientRequestId
    } == EXPECTED_CREATE_COMMANDS
```

路由测试参数化覆盖五类实体 15 条、关系/经历 6 条、参考资料 4 条和文风 2 条；创建请求 ID、更新/删除
版本、ID URL 编码和 delete JSON 影响响应逐项断言。

- [ ] **Step 2: 运行 CLI 结构写测试确认 RED**

Run:

```powershell
uv run --package inkforge-cli pytest tools/inkforge-cli/tests/test_long_lore_entity_commands.py tools/inkforge-cli/tests/test_long_lore_relationship_commands.py tools/inkforge-cli/tests/test_long_reference_commands.py tools/inkforge-cli/tests/test_long_style_commands.py tools/inkforge-cli/tests/test_registry.py -q
```

Expected: FAIL，27 条命令未实现，registry 仍为 45 条。

- [ ] **Step 3: 用静态资源描述表实现五类实体，不动态放宽字段**

```python
ENTITY_RESOURCES = {
    "character": ResourceSpec("characters", "characterId", CHARACTER_FIELDS),
    "location": ResourceSpec("locations", "locationId", LOCATION_FIELDS),
    "faction": ResourceSpec("factions", "factionId", FACTION_FIELDS),
    "item": ResourceSpec("items", "itemId", ITEM_FIELDS),
    "glossary": ResourceSpec("glossary", "glossaryId", GLOSSARY_FIELDS),
}
```

create 发送 `clientRequestId + data`，update 发送 `expectedUpdatedAt + data`，delete 发送版本并保留 Core
JSON 影响报告。每类字段集合必须显式定义，禁止原样透传任意 data。

- [ ] **Step 4: 实现关系/经历、参考资料和文风模块**

关系/经历使用各自 ID 与路径；参考资料 create/update 复用 `require_content_source()`，reindex 发送稳定请求
ID 和 `expectedContentHash`；style apply/clear 分别发送目标 ID 或 null 与 `expectedStyleId`。

- [ ] **Step 5: 注册 32 条命令并同步 README**

`registry.py` 导入五组 `*_COMMAND_SPECS`。新增命令中只有八条 create 设置
`requiresClientRequestId=true`，reindex 依赖确定性 `referenceId + expectedContentHash`。README 的命令
标记区按 registry 顺序列出 77 条命令，记录
CAS、创建重放、删除影响和 RAG pending/failed，不再笼统写“全部 Stage C 未开放”。测试仍明确禁止本
规格排除的大纲、伏笔和用户级文风资产命令。

- [ ] **Step 6: 运行 CLI 全套测试并提交**

Run:

```powershell
uv run --package inkforge-cli pytest tools/inkforge-cli/tests -q
uv run ruff check tools/inkforge-cli
uv run mypy tools/inkforge-cli/src
```

Expected: 全部 PASS，Ruff 无诊断，Mypy 输出 `Success: no issues found`。

```powershell
git add tools/inkforge-cli
git commit -m "命令行：开放长篇创作资料安全写入"
```

## Task 11：更新生产 Skill 的精确授权和恢复流程

**Files:**
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/SKILL.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/scripts/operator.ps1`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/references/cli-contract.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/references/long-serial-workflow.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/references/recovery.md`
- Create: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/references/long-creative-material-writes.md`
- Modify: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/tests/long-cli.Tests.ps1`
- Create: `C:/Users/niebo/.codex/skills/inkforge-production-short-story-operator/tests/structured-writes.Tests.ps1`

- [ ] **Step 1: 写 Skill 精确集合和安全流程失败测试**

```powershell
$expected = @(
    'long.lore.story-background.save',
    'long.lore.world-setting.save',
    'long.lore.writing-bible.save',
    'long.lore.story-progress.save',
    'long.plot-progress.save',
    'long.lore.character.create',
    'long.lore.character.update',
    'long.lore.character.delete',
    'long.lore.location.create',
    'long.lore.location.update',
    'long.lore.location.delete',
    'long.lore.faction.create',
    'long.lore.faction.update',
    'long.lore.faction.delete',
    'long.lore.item.create',
    'long.lore.item.update',
    'long.lore.item.delete',
    'long.lore.glossary.create',
    'long.lore.glossary.update',
    'long.lore.glossary.delete',
    'long.lore.relation.create',
    'long.lore.relation.update',
    'long.lore.relation.delete',
    'long.lore.experience.create',
    'long.lore.experience.update',
    'long.lore.experience.delete',
    'long.reference.create',
    'long.reference.update',
    'long.reference.delete',
    'long.reference.reindex',
    'long.style.apply',
    'long.style.clear'
)
Assert-Equal 32 $expected.Count '结构写命令数量必须精确为 32'
Assert-True (-not ($operatorSource -match "long\.\*|long\.lore\.\*")) '生产授权不得使用通配'
```

测试还要逐项检查文档出现 `expectedUpdatedAt`、`clientRequestId`、完整 Diff、删除影响、写后 GET、
`ragStatus` pending/failed 和网络不确定恢复语义。

- [ ] **Step 2: 运行 Skill 测试确认 RED**

Run:

```powershell
& 'C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\tests\long-cli.Tests.ps1'
& 'C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\tests\structured-writes.Tests.ps1'
```

Expected: 第一条因命令集合仍为旧值或第二个脚本不存在而 FAIL。

- [ ] **Step 3: 精确加入 32 条命令并写入操作矩阵**

`operator.ps1` 逐条加入命令，总 allowlist 77 条，无通配。新 reference 按资源列出：写前 GET、完整
旧值/新值/Diff、一次确认、带版本单次写、写后对应 GET；删除先展示 Core 影响；网络不确定先回拉，
create/reindex 只复用原请求。

- [ ] **Step 4: 更新 Skill 主入口和恢复文档**

删除“Stage C 全部未开放”的旧表述；保留固定 `https://inkforge.cn`、production、逐命令 whoami、禁止
SSH/数据库/内部接口/自制 HTTP。`recovery.md` 为八类版本/资源冲突码、创建重放、删除引用、索引 pending/failed
给出确定恢复步骤。

- [ ] **Step 5: 运行 Skill 全套离线验证**

Run:

```powershell
& 'C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\tests\long-cli.Tests.ps1'
& 'C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\tests\structured-writes.Tests.ps1'
& 'C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\tests\https-migration.Tests.ps1'
& 'C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\tests\unicode-runtime.Tests.ps1'
uv run python -X utf8 'C:\Users\niebo\.codex\skills\.system\skill-creator\scripts\quick_validate.py' 'C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator'
```

Expected: 所有 PowerShell 脚本退出 0，quick_validate 输出 `Skill is valid!`。

## Task 12：同步规格状态并执行完整验收

**Files:**
- Modify: `docs/specs/2026-08-05-long-serial-cli-control-plane.md`
- Modify: `docs/specs/2026-08-06-long-serial-creative-material-cli-writes.md`
- Verify: `apps/core-api/src/inkforge_core/db/schema-contract.json`

- [ ] **Step 1: 更新文档状态和仍未开放边界**

把本规格状态改为“实现完成，待部署”；控制面规格的 Stage C 段落改为：本规格 32 条命令已经实现，
大纲、节点、伏笔和用户级文风库仍未开放。不得把本地实现表述为生产部署完成。

- [ ] **Step 2: 运行 Core、CLI 和 schema 指纹验证**

Run:

```powershell
uv run pytest apps/core-api/tests/lore apps/core-api/tests/outlines apps/core-api/tests/references apps/core-api/tests/styles apps/core-api/tests/test_openapi_long_serial.py apps/core-api/tests/db/test_schema_guard.py -q
uv run --package inkforge-cli pytest tools/inkforge-cli/tests -q
uv run ruff check apps/core-api/src apps/core-api/tests tools/inkforge-cli
uv run mypy apps/core-api/src tools/inkforge-cli/src
```

Expected: pytest 全部 PASS，schema guard 证明指纹未变，Ruff 无诊断，Mypy 成功。

- [ ] **Step 3: 运行生成客户端和 Web 全量验证**

Run:

```powershell
npm run api:generate
npm run api:check
npm run test:web
npm run typecheck
npm run lint
```

Expected: 全部退出 0；api:check 无漂移，Web 测试、类型检查和 lint 无失败。

- [ ] **Step 4: 运行生产 Skill 离线回归**

Run Task 11 Step 5 的完整命令集，Expected: 全部退出 0。

- [ ] **Step 5: 执行生产只读冒烟，不执行线上写入**

```powershell
'{}' | & 'C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\scripts\operator.ps1' auth.whoami
'{}' | & 'C:\Users\niebo\.codex\skills\inkforge-production-short-story-operator\scripts\operator.ps1' long.novel.list
```

Expected: `auth.whoami` 返回配置的生产用户；列表正常返回长篇。未部署新 Core 前，不调用新增 32 条写
命令，不把本地 CLI 注册成功表述为线上可用。

- [ ] **Step 6: 提交规格状态和最终验证记录**

```powershell
git add docs/specs/2026-08-05-long-serial-cli-control-plane.md docs/specs/2026-08-06-long-serial-creative-material-cli-writes.md
git commit -m "文档：记录长篇创作资料写入实现状态"
```

## 完成定义

- 仓库分支包含 Core、Web、生成客户端、CLI、测试和文档的全部实现提交。
- 个人生产 Skill 已通过离线测试，但它不属于仓库提交。
- 32 条命令在 registry、README、OpenAPI 和生产 allowlist 中集合一致。
- Core 过期写入返回 409，不改变权威数据；相同创建请求不重复生成资源。
- PostgreSQL schema 指纹未变化。
- 本轮不自动 push、部署或写入《遗产猎人（迁移）》；这些是实现验收后的独立授权动作。
