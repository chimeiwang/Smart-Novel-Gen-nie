# 中短篇正文来源大纲显式重绑定实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不修改历史版本和正文内容的前提下，让作者通过现有人工版本预览/提交接口显式把正文新版本绑定到当前已应用大纲，并用确认哈希保护该元数据变化。

**Architecture:** 复用现有作品级文档事务、版本号分配和公开版本接口，不新增路由、仓储查询或数据库结构。人工请求显式携带可选 `sourceOutlineVersionId`；Core 在预览和提交事务中解析同一个目标大纲，以人工版本专用确认哈希绑定文本 Diff 与目标来源，并在仅溯源变化时创建内容相同的新版本。默认人工提交、候选采用和历史恢复语义保持不变。

**Tech Stack:** Python 3.12、FastAPI、Pydantic v2、SQLAlchemy、pytest、Ruff、Mypy、PowerShell、OpenAPI TypeScript 生成客户端、InkForge CLI。

---

## 文件结构

- `apps/core-api/src/inkforge_core/short_medium/schemas.py`：人工版本请求/响应 DTO 与人工确认哈希。
- `apps/core-api/src/inkforge_core/short_medium/service.py`：目标来源大纲解析、预览与人工提交。
- `apps/core-api/tests/short_medium/test_version_payload.py`：请求契约校验。
- `apps/core-api/tests/short_medium/test_version_diff.py`：人工确认哈希稳定性与目标大纲绑定。
- `apps/core-api/tests/short_medium/test_version_service.py`：仅溯源、默认继承、合并变化、幂等和冲突行为。
- `apps/core-api/tests/short_medium/test_version_api.py`：HTTP 422、响应模型和 OpenAPI 契约。
- `tools/inkforge-cli/tests/test_cli.py`：CLI 已有字段透传和预览元数据保留的特征测试。
- `tools/inkforge-cli/README.md`：操作员显式重绑定说明。
- `packages/api-client/src/generated/schema.d.ts`：只由 `npm run api:generate` 更新。
- `docs/requirements/04-review-quality-and-workflow.md`：当前不可变版本与显式重绑定规则。
- `docs/specs/2026-07-30-short-medium-writing-workflow.md`：原工作流中“相同内容”和“继承来源”的显式例外。

明确不修改：

- `apps/core-api/src/inkforge_core/short_medium/repository.py`：现有 `current_outline_version()` 已满足需求，且文档事务先锁 Novel，可串行化同一作品的大纲/正文提交。
- `apps/core-api/src/inkforge_core/short_medium/router.py`：现有端点直接绑定 Pydantic 模型。
- `apps/agent-service/**`、`packages/service-contracts/**`、`apps/web/**`、PostgreSQL schema 和迁移。

### Task 1: 扩展人工版本请求与专用确认哈希

**Files:**

- Modify: `apps/core-api/src/inkforge_core/short_medium/schemas.py`
- Test: `apps/core-api/tests/short_medium/test_version_payload.py`
- Test: `apps/core-api/tests/short_medium/test_version_diff.py`

- [ ] **Step 1: 先写人工请求绑定的失败测试**

在 `test_version_payload.py` 增加导入和测试：

```python
from datetime import UTC, datetime

from inkforge_core.short_medium.schemas import (
    ManualVersionRequest,
    VersionPreviewRequest,
)


def test_manual_version_requests_only_allow_source_outline_for_manuscript() -> None:
    manuscript_preview = VersionPreviewRequest(
        documentType="manuscript",
        chapterId="chapter-1",
        baseVersionId="manuscript-v1",
        sourceOutlineVersionId="outline-v2",
    )
    assert manuscript_preview.sourceOutlineVersionId == "outline-v2"

    with pytest.raises(ValidationError, match="来源大纲"):
        VersionPreviewRequest(
            documentType="outline",
            baseVersionId="outline-v1",
            sourceOutlineVersionId="outline-v2",
        )

    with pytest.raises(ValidationError, match="来源大纲"):
        ManualVersionRequest(
            clientRequestId="request-outline-123",
            documentType="outline",
            baseVersionId="outline-v1",
            sourceOutlineVersionId="outline-v2",
            expectedUpdatedAt=datetime(2026, 8, 4, tzinfo=UTC),
            contentHash="a" * 64,
            confirmationHash="b" * 64,
        )
```

- [ ] **Step 2: 运行请求测试并确认失败原因正确**

Run:

```powershell
uv run pytest apps/core-api/tests/short_medium/test_version_payload.py::test_manual_version_requests_only_allow_source_outline_for_manuscript -q
```

Expected: FAIL，正文请求因 `sourceOutlineVersionId` 是额外字段而失败，证明新契约尚未实现。

- [ ] **Step 3: 实现人工请求专用绑定模型**

在 `DocumentBinding` 后增加专用模型，并让两个人工请求继承它；不要扩展 `DocumentBinding`，以免候选采用和历史恢复获得覆盖溯源的能力：

```python
class ManualVersionBinding(DocumentBinding):
    sourceOutlineVersionId: str | None = None

    @model_validator(mode="after")
    def validate_source_outline_binding(self) -> Self:
        if self.documentType == "outline" and self.sourceOutlineVersionId is not None:
            raise ValueError("大纲版本请求不能指定来源大纲")
        return self


class VersionPreviewRequest(ManualVersionBinding):
    baseVersionId: str | None = None


class ManualVersionRequest(ManualVersionBinding):
    clientRequestId: str = Field(min_length=16, max_length=128)
    baseVersionId: str | None = None
    expectedUpdatedAt: JsonDatetime
    contentHash: str = Field(pattern=SHA256_PATTERN)
    confirmationHash: str = Field(pattern=SHA256_PATTERN)
    summary: str | None = None
```

- [ ] **Step 4: 运行请求测试并确认转绿**

Run:

