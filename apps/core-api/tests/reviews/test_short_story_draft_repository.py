from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from inkforge_contracts import (
    ShortStoryOutlineDraft,
    canonical_short_outline_hash,
)
from inkforge_core.chapters.content_state import content_sha256
from inkforge_core.db.models import (
    Chapter,
    ChapterQualityCheck,
    Novel,
    ReviewArtifact,
    ReviewArtifactEvaluation,
    ReviewArtifactRevision,
    User,
    WorkflowRun,
    WritingBible,
    WritingRunCommand,
    WritingSession,
    WritingTask,
)
from inkforge_core.errors import ApiError
from inkforge_core.reviews.formal_writes import FormalWriteRepository
from inkforge_core.reviews.repository import ReviewRepository
from inkforge_core.reviews.schemas import (
    CreateArtifactRequest,
    SubmitArtifactEvaluationRequest,
)
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TABLES = [
    User.__table__,
    Novel.__table__,
    Chapter.__table__,
    ChapterQualityCheck.__table__,
    WritingBible.__table__,
    WritingSession.__table__,
    WritingTask.__table__,
    WritingRunCommand.__table__,
    WorkflowRun.__table__,
    ReviewArtifact.__table__,
    ReviewArtifactRevision.__table__,
    ReviewArtifactEvaluation.__table__,
]


def _outline() -> ShortStoryOutlineDraft:
    return ShortStoryOutlineDraft.model_validate(
        {
            "kind": "outline_draft",
            "storyLengthProfile": "short_medium",
            "originalInspiration": "守夜人收到自己的讣告。",
            "corePremise": "守夜人必须在黎明前查清讣告来源。",
            "anchors": {"mustKeep": ["未来讣告"], "confirmed": [], "avoid": []},
            "sections": [
                {"id": "section-1", "title": "讣告", "events": "守夜人收到讣告。"}
            ],
            "content": "由结构化字段重建",
            "changeSummary": "已批准版本",
            "anchorChanges": [],
        }
    )


def _command_payload(command_id: str = "command-1") -> dict[str, object]:
    del command_id
    outline = _outline()
    return {
        "version": 1,
        "resume": False,
        "chapterId": "chapter-1",
        "writingSessionId": None,
        "resumeInput": None,
        "workflowKind": "short_medium",
        "operation": "write_short_story",
        "targetTotalWordCount": 6000,
        "source": {
            "kind": "approved_short_outline",
            "outlineArtifactId": "outline-1",
            "outlineRevision": 1,
            "outlineHash": canonical_short_outline_hash(outline),
        },
    }


def _draft_request(
    *,
    content: str | None = None,
    command_id: str = "command-1",
    rewrite_count: int = 0,
    generation_reason: str = "user_request",
    expected_revision: int | None = None,
    status: str = "under_review",
    source_hash: str | None = None,
    base_hash: str | None = None,
    source_artifact_id: str = "outline-1",
    source_revision: int = 1,
    target_chapter_id: str = "chapter-1",
    target_word_count: int = 6000,
) -> CreateArtifactRequest:
    value = content or ("甲" * 6000)
    outline = _outline()
    return CreateArtifactRequest.model_validate(
        {
            "runId": "run-1",
            "taskId": "task-1",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "artifactKey": "short-story-draft",
            "kind": "chapter_draft",
            "status": status,
            "title": "完整正文草案",
            "summary": "整稿",
            "payload": {
                "kind": "chapter_draft",
                "storyLengthProfile": "short_medium",
                "content": value,
                "metadata": {
                    "sourceOutlineArtifactId": source_artifact_id,
                    "sourceOutlineRevision": source_revision,
                    "sourceOutlineHash": source_hash
                    or canonical_short_outline_hash(outline),
                    "targetWordCount": target_word_count,
                    "actualWordCount": len(value),
                    "targetChapterId": target_chapter_id,
                    "baseChapterHash": base_hash or content_sha256(""),
                    "generationCommandId": command_id,
                    "automaticRewriteCount": rewrite_count,
                    "generationReason": generation_reason,
                },
            },
            "createdByAgent": "写作",
            "expectedRevision": expected_revision,
        }
    )


