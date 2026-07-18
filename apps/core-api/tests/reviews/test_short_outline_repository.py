from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from inkforge_core.db.models import (
    Chapter,
    Novel,
    ReviewArtifact,
    ReviewArtifactEvaluation,
    ReviewArtifactRevision,
    User,
    WritingBible,
    WritingTask,
)
from inkforge_core.errors import ApiError
from inkforge_core.reviews.repository import ReviewRepository
from inkforge_core.reviews.schemas import CreateArtifactRequest, SaveShortStoryOutlineRequest
from inkforge_core.short_story_artifacts import writing_bible_lock_statement
from sqlalchemy import event
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

TABLES = [
    User.__table__,
    Novel.__table__,
    Chapter.__table__,
    WritingBible.__table__,
    WritingTask.__table__,
    ReviewArtifact.__table__,
    ReviewArtifactRevision.__table__,
    ReviewArtifactEvaluation.__table__,
]


def _payload(*, premise: str = "守夜人必须在黎明前查清讣告来源。") -> dict[str, object]:
    return {
        "kind": "outline_draft",
        "storyLengthProfile": "short_medium",
        "originalInspiration": "守夜人收到自己的讣告。",
        "corePremise": premise,
        "anchors": {"mustKeep": ["未来讣告"], "confirmed": [], "avoid": ["梦境"]},
        "sections": [{"id": "section-1", "title": "讣告", "events": "守夜人收到讣告。"}],
        "content": "由结构化字段重建",
        "changeSummary": "首次生成",
        "anchorChanges": [],
    }


def _create_request(
    *,
    status: str = "draft",
    payload: dict[str, object] | None = None,
    expected_revision: int | None = None,
    title: str = "中短篇大纲",
    summary: str = "首次生成",
    diff: object = None,
    artifact_key: str = "short-outline",
) -> CreateArtifactRequest:
    return CreateArtifactRequest.model_validate(
        {
            "runId": "run-1",
            "taskId": "task-1",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "artifactKey": artifact_key,
            "kind": "outline_draft",
            "status": status,
            "title": title,
            "summary": summary,
            "payload": payload or _payload(),
            "diff": diff,
            "createdByAgent": "剧情",
            "expectedRevision": expected_revision,
        }
    )


@pytest_asyncio.fixture
async def repository(tmp_path: Path) -> AsyncIterator[ReviewRepository]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'reviews.db').as_posix()}")

    @event.listens_for(engine.sync_engine, "connect")
    def attach_public_schema(dbapi_connection: object, _record: object) -> None:
        dbapi_connection.execute("ATTACH DATABASE ':memory:' AS public")  # type: ignore[attr-defined]

    saved_defaults = [
        (column, column.server_default) for table in TABLES for column in table.columns
    ]
    try:
        for column, _default in saved_defaults:
            column.server_default = None
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: User.metadata.create_all(
                    sync_connection,
                    tables=TABLES,
                )
            )
    finally:
        for column, default in saved_defaults:
            column.server_default = default

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            session.add(
                User(
                    id="user-1",
                    username="owner",
                    passwordHash="hash",
                    creditBalanceMicros=0,
                )
            )
            session.add(Novel(id="novel-1", userId="user-1", name="守夜"))
            session.add(
                Chapter(
                    id="chapter-1",
                    novelId="novel-1",
                    order=1,
                    status="drafting",
                    title="正文",
                    content="",
                )
            )
            session.add(
                WritingBible(
                    id="bible-1",
                    novelId="novel-1",
                    storyLengthProfile="short_medium",
                    targetTotalWordCount=6000,
                )
            )
            session.add(
                WritingTask(
                    id="task-1",
                    novelId="novel-1",
                    chapterId="chapter-1",
                    phase="active",
                    selectedAgents="剧情",
                    targetWordCount=6000,
                )
            )
    try:
        yield ReviewRepository(factory)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_content_changes_create_exactly_one_revision_and_status_replay_does_not(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _create_request())
    assert created.revision == 1

    awaiting = await repository.create_or_revise(
        "user-1",
        _create_request(status="awaiting_user", diff={"rawUserMessage": "保留结尾"}),
    )
    assert awaiting.revision == 1
    assert awaiting.status == "awaiting_user"
    assert awaiting.diff is None

    stale_callback = await repository.create_or_revise("user-1", _create_request(status="draft"))
    assert stale_callback.revision == 1
    assert stale_callback.status == "awaiting_user"

    changed = await repository.create_or_revise(
        "user-1",
        _create_request(
            status="draft",
            payload=_payload(premise="守夜人必须主动改写自己的死亡。"),
            expected_revision=1,
            diff={"rawUserMessage": "让主角更主动"},
        ),
    )
    assert changed.revision == 2
    assert changed.diff == {"rawUserMessage": "让主角更主动"}
    revisions = await repository.list_revisions("user-1", created.id)
    assert [item.revision for item in revisions] == [2, 1]