```powershell
uv run pytest apps/core-api/tests/short_medium/test_version_payload.py -q
```

Expected: PASS。

- [ ] **Step 5: 写人工确认哈希的失败测试**

在 `test_version_diff.py` 中导入 `bind_manual_confirmation_hash`，并增加：

```python
from inkforge_core.short_medium.schemas import (
    bind_manual_confirmation_hash,
    build_document_diff,
    content_sha256,
)


def test_manual_confirmation_hash_binds_target_source_outline_version_id() -> None:
    diff = build_document_diff(
        "正文",
        "正文",
        from_version_id="manuscript-v1",
        to_version_id=None,
    )
    common = {
        "document_type": "manuscript",
        "chapter_id": "chapter-1",
        "base_version_id": "manuscript-v1",
        "current_draft_hash": content_sha256("正文"),
        "target_version_id": None,
    }

    first = bind_manual_confirmation_hash(
        diff,
        **common,
        target_source_outline_version_id="outline-v1",
    )
    repeated = bind_manual_confirmation_hash(
        diff,
        **common,
        target_source_outline_version_id="outline-v1",
    )
    second = bind_manual_confirmation_hash(
        diff,
        **common,
        target_source_outline_version_id="outline-v2",
    )

    assert first.confirmationHash == repeated.confirmationHash
    assert first.confirmationHash != second.confirmationHash
```

- [ ] **Step 6: 运行哈希测试并确认失败原因正确**

Run:

```powershell
uv run pytest apps/core-api/tests/short_medium/test_version_diff.py::test_manual_confirmation_hash_binds_target_source_outline_version_id -q
```

Expected: ERROR/FAIL，`bind_manual_confirmation_hash` 尚不存在。

- [ ] **Step 7: 实现人工版本专用确认哈希**

在 `schemas.py` 中抽出规范化 SHA-256 辅助函数，保持现有 `bind_confirmation_hash()` 的规范内容不变，并新增：

```python
def _bind_canonical_hash(
    diff: VersionDiffResponse,
    canonical: dict[str, object],
) -> VersionDiffResponse:
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return diff.model_copy(
        update={"confirmationHash": hashlib.sha256(encoded).hexdigest()}
    )


def bind_manual_confirmation_hash(
    diff: VersionDiffResponse,
    *,
    document_type: DocumentType,
    chapter_id: str | None,
    base_version_id: str | None,
    current_draft_hash: str,
    target_version_id: str | None,
    target_source_outline_version_id: str | None,
) -> VersionDiffResponse:
    return _bind_canonical_hash(
        diff,
        {
            "documentType": document_type,
            "chapterId": chapter_id,
            "baseVersionId": base_version_id,
            "currentDraftHash": current_draft_hash,
            "targetVersionId": target_version_id,
            "targetSourceOutlineVersionId": target_source_outline_version_id,
            "diff": diff.model_dump(exclude={"confirmationHash"}, mode="json"),
        },
    )
```

把现有 `bind_confirmation_hash()` 的 JSON 编码部分改为调用 `_bind_canonical_hash()`，其 canonical 字段集合保持原样，避免改变候选采用和历史恢复哈希。

- [ ] **Step 8: 运行 Task 1 全部测试**

Run:

```powershell
uv run pytest apps/core-api/tests/short_medium/test_version_payload.py apps/core-api/tests/short_medium/test_version_diff.py -q
uv run ruff check apps/core-api/src/inkforge_core/short_medium/schemas.py apps/core-api/tests/short_medium/test_version_payload.py apps/core-api/tests/short_medium/test_version_diff.py
```

Expected: 全部 PASS，Ruff 无错误。

- [ ] **Step 9: 提交请求与哈希契约**

```powershell
git add -- apps/core-api/src/inkforge_core/short_medium/schemas.py apps/core-api/tests/short_medium/test_version_payload.py apps/core-api/tests/short_medium/test_version_diff.py
git commit -m "开发：扩展人工版本来源大纲确认契约"
```

### Task 2: 实现预览与人工提交的显式重绑定

**Files:**

- Modify: `apps/core-api/src/inkforge_core/short_medium/schemas.py`
- Modify: `apps/core-api/src/inkforge_core/short_medium/service.py`
- Test: `apps/core-api/tests/short_medium/test_version_service.py`

- [ ] **Step 1: 扩充内存事务测试夹具**

在 `test_version_service.py` 中导入 `DocumentVersionPayload`，给 `MemoryTransaction` 增加当前大纲，并实现已有协议方法：

```python
@dataclass
class MemoryTransaction:
    document: WorkDocument
    versions: list[VersionRecord] = field(default_factory=list)
    outline_version: VersionRecord | None = None
    adoption_replays: dict[str, str] = field(default_factory=dict)
    replace_call_count: int = 0
    adoption_replay_save_count: int = 0

    async def current_outline_version(self) -> VersionRecord | None:
        return self.outline_version
```

增加不可变测试版本辅助函数：