def _evaluation(
    agent: str,
    *,
    revision: int = 1,
    verdict: str = "pass",
) -> SubmitArtifactEvaluationRequest:
    return SubmitArtifactEvaluationRequest.model_validate(
        {
            "runId": "run-1",
            "taskId": "task-1",
            "novelId": "novel-1",
            "revision": revision,
            "evaluatorAgent": agent,
            "verdict": verdict,
            "summary": f"{agent}审核通过",
            "requiredChanges": ("请修正因果漏洞" if verdict == "revise" else None),
        }
    )


@pytest_asyncio.fixture
async def repository(tmp_path: Path) -> AsyncIterator[ReviewRepository]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'short-story-reviews.db').as_posix()}"
    )

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
    outline = _outline()
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
            session.add(
                Novel(
                    id="novel-1",
                    userId="user-1",
                    name="守夜",
                    summary=outline.originalInspiration,
                )
            )
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
                WritingSession(
                    id="session-1",
                    novelId="novel-1",
                    chapterId="chapter-1",
                    title="中短篇创作",
                    phase="generating",
                )
            )
            session.add(
                WritingTask(
                    id="task-1",
                    novelId="novel-1",
                    chapterId="chapter-1",
                    phase="active",
                    selectedAgents="写作,编辑,校验",
                    targetWordCount=6000,
                    writingSessionId="session-1",
                )
            )
            session.add(
                ReviewArtifact(
                    id="outline-1",
                    novelId="novel-1",
                    chapterId="chapter-1",
                    kind="outline_draft",
                    status="applied",
                    revision=1,
                    payloadJson=outline.model_dump_json(),
                )
            )
            session.add(
                WritingRunCommand(
                    id="command-1",
                    taskId="task-1",
                    kind="start",
                    status="processing",
                    attemptCount=0,
                    idempotencyKey="user-1:start-1",
                    payloadJson=json.dumps(_command_payload(), ensure_ascii=False),
                )
            )
    try:
        yield ReviewRepository(factory)
    finally:
        await engine.dispose()


async def _add_newer_legacy_outline(repository: ReviewRepository) -> None:
    async with repository._session_factory() as session:  # noqa: SLF001
        async with session.begin():
            session.add(
                ReviewArtifact(
                    id="legacy-outline-newer",
                    novelId="novel-1",
                    chapterId="chapter-1",
                    kind="outline_draft",
                    status="awaiting_user",
                    revision=1,
                    payloadJson=json.dumps(
                        {"kind": "outline_draft", "content": "旧流程自由文本大纲"},
                        ensure_ascii=False,
                    ),
                    updatedAt=datetime(2099, 1, 1),
                )
            )


async def _add_newer_malformed_outline(repository: ReviewRepository) -> None:
    async with repository._session_factory() as session:  # noqa: SLF001
        async with session.begin():
            session.add(
                ReviewArtifact(
                    id="malformed-outline-newer",
                    novelId="novel-1",
                    chapterId="chapter-1",
                    kind="outline_draft",
                    status="awaiting_user",
                    revision=1,
                    payloadJson="{不是合法 JSON",
                    updatedAt=datetime(2099, 1, 2),
                )
            )