@pytest.mark.asyncio
async def test_create_or_revise_ignores_version_notes_and_keeps_current_payload(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _create_request())
    notes_only_payload = _payload()
    notes_only_payload["changeSummary"] = "模型换了一种版本摘要"
    notes_only_payload["anchorChanges"] = ["仅解释旧锚点，没有修改锚点"]

    replay = await repository.create_or_revise(
        "user-1",
        _create_request(
            status="awaiting_user",
            payload=notes_only_payload,
            summary="新的顶层摘要",
            diff={"rawUserMessage": "请换一种方式总结"},
        ),
    )

    assert replay.revision == 1
    assert replay.status == "awaiting_user"
    assert replay.summary == "首次生成"
    assert replay.diff is None
    assert replay.payload.changeSummary == "首次生成"  # type: ignore[union-attr]
    assert replay.payload.anchorChanges == []  # type: ignore[union-attr]
    revisions = await repository.list_revisions("user-1", created.id)
    assert [item.revision for item in revisions] == [1]


@pytest.mark.asyncio
async def test_agent_outline_anchor_changes_are_computed_by_core(
    repository: ReviewRepository,
) -> None:
    initial_payload = _payload()
    initial_payload["anchorChanges"] = ["模型伪造的首版锚点变化"]
    created = await repository.create_or_revise(
        "user-1",
        _create_request(status="awaiting_user", payload=initial_payload),
    )
    assert created.payload.anchorChanges == []  # type: ignore[union-attr]

    revised_payload = _payload()
    revised_payload["anchors"] = {
        "mustKeep": ["回到黎明"],
        "confirmed": ["主角知情"],
        "avoid": [],
    }
    revised_payload["anchorChanges"] = ["模型伪造的修订锚点变化"]
    revised = await repository.create_or_revise(
        "user-1",
        _create_request(
            status="awaiting_user",
            payload=revised_payload,
            expected_revision=created.revision,
        ),
    )

    assert revised.payload.anchorChanges == [  # type: ignore[union-attr]
        "必须保留新增：回到黎明",
        "必须保留移除：未来讣告",
        "已经确认新增：主角知情",
        "明确不要移除：梦境",
    ]


@pytest.mark.asyncio
async def test_short_outline_create_locks_bible_before_task_and_artifact(
    repository: ReviewRepository,
) -> None:
    statements: list[str] = []
    engine = repository._session_factory.kw["bind"]  # noqa: SLF001

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record_statement)
    try:
        await repository.create_or_revise("user-1", _create_request())
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record_statement)

    bible_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.lstrip().upper().startswith("SELECT") and '"WritingBible"' in statement
    )
    task_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.lstrip().upper().startswith("SELECT") and '"WritingTask"' in statement
    )
    artifact_insert_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.lstrip().upper().startswith("INSERT")
        and '"ReviewArtifact"' in statement
    )
    assert bible_index < task_index < artifact_insert_index


@pytest.mark.asyncio
async def test_short_outline_revision_locks_bible_before_task_and_artifact(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _create_request())
    statements: list[str] = []
    engine = repository._session_factory.kw["bind"]  # noqa: SLF001

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record_statement)
    try:
        await repository.create_or_revise(
            "user-1",
            _create_request(
                payload=_payload(premise="守夜人必须主动改写自己的死亡。"),
                expected_revision=created.revision,
            ),
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record_statement)

    bible_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.lstrip().upper().startswith("SELECT") and '"WritingBible"' in statement
    )
    task_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.lstrip().upper().startswith("SELECT") and '"WritingTask"' in statement
    )
    artifact_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.lstrip().upper().startswith("SELECT")
        and '"ReviewArtifact"' in statement
    )
    assert bible_index < task_index < artifact_index