```python
def applied_version(
    *,
    version_id: str,
    document_type: str,
    version_number: int,
    content: str,
    source_outline_version_id: str | None = None,
) -> VersionRecord:
    is_outline = document_type == "outline"
    chapter_id = None if is_outline else "chapter-1"
    artifact_key = (
        "short-medium:outline:novel-1"
        if is_outline
        else "short-medium:manuscript:chapter-1"
    )
    payload = DocumentVersionPayload(
        kind="outline_draft" if is_outline else "chapter_draft",
        documentType="outline" if is_outline else "manuscript",
        versionNumber=version_number,
        baseVersionId=None,
        clientRequestId=f"request-{version_id}-manual",
        source="manual",
        content=content,
        contentHash=sha256(content),
        sourceOutlineVersionId=source_outline_version_id,
    )
    return VersionRecord(
        id=version_id,
        novel_id="novel-1",
        chapter_id=chapter_id,
        artifact_key=artifact_key,
        status="applied",
        summary=None,
        payload=payload,
        diff=None,
        created_by_agent=None,
        task_id=None,
        created_at=NOW,
        updated_at=NOW,
        applied_at=NOW,
    )


def manuscript_service() -> tuple[
    ShortMediumVersionService,
    MemoryTransaction,
    VersionRecord,
]:
    base = applied_version(
        version_id="manuscript-v1",
        document_type="manuscript",
        version_number=1,
        content="第一稿",
        source_outline_version_id="outline-v1",
    )
    current_outline = applied_version(
        version_id="outline-v2",
        document_type="outline",
        version_number=2,
        content="第二版大纲",
    )
    tx = MemoryTransaction(
        document=WorkDocument(
            novel_id="novel-1",
            chapter_id="chapter-1",
            document_type="manuscript",
            artifact_key="short-medium:manuscript:chapter-1",
            content="第一稿",
            updated_at=NOW,
        ),
        versions=[base],
        outline_version=current_outline,
    )
    return ShortMediumVersionService(MemoryRepository(tx)), tx, base
```

- [ ] **Step 2: 写仅溯源变化、默认继承和冲突的失败测试**

增加以下测试；每个测试只验证一种行为：

```python
@pytest.mark.asyncio
async def test_preview_only_outline_rebinding_is_dirty_with_empty_text_diff() -> None:
    service, _, base = manuscript_service()

    preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=base.id,
            sourceOutlineVersionId="outline-v2",
        ),
    )

    assert preview.dirty is True
    assert preview.contentChanged is False
    assert preview.sourceOutlineChanged is True
    assert preview.currentSourceOutlineVersionId == "outline-v1"
    assert preview.targetSourceOutlineVersionId == "outline-v2"
    assert preview.diff.blocks == []
    assert preview.diff.wordCountDelta == 0
    assert "outline-v1" in preview.confirmationSummary
    assert "outline-v2" in preview.confirmationSummary


@pytest.mark.asyncio
async def test_manual_submit_creates_content_identical_outline_rebinding_and_replays() -> None:
    service, tx, base = manuscript_service()
    preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=base.id,
            sourceOutlineVersionId="outline-v2",
        ),
    )
    request = ManualVersionRequest(
        clientRequestId="request-rebind-123",
        documentType="manuscript",
        chapterId="chapter-1",
        baseVersionId=base.id,
        sourceOutlineVersionId="outline-v2",
        expectedUpdatedAt=tx.document.updated_at,
        contentHash=sha256("第一稿"),
        confirmationHash=preview.confirmationHash,
        summary="修正正文来源大纲，不改正文内容",
    )

    created = await service.submit_manual("user-1", "novel-1", request)
    replay = await service.submit_manual("user-1", "novel-1", request)

    assert created.id == replay.id
    assert created.versionNumber == 2
    assert created.baseVersionId == base.id
    assert created.content == base.content
    assert created.contentHash == base.contentHash
    assert created.sourceOutlineVersionId == "outline-v2"
    assert base.sourceOutlineVersionId == "outline-v1"
    assert created.diff is not None
    assert created.diff.blocks == []
    assert len(tx.versions) == 2


@pytest.mark.asyncio
async def test_manual_content_change_without_target_inherits_base_outline() -> None:
    service, tx, base = manuscript_service()
    tx.document.content = "第二稿"
    tx.document.updated_at += timedelta(milliseconds=1)
    preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=base.id,
        ),
    )

    created = await service.submit_manual(
        "user-1",
        "novel-1",
        ManualVersionRequest(
            clientRequestId="request-inherit-123",
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=base.id,
            expectedUpdatedAt=tx.document.updated_at,
            contentHash=sha256("第二稿"),
            confirmationHash=preview.confirmationHash,
        ),
    )

    assert preview.contentChanged is True
    assert preview.sourceOutlineChanged is False
    assert created.sourceOutlineVersionId == "outline-v1"


@pytest.mark.asyncio
async def test_manual_submit_combines_content_change_and_outline_rebinding() -> None:
    service, tx, base = manuscript_service()
    tx.document.content = "按第二版大纲校订后的正文"
    tx.document.updated_at += timedelta(milliseconds=1)
    preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=base.id,
            sourceOutlineVersionId="outline-v2",
        ),
    )
    created = await service.submit_manual(
        "user-1",
        "novel-1",
        ManualVersionRequest(
            clientRequestId="request-combined-123",
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=base.id,
            sourceOutlineVersionId="outline-v2",
            expectedUpdatedAt=tx.document.updated_at,
            contentHash=sha256(tx.document.content),
            confirmationHash=preview.confirmationHash,
        ),
    )

    assert preview.contentChanged is True
    assert preview.sourceOutlineChanged is True
    assert created.content == "按第二版大纲校订后的正文"
    assert created.sourceOutlineVersionId == "outline-v2"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_id",
    ["outline-v1", "outline-awaiting", "outline-foreign", "outline-missing"],
)
async def test_invalid_explicit_outline_target_is_rejected(
    target_id: str,
) -> None:
    service, _, base = manuscript_service()

    with pytest.raises(ApiError) as error:
        await service.preview(
            "user-1",
            "novel-1",
            VersionPreviewRequest(
                documentType="manuscript",
                chapterId="chapter-1",
                baseVersionId=base.id,
                sourceOutlineVersionId=target_id,
            ),
        )

    assert error.value.code == "SHORT_MEDIUM_SOURCE_OUTLINE_CONFLICT"


@pytest.mark.asyncio
async def test_submit_rejects_outline_target_that_changed_after_preview() -> None:
    service, tx, base = manuscript_service()
    preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=base.id,
            sourceOutlineVersionId="outline-v2",
        ),
    )
    tx.outline_version = applied_version(
        version_id="outline-v3",
        document_type="outline",
        version_number=3,
        content="第三版大纲",
    )

    with pytest.raises(ApiError) as error:
        await service.submit_manual(
            "user-1",
            "novel-1",
            ManualVersionRequest(
                clientRequestId="request-stale-outline-123",
                documentType="manuscript",
                chapterId="chapter-1",
                baseVersionId=base.id,
                sourceOutlineVersionId="outline-v2",
                expectedUpdatedAt=tx.document.updated_at,
                contentHash=sha256(tx.document.content),
                confirmationHash=preview.confirmationHash,
            ),
        )

    assert error.value.code == "SHORT_MEDIUM_SOURCE_OUTLINE_CONFLICT"


@pytest.mark.asyncio
async def test_explicit_same_outline_and_unchanged_content_returns_current() -> None:
    service, tx, base = manuscript_service()
    tx.outline_version = applied_version(
        version_id="outline-v1",
        document_type="outline",
        version_number=1,
        content="第一版大纲",
    )
    preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=base.id,
            sourceOutlineVersionId="outline-v1",
        ),
    )
    returned = await service.submit_manual(
        "user-1",
        "novel-1",
        ManualVersionRequest(
            clientRequestId="request-same-outline-123",
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=base.id,
            sourceOutlineVersionId="outline-v1",
            expectedUpdatedAt=tx.document.updated_at,
            contentHash=sha256(tx.document.content),
            confirmationHash=preview.confirmationHash,
        ),
    )

    assert preview.dirty is False
    assert returned.id == base.id
    assert len(tx.versions) == 1


@pytest.mark.asyncio
async def test_first_manual_manuscript_binds_current_outline() -> None:
    outline = applied_version(
        version_id="outline-v1",
        document_type="outline",
        version_number=1,
        content="第一版大纲",
    )
    tx = MemoryTransaction(
        document=WorkDocument(
            novel_id="novel-1",
            chapter_id="chapter-1",
            document_type="manuscript",
            artifact_key="short-medium:manuscript:chapter-1",
            content="首版正文",
            updated_at=NOW,
        ),
        outline_version=outline,
    )
    service = ShortMediumVersionService(MemoryRepository(tx))
    preview = await service.preview(
        "user-1",
        "novel-1",
        VersionPreviewRequest(
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=None,
        ),
    )
    created = await service.submit_manual(
        "user-1",
        "novel-1",
        ManualVersionRequest(
            clientRequestId="request-first-manuscript-123",
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=None,
            expectedUpdatedAt=tx.document.updated_at,
            contentHash=sha256(tx.document.content),
            confirmationHash=preview.confirmationHash,
        ),
    )

    assert preview.targetSourceOutlineVersionId == "outline-v1"
    assert created.sourceOutlineVersionId == "outline-v1"
```