@pytest.mark.asyncio
async def test_initial_short_story_draft_rechecks_all_authoritative_sources(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _draft_request())

    assert created.revision == 1
    assert created.payload.metadata.generationCommandId == "command-1"  # type: ignore[union-attr]

    for request, code in [
        (_draft_request(source_hash="0" * 64), "SHORT_STORY_OUTLINE_SOURCE_CHANGED"),
        (
            _draft_request(source_artifact_id="outline-old"),
            "SHORT_STORY_OUTLINE_SOURCE_CHANGED",
        ),
        (
            _draft_request(source_revision=2),
            "SHORT_STORY_OUTLINE_SOURCE_CHANGED",
        ),
        (_draft_request(base_hash="1" * 64), "SHORT_STORY_CHAPTER_BASE_CHANGED"),
        (
            _draft_request(target_chapter_id="chapter-other"),
            "SHORT_STORY_TARGET_CHAPTER_MISMATCH",
        ),
        (
            _draft_request(target_word_count=7000),
            "SHORT_STORY_TARGET_MISMATCH",
        ),
        (_draft_request(command_id="other-command"), "SHORT_STORY_COMMAND_MISMATCH"),
    ]:
        with pytest.raises(ApiError) as caught:
            await repository.create_or_revise("user-1", request)
        assert caught.value.code == code


@pytest.mark.asyncio
async def test_initial_short_story_draft_skips_newer_legacy_outline(
    repository: ReviewRepository,
) -> None:
    await _add_newer_legacy_outline(repository)

    created = await repository.create_or_revise("user-1", _draft_request())

    assert created.revision == 1
    assert created.payload.metadata.sourceOutlineArtifactId == "outline-1"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_initial_short_story_draft_rejects_newer_malformed_outline(
    repository: ReviewRepository,
) -> None:
    await _add_newer_malformed_outline(repository)

    with pytest.raises(ApiError) as caught:
        await repository.create_or_revise("user-1", _draft_request())

    assert caught.value.code == "SHORT_OUTLINE_PAYLOAD_INVALID"


@pytest.mark.asyncio
async def test_short_story_draft_submission_locks_bible_before_task_and_outline(
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
        await repository.create_or_revise("user-1", _draft_request())
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
    outline_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.lstrip().upper().startswith("SELECT")
        and '"ReviewArtifact"' in statement
        and 'kind = ?' in statement
    )
    assert bible_index < task_index < outline_index


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("actual_count", "accepted"),
    [(5999, False), (6000, True), (80000, True), (80001, False)],
)
async def test_short_story_actual_word_count_boundaries_are_core_enforced(
    repository: ReviewRepository,
    actual_count: int,
    accepted: bool,
) -> None:
    request = _draft_request(content="甲" * actual_count)

    if accepted:
        result = await repository.create_or_revise("user-1", request)
        assert result.payload.metadata.actualWordCount == actual_count  # type: ignore[union-attr]
    else:
        with pytest.raises(ApiError) as caught:
            await repository.create_or_revise("user-1", request)
        assert caught.value.code == "SHORT_STORY_ACTUAL_WORD_COUNT_INVALID"


@pytest.mark.asyncio
async def test_short_story_reviews_are_serial_and_awaiting_requires_both(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _draft_request())

    with pytest.raises(ApiError) as validator_first:
        await repository.submit_evaluation("user-1", created.id, _evaluation("校验"))
    assert validator_first.value.code == "SHORT_STORY_EDITOR_REVIEW_REQUIRED"

    await repository.submit_evaluation("user-1", created.id, _evaluation("编辑"))
    with pytest.raises(ApiError) as awaiting_too_early:
        await repository.create_or_revise(
            "user-1", _draft_request(status="awaiting_user")
        )
    assert awaiting_too_early.value.code == "SHORT_STORY_REVIEWS_INCOMPLETE"

    reviewed = await repository.submit_evaluation(
        "user-1", created.id, _evaluation("校验")
    )
    assert [item.evaluatorAgent for item in reviewed.evaluations] == ["校验", "编辑"]
    awaiting = await repository.create_or_revise(
        "user-1", _draft_request(status="awaiting_user")
    )
    assert awaiting.status == "awaiting_user"