def test_writing_bible_lock_statement_targets_shared_postgresql_row() -> None:
    sql = str(
        writing_bible_lock_statement(
            "novel-1",
            user_id="user-1",
        ).compile(dialect=postgresql.dialect())
    )

    assert 'FOR UPDATE OF "WritingBible"' in sql
    assert '"WritingBible"."novelId"' in sql
    assert '"Novel"."userId"' in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["direct_edit", "restore"])
async def test_user_outline_writes_lock_bible_before_task_and_artifact(
    repository: ReviewRepository,
    action: str,
) -> None:
    created = await repository.create_or_revise(
        "user-1", _create_request(status="awaiting_user")
    )
    current = created.payload
    assert not isinstance(current, dict)
    expected_revision = created.revision
    if action == "restore":
        revised = await repository.create_or_revise(
            "user-1",
            _create_request(
                status="awaiting_user",
                payload=_payload(premise="守夜人先追查讣告纸张。"),
                expected_revision=created.revision,
            ),
        )
        expected_revision = revised.revision

    statements: list[str] = []
    engine = repository._session_factory.kw["bind"]  # noqa: SLF001

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record_statement)
    try:
        if action == "restore":
            await repository.restore_revision(
                "user-1",
                created.id,
                1,
                expected_revision=expected_revision,
            )
        else:
            await repository.save_short_story_outline(
                "user-1",
                created.id,
                SaveShortStoryOutlineRequest.model_validate(
                    {
                        "expectedRevision": expected_revision,
                        "corePremise": "守夜人主动追查讣告纸张。",
                        "anchors": current.anchors,
                        "sections": [
                            section.model_dump() for section in current.sections
                        ],
                        "changeSummary": "用户直接修改",
                    }
                ),
            )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record_statement)

    bible_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.lstrip().upper().startswith("SELECT") and '"WritingBible"' in statement
    )
    task_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.lstrip().upper().startswith("SELECT") and '"WritingTask"' in statement
    )
    locked_artifact_index = next(
        index
        for index, statement in enumerate(statements)
        if index > task_index
        and statement.lstrip().upper().startswith("SELECT")
        and '"ReviewArtifact"' in statement
    )
    assert bible_index < task_index < locked_artifact_index


@pytest.mark.asyncio
async def test_content_change_requires_current_expected_revision(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _create_request())
    changed_payload = _payload(premise="新的核心前提")

    with pytest.raises(ApiError) as missing:
        await repository.create_or_revise("user-1", _create_request(payload=changed_payload))
    assert missing.value.code == "ARTIFACT_EXPECTED_REVISION_REQUIRED"

    with pytest.raises(ApiError) as stale:
        await repository.create_or_revise(
            "user-1",
            _create_request(payload=changed_payload, expected_revision=99),
        )
    assert stale.value.code == "ARTIFACT_REVISION_CONFLICT"
    assert (await repository.get_response("user-1", created.id)).revision == 1


@pytest.mark.asyncio
async def test_short_medium_project_rejects_legacy_untyped_outline_payload(
    repository: ReviewRepository,
) -> None:
    request = CreateArtifactRequest.model_validate(
        {
            "runId": "run-1",
            "taskId": "task-1",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "artifactKey": "short-outline",
            "kind": "outline_draft",
            "status": "draft",
            "payload": {"kind": "outline_draft", "content": "旧长篇自由文本"},
            "createdByAgent": "剧情",
        }
    )
    with pytest.raises(ApiError) as caught:
        await repository.create_or_revise("user-1", request)
    assert caught.value.code == "SHORT_OUTLINE_PAYLOAD_INVALID"


@pytest.mark.asyncio
async def test_long_serial_project_rejects_payload_claiming_short_medium(
    repository: ReviewRepository,
) -> None:
    async with repository._session_factory() as session:  # noqa: SLF001
        async with session.begin():
            bible = await session.get(WritingBible, "bible-1")
            assert bible is not None
            bible.storyLengthProfile = "long_serial"

    with pytest.raises(ApiError) as caught:
        await repository.create_or_revise("user-1", _create_request())
    assert caught.value.code == "ARTIFACT_PROFILE_MISMATCH"