保留现有 `test_manuscript_manual_version_inherits_outline_binding`；新增的默认继承测试已经覆盖当前大纲为 v2、基础正文仍绑定 v1 的场景。

- [ ] **Step 3: 运行新增 service 测试并确认失败**

Run:

```powershell
uv run pytest apps/core-api/tests/short_medium/test_version_service.py -q
```

Expected: 新测试因预览字段不存在、目标大纲未解析或相同内容仍直接返回基础版本而 FAIL。

- [ ] **Step 4: 扩展预览响应模型**

在 `VersionPreviewResponse` 中加入四个必返字段：

```python
class VersionPreviewResponse(StrictModel):
    documentType: DocumentType
    chapterId: str | None
    baseVersionId: str | None
    expectedUpdatedAt: datetime
    contentHash: str = Field(pattern=SHA256_PATTERN)
    dirty: bool
    currentSourceOutlineVersionId: str | None
    targetSourceOutlineVersionId: str | None
    sourceOutlineChanged: bool
    contentChanged: bool
    confirmationSummary: str
    confirmationHash: str = Field(pattern=SHA256_PATTERN)
    diff: VersionDiffResponse
```

- [ ] **Step 5: 在 service 中集中解析目标来源大纲**

导入 `bind_manual_confirmation_hash`，并增加：

```python
async def _resolve_source_outline_binding(
    transaction: DocumentTransaction,
    *,
    document_type: DocumentType,
    current: VersionRecord | None,
    requested_source_outline_version_id: str | None,
) -> tuple[str | None, str | None]:
    if document_type == "outline":
        return None, None

    current_source_id = (
        current.payload.sourceOutlineVersionId if current is not None else None
    )
    if requested_source_outline_version_id is not None:
        current_outline = await transaction.current_outline_version()
        if (
            current_outline is None
            or current_outline.id != requested_source_outline_version_id
        ):
            raise ApiError(
                status_code=409,
                code="SHORT_MEDIUM_SOURCE_OUTLINE_CONFLICT",
                message="目标来源大纲不是当前已应用大纲，请重新拉取并预览",
                details={
                    "requestedSourceOutlineVersionId": (
                        requested_source_outline_version_id
                    ),
                    "currentOutlineVersionId": (
                        current_outline.id if current_outline is not None else None
                    ),
                },
            )
        return current_source_id, current_outline.id

    if current is not None:
        return current_source_id, current_source_id

    current_outline = await transaction.current_outline_version()
    if current_outline is None:
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_OUTLINE_VERSION_REQUIRED",
            message="提交首个正文版本前必须先确认一份大纲版本",
        )
    return None, current_outline.id


def _manual_confirmation_summary(
    diff: VersionDiffResponse,
    *,
    content_changed: bool,
    source_outline_changed: bool,
    current_source_outline_version_id: str | None,
    target_source_outline_version_id: str | None,
) -> str:
    parts: list[str] = []
    if content_changed:
        parts.append(f"将提交{diff.toWordCount}字，字数变化{diff.wordCountDelta:+d}")
    if source_outline_changed:
        parts.append(
            "正文来源大纲将从"
            f" {current_source_outline_version_id or '未绑定'}"
            f" 调整为 {target_source_outline_version_id or '未绑定'}"
        )
    return "；".join(parts) if parts else "工作稿与当前版本一致，没有可提交的变化"
```