@pytest.mark.asyncio
async def test_one_automatic_rewrite_requires_first_dual_review(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _draft_request())
    rewritten = _draft_request(
        content="乙" * 6000,
        rewrite_count=1,
        generation_reason="automatic_rewrite",
        expected_revision=1,
    )
    with pytest.raises(ApiError) as no_reviews:
        await repository.create_or_revise("user-1", rewritten)
    assert no_reviews.value.code == "SHORT_STORY_AUTOMATIC_REWRITE_REVIEW_REQUIRED"

    await repository.submit_evaluation(
        "user-1",
        created.id,
        _evaluation("编辑", verdict="revise"),
    )
    await repository.submit_evaluation("user-1", created.id, _evaluation("校验"))
    revised = await repository.create_or_revise("user-1", rewritten)
    assert revised.revision == 2
    assert revised.payload.metadata.automaticRewriteCount == 1  # type: ignore[union-attr]

    with pytest.raises(ValidationError):
        _draft_request(
            content="丙" * 6000,
            rewrite_count=2,
            generation_reason="automatic_rewrite",
            expected_revision=2,
        )


@pytest.mark.asyncio
async def test_automatic_rewrite_is_rejected_when_both_reviews_pass(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _draft_request())
    await repository.submit_evaluation("user-1", created.id, _evaluation("编辑"))
    await repository.submit_evaluation("user-1", created.id, _evaluation("校验"))

    with pytest.raises(ApiError) as caught:
        await repository.create_or_revise(
            "user-1",
            _draft_request(
                content="乙" * 6000,
                rewrite_count=1,
                generation_reason="automatic_rewrite",
                expected_revision=1,
            ),
        )

    assert caught.value.code == "SHORT_STORY_AUTOMATIC_REWRITE_NOT_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rewrite_count", "generation_reason"),
    [(0, "automatic_rewrite"), (1, "user_request")],
)
async def test_short_story_rewrite_count_and_reason_must_match(
    repository: ReviewRepository,
    rewrite_count: int,
    generation_reason: str,
) -> None:
    with pytest.raises(ApiError) as caught:
        await repository.create_or_revise(
            "user-1",
            _draft_request(
                rewrite_count=rewrite_count,
                generation_reason=generation_reason,
            ),
        )
    assert caught.value.code == "SHORT_STORY_INITIAL_GENERATION_INVALID"