@pytest.mark.asyncio
async def test_long_serial_artifact_keeps_existing_full_field_revision_semantics(
    repository: ReviewRepository,
) -> None:
    async with repository._session_factory() as session:  # noqa: SLF001
        async with session.begin():
            bible = await session.get(WritingBible, "bible-1")
            assert bible is not None
            bible.storyLengthProfile = "long_serial"

    base_values = {
        "runId": "run-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "artifactKey": "long-outline",
        "kind": "outline_draft",
        "status": "draft",
        "title": "长篇大纲",
        "payload": {"kind": "outline_draft", "content": "同一份长篇大纲"},
        "createdByAgent": "剧情",
    }
    created = await repository.create_or_revise(
        "user-1",
        CreateArtifactRequest.model_validate({**base_values, "summary": "初版说明"}),
    )
    revised = await repository.create_or_revise(
        "user-1",
        CreateArtifactRequest.model_validate(
            {
                **base_values,
                "summary": "长篇仍把摘要变化视为修订",
                "expectedRevision": created.revision,
            }
        ),
    )

    assert revised.revision == 2
    assert revised.summary == "长篇仍把摘要变化视为修订"


@pytest.mark.asyncio
async def test_direct_edit_generates_missing_ids_then_history_restore_copies_new_revision(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _create_request(status="awaiting_user"))
    edited = await repository.save_short_story_outline(
        "user-1",
        created.id,
        SaveShortStoryOutlineRequest.model_validate(
            {
                "expectedRevision": 1,
                "corePremise": "守夜人决定追查写信人。",
                "anchors": {"mustKeep": ["未来讣告"], "confirmed": [], "avoid": ["梦境"]},
                "sections": [{"title": "追查", "events": "守夜人追查笔迹。"}],
                "changeSummary": "用户直接调整主线",
            }
        ),
    )
    assert edited.revision == 2
    assert edited.payload.sections[0].id  # type: ignore[union-attr]
    assert edited.payload.content.startswith("# 原始灵感")  # type: ignore[union-attr]

    replay_edit = await repository.save_short_story_outline(
        "user-1",
        created.id,
        SaveShortStoryOutlineRequest.model_validate(
            {
                "expectedRevision": 1,
                "corePremise": "守夜人决定追查写信人。",
                "anchors": {"mustKeep": ["未来讣告"], "confirmed": [], "avoid": ["梦境"]},
                "sections": [{"title": "追查", "events": "守夜人追查笔迹。"}],
                "changeSummary": "用户直接调整主线",
            }
        ),
    )
    assert replay_edit.revision == 2

    with pytest.raises(ApiError) as unknown_id:
        await repository.save_short_story_outline(
            "user-1",
            created.id,
            SaveShortStoryOutlineRequest.model_validate(
                {
                    "expectedRevision": 2,
                    "corePremise": "守夜人决定追查写信人。",
                    "anchors": {"mustKeep": [], "confirmed": [], "avoid": []},
                    "sections": [
                        {"id": "client-forged-id", "title": "伪造", "events": "伪造身份。"}
                    ],
                }
            ),
        )
    assert unknown_id.value.code == "SHORT_OUTLINE_SECTION_ID_UNKNOWN"

    detail = await repository.get_revision("user-1", created.id, 1)
    assert detail.payload.corePremise == "守夜人必须在黎明前查清讣告来源。"  # type: ignore[union-attr]

    restored = await repository.restore_revision("user-1", created.id, 1, expected_revision=2)
    assert restored.revision == 3
    assert restored.payload.corePremise == detail.payload.corePremise  # type: ignore[union-attr]

    replay = await repository.restore_revision("user-1", created.id, 1, expected_revision=2)
    assert replay.revision == 3