- [ ] **Step 6: 完整替换 `preview()` 的变化判断与确认绑定**

在文档事务内、`_require_current_base()` 之后按以下顺序实现：

```python
base_content = current.content if current is not None else ""
work_content = transaction.document.content
current_source_id, target_source_id = await _resolve_source_outline_binding(
    transaction,
    document_type=request.documentType,
    current=current,
    requested_source_outline_version_id=request.sourceOutlineVersionId,
)
diff = build_document_diff(
    base_content,
    work_content,
    from_version_id=current.id if current is not None else None,
    to_version_id=None,
)
content_changed = content_sha256(work_content) != content_sha256(base_content)
source_outline_changed = current_source_id != target_source_id
diff = bind_manual_confirmation_hash(
    diff,
    document_type=request.documentType,
    chapter_id=request.chapterId,
    base_version_id=current.id if current is not None else None,
    current_draft_hash=content_sha256(work_content),
    target_version_id=None,
    target_source_outline_version_id=target_source_id,
)
return VersionPreviewResponse(
    documentType=cast(DocumentType, transaction.document.document_type),
    chapterId=transaction.document.chapter_id,
    baseVersionId=current.id if current is not None else None,
    expectedUpdatedAt=transaction.document.updated_at,
    contentHash=content_sha256(work_content),
    dirty=content_changed or source_outline_changed,
    currentSourceOutlineVersionId=current_source_id,
    targetSourceOutlineVersionId=target_source_id,
    sourceOutlineChanged=source_outline_changed,
    contentChanged=content_changed,
    confirmationSummary=_manual_confirmation_summary(
        diff,
        content_changed=content_changed,
        source_outline_changed=source_outline_changed,
        current_source_outline_version_id=current_source_id,
        target_source_outline_version_id=target_source_id,
    ),
    confirmationHash=diff.confirmationHash,
    diff=diff,
)
```

- [ ] **Step 7: 修改 `submit_manual()`，把溯源变化纳入创建门槛**

保留 `clientRequestId` 重放、基础版本、更新时间和工作稿 hash 校验的现有顺序。工作稿 hash 校验后使用：

```python
current_source_id, target_source_id = await _resolve_source_outline_binding(
    transaction,
    document_type=request.documentType,
    current=current,
    requested_source_outline_version_id=request.sourceOutlineVersionId,
)
content_changed = (
    current is None or current.payload.contentHash != work_hash
)
source_outline_changed = current_source_id != target_source_id
confirmation_diff = bind_manual_confirmation_hash(
    build_document_diff(
        current.content if current is not None else "",
        work_content,
        from_version_id=current.id if current is not None else None,
        to_version_id=None,
    ),
    document_type=request.documentType,
    chapter_id=request.chapterId,
    base_version_id=current.id if current is not None else None,
    current_draft_hash=work_hash,
    target_version_id=None,
    target_source_outline_version_id=target_source_id,
)
_require_confirmation(request.confirmationHash, confirmation_diff.confirmationHash)
if (
    current is not None
    and not content_changed
    and not source_outline_changed
):
    return _detail(current)
```

随后删除现有“从基础正文继承或首版查询大纲”的分支，创建 payload 时统一使用：

```python
payload = DocumentVersionPayload(
    kind=(
        "outline_draft"
        if request.documentType == "outline"
        else "chapter_draft"
    ),
    documentType=request.documentType,
    versionNumber=_next_version_number(transaction.versions),
    baseVersionId=current.id if current is not None else None,
    clientRequestId=request.clientRequestId,
    source="manual",
    content=work_content,
    contentHash=work_hash,
    sourceOutlineVersionId=target_source_id,
)
```

版本 Diff 仍使用 `_serialized_diff()` 保存纯文本变化；仅溯源版本的 `blocks=[]`。不要调用 `replace_work_content()`，因为工作稿内容没有被改变。

- [ ] **Step 8: 运行 service 测试并确认转绿**

Run:

```powershell
uv run pytest apps/core-api/tests/short_medium/test_version_service.py -q
uv run ruff check apps/core-api/src/inkforge_core/short_medium apps/core-api/tests/short_medium/test_version_service.py
```

Expected: 全部 PASS，Ruff 无错误。

- [ ] **Step 9: 提交 Core 行为实现**

```powershell
git add -- apps/core-api/src/inkforge_core/short_medium/schemas.py apps/core-api/src/inkforge_core/short_medium/service.py apps/core-api/tests/short_medium/test_version_service.py
git commit -m "修复：支持正文来源大纲显式重绑定"
```

### Task 3: 锁定公共 API、CLI 透传与生成客户端

**Files:**

- Modify: `apps/core-api/tests/short_medium/test_version_api.py`
- Modify: `tools/inkforge-cli/tests/test_cli.py`
- Modify: `tools/inkforge-cli/README.md`
- Generate: `packages/api-client/src/generated/schema.d.ts`

- [ ] **Step 1: 更新 API 假服务响应并增加契约测试**

给 `FakeVersionService.preview()` 返回值补齐：

```python
"currentSourceOutlineVersionId": None,
"targetSourceOutlineVersionId": None,
"sourceOutlineChanged": False,
"contentChanged": True,
```

扩展预览请求测试，使正文目标能传到服务：