@pytest.mark.asyncio
async def test_new_command_count_zero_requires_user_revise_decision(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _draft_request())
    payload = {
        **_command_payload(),
        "resume": True,
        "resumeInput": {
            "artifactId": created.id,
            "decision": "revise",
            "expectedRevision": 1,
            "userMessage": "请让结局更克制",
        },
        "decisionRequest": {
            "artifactId": created.id,
            "decision": "revise",
            "expectedRevision": 1,
            "editedContent": None,
            "selectedUpdateRefs": None,
            "userMessage": "请让结局更克制",
        },
    }
    async with repository._session_factory() as session:  # noqa: SLF001
        async with session.begin():
            first = await session.get(WritingRunCommand, "command-1")
            assert first is not None
            await session.delete(first)
            await session.flush()
            session.add(
                WritingRunCommand(
                    id="command-2",
                    taskId="task-1",
                    artifactId=created.id,
                    decision="revise",
                    kind="artifact_decision",
                    status="processing",
                    attemptCount=0,
                    idempotencyKey="user-1:revise-1",
                    payloadJson=json.dumps(payload, ensure_ascii=False),
                )
            )

    revised = await repository.create_or_revise(
        "user-1",
        _draft_request(
            content="乙" * 6000,
            command_id="command-2",
            rewrite_count=0,
            generation_reason="user_request",
            expected_revision=1,
        ),
    )

    assert revised.revision == 2
    assert revised.payload.metadata.generationCommandId == "command-2"  # type: ignore[union-attr]
    assert revised.payload.metadata.automaticRewriteCount == 0  # type: ignore[union-attr]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("validator_verdict", "expected_status", "expected_summary"),
    [
        ("pass", "skipped", "已由中短篇全稿审核覆盖"),
        ("revise", "pending", None),
    ],
)
async def test_short_story_apply_rechecks_and_writes_only_unique_chapter(
    repository: ReviewRepository,
    validator_verdict: str,
    expected_status: str,
    expected_summary: str | None,
) -> None:
    created = await repository.create_or_revise("user-1", _draft_request())
    await repository.submit_evaluation("user-1", created.id, _evaluation("编辑"))
    await repository.submit_evaluation(
        "user-1",
        created.id,
        _evaluation("校验", verdict=validator_verdict),
    )
    await repository.create_or_revise(
        "user-1", _draft_request(status="awaiting_user")
    )
    artifact = await repository.require_artifact("user-1", created.id)
    await repository.transition(created.id, "awaiting_user", "applying")

    writes = FormalWriteRepository(repository._session_factory)  # noqa: SLF001
    assert await writes.apply_chapter(artifact, "user-1", "甲" * 6000) == 1

    async with repository._session_factory() as session:  # noqa: SLF001
        chapter = await session.get(Chapter, "chapter-1")
        check = await session.scalar(
            select(ChapterQualityCheck).where(
                ChapterQualityCheck.chapterId == "chapter-1"
            )
        )
    assert chapter is not None
    assert chapter.content == "甲" * 6000
    assert chapter.status == "drafting"
    assert check is not None
    assert check.status == expected_status
    assert check.summary == expected_summary
    if validator_verdict == "pass":
        assert json.loads(check.result or "{}")["artifactId"] == created.id


@pytest.mark.asyncio
async def test_short_story_apply_locks_bible_before_selecting_outline(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _draft_request())
    await repository.submit_evaluation("user-1", created.id, _evaluation("编辑"))
    await repository.submit_evaluation("user-1", created.id, _evaluation("校验"))
    await repository.create_or_revise(
        "user-1", _draft_request(status="awaiting_user")
    )
    artifact = await repository.require_artifact("user-1", created.id)
    await repository.transition(created.id, "awaiting_user", "applying")

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
        await FormalWriteRepository(repository._session_factory).apply_chapter(  # noqa: SLF001
            artifact,
            "user-1",
            "甲" * 6000,
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record_statement)

    bible_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.lstrip().upper().startswith("SELECT") and '"WritingBible"' in statement
    )
    outline_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.lstrip().upper().startswith("SELECT")
        and '"ReviewArtifact"' in statement
        and 'kind = ?' in statement
    )
    assert bible_index < outline_index


@pytest.mark.asyncio
async def test_short_story_apply_skips_newer_legacy_outline(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _draft_request())
    await repository.submit_evaluation("user-1", created.id, _evaluation("编辑"))
    await repository.submit_evaluation("user-1", created.id, _evaluation("校验"))
    await repository.create_or_revise(
        "user-1", _draft_request(status="awaiting_user")
    )
    artifact = await repository.require_artifact("user-1", created.id)
    await repository.transition(created.id, "awaiting_user", "applying")
    await _add_newer_legacy_outline(repository)

    writes = FormalWriteRepository(repository._session_factory)  # noqa: SLF001
    assert await writes.apply_chapter(artifact, "user-1", "甲" * 6000) == 1

    async with repository._session_factory() as session:  # noqa: SLF001
        chapter = await session.get(Chapter, "chapter-1")
    assert chapter is not None
    assert chapter.content == "甲" * 6000


@pytest.mark.asyncio
async def test_short_story_apply_rejects_newer_malformed_outline_without_writing(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _draft_request())
    artifact = await repository.require_artifact("user-1", created.id)
    await _add_newer_malformed_outline(repository)

    with pytest.raises(ApiError) as caught:
        await FormalWriteRepository(repository._session_factory).apply_chapter(  # noqa: SLF001
            artifact,
            "user-1",
            "甲" * 6000,
        )

    assert caught.value.code == "SHORT_OUTLINE_PAYLOAD_INVALID"
    async with repository._session_factory() as session:  # noqa: SLF001
        chapter = await session.get(Chapter, "chapter-1")
    assert chapter is not None
    assert chapter.content == ""