@pytest.mark.asyncio
async def test_direct_edit_computes_anchor_changes_from_authoritative_versions(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise(
        "user-1", _create_request(status="awaiting_user")
    )
    current = created.payload
    assert not isinstance(current, dict)

    edited = await repository.save_short_story_outline(
        "user-1",
        created.id,
        SaveShortStoryOutlineRequest.model_validate(
            {
                "expectedRevision": created.revision,
                "corePremise": current.corePremise,
                "anchors": {
                    "mustKeep": ["回到黎明"],
                    "confirmed": ["主角知情"],
                    "avoid": [],
                },
                "sections": [section.model_dump() for section in current.sections],
                "changeSummary": "用户调整创作锚点",
                "anchorChanges": ["客户端伪造的差异说明"],
            }
        ),
    )

    assert edited.revision == 2
    assert edited.payload.anchorChanges == [  # type: ignore[union-attr]
        "必须保留新增：回到黎明",
        "必须保留移除：未来讣告",
        "已经确认新增：主角知情",
        "明确不要移除：梦境",
    ]


@pytest.mark.asyncio
async def test_direct_edit_with_only_version_notes_is_noop_and_keeps_current_payload(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _create_request(status="awaiting_user"))
    current = created.payload
    assert not isinstance(current, dict)

    replay = await repository.save_short_story_outline(
        "user-1",
        created.id,
        SaveShortStoryOutlineRequest.model_validate(
            {
                "expectedRevision": 1,
                "corePremise": current.corePremise,
                "anchors": current.anchors,
                "sections": [section.model_dump() for section in current.sections],
                "changeSummary": "只重写用户编辑摘要",
                "anchorChanges": ["只是说明，没有改变锚点"],
            }
        ),
    )

    assert replay.revision == 1
    assert replay.summary == "首次生成"
    assert replay.diff is None
    assert replay.payload.changeSummary == "首次生成"  # type: ignore[union-attr]
    assert replay.payload.anchorChanges == []  # type: ignore[union-attr]
    revisions = await repository.list_revisions("user-1", created.id)
    assert [item.revision for item in revisions] == [1]


@pytest.mark.asyncio
async def test_restore_semantically_identical_revision_is_noop_and_keeps_current_notes(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _create_request(status="awaiting_user"))
    changed = await repository.create_or_revise(
        "user-1",
        _create_request(
            status="awaiting_user",
            payload=_payload(premise="守夜人先查明讣告的纸张来源。"),
            expected_revision=1,
            summary="第二版摘要",
        ),
    )
    returned_payload = _payload()
    returned_payload["changeSummary"] = "重新回到初版故事内容"
    returned_payload["anchorChanges"] = ["恢复原先的核心前提"]
    returned = await repository.create_or_revise(
        "user-1",
        _create_request(
            status="awaiting_user",
            payload=returned_payload,
            expected_revision=changed.revision,
            summary="当前第三版摘要",
            diff={"rawUserMessage": "还是使用原来的故事"},
        ),
    )
    assert returned.revision == 3

    replay = await repository.restore_revision(
        "user-1",
        created.id,
        1,
        expected_revision=returned.revision,
    )

    assert replay.revision == 3
    assert replay.summary == "当前第三版摘要"
    assert replay.diff == {"rawUserMessage": "还是使用原来的故事"}
    assert replay.payload.changeSummary == "重新回到初版故事内容"  # type: ignore[union-attr]
    assert replay.payload.anchorChanges == []  # type: ignore[union-attr]
    revisions = await repository.list_revisions("user-1", created.id)
    assert [item.revision for item in revisions] == [3, 2, 1]


@pytest.mark.asyncio
async def test_restore_recomputes_anchor_changes_from_current_to_target(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise(
        "user-1", _create_request(status="awaiting_user")
    )
    changed_payload = _payload(premise="守夜人决定亲自改写讣告。")
    changed_payload["anchors"] = {
        "mustKeep": ["回到黎明"],
        "confirmed": ["主角知情"],
        "avoid": [],
    }
    changed = await repository.create_or_revise(
        "user-1",
        _create_request(
            status="awaiting_user",
            payload=changed_payload,
            expected_revision=created.revision,
        ),
    )

    restored = await repository.restore_revision(
        "user-1",
        created.id,
        1,
        expected_revision=changed.revision,
    )

    assert restored.payload.anchorChanges == [  # type: ignore[union-attr]
        "必须保留新增：未来讣告",
        "必须保留移除：回到黎明",
        "已经确认移除：主角知情",
        "明确不要新增：梦境",
    ]


@pytest.mark.asyncio
async def test_stale_direct_edit_with_removed_section_reports_revision_conflict(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise(
        "user-1", _create_request(status="awaiting_user")
    )
    current = created.payload
    assert not isinstance(current, dict)
    original_section = current.sections[0]
    await repository.save_short_story_outline(
        "user-1",
        created.id,
        SaveShortStoryOutlineRequest.model_validate(
            {
                "expectedRevision": 1,
                "corePremise": "另一标签页已经重写结构",
                "anchors": current.anchors,
                "sections": [{"title": "新结构", "events": "新事件"}],
                "changeSummary": "并发修改",
            }
        ),
    )

    with pytest.raises(ApiError) as stale:
        await repository.save_short_story_outline(
            "user-1",
            created.id,
            SaveShortStoryOutlineRequest.model_validate(
                {
                    "expectedRevision": 1,
                    "corePremise": "旧标签页的本地编辑",
                    "anchors": current.anchors,
                    "sections": [
                        {
                            "id": original_section.id,
                            "title": original_section.title,
                            "events": "旧标签页继续修改原分节",
                        }
                    ],
                    "changeSummary": "旧标签页保存",
                }
            ),
        )

    assert stale.value.code == "ARTIFACT_REVISION_CONFLICT"


@pytest.mark.asyncio
async def test_direct_edit_and_restore_require_awaiting_user_status(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _create_request(status="draft"))
    request = SaveShortStoryOutlineRequest.model_validate(
        {
            "expectedRevision": 1,
            "corePremise": "不能在 draft 直接编辑",
            "anchors": {"mustKeep": [], "confirmed": [], "avoid": []},
            "sections": [{"title": "开头", "events": "发生事件。"}],
        }
    )
    with pytest.raises(ApiError) as edit_error:
        await repository.save_short_story_outline("user-1", created.id, request)
    assert edit_error.value.code == "SHORT_OUTLINE_NOT_AWAITING_USER"

    with pytest.raises(ApiError) as restore_error:
        await repository.restore_revision("user-1", created.id, 1, expected_revision=1)
    assert restore_error.value.code == "SHORT_OUTLINE_NOT_AWAITING_USER"


@pytest.mark.asyncio
async def test_short_outline_version_apis_reject_long_serial_artifact(
    repository: ReviewRepository,
) -> None:
    await repository.create_or_revise("user-1", _create_request())
    # 即使载荷伪装为中短篇，作品圣经仍是最终 Profile 权威来源。
    async with repository._session_factory() as session:  # noqa: SLF001
        async with session.begin():
            bible = await session.get(WritingBible, "bible-1")
            assert bible is not None
            bible.storyLengthProfile = "long_serial"

    artifact = await repository.get_task_artifact("user-1", "task-1")
    assert artifact is not None
    with pytest.raises(ApiError) as caught:
        await repository.list_revisions("user-1", artifact.id)
    assert caught.value.code == "SHORT_OUTLINE_REQUIRED"


@pytest.mark.asyncio
async def test_short_outline_approve_requires_latest_typed_outline(
    repository: ReviewRepository,
) -> None:
    older = await repository.create_or_revise(
        "user-1",
        _create_request(status="awaiting_user", artifact_key="short-outline-old"),
    )
    newer = await repository.create_or_revise(
        "user-1",
        _create_request(
            status="awaiting_user",
            artifact_key="short-outline-new",
            payload=_payload(premise="守夜人决定先追查讣告纸张。"),
        ),
    )

    with pytest.raises(ApiError) as stale:
        await repository.require_short_story_artifact_revision(
            "user-1",
            older.id,
            older.revision,
            decision="approve",
        )
    assert stale.value.code == "SHORT_OUTLINE_NOT_LATEST"

    current = await repository.require_short_story_artifact_revision(
        "user-1",
        newer.id,
        newer.revision,
        decision="approve",
    )
    assert current.id == newer.id


@pytest.mark.asyncio
async def test_short_decision_repository_locks_bible_before_task_and_artifact(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise(
        "user-1", _create_request(status="awaiting_user")
    )
    statements: list[str] = []
    engine = repository._session_factory.kw["bind"]  # noqa: SLF001

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record_statement)
    try:
        await repository.require_short_story_artifact_revision(
            "user-1",
            created.id,
            created.revision,
            decision="revise",
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record_statement)

    bible_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.lstrip().upper().startswith("SELECT") and '"WritingBible"' in statement
    )
    task_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.lstrip().upper().startswith("SELECT") and '"WritingTask"' in statement
    )
    locked_artifact_index = next(
        index
        for index, statement in enumerate(statements)
        if index > task_index
        and statement.lstrip().upper().startswith("SELECT")
        and '"ReviewArtifact"' in statement
    )
    assert bible_index < task_index < locked_artifact_index