```python
@pytest.mark.asyncio
async def test_preview_contract_accepts_manuscript_source_outline_target() -> None:
    service = FakeVersionService()
    async with version_client(service) as client:
        response = await client.post(
            "/api/v1/novels/novel-1/versions/preview",
            json={
                "documentType": "manuscript",
                "chapterId": "chapter-1",
                "baseVersionId": "manuscript-v1",
                "sourceOutlineVersionId": "outline-v2",
            },
        )

    assert response.status_code == 200
    body = service.calls[0][-1]
    assert body.sourceOutlineVersionId == "outline-v2"
    assert not hasattr(body, "content")


@pytest.mark.asyncio
async def test_outline_preview_rejects_source_outline_target() -> None:
    service = FakeVersionService()
    async with version_client(service) as client:
        response = await client.post(
            "/api/v1/novels/novel-1/versions/preview",
            json={
                "documentType": "outline",
                "baseVersionId": "outline-v1",
                "sourceOutlineVersionId": "outline-v2",
            },
        )

    assert response.status_code == 422
    assert service.calls == []
```

扩展 OpenAPI 测试：

```python
def test_openapi_exposes_source_outline_rebinding_contract() -> None:
    schemas = create_app(testing=True).openapi()["components"]["schemas"]

    assert "sourceOutlineVersionId" in schemas["VersionPreviewRequest"]["properties"]
    assert "sourceOutlineVersionId" in schemas["ManualVersionRequest"]["properties"]
    assert "sourceOutlineVersionId" not in schemas["VersionActionRequest"]["properties"]
    required = set(schemas["VersionPreviewResponse"]["required"])
    assert {
        "currentSourceOutlineVersionId",
        "targetSourceOutlineVersionId",
        "sourceOutlineChanged",
        "contentChanged",
    } <= required
```

- [ ] **Step 2: 运行 API 测试**

Run:

```powershell
uv run pytest apps/core-api/tests/short_medium/test_version_api.py -q
```

Expected: PASS。

- [ ] **Step 3: 为 CLI 已有透传行为增加特征测试**

在 `test_cli.py` 中增加预览和提交测试。它们可能在 Core 实现前就通过，因为 CLI 已通用透传 JSON；这用于锁定“CLI 不重复实现业务规则”的既有能力：

```python
def test_version_preview_forwards_source_outline_and_preserves_metadata(
    tmp_path: Path,
) -> None:
    diff_file = tmp_path / "rebind-diff.json"
    response = {
        "documentType": "manuscript",
        "chapterId": "chapter-1",
        "baseVersionId": "manuscript-v1",
        "expectedUpdatedAt": "2026-08-04T00:00:00Z",
        "contentHash": "c" * 64,
        "dirty": True,
        "currentSourceOutlineVersionId": "outline-v1",
        "targetSourceOutlineVersionId": "outline-v2",
        "sourceOutlineChanged": True,
        "contentChanged": False,
        "confirmationSummary": "正文来源大纲将从 outline-v1 调整为 outline-v2",
        "confirmationHash": "d" * 64,
        "diff": {
            "fromVersionId": "manuscript-v1",
            "toVersionId": None,
            "fromWordCount": 4,
            "toWordCount": 4,
            "wordCountDelta": 0,
            "blocks": [],
            "confirmationHash": "d" * 64,
        },
    }
    api = RecordingApi(responses=[response])
    code, result, _ = invoke(
        "short.version.preview",
        {
            "novelId": "novel-1",
            "documentType": "manuscript",
            "chapterId": "chapter-1",
            "baseVersionId": "manuscript-v1",
            "sourceOutlineVersionId": "outline-v2",
            "outputFile": str(diff_file),
        },
        api,
    )

    assert code == 0
    assert api.calls[0][2]["json"]["sourceOutlineVersionId"] == "outline-v2"
    assert "outputFile" not in api.calls[0][2]["json"]
    assert result["data"]["sourceOutlineChanged"] is True
    assert result["data"]["contentChanged"] is False
    assert json.loads(diff_file.read_text(encoding="utf-8"))["blocks"] == []


def test_version_submit_forwards_confirmed_source_outline(
    tmp_path: Path,
) -> None:
    manifest_path = create_clean_snapshot(tmp_path)
    api = RecordingApi()
    code, _, _ = invoke(
        "short.version.submit",
        {
            "novelId": "novel-1",
            "documentType": "manuscript",
            "chapterId": "chapter-1",
            "baseVersionId": "manuscript-v1",
            "sourceOutlineVersionId": "outline-v2",
            "expectedUpdatedAt": "2026-08-04T00:00:00Z",
            "contentHash": "c" * 64,
            "confirmationHash": "d" * 64,
            "clientRequestId": "request-rebind-123",
            "manifestPath": manifest_path,
        },
        api,
    )

    assert code == 0
    body = api.calls[0][2]["json"]
    assert body["sourceOutlineVersionId"] == "outline-v2"
    assert body["confirmationHash"] == "d" * 64
    assert "manifestPath" not in body
```

- [ ] **Step 4: 运行 CLI 特征测试**

Run:

```powershell
uv run pytest tools/inkforge-cli/tests/test_cli.py -q
```

Expected: PASS；不修改 `tools/inkforge-cli/src/**`。

- [ ] **Step 5: 更新 CLI README**

在版本命令说明后增加以下规则：

```markdown
正文来源大纲显式重绑定继续复用 `short.version.preview` 与
`short.version.submit`。两次请求必须携带同一个非空
`sourceOutlineVersionId`；操作员必须展示预览响应中的当前/目标来源、
来源变化和 `confirmationHash`。文本 Diff 为空不代表没有可提交变化。
```

- [ ] **Step 6: 生成并检查 TypeScript 公共客户端**

Run:

```powershell
npm run api:generate
npm run api:check
npm run typecheck
```

Expected: `schema.d.ts` 中两个人工请求出现可选可空 `sourceOutlineVersionId`，预览响应出现四个必填字段，`VersionActionRequest` 不出现该字段；命令全部退出 0。

- [ ] **Step 7: 提交 API/CLI 契约**