@pytest.mark.asyncio
async def test_short_story_apply_rejects_changed_chapter_baseline(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _draft_request())
    await repository.submit_evaluation("user-1", created.id, _evaluation("编辑"))
    await repository.submit_evaluation("user-1", created.id, _evaluation("校验"))
    artifact = await repository.require_artifact("user-1", created.id)
    await repository.transition(created.id, "under_review", "awaiting_user")
    await repository.transition(created.id, "awaiting_user", "applying")
    async with repository._session_factory() as session:  # noqa: SLF001
        async with session.begin():
            chapter = await session.get(Chapter, "chapter-1")
            assert chapter is not None
            chapter.content = "用户已经修改正文"

    with pytest.raises(ApiError) as caught:
        await FormalWriteRepository(repository._session_factory).apply_chapter(  # noqa: SLF001
            artifact,
            "user-1",
            "甲" * 6000,
        )
    assert caught.value.code == "SHORT_STORY_CHAPTER_BASE_CHANGED"


@pytest.mark.asyncio
async def test_short_story_workspace_read_model_exposes_task_command_session_and_reviews(
    repository: ReviewRepository,
) -> None:
    created = await repository.create_or_revise("user-1", _draft_request())
    await repository.submit_evaluation("user-1", created.id, _evaluation("编辑"))

    result = await repository.get_short_story_artifacts("user-1", "novel-1")

    assert result.outline is not None
    assert result.outline.id == "outline-1"
    assert result.chapterDraft is not None
    assert result.chapterDraft.id == created.id
    assert result.chapterDraft.evaluations[0].evaluatorAgent == "编辑"
    assert result.latestTask is not None
    assert result.latestTask.id == "task-1"
    assert result.latestTask.operation == "write_short_story"
    assert result.latestTask.latestCommandId == "command-1"
    assert result.latestTask.latestCommandStatus == "processing"
    assert result.latestTask.activeArtifactId == created.id
    assert result.workflowSession is not None
    assert result.workflowSession.id == "session-1"
    assert result.workflowSession.currentTask is not None
    assert result.workflowSession.currentTask.id == "task-1"


@pytest.mark.asyncio
async def test_short_story_workspace_ignores_legacy_untyped_artifacts(
    repository: ReviewRepository,
) -> None:
    async with repository._session_factory() as session:  # noqa: SLF001
        async with session.begin():
            session.add(
                ReviewArtifact(
                    id="zz-legacy-outline",
                    novelId="novel-1",
                    chapterId="chapter-1",
                    kind="outline_draft",
                    status="awaiting_user",
                    revision=1,
                    payloadJson=json.dumps(
                        {"kind": "outline_draft", "content": "旧流程自由文本大纲"},
                        ensure_ascii=False,
                    ),
                )
            )

    result = await repository.get_short_story_artifacts("user-1", "novel-1")

    assert result.outline is not None
    assert result.outline.id == "outline-1"


@pytest.mark.asyncio
async def test_legacy_short_story_with_multiple_chapters_can_open_read_model(
    repository: ReviewRepository,
) -> None:
    async with repository._session_factory() as session:  # noqa: SLF001
        async with session.begin():
            session.add(
                Chapter(
                    id="chapter-legacy-2",
                    novelId="novel-1",
                    order=2,
                    status="drafting",
                    title="旧项目第二章",
                    content="旧正文",
                )
            )

    result = await repository.get_short_story_artifacts("user-1", "novel-1")

    assert result.outline is not None
    assert result.latestTask is not None
    assert result.workflowSession is not None