```powershell
git add -- apps/core-api/tests/short_medium/test_version_api.py tools/inkforge-cli/tests/test_cli.py tools/inkforge-cli/README.md packages/api-client/src/generated/schema.d.ts
git commit -m "测试：锁定正文来源大纲重绑定公共契约"
```

### Task 4: 同步当前需求与原工作流规格

**Files:**

- Modify: `docs/requirements/04-review-quality-and-workflow.md`
- Modify: `docs/specs/2026-07-30-short-medium-writing-workflow.md`

- [ ] **Step 1: 更新当前需求**

在“中短篇不可变版本”段落加入：

```markdown
人工正文版本默认继续继承基础正文的来源大纲。只有请求显式指定同一作品
当前已应用大纲，并在预览中确认包含目标来源的 `confirmationHash`，才允许
创建重绑定版本。仅来源变化也会创建更高版本号的 `applied` 正文版本；正文、
内容 hash、字数和历史版本保持不变。预览中的 `dirty` 表示
`contentChanged || sourceOutlineChanged`。候选采用、历史恢复和 Agent 版本不
接受来源覆盖。
```

- [ ] **Step 2: 更新原中短篇规格的显式例外**

在人工提交、来源绑定、公共 API、CLI 和验收段落统一写明：

```markdown
“相同内容不创建版本”只适用于内容和来源大纲都没有变化。人工请求可以显式
携带同一作品当前已应用大纲的 `sourceOutlineVersionId`；预览同时返回
`currentSourceOutlineVersionId`、`targetSourceOutlineVersionId`、
`contentChanged` 和 `sourceOutlineChanged`，确认哈希绑定解析后的目标来源。
仅来源变化时创建内容相同的新人工版本，旧版本不修改；省略该字段时继续继承
基础正文来源，不能因当前大纲变化自动重绑定。
```

同时修正以下绝对表述：

- “当前工作稿与当前版本内容完全相同时不创建重复版本”改为“内容和来源大纲均未变化时不创建重复版本”。
- “后续人工正文版本继承基础版本来源”补充“除作者显式确认重绑定到当前已应用大纲外”。
- CLI 预览/提交说明补充两次请求必须使用同一个非空目标 ID。
- 验收增加仅溯源版本、默认不自动重绑定、历史版本不可变三项。

- [ ] **Step 3: 检查文档一致性并提交**

Run:

```powershell
rg -n "sourceOutlineVersionId|sourceOutlineChanged|contentChanged|相同内容" docs/requirements/04-review-quality-and-workflow.md docs/specs/2026-07-30-short-medium-writing-workflow.md docs/specs/2026-08-04-short-medium-manuscript-outline-provenance-rebinding.md
git diff --check
```

Expected: 三份文档语义一致，无空白错误。

```powershell
git add -- docs/requirements/04-review-quality-and-workflow.md docs/specs/2026-07-30-short-medium-writing-workflow.md
git commit -m "文档：同步正文来源大纲显式重绑定规则"
```

### Task 5: 完整验证实现与架构边界

**Files:**

- Verify only; no planned source changes.

- [ ] **Step 1: 运行 Core 中短篇与 CLI 完整相关测试**

```powershell
uv run pytest apps/core-api/tests/short_medium tools/inkforge-cli/tests -q
```

Expected: 0 failed。

- [ ] **Step 2: 运行 Python 静态检查**

```powershell
uv run ruff check apps/core-api/src/inkforge_core/short_medium apps/core-api/tests/short_medium tools/inkforge-cli
uv run mypy apps/core-api/src tools/inkforge-cli/src
```

Expected: Ruff 与 Mypy 都退出 0。

- [ ] **Step 3: 运行公共客户端与前端兼容检查**

```powershell
npm run api:check
npm run typecheck
npm run lint
```

Expected: 全部退出 0。

- [ ] **Step 4: 核对未越界改动**

```powershell
git diff a46508e..HEAD --name-only
git status --short
```

Expected: 不包含数据库 schema、迁移、Agent Service、service-contracts 或 Web 业务文件；工作树干净。

### Task 6: 为《无年之灾》生成仅溯源 v9 预览

**Files:**

- Read/write through `C:\Users\niebo\.codex\skills\inkforge-short-story-operator\scripts\operator.ps1` only.
- Snapshot: `C:\Users\niebo\AppData\Local\InkForge\codex-operator\snapshots\cmsbunx463fl8yixoszfnkm16\provenance-v9-preview-2026-08-04-01`

- [ ] **Step 1: 确认本地 Core 已加载新实现**

若当前 `npm run dev` 正在运行，Uvicorn `--reload` 会加载改动；否则按项目入口启动：

```powershell
npm run dev
```

从另一个 PowerShell 会话运行身份检查；只有身份为 `nie` 才继续：

```powershell
'{"expectedUsername":"nie"}' | & 'C:\Users\niebo\.codex\skills\inkforge-short-story-operator\scripts\operator.ps1' auth.whoami
```

- [ ] **Step 2: 拉取新的干净快照**

```powershell
$payload = @{
    novelId = 'cmsbunx463fl8yixoszfnkm16'
    outputDirectory = 'C:\Users\niebo\AppData\Local\InkForge\codex-operator\snapshots\cmsbunx463fl8yixoszfnkm16\provenance-v9-preview-2026-08-04-01'
} | ConvertTo-Json -Compress
$payload | & 'C:\Users\niebo\.codex\skills\inkforge-short-story-operator\scripts\operator.ps1' short.pull
```

Expected: 当前大纲为 v4 `cmsdbw40s6n2royakxqpmd2jq`，当前正文为 v8 `cmsdbxfqk6n2toyaknu4awreg`，正文内容 hash 为 `6bfb53700b06849deb5ecd8b9cf3fe7030fcb636c81fa032f1e3bbcc7a0c8b0f`。

- [ ] **Step 3: 生成仅溯源预览**

```powershell
$root = 'C:\Users\niebo\AppData\Local\InkForge\codex-operator\snapshots\cmsbunx463fl8yixoszfnkm16\provenance-v9-preview-2026-08-04-01'
$payload = @{
    novelId = 'cmsbunx463fl8yixoszfnkm16'
    documentType = 'manuscript'
    chapterId = 'cmsbunx663fl9yixotm7vl7d8'
    baseVersionId = 'cmsdbxfqk6n2toyaknu4awreg'
    sourceOutlineVersionId = 'cmsdbw40s6n2royakxqpmd2jq'
    outputFile = (Join-Path $root 'diffs\manuscript-v9-provenance-preview.json')
} | ConvertTo-Json -Compress
$payload | & 'C:\Users\niebo\.codex\skills\inkforge-short-story-operator\scripts\operator.ps1' short.version.preview
```

Expected:

- `contentChanged=false`
- `sourceOutlineChanged=true`
- `dirty=true`
- 当前来源为大纲 v2 `cmscfmzjz6n0zoyakdrnhkad8`
- 目标来源为大纲 v4 `cmsdbw40s6n2royakxqpmd2jq`
- 字数变化 0，`diff.blocks=[]`
- 返回新的 `confirmationHash`

- [ ] **Step 4: 展示完整预览并暂停**

向用户展示基础正文 v8、目标大纲 v4、当前/目标来源、字数变化、空文本 Diff、摘要和完整 `confirmationHash`。没有用户对该哈希的明确确认，不执行 `short.version.submit`。

### Task 7: 用户确认后创建 v9 并最终对账

**Files:**

- Same operator and snapshot as Task 6.

- [ ] **Step 1: 提交前再次确认身份**

```powershell
'{"expectedUsername":"nie"}' | & 'C:\Users\niebo\.codex\skills\inkforge-short-story-operator\scripts\operator.ps1' auth.whoami
```

- [ ] **Step 2: 使用同一预览事实提交一次**

执行 Agent 把用户回复中的完整哈希绑定为运行时变量 `$confirmedHash`，随后重新运行同一预览。只有新预览哈希与用户确认哈希完全相同才组装提交请求；不得重新生成 client request ID：

```powershell
$root = 'C:\Users\niebo\AppData\Local\InkForge\codex-operator\snapshots\cmsbunx463fl8yixoszfnkm16\provenance-v9-preview-2026-08-04-01'
$previewPayload = @{
    novelId = 'cmsbunx463fl8yixoszfnkm16'
    documentType = 'manuscript'
    chapterId = 'cmsbunx663fl9yixotm7vl7d8'
    baseVersionId = 'cmsdbxfqk6n2toyaknu4awreg'
    sourceOutlineVersionId = 'cmsdbw40s6n2royakxqpmd2jq'
    outputFile = (Join-Path $root 'diffs\manuscript-v9-provenance-recheck.json')
} | ConvertTo-Json -Compress
$previewResult = $previewPayload |
    & 'C:\Users\niebo\.codex\skills\inkforge-short-story-operator\scripts\operator.ps1' short.version.preview |
    ConvertFrom-Json
$previewData = $previewResult.data
if ($previewData.confirmationHash -ne $confirmedHash) {
    throw '用户确认哈希与最新预览不一致，禁止提交'
}
$payload = @{
    novelId = 'cmsbunx463fl8yixoszfnkm16'
    documentType = 'manuscript'
    chapterId = 'cmsbunx663fl9yixotm7vl7d8'
    baseVersionId = 'cmsdbxfqk6n2toyaknu4awreg'
    sourceOutlineVersionId = 'cmsdbw40s6n2royakxqpmd2jq'
    expectedUpdatedAt = $previewData.expectedUpdatedAt
    contentHash = $previewData.contentHash
    confirmationHash = $confirmedHash
    clientRequestId = 'codex-manuscript-provenance-v9-20260804-01'
    summary = '正文内容不变，显式绑定当前大纲 v4'
    manifestPath = (Join-Path $root 'manifest.json')
} | ConvertTo-Json -Compress
$payload | & 'C:\Users\niebo\.codex\skills\inkforge-short-story-operator\scripts\operator.ps1' short.version.submit
```

`$confirmedHash` 必须来自用户对 Task 6 响应的明确回复；不能猜测、留空或复用旧哈希。重新预览只用于确认权威状态仍未变化，若哈希变化则必须返回 Task 6 重新展示并等待确认。

- [ ] **Step 3: 重新拉取并核对 v9**

拉取到一个新的目录，避免覆盖旧 manifest：

```powershell
$payload = @{
    novelId = 'cmsbunx463fl8yixoszfnkm16'
    outputDirectory = 'C:\Users\niebo\AppData\Local\InkForge\codex-operator\snapshots\cmsbunx463fl8yixoszfnkm16\provenance-v9-final-2026-08-04-01'
} | ConvertTo-Json -Compress
$payload | & 'C:\Users\niebo\.codex\skills\inkforge-short-story-operator\scripts\operator.ps1' short.pull
```

再运行 `short.version.list` 和 `short.version.get`，并核对：

- 最新正文为 v9、`status=applied`、`baseVersionId=cmsdbxfqk6n2toyaknu4awreg`。
- v9 `sourceOutlineVersionId=cmsdbw40s6n2royakxqpmd2jq`。
- v8 仍绑定 `cmscfmzjz6n0zoyakdrnhkad8`，历史未被修改。
- v8 与 v9 内容 SHA-256 都是 `6bfb53700b06849deb5ecd8b9cf3fe7030fcb636c81fa032f1e3bbcc7a0c8b0f`，字数都是 17831。
- 最终正文仍包含“这一次，他真正念出一道咒：”与四句结尾，最后非空行是“天下大吉。”。
